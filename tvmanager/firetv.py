"""Fire TV control without ADB, through the local API the Fire TV phone remote app uses.

The TV serves HTTPS on port 8080 once its remote service has been started with a request to port 8009.
Pairing shows a 4-digit PIN on the TV; verifying it returns a token that is stored with the device.
"""
import json
import re
import ssl
import time
import urllib.error
import urllib.request

PORT = 8080
WAKE_PORT = 8009
API_KEY = "0987654321"            # the fixed key the Fire TV remote apps send
SAFE_PIN = re.compile(r"^\d{4}$")

# Manager key names (the ADB key names the Remote tab uses) -> Fire TV actions.
KEYS = {
    "KEYCODE_HOME": "home", "KEYCODE_BACK": "back", "KEYCODE_DPAD_UP": "dpad_up", "KEYCODE_DPAD_DOWN": "dpad_down",
    "KEYCODE_DPAD_LEFT": "dpad_left", "KEYCODE_DPAD_RIGHT": "dpad_right", "KEYCODE_DPAD_CENTER": "select",
    "KEYCODE_ENTER": "select", "KEYCODE_SLEEP": "sleep", "KEYCODE_WAKEUP": "wakeup",
}
MEDIA = {"KEYCODE_MEDIA_PLAY_PAUSE": "play", "KEYCODE_MEDIA_PLAY": "play", "KEYCODE_MEDIA_PAUSE": "play"}

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE        # the TV uses a self-signed certificate


def _https(method, url, headers, body=None, timeout=8):
    """Returns (status, parsed JSON or {})."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            raw, status = r.read(), r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    try:
        return status, json.loads(raw or b"{}")
    except ValueError:
        return status, {}


def _plain_post(url, timeout=5):
    req = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


class FireTV:
    def __init__(self, https=_https, plain_post=_plain_post):
        self.https, self.plain_post = https, plain_post

    def _hdr(self, token=None):
        h = {"X-Api-Key": API_KEY, "Content-Type": "application/json; charset=utf-8", "User-Agent": "okhttp/4.10.0"}
        if token:
            h["X-Client-Token"] = token
        return h

    def start_service(self, host):
        """The remote service only listens on 8080 after this request."""
        try:
            self.plain_post("http://%s:%d/apps/FireTVRemote" % (host, WAKE_PORT))
            return True
        except OSError:
            return False

    def _call(self, host, method, path, token=None, body=None, sleep=time.sleep):
        """The TV's remote service stops itself when idle: on a refused connection start it, wait, and retry."""
        url = "https://%s:%d%s" % (host, PORT, path)
        for attempt in range(4):
            try:
                return self.https(method, url, self._hdr(token), body)
            except OSError:
                if attempt == 3:
                    break
                self.start_service(host)
                sleep(1.0 + attempt)
        return 0, {"description": "The Fire TV did not answer. Check that it is on the network."}

    def show_pin(self, host, friendly="TV Manager"):
        st, body = self._call(host, "POST", "/v1/FireTV/pin/display", body={"friendlyName": friendly})
        return st == 200, body.get("description", "")

    def verify_pin(self, host, pin):
        """Returns (ok, token or message)."""
        if not SAFE_PIN.match(str(pin)):
            return False, "The PIN is 4 digits"
        st, body = self._call(host, "POST", "/v1/FireTV/pin/verify", body={"pin": str(pin)})
        if st == 200 and body.get("description"):
            return True, body["description"]
        return False, body.get("description") or "The TV did not accept that PIN"

    def press(self, host, token, key):
        """Send an ADB-style key name. Returns (ok, message)."""
        if not token:
            return False, "This Fire TV is not paired yet"
        if key in KEYS:
            path = "/v1/FireTV?action=" + KEYS[key]
        elif key in MEDIA:
            path = "/v1/media?action=" + MEDIA[key]
        else:
            return False, "That key is not available on a Fire TV"
        st, body = self._call(host, "POST", path, token)
        if st == 200:
            return True, body.get("description", "OK")
        if st in (401, 403):
            return False, "The pairing was rejected. Pair this Fire TV again in Settings."
        return False, body.get("description") or "The Fire TV did not answer (HTTP %d)" % st
