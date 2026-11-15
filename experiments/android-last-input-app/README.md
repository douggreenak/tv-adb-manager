# Abandoned: on-device "last input" app

First attempt at power-on restore: an AccessibilityService that recorded the active input and relaunched
it on screen-on / boot. It works until the TV enters standby, where the vendor firmware SIGKILLs
background processes and the accessibility service is marked crashed and never rebound. Kept for reference only.
The server-side restore in `tvmanager/monitor.py` replaced it. Build needs a JDK, `aapt`, `apksigner` and
`dalvik-exchange`, plus a signing key you generate yourself (`*.jks` is git-ignored).
