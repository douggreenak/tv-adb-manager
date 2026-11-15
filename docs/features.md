# Using the dashboard

## Devices

Each card shows the TV's state (**On**, **Standby**, **Offline**, **Needs approval on TV**), model and
Android version, the active **Input**, the foreground app (**Showing**), the remembered **Last input**
and when it was last seen. Quick buttons send Wake, Standby and Home. Click a card for the details drawer.

Use the search box and group chips to filter. Tick cards (or *Select all*) to get a bulk bar:
Wake, Standby, Home, Restore input, Reboot.

## The details drawer

| Tab | What it does |
|---|---|
| **Remote** | D-pad, Back/Home/Menu/Info/Input, volume, media keys, Wake/Standby/Reboot. A screenshot panel (refresh or auto-refresh every 3 s). Tick *Use keyboard* to drive it with arrows, Enter, Backspace (Back) and H (Home). |
| **Inputs** | Every TV input the framework reports, using the names you set on the TV. **Switch** launches it; **Set as power-on** chooses what gets restored. Also the restore switch, *Restore now* and *Forget*. |
| **Apps** | Installed, disabled, system or all packages with a filter box. Open, Stop, Disable/Enable, Clear data, Remove (uninstall for user 0). |
| **Install** | Upload an `.apk`; it is installed with `adb install -r`, so existing apps are updated in place. |
| **Shell** | Run `adb shell` commands. Up/Down recall history; chips offer common diagnostics. Output is capped at 60 KB and commands at 30 s. |
| **Info** | Storage and memory bars, uptime, IP and key build properties. |
| **Settings** | Rename, change address or group, reconnect ADB, remove the device from the manager (nothing changes on the TV). |

## Power-on restore

Stock Android TV launchers remember the last input and return to it when the TV powers on. If you disable
that launcher (for example to remove ads), the feature goes with it. This manager brings it back:

1. While a TV is awake on an HDMI-style input, the input is remembered.
2. When the TV wakes from standby, reboots, or comes back after a power cut, the manager waits about
   three seconds and looks at what the TV did on its own.
3. If the TV is sitting on its launcher, the remembered input is launched. If the TV already went to an
   input, or the user opened an app, nothing is done.

Turn it off per TV on the **Inputs** tab. Events appear in **Activity** ("remembered input…",
"restored input…", "not restoring input: TV is on …").

## Schedules

*Schedules → + New schedule*: pick an action (wake, standby, reboot, go Home, switch input), a time, days
of the week and the target TVs. Times use the **server's** clock. Each schedule can be toggled on and off.
A schedule fires at most once per minute even if the scheduler wakes twice.

## Activity

The last 300 events: status changes, restores, schedule runs, power actions, installs and every shell
command with the device it ran on. The full log is appended to `data/events.log`.
