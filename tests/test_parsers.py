import unittest
from tvmanager import parsers as P

TV_INPUT = """TV Input Manager State:
  inputMap: inputId -> TvInputState
    com.hisense.tv.hitvinput/.tuner.TunerTvInputService/HW0: info: TvInputInfo{id=com.hisense.tv.hitvinput/.tuner.TunerTvInputService/HW0, pkg=com.hisense.tv.hitvinput, service=x}; state: 0
    com.hisense.tv.hitvinput/.hdmi.HdmiTvInputService/HW7: info: TvInputInfo{id=com.hisense.tv.hitvinput/.hdmi.HdmiTvInputService/HW7, pkg=p, service=s}; state: 1
    com.hisense.tv.hitvinput/.composite.CompositeTvInputService/HW1: info: TvInputInfo{id=com.hisense.tv.hitvinput/.composite.CompositeTvInputService/HW1, pkg=p, service=s}; state: 2
  sessionStateMap: ITvInputSession -> SessionState
    android.os.Binder@9a881da: com.android.server.tv.TvInputManagerService$SessionState@92e3197
      inputId: com.hisense.tv.hitvinput/.hdmi.HdmiTvInputService/HW5
"""


class ParserTests(unittest.TestCase):
    def test_wakefulness(self):
        self.assertTrue(P.parse_wakefulness("  mWakefulness=Awake\n"))
        self.assertFalse(P.parse_wakefulness("  mWakefulness=Asleep"))
        self.assertFalse(P.parse_wakefulness("mWakefulness=Dozing"))
        self.assertIsNone(P.parse_wakefulness("nothing"))

    def test_sessions_ignore_map_header(self):
        self.assertEqual(P.parse_sessions(TV_INPUT), ["com.hisense.tv.hitvinput/.hdmi.HdmiTvInputService/HW5"])

    def test_inputs_and_states(self):
        ins = P.parse_inputs(TV_INPUT)
        self.assertEqual([i["state"] for i in ins], ["connected", "standby", "disconnected"])
        self.assertEqual(len(ins), 3)

    def test_passthrough_selection(self):
        tuner = "com.hisense.tv.hitvinput/.tuner.TunerTvInputService/HW0"
        hdmi = "com.hisense.tv.hitvinput/.hdmi.HdmiTvInputService/HW5"
        self.assertFalse(P.is_passthrough(tuner))
        self.assertTrue(P.is_passthrough("com.tcl.tvinput/.TvPassThroughService/HW15"))
        self.assertTrue(P.is_passthrough("com.mediatek.tvinput/.hdmi.HDMIInputService/HDMI100004"))
        self.assertEqual(P.pick_passthrough([tuner, hdmi]), hdmi)
        self.assertIsNone(P.pick_passthrough([tuner]))

    def test_top_activity(self):
        a11 = "    mResumedActivity: ActivityRecord{3e82436 u0 com.mediatek.wwtv.tvcenter/.LiveTVMainActivity t270}"
        a14 = "    topResumedActivity=ActivityRecord{d10dbcd u0 com.mediatek.wwtv.tvcenter/.nav.TurnkeyUiMainActivity t68}"
        self.assertEqual(P.parse_top_activity(a11), "com.mediatek.wwtv.tvcenter/.LiveTVMainActivity")
        self.assertEqual(P.parse_top_activity(a14), "com.mediatek.wwtv.tvcenter/.nav.TurnkeyUiMainActivity")
        self.assertIsNone(P.parse_top_activity(""))

    def test_labels(self):
        v = ("com.hisense.tv.hitvinput%2F.hdmi.HdmiTvInputService%2FHW5,Bethel%20Live%20Stream%20:"
             "com.hisense.tv.hitvinput%2F.hdmi.HdmiTvInputService%2FHW4,Soundbar")
        lab = P.parse_labels(v)
        k5 = "com.hisense.tv.hitvinput/.hdmi.HdmiTvInputService/HW5"
        self.assertEqual(lab[k5], "Bethel Live Stream")
        self.assertEqual(P.short_input_name(k5, lab), "Bethel Live Stream")
        self.assertEqual(P.short_input_name("x/y/HW9", lab), "HW9")
        self.assertEqual(P.parse_labels("null"), {})

    def test_packages_props_df_mem(self):
        self.assertEqual(P.parse_packages("package:b.b.b\npackage:a.a.a\n"), ["a.a.a", "b.b.b"])
        self.assertEqual(P.parse_props("[ro.x]: [1]\n[ro.y]: []\n"), {"ro.x": "1", "ro.y": ""})
        self.assertEqual(P.parse_df("Filesystem 1K-blocks Used Available Use% Mounted\n/dev/x 1000 400 600 40% /data"), (1000, 400))
        self.assertEqual(P.parse_meminfo("MemTotal:  100 kB\nMemFree: 5 kB\nMemAvailable:  60 kB"), {"MemTotal": 100, "MemAvailable": 60})

    def test_validators(self):
        self.assertTrue(P.SAFE_PKG.match("com.google.android.tvlauncher"))
        self.assertFalse(P.SAFE_PKG.match("com.x; rm -rf /"))
        self.assertTrue(P.SAFE_KEY.match("KEYCODE_HOME"))
        self.assertFalse(P.SAFE_KEY.match("KEYCODE_HOME; reboot"))
        self.assertTrue(P.SAFE_ADDR.match("192.168.1.10:5555"))
        self.assertFalse(P.SAFE_ADDR.match("1.2.3.4; ls"))
        self.assertFalse(P.SAFE_INPUT.match("x' ; reboot ; '"))


if __name__ == "__main__":
    unittest.main()
