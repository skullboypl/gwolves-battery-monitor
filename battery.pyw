import os, asyncio, re, time, threading
from PIL import Image, ImageDraw, ImageFont
import pystray
from playwright.async_api import async_playwright

# --- Make Playwright find bundled browsers inside PyInstaller onefile ---
import sys
from pathlib import Path

# When running as onefile, PyInstaller extracts to a temp dir in sys._MEIPASS
_BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
_BROWSERS = _BUNDLE_DIR / "ms-playwright"
# Tell Playwright to use our bundled browsers dir (not user profile)
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_BROWSERS))

# --- Bootstrap przeglądarki, gdy katalog ms-playwright jest pusty ---
import subprocess, shutil

def _chromium_present(root: Path) -> bool:
    try:
        next(root.rglob("chrome.exe"))
        return True
    except StopIteration:
        return False

# Preferuj lokalny ms-playwright (dla PyInstaller)
LOCAL_MS = _BROWSERS
if not LOCAL_MS.exists():
    LOCAL_MS.mkdir(parents=True, exist_ok=True)

if not _chromium_present(LOCAL_MS):
    # jeśli brak chromium w lokalnym ms-playwright → zainstaluj tam
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(LOCAL_MS)
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except Exception as e:
        # awaryjnie: spróbuj użyć globalnego cache
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
else:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(LOCAL_MS)


URL = "https://mouse.fit" # NEW LINK FOR OLD WEBSITE Mouse.xyz is new website
POLL_EVERY_SECONDS = 10 * 60
CONNECT_BUTTONS = ['button:has(.n-button__content:has-text("Connect"))']
PERCENT_RE = re.compile(r'(\d{1,3})\s*%')

# First-read stabilization
WARMUP_AFTER_CONNECT_MS = 5000    # wait after HID authorization (5 s)
STABILIZE_SAMPLES = 3             # consecutive identical samples required
STABILIZE_INTERVAL_MS = 1000      # gap between stabilization samples
FIRST_READ_TIMEOUT_MS = 30000     # max time to get a stable first read

# ---------- Native WebHID picker auto-click (Windows) ----------
import time as _t
try:
    from pywinauto import Desktop
except Exception:
    Desktop = None  # pozwala uruchomić się bez pywinauto (bez auto-accept)

def auto_accept_hid_dialog(device_index=0, timeout=20):
    """
    Searches the Chromium/Edge native WebHID dialog, selects a device, clicks "Connect".
    Returns True on success.
    """
    if Desktop is None:
        return False
    t0 = _t.time()
    title_re = r".*połączyć z urządzeniem HID|.*connect to a HID device"
    while _t.time() - t0 < timeout:
        try:
            dlg = Desktop(backend="uia").window(title_re=title_re, control_type="Window")
            if dlg.exists(timeout=0.2):
                lst = dlg.child_window(control_type="List")
                items = lst.children()
                if items:
                    idx = max(0, min(device_index, len(items)-1))
                    items[idx].select()
                    items[idx].click_input()
                btn = (dlg.child_window(title="Połącz", control_type="Button")
                       or dlg.child_window(title="Connect", control_type="Button")
                       or dlg.child_window(title_re="Połącz|Connect", control_type="Button"))
                btn.click_input()
                return True
        except Exception:
            pass
        _t.sleep(0.3)
    return False

# ---------- WinAPI: hide/show Chromium window in the Windows taskbar ----------
import ctypes
from ctypes import wintypes
user32 = ctypes.WinDLL('user32', use_last_error=True)
EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
GetWindowTextLengthW = user32.GetWindowTextLengthW
GetWindowTextW = user32.GetWindowTextW
GetWindowLongW = user32.GetWindowLongW
SetWindowLongW = user32.SetWindowLongW
ShowWindow = user32.ShowWindow
SetForegroundWindow = user32.SetForegroundWindow
GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
SW_HIDE, SW_SHOW, SW_RESTORE = 0, 5, 9

def _iter_hwnds_with_title(substr: str):
    matches = []
    substr = substr.lower()
    def _enum(hwnd, _):
        length = GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length+1)
            GetWindowTextW(hwnd, buf, length+1)
            if substr in buf.value.lower():
                matches.append(hwnd)
        return True
    EnumWindows(EnumWindowsProc(_enum), 0)
    return matches

def hide_from_taskbar_by_title(title="HID Worker"):
    for hwnd in _iter_hwnds_with_title(title):
        style = GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
        SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        ShowWindow(hwnd, SW_HIDE)

def show_on_taskbar_by_title(title="HID Worker"):
    for hwnd in _iter_hwnds_with_title(title):
        style = GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
        SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        ShowWindow(hwnd, SW_SHOW)
        ShowWindow(hwnd, SW_RESTORE)
        try:
            SetForegroundWindow(hwnd)
        except Exception:
            pass

# ---------- DOM helpers ----------
async def wait_for_app_ready(page, timeout=30000):
    await page.wait_for_load_state('domcontentloaded')
    await page.wait_for_function("""
        () => {
          const hasRoot = document.querySelector('#root, #app, [data-v-app]');
          const hasUI   = document.querySelector('.n-button__content, .n-progress, .n-form-item');
          return !!(hasRoot || hasUI);
        }
    """, timeout=timeout)
    await page.wait_for_timeout(200)
    try:
        await page.wait_for_load_state('networkidle', timeout=2000)
    except Exception:
        pass

async def wait_for_hid_authorized(page, timeout=30000):
    # waits until navigator.hid.getDevices() yields at least 1 device (after picker approval)
    return await page.wait_for_function(
        " () => navigator.hid.getDevices().then(ds => ds && ds.length > 0) ",
        timeout=timeout
    )

async def get_percent_from_dom(page):
    row = page.locator('.n-form-item:has(.n-form-item-label__text:has-text("Battery"))').first
    if await row.count() == 0:
        rows = page.locator('.n-form-item'); n = await rows.count(); row = None
        for i in range(n):
            lbl = rows.nth(i).locator('.n-form-item-label__text')
            if await lbl.count():
                if (await lbl.inner_text()).strip() == 'Battery':
                    row = rows.nth(i); break
        if row is None:
            html = await page.content()
            m = PERCENT_RE.search(html)
            return (int(m.group(1)), 'regex') if m else (None, 'no-row')

    prog = row.locator('.n-progress[role="progressbar"]').first
    if await prog.count():
        val = await prog.get_attribute('aria-valuenow')
        if val and val.isdigit():
            return int(val), 'aria-valuenow'

    ind = row.locator('.n-progress-graph-line-indicator').first
    if await ind.count():
        m = PERCENT_RE.search((await ind.inner_text()).strip())
        if m:
            return int(m.group(1)), '.n-progress-graph-line-indicator'
    return None, 'no-value'

async def read_stable_percent(page):
    """
    After HID is authorized:
     - wait WARMUP_AFTER_CONNECT_MS,
     - sample every STABILIZE_INTERVAL_MS,
     - return once STABILIZE_SAMPLES identical values were observed.
    """
    await page.wait_for_timeout(WARMUP_AFTER_CONNECT_MS)

    deadline = time.time() + FIRST_READ_TIMEOUT_MS / 1000
    last = None
    streak = 0
    best = None

    while time.time() < deadline:
        val, _src = await get_percent_from_dom(page)
        if val is not None:
            best = val
            if val == last:
                streak += 1
            else:
                streak = 1
                last = val
            if streak >= STABILIZE_SAMPLES:
                return val
        await page.wait_for_timeout(STABILIZE_INTERVAL_MS)

    # fallback: if stabilization failed, return last sensible value
    return best

async def click_connect_if_present(page):
    clicked = False
    for sel in CONNECT_BUTTONS:
        loc = page.locator(sel).first
        if await loc.count():
            try:
                await loc.click(); clicked = True; break
            except Exception:
                pass
    if not clicked:
        span = page.locator('.n-button__content:has-text("Connect")').first
        if await span.count():
            try:
                await span.evaluate('el => el.closest("button")?.click()'); clicked = True
            except Exception:
                pass
    return clicked

async def connect_and_read_percent(page, device_index=0):
    """Flow: reload -> app ready -> Connect -> auto-accept -> HID ready -> stable %."""
    await page.reload(wait_until="domcontentloaded")
    await wait_for_app_ready(page)

    # Spróbuj kliknąć „Connect” (jeśli trzeba)
    await click_connect_if_present(page)

    # Autoklik natywnego selektora WebHID (wątek w tle)
    threading.Thread(target=auto_accept_hid_dialog,
                     kwargs={"device_index": device_index, "timeout": 20},
                     daemon=True).start()

    # Czekaj aż HID będzie autoryzowany
    try:
        await wait_for_hid_authorized(page, timeout=30000)
    except Exception:
        # jeśli prawo było nadane wcześniej – ok
        pass

    # Stabilny odczyt po rozgrzaniu
    pct = await read_stable_percent(page)
    return pct

# ---------- CDP window helpers ----------
async def get_window_id(page):
    cdp = await page.context.new_cdp_session(page)
    win = await cdp.send('Browser.getWindowForTarget')
    return cdp, win['windowId']

async def hide_window(page):
    try:
        cdp, wid = await get_window_id(page)
        await cdp.send('Browser.setWindowBounds', {'windowId': wid,
            'bounds': {'left': -32000, 'top': -32000, 'width': 900, 'height': 700}})
        await cdp.send('Browser.setWindowBounds', {'windowId': wid,
            'bounds': {'windowState': 'minimized'}})
    except Exception:
        pass

async def show_window(page, left=(1920-1000)//2, top=(1080-800)//2):
    """Restore to NORMAL and place the window in a reasonable position."""
    try:
        cdp, wid = await get_window_id(page)
        await cdp.send('Browser.setWindowBounds', {
            'windowId': wid,
            'bounds': {'windowState': 'normal'}
        })
        await cdp.send('Browser.setWindowBounds', {
            'windowId': wid,
            'bounds': {'left': int(left), 'top': int(top), 'width': 1000, 'height': 800}
        })
    except Exception:
        pass

# ---------- Tray ----------
class TrayController:
    def __init__(self):
        self.icon = pystray.Icon("mouse_batt_dom", make_icon(None), "Mouse Battery")
        self._is_hidden = False
        self._loop_stop = threading.Event()
        self._refresh_cb = None
        self._toggle_cb = None
        self.icon.menu = pystray.Menu(
            pystray.MenuItem("Refresh now", self._on_refresh),
            pystray.MenuItem(lambda _: "Hide window" if not self._is_hidden else "Show window",
                             self._on_toggle_window),
            pystray.MenuItem("Quit", self._on_quit)
        )
    def _on_refresh(self, *_):
        if self._refresh_cb: self._refresh_cb()
    def _on_toggle_window(self, *_):
        self._is_hidden = not self._is_hidden
        if self._toggle_cb: self._toggle_cb(self._is_hidden)
    def _on_quit(self, *_):
        self._loop_stop.set(); self.icon.stop()
    def set_percent(self, pct):
        self.icon.icon = make_icon(pct)
        self.icon.title = f"Battery: {pct}%" if pct is not None else "Battery: --"

def make_icon(percent):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    txt = "--" if percent is None else str(percent)
    try:
        font = ImageFont.truetype("arialbd.ttf", 48)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", 48)
        except Exception:
            font = ImageFont.load_default()
    try:
        w, h = d.textsize(txt, font=font)
        y = (64 - h)//2
    except AttributeError:
        bbox = d.textbbox((0,0), txt, font=font)
        w = bbox[2] - bbox[0]; h = bbox[3] - bbox[1]; y = (64 - h)//2 - bbox[1]
    d.text(((64 - w)//2, y), txt, font=font, fill=(255,255,255,255))
    return img

# ---------- Main logic ----------
async def main_async(tray: TrayController):
    async with async_playwright() as p:
        PROFILE_DIR = r"C:\ProgramData\GwovesBatteryChromium"
        os.makedirs(PROFILE_DIR, exist_ok=True)

        browser = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            args=[
                "--enable-experimental-web-platform-features",
                "--force-dark-mode",
                "--enable-features=WebContentsForceDark",
                "--window-size=900,700",
                "--disable-session-crashed-bubble",   # blokuje „Przywróć stronę”
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-popup-blocking",
                "--noerrdialogs",
            ],
            color_scheme="dark"
        )

        page = await browser.new_page()
        await page.goto(URL)
        await wait_for_app_ready(page)
        await show_window(page)  # normalize & center-ish

        # 1) Pierwszy pełny odczyt (z połączeniem HID)
        pct = await connect_and_read_percent(page, device_index=0)
        tray.set_percent(pct)
        print(f"Start battery: {pct}%")

        # 2) Po pierwszym odczycie: ustaw tytuł, ukryj z paska, zminimalizuj okno
        await page.evaluate("document.title = 'HID Worker'")
        await page.wait_for_timeout(500)  # daj Windowsowi czas na zaciągnięcie tytułu
        hide_from_taskbar_by_title("HID Worker")
        await hide_window(page)
        tray._is_hidden = True

        loop = asyncio.get_event_loop()

        async def refresh_once():
            # Pełny flow z ponownym połączeniem i stabilizacją
            new_pct = await connect_and_read_percent(page, device_index=0)
            if new_pct is not None:
                tray.set_percent(new_pct)
                print(f"[{time.strftime('%H:%M:%S')}] {new_pct}%")
            # Jeśli okno ma być ukryte – po re-read przywróć stan ukrycia
            if tray._is_hidden:
                await page.evaluate("document.title = 'HID Worker'")
                hide_from_taskbar_by_title("HID Worker")
                await hide_window(page)

        def refresh_from_tray():
            asyncio.run_coroutine_threadsafe(refresh_once(), loop)

        def toggle_window(hidden: bool):
            if hidden:
                # schowaj
                asyncio.run_coroutine_threadsafe(
                    page.evaluate("document.title = 'HID Worker'"), loop
                ).result()
                hide_from_taskbar_by_title("HID Worker")
                asyncio.run_coroutine_threadsafe(hide_window(page), loop)
            else:
                # pokaż
                show_on_taskbar_by_title("HID Worker")
                asyncio.run_coroutine_threadsafe(show_window(page), loop)

        tray._refresh_cb = refresh_from_tray
        tray._toggle_cb = toggle_window

        # 3) Periodic refresh (co 10 min) – pełny flow (reload + reconnect)
        while not tray._loop_stop.is_set():
            await refresh_once()
            for _ in range(POLL_EVERY_SECONDS // 5):
                if tray._loop_stop.is_set(): break
                await page.wait_for_timeout(5000)

        await browser.close()

# ---------- Entry ----------
def run():
    tray = TrayController()
    loop = asyncio.new_event_loop()
    def loop_runner():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main_async(tray))
    threading.Thread(target=loop_runner, daemon=True).start()
    tray.icon.run()

if __name__ == "__main__":
    run()
