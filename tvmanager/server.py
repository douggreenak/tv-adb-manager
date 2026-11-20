"""HTTP API + static web UI (stdlib only)."""
import json
import mimetypes
import os
import re
import tempfile
import threading
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import __version__
from . import parsers as P
from .adb import Adb
from .auth import Auth
from . import live as livemod
from . import wol
from .keepalive import KeepAlive, clamp as clamp_keepalive
from .monitor import Monitor, launch_input
from .scheduler import Scheduler, validate as validate_schedule
from .store import EventLog, Store

MAX_JSON = 1 << 20
MAX_APK = 600 << 20
COOKIE = "tvm_session"
BASE_KEYS = {"home": "KEYCODE_HOME", "back": "KEYCODE_BACK"}


class ApiError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status, self.msg = status, msg


class App:
    def __init__(self, data_dir, web_dir, adb=None, env_password=None, poll=3.0, start_threads=True):
        self.data_dir, self.web_dir = data_dir, web_dir
        os.makedirs(data_dir, exist_ok=True)
        self.adb = adb or Adb()
        self.store = Store(data_dir)
        self.events = EventLog(data_dir)
        self.auth = Auth(data_dir, env_password, log=lambda m: print(m, flush=True))
        self.monitor = Monitor(self.adb, self.store, self.events, poll=poll)
        self.scheduler = Scheduler(self.store, self.events, self.run_action)
        self.keepalive = KeepAlive(self.store, self.monitor, self.events)
        self.live = livemod.LiveManager()
        self.started = time.time()
        if start_threads:
            self.monitor.start()
            self.scheduler.start()
            self.keepalive.start()

    # ---- views ---------------------------------------------------------
    def device_view(self, d):
        st = self.monitor.snapshot(d["id"]) or {}
        labels = st.get("labels") or {}
        inp = st.get("input")
        last = (d.get("restore") or {}).get("last")
        return {
            "id": d["id"], "name": d["name"], "addr": d["addr"], "group": d.get("group", ""),
            "auto_name": d.get("auto_name", False), "tv_name": st.get("tv_name"),
            "restore": {"enabled": (d.get("restore") or {}).get("enabled", True), "last": last,
                        "last_name": P.short_input_name(last, labels) if last else None},
            "keep_on": d.get("keep_on", True),
            "network": (self.keepalive.view(d["id"]) or {}).get("up"),
            "mac": d.get("mac") or st.get("mac") or "", "mac_auto": d.get("mac_auto", True),
            "status": st.get("status", "unknown"), "awake": st.get("awake"),
            "input": inp, "input_name": P.short_input_name(inp, labels) if inp else None,
            "top": st.get("top"), "manufacturer": st.get("manufacturer"), "model": st.get("model"),
            "android": st.get("android"), "last_seen": st.get("last_seen"),
        }

    def require_device(self, dev_id):
        d = self.store.device(dev_id)
        if not d:
            raise ApiError(404, "unknown device")
        return d

    # ---- actions shared by API, bulk, scheduler --------------------------
    def key(self, dev, keycode):
        if not P.SAFE_KEY.match(str(keycode)):
            raise ApiError(400, "invalid key")
        rc, out = self.adb.shell(dev["addr"], "input keyevent %s" % keycode)
        return rc == 0, out.strip()

    def wake_on_lan(self, dev):
        st = self.monitor.snapshot(dev["id"]) or {}
        mac = dev.get("mac") or st.get("mac")
        if not mac:
            return False, "No MAC address known yet. It is learned while the TV is on, or enter it in Settings."
        n = wol.send(mac, dev["addr"].split(":")[0])
        if not n:
            return False, "Could not send the Wake-on-LAN packet from this server."
        return True, "Sent Wake-on-LAN to %s. A TV that is fully off may not respond; standby usually does." % mac

    def run_action(self, dev, action, args=None):
        args = args or {}
        addr = dev["addr"]
        if action == "wol":
            return self.wake_on_lan(dev)
        if action == "wake":
            st = self.monitor.snapshot(dev["id"]) or {}
            if st.get("status") in ("offline", "unknown") and (dev.get("mac") or st.get("mac")):
                return self.wake_on_lan(dev)          # fully off: ADB can't reach it, so use the network
            return self.key(dev, "KEYCODE_WAKEUP")
        if action == "sleep":
            return self.key(dev, "KEYCODE_SLEEP")
        if action in BASE_KEYS:
            return self.key(dev, BASE_KEYS[action])
        if action == "reboot":
            rc, out = self.adb.reboot(addr)
            return rc == 0, out
        if action == "input":
            iid = args.get("input") or ""
            if not P.SAFE_INPUT.match(iid):
                return False, "invalid input id"
            self.key(dev, "KEYCODE_WAKEUP")
            return launch_input(self.adb, addr, iid)
        if action == "restore":
            return self.monitor.restore_now(dev)
        if action == "connect":
            out = self.adb.connect(addr)
            return "connected" in out, out
        return False, "unknown action"

    # ---- lifecycle -----------------------------------------------------
    def shutdown(self):
        self.monitor.stop()
        self.scheduler.stop()
        self.keepalive.stop()


class Handler(BaseHTTPRequestHandler):
    server_version = "TVManager/" + __version__
    protocol_version = "HTTP/1.1"
    app = None  # set by make_server

    def log_message(self, fmt, *a):
        pass

    # ---- plumbing --------------------------------------------------------
    def _send(self, status, body=b"", ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _token(self):
        c = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        return c[COOKIE].value if COOKIE in c else None

    def _json_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_JSON:
            raise ApiError(413, "body too large")
        if n == 0:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except ValueError:
            raise ApiError(400, "invalid JSON")

    def _dispatch(self):
        url = urlsplit(self.path)
        path, query = url.path, parse_qs(url.query)
        try:
            if not path.startswith("/api/"):
                return self._static(path)
            if self.command != "GET" and self.headers.get("X-Requested-With") != "tvm":
                raise ApiError(403, "missing X-Requested-With header")
            route = None
            for method, rx, fn, public in ROUTES:
                m = rx.match(path)
                if m and method == self.command:
                    route = (fn, m, public)
                    break
            if not route:
                raise ApiError(404, "not found")
            fn, m, public = route
            if not public and not self.app.auth.valid(self._token()):
                raise ApiError(401, "login required")
            return fn(self, m, query)
        except ApiError as e:
            if self.headers.get("Content-Length") and self.command in ("POST", "PUT") and "install" in path:
                self.close_connection = True
            return self._send(e.status, {"error": e.msg})
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:
            self.app.events.add("-", "server error on %s: %r" % (path, e), "error")
            return self._send(500, {"error": "internal error"})

    do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = _dispatch

    def _static(self, path):
        if self.command not in ("GET", "HEAD"):
            raise ApiError(405, "method not allowed")
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        full = os.path.realpath(os.path.join(self.app.web_dir, rel))
        root = os.path.realpath(self.app.web_dir)
        if not (full == root or full.startswith(root + os.sep)) or not os.path.isfile(full):
            raise ApiError(404, "not found")
        with open(full, "rb") as f:
            data = f.read()
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(200, data, ctype)


# ---- route handlers ---------------------------------------------------------
ROUTES = []


def route(method, pattern, public=False):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn, public))
        return fn
    return deco


@route("GET", "/api/session", public=True)
def r_session(h, m, q):
    h._send(200, {"authenticated": h.app.auth.valid(h._token()), "version": __version__})


@route("POST", "/api/login", public=True)
def r_login(h, m, q):
    body = h._json_body()
    ip = h.client_address[0]
    if h.app.auth.throttled(ip):
        raise ApiError(429, "too many attempts, try again in a few minutes")
    token = h.app.auth.login(ip, str(body.get("password", "")))
    if not token:
        raise ApiError(401, "wrong password")
    h._send(200, {"ok": True}, extra={
        "Set-Cookie": "%s=%s; HttpOnly; SameSite=Strict; Path=/; Max-Age=%d" % (COOKIE, token, 7 * 24 * 3600)})


@route("POST", "/api/logout")
def r_logout(h, m, q):
    h.app.auth.logout(h._token())
    h._send(200, {"ok": True}, extra={"Set-Cookie": "%s=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0" % COOKIE})


@route("POST", "/api/password")
def r_password(h, m, q):
    body = h._json_body()
    if not h.app.auth.check(str(body.get("current", ""))):
        raise ApiError(403, "current password is wrong")
    h.app.auth.set_password(str(body.get("new", "")))
    token = h.app.auth.login(h.client_address[0], str(body.get("new")))
    h._send(200, {"ok": True}, extra={
        "Set-Cookie": "%s=%s; HttpOnly; SameSite=Strict; Path=/; Max-Age=%d" % (COOKIE, token, 7 * 24 * 3600)})


@route("GET", "/api/settings")
def r_settings(h, m, q):
    h._send(200, {"keepalive": clamp_keepalive(h.app.store.settings().get("keepalive", 5))})


@route("PUT", "/api/settings")
def r_put_settings(h, m, q):
    b = h._json_body()
    if "keepalive" in b:
        try:
            v = clamp_keepalive(b["keepalive"])
        except (TypeError, ValueError):
            raise ApiError(400, "keepalive must be a number of seconds (0 turns it off)")
        h.app.store.set_settings(keepalive=v)
        h.app.events.add("-", "network keepalive %s" % ("every %d s" % v if v else "turned off"))
    h._send(200, {"keepalive": clamp_keepalive(h.app.store.settings().get("keepalive", 5))})


@route("GET", "/api/devices")
def r_devices(h, m, q):
    a = h.app
    h._send(200, {"devices": [a.device_view(d) for d in a.store.devices()],
                  "groups": sorted({d.get("group", "") for d in a.store.devices() if d.get("group")})})


@route("POST", "/api/devices")
def r_add_device(h, m, q):
    b = h._json_body()
    d = h.app.store.add_device(b.get("name"), b.get("addr"), b.get("group"))
    h.app.events.add(d["name"], "device added (%s)" % d["addr"])
    h._send(201, h.app.device_view(d))


@route("PUT", r"/api/devices/(\w+)")
def r_update_device(h, m, q):
    a = h.app
    d = a.require_device(m.group(1))
    b = h._json_body()
    fields = {k: b[k] for k in ("name", "addr", "group", "auto_name", "mac") if k in b}
    if "restore" in b and isinstance(b["restore"], dict):
        r = dict(d.get("restore") or {})
        if "enabled" in b["restore"]:
            r["enabled"] = bool(b["restore"]["enabled"])
        if "last" in b["restore"]:
            v = b["restore"]["last"]
            if v and not P.SAFE_INPUT.match(v):
                raise ApiError(400, "invalid input id")
            r["last"] = v or None
        fields["restore"] = r
    if "keep_on" in b:
        want = bool(b["keep_on"])
        if want != d.get("keep_on", True):
            fields["keep_on"] = want
            if not want:
                ok, out = a.monitor.revert_keep_on(d)
                if not ok:
                    raise ApiError(502, "Could not restore the TV's timers: " + out)
    updated = a.store.update_device(d["id"], **fields)
    if fields.get("keep_on"):
        a.monitor.keep_on(a.store.device(d["id"]), a.monitor._st(d["id"]), force=True)
    if fields.get("auto_name"):
        a.monitor.apply_auto_name(d["id"])          # take the TV's name straight away if we already know it
        updated = a.store.device(d["id"])
    h._send(200, a.device_view(updated))


@route("DELETE", r"/api/devices/(\w+)")
def r_delete_device(h, m, q):
    d = h.app.require_device(m.group(1))
    h.app.store.delete_device(d["id"])
    h.app.adb.disconnect(d["addr"])
    h.app.events.add(d["name"], "device removed")
    h._send(200, {"ok": True})


@route("POST", r"/api/devices/(\w+)/action")
def r_action(h, m, q):
    a = h.app
    d = a.require_device(m.group(1))
    b = h._json_body()
    action = b.get("action")
    if action == "key":
        ok, out = a.key(d, b.get("key"))
    else:
        ok, out = a.run_action(d, action, b)
    if action in ("reboot", "sleep", "wake", "wol", "input", "restore"):
        a.events.add(d["name"], "%s%s" % (action, "" if ok else " failed: %s" % out), "info" if ok else "error")
    h._send(200, {"ok": ok, "output": out})


@route("POST", "/api/bulk")
def r_bulk(h, m, q):
    a = h.app
    b = h._json_body()
    action, ids = b.get("action"), b.get("ids") or []
    if action == "key" and not P.SAFE_KEY.match(str(b.get("key"))):
        raise ApiError(400, "invalid key")
    results = {}
    for i in ids:
        d = a.store.device(str(i))
        if not d:
            results[i] = {"ok": False, "output": "unknown device"}
            continue
        ok, out = a.key(d, b["key"]) if action == "key" else a.run_action(d, action, b)
        results[i] = {"ok": ok, "output": out}
        if action in ("reboot", "sleep", "wake", "wol", "input", "restore"):
            a.events.add(d["name"], "bulk %s%s" % (action, "" if ok else " failed: %s" % out), "info" if ok else "error")
    h._send(200, {"results": results})


@route("GET", r"/api/devices/(\w+)/info")
def r_info(h, m, q):
    a = h.app
    d = a.require_device(m.group(1))
    sh = lambda c, t=15: a.adb.shell(d["addr"], c, t)[1]
    props = P.parse_props(sh("getprop"))
    keep = ["ro.product.manufacturer", "ro.product.model", "ro.product.device", "ro.build.version.release",
            "ro.build.version.sdk", "ro.build.version.security_patch", "ro.build.fingerprint", "ro.serialno",
            "ro.boot.hardware", "persist.sys.timezone"]
    df = P.parse_df(sh("df -k /data"))
    mem = P.parse_meminfo(sh("cat /proc/meminfo"))
    up = sh("cat /proc/uptime").split()
    ip = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", sh("ip -f inet addr show wlan0; ip -f inet addr show eth0"))
    h._send(200, {
        "props": {k: props.get(k) for k in keep if props.get(k)},
        "storage_kb": {"total": df[0], "used": df[1]} if df else None,
        "memory_kb": {"total": mem.get("MemTotal"), "available": mem.get("MemAvailable")} if mem else None,
        "uptime_s": int(float(up[0])) if up else None,
        "ip": ip.group(1) if ip else None,
    })


@route("GET", r"/api/devices/(\w+)/inputs")
def r_inputs(h, m, q):
    a = h.app
    d = a.require_device(m.group(1))
    st = a.monitor.snapshot(d["id"]) or {}
    labels = st.get("labels") or {}
    out = a.adb.shell(d["addr"], "dumpsys tv_input", 20)[1]
    items = []
    for i in P.parse_inputs(out):
        items.append({"id": i["id"], "state": i["state"], "name": P.short_input_name(i["id"], labels),
                      "passthrough": P.is_passthrough(i["id"]), "active": i["id"] == st.get("input")})
    h._send(200, {"inputs": items})


@route("GET", r"/api/devices/(\w+)/packages")
def r_packages(h, m, q):
    a = h.app
    d = a.require_device(m.group(1))
    flt = (q.get("filter") or ["user"])[0]
    sh = lambda c: P.parse_packages(a.adb.shell(d["addr"], c, 30)[1])
    disabled = set(sh("pm list packages -d"))
    flag = {"user": "-3", "system": "-s"}.get(flt, "")
    pkgs = disabled if flt == "disabled" else set(sh("pm list packages %s" % flag))
    h._send(200, {"packages": [{"name": p, "disabled": p in disabled} for p in sorted(pkgs)]})


@route("POST", r"/api/devices/(\w+)/packages/([\w.]+)")
def r_package_action(h, m, q):
    a = h.app
    d = a.require_device(m.group(1))
    pkg = m.group(2)
    if not P.SAFE_PKG.match(pkg):
        raise ApiError(400, "invalid package name")
    action = h._json_body().get("action")
    cmds = {
        "enable": "pm enable --user 0 %s" % pkg,
        "disable": "pm disable-user --user 0 %s" % pkg,
        "uninstall": "pm uninstall --user 0 %s" % pkg,
        "stop": "am force-stop %s" % pkg,
        "clear": "pm clear %s" % pkg,
        "launch": "monkey -p %s -c android.intent.category.LEANBACK_LAUNCHER 1 2>&1 | grep -q 'Events injected: 1' "
                  "|| monkey -p %s -c android.intent.category.LAUNCHER 1" % (pkg, pkg),
    }
    if action not in cmds:
        raise ApiError(400, "unknown action")
    rc, out = a.adb.shell(d["addr"], cmds[action], 30)
    ok = rc == 0 and "Error" not in out and "Failure" not in out
    a.events.add(d["name"], "%s %s%s" % (action, pkg, "" if ok else " failed"), "info" if ok else "error")
    h._send(200, {"ok": ok, "output": out.strip()})


@route("POST", r"/api/devices/(\w+)/install")
def r_install(h, m, q):
    a = h.app
    d = a.require_device(m.group(1))
    n = int(h.headers.get("Content-Length") or 0)
    if n <= 0 or n > MAX_APK:
        raise ApiError(413, "APK missing or too large")
    updir = os.path.join(a.data_dir, "uploads")
    os.makedirs(updir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".apk", dir=updir)
    try:
        with os.fdopen(fd, "wb") as f:
            left = n
            while left:
                chunk = h.rfile.read(min(1 << 20, left))
                if not chunk:
                    raise ApiError(400, "upload interrupted")
                f.write(chunk)
                left -= len(chunk)
        name = os.path.basename((q.get("name") or ["app.apk"])[0])[:80]
        rc, out = a.adb.install(d["addr"], tmp)
        ok = rc == 0 and "Success" in out
        a.events.add(d["name"], "install %s %s" % (name, "ok" if ok else "failed: %s" % out[-120:]), "info" if ok else "error")
        h._send(200, {"ok": ok, "output": out})
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


@route("GET", r"/api/devices/(\w+)/screenshot")
def r_screenshot(h, m, q):
    d = h.app.require_device(m.group(1))
    png = h.app.adb.screencap(d["addr"])
    if not png:
        raise ApiError(502, "screenshot failed (device asleep or protected content)")
    h._send(200, png, "image/png")


@route("GET", r"/api/devices/(\w+)/live")
def r_live(h, m, q):
    """Live view: multipart/x-mixed-replace stream of JPEG frames (also works directly in an <img>)."""
    a = h.app
    d = a.require_device(m.group(1))
    ff = livemod.ffmpeg_path()
    if not ff:
        raise ApiError(501, "Live view needs ffmpeg on the server (sudo apt install ffmpeg)")
    st = a.monitor.snapshot(d["id"]) or {}
    if st.get("status") not in ("online", "asleep"):
        raise ApiError(409, "The TV is not reachable")
    if st.get("status") == "asleep":
        raise ApiError(409, "The TV is in standby, so there is no picture to show. Wake it first.")
    name = (q.get("quality") or ["medium"])[0]
    preset = livemod.PRESETS.get(name)
    if not preset:
        raise ApiError(400, "quality must be low, medium or high")
    sess = frame = None
    err = ""
    got_bytes = 0
    for size in (preset["size"], None):      # preset first, then the TV's native size (some TVs reject odd sizes)
        try:
            sess = a.live.open(d["id"], a.adb.screenrecord_argv(d["addr"], size, preset["bitrate"]), preset, ff)
        except livemod.LiveError as e:
            raise ApiError(429, str(e))
        seq, frame = sess.next_frame(0, timeout=8)
        if frame is not None:
            break
        err = sess.error_text() or err
        got_bytes = max(got_bytes, sess.bytes_in)
        a.live.release(d["id"], sess)
    if frame is None:
        if not err and got_bytes:
            err = "The TV sent video headers but no picture. It is probably showing an HDMI input, which can't be captured."
        a.events.add(d["name"], "live view failed: %s" % (err or "the TV produced no video"), "error")
        raise ApiError(502, "No video from the TV. " + (err if err else
                       "It sent nothing for 8 seconds. It may be going to standby or busy, or it may not allow screen capture."))
    a.events.add(d["name"], "live view started (%s)" % name)
    started = time.time()
    h.close_connection = True
    h.send_response(200)
    # fetch() readers ask for raw=1: Safari/WebKit cannot fetch multipart/x-mixed-replace ("Load failed"), but an
    # <img> needs exactly that content type, so the two callers get different headers for the same frames.
    raw = (q.get("raw") or [""])[0] == "1"
    h.send_header("Content-Type", "application/octet-stream" if raw else "multipart/x-mixed-replace; boundary=frame")
    h.send_header("Cache-Control", "no-store")
    h.send_header("X-Content-Type-Options", "nosniff")
    h.send_header("Connection", "close")
    h.end_headers()
    try:
        while frame is not None:
            h.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(frame) + frame + b"\r\n")
            h.wfile.flush()
            seq, frame = sess.next_frame(seq, timeout=4, repeat=True)     # repeat = keep-alive while the screen is static
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        a.live.release(d["id"], sess)
        a.events.add(d["name"], "live view ended after %ds" % (time.time() - started))


@route("POST", r"/api/devices/(\w+)/shell")
def r_shell(h, m, q):
    a = h.app
    d = a.require_device(m.group(1))
    cmd = str(h._json_body().get("cmd", "")).strip()
    if not cmd or len(cmd) > 2000:
        raise ApiError(400, "command missing or too long")
    rc, out = a.adb.shell(d["addr"], cmd, 30)
    a.events.add(d["name"], "shell: %s" % cmd[:200])
    h._send(200, {"rc": rc, "output": out[-60000:]})


@route("GET", "/api/events")
def r_events(h, m, q):
    h._send(200, {"events": h.app.events.list(300)})


@route("GET", "/api/schedules")
def r_schedules(h, m, q):
    h._send(200, {"schedules": h.app.store.schedules()})


@route("POST", "/api/schedules")
def r_schedule_add(h, m, q):
    s = validate_schedule(h._json_body())
    h._send(201, h.app.store.save_schedule(s))


@route("PUT", r"/api/schedules/(\w+)")
def r_schedule_put(h, m, q):
    sid = m.group(1)
    if not any(s["id"] == sid for s in h.app.store.schedules()):
        raise ApiError(404, "unknown schedule")
    h._send(200, h.app.store.save_schedule(validate_schedule(h._json_body(), sid)))


@route("DELETE", r"/api/schedules/(\w+)")
def r_schedule_del(h, m, q):
    if not h.app.store.delete_schedule(m.group(1)):
        raise ApiError(404, "unknown schedule")
    h._send(200, {"ok": True})


def make_server(app, host="0.0.0.0", port=8420):
    handler = type("BoundHandler", (Handler,), {"app": app})
    srv = ThreadingHTTPServer((host, port), handler)
    srv.daemon_threads = True
    return srv
