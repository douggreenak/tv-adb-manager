class FakeAdb:
    """Same surface as tvmanager.adb.Adb, scripted per test."""
    def __init__(self):
        self.states = {}          # addr -> adb state
        self.responses = []       # list of (substring, output)
        self.calls = []
        self.png = b"\x89PNG\r\n\x1a\nfake"
        self.install_result = (0, "Success")

    def devices(self):
        return dict(self.states)

    def connect(self, addr):
        self.calls.append(("connect", addr))
        return "connected to " + addr

    def disconnect(self, addr):
        self.calls.append(("disconnect", addr))

    def shell(self, addr, cmd, timeout=15):
        self.calls.append(("shell", addr, cmd))
        for sub, out in self.responses:
            if sub in cmd:
                return 0, out() if callable(out) else out
        return 0, ""

    def screencap(self, addr, timeout=20):
        return self.png

    def install(self, addr, path, timeout=600):
        self.calls.append(("install", addr, path))
        return self.install_result

    def screenrecord_argv(self, addr, size, bitrate):
        self.calls.append(("screenrecord", addr, size))
        if getattr(self, "live_fail", False) or (size and getattr(self, "live_fail_sized", False)):
            return ["sh", "-c", "echo 'ERROR: no encoder' >&2; exit 1"]
        mode = getattr(self, "live_mode", "continuous")
        enc = "ffmpeg -nostdin -loglevel error -f lavfi -i testsrc2=size=%s:rate=15 -frames:v %%d -c:v libx264 -preset ultrafast -tune zerolatency -g 15 -pix_fmt yuv420p -f h264 -" % (size or "320x180")
        if mode == "static":       # what a static TV screen does: one frame, then silence
            return ["sh", "-c", (enc % 1) + "; sleep 20"]
        if mode == "headers":      # what the TCL does on HDMI: parameter sets only, never a picture
            return ["sh", "-c", (enc % 3) + " 2>/dev/null | head -c 70; sleep 20"]
        return ["ffmpeg", "-nostdin", "-loglevel", "error", "-re", "-f", "lavfi", "-i", "testsrc2=size=%s:rate=15" % (size or "320x180"),
                "-t", "8", "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-g", "15", "-pix_fmt", "yuv420p", "-f", "h264", "-"]

    def reboot(self, addr):
        self.calls.append(("reboot", addr))
        return 0, ""

    def shells(self, addr=None):
        return [c[2] for c in self.calls if c[0] == "shell" and (addr is None or c[1] == addr)]
