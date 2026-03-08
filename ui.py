import os, json, time, math, random, threading
import tkinter as tk
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
MODEL_BADGE = "MARK X"
SUBTITLE    = "Linguistic Executive Officer"

# ── Purple gradient palette ─────────────────────────────────────
C_BG     = "#0a0012"       # deep purple-black
C_PRI    = "#b44aff"       # vivid purple
C_PRI2   = "#7c3aed"       # deeper purple
C_MID    = "#6d28d9"       # mid purple
C_DIM    = "#3b0764"       # dim purple
C_DIMMER = "#0f0018"       # near-black purple
C_ACC    = "#e879f9"       # pink-purple accent
C_ACC2   = "#c084fc"       # light purple accent
C_TEXT   = "#e0d4ff"       # soft lavender text
C_GREEN  = "#a78bfa"       # muted purple-green
C_RED    = "#f472b6"       # pink-red
C_GLOW1  = "#a855f7"       # glow purple 1
C_GLOW2  = "#7c3aed"       # glow purple 2


class LeoUI:
    """Dot-particle sphere UI for LEO — purple gradient theme."""

    def __init__(self, size=None):
        self.root = tk.Tk()
        self.root.title("L.E.O — MARK X")
        self.root.resizable(False, False)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        W  = min(sw, 1024)
        H  = min(sh, 820)
        self.root.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        self.root.configure(bg=C_BG)

        self.W = W
        self.H = H

        # Sphere settings (larger since no log panel)
        self.SPHERE_R     = min(int(H * 0.30), 240)
        self.FCX          = W // 2
        self.FCY          = int(H * 0.45)
        self.LAT_STEPS    = 18
        self.LON_STEPS    = 24

        # State
        self.speaking     = False
        self.listening    = False
        self.tick         = 0

        # Real audio amplitude (0.0 – 1.0), fed from main engine
        self._audio_level  = 0.0
        self._audio_smooth = 0.0
        self._audio_peak   = 0.0
        self._audio_lock   = threading.Lock()

        # Sphere rotation angles
        self.rot_x = 0.0
        self.rot_y = 0.0

        # Vertex displacement amplitudes
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

        # Build canvas
        self.bg = tk.Canvas(self.root, width=W, height=H,
                            bg=C_BG, highlightthickness=0)
        self.bg.place(x=0, y=0)

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
        """Pre-compute base sphere vertices (unit sphere)."""
        self._vertices = []
        lats = self.LAT_STEPS
        lons = self.LON_STEPS

        for i in range(lats + 1):
            theta = math.pi * i / lats
            for j in range(lons + 1):
                phi = 2 * math.pi * j / lons
                self._vertices.append((theta, phi))

        self._displacements = [0.0] * len(self._vertices)
        self._target_displacements = [0.0] * len(self._vertices)

    def _project(self, x3d, y3d, z3d):
        """Rotate and project 3D → 2D."""
        cos_y = math.cos(self.rot_y)
        sin_y = math.sin(self.rot_y)
        x1 = x3d * cos_y + z3d * sin_y
        z1 = -x3d * sin_y + z3d * cos_y

        cos_x = math.cos(self.rot_x)
        sin_x = math.sin(self.rot_x)
        y1 = y3d * cos_x - z1 * sin_x
        z2 = y3d * sin_x + z1 * cos_x

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
        t = self.tick

        # ── Read real audio level (thread-safe) ────────────────
        with self._audio_lock:
            raw_level = self._audio_level

        active = self.speaking or self.listening
        if active and raw_level > 0.01:
            self._audio_smooth += (raw_level - self._audio_smooth) * 0.45
        else:
            self._audio_smooth *= 0.85

        self._audio_peak = max(self._audio_peak * 0.92, raw_level)
        amp = self._audio_smooth

        # Sphere rotation
        if self.speaking:
            self.rot_y += 0.018 + amp * 0.03
            self.rot_x += 0.005 + amp * 0.01
        elif self.listening:
            self.rot_y += 0.012
            self.rot_x += 0.004
        else:
            self.rot_y += 0.005
            self.rot_x += 0.002

        # ── Vertex displacements driven by audio ───────────────
        for i, (theta, phi) in enumerate(self._vertices):
            if active and amp > 0.02:
                wave = math.sin(theta * 3 + t * 0.12) * math.cos(phi * 2 + t * 0.08)
                band = math.sin(phi * 4 + t * 0.2) * 0.5 + 0.5
                self._target_displacements[i] = wave * amp * 0.4 + band * amp * 0.2
            else:
                wave = math.sin(theta * 2 + t * 0.03) * math.cos(phi * 1.5 + t * 0.02)
                self._target_displacements[i] = wave * 0.02

        lerp = 0.5 if active else 0.12
        for i in range(len(self._displacements)):
            self._displacements[i] += (self._target_displacements[i] - self._displacements[i]) * lerp

        # Pulse rings
        pspd  = 2.0 + amp * 4.0 if active else 1.2
        limit = self.SPHERE_R * 1.8
        new_p = [r + pspd for r in self.pulse_r if r + pspd < limit]
        spawn_chance = (0.12 + amp * 0.3) if active else 0.02
        if len(new_p) < 4 and random.random() < spawn_chance:
            new_p.append(0.0)
        self.pulse_r = new_p

        # ── Audio bars driven by amplitude ─────────────────────
        for i in range(self.NUM_BARS):
            if active and amp > 0.02:
                phase = math.sin(i * 0.35 + t * 0.15)
                base  = int(amp * 26 * (0.5 + 0.5 * abs(phase)))
                jitter = random.randint(-2, 2) if amp > 0.1 else 0
                self._bar_targets[i] = max(2, min(30, base + jitter))
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

        # ── Background radial glow (purple gradient) ───────────
        glow_r = int(self.SPHERE_R * 1.6)
        for i in range(8, 0, -1):
            r = int(glow_r * i / 8)
            frac = i / 8
            a = max(0, min(255, int(50 * frac if not (self.speaking or self.listening) else 90 * frac)))
            # Purple glow: mix of (100, 20, 180) at centre
            c.create_oval(FCX-r, FCY-r, FCX+r, FCY+r,
                          fill=self._ac(100, 20, 180, a), outline="")

        # ── Pulse rings ────────────────────────────────────────
        for pr in self.pulse_r:
            pa = max(0, int(160 * (1.0 - pr / (self.SPHERE_R * 1.8))))
            r  = int(pr)
            if r > 0:
                c.create_oval(FCX-r, FCY-r, FCX+r, FCY+r,
                              outline=self._ac(180, 74, 255, pa), width=1)

        # ── Draw sphere as dots ────────────────────────────────
        projected = []
        for i in range(len(self._vertices)):
            x3, y3, z3 = self._get_vertex_3d(i)
            sx, sy, sz = self._project(x3, y3, z3)
            projected.append((sx, sy, sz))

        # Sort by depth (back to front) for proper layering
        indexed = sorted(enumerate(projected), key=lambda x: x[1][2])

        for idx, (sx, sy, sz) in indexed:
            # Depth-based size: front dots bigger, back dots smaller
            if sz < -0.6:
                continue  # skip very back-facing dots

            depth_norm = (sz + 1.0) / 2.0  # 0 (back) to 1 (front)
            depth_norm = max(0.0, min(1.0, depth_norm))

            # Dot size: 1 to 5 pixels based on depth
            dot_r = 1.0 + depth_norm * 3.5

            # When speaking, dots grow more
            if self.speaking or self.listening:
                amp = self._audio_smooth
                dot_r += amp * 2.0

            # Colour: gradient from dim purple (back) to bright pink-purple (front)
            # Back: (60, 20, 120),  Front: (228, 121, 249)
            r_col = int(60 + depth_norm * 168)
            g_col = int(20 + depth_norm * 101)
            b_col = int(120 + depth_norm * 129)

            # Brighten when speaking
            if (self.speaking or self.listening) and self._audio_smooth > 0.05:
                boost = min(1.0, self._audio_smooth * 2)
                r_col = min(255, int(r_col + boost * 40))
                g_col = min(255, int(g_col + boost * 30))
                b_col = min(255, int(b_col + boost * 20))

            alpha = max(40, min(255, int(80 + depth_norm * 175)))
            col = self._ac(r_col, g_col, b_col, alpha)

            c.create_oval(sx - dot_r, sy - dot_r, sx + dot_r, sy + dot_r,
                          fill=col, outline="")

        # ── Concentric ring ornaments (purple) ──────────────────
        for ring_r_frac, w, arc_len, gap in [(1.40, 2, 80, 65), (1.52, 1, 55, 55)]:
            ring_r = int(self.SPHERE_R * ring_r_frac)
            spin   = (t * (0.7 if (self.speaking or self.listening) else 0.25)) % 360
            a_val  = 120 if (self.speaking or self.listening) else 50
            col    = self._ac(180, 74, 255, a_val)
            seg    = arc_len + gap
            for s in range(360 // seg):
                start = (spin + s * seg) % 360
                c.create_arc(FCX-ring_r, FCY-ring_r, FCX+ring_r, FCY+ring_r,
                             start=start, extent=arc_len,
                             outline=col, width=w, style="arc")

        # Tick marks
        tick_r_out = int(self.SPHERE_R * 1.55)
        tick_r_in  = int(self.SPHERE_R * 1.50)
        tick_col   = self._ac(180, 74, 255, 60)
        for deg in range(0, 360, 15):
            rad = math.radians(deg)
            inn = tick_r_in if deg % 45 == 0 else tick_r_in + 3
            c.create_line(FCX + tick_r_out * math.cos(rad), FCY - tick_r_out * math.sin(rad),
                          FCX + inn * math.cos(rad),        FCY - inn * math.sin(rad),
                          fill=tick_col, width=1)

        # ── Header bar ─────────────────────────────────────────
        HDR = 60
        c.create_rectangle(0, 0, W, HDR, fill="#06000e", outline="")
        c.create_line(0, HDR, W, HDR, fill=C_DIM, width=1)
        c.create_text(W // 2, 20, text=SYSTEM_NAME,
                      fill=C_PRI, font=("Consolas", 20, "bold"))
        c.create_text(W // 2, 42, text=SUBTITLE,
                      fill=C_MID, font=("Consolas", 9))
        c.create_text(16, 30, text=MODEL_BADGE,
                      fill=C_DIM, font=("Consolas", 9), anchor="w")
        c.create_text(W - 16, 30, text=time.strftime("%H:%M:%S"),
                      fill=C_PRI, font=("Consolas", 14, "bold"), anchor="e")

        # ── Status indicator ───────────────────────────────────
        sy = FCY + self.SPHERE_R + 70
        if self.speaking:
            stat, sc = "● SPEAKING", C_ACC
        elif self.listening:
            stat, sc = "● LISTENING", C_GREEN
        else:
            sym = "●" if self.status_blink else "○"
            stat, sc = f"{sym} {self.status_text}", C_PRI

        c.create_text(W // 2, sy, text=stat,
                      fill=sc, font=("Consolas", 12, "bold"))

        # ── Audio visualizer bars (purple) ─────────────────────
        wy = sy + 28
        BH = 24
        bw = 7
        total_w = self.NUM_BARS * bw
        wx0 = (W - total_w) // 2
        for i in range(self.NUM_BARS):
            hb  = self._bar_heights[i]
            if self.speaking or self.listening:
                # Purple to pink gradient per bar height
                frac = min(1.0, hb / BH)
                r_c = int(124 + frac * 108)
                g_c = int(58 + frac * 63)
                b_c = int(237 + frac * 18)
                col = self._ac(r_c, g_c, b_c, 220)
            else:
                col = C_DIM
            bx = wx0 + i * bw
            c.create_rectangle(bx, wy + BH - hb, bx + bw - 2, wy + BH,
                               fill=col, outline="")

        # ── Footer ─────────────────────────────────────────────
        c.create_rectangle(0, H - 28, W, H, fill="#06000e", outline="")
        c.create_line(0, H - 28, W, H - 28, fill=C_DIM, width=1)
        c.create_text(W // 2, H - 14, fill=C_DIM, font=("Consolas", 8),
                      text="LEO Systems  ·  CLASSIFIED  ·  MARK X")

    # ── Log system (now prints to terminal) ─────────────────────
    def write_log(self, text: str):
        """All logs go to terminal stdout instead of UI."""
        print(f"[LEO UI] {text}")
        tl = text.lower()
        if tl.startswith("you:"):
            self.status_text = "PROCESSING"
        elif tl.startswith("leo:") or tl.startswith("ai:"):
            self.status_text = "RESPONDING"

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
            self.root, bg="#06000e",
            highlightbackground=C_PRI, highlightthickness=1
        )
        self.setup_frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(self.setup_frame, text="◈  INITIALISATION REQUIRED",
                 fg=C_PRI, bg="#06000e", font=("Consolas", 13, "bold")).pack(pady=(18, 4))
        tk.Label(self.setup_frame,
                 text="Enter your Gemini API key to boot L.E.O.",
                 fg=C_MID, bg="#06000e", font=("Consolas", 9)).pack(pady=(0, 10))

        tk.Label(self.setup_frame, text="GEMINI API KEY",
                 fg=C_DIM, bg="#06000e", font=("Consolas", 9)).pack(pady=(8, 2))
        self.gemini_entry = tk.Entry(
            self.setup_frame, width=52, fg=C_TEXT, bg="#0f0018",
            insertbackground=C_TEXT, borderwidth=0, font=("Consolas", 10), show="*"
        )
        self.gemini_entry.pack(pady=(0, 4))

        tk.Button(
            self.setup_frame, text="▸  INITIALISE SYSTEMS",
            command=self._save_api_keys, bg=C_BG, fg=C_PRI,
            activebackground=C_DIM, font=("Consolas", 10),
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
        print("[LEO UI] SYS: Systems initialised. LEO online.")
