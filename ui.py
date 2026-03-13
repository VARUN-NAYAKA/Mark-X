import os, json, time, math, random, threading
import tkinter as tk
import sys
from pathlib import Path

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR   = get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

SYSTEM_NAME = "L.E.O"
SUBTITLE    = "Linguistic Executive Officer"

# ── UI 1: Monochrome palette (white-on-black) ──────────────────
C_BG      = "#000000"
C_WHITE   = "#ffffff"
C_GREY1   = "#e0e0e0"
C_GREY2   = "#a0a0a0"
C_GREY3   = "#606060"
C_DIM     = "#303030"
C_DIMMER  = "#181818"
C_GREEN   = "#00ff88"
C_RED     = "#ff4444"
C_ACC     = "#cccccc"

# ── UI 2: Teal / Cyan dashboard palette ────────────────────────
D_BG       = "#0a0e14"       # deep dark blue-black
D_PANEL    = "#0d1117"       # panel background
D_BORDER   = "#00ffcc"       # teal glow
D_BORDER2  = "#00b894"       # dimmer teal
D_TEXT     = "#e6f5f0"       # light text
D_TEXT_DIM = "#5a7a70"       # dim teal-grey
D_ACCENT   = "#00ffcc"       # primary accent
D_ACCENT2  = "#007a63"       # secondary accent
D_GLOW_BG  = "#0a1f1a"       # subtle glow behind panels


class LeoUI:
    """Dual-mode UI for LEO — Classic sphere (UI 1) + Dashboard (UI 2)."""

    def __init__(self, size=None):
        self.root = tk.Tk()
        self.root.title("LEO")
        self.root.resizable(False, False)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        W  = min(sw, 1024)
        H  = min(sh, 820)
        self.root.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        self.root.configure(bg=C_BG)

        self.W = W
        self.H = H

        # ── UI Mode ────────────────────────────────────────────
        self._ui_mode = 1  # 1 = classic, 2 = dashboard

        # ── Sphere settings ────────────────────────────────────
        self.SPHERE_R     = min(int(H * 0.30), 240)
        self.FCX          = W // 2
        self.FCY          = int(H * 0.46)
        self.LAT_STEPS    = 40
        self.LON_STEPS    = 60

        # State
        self.speaking     = False
        self.listening    = False
        self.tick         = 0

        # Real audio amplitude (0.0 – 1.0)
        self._audio_level  = 0.0
        self._audio_smooth = 0.0
        self._audio_peak   = 0.0
        self._audio_lock   = threading.Lock()

        # Sphere rotation
        self.rot_x = 0.0
        self.rot_y = 0.0

        # Vertex data
        self._displacements = [0.0] * ((self.LAT_STEPS + 1) * (self.LON_STEPS + 1))
        self._target_displacements = [0.0] * len(self._displacements)
        self._noise_phases = []

        # Status
        self.status_text  = "INITIALISING"
        self.status_blink = True

        # ── Dashboard state (UI 2) ─────────────────────────────
        self._chat_log = []         # [(role, text, timestamp), ...]  max 10
        self._spotify_info = {
            "track": "", "artist": "", "album": "",
            "progress": 0, "duration": 0, "is_playing": False,
        }
        self._system_stats = {"cpu": 0, "memory": 0, "network": "ACTIVE"}
        self._stats_tick = 0

        # Canvas
        self.bg = tk.Canvas(self.root, width=W, height=H,
                            bg=C_BG, highlightthickness=0)
        self.bg.place(x=0, y=0)

        # API key check
        self._api_key_ready = self._api_keys_exist()
        if not self._api_key_ready:
            self._show_setup_ui()

        # Build sphere
        self._build_sphere()

        # Start animation
        self._animate()
        self.root.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))

    # ────────────────────────────────────────────────────────────
    #  UI MODE SWITCHING
    # ────────────────────────────────────────────────────────────
    def switch_ui(self, mode: int):
        """Switch between UI 1 (classic) and UI 2 (dashboard)."""
        if mode in (1, 2):
            self._ui_mode = mode
            if mode == 2:
                self.FCX = int(self.W * 0.65)
                self.FCY = int(self.H * 0.48)
                self.SPHERE_R = min(int(self.H * 0.28), 200)
                self.LAT_STEPS = 20   # fewer dots for performance
                self.LON_STEPS = 30
                self.root.configure(bg=D_BG)
                self.bg.configure(bg=D_BG)
            else:
                self.FCX = self.W // 2
                self.FCY = int(self.H * 0.46)
                self.SPHERE_R = min(int(self.H * 0.30), 240)
                self.LAT_STEPS = 40
                self.LON_STEPS = 60
                self.root.configure(bg=C_BG)
                self.bg.configure(bg=C_BG)
            # Rebuild sphere with new density
            self._build_sphere()
            print(f"[LEO UI] Switched to UI {mode}")

    # ────────────────────────────────────────────────────────────
    #  SPHERE GEOMETRY
    # ────────────────────────────────────────────────────────────
    def _build_sphere(self):
        self._vertices = []
        self._noise_phases = []
        lats = self.LAT_STEPS
        lons = self.LON_STEPS

        for i in range(lats + 1):
            theta = math.pi * i / lats
            for j in range(lons + 1):
                phi = 2 * math.pi * j / lons
                self._vertices.append((theta, phi))
                self._noise_phases.append((
                    random.uniform(0, math.pi * 2),
                    random.uniform(0, math.pi * 2),
                    random.uniform(0, math.pi * 2),
                    random.uniform(0.6, 1.4),
                ))

        self._displacements = [0.0] * len(self._vertices)
        self._target_displacements = [0.0] * len(self._vertices)

    def _project(self, x3d, y3d, z3d):
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
        theta, phi = self._vertices[idx]
        r = 1.0 + self._displacements[idx]
        x = r * math.sin(theta) * math.cos(phi)
        y = r * math.cos(theta)
        z = r * math.sin(theta) * math.sin(phi)
        return x, y, z

    # ────────────────────────────────────────────────────────────
    #  ANIMATION LOOP (shared)
    # ────────────────────────────────────────────────────────────
    def _animate(self):
        self.tick += 1
        t = self.tick

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
            self.rot_y += 0.014 + amp * 0.025
            self.rot_x += 0.004 + amp * 0.008
        elif self.listening:
            self.rot_y += 0.010
            self.rot_x += 0.003
        else:
            self.rot_y += 0.004
            self.rot_x += 0.0015

        # Vertex displacements
        time_slow = t * 0.015
        time_mid  = t * 0.04
        time_fast = t * 0.08

        for i, (theta, phi) in enumerate(self._vertices):
            p1, p2, p3, amp_scale = self._noise_phases[i]

            if active and amp > 0.02:
                n1 = math.sin(theta * 3.0 + time_fast + p1) * math.cos(phi * 2.5 + time_fast * 0.7 + p2)
                n2 = math.sin(theta * 5.0 + time_mid * 1.3 + p3) * math.cos(phi * 4.0 + time_mid + p1) * 0.4
                n3 = math.sin(theta * 7.0 + time_fast * 1.5 + p2) * 0.15
                turbulence = (n1 + n2 + n3) * amp_scale
                intensity = amp * 0.55 + self._audio_peak * 0.15
                self._target_displacements[i] = turbulence * intensity
            else:
                n1 = math.sin(theta * 2.0 + time_slow + p1) * math.cos(phi * 1.5 + time_slow * 0.8 + p2)
                n2 = math.sin(theta * 3.5 + time_slow * 1.2 + p3) * 0.3
                breathing = (n1 + n2) * amp_scale
                self._target_displacements[i] = breathing * 0.04

        lerp = 0.4 if active else 0.08
        for i in range(len(self._displacements)):
            self._displacements[i] += (self._target_displacements[i] - self._displacements[i]) * lerp

        if t % 40 == 0:
            self.status_blink = not self.status_blink

        # Update system stats every ~2 seconds (120 frames at 16ms)
        if self._ui_mode == 2:
            self._stats_tick += 1
            if self._stats_tick >= 120:
                self._stats_tick = 0
                self._refresh_system_stats()

        # Dispatch to correct renderer
        if self._ui_mode == 1:
            self._draw_classic()
            self.root.after(16, self._animate)   # 60fps for classic
        else:
            self._draw_dashboard()
            self.root.after(33, self._animate)   # 30fps for dashboard

    # ────────────────────────────────────────────────────────────
    #  UI 1: CLASSIC MONOCHROME SPHERE
    # ────────────────────────────────────────────────────────────
    def _draw_classic(self):
        c    = self.bg
        W, H = self.W, self.H
        t    = self.tick
        FCX  = self.FCX
        FCY  = self.FCY
        c.delete("all")

        active = self.speaking or self.listening
        amp    = self._audio_smooth

        # Background glow
        glow_r = int(self.SPHERE_R * 1.3)
        for i in range(6, 0, -1):
            r = int(glow_r * i / 6)
            frac = i / 6
            brightness = int(12 * frac) if not active else int(20 * frac + amp * 15)
            brightness = min(40, brightness)
            col = f"#{brightness:02x}{brightness:02x}{brightness:02x}"
            c.create_oval(FCX-r, FCY-r, FCX+r, FCY+r, fill=col, outline="")

        # Sphere dots
        projected = []
        for i in range(len(self._vertices)):
            x3, y3, z3 = self._get_vertex_3d(i)
            sx, sy, sz = self._project(x3, y3, z3)
            projected.append((sx, sy, sz))

        indexed = sorted(enumerate(projected), key=lambda x: x[1][2])

        for idx, (sx, sy, sz) in indexed:
            if sz < -0.7:
                continue
            depth_norm = max(0.0, min(1.0, (sz + 1.0) / 2.0))
            dot_r = 0.6 + depth_norm * 2.2
            if active:
                dot_r += amp * 1.2
            base_bright = int(40 + depth_norm * 215)
            if active and amp > 0.03:
                boost = min(1.0, amp * 2.5)
                base_bright = min(255, int(base_bright + boost * 40))
            col = f"#{base_bright:02x}{base_bright:02x}{base_bright:02x}"
            c.create_oval(sx - dot_r, sy - dot_r, sx + dot_r, sy + dot_r,
                          fill=col, outline="")

        # Header
        HDR = 60
        c.create_rectangle(0, 0, W, HDR, fill="#000000", outline="")
        c.create_line(0, HDR, W, HDR, fill=C_DIM, width=1)
        c.create_text(W // 2, 16, text=SYSTEM_NAME,
                      fill=C_WHITE, font=("Consolas", 20, "bold"))
        c.create_text(W // 2, 44, text=SUBTITLE,
                      fill=C_GREY2, font=("Consolas", 9))
        c.create_text(W - 16, 30, text=time.strftime("%H:%M:%S"),
                      fill=C_WHITE, font=("Consolas", 14, "bold"), anchor="e")

        # Status indicator
        sy = FCY + self.SPHERE_R + 70
        if self.speaking:
            stat, sc = "● SPEAKING", C_WHITE
        elif self.listening:
            stat, sc = "● LISTENING", C_GREY1
        else:
            sym = "●" if self.status_blink else "○"
            sc = C_GREEN if self.status_text == "ONLINE" else C_GREY2
            stat = f"{sym} {self.status_text}"
        c.create_text(W // 2, sy, text=stat,
                      fill=sc, font=("Consolas", 12, "bold"))

        # Footer
        c.create_rectangle(0, H - 28, W, H, fill="#000000", outline="")
        c.create_line(0, H - 28, W, H - 28, fill=C_DIM, width=1)
        c.create_text(W // 2, H - 14, fill=C_DIM, font=("Consolas", 8),
                      text="LEO Systems  ·  CLASSIFIED")

    # ────────────────────────────────────────────────────────────
    #  UI 2: PREMIUM DASHBOARD
    # ────────────────────────────────────────────────────────────
    def _draw_dashboard(self):
        c    = self.bg
        W, H = self.W, self.H
        t    = self.tick
        FCX  = self.FCX
        FCY  = self.FCY
        c.delete("all")

        active = self.speaking or self.listening
        amp    = self._audio_smooth

        # ── Background ─────────────────────────────────────────
        c.create_rectangle(0, 0, W, H, fill=D_BG, outline="")

        # ── Holographic orb glow rings ─────────────────────────
        glow_r = int(self.SPHERE_R * 1.5)
        for i in range(8, 0, -1):
            r = int(glow_r * i / 8)
            frac = i / 8
            g_val = int(8 * frac) if not active else int(14 * frac + amp * 10)
            b_val = int(g_val * 1.3)
            g_val = min(30, g_val)
            b_val = min(40, b_val)
            col = f"#00{g_val:02x}{b_val:02x}"
            c.create_oval(FCX-r, FCY-r, FCX+r, FCY+r, fill=col, outline="")

        # Animated glow rings
        for ring in range(3):
            ring_phase = t * 0.02 + ring * 2.1
            ring_r = int(self.SPHERE_R * (1.15 + ring * 0.12 + math.sin(ring_phase) * 0.04))
            pulse = abs(math.sin(ring_phase * 0.5))
            g = int(80 * pulse + amp * 60)
            col = f"#00{min(255, g):02x}{min(200, int(g * 0.8)):02x}"
            c.create_oval(FCX - ring_r, FCY - ring_r,
                          FCX + ring_r, FCY + ring_r,
                          outline=col, width=1)

        # ── Sphere dots (teal/cyan) ────────────────────────────
        projected = []
        for i in range(len(self._vertices)):
            x3, y3, z3 = self._get_vertex_3d(i)
            sx, sy, sz = self._project(x3, y3, z3)
            projected.append((sx, sy, sz))

        indexed = sorted(enumerate(projected), key=lambda x: x[1][2])

        for idx, (sx, sy, sz) in indexed:
            if sz < -0.7:
                continue
            depth_norm = max(0.0, min(1.0, (sz + 1.0) / 2.0))
            dot_r = 0.5 + depth_norm * 2.0
            if active:
                dot_r += amp * 1.0

            # Teal/cyan colour with depth
            g_bright = int(60 + depth_norm * 195)
            b_bright = int(40 + depth_norm * 160)
            if active and amp > 0.03:
                boost = min(1.0, amp * 2.5)
                g_bright = min(255, int(g_bright + boost * 40))
                b_bright = min(200, int(b_bright + boost * 30))
            col = f"#00{g_bright:02x}{b_bright:02x}"
            c.create_oval(sx - dot_r, sy - dot_r, sx + dot_r, sy + dot_r,
                          fill=col, outline="")

        # ── Header ─────────────────────────────────────────────
        HDR = 55
        c.create_rectangle(0, 0, W, HDR, fill=D_BG, outline="")
        # Glowing bottom line
        c.create_line(0, HDR, W, HDR, fill=D_ACCENT2, width=1)
        c.create_line(0, HDR + 1, W, HDR + 1, fill="#003d32", width=1)

        c.create_text(W // 2, 16, text="LEO",
                      fill=D_ACCENT, font=("Consolas", 22, "bold"))
        c.create_text(W // 2, 40, text="AWARENESS INTERFACE v3.14",
                      fill=D_TEXT_DIM, font=("Consolas", 9))

        # Clock
        c.create_text(W - 16, 28, text=time.strftime("%H:%M:%S"),
                      fill=D_ACCENT, font=("Consolas", 14, "bold"), anchor="e")

        # ── LEFT SIDEBAR PANELS ────────────────────────────────
        panel_x = 16
        panel_w = int(W * 0.28)

        self._draw_panel_system_status(c, panel_x, 70, panel_w, 90)
        self._draw_panel_active_task(c, panel_x, 175, panel_w, 105)
        self._draw_panel_spotify(c, panel_x, 295, panel_w, 170)
        self._draw_panel_conversations(c, panel_x, 480, panel_w, H - 480 - 40)

        # ── Status indicator (under orb) ───────────────────────
        sy = FCY + self.SPHERE_R + 50
        if self.speaking:
            stat, sc = "● SPEAKING", D_ACCENT
        elif self.listening:
            stat, sc = "● LISTENING", D_BORDER2
        else:
            sym = "●" if self.status_blink else "○"
            sc = D_ACCENT if self.status_text == "ONLINE" else D_TEXT_DIM
            stat = f"{sym} {self.status_text}"
        c.create_text(FCX, sy, text=stat,
                      fill=sc, font=("Consolas", 11, "bold"))

        # ── Footer ─────────────────────────────────────────────
        c.create_rectangle(0, H - 28, W, H, fill=D_BG, outline="")
        c.create_line(0, H - 28, W, H - 28, fill=D_ACCENT2, width=1)
        c.create_text(W // 2, H - 14, fill=D_TEXT_DIM, font=("Consolas", 8),
                      text="LEO Systems  ·  AWARENESS INTERFACE  ·  CLASSIFIED")

    # ── Glassmorphism panel helper ──────────────────────────────
    def _draw_glass_panel(self, c, x, y, w, h):
        """Draw a glassmorphism panel with glow border."""
        # Outer glow layers
        for i in range(3, 0, -1):
            g = int(15 - i * 4)
            glow_col = f"#00{max(0, g):02x}{max(0, int(g * 0.8)):02x}"
            c.create_rectangle(x - i, y - i, x + w + i, y + h + i,
                               fill="", outline=glow_col, width=1)

        # Panel background
        c.create_rectangle(x, y, x + w, y + h,
                           fill=D_PANEL, outline=D_ACCENT2, width=1)

        # Top highlight line (liquid glass effect)
        c.create_line(x + 1, y + 1, x + w - 1, y + 1,
                      fill="#1a3d35", width=1)
        # Subtle gradient at top
        for i in range(4):
            a = int(12 - i * 3)
            gc = f"#00{max(0, a):02x}{max(0, int(a * 0.8)):02x}"
            c.create_line(x + 1, y + 2 + i, x + w - 1, y + 2 + i,
                          fill=gc, width=1)

    # ── Panel: System Status ───────────────────────────────────
    def _draw_panel_system_status(self, c, x, y, w, h):
        self._draw_glass_panel(c, x, y, w, h)

        # Title
        c.create_text(x + 12, y + 14, text="SYSTEM STATUS",
                      fill=D_ACCENT, font=("Consolas", 10, "bold"), anchor="w")
        # Separator
        c.create_line(x + 8, y + 28, x + w - 8, y + 28, fill=D_ACCENT2, width=1)

        # Network
        c.create_text(x + 12, y + 42, text="Network:",
                      fill=D_TEXT_DIM, font=("Consolas", 9), anchor="w")
        c.create_text(x + 80, y + 42, text=self._system_stats.get("network", "ACTIVE"),
                      fill=D_ACCENT, font=("Consolas", 9, "bold"), anchor="w")

        # CPU
        cpu = self._system_stats.get("cpu", 0)
        c.create_text(x + 12, y + 60, text="CPU:",
                      fill=D_TEXT_DIM, font=("Consolas", 9), anchor="w")
        c.create_text(x + 55, y + 60, text=f"{cpu}%",
                      fill=D_TEXT, font=("Consolas", 10, "bold"), anchor="w")

        # CPU bar
        bar_x = x + 90
        bar_w = w - 108
        c.create_rectangle(bar_x, y + 55, bar_x + bar_w, y + 65,
                           fill="#1a2a25", outline=D_ACCENT2, width=1)
        fill_w = int(bar_w * cpu / 100)
        if fill_w > 0:
            c.create_rectangle(bar_x + 1, y + 56, bar_x + 1 + fill_w, y + 64,
                               fill=D_ACCENT, outline="")

        # Memory
        mem = self._system_stats.get("memory", 0)
        c.create_text(x + 12, y + 78, text="MEM:",
                      fill=D_TEXT_DIM, font=("Consolas", 9), anchor="w")
        c.create_text(x + 55, y + 78, text=f"{mem}%",
                      fill=D_TEXT, font=("Consolas", 10, "bold"), anchor="w")

        # MEM bar
        c.create_rectangle(bar_x, y + 73, bar_x + bar_w, y + 83,
                           fill="#1a2a25", outline=D_ACCENT2, width=1)
        fill_w = int(bar_w * mem / 100)
        if fill_w > 0:
            c.create_rectangle(bar_x + 1, y + 74, bar_x + 1 + fill_w, y + 82,
                               fill=D_BORDER2, outline="")

    # ── Panel: Active Task ─────────────────────────────────────
    def _draw_panel_active_task(self, c, x, y, w, h):
        self._draw_glass_panel(c, x, y, w, h)

        c.create_text(x + 12, y + 14, text="ACTIVE TASK",
                      fill=D_ACCENT, font=("Consolas", 10, "bold"), anchor="w")

        # Three dots menu icon
        for dot_i in range(3):
            dx = x + w - 20 + dot_i * 6
            c.create_oval(dx, y + 12, dx + 3, y + 15, fill=D_TEXT_DIM, outline="")

        c.create_line(x + 8, y + 28, x + w - 8, y + 28, fill=D_ACCENT2, width=1)

        # Task description
        if self.speaking:
            task_text = "LEO: Speaking response..."
        elif self.listening:
            task_text = "LEO: Listening for input..."
        else:
            task_text = "LEO: Idle — awaiting command"

        c.create_text(x + 12, y + 44, text=task_text,
                      fill=D_TEXT, font=("Consolas", 8), anchor="w", width=w - 24)

        # Status indicator
        if self.speaking:
            stat_col = D_ACCENT
            stat_text = "● ACTIVE"
        elif self.listening:
            stat_col = D_BORDER2
            stat_text = "● LISTENING"
        else:
            stat_col = D_TEXT_DIM
            stat_text = "○ IDLE"

        c.create_text(x + 12, y + h - 15, text=stat_text,
                      fill=stat_col, font=("Consolas", 8, "bold"), anchor="w")

        c.create_text(x + w - 12, y + h - 15,
                      text=time.strftime("%H:%M"),
                      fill=D_TEXT_DIM, font=("Consolas", 8), anchor="e")

    # ── Panel: Spotify Status ──────────────────────────────────
    def _draw_panel_spotify(self, c, x, y, w, h):
        self._draw_glass_panel(c, x, y, w, h)

        c.create_text(x + 12, y + 14, text="SPOTIFY STATUS",
                      fill=D_ACCENT, font=("Consolas", 10, "bold"), anchor="w")

        # Music icon
        c.create_text(x + w - 18, y + 14, text="♪",
                      fill=D_ACCENT, font=("Consolas", 14), anchor="e")

        c.create_line(x + 8, y + 28, x + w - 8, y + 28, fill=D_ACCENT2, width=1)

        track  = self._spotify_info.get("track", "")
        artist = self._spotify_info.get("artist", "")
        album  = self._spotify_info.get("album", "")
        is_playing = self._spotify_info.get("is_playing", False)
        progress = self._spotify_info.get("progress", 0)
        duration = self._spotify_info.get("duration", 0)

        if not track:
            c.create_text(x + 12, y + 50, text="No track playing",
                          fill=D_TEXT_DIM, font=("Consolas", 9), anchor="w")
            # Play controls (dimmed)
            ctrl_y = y + h - 40
            for ci, sym in enumerate(["⏮", "▶", "⏭"]):
                cx = x + w // 2 - 30 + ci * 30
                c.create_text(cx, ctrl_y, text=sym,
                              fill=D_TEXT_DIM, font=("Consolas", 14))
        else:
            # Album art placeholder (teal square with note)
            art_x = x + 12
            art_y = y + 36
            art_s = 50
            c.create_rectangle(art_x, art_y, art_x + art_s, art_y + art_s,
                               fill="#1a3a30", outline=D_ACCENT2, width=1)
            c.create_text(art_x + art_s // 2, art_y + art_s // 2,
                          text="♪", fill=D_ACCENT, font=("Consolas", 20))

            # Track info
            text_x = art_x + art_s + 10
            c.create_text(text_x, y + 38, text="Currently Playing:",
                          fill=D_TEXT_DIM, font=("Consolas", 7), anchor="nw")

            # Truncate long names
            display_track = track[:20] + "..." if len(track) > 20 else track
            display_artist = artist[:18] + "..." if len(artist) > 18 else artist

            c.create_text(text_x, y + 52, text=display_track.upper(),
                          fill=D_TEXT, font=("Consolas", 9, "bold"), anchor="nw")
            c.create_text(text_x, y + 66, text=f"by {display_artist}",
                          fill=D_TEXT_DIM, font=("Consolas", 8), anchor="nw")
            if album:
                display_album = album[:18] + "..." if len(album) > 18 else album
                c.create_text(text_x, y + 80, text=display_album,
                              fill=D_TEXT_DIM, font=("Consolas", 7), anchor="nw")

            # Progress bar
            bar_y = y + h - 55
            bar_x1 = x + 12
            bar_x2 = x + w - 12
            bar_w = bar_x2 - bar_x1
            c.create_rectangle(bar_x1, bar_y, bar_x2, bar_y + 4,
                               fill="#1a2a25", outline="")
            if duration > 0:
                fill_frac = min(1.0, progress / duration)
                fill_w = int(bar_w * fill_frac)
                if fill_w > 0:
                    c.create_rectangle(bar_x1, bar_y, bar_x1 + fill_w, bar_y + 4,
                                       fill=D_ACCENT, outline="")
                # Dot at position
                c.create_oval(bar_x1 + fill_w - 3, bar_y - 2,
                              bar_x1 + fill_w + 3, bar_y + 6,
                              fill=D_ACCENT, outline="")

            # Time display
            p_min, p_sec = divmod(progress, 60)
            d_min, d_sec = divmod(duration, 60)
            c.create_text(bar_x1, bar_y + 12,
                          text=f"{p_min}:{p_sec:02d}",
                          fill=D_TEXT_DIM, font=("Consolas", 7), anchor="nw")
            c.create_text(bar_x2, bar_y + 12,
                          text=f"{d_min}:{d_sec:02d}",
                          fill=D_TEXT_DIM, font=("Consolas", 7), anchor="ne")

            # Play controls
            ctrl_y = y + h - 18
            play_sym = "⏸" if is_playing else "▶"
            for ci, sym in enumerate(["⏮", play_sym, "⏭"]):
                cx = x + w // 2 - 30 + ci * 30
                c.create_text(cx, ctrl_y, text=sym,
                              fill=D_ACCENT if ci == 1 else D_TEXT_DIM,
                              font=("Consolas", 14))

    # ── Panel: Recent Conversations ────────────────────────────
    def _draw_panel_conversations(self, c, x, y, w, h):
        self._draw_glass_panel(c, x, y, w, h)

        c.create_text(x + 12, y + 14, text="RECENT CONVERSATIONS",
                      fill=D_ACCENT, font=("Consolas", 10, "bold"), anchor="w")
        c.create_line(x + 8, y + 28, x + w - 8, y + 28, fill=D_ACCENT2, width=1)

        # Render last N entries from chat log
        max_entries = min(len(self._chat_log), max(1, (h - 40) // 36))
        recent = self._chat_log[-max_entries:] if self._chat_log else []

        cy = y + 38
        for role, text, ts in recent:
            if cy + 30 > y + h - 10:
                break

            # Role icon
            if role == "user":
                icon = "👤"
                role_text = "USER"
                role_col = D_TEXT_DIM
            else:
                icon = "🤖"
                role_text = "LEO"
                role_col = D_ACCENT

            c.create_text(x + 12, cy, text=f"{icon} {role_text}",
                          fill=role_col, font=("Consolas", 8, "bold"), anchor="nw")

            c.create_text(x + w - 12, cy, text=ts,
                          fill=D_TEXT_DIM, font=("Consolas", 7), anchor="ne")

            # Truncate message
            display_text = text[:30] + "..." if len(text) > 30 else text
            c.create_text(x + 16, cy + 14, text=display_text,
                          fill=D_TEXT, font=("Consolas", 8), anchor="nw",
                          width=w - 32)

            cy += 36

        if not recent:
            c.create_text(x + w // 2, y + h // 2,
                          text="No conversations yet",
                          fill=D_TEXT_DIM, font=("Consolas", 9))

    # ────────────────────────────────────────────────────────────
    #  SYSTEM STATS
    # ────────────────────────────────────────────────────────────
    def _refresh_system_stats(self):
        if _HAS_PSUTIL:
            try:
                self._system_stats["cpu"] = int(psutil.cpu_percent(interval=0))
                self._system_stats["memory"] = int(psutil.virtual_memory().percent)
            except Exception:
                pass

    # ────────────────────────────────────────────────────────────
    #  PUBLIC API (unchanged interface for main.py)
    # ────────────────────────────────────────────────────────────
    def write_log(self, text: str):
        """Log to terminal + store in chat buffer for dashboard."""
        print(f"[LEO UI] {text}")
        tl = text.lower()
        if tl.startswith("you:"):
            self.status_text = "PROCESSING"
            msg = text[4:].strip()
            self._chat_log.append(("user", msg, time.strftime("%H:%M")))
        elif tl.startswith("leo:") or tl.startswith("ai:"):
            self.status_text = "RESPONDING"
            prefix = "leo:" if tl.startswith("leo:") else "ai:"
            msg = text[len(prefix):].strip()
            self._chat_log.append(("leo", msg, time.strftime("%H:%M")))

        # Keep max 20 entries
        if len(self._chat_log) > 20:
            self._chat_log = self._chat_log[-20:]

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
        with self._audio_lock:
            self._audio_level = max(0.0, min(1.0, level))

    def update_spotify_info(self, info: dict):
        """Update Spotify widget data for dashboard display."""
        if info:
            self._spotify_info.update(info)

    # ── API key setup ───────────────────────────────────────────
    def _api_keys_exist(self):
        return API_FILE.exists()

    def wait_for_api_key(self):
        while not self._api_key_ready:
            time.sleep(0.1)

    def _show_setup_ui(self):
        self.setup_frame = tk.Frame(
            self.root, bg="#050505",
            highlightbackground=C_GREY2, highlightthickness=1
        )
        self.setup_frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(self.setup_frame, text="◈  INITIALISATION REQUIRED",
                 fg=C_WHITE, bg="#050505", font=("Consolas", 13, "bold")).pack(pady=(18, 4))
        tk.Label(self.setup_frame,
                 text="Enter your Gemini API key to boot L.E.O.",
                 fg=C_GREY2, bg="#050505", font=("Consolas", 9)).pack(pady=(0, 10))

        tk.Label(self.setup_frame, text="GEMINI API KEY",
                 fg=C_GREY3, bg="#050505", font=("Consolas", 9)).pack(pady=(8, 2))
        self.gemini_entry = tk.Entry(
            self.setup_frame, width=52, fg=C_WHITE, bg="#111111",
            insertbackground=C_WHITE, borderwidth=0, font=("Consolas", 10), show="*"
        )
        self.gemini_entry.pack(pady=(0, 4))

        tk.Button(
            self.setup_frame, text="▸  INITIALISE SYSTEMS",
            command=self._save_api_keys, bg=C_BG, fg=C_WHITE,
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
