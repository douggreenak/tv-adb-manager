"""Browser test of the schedule calendar's interactions (needs playwright + Chromium; run from the repo root).
Starts its own manager on 127.0.0.1:8435 with a throwaway data dir and the fake TV fleet."""
import atexit, json, os, subprocess, sys, tempfile, time
from playwright.sync_api import sync_playwright, expect

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAKE = os.path.join(ROOT, "tools", "fake_adb.py")
TMP = tempfile.mkdtemp(prefix="tvm-cal-")
OUT = os.environ.get("CAL_OUT", TMP)
os.environ.update(FAKE_ADB_STATE=os.path.join(TMP, "fleet.json"), TVM_PASSWORD="testpass123", TVM_PORT="8435",
                  TVM_HOST="127.0.0.1", TVM_DATA=os.path.join(TMP, "data"), TVM_ADB=FAKE, TVM_POLL="1")
subprocess.run([sys.executable, FAKE, "ctl", "seed"], check=True)
server = subprocess.Popen([sys.executable, "-m", "tvmanager"], cwd=ROOT)
atexit.register(server.terminate)
time.sleep(2)
BASE = "http://127.0.0.1:8435"
errs = []
HOUR = 44


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page(); pg.set_default_timeout(8000)
    pg.on("pageerror", lambda e: errs.append("pageerror: %s" % e))
    pg.on("console", lambda m: errs.append("console.%s: %s" % (m.type, m.text)) if m.type in ("error", "warning") else None)
    pg.goto(BASE + "/?nosso"); pg.fill("#pw", "testpass123"); pg.press("#pw", "Enter"); pg.wait_for_selector("text=Add your first TV")
    api = lambda path: ctx.request.get(BASE + path).json()
    hdr = {"X-Requested-With": "tvm", "Content-Type": "application/json"}
    for name, addr in [("Lobby", "10.0.0.11"), ("Gym", "10.0.0.12"), ("Cafe", "10.0.0.13")]:
        ctx.request.post(BASE + "/api/devices", headers=hdr, data=json.dumps({"name": name, "addr": addr}))
    ids = {d["name"]: d["id"] for d in api("/api/devices")["devices"]}
    wins = lambda: sorted([x for x in api("/api/schedules")["schedules"] if x.get("kind") == "window"], key=lambda x: (x["start"], x["name"]))
    pg.reload(); pg.click("nav >> text=Schedules"); pg.wait_for_selector(".cal-col"); pg.wait_for_timeout(400)

    col = lambda d: pg.locator(".cal-col[data-day='%d']" % d)
    def ypx(d, minutes): return col(d).bounding_box()["y"] + minutes / 60 * HOUR
    def xmid(d): bb = col(d).bounding_box(); return bb["x"] + bb["width"] / 2
    def drag(d, m0, m1, steps=6):
        pg.mouse.move(xmid(d), ypx(d, m0)); pg.mouse.down(); pg.mouse.move(xmid(d), (ypx(d, m0) + ypx(d, m1)) / 2, steps=steps); pg.mouse.move(xmid(d), ypx(d, m1), steps=steps); pg.mouse.up()
    def wait_dialog(): pg.wait_for_selector(".modal"); pg.wait_for_timeout(100)
    def save(): pg.click(".modal button:text-is('Save')"); pg.wait_for_selector(".modal", state="detached")
    def blocks(): return pg.locator(".cal-block")
    def settle(): pg.wait_for_timeout(700)

    # ---- the page itself -------------------------------------------------
    now = api("/api/schedules")["now"]
    check(pg.locator(".cal-day.today").count() == 1 and pg.locator(".cal-col.today").get_attribute("data-day") == str(now["wday"]), "today column")
    pg.wait_for_selector(".cal-hint")
    sc_top = lambda: pg.eval_on_selector(".cal-scroll", "e => e.scrollTop")
    check(sc_top() > 0, "calendar should open scrolled to the morning, not midnight")
    # the now-line sits at the server's current time
    top = pg.eval_on_selector(".cal-now", "e => parseFloat(e.style.top)")
    hh, mm = map(int, now["time"].split(":"))
    check(abs(top - (hh * 60 + mm) / 60 * HOUR) < 3, "now-line at server time: %s vs %s" % (top, (hh * 60 + mm) / 60 * HOUR))
    pg.screenshot(path=OUT + "/c01_empty.png")

    # ---- creating --------------------------------------------------------
    drag(1, 11 * 60, 9 * 60)                                           # drag UPWARD
    wait_dialog(); check((pg.input_value("#ws"), pg.input_value("#we")) == ("09:00", "11:00"), "upward drag normalises")
    check(len(pg.locator(".cal-ghost").all()) == 0, "ghost removed")
    pg.keyboard.press("Escape"); pg.wait_for_selector(".modal", state="detached"); check(wins() == [], "Escape must not create")
    drag(1, 600, 600 + 5, steps=2)                                     # 5-minute wiggle = a click = one hour
    wait_dialog(); check((pg.input_value("#ws"), pg.input_value("#we")) == ("10:00", "11:00"), "tiny drag acts like a click")
    pg.mouse.click(5, 5); pg.wait_for_selector(".modal", state="detached")   # click on the backdrop closes
    pg.mouse.click(xmid(2), ypx(2, 12 * 60 + 20)); wait_dialog()
    check(pg.input_value("#ws") in ("12:15", "12:30"), "click snaps to 15 minutes: " + pg.input_value("#ws"))
    # validation, all in one dialog
    pg.click(".modal .chip:text-is('All TVs')")                          # deselect everything
    check("Choose at least one TV" in pg.inner_text(".cal-summary"), pg.inner_text(".cal-summary"))
    pg.click(".modal button:text-is('Save')"); pg.wait_for_selector(".modal .err:has-text('TV')"); check(pg.locator(".modal").count() == 1, "stays open on error")
    pg.click(".modal .chip:text-is('All TVs')")
    pg.fill("#we", pg.input_value("#ws")); check("Choose a start and end" in pg.inner_text(".cal-summary"), "zero length")
    pg.click(".modal button:text-is('Save')"); pg.wait_for_selector(".modal .err:has-text('different')")
    pg.fill("#we", "14:00"); pg.fill("#ws", "13:00")
    pg.click(".modal .chips.days .chip:text-is('Wed')"); check("Choose at least one day" in pg.inner_text(".cal-summary"), "no days")
    pg.click(".modal button:text-is('Weekdays')")
    check(pg.locator(".chips.days .chip[aria-pressed='true']").count() == 5, "weekdays shortcut")
    pg.click(".modal button:text-is('Every day')"); check(pg.locator(".chips.days .chip[aria-pressed='true']").count() == 7, "every day shortcut")
    check("every day" in pg.inner_text(".cal-summary") and "3 TVs" in pg.inner_text(".cal-summary"), pg.inner_text(".cal-summary"))
    pg.fill("#wn", "Everything"); save(); settle()
    check(blocks().count() == 7, "an every-day block shows in all 7 columns: %d" % blocks().count())
    w = wins(); check(len(w) == 1 and w[0]["days"] == [0, 1, 2, 3, 4, 5, 6] and len(w[0]["targets"]) == 3, w)
    pg.screenshot(path=OUT + "/c02_everyday.png")

    # ---- overlap: two blocks at the same time sit side by side --------------
    drag(3, 16 * 60, 17 * 60); wait_dialog(); pg.fill("#ws", "13:30"); pg.fill("#we", "15:00"); pg.click(".modal .chip:text-is('All TVs')"); pg.click(".modal .chip:text-is('Gym')"); pg.fill("#wn", "Gym only"); save(); settle()
    thu = [bb for bb in (blocks().nth(i).bounding_box() for i in range(blocks().count())) if abs(bb["x"] - xmid(3)) < col(3).bounding_box()["width"] / 2]
    check(len(thu) == 2, "two blocks in Thursday: %d" % len(thu))
    a, c = sorted(thu, key=lambda r: r["x"])
    check(a["x"] + a["width"] <= c["x"] + 1, "overlapping blocks must not cover each other: %s %s" % (a, c))
    pg.screenshot(path=OUT + "/c03_overlap.png")

    # ---- moving and resizing ----------------------------------------------
    gym = lambda: pg.locator(".cal-block:has-text('Gym only')")
    bb = gym().bounding_box()
    pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + 20); pg.mouse.down()
    pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] - 3000, steps=8); pg.mouse.up(); settle()   # far above the top
    g = [x for x in wins() if x["name"] == "Gym only"][0]; check((g["start"], g["end"]) == ("00:00", "01:30"), "clamped at midnight: %s" % g)
    sc = pg.eval_on_selector(".cal-scroll", "e => e.scrollTop"); pg.eval_on_selector(".cal-scroll", "e => { e.scrollTop = 0 }")
    bb = gym().bounding_box()
    pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + 20); pg.mouse.down()
    pg.mouse.move(bb["x"] + bb["width"] / 2 + col(3).bounding_box()["width"] * 9, bb["y"] + 20, steps=8); pg.mouse.up(); settle()  # far right
    g = [x for x in wins() if x["name"] == "Gym only"][0]; check(g["days"] == [6], "clamped at Sunday: %s" % g)
    # 15-minute block: the middle drags, it doesn't resize
    pg.eval_on_selector(".cal-scroll", "e => { e.scrollTop = 6 * 44 }")
    drag(4, 9 * 60, 9 * 60 + 15); wait_dialog(); check((pg.input_value("#ws"), pg.input_value("#we")) == ("09:00", "09:15"), "15 minute block")
    pg.fill("#wn", "Tiny"); pg.click(".modal .chip:text-is('All TVs')"); pg.click(".modal .chip:text-is('Cafe')"); save(); settle()
    tiny = lambda: pg.locator(".cal-block:has-text('Tiny')")
    bb = tiny().bounding_box(); check(abs(bb["height"] - 11) < 2, "15 minutes is 11px high: %s" % bb["height"])
    pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2); pg.mouse.down(); pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2 + 44, steps=6); pg.mouse.up(); settle()
    t = [x for x in wins() if x["name"] == "Tiny"][0]; check((t["start"], t["end"]) == ("10:00", "10:15"), "tiny block moved, not resized: %s" % t)
    # resize can't go below 15 minutes or past midnight
    bb = tiny().bounding_box(); hx = bb["x"] + bb["width"] / 2
    pg.mouse.move(hx, bb["y"] + bb["height"] - 2); pg.mouse.down(); pg.mouse.move(hx, bb["y"] - 200, steps=8); pg.mouse.up(); settle()
    t = [x for x in wins() if x["name"] == "Tiny"][0]; check(t["end"] > t["start"] and t["start"] == "10:00" and t["end"] == "10:15", "minimum length kept: %s" % t)
    # a tiny wiggle is a click (opens the editor), not a move
    bb = tiny().bounding_box(); pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + 5); pg.mouse.down(); pg.mouse.move(bb["x"] + bb["width"] / 2 + 2, bb["y"] + 6); pg.mouse.up()
    wait_dialog(); check(pg.input_value("#wn") == "Tiny", "click opens the editor"); pg.keyboard.press("Escape")

    # ---- filter chips ------------------------------------------------------
    pg.click(".cal-filter .chip:text-is('Cafe')"); settle()
    check(blocks().count() == 8 and pg.locator(".cal-block:has-text('Gym only')").count() == 0, "filter by Cafe keeps 'Everything' (7) + Tiny")
    pg.click(".cal-filter .chip:text-is('Gym')"); settle(); check(pg.locator(".cal-block:has-text('Tiny')").count() == 0, "filter by Gym")
    pg.click(".cal-filter .chip:text-is('Gym')"); settle(); check(pg.locator(".cal-filter .chip[aria-pressed='true']").inner_text().endswith("All TVs"), "toggle filter off")
    pg.click(".cal-filter .chip:text-is('Cafe')"); settle(); pg.eval_on_selector(".cal-scroll", "e => { e.scrollTop = 8 * 44 }"); drag(5, 18 * 60, 19 * 60)
    wait_dialog(); check(pg.locator(".modal .chips:not(.days) .chip[aria-pressed='true']").count() == 1 and "Cafe" in pg.inner_text(".modal .chips:not(.days)"), "new block while filtered is for that TV")
    pg.keyboard.press("Escape"); pg.click(".cal-filter .chip:text-is('Cafe')"); settle()

    # ---- overnight, pause, scroll retention, keyboard --------------------------
    pg.eval_on_selector(".cal-scroll", "e => { e.scrollTop = 14 * 44 }")
    drag(4, 22 * 60, 23 * 60 + 45); wait_dialog(); pg.fill("#we", "05:00"); pg.fill("#wn", "Night")
    pg.click(".modal .chip:text-is('All TVs')"); pg.click(".modal .chip:text-is('Lobby')")
    check("the next day" in pg.inner_text(".cal-summary"), "summary mentions next day"); before = sc_top(); save(); settle()
    check(abs(sc_top() - before) < 2, "scroll position kept after saving: %s -> %s" % (before, sc_top()))
    night = pg.locator(".cal-block:has-text('Night')"); check(night.count() == 2, "overnight block drawn on both days")
    check(night.first.bounding_box()["height"] > 0 and night.last.bounding_box()["height"] > 0, "both halves have size")
    night.last.click(); wait_dialog(); check(pg.input_value("#wn") == "Night", "clicking the second half edits the same block")
    pg.click(".modal .switch"); save(); settle(); check(pg.locator(".cal-block.paused").count() == 2, "paused block is dimmed on both days")
    check([x for x in wins() if x["name"] == "Night"][0]["enabled"] is False, "paused saved")
    pg.eval_on_selector(".cal-scroll", "e => { e.scrollTop = 600 }")
    hy = pg.eval_on_selector(".cal-head", "e => e.getBoundingClientRect().top"); sy = pg.eval_on_selector(".cal-scroll", "e => e.getBoundingClientRect().top")
    check(abs(hy - sy) < 2, "day header stays pinned while scrolling")
    pg.eval_on_selector(".cal-scroll", "e => { e.scrollTop = 0 }")
    pg.locator(".cal-block:has-text('Tiny')").focus(); pg.keyboard.press("Enter"); wait_dialog(); check(pg.input_value("#wn") == "Tiny", "keyboard opens a block")
    pg.keyboard.press("Escape")
    pg.screenshot(path=OUT + "/c04_full.png")

    # ---- persistence, themes, phone ------------------------------------------
    pg.reload(); pg.click("nav >> text=Schedules"); pg.wait_for_selector(".cal-block"); settle()
    check(blocks().count() == 7 + 2 + 1 + 1, "blocks survive a reload: %d" % blocks().count())
    pg.click("nav >> text=Settings"); pg.click("button:text-is('Dark')"); pg.click("nav >> text=Schedules"); pg.wait_for_selector(".cal-block"); settle()
    pg.screenshot(path=OUT + "/c05_dark.png")
    pg.click("nav >> text=Settings"); pg.click("button:text-is('Light')"); pg.click("nav >> text=Schedules"); pg.wait_for_selector(".cal-block")
    pg.set_viewport_size({"width": 390, "height": 800}); settle()
    check(pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "no sideways scroll on a phone")
    pg.screenshot(path=OUT + "/c06_phone.png")
    # delete everything through the editor
    pg.set_viewport_size({"width": 1280, "height": 900}); settle()
    while blocks().count():
        pg.once("dialog", lambda d: d.accept()); blocks().first.click(); wait_dialog(); pg.click(".modal button:text-is('Delete')"); settle()
    check(wins() == [], "all deleted")
    bad = [e for e in errs if "favicon" not in e and "400 (Bad Request)" not in e]      # the two 400s are the validation checks above
    check(sum("400 (Bad Request)" in e for e in errs) == 2, "exactly the two expected validation 400s: %s" % errs)
    check(not bad, "browser errors: %s" % bad)
    b.close()
print("calendar e2e OK; screenshots in", OUT)
