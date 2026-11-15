"""Live screen view: the ffmpeg pipeline directly, and the HTTP endpoint. Needs ffmpeg (skipped without it)."""
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

from tests.fakes import FakeAdb
from tvmanager import live
from tvmanager.server import App, make_server

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
FFMPEG = shutil.which("ffmpeg")
SRC = ["ffmpeg", "-nostdin", "-loglevel", "error", "-re", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15", "-t", "6",
       "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-g", "15", "-pix_fmt", "yuv420p", "-f", "h264", "-"]
PRESET = live.PRESETS["low"]


@unittest.skipUnless(FFMPEG, "ffmpeg not installed")
class SessionTests(unittest.TestCase):
    def test_streams_jpeg_frames_and_stops(self):
        s = live.LiveSession(SRC, PRESET, FFMPEG)
        s.start()
        try:
            seq, f = s.next_frame(0, 10)
            self.assertIsNotNone(f)
            self.assertEqual(f[:2], b"\xff\xd8")                       # JPEG start
            self.assertEqual(f[-2:], b"\xff\xd9")                      # JPEG end: the frame is complete
            seq2, f2 = s.next_frame(seq, 10)
            self.assertGreater(seq2, seq)
        finally:
            s.stop()
        self.assertEqual(s.next_frame(s.seq, 0.5)[1], None)             # nothing after stop

    def test_source_failure_is_reported(self):
        s = live.LiveSession(["sh", "-c", "echo 'ERROR: no encoder' >&2; exit 1"], PRESET, FFMPEG)
        s.start()
        try:
            self.assertIsNone(s.next_frame(0, 6)[1])
            time.sleep(0.3)
            self.assertIn("no encoder", s.error_text())
        finally:
            s.stop()

    def test_manager_one_session_per_tv_and_cap(self):
        m = live.LiveManager()
        a = m.open("tv1", SRC, PRESET, FFMPEG)
        b = m.open("tv1", SRC, PRESET, FFMPEG)
        self.assertTrue(a.stopped.is_set())                            # replaced
        self.assertEqual(m.count(), 1)
        for i in range(live.MAX_SESSIONS - 1):
            m.open("x%d" % i, SRC, PRESET, FFMPEG)
        with self.assertRaises(live.LiveError):
            m.open("one-too-many", SRC, PRESET, FFMPEG)
        for k in list(m.sessions):
            m.release(k, m.sessions[k])
        self.assertEqual(m.count(), 0)


class LiveApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.adb = FakeAdb()
        cls.app = App(cls.tmp.name, WEB, adb=cls.adb, env_password="correct-horse", start_threads=False)
        cls.srv = make_server(cls.app, "127.0.0.1", 0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        r = urllib.request.Request("http://127.0.0.1:%d/api/login" % cls.port, data=b'{"password":"correct-horse"}', method="POST",
                                   headers={"X-Requested-With": "tvm", "Content-Type": "application/json"})
        cls.cookie = urllib.request.urlopen(r).headers["Set-Cookie"].split(";")[0]
        cls.dev = cls.app.store.add_device("Lobby", "10.9.9.9")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.tmp.cleanup()

    def setUp(self):
        self.adb.live_fail = False
        self.app.monitor.states[self.dev["id"]] = {"status": "online"}

    def get(self, path):
        r = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), headers={"Cookie": self.cookie})
        return urllib.request.urlopen(r, timeout=20)

    def err(self, path):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get(path).close()
        e = cm.exception
        return e.code, json.loads(e.read())["error"]

    def test_requires_login(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen("http://127.0.0.1:%d/api/devices/%s/live" % (self.port, self.dev["id"]))
        self.assertEqual(cm.exception.code, 401)

    def test_bad_quality_and_unreachable_and_no_ffmpeg(self):
        url = "/api/devices/%s/live" % self.dev["id"]
        self.assertEqual(self.err(url + "?quality=ultra")[0], 400)
        self.app.monitor.states[self.dev["id"]] = {"status": "offline"}
        self.assertEqual(self.err(url)[0], 409)
        self.app.monitor.states[self.dev["id"]] = {"status": "online"}
        with mock.patch("tvmanager.live.ffmpeg_path", return_value=None):
            code, msg = self.err(url)
        self.assertEqual(code, 501)
        self.assertIn("ffmpeg", msg)

    @unittest.skipUnless(FFMPEG, "ffmpeg not installed")
    def test_capture_failure_returns_the_reason(self):
        self.adb.live_fail = True
        code, msg = self.err("/api/devices/%s/live?quality=low" % self.dev["id"])
        self.assertEqual(code, 502)
        self.assertIn("No video", msg)
        self.assertIn("no encoder", msg)                              # the TV's own reason reaches the user
        self.assertEqual(self.app.live.count(), 0)                    # nothing left running
        ev = [e for e in self.app.events.list() if "live view failed" in e["msg"]]
        self.assertTrue(ev and ev[0]["level"] == "error" and "no encoder" in ev[0]["msg"])   # and the Activity log

    @unittest.skipUnless(FFMPEG, "ffmpeg not installed")
    def test_retries_with_native_size_when_the_preset_size_is_rejected(self):
        self.adb.live_fail_sized = True
        try:
            resp = self.get("/api/devices/%s/live?quality=low" % self.dev["id"])
            data = b""
            end = time.time() + 15
            while data.count(b"\xff\xd8") < 2 and time.time() < end:
                data += resp.read1(65536)
            resp.close()
        finally:
            self.adb.live_fail_sized = False
        self.assertGreaterEqual(data.count(b"\xff\xd8"), 2)
        sizes = [c[2] for c in self.adb.calls if c[0] == "screenrecord"][-2:]
        self.assertEqual(sizes, ["854x480", None])                    # preset first, then native

    @unittest.skipUnless(FFMPEG, "ffmpeg not installed")
    def test_streams_multipart_frames_and_cleans_up(self):
        resp = self.get("/api/devices/%s/live?quality=low" % self.dev["id"])
        self.assertTrue(resp.headers["Content-Type"].startswith("multipart/x-mixed-replace"))
        data = b""
        end = time.time() + 15
        while data.count(b"\xff\xd8") < 3 and time.time() < end:
            data += resp.read1(65536)
        resp.close()
        self.assertGreaterEqual(data.count(b"\xff\xd8"), 3)
        self.assertIn(b"Content-Length:", data)
        for _ in range(40):                                            # server notices the disconnect
            if self.app.live.count() == 0:
                break
            time.sleep(0.25)
        self.assertEqual(self.app.live.count(), 0)
        msgs = [e["msg"] for e in self.app.events.list()]
        self.assertTrue(any("live view started" in m for m in msgs))


if __name__ == "__main__":
    unittest.main()
