"""Live screen view: `adb screenrecord` (H.264) -> ffmpeg (JPEG frames) -> HTTP multipart stream.

Why transcode on the server: browsers can only decode H.264 over HTTPS (WebCodecs) or via heavy JS
decoders, while JPEG frames work everywhere over plain HTTP. Only the latest frame is kept, so a slow
client drops frames instead of building up lag.
"""
import shutil
import subprocess
import threading
import time
from collections import deque

PRESETS = {
    "low":    {"size": "854x480",   "fps": 6,  "q": 9, "bitrate": 2000000},
    "medium": {"size": "1280x720",  "fps": 10, "q": 6, "bitrate": 4000000},
    "high":   {"size": "1920x1080", "fps": 15, "q": 4, "bitrate": 8000000},
}
MAX_SECONDS = 30 * 60      # a forgotten tab must not stream forever
MAX_SESSIONS = 4
BOUNDARY = b"frame"


def ffmpeg_path():
    return shutil.which("ffmpeg")


class LiveError(Exception):
    pass


class LiveSession:
    def __init__(self, source_argv, preset, ffmpeg_bin, max_seconds=MAX_SECONDS):
        self.source_argv, self.preset, self.ffmpeg_bin, self.max_seconds = source_argv, preset, ffmpeg_bin, max_seconds
        self.stopped = threading.Event()
        self.cond = threading.Condition()
        self.seq, self.frame = 0, None
        self.errors = {"tv": deque(maxlen=12), "ffmpeg": deque(maxlen=12)}
        self.started = time.time()
        self.ff = None
        self._src = None

    # ---- lifecycle -----------------------------------------------------
    def start(self):
        w = self.preset["size"].split("x")[0]
        argv = [self.ffmpeg_bin, "-nostdin", "-hide_banner", "-loglevel", "error",
                "-fflags", "nobuffer", "-flags", "low_delay", "-probesize", "32", "-analyzeduration", "0",
                "-use_wallclock_as_timestamps", "1", "-f", "h264", "-i", "pipe:0",
                "-vf", "fps=%d,scale=%s:-2" % (self.preset["fps"], w), "-pix_fmt", "yuvj420p",
                "-q:v", str(self.preset["q"]), "-f", "mpjpeg", "-boundary_tag", BOUNDARY.decode(), "pipe:1"]
        self.ff = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for target in (self._feed, self._read_frames):
            threading.Thread(target=target, daemon=True).start()
        threading.Thread(target=self._drain, args=(self.ff.stderr, "ffmpeg"), daemon=True).start()

    def stop(self):
        self.stopped.set()
        for p in (self._src, self.ff):
            try:
                if p and p.poll() is None:
                    p.kill()
            except OSError:
                pass
        with self.cond:
            self.cond.notify_all()

    def _drain(self, stream, who):
        try:
            for line in iter(stream.readline, b""):
                t = line.decode("utf-8", "replace").strip()
                if t:
                    self.errors[who].append(t)
        except (OSError, ValueError):
            pass

    # ---- TV side: keep feeding H.264; screenrecord stops after 3 minutes, so restart it ----
    def _feed(self):
        try:
            while not self.stopped.is_set() and time.time() - self.started < self.max_seconds:
                src = self._src = subprocess.Popen(self.source_argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                threading.Thread(target=self._drain, args=(src.stderr, "tv"), daemon=True).start()
                t0, n = time.time(), 0
                while True:
                    data = src.stdout.read1(65536)
                    if not data:
                        break
                    n += len(data)
                    self.ff.stdin.write(data)
                    self.ff.stdin.flush()
                src.wait()
                if n == 0 or time.time() - t0 < 2:   # failed straight away: do not loop
                    break
        except (BrokenPipeError, OSError, ValueError):
            pass
        finally:
            try:
                self.ff.stdin.close()
            except OSError:
                pass

    # ---- ffmpeg side: split the mpjpeg stream into frames, keep only the newest ----
    def _read_frames(self):
        buf = bytearray()
        try:
            while True:
                chunk = self.ff.stdout.read1(65536)
                if not chunk:
                    break
                buf += chunk
                while True:
                    he = buf.find(b"\r\n\r\n")
                    if he < 0:
                        break
                    head = bytes(buf[:he]).lower()
                    i = head.find(b"content-length:")
                    if i < 0:
                        del buf[:he + 4]
                        continue
                    n = int(head[i + 15:].split(b"\r\n")[0].strip() or 0)
                    if len(buf) < he + 4 + n:
                        break
                    jpeg = bytes(buf[he + 4:he + 4 + n])
                    del buf[:he + 4 + n]
                    with self.cond:
                        self.seq += 1
                        self.frame = jpeg
                        self.cond.notify_all()
        except (OSError, ValueError):
            pass
        finally:
            self.stopped.set()
            with self.cond:
                self.cond.notify_all()

    # ---- consumer ------------------------------------------------------
    def next_frame(self, after_seq, timeout):
        """Block until a frame newer than after_seq exists. Returns (seq, jpeg) or (after_seq, None) when over."""
        end = time.time() + timeout
        with self.cond:
            while self.seq <= after_seq:
                left = end - time.time()
                if self.stopped.is_set() or left <= 0:
                    return after_seq, None
                self.cond.wait(left)
            return self.seq, self.frame

    def error_text(self):
        """The TV's own complaint if it gave one, otherwise ffmpeg's (the TV's is the useful one)."""
        lines = list(self.errors["tv"]) or list(self.errors["ffmpeg"])
        return " | ".join(lines[-3:])


class LiveManager:
    """At most one live session per TV, and a global cap."""

    def __init__(self):
        self.lock = threading.Lock()
        self.sessions = {}

    def open(self, key, source_argv, preset, ffmpeg_bin):
        with self.lock:
            old = self.sessions.pop(key, None)
            if old:
                old.stop()
            if len(self.sessions) >= MAX_SESSIONS:
                raise LiveError("Too many live views are open (max %d). Close one first." % MAX_SESSIONS)
            s = LiveSession(source_argv, preset, ffmpeg_bin)
            self.sessions[key] = s
        s.start()
        return s

    def release(self, key, session):
        session.stop()
        with self.lock:
            if self.sessions.get(key) is session:
                del self.sessions[key]

    def count(self):
        with self.lock:
            return len(self.sessions)
