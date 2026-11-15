"""Minimal systemd notification (sd_notify) and watchdog, stdlib only. All of it is a no-op outside systemd."""
import http.client
import os
import socket
import threading
import time


def notify(message):
    """Send e.g. "READY=1" or "WATCHDOG=1" to systemd. Returns False when not running under systemd."""
    path = os.environ.get("NOTIFY_SOCKET")
    if not path:
        return False
    if path.startswith("@"):                      # abstract socket
        path = "\0" + path[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(path)
            s.sendall(message.encode())
        return True
    except OSError:
        return False


def healthy(app, host, port, max_tick_age=None, timeout=5):
    """True if the poller is still ticking and the HTTP server answers. A hung process fails this."""
    max_tick_age = max_tick_age or max(30.0, app.monitor.poll * 10)
    tick = getattr(app.monitor, "last_tick", None)
    if tick is None or time.time() - tick > max_tick_age:
        return False
    try:
        c = http.client.HTTPConnection("127.0.0.1" if host in ("0.0.0.0", "") else host, port, timeout=timeout)
        c.request("GET", "/api/session")
        ok = c.getresponse().status == 200
        c.close()
        return ok
    except (OSError, http.client.HTTPException):
        return False


def start_watchdog(app, host, port, log=print):
    """If systemd set WatchdogSec, ping it at half that interval, but only while healthy()."""
    usec = int(os.environ.get("WATCHDOG_USEC", "0") or 0)
    if not usec:
        return None
    every = usec / 2_000_000.0

    def loop():
        started, was_ok = time.time(), True
        while True:
            ok = healthy(app, host, port)
            if not ok and app.monitor.last_tick is None and time.time() - started < every * 2:
                ok = True                       # still starting up: the poller has not had its first tick yet
            if ok:
                notify("WATCHDOG=1")
                if not was_ok:
                    log("watchdog: healthy again")
            elif was_ok:
                log("watchdog: unhealthy, not pinging systemd (it will restart us)")
            was_ok = ok
            time.sleep(every)

    t = threading.Thread(target=loop, daemon=True, name="watchdog")
    t.start()
    return t
