import json
import msvcrt
import os
import re
import sys
import time
from collections import deque
from datetime import datetime, timedelta

import ocr as ocr_mod
from ocr import (
    FortniteOCR,
    ScreenScan,
    capture_window,
    find_fortnite_hwnd,
    get_capture_rect,
    get_window_display,
    is_window_focused,
    list_displays,
    load_token_templates,
    match_token_templates,
    move_console_away_from_fortnite,
    move_window_to_display,
)
import cv2
from colorama import Fore, Style, init as colorama_init
from pad import Btn, VirtualPad

colorama_init(autoreset=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


DEFAULT_ALLOWED_MODES = ["BATTLE ROYALE"]
DEFAULT_BLOCKED_MODES = [
    "RELOAD",
    "FORTNITE OG",
    "BLITZ",
    "LEGO",
    "FESTIVAL",
    "MAIN STAGE",
    "JAM STAGE",
    "BATTLE STAGE",
    "ROCKET RACING",
    "BALLISTIC",
    "SAVE THE WORLD",
    "SALVA IL MONDO",
    "CREATIVE",
    "CREATIVA",
    "BRICK LIFE",
    "ODYSSEY",
    "DELULU",
    "TYCOON",
    "BOX FIGHT",
    "ZONE WARS",
    "RED VS BLUE",
    "THE PIT",
    "DEATHRUN",
]


DEFAULT_GIZMO_KEYWORDS = [
    "LUCKY LOCATOR",
    "SPRITE LOCATOR",
    "TREASURE LOCATOR",
    "LOOT LOCATOR",
    "PORTABLE EXTRACTOR",
    "EXTRACTION ACCELERATOR",
    "GIZMO",
]
DEFAULT_TOKEN_TEXT_KEYWORDS = [
    "PIRATE TOKEN",
    "PIRATE SHOP",
    "SHOP TOKEN",
    "TOKEN PIRATA",
    "PIRATE ACCESS",
    "FREE ITEM SHOP",
]


def load_config() -> dict:
    defaults = {
        "timer_seconds": 180,
        "drop_from_bus": True,
        "bus_wait_seconds": 8,
        "anti_kick_interval_seconds": 25,
        "scan_interval_seconds": 1.5,
        "menu_open_delay": 2.2,
        "rb_delay": 0.7,
        "confirm_delay": 0.8,
        "strict_mode_match": False,
        "allowed_modes": list(DEFAULT_ALLOWED_MODES),
        "blocked_modes": list(DEFAULT_BLOCKED_MODES),
        "gizmo_keywords": list(DEFAULT_GIZMO_KEYWORDS),
        "token_text_keywords": list(DEFAULT_TOKEN_TEXT_KEYWORDS),
        "token_template_threshold": 0.72,
        "gizmo_cooldown_seconds": 25,
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                defaults.update(data)
        except Exception:
            pass
    return defaults


class Dashboard:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.state = "STARTING"
        self.last_ocr = "--"
        self.last_frame = None
        self.last_lines = []
        self.timer_text = "--"
        self.display_label = "--"
        self.capture_info = "--"
        self.gizmo_summary = "0 found"
        self.token_status = "0 templates"
        self.matches = 0
        self.recovered = 0
        self.paused = False
        self.start_time = time.time()
        self.logs: deque[str] = deque(maxlen=12)

    def log(self, msg: str, color: str = Fore.WHITE):
        ts = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"{Fore.LIGHTBLACK_EX}[{ts}]{Style.RESET_ALL} {color}{msg}{Style.RESET_ALL}")
        self.render()

    def render(self):
        uptime = str(timedelta(seconds=int(time.time() - self.start_time)))
        status_col = Fore.YELLOW if self.paused else Fore.GREEN
        status_txt = "PAUSED" if self.paused else self.state
        ocr_preview = (self.last_ocr[:110] + "...") if len(self.last_ocr) > 110 else self.last_ocr

        os.system("cls")
        print(f"{Fore.CYAN}{Style.BRIGHT}======================================================================")
        print(f"  FORTNITE AUTO OCR  |  ViGEm Virtual Pad + RapidOCR  |  Timer: {self.cfg['timer_seconds']}s")
        print(f"======================================================================{Style.RESET_ALL}")
        print(f"  Status    : {status_col}{Style.BRIGHT}{status_txt}{Style.RESET_ALL}")
        print(f"  Display   : {Fore.MAGENTA}{self.display_label}{Style.RESET_ALL}")
        print(f"  Capture   : {Fore.LIGHTBLACK_EX}{self.capture_info}{Style.RESET_ALL}")
        print(f"  Timer     : {Fore.CYAN}{self.timer_text}{Style.RESET_ALL}")
        print(f"  Matches   : {Fore.GREEN}{self.matches}{Style.RESET_ALL}   |   Recovered: {Fore.YELLOW}{self.recovered}{Style.RESET_ALL}   |   Uptime: {uptime}")
        print(f"  Gizmos    : {Fore.YELLOW}{self.gizmo_summary}{Style.RESET_ALL}")
        print(f"  Token Img : {Fore.LIGHTBLACK_EX}{self.token_status}{Style.RESET_ALL}")
        print(f"  OCR       : {Fore.LIGHTBLACK_EX}{ocr_preview}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}----------------------------------------------------------------------{Style.RESET_ALL}")
        print(f"  Controls: [P] Pause   [T] Timer (180s/300s)   [M] Move Display   [D] Debug Snapshot   [Q] Quit")
        print(f"{Fore.CYAN}----------------------------------------------------------------------{Style.RESET_ALL}")
        for line in self.logs:
            print(f"  {line}")


class LootTracker:
    """Tracks session Gizmo drops (e.g. Lucky Locator) and stops if Pirate Token (image + text) is found."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        templates_dir = os.path.join(BASE_DIR, "templates")
        self.token_templates = load_token_templates(templates_dir, prefix="pirate_token")
        self.gizmo_counts: dict[str, int] = {}
        self.last_seen_ts: dict[str, float] = {}
        self.prev_scan_gizmos: set[str] = set()

    def token_status_label(self) -> str:
        if self.token_templates:
            names = ", ".join(t.name for t in self.token_templates[:2])
            return f"ACTIVE ({len(self.token_templates)} img: {names})"
        return "TEXT-ONLY STRICT (place templates/pirate_token.png for visual match)"

    def summary_text(self) -> str:
        total = sum(self.gizmo_counts.values())
        if total == 0:
            return "0 found"
        parts = [f"{k.title()}: {v}" for k, v in sorted(self.gizmo_counts.items())]
        return f"{total} found ({', '.join(parts)})"

    def _check_pirate_token(self, frame, txt: str, state: str) -> str | None:
        if not txt or state in ("WRONG_MENU", "DISCOVER_SCROLL", "WRONG_MODE", "LOADING"):
            return None
        # Ignore explanatory tips or news rules
        if any(bad in txt for bad in ("CAN GET", "COULD GET", "1 IN 137", "DROP RATE", "BREAKING THE RULES")):
            return None

        token_kws = [k.upper().strip() for k in self.cfg.get("token_text_keywords", DEFAULT_TOKEN_TEXT_KEYWORDS)]
        matched_kw = next((k for k in token_kws if k in txt), None)
        has_pair = ("PIRATE" in txt and "TOKEN" in txt) or ("PIRATA" in txt and "TOKEN" in txt)

        if self.token_templates:
            # Strict requirement: BOTH matching text AND visual token template image match!
            if not (matched_kw or has_pair):
                return None
            thresh = float(self.cfg.get("token_template_threshold", 0.72))
            score, tmpl_name = match_token_templates(frame, self.token_templates)
            if score >= thresh:
                kw_label = matched_kw or "PIRATE+TOKEN"
                return f"Image '{tmpl_name}' ({score:.2f} >= {thresh:.2f}) + text '{kw_label}'"
            return None

        # No template image present yet: only stop on unambiguous reward/claim confirmation text
        strict_phrases = ("PIRATE SHOP TOKEN", "TOKEN PIRATA", "PIRATE SHOP ACCESS", "FREE ITEM SHOP")
        if any(p in txt for p in strict_phrases):
            return f"Exact text '{matched_kw or 'PIRATE SHOP TOKEN'}' (add templates/pirate_token.png!)"
        if has_pair and any(c in txt for c in ("UNLOCKED", "CONGRATULATIONS", "CLAIM", "14 DAYS", "REWARD")):
            return "Pirate Token confirmation (add templates/pirate_token.png!)"
        return None

    def evaluate(self, frame, scan: ScreenScan, state: str, dash: Dashboard) -> str | None:
        """
        Inspects the scan for Pirate Token (returns reason str if found) and updates session Gizmo counts.
        """
        txt = scan.full_text
        if not txt:
            self.prev_scan_gizmos = set()
            return None

        # 1. Pirate Token check (image + text)
        token_reason = self._check_pirate_token(frame, txt, state)
        if token_reason is not None:
            return token_reason

        # 2. Gizmo counter (skip Shop/Locker/Discover/Queueing screens to avoid menu false counts)
        if state in ("WRONG_MENU", "DISCOVER_SCROLL", "QUEUEING", "BANNED"):
            self.prev_scan_gizmos = set()
            return None

        gizmo_kws = [k.upper().strip() for k in self.cfg.get("gizmo_keywords", DEFAULT_GIZMO_KEYWORDS)]
        specific = [k for k in gizmo_kws if k != "GIZMO"]
        found_now: set[str] = set()

        for kw in specific:
            if kw in txt:
                found_now.add(kw)

        if not found_now and "GIZMO" in gizmo_kws and re.search(r"\bGIZMO\b", txt):
            found_now.add("GIZMO")

        now = time.time()
        cooldown = float(self.cfg.get("gizmo_cooldown_seconds", 25))
        updated = False
        for g in sorted(found_now):
            last_t = self.last_seen_ts.get(g, 0.0)
            if g not in self.prev_scan_gizmos and (now - last_t >= cooldown):
                self.gizmo_counts[g] = self.gizmo_counts.get(g, 0) + 1
                self.last_seen_ts[g] = now
                updated = True
                dash.gizmo_summary = self.summary_text()
                dash.log(
                    f"GIZMO FOUND: {g.title()}! (Session: {self.gizmo_counts[g]} | Total: {sum(self.gizmo_counts.values())})",
                    Fore.YELLOW,
                )
                try:
                    log_path = os.path.join(BASE_DIR, "session_loot.log")
                    with open(log_path, "a", encoding="utf-8") as lf:
                        lf.write(
                            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                            f"GIZMO={g} count={self.gizmo_counts[g]} total={sum(self.gizmo_counts.values())} | OCR={txt[:140]}\n"
                        )
                except Exception:
                    pass

        self.prev_scan_gizmos = found_now
        if updated:
            dash.render()
        return None


_LOBBY_BTN_RE = re.compile(r"\b(PLAY|GIOCA|READY UP|READY|PRONTO)\b")

_NET_BTN_RE = re.compile(
    r"^\W*(?:\[\w+\]\s*|\(\w+\)\s*)?(?:CONTINUE|CONTINUA|RETRY|RIPROVA|OK)\W*$",
    re.IGNORECASE,
)


_BUS_JUMP_RE = re.compile(r"\b(JUMP|LANCIATI)\b")


_ISLAND_CODE_RE = re.compile(r"\b\d{4}-\d{4}-\d{4}\b")
_NON_EPIC_CREATOR_RE = re.compile(r"\bBY\s+(?!EPIC\b)[A-Z0-9_]{2,}")


def _matches_mode(mode_name: str, text: str, text_nospace: str) -> bool:
    """Word-boundary-safe mode name check (also tolerates merged OCR words of >=4 chars)."""
    m = mode_name.upper().strip()
    if not m:
        return False
    if re.search(rf"\b{re.escape(m)}\b", text):
        return True
    m_ns = m.replace(" ", "")
    return len(m_ns) >= 4 and m_ns in text_nospace


def _evaluate_lobby_mode(scan: ScreenScan, cfg: dict | None = None) -> tuple[str, str]:
    """
    Evaluates whether a visible PLAY/READY Lobby screen is Battle Royale or another mode.
    Returns (state, reason).
    """
    txt = scan.full_text
    allowed = [m.upper().strip() for m in (cfg or {}).get("allowed_modes", DEFAULT_ALLOWED_MODES)]
    blocked = [m.upper().strip() for m in (cfg or {}).get("blocked_modes", DEFAULT_BLOCKED_MODES)]
    blocked_clean = [b for b in blocked if b not in allowed]
    strict = bool((cfg or {}).get("strict_mode_match", False))

    # Active mode-card zone ONLY (cy <= 0.87 ignores the peeking Discover shelf below PLAY!)
    card_lines = [l.text for l in scan.lines if l.cx <= 0.45 and 0.50 <= l.cy <= 0.87]
    card_text = " ".join(card_lines)
    card_nospace = card_text.replace(" ", "")

    # Wide left/center excluding bottom peeking Discover shelf
    wide_left = " ".join(l.text for l in scan.lines if l.cx <= 0.60 and 0.25 <= l.cy <= 0.87)
    wide_left_ns = wide_left.replace(" ", "")

    # 1. Make sure another blocked mode (e.g. RELOAD, LEGO, FESTIVAL, OG) isn't explicitly on the mode card
    for b in blocked_clean:
        if _matches_mode(b, card_text, card_nospace):
            return "WRONG_MODE", b

    if _ISLAND_CODE_RE.search(card_text):
        return "WRONG_MODE", "CREATIVE ISLAND CODE"

    # 2. If Battle Royale (Zero Build or Build) is visible in Lobby, approve immediately!
    txt_ns = txt.replace(" ", "")
    if any(_matches_mode(a, wide_left, wide_left_ns) or _matches_mode(a, txt, txt_ns) for a in allowed):
        return "LOBBY_READY", "BATTLE ROYALE"

    # 3. If standard Lobby top tabs are missing, check wide area for promoted/Discover modal screens
    has_lobby_tabs = any(t in txt for t in ("LOCKER", "ARMADIETTO", "SHOP", "NEGOZIO", "QUESTS", "INCARICHI", "CAREER"))
    if not has_lobby_tabs:
        for b in blocked_clean:
            if _matches_mode(b, wide_left, wide_left_ns):
                return "WRONG_MODE", b
        if any(k in wide_left for k in ("EPIC'S PICKS", "DISCOVER", "SCOPRI")):
            return "WRONG_MODE", "DISCOVER"

    if strict:
        return "LOBBY_UNVERIFIED", "Battle Royale text not detected"

    # 4. Non-strict safe fallback (Battle Royale logo is often graphic artwork skipped by OCR)
    lobby_cues = (
        "LOCKER", "ARMADIETTO", "SHOP", "NEGOZIO", "QUESTS", "INCARICHI", "CAREER", "CARRIERA",
        "PASSES", "TREASURE", "COMPETE", "ZERO BUILD", "SQUAD", "SOLO", "DUO", "TRIO",
        "BY EPIC", "UNRANKED", "FILL", "NO FILL",
    )
    if any(k in txt for k in lobby_cues):
        return "LOBBY_READY", "LOBBY VERIFIED (no blocked mode)"

    return "LOBBY_UNVERIFIED", "Screen not recognized as Battle Royale Lobby"


_QUEUE_LOADING_RE = re.compile(r"\b(LOADING|CARICAMENTO)\b")
_CANCEL_WORD_RE = re.compile(r"\b(CANCEL|ANNULLA)\b")
_PLAY_WORD_RE = re.compile(r"\bPLAY\b")


def _queue_trigger_reason(txt: str) -> str | None:
    is_downtime_notice = any(
        d in txt for d in ("SCHEDULED", "DOWNTIME", "WILL END", "WILLEND", "SHORTLY", "BEGINS AT", "MANUTENZIONE")
    )
    queue_kw = (
        "CONNECTING", "CONNESSIONE", "LOGGING IN", "TRAVELING",
        "FINDING MATCH", "RICERCA PARTITA", "MATCHMAKING",
        "PREPARING", "PREPARAZIONE", "CHECKING FOR", "CONTROLLO",
        "WAITING FOR SERVER", "WAITING FOR PARTY", "ATTESA SERVER",
        "UNREADY", "NON PRONTO",
    )
    for k in queue_kw:
        if k == "MATCHMAKING" and is_downtime_notice:
            continue
        if k in txt:
            return k
    m = _QUEUE_LOADING_RE.search(txt)
    if m:
        return m.group(0)
    if _CANCEL_WORD_RE.search(txt):
        queue_ctx = (
            "LOCKER", "ARMADIETTO", "SHOP", "NEGOZIO", "QUESTS", "CAREER",
            "MATCH RECAP", "MATCHRECAP", "YOU PLACED", "RETURN TO LOBBY", "TORNA ALLA LOBBY",
            "FINDING", "RICERCA",
        )
        for c in queue_ctx:
            if c in txt:
                return f"CANCEL+{c}"
        if _PLAY_WORD_RE.search(txt):
            return "CANCEL+PLAY"
    return None


_BAN_PHRASE_RE = re.compile(
    r"\b("
    r"YOU HAVE BEEN BANNED|YOU ARE BANNED|YOU'VE BEEN BANNED|YOU WERE BANNED|"
    r"ACCOUNT HAS BEEN BANNED|ACCOUNT BANNED|YOUR ACCOUNT IS BANNED|"
    r"BANNED FROM FORTNITE|BANNED FROM MATCHMAKING|BANNED FROM COMPETITIVE|"
    r"PERMANENTLY BANNED|TEMPORARILY BANNED|MATCHMAKING BAN|COMPETITIVE BAN|"
    r"BANNED FOR \d+|"
    r"YOU HAVE BEEN SUSPENDED|YOU ARE SUSPENDED|ACCOUNT HAS BEEN SUSPENDED|"
    r"ACCOUNT SUSPENDED|TEMPORARILY SUSPENDED|"
    r"ACCOUNT DISABLED|YOUR ACCOUNT IS CURRENTLY DISABLED|ACCOUNT IS DISABLED|"
    r"MATCHMAKING RESTRICTED|RESTRICTED FROM MATCHMAKING|"
    r"MATCHMAKING PENALTY|ABANDON PENALTY|LEAVER PENALTY|"
    r"SEI STATO BANNAT[OA]|ACCOUNT BANNATO|BAN TEMPORANEO|BAN PERMANENTE|"
    r"SEI STATO SOSPESO|ACCOUNT SOSPESO|ACCOUNT DISABILITATO|"
    r"PENALITA MATCHMAKING|LIMITAZIONE MATCHMAKING|RESTRIZIONE MATCHMAKING"
    r")\b"
)
_BAN_FALSE_TIP_RE = re.compile(
    r"(CAN GET YOU BANNED|COULD GET YOU BANNED|GET YOU BANNED|"
    r"BREAKING THE RULES|COMMUNITY RULES|REPORTED FOR)"
)
_BAN_DUR_RE = re.compile(
    r"\b(\d+)\s*(DAYS?|GIORN[IO]|HOURS?|HRS?|OR[AE]|MINUTES?|MINS?|MINUT[IO]|SECONDS?|SECS?|SECOND[IO])\b"
)
_BAN_CLOCK_RE = re.compile(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b")


def is_real_ban_screen(txt: str) -> bool:
    """Returns True only for genuine account/matchmaking ban or suspension notices, never loading tips."""
    if not txt:
        return False
    # Loading / Connecting screens (e.g. "Breaking the rules can get you banned from voice chat.") are NOT bans
    if any(k in txt for k in ("CONNECTING", "CONNESSIONE")) or _QUEUE_LOADING_RE.search(txt):
        return False
    if _BAN_FALSE_TIP_RE.search(txt):
        return False
    return bool(_BAN_PHRASE_RE.search(txt))


def extract_ban_duration(txt: str) -> str:
    """Extracts human-readable ban duration in minutes from OCR text."""
    if any(k in txt for k in ("PERMANENT", "PERMANENTLY", "PERMANENTE")):
        return "PERMANENT"

    total_minutes = 0
    matched_parts: list[str] = []
    for num_s, unit in _BAN_DUR_RE.findall(txt):
        val = int(num_s)
        u = unit.upper()
        if u.startswith(("DAY", "GIORN")):
            total_minutes += val * 1440
        elif u.startswith(("HOUR", "HR", "OR")):
            total_minutes += val * 60
        elif u.startswith("MIN"):
            total_minutes += val
        elif u.startswith("SEC"):
            total_minutes += max(1, (val + 59) // 60)
        matched_parts.append(f"{val} {unit}")

    if matched_parts:
        return f"{total_minutes} minutes ({', '.join(matched_parts)})"

    cm = _BAN_CLOCK_RE.search(txt)
    if cm:
        a, b, c = int(cm.group(1)), int(cm.group(2)), cm.group(3)
        if c is not None:
            mins = a * 60 + b + (1 if int(c) > 0 else 0)
            return f"{mins} minutes ({cm.group(0)})"
        else:
            mins = a + (1 if b > 0 else 0)
            return f"{mins} minutes ({cm.group(0)})"

    return "unspecified duration"


def classify_screen(scan: ScreenScan, cfg: dict | None = None) -> str:
    txt = scan.full_text
    if not txt:
        return "LOADING"

    # 0. Account / Matchmaking Ban / Suspension (MUST run before NETWORK_ERROR / CONTINUE!)
    if is_real_ban_screen(txt):
        return "BANNED"

    # 1. Network / Whoops error popup
    net_kw = (
        "WHOOPS", "NO NETWORK", "NO_NETWORK", "CONNECTION ERROR",
        "ERRORE DI RETE", "CONNESSIONE PERSA", "DISCONNECTED", "DISCONNESSO",
        "MATCHMAKING ERROR", "ERRORE MATCHMAKING", "FAILED TO CONNECT",
        "UNEXPECTED ERROR", "ERRORE INATTESO",
    )
    if any(k in txt for k in net_kw):
        return "NETWORK_ERROR"

    # Centered standalone CONTINUE / RETRY / OK button alone (isolated button on error popup)
    for line in scan.lines:
        t_clean = line.text.strip()
        if len(t_clean) <= 16 and _NET_BTN_RE.match(t_clean):
            if 0.30 <= line.cx <= 0.70 and 0.35 <= line.cy <= 0.80:
                return "NETWORK_ERROR"

    # 2. Fortnite Sleep Mode
    sleep_kw = ("SLEEP MODE", "MODALITA RIPOSO", "MODALITÀ RIPOSO", "IS IN SLEEP", "WAKE UP", "SVEGLIA")
    if any(k in txt for k in sleep_kw):
        return "SLEEP_MODE"

    # 3. Leave match confirmation dialog
    if any(k in txt for k in ("ARE YOU SURE", "SEI SICURO", "LEAVE MATCH?", "ABBANDONARE")):
        return "LEAVE_CONFIRM"

    # 4. Match Recap Queued (Play Again already clicked -> CANCEL/FINDING active) & TRUE Match Ended
    is_recap_screen = any(
        k in txt
        for k in (
            "PLAY AGAIN", "PLAYAGAIN", "GIOCA ANCORA",
            "MATCH RECAP", "MATCHRECAP", "RIEPILOGO PARTITA",
            "YOU PLACED", "SEI ARRIVATO",
            "RETURN TO LOBBY", "TORNA ALLA LOBBY",
        )
    )
    if is_recap_screen:
        q_reason = _queue_trigger_reason(txt)
        if q_reason is not None:
            return "QUEUEING"
        return "MATCH_ENDED"

    # 5. Pre-match Spawn Island (never override with QUEUEING)
    spawn_kw = (
        "LAUNCHING IN", "BUS LAUNCHING", "PARTENZA TRA",
        "WAITING FOR PLAYERS", "IN ATTESA DI GIOCATORI",
        "WARM UP", "RISCALDAMENTO", "MATCH STARTING", "INIZIO PARTITA",
    )
    if any(k in txt for k in spawn_kw):
        return "SPAWN_ISLAND"

    # 6. Battle Bus / One Piece Ship
    bus_kw = (
        "THANK THE BUS", "THANK BUS", "BUS DRIVER",
        "THE CAPTAIN", "THECAPTAIN",
        "RINGRAZIA", "AUTISTA", "EXIT BUS", "ESCI DAL BUS",
    )
    if any(k in txt for k in bus_kw):
        return "ON_BUS"

    for line in scan.lines:
        if 0.35 <= line.cy <= 0.96 and _BUS_JUMP_RE.search(line.text):
            return "ON_BUS"

    # 7. Explicit In-Game cues BEFORE generic QUEUEING words (prevents RELOADING/CANCEL traps in-game)
    ingame_kw = (
        "DELTAPLANO", "GLIDER", "DEPLOY", "APRI DELTAPLANO",
        "TEMPESTA", "STORM", "ELIMINATIONS", "ELIMINAZIONI",
        "INVENTORY", "INVENTARIO", "COSTRUISCI", "ACCOVACCIATI",
        "SPECTATING", "SPETTATORE", "ELIMINATED BY", "ELIMINATO DA",
        "REBOOT", "RIAVVIO", "RELOAD",
    )
    has_lobby_tabs = any(k in txt for k in ("LOCKER", "ARMADIETTO", "SHOP", "NEGOZIO", "CAREER", "CARRIERA"))
    if not has_lobby_tabs and any(k in txt for k in ingame_kw):
        return "IN_GAME"

    # 8. Connecting / Loading / Lobby Queueing
    if _queue_trigger_reason(txt) is not None:
        return "QUEUEING"

    # 9. HUD fallback for In-Game (no lobby tabs + player count / timer in top-right)
    if not has_lobby_tabs:
        for l in scan.lines:
            if l.cx > 0.72 and l.cy < 0.45 and any(ch.isdigit() for ch in l.text):
                if len(l.text) <= 12:
                    return "IN_GAME"

    # 10. Scrolled-down Discover / Promoted Game Carousel (e.g. "Continue Playing", "GO TO LOBBY", "PEGI")
    # Must run BEFORE Lobby check so tiny bottom cards like "BATTLE ROYALE" in Continue Playing never trigger Y!
    discover_kw = (
        "GO TO LOBBY", "VAI ALLA LOBBY",
        "CONTINUE PLAYING", "CONTINUA A GIOCARE",
        "CUSTOM KEY", "CHIAVE PERSONALIZZATA",
        "READY TO EXPLORE",
        "EPIC'S PICKS", "EPICS PICKS",
        "RECENTLY PLAYED", "GIOCATI DI RECENTE",
        "PEGI",
    )
    txt_ns = txt.replace(" ", "")
    if any(k in txt or k.replace(" ", "") in txt_ns for k in discover_kw):
        return "DISCOVER_SCROLL"

    # 11. Lobby Main Screen (mode verification before allowing PLAY / Y!)
    has_lobby_btn = any(line.cy >= 0.50 and _LOBBY_BTN_RE.search(line.text) for line in scan.lines)
    if has_lobby_btn:
        lobby_state, _reason = _evaluate_lobby_mode(scan, cfg)
        return lobby_state

    # 12. Top-bar tabs (PASSES, QUESTS, SHOP, LOCKER, etc.) -> Navigate back to PLAY via LB
    top_bar_kw = ("TREASURE", "TESORO", "SHOP", "NEGOZIO", "LOCKER", "ARMADIETTO", "PASSES", "PASS", "QUESTS", "INCARICHI", "COMPETE", "COMPETIZIONE", "CAREER", "CARRIERA")
    has_top_tabs = any(line.cy <= 0.12 and any(t in line.text for t in top_bar_kw) for line in scan.lines)
    if has_top_tabs and not has_lobby_btn:
        return "WRONG_MENU"

    # 13. Claim / Reward popup (only when NOT on a lobby tab or in battle pass)
    claim_kw = ("CLAIM", "RISCATTA", "LEVEL UP", "LIVELLO SUPERATO", "REWARD UNLOCKED", "RICOMPENSA")
    is_bp_screen = any(k in txt for k in ("BATTLE PASS", "PASS BATTAGLIA", "PASSES & FN CREW", "GET BATTLE PASS"))
    if not is_bp_screen and any(k in txt for k in claim_kw):
        if not has_lobby_btn:
            return "POPUP_CLAIM"

    # 14. Top Bar Non-Play Tabs / Settings / Shop / Locker / Submenu fallback
    wrong_kw = (
        "ITEM SHOP", "NEGOZIO", "LOCKER", "ARMADIETTO", "BATTLE PASS", "PASS BATTAGLIA", "PASSES",
        "QUESTS", "INCARICHI", "CAREER", "CARRIERA", "SETTINGS",
        "IMPOSTAZIONI", "CREW", "V-BUCKS", "DISCOVER", "SCOPRI",
        "NEWS", "NOTIZIE", "SUPPORT", "SUPPORTO",
        "TREASURE", "TESORO", "COMPETE", "COMPETIZIONE",
    )
    if any(k in txt for k in wrong_kw):
        return "WRONG_MENU"

    return "UNKNOWN"


def _toggle_fortnite_display(dash: Dashboard):
    """Moves Fortnite window to the next display (e.g. primary monitor <-> drawing tablet)."""
    displays = list_displays()
    if len(displays) < 2:
        dash.log("Only one display detected.", Fore.YELLOW)
        return
    hwnd = find_fortnite_hwnd()
    if not hwnd:
        dash.log("Open Fortnite first before moving it to another display.", Fore.YELLOW)
        return
    cur = get_window_display(hwnd)
    cur_idx = next((i for i, d in enumerate(displays) if cur and d.hmonitor == cur.hmonitor), 0)
    target = displays[(cur_idx + 1) % len(displays)]
    if move_window_to_display(hwnd, target):
        dash.display_label = target.label()
        dash.log(f"Moved Fortnite to: {target.label()}", Fore.MAGENTA)
    else:
        dash.log("Failed to move Fortnite window (try Win+Shift+Arrow).", Fore.RED)


_last_auto_dump = 0.0


def _write_debug_files(
    dash: Dashboard,
    txt_name: str,
    img_name: str,
    box,
    disp,
    frame,
    scan_lines,
):
    txt_path = os.path.join(BASE_DIR, txt_name)
    img_path = os.path.join(BASE_DIR, img_name)
    try:
        if frame is not None:
            cv2.imwrite(img_path, frame)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"Time: {datetime.now().strftime('%H:%M:%S')}\n")
            f.write(f"State: {dash.state}\n")
            f.write(f"Backend: {ocr_mod.LAST_CAPTURE_METHOD}\n")
            f.write(f"Display: {disp.label() if disp else '--'}\n")
            f.write(f"CaptureRect: {box}\n")
            f.write(f"FrameShape: {None if frame is None else frame.shape}\n")
            f.write(f"OCR: {dash.last_ocr}\n")
            for l in scan_lines:
                f.write(f"  [{l.cx:.2f}, {l.cy:.2f}] ({l.score:.2f}) {l.text}\n")
    except Exception:
        pass


def _save_debug_snapshot(dash: Dashboard):
    """Saves last captured frame & OCR coordinates for troubleshooting display/tablet issues."""
    hwnd = find_fortnite_hwnd()
    box = get_capture_rect(hwnd) if hwnd else None
    disp = get_window_display(hwnd) if hwnd else None
    frame = dash.last_frame if dash.last_frame is not None else (capture_window(hwnd) if hwnd else None)
    _write_debug_files(dash, "debug_ocr.txt", "debug_capture.png", box, disp, frame, dash.last_lines)
    dash.log("Saved debug_capture.png + debug_ocr.txt!", Fore.MAGENTA)


def check_keys(dash: Dashboard, cfg: dict) -> bool:
    """Handles [P]ause, [T]imer toggle, [M]ove display, [D]ebug snapshot, [Q]uit."""
    while msvcrt.kbhit():
        ch = msvcrt.getch().decode("utf-8", errors="ignore").lower()
        if ch == "q":
            return False
        elif ch == "p":
            dash.paused = not dash.paused
            dash.log("Bot PAUSED." if dash.paused else "Bot RESUMED.", Fore.YELLOW)
        elif ch == "t":
            cfg["timer_seconds"] = 300 if cfg["timer_seconds"] == 180 else 180
            dash.log(f"Timer switched to {cfg['timer_seconds']}s.", Fore.CYAN)
        elif ch == "m":
            _toggle_fortnite_display(dash)
        elif ch == "d":
            _save_debug_snapshot(dash)
    return True


def leave_match(pad: VirtualPad, ocr: FortniteOCR, hwnd: int, dash: Dashboard, cfg: dict):
    """Executes Menu -> RB -> RB -> A and verifies departure via OCR."""
    # Pre-check: if match already truly ended (Match Recap) or already back in Lobby, do not open Menu
    frame = capture_window(hwnd)
    if frame is not None:
        scan = ocr.scan(frame)
        st = classify_screen(scan, cfg)
        if st in ("MATCH_ENDED", "LOBBY_READY", "WRONG_MODE", "LOBBY_UNVERIFIED", "QUEUEING"):
            dash.log(f"Leave not needed ({st}), continuing.", Fore.CYAN)
            return

    dash.state = "LEAVING MATCH"
    dash.log("Timer finished -> Executing Menu -> RB -> RB -> A", Fore.CYAN)

    pad.press(Btn.MENU, hold_ms=300, after_wait=cfg["menu_open_delay"])
    pad.press(Btn.RB, hold_ms=250, after_wait=cfg["rb_delay"])
    pad.press(Btn.RB, hold_ms=250, after_wait=cfg["confirm_delay"])
    pad.press(Btn.A, hold_ms=350, after_wait=2.0)

    # Check if a confirmation dialog appeared
    frame = capture_window(hwnd)
    if frame is not None:
        scan = ocr.scan(frame)
        dash.last_ocr = scan.full_text or "--"
        st = classify_screen(scan, cfg)
        if st == "LEAVE_CONFIRM":
            dash.log("Leave confirmation detected -> Pressing A", Fore.YELLOW)
            pad.press(Btn.A, hold_ms=300, after_wait=2.0)

    dash.matches += 1
    dash.log("Leave sequence complete. Waiting for Lobby...", Fore.GREEN)
    time.sleep(5.0)


def drop_from_bus_sequence(
    pad: VirtualPad, ocr: FortniteOCR, hwnd: int, dash: Dashboard, cfg: dict
) -> str:
    """Waits bus_wait_seconds on the Battle Bus / One Piece ship, then jumps with A."""
    bus_wait = float(cfg.get("bus_wait_seconds", 8))
    dash.state = "ON BUS / SHIP"
    dash.log(f"On Bus / Ship detected! Waiting {int(bus_wait)}s before jumping...", Fore.GREEN)
    end_bus = time.time() + bus_wait
    while time.time() < end_bus:
        if not check_keys(dash, cfg):
            return "QUIT"
        if dash.paused:
            time.sleep(0.5)
            continue
        dash.timer_text = f"Jumping in {int(max(0, end_bus - time.time()))}s"
        dash.render()
        time.sleep(1.0)

    dash.timer_text = "--"
    dash.log("Jumping from Bus / Ship (Pressing A)!", Fore.CYAN)
    pad.press(Btn.A, hold_ms=350, after_wait=1.5)

    # Double-check jump succeeded in case jump unlocked slightly late
    frame = capture_window(hwnd)
    if frame is not None:
        scan = ocr.scan(frame)
        dash.last_ocr = scan.full_text or "--"
        if classify_screen(scan, cfg) == "ON_BUS":
            dash.log("Still on Bus -> Pressing A again to jump!", Fore.YELLOW)
            pad.press(Btn.A, hold_ms=350, after_wait=1.0)

    return "DONE"


def run_match_timer(
    pad: VirtualPad,
    ocr: FortniteOCR,
    hwnd: int,
    dash: Dashboard,
    cfg: dict,
    start_from_bus: bool = False,
    is_spectating: bool = False,
    loot: LootTracker | None = None,
) -> tuple[str, tuple[str, str] | None]:
    """Runs the in-game survival timer with bus-drop detection, loot/token tracking, anti-kick, and early-end checks."""
    bus_dropped = is_spectating

    if start_from_bus and cfg.get("drop_from_bus", True) and not is_spectating:
        if drop_from_bus_sequence(pad, ocr, hwnd, dash, cfg) == "QUIT":
            return "QUIT", None
        bus_dropped = True

    total = int(cfg["timer_seconds"])
    dash.state = "SPECTATING SQUAD (TIMER)" if is_spectating else "IN MATCH (TIMER)"
    dash.log(
        f"Match timer started ({'spectating squad' if is_spectating else 'in game'}): {total} seconds.",
        Fore.GREEN,
    )

    start_t = time.time()
    last_nudge = start_t
    last_ocr_check = start_t
    toggle = False
    nudge_interval = float(cfg.get("anti_kick_interval_seconds", 25))

    while True:
        if not check_keys(dash, cfg):
            return "QUIT", None
        if dash.paused:
            time.sleep(0.5)
            continue

        elapsed = time.time() - start_t
        rem = int(max(0, total - elapsed))
        dash.timer_text = f"{rem}s remaining / {total}s"
        dash.render()

        if elapsed >= total:
            dash.timer_text = "--"
            leave_match(pad, ocr, hwnd, dash, cfg)
            return "DONE", None

        # Periodic anti-kick movement
        if time.time() - last_nudge >= nudge_interval:
            last_nudge = time.time()
            toggle = not toggle
            pad.anti_kick_nudge(toggle_action=toggle)

        # Poll OCR every 2s before bus drop, otherwise every 3.5s to catch Gizmos / Token / Match Recap
        check_interval = 2.0 if (not bus_dropped and elapsed < 45.0) else 3.5
        if time.time() - last_ocr_check >= check_interval:
            last_ocr_check = time.time()
            frame = capture_window(hwnd)
            if frame is not None:
                scan = ocr.scan(frame)
                dash.last_frame = frame
                dash.last_lines = scan.lines
                dash.last_ocr = scan.full_text or "--"
                st = classify_screen(scan, cfg)

                if loot is not None:
                    tok_reason = loot.evaluate(frame, scan, st, dash)
                    if tok_reason is not None:
                        dash.timer_text = "--"
                        cur_disp = get_window_display(hwnd)
                        box = get_capture_rect(hwnd)
                        _write_debug_files(
                            dash, "pirate_token_ocr.txt", "pirate_token_capture.png", box, cur_disp, frame, scan.lines
                        )
                        return "TOKEN_FOUND", (tok_reason, scan.full_text)

                if st == "SPAWN_ISLAND" and not bus_dropped:
                    dash.timer_text = "--"
                    dash.log("Spawn island detected -> waiting for Bus / Ship launch.", Fore.LIGHTBLUE_EX)
                    return "EARLY_END", None
                if st == "ON_BUS" and not bus_dropped and cfg.get("drop_from_bus", True):
                    if drop_from_bus_sequence(pad, ocr, hwnd, dash, cfg) == "QUIT":
                        return "QUIT", None
                    bus_dropped = True
                    start_t = time.time()
                    last_nudge = start_t
                    dash.state = "IN MATCH (TIMER)"
                    dash.log(f"Dropped from Bus! Starting {total}s timer.", Fore.GREEN)
                    continue
                if st == "BANNED":
                    dash.timer_text = "--"
                    return "EARLY_END", None
                if st in ("MATCH_ENDED", "LOBBY_READY", "WRONG_MODE", "LOBBY_UNVERIFIED", "NETWORK_ERROR", "SLEEP_MODE"):
                    dash.timer_text = "--"
                    if st == "MATCH_ENDED":
                        dash.log("Match ended (Match Recap) -> Switching to Play Again.", Fore.CYAN)
                    else:
                        dash.recovered += 1
                        dash.log(f"Screen changed ({st}) -> Stopping timer.", Fore.YELLOW)
                    return "EARLY_END", None

        time.sleep(1.0)


def main():
    cfg = load_config()
    dash = Dashboard(cfg)
    loot = LootTracker(cfg)
    dash.token_status = loot.token_status_label()
    dash.log("Initializing RapidOCR and ViGEm Virtual Pad...", Fore.CYAN)

    ocr = FortniteOCR()
    pad = VirtualPad()
    displays = list_displays()
    for d in displays:
        dash.log(f"Display detected: {d.label()}", Fore.MAGENTA if d.is_tablet else Fore.LIGHTBLACK_EX)
    if not loot.token_templates:
        dash.log("Note: no templates/pirate_token.png found (using strict text-only mode).", Fore.YELLOW)
    dash.log("Virtual Xbox 360 Controller active! Looking for Fortnite window...", Fore.GREEN)

    wrong_menu_streak = 0
    wrong_mode_streak = 0
    discover_streak = 0
    match_ended_streak = 0
    match_ended_counted = False
    last_lobby_ready_press = 0.0
    last_fn_hmon = 0
    ban_alert: tuple[str, str] | None = None
    token_alert: tuple[str, str] | None = None

    try:
        while True:
            if not check_keys(dash, cfg):
                break
            if dash.paused:
                time.sleep(0.4)
                continue

            hwnd = find_fortnite_hwnd()
            if not hwnd:
                dash.state = "WAITING FOR FORTNITE"
                dash.display_label = "--"
                dash.capture_info = "--"
                dash.timer_text = "--"
                dash.last_ocr = "Fortnite window not found (launch it or un-minimize)"
                dash.render()
                time.sleep(2.5)
                continue

            cur_disp = get_window_display(hwnd)
            if cur_disp is not None:
                dash.display_label = cur_disp.label()
                if cur_disp.hmonitor != last_fn_hmon:
                    last_fn_hmon = cur_disp.hmonitor
                    if move_console_away_from_fortnite(hwnd):
                        dash.log("Console moved to secondary display to avoid covering the game.", Fore.CYAN)

            box = get_capture_rect(hwnd)
            focused = is_window_focused(hwnd)
            if box is not None:
                dash.capture_info = f"({box[0]},{box[1]}) {box[2]}x{box[3]} | Focus: {'YES' if focused else 'NO (click Fortnite)'}"
            else:
                dash.capture_info = "--"

            frame = capture_window(hwnd)
            if frame is None:
                dash.state = "WINDOW MINIMIZED"
                dash.last_ocr = "Cannot capture: do not minimize Fortnite"
                dash.render()
                time.sleep(2.0)
                continue

            scan = ocr.scan(frame)
            dash.last_frame = frame
            dash.last_lines = scan.lines
            dash.last_ocr = scan.full_text or "(loading screen / no text)"
            state = classify_screen(scan, cfg)
            dash.state = state
            dash.render()

            global _last_auto_dump
            if time.time() - _last_auto_dump >= 3.0:
                _last_auto_dump = time.time()
                _write_debug_files(dash, "last_debug.txt", "last_frame.jpg", box, cur_disp, frame, scan.lines)

            tok_reason = loot.evaluate(frame, scan, state, dash)
            if tok_reason is not None:
                dash.state = "PIRATE TOKEN FOUND!"
                _write_debug_files(
                    dash, "pirate_token_ocr.txt", "pirate_token_capture.png", box, cur_disp, frame, scan.lines
                )
                dash.log(f"!!! PIRATE TOKEN FOUND ({tok_reason}) !!!", Fore.GREEN)
                print("\a\a\a", end="", flush=True)
                token_alert = (tok_reason, scan.full_text)
                break

            if state == "BANNED":
                dur = extract_ban_duration(scan.full_text)
                dash.state = f"BANNED ({dur})"
                _write_debug_files(dash, "ban_ocr.txt", "ban_capture.png", box, cur_disp, frame, scan.lines)
                dash.log(f"!!! BAN DETECTED: ACCOUNT BANNED FOR {dur} !!!", Fore.RED)
                print("\a\a", end="", flush=True)
                ban_alert = (dur, scan.full_text)
                break

            elif state == "NETWORK_ERROR":
                dash.recovered += 1
                dash.log("Network error popup detected -> Pressing A", Fore.RED)
                pad.press(Btn.A, hold_ms=300, after_wait=3.5)
                wrong_menu_streak = 0
                wrong_mode_streak = 0
                match_ended_streak = 0

            elif state == "SLEEP_MODE":
                dash.recovered += 1
                dash.log("Sleep mode detected -> Pressing A to wake up", Fore.YELLOW)
                pad.press(Btn.A, hold_ms=300, after_wait=2.5)
                wrong_menu_streak = 0
                wrong_mode_streak = 0
                match_ended_streak = 0

            elif state == "POPUP_CLAIM":
                dash.recovered += 1
                dash.log("Reward/level popup detected -> Pressing A", Fore.YELLOW)
                pad.press(Btn.A, hold_ms=250, after_wait=1.5)
                wrong_menu_streak = 0
                wrong_mode_streak = 0
                match_ended_streak = 0

            elif state == "MATCH_ENDED":
                wrong_menu_streak = 0
                wrong_mode_streak = 0
                match_ended_streak += 1
                if not match_ended_counted:
                    dash.matches += 1
                    match_ended_counted = True

                has_play_again = any(k in scan.full_text for k in ("PLAY AGAIN", "PLAYAGAIN", "GIOCA ANCORA"))
                if match_ended_streak >= 3:
                    dash.log("Match end stuck -> Pressing B then Down + A", Fore.YELLOW)
                    pad.press(Btn.B, hold_ms=200, after_wait=0.6)
                    pad.press(Btn.DOWN, hold_ms=150, after_wait=0.4)
                    pad.press(Btn.A, hold_ms=300, after_wait=3.0)
                elif has_play_again:
                    dash.log("Match ended -> Starting next match (A)", Fore.CYAN)
                    pad.press(Btn.A, hold_ms=300, after_wait=3.5)
                else:
                    dash.log("Match ended -> Pressing A to continue", Fore.CYAN)
                    pad.press(Btn.A, hold_ms=300, after_wait=3.0)

            elif state == "LEAVE_CONFIRM":
                dash.log("Leave confirmation dialog -> Pressing A", Fore.CYAN)
                pad.press(Btn.A, hold_ms=300, after_wait=2.5)
                wrong_menu_streak = 0
                wrong_mode_streak = 0
                match_ended_streak = 0

            elif state == "SPAWN_ISLAND":
                wrong_menu_streak = 0
                wrong_mode_streak = 0
                match_ended_streak = 0
                match_ended_counted = False
                dash.log("Spawn island -> waiting for Bus / Ship launch...", Fore.LIGHTBLUE_EX)
                time.sleep(1.5)

            elif state == "ON_BUS":
                wrong_menu_streak = 0
                wrong_mode_streak = 0
                match_ended_streak = 0
                match_ended_counted = False
                res, tok_info = run_match_timer(
                    pad, ocr, hwnd, dash, cfg, start_from_bus=True, is_spectating=False, loot=loot
                )
                if res == "TOKEN_FOUND" and tok_info is not None:
                    token_alert = tok_info
                    print("\a\a\a", end="", flush=True)
                    break
                if res == "QUIT":
                    break

            elif state == "IN_GAME":
                wrong_menu_streak = 0
                wrong_mode_streak = 0
                match_ended_streak = 0
                match_ended_counted = False
                is_spec = any(
                    k in scan.full_text for k in ("SPECTATING", "SPETTATORE", "ELIMINATED BY", "ELIMINATO DA")
                )
                res, tok_info = run_match_timer(
                    pad, ocr, hwnd, dash, cfg, start_from_bus=False, is_spectating=is_spec, loot=loot
                )
                if res == "TOKEN_FOUND" and tok_info is not None:
                    token_alert = tok_info
                    print("\a\a\a", end="", flush=True)
                    break
                if res == "QUIT":
                    break

            elif state == "QUEUEING":
                wrong_menu_streak = 0
                wrong_mode_streak = 0
                match_ended_streak = 0
                match_ended_counted = False
                q_why = (_queue_trigger_reason(scan.full_text) or "?").lower()
                dash.log(f"Queueing / matchmaking ({q_why}), waiting...", Fore.LIGHTBLUE_EX)
                time.sleep(2.0)

            elif state == "LOBBY_READY":
                wrong_menu_streak = 0
                wrong_mode_streak = 0
                discover_streak = 0
                match_ended_streak = 0
                match_ended_counted = False
                if time.time() - last_lobby_ready_press > 5.0:
                    last_lobby_ready_press = time.time()
                    msg = "Battle Royale Lobby ready -> Pressing Y!"
                    if not focused:
                        msg += " [Focus NO: click Fortnite if it does not ready up]"
                    dash.log(msg, Fore.GREEN)
                    pad.press(Btn.Y, hold_ms=300, after_wait=2.5)

            elif state == "DISCOVER_SCROLL":
                wrong_menu_streak = 0
                wrong_mode_streak = 0
                match_ended_streak = 0
                discover_streak += 1
                dash.recovered += 1
                if discover_streak % 4 == 0:
                    dash.log("Discover screen still open -> Pressing B to close", Fore.YELLOW)
                    pad.press(Btn.B, hold_ms=250, after_wait=1.5)
                else:
                    dash.log("Discover / Promo screen detected -> Flicking left stick UP!", Fore.YELLOW)
                    pad.flick_stick_up(hold_ms=220, after_wait=1.5)

            elif state == "WRONG_MODE":
                wrong_menu_streak = 0
                discover_streak = 0
                wrong_mode_streak += 1
                match_ended_streak = 0
                _, reason = _evaluate_lobby_mode(scan, cfg)
                if wrong_mode_streak <= 2:
                    dash.recovered += 1
                    dash.log(f"BLOCKED MODE ({reason}) -> Pressing B to exit promo/card", Fore.RED)
                    pad.press(Btn.B, hold_ms=250, after_wait=1.5)
                else:
                    dash.log(f"PLAY BLOCKED ({reason}): Select 'Battle Royale' in Lobby!", Fore.RED)
                    time.sleep(2.0)

            elif state == "LOBBY_UNVERIFIED":
                wrong_menu_streak = 0
                wrong_mode_streak += 1
                match_ended_streak = 0
                _, reason = _evaluate_lobby_mode(scan, cfg)
                if wrong_mode_streak == 3:
                    dash.recovered += 1
                    dash.log(f"{reason} -> Pressing B to dismiss any popup", Fore.YELLOW)
                    pad.press(Btn.B, hold_ms=250, after_wait=1.5)
                else:
                    dash.log(f"PLAY BLOCKED: {reason}", Fore.YELLOW)

            elif state == "WRONG_MENU":
                wrong_menu_streak += 1
                wrong_mode_streak = 0
                match_ended_streak = 0
                dash.recovered += 1
                dash.log(f"Non-PLAY tab/menu detected (LB press #{wrong_menu_streak}) -> Pressing LB toward PLAY", Fore.YELLOW)
                # If stuck after multiple LB presses, tap B first in case a sub-modal or item inspect is open
                if wrong_menu_streak % 3 == 0:
                    pad.press(Btn.B, hold_ms=200, after_wait=0.4)
                pad.press(Btn.LB, hold_ms=220, after_wait=0.8)

            else:
                # LOADING / UNKNOWN
                pass

            time.sleep(float(cfg.get("scan_interval_seconds", 1.5)))

    except KeyboardInterrupt:
        pass
    finally:
        pad.close()
        if token_alert is not None:
            tok_reason, raw_txt = token_alert
            print(f"\n{Fore.GREEN}{Style.BRIGHT}======================================================================")
            print(f"  PIRATE TOKEN FOUND!! BOT STOPPED!")
            print(f"  Match    : {tok_reason}")
            print(f"  Gizmos   : {loot.summary_text()}")
            print(f"  Screen   : {raw_txt[:150]}")
            print(f"  Saved    : pirate_token_capture.png + pirate_token_ocr.txt")
            print(f"======================================================================{Style.RESET_ALL}")
        elif ban_alert is not None:
            dur, raw_txt = ban_alert
            print(f"\n{Fore.RED}{Style.BRIGHT}======================================================================")
            print(f"  WARNING: BAN / SUSPENSION DETECTED!")
            print(f"  Duration : Banned for {dur}")
            print(f"  Screen   : {raw_txt[:160]}")
            print(f"  The bot stopped automatically (saved ban_capture.png / ban_ocr.txt).")
            print(f"======================================================================{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.YELLOW}Bot stopped and virtual controller disconnected.{Style.RESET_ALL}")


if __name__ == "__main__":
    main()

