import os, json, time, math, random, threading
import tkinter as tk
from collections import deque
import sys
from pathlib import Path


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR   = get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

SYSTEM_NAME = "L.E.O"
MODEL_BADGE = "MARK XXXXX"
SUBTITLE    = "Linguistic Executive Officer"

# ── Colour palette ──────────────────────────────────────────────
C_BG     = "#0a0a0a"
C_PRI    = "#00d4ff"
C_MID    = "#007a99"
C_DIM    = "#003344"
C_DIMMER = "#0d1117"
C_ACC    = "#ff6600"
C_ACC2   = "#ffcc00"
C_TEXT   = "#8ffcff"
C_PANEL  = "#010c10"
C_GREEN  = "#00ff88"
C_RED    = "#ff3333"
C_GLOW1  = "#00ffcc"
C_GLOW2  = "#0088ff"


class LeoUI:
    """Spherical waveform UI for LEO — 3D wireframe sphere synced with voice."""

    def __init__(self, size=None):
        self.root = tk.Tk()
        self.root.title("L.E.O — MARK XXXXX")
        self.root.resizable(False, False)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        W  = min(sw, 1024)
        H  = min(sh, 820)
        self.root.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        self.root.configure(bg=C_BG)

        self.W = W
        self.H = H

        # Sphere settings
        self.SPHERE_R     = min(int(H * 0.22), 180)
        self.FCX          = W // 2
        self.FCY          = int(H * 0.38)
        self.LAT_STEPS    = 14
        self.LON_STEPS    = 20

        # State
        self.speaking     = False
        self.listening    = False
        self.tick         = 0
        self.last_t       = time.time()

        # Real audio amplitude (0.0 – 1.0), fed from main engine
        self._audio_level  = 0.0
        self._audio_smooth = 0.0    # smoothed for sphere
        self._audio_peak   = 0.0    # peak hold for bars
        self._audio_lock   = threading.Lock()

        # Sphere rotation angles
        self.rot_x = 0.0
        self.rot_y = 0.0
        self.rot_z = 0.0

        # Vertex displacement amplitudes (for waveform effect)
        self._displacements = [0.0] * ((self.LAT_STEPS + 1) * (self.LON_STEPS + 1))
        self._target_displacements = [0.0] * len(self._displacements)

        # Pulse effects
        self.pulse_r = [0.0, self.SPHERE_R * 0.4, self.SPHERE_R * 0.8]

        # Status
        self.status_text  = "INITIALISING"
        self.status_blink = True

        # Audio visualizer bars
        self.NUM_BARS    = 48
        self._bar_heights = [3] * self.NUM_BARS
        self._bar_targets = [3] * self.NUM_BARS

        # Log / typing
        self.typing_queue = deque()
        self.is_typing    = False

        # Build canvas
        self.bg = tk.Canvas(self.root, width=W, height=H,
                            bg=C_BG, highlightthickness=0)
        self.bg.place(x=0, y=0)

        # Log panel
        LW = int(W * 0.72)
        LH = 130
        self.log_frame = tk.Frame(self.root, bg=C_PANEL,
                                   highlightbackground=C_MID,
                                   highlightthickness=1)
        self.log_frame.place(x=(W - LW) // 2, y=H - LH - 36, width=LW, height=LH)
        self.log_text = tk.Text(self.log_frame, fg=C_TEXT, bg=C_PANEL,
                                insertbackground=C_TEXT, borderwidth=0,
                                wrap="word", font=("Consolas", 10), padx=10, pady=6)
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")
        self.log_text.tag_config("you", foreground="#e8e8e8")
        self.log_text.tag_config("ai",  foreground=C_PRI)
        self.log_text.tag_config("sys", foreground=C_ACC2)

        # API key check
        self._api_key_ready = self._api_keys_exist()
        if not self._api_key_ready:
            self._show_setup_ui()

        # Pre-compute sphere vertices
        self._build_sphere()

        # Start animation
        self._animate()
        self.root.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))

    # ── Sphere geometry ─────────────────────────────────────────
    def _build_sphere(self):
        """Pre-compute base sphere vertices (unit sphere) and edge list."""
        self._vertices = []  # (θ, φ) for each vertex
        lats = self.LAT_STEPS
        lons = self.LON_STEPS

        for i in range(lats + 1):
            theta = math.pi * i / lats  # 0 → π
            for j in range(lons + 1):
                phi = 2 * math.pi * j / lons  # 0 → 2π
                self._vertices.append((theta, phi))

        # Edges: connect grid
        self._lat_edges = []  # latitude lines
        self._lon_edges = []  # longitude lines
        for i in range(lats + 1):
            for j in range(lons):
                a = i * (lons + 1) + j
                b = a + 1
                self._lat_edges.append((a, b))
        for i in range(lats):
            for j in range(lons + 1):
                a = i * (lons + 1) + j
                b = (i + 1) * (lons + 1) + j
                self._lon_edges.append((a, b))

        self._displacements = [0.0] * len(self._vertices)
        self._target_displacements = [0.0] * len(self._vertices)

    def _project(self, x3d, y3d, z3d):
        """Rotate and project 3D → 2D."""
        # Rotate around Y
        cos_y = math.cos(self.rot_y)
        sin_y = math.sin(self.rot_y)
        x1 = x3d * cos_y + z3d * sin_y
        z1 = -x3d * sin_y + z3d * cos_y

        # Rotate around X
        cos_x = math.cos(self.rot_x)
        sin_x = math.sin(self.rot_x)
        y1 = y3d * cos_x - z1 * sin_x
        z2 = y3d * sin_x + z1 * cos_x

        # Perspective (mild)
        fov    = 600
        depth  = z2 + 3.0
        scale  = fov / (fov + depth * 80)

        sx = self.FCX + x1 * self.SPHERE_R * scale
        sy = self.FCY + y1 * self.SPHERE_R * scale
        return sx, sy, z2

    def _get_vertex_3d(self, idx):
        """Get displaced 3D vertex position."""
        theta, phi = self._vertices[idx]
        r = 1.0 + self._displacements[idx]
        x = r * math.sin(theta) * math.cos(phi)
        y = r * math.cos(theta)
        z = r * math.sin(theta) * math.sin(phi)
        return x, y, z

    # ── Animation ───────────────────────────────────────────────
    @staticmethod
    def _ac(r, g, b, a):
        f = a / 255.0
        return f"#{int(r*f):02x}{int(g*f):02x}{int(b*f):02x}"

    def _animate(self):
        self.tick += 1
        t   = self.tick
        now = time.time()

        # ── Read real audio level (thread-safe) ────────────────
        with self._audio_lock:
            raw_level = self._audio_level

        # Smooth the audio level for sphere deformation
        active = self.speaking or self.listening
        if active and raw_level > 0.01:
            self._audio_smooth += (raw_level - self._audio_smooth) * 0.45
        else:
            self._audio_smooth *= 0.85  # decay fast when silent

        self._audio_peak = max(self._audio_peak * 0.92, raw_level)
        amp = self._audio_smooth  # 0..1 normalized amplitude

        # Sphere rotation — faster when speaking
        if self.speaking:
            self.rot_y += 0.02 + amp * 0.03
            self.rot_x += 0.006 + amp * 0.01
        elif self.listening:
            self.rot_y += 0.012
            self.rot_x += 0.004
        else:
            self.rot_y += 0.006
            self.rot_x += 0.002

        # ── Vertex displacements driven by real audio ──────────
        for i, (theta, phi) in enumerate(self._vertices):
            if active and amp > 0.02:
                # Mix of audio-reactive wave and spatial variation
                wave = math.sin(theta * 3 + t * 0.12) * math.cos(phi * 2 + t * 0.08)
                band = math.sin(phi * 4 + t * 0.2) * 0.5 + 0.5  # per-vertex variety
                self._target_displacements[i] = wave * amp * 0.35 + band * amp * 0.15
            else:
                # Gentle idle breathing
                wave = math.sin(theta * 2 + t * 0.03) * math.cos(phi * 1.5 + t * 0.02)
                self._target_displacements[i] = wave * 0.025

        # Smooth interpolation of displacements
        lerp = 0.5 if active else 0.12
        for i in range(len(self._displacements)):
            self._displacements[i] += (self._target_displacements[i] - self._displacements[i]) * lerp

        # Pulse ring animation — spawn more when speaking loud
        pspd  = 2.0 + amp * 4.0 if active else 1.2
        limit = self.SPHERE_R * 1.8
        new_p = [r + pspd for r in self.pulse_r if r + pspd < limit]
        spawn_chance = (0.12 + amp * 0.3) if active else 0.02
        if len(new_p) < 4 and random.random() < spawn_chance:
            new_p.append(0.0)
        self.pulse_r = new_p

        # ── Audio bars driven by real amplitude ────────────────
        for i in range(self.NUM_BARS):
            if active and amp > 0.02:
                # Each bar gets a slightly different height based on its position
                phase = math.sin(i * 0.35 + t * 0.15)
                base  = int(amp * 24 * (0.5 + 0.5 * abs(phase)))
                jitter = random.randint(-2, 2) if amp > 0.1 else 0
                self._bar_targets[i] = max(2, min(28, base + jitter))
            else:
                self._bar_targets[i] = int(3 + 1.5 * math.sin(t * 0.04 + i * 0.5))
            self._bar_heights[i] += int((self._bar_targets[i] - self._bar_heights[i]) * 0.5)

        # Status blink
        if t % 40 == 0:
            self.status_blink = not self.status_blink

        self._draw()
        self.root.after(16, self._animate)

    # ── Drawing ─────────────────────────────────────────────────
    def _draw(self):
        c    = self.bg
        W, H = self.W, self.H
        t    = self.tick
        FCX  = self.FCX
        FCY  = self.FCY
        c.delete("all")

        # Subtle dot grid
        for x in range(0, W, 50):
            for y in range(0, H, 50):
                c.create_rectangle(x, y, x+1, y+1, fill=C_DIMMER, outline="")

        # Glow behind sphere
        glow_r = int(self.SPHERE_R * 1.3)
        for i in range(6, 0, -1):
            r = int(glow_r * i / 6)
            frac = i / 6
            a = max(0, min(255, int(35 * frac if not self.speaking else 65 * frac)))
            c.create_oval(FCX-r, FCY-r, FCX+r, FCY+r,
                          fill=self._ac(0, 40, 80, a), outline="")

        # Pulse rings
        for pr in self.pulse_r:
            pa = max(0, int(180 * (1.0 - pr / (self.SPHERE_R * 1.8))))
            r  = int(pr)
            if r > 0:
                c.create_oval(FCX-r, FCY-r, FCX+r, FCY+r,
                              outline=self._ac(0, 212, 255, pa), width=1)

        # ── Draw sphere wireframe ───────────────────────────────
        # Project all vertices
        projected = []
        for i in range(len(self._vertices)):
            x3, y3, z3 = self._get_vertex_3d(i)
            sx, sy, sz = self._project(x3, y3, z3)
            projected.append((sx, sy, sz))

        # Draw latitude lines (horizontal rings)
        for a_idx, b_idx in self._lat_edges:
            ax, ay, az = projected[a_idx]
            bx, by, bz = projected[b_idx]
            avg_z = (az + bz) / 2
            # Depth-based alpha: front edges brighter
            depth_alpha = max(30, min(220, int(140 + avg_z * 60)))
            if self.speaking:
                depth_alpha = min(255, depth_alpha + 40)
            col = self._ac(0, 212, 255, depth_alpha)
            c.create_line(ax, ay, bx, by, fill=col, width=1)

        # Draw longitude lines (vertical arcs)
        for a_idx, b_idx in self._lon_edges:
            ax, ay, az = projected[a_idx]
            bx, by, bz = projected[b_idx]
            avg_z = (az + bz) / 2
            depth_alpha = max(20, min(200, int(120 + avg_z * 50)))
            if self.speaking:
                depth_alpha = min(255, depth_alpha + 30)
            col = self._ac(0, 180, 220, depth_alpha)
            c.create_line(ax, ay, bx, by, fill=col, width=1)

        # Draw bright dots at vertices (front-facing only)
        for sx, sy, sz in projected:
            if sz > -0.3:
                dot_a = max(0, min(255, int(100 + sz * 120)))
                if self.speaking:
                    dot_a = min(255, dot_a + 60)
                dot_r = 2 if sz > 0.3 else 1
                col = self._ac(0, 255, 200, dot_a)
                c.create_oval(sx-dot_r, sy-dot_r, sx+dot_r, sy+dot_r,
                              fill=col, outline="")

        # ── Concentric ring ornaments ───────────────────────────
        for ring_r_frac, w, arc_len, gap in [(1.35, 2, 90, 60), (1.45, 1, 60, 50)]:
            ring_r = int(self.SPHERE_R * ring_r_frac)
            spin   = (t * (0.8 if self.speaking else 0.3)) % 360
            a_val  = 100 if self.speaking else 60
            col    = self._ac(0, 212, 255, a_val)
            seg    = arc_len + gap
            for s in range(360 // seg):
                start = (spin + s * seg) % 360
                c.create_arc(FCX-ring_r, FCY-ring_r, FCX+ring_r, FCY+ring_r,
                             start=start, extent=arc_len,
                             outline=col, width=w, style="arc")

        # Tick marks around outer ring
        tick_r_out = int(self.SPHERE_R * 1.48)
        tick_r_in  = int(self.SPHERE_R * 1.44)
        tick_col   = self._ac(0, 212, 255, 80)
        for deg in range(0, 360, 15):
            rad = math.radians(deg)
            inn = tick_r_in if deg % 45 == 0 else tick_r_in + 3
            c.create_line(FCX + tick_r_out * math.cos(rad), FCY - tick_r_out * math.sin(rad),
                          FCX + inn * math.cos(rad),        FCY - inn * math.sin(rad),
                          fill=tick_col, width=1)

        # ── Header bar ─────────────────────────────────────────
        HDR = 60
        c.create_rectangle(0, 0, W, HDR, fill="#050a0e", outline="")
        c.create_line(0, HDR, W, HDR, fill=C_MID, width=1)
        c.create_text(W // 2, 20, text=SYSTEM_NAME,
                      fill=C_PRI, font=("Consolas", 20, "bold"))
        c.create_text(W // 2, 42, text=SUBTITLE,
                      fill=C_MID, font=("Consolas", 9))
        c.create_text(16, 30, text=MODEL_BADGE,
                      fill=C_DIM, font=("Consolas", 9), anchor="w")
        c.create_text(W - 16, 30, text=time.strftime("%H:%M:%S"),
                      fill=C_PRI, font=("Consolas", 14, "bold"), anchor="e")

        # ── Status indicator ────────────────────────────────────
        sy = FCY + self.SPHERE_R + 60
        if self.speaking:
            stat, sc = "● SPEAKING", C_ACC
        elif self.listening:
            stat, sc = "● LISTENING", C_GREEN
        else:
            sym = "●" if self.status_blink else "○"
            stat, sc = f"{sym} {self.status_text}", C_PRI

        c.create_text(W // 2, sy, text=stat,
                      fill=sc, font=("Consolas", 11, "bold"))

        # ── Audio visualizer bars ───────────────────────────────
        wy = sy + 22
        BH = 22
        bw = 7
        total_w = self.NUM_BARS * bw
        wx0 = (W - total_w) // 2
        for i in range(self.NUM_BARS):
            hb  = self._bar_heights[i]
            if self.speaking:
                col = C_PRI if hb > BH * 0.5 else C_MID
            else:
                col = C_DIM
            bx = wx0 + i * bw
            c.create_rectangle(bx, wy + BH - hb, bx + bw - 2, wy + BH,
                               fill=col, outline="")

        # ── Footer ──────────────────────────────────────────────
        c.create_rectangle(0, H - 28, W, H, fill="#050a0e", outline="")
        c.create_line(0, H - 28, W, H - 28, fill=C_DIM, width=1)
        c.create_text(W // 2, H - 14, fill=C_DIM, font=("Consolas", 8),
                      text="LEO Systems  ·  CLASSIFIED  ·  MARK XXXXX")

    # ── Log system ──────────────────────────────────────────────
    def write_log(self, text: str):
        self.typing_queue.append(text)
        tl = text.lower()
        self.status_text = ("PROCESSING" if tl.startswith("you:")
                            else "RESPONDING" if tl.startswith("ai:")
                            else self.status_text)
        if not self.is_typing:
            self._start_typing()

    def _start_typing(self):
        if not self.typing_queue:
            self.is_typing = False
            if not self.speaking:
                self.status_text = "ONLINE"
            return
        self.is_typing = True
        text = self.typing_queue.popleft()
        tl   = text.lower()
        tag  = "you" if tl.startswith("you:") else "ai" if tl.startswith("ai:") else "sys"
        self.log_text.configure(state="normal")
        self._type_char(text, 0, tag)

    def _type_char(self, text, i, tag):
        if i < len(text):
            self.log_text.insert(tk.END, text[i], tag)
            self.log_text.see(tk.END)
            self.root.after(8, self._type_char, text, i + 1, tag)
        else:
            self.log_text.insert(tk.END, "\n")
            self.log_text.configure(state="disabled")
            self.root.after(25, self._start_typing)

    # ── Speaking / listening state ──────────────────────────────
    def start_speaking(self):
        self.speaking    = True
        self.listening   = False
        self.status_text = "SPEAKING"

    def stop_speaking(self):
        self.speaking    = False
        self.status_text = "ONLINE"

    def set_listening(self, val: bool):
        self.listening = val
        if val and not self.speaking:
            self.status_text = "LISTENING"

    def set_audio_level(self, level: float):
        """Called from audio pipeline with RMS amplitude 0.0–1.0."""
        with self._audio_lock:
            self._audio_level = max(0.0, min(1.0, level))

    # ── API key setup ───────────────────────────────────────────
    def _api_keys_exist(self):
        return API_FILE.exists()

    def wait_for_api_key(self):
        """Block until API key is saved (called from runner thread)."""
        while not self._api_key_ready:
            time.sleep(0.1)

    def _show_setup_ui(self):
        self.setup_frame = tk.Frame(
            self.root, bg="#050a0e",
            highlightbackground=C_PRI, highlightthickness=1
        )
        self.setup_frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(self.setup_frame, text="◈  INITIALISATION REQUIRED",
                 fg=C_PRI, bg="#050a0e", font=("Consolas", 13, "bold")).pack(pady=(18, 4))
        tk.Label(self.setup_frame,
                 text="Enter your Gemini API key to boot L.E.O.",
                 fg=C_MID, bg="#050a0e", font=("Consolas", 9)).pack(pady=(0, 10))

        tk.Label(self.setup_frame, text="GEMINI API KEY",
                 fg=C_DIM, bg="#050a0e", font=("Consolas", 9)).pack(pady=(8, 2))
        self.gemini_entry = tk.Entry(
            self.setup_frame, width=52, fg=C_TEXT, bg="#000d12",
            insertbackground=C_TEXT, borderwidth=0, font=("Consolas", 10), show="*"
        )
        self.gemini_entry.pack(pady=(0, 4))

        tk.Button(
            self.setup_frame, text="▸  INITIALISE SYSTEMS",
            command=self._save_api_keys, bg=C_BG, fg=C_PRI,
            activebackground="#003344", font=("Consolas", 10),
            borderwidth=0, pady=8
        ).pack(pady=14)

    def _save_api_keys(self):
        gemini = self.gemini_entry.get().strip()
        if not gemini:
            return
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(API_FILE, "w", encoding="utf-8") as f:
            json.dump({"gemini_api_key": gemini}, f, indent=4)
        self.setup_frame.destroy()
        self._api_key_ready = True
        self.status_text = "ONLINE"
        self.write_log("SYS: Systems initialised. LEO online.")
