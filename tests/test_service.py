"""Running unattended: systemd notification, watchdog health check, activity-log rotation."""
import os
import socket
import tempfile
import threading
import time
import unittest

from tests.fakes import FakeAdb
from tvmanager import sdnotify
from tvmanager.server import App, make_server
from tvmanager.store import EventLog

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


class NotifyTests(unittest.TestCase):
    def test_noop_outside_systemd(self):
        os.environ.pop("NOTIFY_SOCKET", None)
        self.assertFalse(sdnotify.notify("READY=1"))

    def test_sends_datagrams_to_the_notify_socket(self):
        with tempfile.TemporaryDirectory() as t:
            path = os.path.join(t, "notify.sock")
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            srv.bind(path)
            srv.settimeout(3)
            os.environ["NOTIFY_SOCKET"] = path
            try:
                self.assertTrue(sdnotify.notify("READY=1"))
                self.assertEqual(srv.recv(100), b"READY=1")
                sdnotify.notify("WATCHDOG=1")
                self.assertEqual(srv.recv(100), b"WATCHDOG=1")
            finally:
                os.environ.pop("NOTIFY_SOCKET", None)
                srv.close()


class WatchdogTests(unittest.TestCase):
    def test_pings_systemd_while_healthy_and_stops_when_wedged(self):
        with tempfile.TemporaryDirectory() as t:
            path = os.path.join(t, "n.sock")
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            srv.bind(path)
            srv.settimeout(2)
            app = App(t, WEB, adb=FakeAdb(), env_password="correct-horse", start_threads=False)
            httpd = make_server(app, "127.0.0.1", 0)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            os.environ.update(NOTIFY_SOCKET=path, WATCHDOG_USEC="400000")            # ping every 0.2 s
            try:
                logs = []
                sdnotify.start_watchdog(app, "127.0.0.1", httpd.server_address[1], log=logs.append)
                self.assertEqual(srv.recv(50), b"WATCHDOG=1")                       # startup grace: pings before the first tick
                app.monitor.last_tick = time.time()
                self.assertEqual(srv.recv(50), b"WATCHDOG=1")                       # healthy
                app.monitor.last_tick = time.time() - 600                           # wedged poller: pings must stop
                time.sleep(0.5)
                srv.settimeout(0.8)
                with self.assertRaises(socket.timeout):
                    while True:
                        srv.recv(50)
                self.assertTrue(any("unhealthy" in m for m in logs))
            finally:
                os.environ.pop("NOTIFY_SOCKET", None)
                os.environ.pop("WATCHDOG_USEC", None)
                httpd.shutdown()
                srv.close()


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(self.tmp.name, WEB, adb=FakeAdb(), env_password="correct-horse", start_threads=False)
        self.srv = make_server(self.app, "127.0.0.1", 0)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.tmp.cleanup()

    def test_healthy_only_while_the_poller_ticks_and_the_server_answers(self):
        self.assertFalse(sdnotify.healthy(self.app, "127.0.0.1", self.port))       # poller never ticked
        self.app.monitor.last_tick = time.time()
        self.assertTrue(sdnotify.healthy(self.app, "127.0.0.1", self.port))
        self.app.monitor.last_tick = time.time() - 600                              # poller wedged
        self.assertFalse(sdnotify.healthy(self.app, "127.0.0.1", self.port))
        self.app.monitor.last_tick = time.time()
        self.srv.shutdown()
        self.srv.server_close()                                                     # HTTP server gone
        self.assertFalse(sdnotify.healthy(self.app, "127.0.0.1", self.port, timeout=1))

    def test_real_monitor_loop_keeps_the_heartbeat(self):
        self.app.monitor.poll = 0.1
        self.app.monitor.start()
        try:
            time.sleep(0.6)
            self.assertIsNotNone(self.app.monitor.last_tick)
            self.assertLess(time.time() - self.app.monitor.last_tick, 2)
        finally:
            self.app.monitor.stop()


class LogRotationTests(unittest.TestCase):
    def test_activity_log_is_capped(self):
        with tempfile.TemporaryDirectory() as t:
            log = EventLog(t)
            log.max_bytes = 2000
            for i in range(200):
                log.add("tv", "event number %d with some padding to take space" % i)
            names = sorted(os.listdir(t))
            self.assertEqual(names, ["events.log", "events.log.1"])
            self.assertLess(os.path.getsize(os.path.join(t, "events.log")), 4000)   # never grows without bound


if __name__ == "__main__":
    unittest.main()
