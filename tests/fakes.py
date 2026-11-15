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

    def reboot(self, addr):
        self.calls.append(("reboot", addr))
        return 0, ""

    def shells(self, addr=None):
        return [c[2] for c in self.calls if c[0] == "shell" and (addr is None or c[1] == addr)]
