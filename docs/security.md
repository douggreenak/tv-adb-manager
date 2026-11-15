# Security

This application can run arbitrary shell commands on every TV it manages. Treat access to it like admin
access to those devices.

**What is in place**

* Password login, stored as an scrypt hash (`data/auth.json`, mode 0600). Sessions are random 256-bit
  tokens in `HttpOnly; SameSite=Strict` cookies and last 7 days; changing the password ends all sessions.
* Login throttling: 8 failed attempts per client IP per 5 minutes.
* CSRF: every non-GET API call must send `X-Requested-With: tvm`, which a cross-site form cannot do.
* Input validation: addresses, key codes, package names and input ids are matched against strict
  allow-list patterns before they reach a shell command. The shell tab is the one deliberate exception,
  and requires login.
* The static server resolves real paths and refuses anything outside `web/`.
* Response headers: `Content-Security-Policy` (same-origin only), `X-Frame-Options: DENY`, `nosniff`,
  `Cache-Control: no-store`. The UI builds all dynamic content with `textContent`, never `innerHTML`.
* Everything run through the shell tab and every package or power action is written to the activity log.

* **Live view shows the TV's screen** to anyone logged in. Starting and ending a view is recorded in *Activity*, views end
  after 30 minutes, and at most 4 run at once. Nothing is stored: frames are streamed and discarded.

**What is not**

* No TLS. Use a reverse proxy (see `setup.md`) or keep it on a trusted network.
* One shared password, no per-user accounts or roles.
* Sessions are in memory, so a restart signs everyone out.
* The ADB key on the server (`~/.android/adbkey`) is what TVs trust. Protect that account.

**Reporting a vulnerability**: open a private security advisory on the repository, or contact the maintainer
through GitHub rather than filing a public issue.
