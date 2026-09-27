"""
ExifCraft  ·  Professional EXIF Editor
A clean, modern tool for reading & writing image metadata.

Author : yohoten
License: MIT
"""

import os
import sys
import csv
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from fractions import Fraction
from datetime import datetime
from PIL import Image, UnidentifiedImageError

import piexif


# ---------------------------------------------------------------------
#  Application assets
# ---------------------------------------------------------------------
def _app_dir() -> str:
    """Folder that holds the script and its assets (frozen or plain .pyw)."""
    if getattr(sys, "frozen", False):            # PyInstaller / py2exe build
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR  = _app_dir()
ICON_ICO = os.path.join(APP_DIR, "ExifCraft.ico")   # Windows: multi-resolution
ICON_PNG = os.path.join(APP_DIR, "ExifCraft.png")   # fallback: any platform

# Optional widgets
try:
    from tkintermapview import TkinterMapView
    HAS_MAP = True
except ImportError:
    HAS_MAP = False

try:
    from tkcalendar import DateEntry
    HAS_CALENDAR = True
except ImportError:
    HAS_CALENDAR = False


# =====================================================================
#  Theme  ──  color tokens, fonts, and ttk styling
# =====================================================================
class Theme:
    # ---- palette
    BG          = "#F4F6FA"   # app background
    SURFACE     = "#FFFFFF"   # cards / inputs
    SURFACE_2   = "#F8FAFC"   # secondary surface (log)
    BORDER      = "#E2E8F0"   # hairline borders
    BORDER_FOCUS= "#CBD5E1"

    PRIMARY     = "#2563EB"   # brand blue
    PRIMARY_H   = "#1D4ED8"   # hover
    PRIMARY_S   = "#DBEAFE"   # soft / selected

    TEXT        = "#0F172A"   # primary text
    TEXT_2      = "#475569"   # secondary
    TEXT_3      = "#94A3B8"   # tertiary / placeholder

    SUCCESS     = "#059669"
    ERROR       = "#DC2626"
    WARNING     = "#D97706"

    # ---- typography
    if sys.platform.startswith("win"):
        FONT       = ("Segoe UI", 10)
        FONT_BOLD  = ("Segoe UI Semibold", 10)
        FONT_H1    = ("Segoe UI Semibold", 15)
        FONT_H2    = ("Segoe UI Semibold", 11)
        FONT_MONO  = ("Consolas", 9)
    elif sys.platform == "darwin":
        FONT       = ("SF Pro Text", 12)
        FONT_BOLD  = ("SF Pro Text Semibold", 12)
        FONT_H1    = ("SF Pro Display Semibold", 17)
        FONT_H2    = ("SF Pro Text Semibold", 13)
        FONT_MONO  = ("Menlo", 11)
    else:
        FONT       = ("Inter", 10)
        FONT_BOLD  = ("Inter", 10, "bold")
        FONT_H1    = ("Inter", 14, "bold")
        FONT_H2    = ("Inter", 11, "bold")
        FONT_MONO  = ("JetBrains Mono", 9)


# =====================================================================
#  EXIF helpers
# =====================================================================
def to_degrees(value: float):
    d = int(value)
    m = int((value - d) * 60)
    s = (value - d - m / 60) * 3600
    return [(d, 1), (m, 1), _to_fraction(s)]


def _to_fraction(value: float):
    f = Fraction(value).limit_denominator(1_000_000)
    return (f.numerator, f.denominator)


def set_exif_data(img_path, output_path, *, longitude, latitude, altitude,
                  focal_length, aperture, iso,
                  make, model, shot_date, overwrite=False):
    """Write EXIF into a copy of *img_path* at *output_path*."""
    try:
        img = Image.open(img_path)
    except UnidentifiedImageError:
        raise ValueError(f"Unrecognized image: {os.path.basename(img_path)}")

    if 'exif' in img.info:
        exif_dict = piexif.load(img.info['exif'])
    else:
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

    # ---- GPS
    exif_dict['GPS'][piexif.GPSIFD.GPSLongitude]  = to_degrees(longitude)
    exif_dict['GPS'][piexif.GPSIFD.GPSLongitudeRef] = "E" if longitude >= 0 else "W"
    exif_dict['GPS'][piexif.GPSIFD.GPSLatitude]   = to_degrees(latitude)
    exif_dict['GPS'][piexif.GPSIFD.GPSLatitudeRef] = "N" if latitude >= 0 else "S"
    exif_dict['GPS'][piexif.GPSIFD.GPSAltitude]   = _to_fraction(altitude) if altitude else (0, 1)
    exif_dict['GPS'][piexif.GPSIFD.GPSAltitudeRef] = 0 if altitude >= 0 else 1

    # ---- capture params
    exif_dict['Exif'][piexif.ExifIFD.FocalLength]      = _to_fraction(focal_length)
    exif_dict['Exif'][piexif.ExifIFD.FNumber]          = _to_fraction(aperture)
    exif_dict['Exif'][piexif.ExifIFD.ISOSpeedRatings]  = iso
    exif_dict['0th'][piexif.ImageIFD.Make]             = make.encode("utf-8")
    exif_dict['0th'][piexif.ImageIFD.Model]            = model.encode("utf-8")
    exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = shot_date.encode("utf-8")

    exif_bytes = piexif.dump(exif_dict)
    ext = os.path.splitext(output_path)[1].lower()
    save_kwargs = {"exif": exif_bytes}
    if ext in (".jpg", ".jpeg"):
        save_kwargs["quality"] = 100
    img.save(output_path, **save_kwargs)


def read_exif_info(img_path):
    """Return a dict of human-readable EXIF fields (missing → '')."""
    info = dict.fromkeys(
        ["make", "model", "datetime",
         "focal_length", "fnumber", "iso",
         "longitude", "latitude", "altitude"], "")
    try:
        img = Image.open(img_path)
        if 'exif' not in img.info:
            return info
        exif = piexif.load(img.info['exif'])
    except Exception:
        return info

    def _s(b):
        return b.decode("utf-8", "ignore") if isinstance(b, (bytes, bytearray)) else b

    info["make"]    = _s(exif['0th'].get(piexif.ImageIFD.Make, b''))
    info["model"]   = _s(exif['0th'].get(piexif.ImageIFD.Model, b''))
    info["datetime"]= _s(exif['Exif'].get(piexif.ExifIFD.DateTimeOriginal, b''))

    fl = exif['Exif'].get(piexif.ExifIFD.FocalLength)
    if fl and isinstance(fl, tuple) and len(fl) == 2 and fl[1]:
        info["focal_length"] = f"{fl[0]/fl[1]:.1f}"

    fn = exif['Exif'].get(piexif.ExifIFD.FNumber)
    if fn and isinstance(fn, tuple) and len(fn) == 2 and fn[1]:
        info["fnumber"] = f"{fn[0]/fn[1]:.1f}"

    iso = exif['Exif'].get(piexif.ExifIFD.ISOSpeedRatings)
    if iso:
        info["iso"] = str(iso[0] if isinstance(iso, tuple) else iso)

    gps = exif.get('GPS', {})
    def _dms(tag, ref_tag, default_ref):
        dms = gps.get(tag)
        if not dms or len(dms) != 3:
            return ""
        d, m, s = dms
        val = d[0]/d[1] + m[0]/(m[1]*60) + s[0]/(s[1]*3600)
        ref = gps.get(ref_tag, default_ref)
        if ref in ("S", "W"):
            val = -val
        return f"{val:.6f}"

    info["latitude"]  = _dms(piexif.GPSIFD.GPSLatitude,  piexif.GPSIFD.GPSLatitudeRef,  "N")
    info["longitude"] = _dms(piexif.GPSIFD.GPSLongitude, piexif.GPSIFD.GPSLongitudeRef, "E")

    alt = gps.get(piexif.GPSIFD.GPSAltitude)
    if alt and isinstance(alt, tuple) and len(alt) == 2 and alt[1]:
        info["altitude"] = f"{alt[0]/alt[1]:.1f}"

    return info


# =====================================================================
#  Validators
# =====================================================================
class Validator:
    """Return (ok, [errors]).  Keyword names mirror `_collect_params`."""
    @staticmethod
    def check(longitude, latitude, altitude, focal_length, aperture, iso,
              make, model, date):
        errs = []

        def _num(name, raw, *, lo=None, hi=None, integer=False, allow_empty=False):
            s = (raw or "").strip()
            if not s:
                if allow_empty:
                    return None
                errs.append(f"{name} 不能为空"); return None
            try:
                v = int(s) if integer else float(s)
            except ValueError:
                errs.append(f"{name} 必须为{'整数' if integer else '数字'}"); return None
            if lo is not None and v < lo:
                errs.append(f"{name} 不能小于 {lo}"); return None
            if hi is not None and v > hi:
                errs.append(f"{name} 不能大于 {hi}"); return None
            return v

        _num("经度", longitude, lo=-180, hi=180)
        _num("纬度", latitude,  lo=-90,  hi=90)
        _num("海拔", altitude,  allow_empty=True)        # optional
        _num("焦距", focal_length, lo=0.01)
        _num("光圈", aperture,     lo=0.01)
        _num("ISO",  iso,          lo=1, integer=True)

        if not (make or "").strip():  errs.append("相机制造商不能为空")
        if not (model or "").strip(): errs.append("相机型号不能为空")

        d = (date or "").strip()
        if not d:
            errs.append("拍摄日期不能为空")
        else:
            try:
                datetime.strptime(d, "%Y:%m:%d %H:%M:%S")
            except ValueError:
                errs.append("日期格式错误，应为 YYYY:MM:DD HH:MM:SS")

        return len(errs) == 0, errs


# =====================================================================
#  UI building blocks
# =====================================================================
class Card(tk.Frame):
    """A hairline-bordered surface card with an optional section title."""
    def __init__(self, master, title=None, **kw):
        super().__init__(
            master,
            bg=Theme.SURFACE,
            highlightthickness=1,
            highlightbackground=Theme.BORDER,
            highlightcolor=Theme.BORDER,
            bd=0,
            **kw,
        )
        pad = ttk.Frame(self, style="Card.TFrame")
        pad.pack(fill="both", expand=True, padx=14, pady=10)
        if title:
            ttk.Label(pad, text=title, style="CardTitle.TLabel").pack(anchor="w", pady=(0, 9))
        self.body = ttk.Frame(pad, style="Card.TFrame")
        self.body.pack(fill="both", expand=True)


# =====================================================================
#  Main application
# =====================================================================
class ExifCraft:
    APP_NAME   = "ExifCraft"
    APP_TAG    = "Professional EXIF Editor"
    APP_VER    = "2.1"

    IMG_EXTS = (".jpg", ".jpeg", ".tiff", ".tif", ".png")

    def __init__(self, root: tk.Tk):
        self.root = root
        self._apply_theme()
        root.title(f"{self.APP_NAME}  ·  {self.APP_TAG}")
        self.root.configure(bg=Theme.BG)

        # state
        self.input_files: list[str] = []
        self.worker: threading.Thread | None = None

        # string vars (defaults empty — let the user fill in)
        self.src_var   = tk.StringVar()
        self.out_var   = tk.StringVar()
        self.make_var  = tk.StringVar()
        self.model_var = tk.StringVar()
        self.time_var  = tk.StringVar(value="12:00:00")
        self.status_var= tk.StringVar(value="Ready")
        self.overwrite_var = tk.BooleanVar(value=False)

        self.field_vars: dict[str, tk.StringVar] = {
            "longitude":     tk.StringVar(),
            "latitude":      tk.StringVar(),
            "altitude":      tk.StringVar(),
            "focal_length":  tk.StringVar(),
            "aperture":      tk.StringVar(),
            "iso":           tk.StringVar(),
        }

        self._build()
        self._setup_window()          # needs measured widget sizes → after _build
        self._set_window_icon()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    #  Window icon
    # ------------------------------------------------------------------
    def _apply_icon(self, window):
        """Put the ExifCraft icon on any Tk window (title bar + taskbar)."""
        # Windows: a multi-resolution .ico stays sharp at every shell size.
        # NB: the path must be positional — `default=` only seeds *future*
        # windows and leaves this one with Tk's stock feather icon.
        if sys.platform.startswith("win") and os.path.exists(ICON_ICO):
            try:
                window.iconbitmap(ICON_ICO)               # this window + taskbar
                window.iconbitmap(default=ICON_ICO)       # future children
                return
            except tk.TclError:
                pass

        # Fallback for other platforms, or if the .ico is missing.
        if os.path.exists(ICON_PNG):
            try:
                img = tk.PhotoImage(file=ICON_PNG)
                window.iconphoto(True, img)
                setattr(window, "_exifcraft_icon", img)   # keep the ref alive
            except tk.TclError:
                pass

    def _set_window_icon(self):
        self._apply_icon(self.root)

    # ------------------------------------------------------------------
    #  Window sizing  (fits the content, clamped to the visible desktop)
    # ------------------------------------------------------------------
    def _setup_window(self):
        self.root.update_idletasks()
        sw, sh   = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        need_w   = self.root.winfo_reqwidth()
        need_h   = self.root.winfo_reqheight()
        w = min(max(need_w + 16, 1020), sw - 60)
        h = min(max(need_h + 20, 680),  sh - 90)
        x = max(20, (sw - w) // 2)
        y = max(20, (sh - h) // 2 - 20)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(min(1000, sw - 100), min(680, sh - 160))

    # ------------------------------------------------------------------
    #  Theming
    # ------------------------------------------------------------------
    def _apply_theme(self):
        style = ttk.Style()
        # 'clam' is the most styleable cross-platform theme.
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        s = style
        base = Theme

        # Frames
        s.configure("App.TFrame",        background=base.BG)
        s.configure("Card.TFrame",        background=base.SURFACE, relief="flat")
        s.configure("CardInner.TFrame",   background=base.SURFACE)
        s.configure("Log.TFrame",         background=base.SURFACE_2)

        # Labels
        s.configure("App.TLabel",   background=base.BG, foreground=base.TEXT,
                    font=base.FONT)
        s.configure("CardTitle.TLabel",
                    background=base.SURFACE, foreground=base.TEXT,
                    font=base.FONT_H2)
        s.configure("Field.TLabel",
                    background=base.SURFACE, foreground=base.TEXT_2,
                    font=base.FONT)
        s.configure("Hint.TLabel",
                    background=base.SURFACE, foreground=base.TEXT_3,
                    font=(base.FONT[0], base.FONT[1]-1))
        s.configure("Title.TLabel",
                    background=base.BG, foreground=base.TEXT,
                    font=base.FONT_H1)
        s.configure("Subtitle.TLabel",
                    background=base.BG, foreground=base.TEXT_2,
                    font=(base.FONT[0], base.FONT[1]+1))
        s.configure("Status.TLabel",
                    background=base.BG, foreground=base.TEXT_2,
                    font=base.FONT)
        s.configure("Err.TLabel",
                    background=base.BG, foreground=base.ERROR,
                    font=base.FONT_BOLD)

        # Buttons
        s.configure("Primary.TButton",
                    font=base.FONT_BOLD, padding=(14, 8),
                    foreground=base.SURFACE, background=base.PRIMARY,
                    borderwidth=0, relief="flat", focuscolor=base.PRIMARY,
                    bordercolor=base.PRIMARY, lightcolor=base.PRIMARY,
                    darkcolor=base.PRIMARY)
        s.map("Primary.TButton",
              background=[("active", base.PRIMARY_H), ("pressed", base.PRIMARY_H)],
              foreground=[("disabled", "#BFD3F5")])

        s.configure("Ghost.TButton",
                    font=base.FONT, padding=(12, 7),
                    foreground=base.TEXT, background=base.SURFACE,
                    borderwidth=1, relief="solid", focuscolor=base.SURFACE,
                    bordercolor=base.BORDER_FOCUS,
                    lightcolor=base.SURFACE, darkcolor=base.SURFACE)
        s.map("Ghost.TButton",
              background=[("active", base.PRIMARY_S), ("pressed", base.PRIMARY_S)],
              foreground=[("active", base.PRIMARY_H)],
              bordercolor=[("active", base.PRIMARY)])

        s.configure("Subtle.TButton",
                    font=base.FONT, padding=(10, 6),
                    foreground=base.TEXT_2, background=base.BG,
                    borderwidth=0, relief="flat")
        s.map("Subtle.TButton",
              foreground=[("active", base.PRIMARY)],
              background=[("active", base.SURFACE)])

        # Inputs
        s.configure("Field.TEntry",
                    fieldbackground=base.SURFACE, foreground=base.TEXT,
                    insertcolor=base.TEXT, borderwidth=1, relief="solid",
                    padding=6)
        s.map("Field.TEntry",
              bordercolor=[("focus", base.PRIMARY), ("!focus", base.BORDER)],
              lightcolor=[("focus", base.PRIMARY), ("!focus", base.BORDER)],
              darkcolor=[("focus", base.PRIMARY), ("!focus", base.BORDER)])

        s.configure("Field.TCombobox",
                    fieldbackground=base.SURFACE, foreground=base.TEXT,
                    borderwidth=1, relief="solid", padding=4)
        s.map("Field.TCombobox",
              bordercolor=[("focus", base.PRIMARY), ("!focus", base.BORDER)],
              lightcolor=[("focus", base.PRIMARY), ("!focus", base.BORDER)],
              darkcolor=[("focus", base.PRIMARY), ("!focus", base.BORDER)])

        # Listbox (use Tk widget, but style scrollbar)
        s.configure("Vertical.TScrollbar",
                    background=base.BG, troughcolor=base.BG,
                    bordercolor=base.BG, arrowcolor=base.TEXT_3)
        s.map("Vertical.TScrollbar",
              background=[("active", base.BORDER_FOCUS), ("pressed", base.TEXT_3)])

        # Progressbar
        s.configure("Accent.Horizontal.TProgressbar",
                    troughcolor="#E9EEF6", background=base.PRIMARY,
                    bordercolor="#E9EEF6", lightcolor="#E9EEF6",
                    darkcolor="#E9EEF6", borderwidth=0, thickness=9)

        # Checkbutton
        s.configure("App.TCheckbutton",
                    background=base.SURFACE, foreground=base.TEXT,
                    font=base.FONT, focuscolor=base.SURFACE,
                    indicatorcolor=base.SURFACE,
                    bordercolor=base.BORDER_FOCUS,
                    padding=2)
        s.map("App.TCheckbutton",
              background=[("active", base.SURFACE)],
              foreground=[("active", base.TEXT)],
              indicatorcolor=[("selected", base.PRIMARY), ("!selected", base.SURFACE)])

    # ------------------------------------------------------------------
    #  Layout
    # ------------------------------------------------------------------
    def _build(self):
        # outer canvas with padding
        outer = ttk.Frame(self.root, style="App.TFrame", padding=12)
        outer.pack(fill="both", expand=True)

        # ---- header
        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="◼", style="Title.TLabel",
                  foreground=Theme.PRIMARY).pack(side="left", padx=(0, 8))
        ttk.Label(header, text=self.APP_NAME, style="Title.TLabel").pack(side="left")
        ttk.Label(header, text=f"  v{self.APP_VER}", style="Subtitle.TLabel",
                  foreground=Theme.TEXT_3).pack(side="left", padx=(2, 0), pady=(4, 0))
        ttk.Label(header, text=self.APP_TAG, style="Subtitle.TLabel").pack(side="right")

        # ---- body: two-column (cards) layout
        body = ttk.Frame(outer, style="App.TFrame")
        body.pack(fill="both", expand=True, pady=(10, 0))
        body.columnconfigure(0, weight=1, uniform="col")
        body.columnconfigure(1, weight=1, uniform="col")
        body.rowconfigure(0, weight=1)

        # --- left column
        left = ttk.Frame(body, style="App.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        src_card = Card(left, title="Source  ·  源文件")
        src_card.pack(fill="both", expand=True)

        # source row
        row = ttk.Frame(src_card.body, style="CardInner.TFrame")
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Path", style="Field.TLabel").pack(side="left")
        ttk.Entry(row, textvariable=self.src_var, style="Field.TEntry",
                  font=Theme.FONT, width=1).pack(side="left", fill="x", expand=True, padx=(8, 8))
        ttk.Button(row, text="File",  style="Ghost.TButton",
                   command=self._pick_file).pack(side="left", padx=2)
        ttk.Button(row, text="Folder", style="Ghost.TButton",
                   command=self._pick_folder).pack(side="left", padx=2)

        # output row
        row = ttk.Frame(src_card.body, style="CardInner.TFrame")
        row.pack(fill="x", pady=(6, 2))
        ttk.Label(row, text="Output", style="Field.TLabel").pack(side="left")
        ttk.Entry(row, textvariable=self.out_var, style="Field.TEntry",
                  font=Theme.FONT, width=1).pack(side="left", fill="x", expand=True, padx=(8, 8))
        ttk.Button(row, text="Browse", style="Ghost.TButton",
                   command=self._pick_output).pack(side="left", padx=2)

        # file list
        list_holder = ttk.Frame(src_card.body, style="CardInner.TFrame")
        list_holder.pack(fill="both", expand=True, pady=(8, 4))

        self.file_list = tk.Listbox(
            list_holder, height=6, activestyle="none",
            background=Theme.SURFACE_2, foreground=Theme.TEXT,
            selectbackground=Theme.PRIMARY_S, selectforeground=Theme.PRIMARY_H,
            relief="flat", highlightthickness=1,
            highlightbackground=Theme.BORDER, highlightcolor=Theme.PRIMARY,
            font=Theme.FONT_MONO, bd=0,
        )
        self.file_list.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(list_holder, orient="vertical",
                           style="Vertical.TScrollbar", command=self.file_list.yview)
        sb.pack(side="right", fill="y")
        self.file_list.configure(yscrollcommand=sb.set)

        # list footer
        list_footer = ttk.Frame(src_card.body, style="CardInner.TFrame")
        list_footer.pack(fill="x", pady=(4, 0))
        self.list_count_lbl = ttk.Label(list_footer, text="0 files",
                                        style="Hint.TLabel")
        self.list_count_lbl.pack(side="left")
        ttk.Button(list_footer, text="Clear", style="Subtle.TButton",
                   command=self._clear_files).pack(side="right")

        # options row
        opt_row = ttk.Frame(src_card.body, style="CardInner.TFrame")
        opt_row.pack(fill="x", pady=(8, 0))
        ttk.Checkbutton(opt_row, text="Overwrite originals in-place",
                        variable=self.overwrite_var,
                        style="App.TCheckbutton").pack(side="left")

        # --- right column
        right = ttk.Frame(body, style="App.TFrame")
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        # Camera card
        cam_card = Card(right, title="Camera  ·  相机")
        cam_card.pack(fill="x")

        cam_grid = ttk.Frame(cam_card.body, style="CardInner.TFrame")
        cam_grid.pack(fill="x")
        cam_grid.columnconfigure(0, weight=1, uniform="cam")
        cam_grid.columnconfigure(1, weight=1, uniform="cam")
        self._labeled_entry(cam_grid, "Make",  self.make_var,  col=0, hint="e.g. Nikon")
        self._labeled_entry(cam_grid, "Model", self.model_var, col=1, hint="e.g. Z6 II")

        # Exposure card
        exp_card = Card(right, title="Exposure  ·  曝光参数")
        exp_card.pack(fill="x", pady=(10, 0))

        grid = ttk.Frame(exp_card.body, style="CardInner.TFrame")
        grid.pack(fill="x")
        for c in range(3):
            grid.columnconfigure(c, weight=1, uniform="exp")

        self._labeled_entry(grid, "Focal (mm)",   self.field_vars["focal_length"], col=0)
        self._labeled_entry(grid, "Aperture (F)", self.field_vars["aperture"],     col=1)
        self._labeled_entry(grid, "ISO",          self.field_vars["iso"],          col=2)

        # Date card
        date_card = Card(right, title="Date  ·  拍摄时间")
        date_card.pack(fill="x", pady=(10, 0))

        row = ttk.Frame(date_card.body, style="CardInner.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="Date", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        if HAS_CALENDAR:
            self.date_picker = DateEntry(row, width=14, date_pattern="yyyy-MM-dd",
                                         background=Theme.SURFACE, foreground=Theme.TEXT,
                                         borderwidth=1, relief="solid")
            self.date_picker.grid(row=0, column=1, sticky="w", padx=(8, 4), pady=2)
            ttk.Entry(row, textvariable=self.time_var, width=8,
                      style="Field.TEntry", font=Theme.FONT_MONO
                      ).grid(row=0, column=2, sticky="w", padx=(4, 4))
            ttk.Label(row, text="HH:MM:SS", style="Hint.TLabel").grid(row=0, column=3, sticky="w", padx=(6, 0))
        else:
            self.date_str_var = tk.StringVar()
            ttk.Entry(row, textvariable=self.date_str_var,
                      style="Field.TEntry", font=Theme.FONT_MONO, width=24
                      ).grid(row=0, column=1, columnspan=3, sticky="we", padx=(8, 0), pady=2)
        row.columnconfigure(1, weight=1)

        # GPS card (under exposure)
        gps_card = Card(right, title="Location  ·  GPS 坐标")
        gps_card.pack(fill="x", pady=(10, 0))

        grid = ttk.Frame(gps_card.body, style="CardInner.TFrame")
        grid.pack(fill="x")
        for c in range(2):
            grid.columnconfigure(c, weight=1, uniform="gps")

        self._labeled_entry(grid, "Longitude", self.field_vars["longitude"],
                            col=0, hint="-180 ~ 180")
        self._labeled_entry(grid, "Latitude",  self.field_vars["latitude"],
                            col=1, hint="-90 ~ 90")

        self._labeled_entry(gps_card.body, "Altitude (m)", self.field_vars["altitude"])

        # map button (if available)
        if HAS_MAP:
            map_btn_row = ttk.Frame(gps_card.body, style="CardInner.TFrame")
            map_btn_row.pack(fill="x", pady=(6, 0))
            ttk.Button(map_btn_row, text="📍 Pick on map",
                       style="Ghost.TButton",
                       command=self._open_map).pack(side="right")

        # ---- bottom action bar + progress + log
        actions = ttk.Frame(outer, style="App.TFrame")
        actions.pack(fill="x", pady=(12, 5))

        ttk.Button(actions, text="Read EXIF",  style="Ghost.TButton",
                   command=self._read_selected).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Write EXIF", style="Primary.TButton",
                   command=self._write_async).pack(side="left", padx=6)
        ttk.Button(actions, text="Read folder EXIF → CSV",
                   style="Ghost.TButton",
                   command=self._export_csv).pack(side="left", padx=6)

        # progress
        prog_row = ttk.Frame(outer, style="App.TFrame")
        prog_row.pack(fill="x")
        self.progress = ttk.Progressbar(prog_row, orient="horizontal", mode="determinate",
                                        style="Accent.Horizontal.TProgressbar")
        self.progress.pack(side="left", fill="x", expand=True)
        self.progress_text = ttk.Label(prog_row, text="", style="Status.TLabel")
        self.progress_text.pack(side="left", padx=(8, 0))

        # log
        log_holder = ttk.Frame(outer, style="App.TFrame")
        log_holder.pack(fill="x", pady=(6, 0))

        log_frame = ttk.Frame(log_holder, style="Log.TFrame", padding=(8, 6))
        log_frame.pack(fill="x")
        self.log = tk.Text(log_frame, height=4, wrap="word", state="disabled",
                           background=Theme.SURFACE_2, foreground=Theme.TEXT,
                           insertbackground=Theme.TEXT,
                           relief="flat", highlightthickness=1,
                           highlightbackground=Theme.BORDER,
                           font=Theme.FONT_MONO, bd=0, padx=4, pady=4)
        self.log.pack(side="left", fill="both", expand=True)
        log_sb = ttk.Scrollbar(log_frame, orient="vertical",
                               style="Vertical.TScrollbar",
                               command=self.log.yview)
        log_sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=log_sb.set)

        # color tags for log
        self.log.tag_configure("ok",    foreground=Theme.SUCCESS)
        self.log.tag_configure("err",   foreground=Theme.ERROR)
        self.log.tag_configure("warn",  foreground=Theme.WARNING)
        self.log.tag_configure("muted", foreground=Theme.TEXT_3)

        # status bar
        status_bar = ttk.Frame(outer, style="App.TFrame")
        status_bar.pack(fill="x", pady=(6, 0))
        self.status_lbl = ttk.Label(status_bar, textvariable=self.status_var,
                                    style="Status.TLabel")
        self.status_lbl.pack(side="left")
        self.err_lbl = ttk.Label(status_bar, text="", style="Err.TLabel")
        self.err_lbl.pack(side="right")

    def _labeled_entry(self, parent, label, var, *, hint=None, col=None):
        """Build a label + entry (+ optional hint) block. Returns its frame."""
        frame = ttk.Frame(parent, style="CardInner.TFrame")
        if col is not None:
            frame.grid(row=0, column=col, sticky="nsew",
                       padx=(0 if col == 0 else 8, 0), pady=2)
        else:
            frame.pack(fill="x", pady=2)
        ttk.Label(frame, text=label, style="Field.TLabel").pack(anchor="w")
        ttk.Entry(frame, textvariable=var, style="Field.TEntry",
                  font=Theme.FONT_MONO, width=1).pack(fill="x", pady=(3, 0))
        if hint:
            ttk.Label(frame, text=hint, style="Hint.TLabel").pack(anchor="w", pady=(2, 0))
        return frame

    # ------------------------------------------------------------------
    #  Logging & status
    # ------------------------------------------------------------------
    def _log(self, msg, level="info"):
        self.log.configure(state="normal")
        prefix = {"ok": "✔ ", "err": "✖ ", "warn": "! ", "muted": "· ", "info": ""}.get(level, "")
        self.log.insert("end", prefix + msg + "\n", (level,) if level != "info" else ())
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_status(self, text):
        self.status_var.set(text)

    def _set_error(self, text):
        self.err_lbl.configure(text=text or "")

    # ------------------------------------------------------------------
    #  Source handling
    # ------------------------------------------------------------------
    def _pick_file(self):
        p = filedialog.askopenfilename(
            filetypes=[("Images", " ".join(f"*{e}" for e in self.IMG_EXTS)), ("All files", "*.*")]
        )
        if not p:
            return
        self.input_files = [p]
        self.src_var.set(p)
        if not self.out_var.get():
            self.out_var.set(os.path.dirname(p))
        self._refresh_list()

    def _pick_folder(self):
        d = filedialog.askdirectory()
        if not d:
            return
        files = [os.path.join(d, f) for f in os.listdir(d)
                 if f.lower().endswith(self.IMG_EXTS)]
        files.sort()
        self.input_files = files
        self.src_var.set(d)
        if not self.out_var.get():
            self.out_var.set(d)
        self._refresh_list()

    def _pick_output(self):
        d = filedialog.askdirectory()
        if d:
            self.out_var.set(d)

    def _clear_files(self):
        self.input_files.clear()
        self.src_var.set("")
        self._refresh_list()
        self._log("File list cleared.", "muted")

    def _refresh_list(self):
        self.file_list.delete(0, "end")
        for f in self.input_files:
            self.file_list.insert("end", os.path.basename(f))
        n = len(self.input_files)
        self.list_count_lbl.configure(
            text=f"{n} file{'s' if n != 1 else ''} loaded"
        )

    # ------------------------------------------------------------------
    #  Read existing EXIF
    # ------------------------------------------------------------------
    def _read_selected(self):
        sel = self.file_list.curselection()
        if not sel:
            messagebox.showinfo(self.APP_NAME, "Select a file from the list first.")
            return
        path = self.input_files[sel[0]]
        try:
            info = read_exif_info(path)
        except Exception as e:
            messagebox.showerror(self.APP_NAME, f"Failed to read EXIF:\n{e}")
            return

        self.field_vars["longitude"].set(info["longitude"])
        self.field_vars["latitude"].set(info["latitude"])
        self.field_vars["altitude"].set(info["altitude"])
        self.field_vars["focal_length"].set(info["focal_length"])
        self.field_vars["aperture"].set(info["fnumber"])
        self.field_vars["iso"].set(info["iso"])
        self.make_var.set(info["make"])
        self.model_var.set(info["model"])

        if info["datetime"]:
            try:
                d, t = info["datetime"].split(" ")
                if HAS_CALENDAR:
                    self.date_picker.set_date(d.replace(":", "-"))
                else:
                    self.date_str_var.set(info["datetime"])
                self.time_var.set(t)
            except ValueError:
                if not HAS_CALENDAR:
                    self.date_str_var.set(info["datetime"])

        self._log(f"Loaded EXIF from {os.path.basename(path)}", "ok")

    # ------------------------------------------------------------------
    #  Map picker
    # ------------------------------------------------------------------
    def _open_map(self):
        if not HAS_MAP:
            messagebox.showinfo(self.APP_NAME,
                                "Install tkintermapview to enable:\n"
                                "  pip install tkintermapview")
            return
        win = tk.Toplevel(self.root)
        win.title(f"{self.APP_NAME}  ·  Map picker")
        win.geometry("640x520")
        win.configure(bg=Theme.BG)
        self._apply_icon(win)

        m = TkinterMapView(win, width=640, height=440, corner_radius=0)
        m.pack(fill="both", expand=True, padx=10, pady=10)

        try:
            lat = float(self.field_vars["latitude"].get())
            lon = float(self.field_vars["longitude"].get())
        except ValueError:
            lat, lon = 39.9042, 116.4074  # Beijing fallback
        m.set_position(lat, lon)
        m.set_zoom(8)

        info = ttk.Label(win, text="Click anywhere on the map to pick coordinates",
                         style="Subtitle.TLabel")
        info.pack(pady=(0, 8))

        def on_click(coords):
            la, lo = coords
            info.configure(text=f"Latitude: {la:.6f}   Longitude: {lo:.6f}")
            self.field_vars["latitude"].set(f"{la:.6f}")
            self.field_vars["longitude"].set(f"{lo:.6f}")
            self._log(f"Map pick: {la:.6f}, {lo:.6f}", "muted")

        m.add_left_click_map_command(on_click)

        ttk.Button(win, text="Close", style="Ghost.TButton",
                   command=win.destroy).pack(pady=(0, 10))

    # ------------------------------------------------------------------
    #  Writing (off the UI thread)
    # ------------------------------------------------------------------
    def _collect_params(self):
        p = {
            "longitude":     self.field_vars["longitude"].get(),
            "latitude":      self.field_vars["latitude"].get(),
            "altitude":      self.field_vars["altitude"].get(),
            "focal_length":  self.field_vars["focal_length"].get(),
            "aperture":      self.field_vars["aperture"].get(),
            "iso":           self.field_vars["iso"].get(),
            "make":          self.make_var.get(),
            "model":         self.model_var.get(),
            "date":          self._date_string(),
        }
        return p

    def _date_string(self):
        if HAS_CALENDAR:
            d = self.date_picker.get_date().strftime("%Y:%m:%d")
            t = self.time_var.get().strip() or "00:00:00"
            return f"{d} {t}"
        return self.date_str_var.get()

    def _write_async(self):
        if self.worker and self.worker.is_alive():
            return
        if not self.input_files:
            messagebox.showerror(self.APP_NAME, "Pick at least one image first.")
            return

        params = self._collect_params()
        ok, errs = Validator.check(**params)
        if not ok:
            self._set_error("  ·  ".join(errs))
            messagebox.showerror(self.APP_NAME, "\n".join(errs))
            return
        self._set_error("")

        out_dir = self.out_var.get().strip() or os.path.dirname(self.input_files[0])
        os.makedirs(out_dir, exist_ok=True)
        overwrite = self.overwrite_var.get()

        self.progress["value"] = 0
        self.progress["maximum"] = len(self.input_files)
        self.progress_text.configure(text=f"0 / {len(self.input_files)}")
        self._set_status("Writing…")
        self._log(f"Starting write of {len(self.input_files)} file(s)…", "muted")

        self.worker = threading.Thread(
            target=self._write_worker,
            args=(list(self.input_files), out_dir, params, overwrite),
            daemon=True,
        )
        self.worker.start()

    def _write_worker(self, files, out_dir, params, overwrite):
        success = 0
        total = len(files)
        # defensive: the worker owns the destination, so make sure it exists
        if not overwrite:
            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError as e:
                self.root.after(0, lambda m=str(e):
                                self._log(f"Cannot create output dir: {m}", "err"))
                self.root.after(0, lambda: self._finish_write(0, total))
                return
        # normalize numeric values
        try:
            lon = float(params["longitude"])
            lat = float(params["latitude"])
            alt = float(params["altitude"]) if (params["altitude"] or "").strip() else 0.0
            fl  = float(params["focal_length"])
            ap  = float(params["aperture"])
            iso = int(params["iso"])
        except (TypeError, ValueError) as e:
            self.root.after(0, lambda: self._log(f"Bad numeric input: {e}", "err"))
            return

        for idx, src in enumerate(files, 1):
            base = os.path.basename(src)
            name, ext = os.path.splitext(base)
            if overwrite:
                dst = src
            else:
                dst = os.path.join(out_dir, f"{name}_exif{ext}")

            try:
                set_exif_data(
                    src, dst,
                    longitude=lon, latitude=lat, altitude=alt,
                    focal_length=fl, aperture=ap, iso=iso,
                    make=params["make"], model=params["model"],
                    shot_date=params["date"],
                    overwrite=overwrite,
                )
                success += 1
                self.root.after(0, lambda b=base, d=os.path.basename(dst):
                                self._log(f"{b}  →  {d}", "ok"))
            except Exception as e:
                self.root.after(0, lambda b=base, m=str(e):
                                self._log(f"{b} failed: {m}", "err"))

            self.root.after(0, lambda i=idx, t=total:
                            (self.progress.configure(value=i),
                             self.progress_text.configure(text=f"{i} / {t}")))

        self.root.after(0, lambda s=success, t=total:
                        self._finish_write(s, t))

    def _finish_write(self, success, total):
        self.progress["value"] = 0
        self.progress_text.configure(text="")
        self._set_status(f"Done  ·  {success}/{total} succeeded")
        self._log(f"Finished. {success}/{total} succeeded.", "ok"
                  if success == total else "warn")
        messagebox.showinfo(self.APP_NAME,
                            f"Processed {total} file(s).\n"
                            f"{success} succeeded, {total - success} failed.")

    # ------------------------------------------------------------------
    #  CSV export
    # ------------------------------------------------------------------
    def _export_csv(self):
        if not self.input_files:
            messagebox.showinfo(self.APP_NAME, "No files loaded.")
            return
        target = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="exif_summary.csv",
        )
        if not target:
            return
        rows = []
        for f in self.input_files:
            info = read_exif_info(f)
            rows.append({"file": os.path.basename(f), **{k: v for k, v in info.items()}})
        with open(target, "w", newline="", encoding="utf-8") as fp:
            w = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        self._log(f"Exported CSV: {target}", "ok")

    # ------------------------------------------------------------------
    #  Lifecycle
    # ------------------------------------------------------------------
    def _on_close(self):
        try:
            self.root.destroy()
        except Exception:
            pass


# =====================================================================
#  Entry point
# =====================================================================
def enable_dpi_awareness():
    """Crisp text on HiDPI displays; must run before Tk() is created."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # system-DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    ExifCraft(root)
    root.mainloop()


if __name__ == "__main__":
    main()
