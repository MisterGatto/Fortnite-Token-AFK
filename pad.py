import ctypes
import os
import time


class Btn:
    UP = 0x0001
    DOWN = 0x0002
    LEFT = 0x0004
    RIGHT = 0x0008
    MENU = 0x0010
    VIEW = 0x0020
    LS = 0x0040
    RS = 0x0080
    LB = 0x0100
    RB = 0x0200
    A = 0x1000
    B = 0x2000
    X = 0x4000
    Y = 0x8000


class VirtualPad:
    """Wrapper around native ViGEmBus C++ bridge DLL for virtual Xbox 360 inputs."""

    def __init__(self, dll_path: str | None = None):
        if dll_path is None:
            base = os.path.dirname(os.path.abspath(__file__))
            dll_path = os.path.join(base, "bin", "vigem_bridge.dll")
        if not os.path.exists(dll_path):
            raise FileNotFoundError(
                f"DLL not found: {dll_path}. Build native/ or verify the bin/ directory."
            )

        self._dll = ctypes.CDLL(dll_path)
        self._dll.pad_init.restype = ctypes.c_int
        self._dll.pad_shutdown.restype = None
        self._dll.pad_set.argtypes = [
            ctypes.c_uint16,
            ctypes.c_int16,
            ctypes.c_int16,
            ctypes.c_int16,
            ctypes.c_int16,
            ctypes.c_uint8,
            ctypes.c_uint8,
        ]
        self._dll.pad_set.restype = ctypes.c_int
        self._dll.pad_press.argtypes = [ctypes.c_uint16, ctypes.c_int]
        self._dll.pad_press.restype = ctypes.c_int

        rc = self._dll.pad_init()
        if rc != 0:
            raise RuntimeError(
                f"Failed to initialize ViGEm virtual controller (error code {rc}). "
                "Make sure the ViGEmBus driver is installed (winget install ViGEm.ViGEmBus)."
            )
        self._active = True

    def press(self, mask: int, hold_ms: int = 250, after_wait: float = 0.0):
        if not self._active:
            return
        self._dll.pad_press(mask, hold_ms)
        if after_wait > 0:
            time.sleep(after_wait)

    def set_state(self, buttons=0, lx=0, ly=0, rx=0, ry=0, lt=0, rt=0):
        if not self._active:
            return
        self._dll.pad_set(buttons, lx, ly, rx, ry, lt, rt)

    def flick_stick_up(self, hold_ms: int = 220, after_wait: float = 1.5):
        """Flicks the left analog stick upward (returns from Discover back to Lobby)."""
        if not self._active:
            return
        self.set_state(ly=32000)
        time.sleep(hold_ms / 1000.0)
        self.set_state(ly=0)
        if after_wait > 0:
            time.sleep(after_wait)

    def anti_kick_nudge(self, toggle_action: bool = False):
        """Small natural left-stick movement + jump or pickaxe swing."""
        if not self._active:
            return
        self.set_state(ly=26000)
        time.sleep(0.35)
        self.set_state(ly=0)
        time.sleep(0.15)
        if toggle_action:
            self.press(Btn.A, hold_ms=180)
        else:
            self.set_state(rt=255)
            time.sleep(0.25)
            self.set_state(rt=0)

    def close(self):
        if self._active:
            self._dll.pad_shutdown()
            self._active = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

