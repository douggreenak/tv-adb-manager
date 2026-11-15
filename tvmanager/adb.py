"""Thin wrapper around the `adb` binary. Everything talks to devices through this class,
so tests can swap in a fake with the same methods."""
import subprocess


class Adb:
    def __init__(self, binary="adb"):
        self.binary = binary

    def _run(self, args, timeout=15, text=True, stdin=None):
        try:
            r = subprocess.run([self.binary] + list(args), capture_output=True, text=text,
                               timeout=timeout, input=stdin)
            return r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired:
            return 124, "" if text else b"", "timeout"
        except FileNotFoundError:
            return 127, "" if text else b"", "adb binary not found"

    def devices(self):
        """Return {address: state} where state is device|offline|unauthorized|..."""
        rc, out, _ = self._run(["devices"], timeout=10)
        res = {}
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                res[parts[0]] = parts[1]
        return res

    def connect(self, addr):
        rc, out, err = self._run(["connect", addr], timeout=12)
        return (out + err).strip()

    def disconnect(self, addr):
        self._run(["disconnect", addr], timeout=8)

    def shell(self, addr, cmd, timeout=15):
        """Run a shell command. Returns (returncode, stdout)."""
        rc, out, err = self._run(["-s", addr, "shell", cmd], timeout=timeout)
        return rc, out

    def screencap(self, addr, timeout=20):
        rc, out, _ = self._run(["-s", addr, "exec-out", "screencap", "-p"], timeout=timeout, text=False)
        return out if rc == 0 and out[:4] == b"\x89PNG" else None

    def screenrecord_argv(self, addr, size, bitrate):
        """argv that streams the TV's screen as raw H.264 on stdout (screenrecord stops itself after 3 minutes)."""
        return [self.binary, "-s", addr, "exec-out", "screenrecord", "--output-format=h264", "--size", size,
                "--bit-rate", str(bitrate), "--time-limit", "180", "-"]

    def install(self, addr, path, timeout=600):
        rc, out, err = self._run(["-s", addr, "install", "-r", path], timeout=timeout)
        return rc, (out + err).strip()

    def reboot(self, addr):
        rc, out, err = self._run(["-s", addr, "reboot"], timeout=15)
        return rc, (out + err).strip()
