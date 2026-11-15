# Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| **Needs approval on TV** | The *Allow USB debugging?* prompt is open on the TV. Accept it (tick *Always allow*). If it never appears, turn USB debugging off and on, or run `adb disconnect` then `adb connect <ip>:5555`. |
| Asked to approve again after every restart | The manager runs as a different user, or `~/.android/adbkey` changed. Run it as one fixed user. |
| **Offline** though the TV is on | The TV's IP changed, network debugging is off, or the TV reset its settings after an update. Check `ping <ip>` and `adb connect <ip>:5555` from the server. |
| Goes **Offline** when you press the remote's power button | Some sets drop off the network in deep standby. The manager restores the input when the TV returns, but it cannot wake a TV that is unreachable. |
| Wake does nothing | The TV must be reachable. If standby cuts the network, use the remote or HDMI-CEC to wake it. |
| Input not restored after power-on | Check **Activity**: "not restoring input: TV is on …" means the TV started an app, which is left alone. Make sure restore is enabled on the Inputs tab and that an input has been remembered (the *Last input* line on the card). |
| Restores the wrong input | Pick the right one on the Inputs tab and press **Set as power-on**, or *Forget* and switch to the input you want. |
| Live view says *No video from the TV* | The TV's firmware doesn't allow `screenrecord`. Try another quality; if it still fails the TV can't be viewed this way. |
| Live view is black on an HDMI input or in Netflix | The video layer isn't captured; only the interface is. This is a TV limitation, not a manager bug. |
| Live view says *needs ffmpeg* | Install it on the server: `sudo apt install ffmpeg`. |
| Screenshot fails (502) | Some TVs block `screencap`, and protected video renders black. Not fixable from the manager. |
| Install fails with `INSTALL_FAILED_…` | The message is shown in the output box. Common: `VERSION_DOWNGRADE`, `INSUFFICIENT_STORAGE`, or an APK for another ABI. |
| Can't log in | The password is in `data/auth.json` as a hash. Start once with `TVM_PASSWORD=newpass` to reset it. |
| Page loads but is blank | Check the browser console. A reverse proxy that rewrites paths or blocks `/app.js` is the usual cause. |

**Useful checks from the server**

```bash
adb devices                              # state of every connection
adb -s <ip>:5555 shell dumpsys power | grep mWakefulness
adb -s <ip>:5555 shell dumpsys tv_input | grep -A1 'SessionState@'
journalctl -u tv-adb-manager -f          # the manager's log
tail -f data/events.log                  # the activity log as JSON lines
```
