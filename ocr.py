import ctypes
import ctypes.wintypes
from dataclasses import dataclass
import os
import winreg

# ---------------------------------------------------------------------------
# Enable Per-Monitor v2 DPI Awareness BEFORE importing mss or querying rects!
# Crucial when primary monitor is 100% DPI (2560x1440) and drawing tablet is
# 150% DPI (Kamvas 13 1920x1080) so Win32 returns physical pixels, not 1280x720.
# ---------------------------------------------------------------------------
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32
try:
    shcore = ctypes.windll.shcore
except Exception:
    shcore = None


def _enable_per_monitor_dpi_awareness():
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext.restype = ctypes.wintypes.BOOL
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):  # PER_MONITOR_AWARE_V2
            return
    except Exception:
        pass
    try:
        if shcore is not None:
            shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
            shcore.SetProcessDpiAwareness.restype = ctypes.c_long
            shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
            return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


_enable_per_monitor_dpi_awareness()

import cv2
import mss
import numpy as np
from rapidocr_onnxruntime import RapidOCR

PW_CLIENTONLY = 0x00000001
PW_RENDERFULLCONTENT = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
DIB_RGB_COLORS = 0
SRCCOPY = 0x00CC0020
MONITOR_DEFAULTTONEAREST = 0x00000002
DISPLAY_DEVICE_ACTIVE = 0x00000001
SWP_SHOWWINDOW = 0x0040
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010

# ---------------------------------------------------------------------------
# Strict 64-bit Win32 API function signatures (prevents ctypes OverflowError)
# ---------------------------------------------------------------------------
user32.IsWindow.argtypes = [ctypes.wintypes.HWND]
user32.IsWindow.restype = ctypes.wintypes.BOOL

user32.IsIconic.argtypes = [ctypes.wintypes.HWND]
user32.IsIconic.restype = ctypes.wintypes.BOOL

user32.IsWindowVisible.argtypes = [ctypes.wintypes.HWND]
user32.IsWindowVisible.restype = ctypes.wintypes.BOOL

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = ctypes.wintypes.HWND

user32.GetClientRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.RECT)]
user32.GetClientRect.restype = ctypes.wintypes.BOOL

user32.GetWindowRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.RECT)]
user32.GetWindowRect.restype = ctypes.wintypes.BOOL

user32.ClientToScreen.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.POINT)]
user32.ClientToScreen.restype = ctypes.wintypes.BOOL

user32.SetWindowPos.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.wintypes.UINT,
]
user32.SetWindowPos.restype = ctypes.wintypes.BOOL

user32.GetDC.argtypes = [ctypes.wintypes.HWND]
user32.GetDC.restype = ctypes.wintypes.HDC

user32.ReleaseDC.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int

user32.PrintWindow.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HDC, ctypes.wintypes.UINT]
user32.PrintWindow.restype = ctypes.wintypes.BOOL

user32.GetClassNameW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int

user32.GetWindowTextW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

user32.GetWindowThreadProcessId.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD

user32.FindWindowW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPCWSTR]
user32.FindWindowW.restype = ctypes.wintypes.HWND

user32.MonitorFromWindow.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.DWORD]
user32.MonitorFromWindow.restype = ctypes.wintypes.HMONITOR

user32.GetWindow.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.UINT]
user32.GetWindow.restype = ctypes.wintypes.HWND

EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumWindowsProc, ctypes.wintypes.LPARAM]
user32.EnumWindows.restype = ctypes.wintypes.BOOL

MonitorEnumProc = ctypes.WINFUNCTYPE(
    ctypes.wintypes.BOOL,
    ctypes.wintypes.HMONITOR,
    ctypes.wintypes.HDC,
    ctypes.POINTER(ctypes.wintypes.RECT),
    ctypes.wintypes.LPARAM,
)
user32.EnumDisplayMonitors.argtypes = [
    ctypes.wintypes.HDC,
    ctypes.POINTER(ctypes.wintypes.RECT),
    MonitorEnumProc,
    ctypes.wintypes.LPARAM,
]
user32.EnumDisplayMonitors.restype = ctypes.wintypes.BOOL

gdi32.CreateCompatibleDC.argtypes = [ctypes.wintypes.HDC]
gdi32.CreateCompatibleDC.restype = ctypes.wintypes.HDC

gdi32.CreateCompatibleBitmap.argtypes = [ctypes.wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = ctypes.wintypes.HBITMAP

gdi32.SelectObject.argtypes = [ctypes.wintypes.HDC, ctypes.wintypes.HGDIOBJ]
gdi32.SelectObject.restype = ctypes.wintypes.HGDIOBJ

gdi32.DeleteObject.argtypes = [ctypes.wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = ctypes.wintypes.BOOL

gdi32.DeleteDC.argtypes = [ctypes.wintypes.HDC]
gdi32.DeleteDC.restype = ctypes.wintypes.BOOL

gdi32.BitBlt.argtypes = [
    ctypes.wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.wintypes.DWORD,
]
gdi32.BitBlt.restype = ctypes.wintypes.BOOL

gdi32.GetDIBits.argtypes = [
    ctypes.wintypes.HDC,
    ctypes.wintypes.HBITMAP,
    ctypes.wintypes.UINT,
    ctypes.wintypes.UINT,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.wintypes.UINT,
]
gdi32.GetDIBits.restype = ctypes.c_int

kernel32.OpenProcess.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE

kernel32.QueryFullProcessImageNameW.argtypes = [
    ctypes.wintypes.HANDLE,
    ctypes.wintypes.DWORD,
    ctypes.wintypes.LPWSTR,
    ctypes.POINTER(ctypes.wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = ctypes.wintypes.BOOL

kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
kernel32.CloseHandle.restype = ctypes.wintypes.BOOL


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.wintypes.DWORD),
        ("biWidth", ctypes.wintypes.LONG),
        ("biHeight", ctypes.wintypes.LONG),
        ("biPlanes", ctypes.wintypes.WORD),
        ("biBitCount", ctypes.wintypes.WORD),
        ("biCompression", ctypes.wintypes.DWORD),
        ("biSizeImage", ctypes.wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.wintypes.LONG),
        ("biYPelsPerMeter", ctypes.wintypes.LONG),
        ("biClrUsed", ctypes.wintypes.DWORD),
        ("biClrImportant", ctypes.wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.wintypes.DWORD * 3)]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("rcMonitor", ctypes.wintypes.RECT),
        ("rcWork", ctypes.wintypes.RECT),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("szDevice", ctypes.wintypes.WCHAR * 32),
    ]


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.wintypes.DWORD),
        ("DeviceName", ctypes.wintypes.WCHAR * 32),
        ("DeviceString", ctypes.wintypes.WCHAR * 128),
        ("StateFlags", ctypes.wintypes.DWORD),
        ("DeviceID", ctypes.wintypes.WCHAR * 128),
        ("DeviceKey", ctypes.wintypes.WCHAR * 128),
    ]


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.wintypes.WCHAR * 32),
        ("dmSpecVersion", ctypes.wintypes.WORD),
        ("dmDriverVersion", ctypes.wintypes.WORD),
        ("dmSize", ctypes.wintypes.WORD),
        ("dmDriverExtra", ctypes.wintypes.WORD),
        ("dmFields", ctypes.wintypes.DWORD),
        ("dmPositionX", ctypes.wintypes.LONG),
        ("dmPositionY", ctypes.wintypes.LONG),
        ("dmDisplayOrientation", ctypes.wintypes.DWORD),
        ("dmDisplayFixedOutput", ctypes.wintypes.DWORD),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.wintypes.WCHAR * 32),
        ("dmLogPixels", ctypes.wintypes.WORD),
        ("dmBitsPerPel", ctypes.wintypes.DWORD),
        ("dmPelsWidth", ctypes.wintypes.DWORD),
        ("dmPelsHeight", ctypes.wintypes.DWORD),
        ("dmDisplayFlags", ctypes.wintypes.DWORD),
        ("dmDisplayFrequency", ctypes.wintypes.DWORD),
    ]


user32.GetMonitorInfoW.argtypes = [ctypes.wintypes.HMONITOR, ctypes.c_void_p]
user32.GetMonitorInfoW.restype = ctypes.wintypes.BOOL

user32.EnumDisplayDevicesW.argtypes = [
    ctypes.wintypes.LPCWSTR,
    ctypes.wintypes.DWORD,
    ctypes.POINTER(DISPLAY_DEVICEW),
    ctypes.wintypes.DWORD,
]
user32.EnumDisplayDevicesW.restype = ctypes.wintypes.BOOL

user32.EnumDisplaySettingsW.argtypes = [
    ctypes.wintypes.LPCWSTR,
    ctypes.wintypes.DWORD,
    ctypes.POINTER(DEVMODEW),
]
user32.EnumDisplaySettingsW.restype = ctypes.wintypes.BOOL

user32.GetAncestor.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.UINT]
user32.GetAncestor.restype = ctypes.wintypes.HWND

kernel32.GetConsoleWindow.argtypes = []
kernel32.GetConsoleWindow.restype = ctypes.wintypes.HWND

if shcore is not None:
    try:
        shcore.GetDpiForMonitor.argtypes = [
            ctypes.wintypes.HMONITOR,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint),
        ]
        shcore.GetDpiForMonitor.restype = ctypes.c_long
    except Exception:
        pass


@dataclass
class DisplayInfo:
    hmonitor: int
    device: str
    friendly_name: str
    left: int
    top: int
    width: int
    height: int
    dpi_percent: int
    is_primary: bool
    is_tablet: bool
    rotation_deg: int = 0

    def label(self) -> str:
        tag = " [Tablet]" if self.is_tablet else (" [Primary]" if self.is_primary else "")
        rot = f" {self.rotation_deg}°" if self.rotation_deg else ""
        return f"{self.friendly_name} ({self.width}x{self.height} @ {self.dpi_percent}%{rot}){tag}"


@dataclass
class OcrLine:
    text: str
    cx: float  # normalized center X [0..1]
    cy: float  # normalized center Y [0..1]
    score: float


@dataclass
class ScreenScan:
    lines: list[OcrLine]
    full_text: str
    frame_bgr: np.ndarray

    def has_any(self, keywords: tuple[str, ...]) -> str | None:
        for kw in keywords:
            if kw in self.full_text:
                return kw
        return None


_TABLET_HINTS = (
    "KAMVAS", "HUION", "WACOM", "CINTIQ", "XPPEN", "XP-PEN", "ARTIST",
    "GAOMON", "UGEE", "BOPPER", "HAT1", "HAT2", "PARBLO", "VEIKK",
)


def _read_edid_model_name(device_id: str) -> str:
    parts = device_id.split("\\")
    if len(parts) < 2:
        return ""
    model = parts[1]
    base_path = rf"SYSTEM\CurrentControlSet\Enum\DISPLAY\{model}"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_path) as k:
            idx = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, idx)
                    idx += 1
                    try:
                        with winreg.OpenKey(k, rf"{sub}\Device Parameters") as dp:
                            edid, _ = winreg.QueryValueEx(dp, "EDID")
                            for off in (54, 72, 90, 108):
                                if off + 18 <= len(edid) and edid[off : off + 4] == b"\x00\x00\x00\xfc":
                                    raw = edid[off + 5 : off + 18]
                                    name = raw.split(b"\n")[0].decode("ascii", errors="ignore").strip()
                                    if name:
                                        return name
                    except OSError:
                        pass
                except OSError:
                    break
    except OSError:
        pass
    return model


def _monitor_friendly_name(device_name: str) -> tuple[str, str]:
    mon = DISPLAY_DEVICEW()
    mon.cb = ctypes.sizeof(mon)
    if user32.EnumDisplayDevicesW(device_name, 0, ctypes.byref(mon), 0):
        edid_name = _read_edid_model_name(mon.DeviceID)
        return (edid_name or mon.DeviceString or device_name), mon.DeviceID
    return device_name, ""


def list_displays() -> list[DisplayInfo]:
    """Lists all active displays with physical pixel geometry, DPI %, and tablet detection."""
    displays: list[DisplayInfo] = []

    def cb(hmon, _hdc, _lprc, _data):
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(mi)
        if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return 1
        rc = mi.rcMonitor
        dpi_pct = 100
        if shcore is not None:
            dx = ctypes.c_uint(96)
            dy = ctypes.c_uint(96)
            if shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dx), ctypes.byref(dy)) == 0 and dx.value > 0:
                dpi_pct = int(round(dx.value * 100.0 / 96.0))
        friendly, dev_id = _monitor_friendly_name(mi.szDevice)
        combined = f"{friendly} {dev_id}".upper()
        is_tablet = any(h in combined for h in _TABLET_HINTS)

        dm = DEVMODEW()
        dm.dmSize = ctypes.sizeof(dm)
        rot_deg = 0
        if user32.EnumDisplaySettingsW(mi.szDevice, 0xFFFFFFFF, ctypes.byref(dm)):
            rot_deg = int(dm.dmDisplayOrientation) * 90

        displays.append(
            DisplayInfo(
                hmonitor=int(hmon),
                device=mi.szDevice,
                friendly_name=friendly,
                left=int(rc.left),
                top=int(rc.top),
                width=int(rc.right - rc.left),
                height=int(rc.bottom - rc.top),
                dpi_percent=dpi_pct,
                is_primary=bool(mi.dwFlags & 1),
                is_tablet=is_tablet,
                rotation_deg=rot_deg,
            )
        )
        return 1

    user32.EnumDisplayMonitors(None, None, MonitorEnumProc(cb), 0)
    return displays


def get_window_display(hwnd: int) -> DisplayInfo | None:
    """Returns the DisplayInfo where the given window currently resides."""
    if not hwnd or not user32.IsWindow(hwnd):
        return None
    hmon = int(user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST))
    for d in list_displays():
        if d.hmonitor == hmon:
            return d
    return None


def move_window_to_display(hwnd: int, target: DisplayInfo) -> bool:
    """Moves and resizes window cleanly to the target display in physical pixels."""
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    return bool(
        user32.SetWindowPos(
            hwnd,
            0,
            int(target.left),
            int(target.top),
            int(target.width),
            int(target.height),
            SWP_NOZORDER | SWP_SHOWWINDOW | SWP_NOACTIVATE,
        )
    )


def find_fortnite_hwnd() -> int:
    """Finds the UnrealWindow / FortniteClient-Win64-Shipping.exe window handle."""
    direct_hwnd = user32.FindWindowW("UnrealWindow", None)
    if direct_hwnd and user32.IsWindowVisible(direct_hwnd) and not user32.IsIconic(direct_hwnd):
        title_buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(direct_hwnd, title_buf, 256)
        if "Fortnite" in title_buf.value or title_buf.value == "":
            return int(direct_hwnd)

    found = []

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return 1

        cls_buf = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(hwnd, cls_buf, 128)
        title_buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title_buf, 256)

        if cls_buf.value == "UnrealWindow" and "Fortnite" in title_buf.value:
            found.append(int(hwnd))
            return 0

        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value > 0:
            hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
            if hproc:
                exe_buf = ctypes.create_unicode_buffer(512)
                size = ctypes.wintypes.DWORD(512)
                if kernel32.QueryFullProcessImageNameW(hproc, 0, exe_buf, ctypes.byref(size)):
                    if "FortniteClient" in exe_buf.value:
                        found.append(int(hwnd))
                        kernel32.CloseHandle(hproc)
                        return 0
                kernel32.CloseHandle(hproc)

        return 1

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return found[0] if found else 0


def _capture_via_gdi_bitblt(x: int, y: int, w: int, h: int) -> np.ndarray | None:
    """Fast screen rectangle grab using desktop DC BitBlt in physical virtual-screen coords."""
    hdc_screen = user32.GetDC(0)
    if not hdc_screen:
        return None

    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbm = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    old_obj = gdi32.SelectObject(hdc_mem, hbm)
    img = None

    try:
        ok = gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, x, y, SRCCOPY)
        if ok:
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = w
            bmi.bmiHeader.biHeight = -h  # top-down
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = 0

            buf = np.empty((h, w, 4), dtype=np.uint8)
            lines = gdi32.GetDIBits(
                hdc_mem,
                hbm,
                0,
                h,
                ctypes.c_void_p(buf.ctypes.data),
                ctypes.byref(bmi),
                DIB_RGB_COLORS,
            )
            if lines > 0:
                img = buf[:, :, :3].copy()
    finally:
        gdi32.SelectObject(hdc_mem, old_obj)
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)

    return img


def _capture_via_mss(x: int, y: int, w: int, h: int) -> np.ndarray | None:
    try:
        mss_cls = getattr(mss, "MSS", mss.mss)
        with mss_cls() as sct:
            mon = {"left": int(x), "top": int(y), "width": int(w), "height": int(h)}
            shot = np.array(sct.grab(mon))
            if shot is not None and shot.size > 0:
                return shot[:, :, :3].copy()
    except Exception:
        pass
    return None


def _capture_via_print_window(hwnd: int, w: int, h: int) -> np.ndarray | None:
    hdc_win = user32.GetDC(hwnd)
    if not hdc_win:
        return None

    hdc_mem = gdi32.CreateCompatibleDC(hdc_win)
    hbm = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
    old_obj = gdi32.SelectObject(hdc_mem, hbm)
    img = None

    try:
        ok = user32.PrintWindow(hwnd, hdc_mem, PW_CLIENTONLY | PW_RENDERFULLCONTENT)
        if not ok:
            ok = user32.PrintWindow(hwnd, hdc_mem, PW_CLIENTONLY)
        if ok:
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = w
            bmi.bmiHeader.biHeight = -h
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = 0

            buf = np.empty((h, w, 4), dtype=np.uint8)
            lines = gdi32.GetDIBits(
                hdc_mem,
                hbm,
                0,
                h,
                ctypes.c_void_p(buf.ctypes.data),
                ctypes.byref(bmi),
                DIB_RGB_COLORS,
            )
            if lines > 0:
                img = buf[:, :, :3].copy()
    finally:
        gdi32.SelectObject(hdc_mem, old_obj)
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(hwnd, hdc_win)

    return img


def is_window_focused(hwnd: int) -> bool:
    """Returns True if the given window currently has keyboard/controller foreground focus."""
    if not hwnd:
        return False
    return int(user32.GetForegroundWindow() or 0) == int(hwnd)


def get_capture_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Computes physical capture rectangle (x, y, w, h) clamped safely inside the active display."""
    if not hwnd or not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        return None

    rect = ctypes.wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None

    w = int(rect.right - rect.left)
    h = int(rect.bottom - rect.top)
    if w <= 10 or h <= 10:
        return None

    pt = ctypes.wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    x, y = int(pt.x), int(pt.y)

    disp = get_window_display(hwnd)
    if disp is not None:
        # Handle fullscreen / borderless window on a scaled secondary monitor (e.g. Kamvas 13 @ 150%)
        scaled_w = int(round(w * disp.dpi_percent / 100.0))
        scaled_h = int(round(h * disp.dpi_percent / 100.0))
        is_dpi_shrunk_fullscreen = (
            disp.dpi_percent > 100
            and abs(scaled_w - disp.width) <= 30
            and abs(scaled_h - disp.height) <= 30
        )
        is_near_fullscreen = abs(w - disp.width) <= 24 and abs(h - disp.height) <= 24
        if is_dpi_shrunk_fullscreen or is_near_fullscreen:
            return (disp.left, disp.top, disp.width, disp.height)

        # Clamp tightly within monitor bounds so oversized/moved windows (e.g. 2560x1440 moved onto 1920x1080)
        # never overflow the virtual desktop in BitBlt / mss!
        left = max(x, disp.left)
        top = max(y, disp.top)
        right = min(x + w, disp.left + disp.width)
        bottom = min(y + h, disp.top + disp.height)
        if right - left > 100 and bottom - top > 100:
            return (left, top, right - left, bottom - top)
        return (disp.left, disp.top, disp.width, disp.height)

    return (x, y, w, h)


_dxgi_dll = None
LAST_CAPTURE_METHOD = "--"


def _get_dxgi_dll():
    global _dxgi_dll
    if _dxgi_dll is not None:
        return _dxgi_dll if _dxgi_dll is not False else None
    dll_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", "dxgi_bridge.dll")
    if not os.path.exists(dll_path):
        _dxgi_dll = False
        return None
    try:
        lib = ctypes.CDLL(dll_path)
        lib.dxgi_grab_rect.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_int,
        ]
        lib.dxgi_grab_rect.restype = ctypes.c_int
        lib.dxgi_shutdown.argtypes = []
        lib.dxgi_shutdown.restype = None
        _dxgi_dll = lib
        return lib
    except Exception:
        _dxgi_dll = False
        return None


def _capture_via_dxgi(disp: DisplayInfo, x: int, y: int, w: int, h: int) -> np.ndarray | None:
    lib = _get_dxgi_dll()
    if lib is None or not disp.device:
        return None

    rot = disp.rotation_deg
    rel_x = int(x - disp.left)
    rel_y = int(y - disp.top)

    if rot == 0:
        dx, dy, dw, dh = int(x), int(y), int(w), int(h)
    elif rot == 180:
        dx = int(disp.left + (disp.width - rel_x - w))
        dy = int(disp.top + (disp.height - rel_y - h))
        dw, dh = int(w), int(h)
    else:
        # For 90/270 portrait/rotated displays let BitBlt handle GDI rotation cleanly
        return None

    buf = np.empty((dh, dw, 4), dtype=np.uint8)
    rc = lib.dxgi_grab_rect(
        disp.device,
        dx,
        dy,
        dw,
        dh,
        ctypes.c_void_p(buf.ctypes.data),
        int(buf.nbytes),
    )
    if rc != 1:
        return None

    img = buf[:, :, :3].copy()
    if rot == 180:
        img = cv2.rotate(img, cv2.ROTATE_180)
    return img


def find_console_hwnd() -> int:
    """Finds the bot's own console / terminal root window handle."""
    found = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return 1
        t = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, t, 256)
        if "Fortnite Auto OCR" in t.value:
            found.append(int(hwnd))
            return 0
        return 1

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    if found:
        return found[0]

    c = int(kernel32.GetConsoleWindow() or 0)
    if c:
        root = int(user32.GetAncestor(c, 2) or c)
        if user32.IsWindowVisible(root):
            return root
    return 0


def _is_window_above(candidate_hwnd: int, base_hwnd: int) -> bool:
    """Returns True only if candidate_hwnd is higher than base_hwnd in the Windows Z-order."""
    if not candidate_hwnd or not base_hwnd or candidate_hwnd == base_hwnd:
        return False
    GW_HWNDPREV = 3
    cur = int(base_hwnd)
    for _ in range(300):
        cur = int(user32.GetWindow(cur, GW_HWNDPREV) or 0)
        if not cur:
            return False
        if cur == int(candidate_hwnd):
            return True
    return False


def move_console_away_from_fortnite(fn_hwnd: int) -> bool:
    """If >=2 displays exist and the bot console is visibly covering Fortnite, move console to another display."""
    displays = list_displays()
    if len(displays) < 2 or not fn_hwnd:
        return False
    fn_disp = get_window_display(fn_hwnd)
    ch = find_console_hwnd()
    if not ch or ch == fn_hwnd or fn_disp is None or user32.IsIconic(ch):
        return False
    # If the user intentionally placed the console in the background behind Fortnite, leave it alone!
    if not _is_window_above(ch, fn_hwnd):
        return False
    c_disp = get_window_display(ch)
    if c_disp is None or c_disp.hmonitor != fn_disp.hmonitor:
        return False
    other = next((d for d in displays if d.hmonitor != fn_disp.hmonitor), None)
    if other is None:
        return False
    rc = ctypes.wintypes.RECT()
    user32.GetWindowRect(ch, ctypes.byref(rc))
    cw = max(680, min(960, int(rc.right - rc.left)))
    ch_h = max(420, min(680, int(rc.bottom - rc.top)))
    return bool(
        user32.SetWindowPos(
            ch,
            0,
            int(other.left + 80),
            int(other.top + 80),
            cw,
            ch_h,
            SWP_NOZORDER | SWP_SHOWWINDOW | SWP_NOACTIVATE,
        )
    )


def _mask_console_overlap(img: np.ndarray, box: tuple[int, int, int, int], fn_hwnd: int) -> np.ndarray:
    """Blacks out our own console window ONLY if it is actually in front of Fortnite."""
    ch = find_console_hwnd()
    if not ch or ch == fn_hwnd or user32.IsIconic(ch):
        return img
    if not _is_window_above(ch, fn_hwnd):
        return img
    rc = ctypes.wintypes.RECT()
    if not user32.GetWindowRect(ch, ctypes.byref(rc)):
        return img
    x, y, w, h = box
    ix1 = max(0, int(rc.left) - x)
    iy1 = max(0, int(rc.top) - y)
    ix2 = min(w, int(rc.right) - x)
    iy2 = min(h, int(rc.bottom) - y)
    if ix2 - ix1 > 10 and iy2 - iy1 > 10:
        img[iy1:iy2, ix1:ix2] = 0
    return img


def capture_window(hwnd: int) -> np.ndarray | None:
    """
    Captures live Fortnite screen region cleanly across primary monitor AND scaled/rotated
    secondary pen displays (e.g. Kamvas 13 @ 150% DPI, 180 deg rotation).
    Order: DXGI GPU Desktop Duplication -> GDI BitBlt -> mss -> PrintWindow.
    """
    global LAST_CAPTURE_METHOD
    box = get_capture_rect(hwnd)
    if box is None:
        return None

    x, y, w, h = box
    disp = get_window_display(hwnd)

    img = None
    if disp is not None:
        img = _capture_via_dxgi(disp, x, y, w, h)
        if img is not None and float(img.mean()) >= 1.5:
            LAST_CAPTURE_METHOD = f"DXGI({disp.device},{disp.rotation_deg}d)"
            return _mask_console_overlap(img, box, hwnd)

    img = _capture_via_gdi_bitblt(x, y, w, h)
    if img is not None and float(img.mean()) >= 1.5:
        LAST_CAPTURE_METHOD = "BitBlt"
        return _mask_console_overlap(img, box, hwnd)

    img = _capture_via_mss(x, y, w, h)
    if img is not None and float(img.mean()) >= 1.5:
        LAST_CAPTURE_METHOD = "mss"
        return _mask_console_overlap(img, box, hwnd)

    img = _capture_via_print_window(hwnd, w, h)
    if img is not None and float(img.mean()) >= 1.5:
        LAST_CAPTURE_METHOD = "PrintWindow"
        return _mask_console_overlap(img, box, hwnd)

    LAST_CAPTURE_METHOD = "NONE"
    return img


class FortniteOCR:
    def __init__(self, target_width: int = 1280):
        self._ocr = RapidOCR()
        self._target_width = target_width

    def scan(self, frame_bgr: np.ndarray) -> ScreenScan:
        h, w = frame_bgr.shape[:2]
        if w > self._target_width:
            scale = self._target_width / float(w)
            resized = cv2.resize(frame_bgr, (self._target_width, int(h * scale)), interpolation=cv2.INTER_AREA)
        else:
            resized = frame_bgr

        rh, rw = resized.shape[:2]
        result, _ = self._ocr(resized)
        lines: list[OcrLine] = []
        texts: list[str] = []

        if result:
            for item in result:
                box, txt, score = item[0], item[1], float(item[2])
                if not txt:
                    continue
                upper = txt.strip().upper()
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                cx = (sum(xs) / 4.0) / rw
                cy = (sum(ys) / 4.0) / rh
                lines.append(OcrLine(text=upper, cx=cx, cy=cy, score=score))
                texts.append(upper)

        return ScreenScan(lines=lines, full_text=" | ".join(texts), frame_bgr=frame_bgr)


@dataclass
class TokenTemplate:
    name: str
    bgr: np.ndarray
    mask: np.ndarray | None = None


def load_token_templates(templates_dir: str, prefix: str = "pirate_token") -> list[TokenTemplate]:
    """Loads template images (e.g. templates/pirate_token.png) for visual icon verification."""
    out: list[TokenTemplate] = []
    if not os.path.isdir(templates_dir):
        return out
    exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
    for fn in sorted(os.listdir(templates_dir)):
        low = fn.lower()
        if not low.startswith(prefix.lower()) or not low.endswith(exts):
            continue
        path = os.path.join(templates_dir, fn)
        raw = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if raw is None or raw.size == 0:
            continue
        if raw.ndim == 2:
            bgr = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
            out.append(TokenTemplate(name=fn, bgr=bgr, mask=None))
        elif raw.shape[2] == 4:
            bgr = raw[:, :, :3].copy()
            alpha = raw[:, :, 3]
            # Use alpha mask only if image actually has meaningful transparent regions
            mask = alpha if (alpha.min() < 240 and alpha.max() > 15) else None
            out.append(TokenTemplate(name=fn, bgr=bgr, mask=mask))
        else:
            out.append(TokenTemplate(name=fn, bgr=raw[:, :, :3].copy(), mask=None))
    return out


def match_token_templates(
    frame_bgr: np.ndarray,
    templates: list[TokenTemplate],
    target_width: int = 1280,
) -> tuple[float, str]:
    """
    Runs multi-scale template matching on a normalized frame.
    Returns (best_score, template_name).
    """
    if frame_bgr is None or frame_bgr.size == 0 or not templates:
        return 0.0, ""

    fh, fw = frame_bgr.shape[:2]
    if fw > target_width:
        fscale = target_width / float(fw)
        work = cv2.resize(frame_bgr, (target_width, max(1, int(fh * fscale))), interpolation=cv2.INTER_AREA)
    else:
        work = frame_bgr
    wh, ww = work.shape[:2]

    best_score = 0.0
    best_name = ""
    scales = (0.35, 0.45, 0.55, 0.65, 0.75, 0.83, 0.92, 1.0, 1.10, 1.25, 1.45, 1.70)

    for tmpl in templates:
        th, tw = tmpl.bgr.shape[:2]
        for s in scales:
            nw, nh = int(round(tw * s)), int(round(th * s))
            if nw < 18 or nh < 18 or nw > ww - 2 or nh > wh - 2:
                continue
            interp = cv2.INTER_AREA if s < 1.0 else cv2.INTER_LINEAR
            t_rs = cv2.resize(tmpl.bgr, (nw, nh), interpolation=interp)
            if tmpl.mask is not None:
                m_rs = cv2.resize(tmpl.mask, (nw, nh), interpolation=cv2.INTER_NEAREST)
                res = cv2.matchTemplate(work, t_rs, cv2.TM_CCOEFF_NORMED, mask=m_rs)
            else:
                res = cv2.matchTemplate(work, t_rs, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            if np.isfinite(max_val) and float(max_val) > best_score:
                best_score = float(max_val)
                best_name = tmpl.name

    return best_score, best_name
