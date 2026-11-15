"""Browser end-to-end test of the whole UI against a simulated fleet (needs `pip install playwright`
and a Chromium; run `python tests/e2e_ui.py` from the repo root). It starts its own manager on
127.0.0.1:8431 with a throwaway data dir and tools/fake_adb.py, so it never touches real TVs."""
import atexit, os, re, subprocess, sys, tempfile, time
from playwright.sync_api import sync_playwright, expect
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAKE = os.path.join(ROOT, "tools", "fake_adb.py")
TMP = tempfile.mkdtemp(prefix="tvm-e2e-")
OUT = TMP
os.environ.update(FAKE_ADB_STATE=os.path.join(TMP, "fleet.json"), TVM_PASSWORD="testpass123", TVM_PORT="8431",
                  TVM_HOST="127.0.0.1", TVM_DATA=os.path.join(TMP, "data"), TVM_ADB=FAKE, TVM_POLL="1")
subprocess.run([sys.executable, FAKE, "ctl", "seed"], check=True)
server = subprocess.Popen([sys.executable, "-m", "tvmanager"], cwd=ROOT)
atexit.register(server.terminate)   # never leave the helper server behind, even if a check fails
time.sleep(2)
ctl = lambda *a: subprocess.run([sys.executable, FAKE, "ctl", *a], capture_output=True, text=True).stdout
errs = []

def assert_clean(pg, where):
    txt = pg.inner_text("body")
    m = re.search(r"(^|\n)\s*(null|undefined|NaN)\s*(\n|$)", txt)
    assert not m, "literal %r leaked onto the page at: %s" % (m.group(2), where)
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 860})
    pg.set_default_timeout(10000)
    pg.on("pageerror", lambda e: errs.append("pageerror: %s" % e))
    pg.on("console", lambda m: errs.append("console.%s: %s" % (m.type, m.text)) if m.type in ("error", "warning") else None)
    pg.goto("http://127.0.0.1:8431/?nosso")  # nosso: skip the Services Hub redirect (web/sso.js)
    pg.wait_for_selector("#pw"); pg.screenshot(path=OUT + "/f_login.png")
    pg.fill("#pw", "wrong"); pg.press("#pw", "Enter"); pg.wait_for_selector(".err:has-text('wrong password')")
    pg.fill("#pw", "testpass123"); pg.press("#pw", "Enter"); pg.wait_for_selector("text=Add your first TV")
    # add the five fake TVs through the dialog
    for name, addr, grp in [("Lobby", "10.0.0.11", "Lobby"), ("Gym", "10.0.0.12", "Fitness"), ("Cafe", "10.0.0.13", "Lobby"), ("Office", "10.0.0.14", "Offices"), ("Spare", "10.0.0.15", "")]:
        pg.get_by_role("button", name=re.compile(r"^Add (device|your first TV)$")).click(); pg.fill("#an", name); pg.fill("#aa", addr); pg.fill("#ag", grp)
        pg.click(".modal button:text-is('Add')"); pg.wait_for_selector(".card[aria-label='Open %s']" % name)
    # duplicate rejected
    pg.click("#fab"); pg.fill("#an", "dup"); pg.fill("#aa", "10.0.0.11"); pg.click(".modal button:text-is('Add')")
    pg.wait_for_selector(".modal .err:has-text('already exists')"); pg.keyboard.press("Escape")
    pg.wait_for_timeout(6000)
    expect(pg.locator(".card[aria-label='Open Lobby'] .status")).to_have_text("On")
    expect(pg.locator(".card[aria-label='Open Office'] .status")).to_contain_text("Needs approval")
    expect(pg.locator(".card[aria-label='Open Spare'] .status")).to_have_text("Offline")
    pg.screenshot(path=OUT + "/f_devices.png")
    # approve Office on the "TV" and watch it come online
    ctl("approve", "10.0.0.14:5555"); pg.wait_for_timeout(5000)
    expect(pg.locator(".card[aria-label='Open Office'] .status")).to_have_text("On")
    # group filter chips
    pg.click(".chip:has-text('Lobby')"); assert pg.locator(".card").count() == 2; pg.click(".chip:has-text('All')")
    # remote: switch input from Inputs tab, set as power-on
    pg.locator(".card[aria-label='Open Lobby']").click(); pg.wait_for_selector(".drawer")
    pg.click("role=tab[name='Inputs']"); pg.wait_for_selector("text=Soundbar")
    pg.locator(".row:has-text('Soundbar') >> text=Switch").click(); pg.wait_for_timeout(2500)
    expect(pg.locator(".row:has-text('Soundbar') .badge.active")).to_have_text("Active")
    pg.screenshot(path=OUT + "/f_inputs.png")
    assert "HW2" in ctl("list")
    # keyboard remote
    pg.click("role=tab[name='Remote']"); pg.check("#kbctl"); pg.keyboard.press("ArrowDown")
    pg.screenshot(path=OUT + "/f_remote.png")
    # apps: disable netflix then re-enable
    pg.click("role=tab[name='Apps']"); pg.wait_for_selector(".row:has-text('com.netflix.ninja')")
    pg.locator(".row:has-text('com.netflix.ninja') >> text=Disable").click(); pg.wait_for_timeout(1500)
    pg.select_option("select[aria-label='Package filter']", "disabled"); pg.wait_for_selector(".row:has-text('com.netflix.ninja') .chip-s")
    pg.screenshot(path=OUT + "/f_apps.png")
    pg.locator(".row:has-text('com.netflix.ninja') >> text=Enable").click(); pg.wait_for_timeout(1500)
    # install an APK
    pg.click("role=tab[name='Install']"); open(OUT + "/t.apk", "wb").write(b"PK\x03\x04fake")
    pg.set_input_files("#apkf", OUT + "/t.apk"); pg.click("text=Upload & install"); pg.wait_for_selector("pre.out:has-text('Success')")
    # shell + info
    pg.click("role=tab[name='Shell']"); pg.click(".chip:has-text('Disabled packages')"); pg.wait_for_selector("pre.out:has-text('tvlauncher')")
    pg.click("role=tab[name='Info']"); pg.wait_for_selector("text=Storage"); assert_clean(pg, "Info tab"); pg.screenshot(path=OUT + "/f_info.png")
    # live screen view: the simulated TV streams a test pattern (screenrecord -> ffmpeg -> JPEG frames)
    pg.click("role=tab[name='Screen']"); assert_clean(pg, "Screen tab, TV not on HDMI"); pg.screenshot(path=OUT + "/f_screen_idle.png"); pg.click(".viewer-overlay .big-play")
    for _ in range(100):      # wait for a real decoded frame (the page CSP forbids wait_for_function's string eval)
        if pg.locator(".live-img:not(.hidden)").count() and pg.eval_on_selector(".live-img", "el => el.naturalWidth") > 200:
            break
        pg.wait_for_timeout(250)
    else:
        raise AssertionError("live view never showed a frame")
    expect(pg.locator(".live-badge")).to_be_visible(); pg.wait_for_timeout(1500); pg.screenshot(path=OUT + "/f_screen_live.png")
    pg.select_option("select[aria-label='Quality']", "low"); pg.wait_for_timeout(2500)
    expect(pg.locator(".live-badge")).to_be_visible()
    pg.click(".viewer-tools >> text=Stop"); expect(pg.locator(".viewer-overlay .big-play")).to_be_visible()
    pg.keyboard.press("Escape")
    pg.locator(".card[aria-label='Open Cafe']").click(); pg.wait_for_selector(".drawer"); pg.click("role=tab[name='Screen']"); pg.click(".viewer-overlay .big-play")
    expect(pg.locator(".viewer-msg")).to_contain_text("No video from the TV", timeout=20000); assert_clean(pg, "Screen error state"); pg.screenshot(path=OUT + "/f_screen_error.png"); pg.keyboard.press("Escape")
    # standby -> wake -> expect auto restore of Soundbar on Lobby
    pg.locator(".card[aria-label='Open Lobby'] >> text=Standby").click(); pg.wait_for_timeout(3500)
    expect(pg.locator(".card[aria-label='Open Lobby'] .status")).to_have_text("Standby")
    pg.locator(".card[aria-label='Open Lobby'] >> text=Wake").click(); pg.wait_for_timeout(9000)
    assert "HW2" in [l for l in ctl("list").splitlines() if "10.0.0.11" in l][0], ctl("list")
    # bulk: select all lobby-group, standby
    pg.click(".chip:has-text('Lobby')"); pg.click("text=Select all"); pg.click(".bulkbar >> text=Standby"); pg.wait_for_timeout(3500)
    pg.screenshot(path=OUT + "/f_bulk.png")
    # schedule
    pg.click("nav >> text=Schedules"); pg.click("#fab"); pg.fill("#sn1", "Morning on"); pg.fill("#st1", "07:30")
    pg.click(".modal .chip:has-text('Lobby')"); pg.click(".modal >> text=Save"); pg.wait_for_selector(".sched:has-text('Morning on')")
    pg.screenshot(path=OUT + "/f_sched.png")
    # activity log
    pg.click("nav >> text=Activity"); pg.wait_for_selector(".ev:has-text('restored input')"); assert_clean(pg, "Activity"); pg.screenshot(path=OUT + "/f_activity.png")
    # change password + relogin
    pg.click("nav >> text=Settings"); pg.fill("#pc", "testpass123"); pg.fill("#pn", "newpass4567"); pg.click("text=Update"); pg.wait_for_selector("text=Password changed")
    # appearance: dark theme + teal accent, then back to the devices page
    pg.click("nav >> text=Settings"); pg.click("button:text-is('Dark')"); pg.click("button.swatch[aria-label='Teal']"); pg.wait_for_timeout(500)
    assert pg.evaluate("document.documentElement.dataset.theme") == "dark"
    pg.screenshot(path=OUT + "/f_settings_dark.png")
    pg.click("nav >> text=Devices"); pg.wait_for_timeout(1500); pg.screenshot(path=OUT + "/f_devices_dark.png")
    pg.locator(".card[aria-label='Open Lobby']").click(); pg.wait_for_selector(".drawer"); pg.wait_for_timeout(800)
    pg.screenshot(path=OUT + "/f_remote_dark.png"); pg.keyboard.press("Escape")
    pg.click("nav >> text=Settings"); pg.click("button:text-is('Light')"); pg.click("button.swatch[aria-label='Blue']")
    # mobile layout
    pg.set_viewport_size({"width": 390, "height": 800}); pg.click("nav >> text=Devices"); pg.wait_for_timeout(1500); pg.screenshot(path=OUT + "/f_mobile.png")
    pg.locator(".card[aria-label='Open Lobby']").click(); pg.wait_for_selector(".drawer"); pg.wait_for_timeout(900); pg.screenshot(path=OUT + "/f_mobile_sheet.png")
    # Safari-style browser: fetch() has no streaming body, so the viewer must fall back to a plain <img>
    pg2 = b.new_context(viewport={"width": 1280, "height": 860}).new_page(); pg2.set_default_timeout(15000)
    pg2.add_init_script("Object.defineProperty(Response.prototype, 'body', { get() { return null; } });")
    pg2.goto("http://127.0.0.1:8431/?nosso"); pg2.fill("#pw", "newpass4567"); pg2.press("#pw", "Enter")
    pg2.locator(".card[aria-label='Open Lobby']").click(); pg2.click("role=tab[name='Screen']"); pg2.click(".viewer-overlay .big-play")
    for _ in range(100):
        if pg2.locator(".live-img:not(.hidden)").count() and pg2.eval_on_selector(".live-img", "el => el.naturalWidth") > 200:
            break
        pg2.wait_for_timeout(250)
    else:
        raise AssertionError("img fallback never showed a frame")
    expect(pg2.locator(".live-badge")).to_be_visible(); pg2.screenshot(path=OUT + "/f_screen_imgfallback.png")
    b.close()
server.terminate()
print("UI flow OK (screenshots in %s); errors:" % TMP, errs or "none")
