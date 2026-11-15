"""Live view in WebKit (Safari's engine). Safari's fetch() cannot read multipart/x-mixed-replace ("Load failed"),
which Chromium tests alone would never notice. Needs `pip install playwright && playwright install webkit`
(on Linux also `playwright install-deps webkit`). Starts its own manager on 127.0.0.1:8433 with the fake fleet."""
import atexit, os, subprocess, sys, tempfile, time
from playwright.sync_api import sync_playwright, expect

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAKE = os.path.join(ROOT, "tools", "fake_adb.py")
TMP = tempfile.mkdtemp(prefix="tvm-webkit-")
os.environ.update(FAKE_ADB_STATE=os.path.join(TMP, "fleet.json"), TVM_PASSWORD="testpass123", TVM_PORT="8433",
                  TVM_HOST="127.0.0.1", TVM_DATA=os.path.join(TMP, "data"), TVM_ADB=FAKE, TVM_POLL="1")
subprocess.run([sys.executable, FAKE, "ctl", "seed"], check=True)
server = subprocess.Popen([sys.executable, "-m", "tvmanager"], cwd=ROOT)
atexit.register(server.terminate)
time.sleep(2)


import re


def assert_clean(pg, where):
    m = re.search(r"(^|\n)\s*(null|undefined|NaN)\s*(\n|$)", pg.inner_text("body"))
    assert not m, "literal %r leaked onto the page at: %s" % (m.group(2), where)


def frame_ready(pg):
    return pg.locator(".live-img:not(.hidden)").count() and pg.eval_on_selector(".live-img", "el => el.naturalWidth") > 200


with sync_playwright() as p:
    b = p.webkit.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 860}); pg.set_default_timeout(15000)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:8433/?nosso"); pg.fill("#pw", "testpass123"); pg.press("#pw", "Enter")
    pg.wait_for_selector("text=Add your first TV")
    pg.evaluate("""() => fetch('/api/devices', {method: 'POST', credentials: 'same-origin',
        headers: {'X-Requested-With': 'tvm', 'Content-Type': 'application/json'}, body: JSON.stringify({name: 'Lobby', addr: '10.0.0.11'})})""")
    pg.wait_for_selector(".card[aria-label='Open Lobby'] .status:text-is('On')", timeout=20000)
    pg.locator(".card[aria-label='Open Lobby']").click(); pg.click("role=tab[name='Screen']")
    assert_clean(pg, "Screen tab before starting")
    pg.click(".viewer-overlay .big-play")
    for _ in range(120):
        if frame_ready(pg):
            break
        pg.wait_for_timeout(250)
    else:
        raise AssertionError("WebKit never showed a live frame; overlay says: " + pg.inner_text(".viewer-overlay"))
    expect(pg.locator(".live-badge")).to_be_visible(); assert_clean(pg, "Screen tab while live")
    pg.screenshot(path=os.path.join(TMP, "webkit_live.png"))
    pg.click(".viewer-tools >> text=Stop"); expect(pg.locator(".viewer-overlay .big-play")).to_be_visible()
    b.close()
server.terminate()
print("WebKit live view OK (screenshot %s/webkit_live.png); page errors: %s" % (TMP, errs or "none"))
