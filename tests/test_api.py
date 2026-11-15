import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from tests.fakes import FakeAdb
from tvmanager.server import App, make_server

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.adb = FakeAdb()
        cls.app = App(cls.tmp.name, WEB, adb=cls.adb, env_password="correct-horse", start_threads=False)
        cls.srv = make_server(cls.app, "127.0.0.1", 0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.tmp.cleanup()

    def req(self, method, path, body=None, cookie=None, raw=None, headers=None):
        h = {"X-Requested-With": "tvm"}
        if cookie:
            h["Cookie"] = cookie
        h.update(headers or {})
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        r = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def login(self):
        st, _, hd = self.req("POST", "/api/login", {"password": "correct-horse"})
        self.assertEqual(st, 200)
        return hd["Set-Cookie"].split(";")[0]

    def test_auth_required_and_login(self):
        self.assertEqual(self.req("GET", "/api/devices")[0], 401)
        self.assertEqual(self.req("POST", "/api/login", {"password": "nope"})[0], 401)
        c = self.login()
        self.assertEqual(self.req("GET", "/api/devices", cookie=c)[0], 200)

    def test_csrf_header_required_for_writes(self):
        c = self.login()
        r = urllib.request.Request("http://127.0.0.1:%d/api/devices" % self.port, data=b"{}", method="POST",
                                   headers={"Cookie": c})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(r)
        self.assertEqual(cm.exception.code, 403)

    def test_device_crud_action_and_validation(self):
        c = self.login()
        st, body, _ = self.req("POST", "/api/devices", {"name": "T1", "addr": "10.1.1.1", "group": "Lobby"}, c)
        self.assertEqual(st, 201)
        dev = json.loads(body)
        self.assertEqual(dev["addr"], "10.1.1.1:5555")
        self.assertEqual(self.req("POST", "/api/devices", {"name": "dup", "addr": "10.1.1.1"}, c)[0], 400)
        self.assertEqual(self.req("POST", "/api/devices", {"name": "bad", "addr": "1.1.1.1; ls"}, c)[0], 400)
        did = dev["id"]
        self.adb.calls.clear()
        self.assertEqual(self.req("POST", "/api/devices/%s/action" % did, {"action": "wake"}, c)[0], 200)
        self.assertIn("input keyevent KEYCODE_WAKEUP", self.adb.shells())
        self.assertEqual(self.req("POST", "/api/devices/%s/action" % did, {"action": "key", "key": "KEYCODE_HOME; reboot"}, c)[0], 400)
        self.assertEqual(self.req("POST", "/api/devices/%s/packages/%s" % (did, "com.x;reboot"), {"action": "disable"}, c)[0], 404)
        self.assertEqual(self.req("POST", "/api/devices/%s/packages/com.a.b" % did, {"action": "disable"}, c)[0], 200)
        self.assertIn("pm disable-user --user 0 com.a.b", self.adb.shells())
        st, body, _ = self.req("POST", "/api/devices/%s/action" % did, {"action": "input", "input": "x/HDMI1' ; reboot"}, c)
        self.assertFalse(json.loads(body)["ok"])
        self.assertEqual(self.req("GET", "/api/devices/%s/screenshot" % did, cookie=c)[0], 200)
        self.assertEqual(self.req("DELETE", "/api/devices/%s" % did, cookie=c)[0], 200)
        self.assertEqual(self.req("GET", "/api/devices/%s/info" % did, cookie=c)[0], 404)

    def test_bulk_and_events(self):
        c = self.login()
        ids = [json.loads(self.req("POST", "/api/devices", {"name": n, "addr": a}, c)[1])["id"]
               for n, a in (("B1", "10.2.2.1"), ("B2", "10.2.2.2"))]
        st, body, _ = self.req("POST", "/api/bulk", {"action": "sleep", "ids": ids + ["ghost"]}, c)
        res = json.loads(body)["results"]
        self.assertTrue(res[ids[0]]["ok"] and res[ids[1]]["ok"])
        self.assertFalse(res["ghost"]["ok"])
        ev = json.loads(self.req("GET", "/api/events", cookie=c)[1])["events"]
        self.assertTrue(any("sleep" in e["msg"] for e in ev))

    def test_install_streams_to_adb(self):
        c = self.login()
        did = json.loads(self.req("POST", "/api/devices", {"name": "I", "addr": "10.3.3.3"}, c)[1])["id"]
        st, body, _ = self.req("POST", "/api/devices/%s/install?name=a.apk" % did, cookie=c, raw=b"PK\x03\x04data",
                               headers={"Content-Type": "application/octet-stream"})
        self.assertEqual(st, 200)
        self.assertTrue(json.loads(body)["ok"])
        self.assertTrue(any(x[0] == "install" for x in self.adb.calls))

    def test_schedule_validation_and_crud(self):
        c = self.login()
        did = json.loads(self.req("POST", "/api/devices", {"name": "S", "addr": "10.4.4.4"}, c)[1])["id"]
        self.assertEqual(self.req("POST", "/api/schedules", {"action": "wake", "time": "25:00", "targets": [did]}, c)[0], 400)
        self.assertEqual(self.req("POST", "/api/schedules", {"action": "wake", "time": "07:30", "targets": []}, c)[0], 400)
        st, body, _ = self.req("POST", "/api/schedules", {"action": "wake", "time": "7:05", "days": [0, 1], "targets": [did]}, c)
        self.assertEqual(st, 201)
        s = json.loads(body)
        self.assertEqual(s["time"], "07:05")
        self.assertEqual(self.req("DELETE", "/api/schedules/%s" % s["id"], cookie=c)[0], 200)

    def test_static_and_traversal(self):
        self.assertEqual(self.req("GET", "/")[0], 200)
        self.assertEqual(self.req("GET", "/..%2f..%2fetc/passwd")[0], 404)
        self.assertEqual(self.req("GET", "/../tvmanager/auth.py")[0], 404)

    def test_change_password(self):
        c = self.login()
        self.assertEqual(self.req("POST", "/api/password", {"current": "bad", "new": "longenough1"}, c)[0], 403)
        self.assertEqual(self.req("POST", "/api/password", {"current": "correct-horse", "new": "short"}, c)[0], 400)


if __name__ == "__main__":
    unittest.main()
