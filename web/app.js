"use strict";
/* TV Manager UI. All dynamic text is set via textContent, never innerHTML. */

const $ = (s, el = document) => el.querySelector(s);

/* DOM's append/replaceChildren print `null` and `false` as literal text. Skip empty values so a conditional child
   (`cond ? el : null`) can never leak the word "null" onto the page. */
for (const m of ["append", "prepend", "replaceChildren"]) {
  const native = Element.prototype[m];
  Element.prototype[m] = function (...kids) { return native.apply(this, kids.filter(k => k != null && k !== false)); };
}

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

function toast(msg, error = false) {
  const t = h("div", { class: "toast" + (error ? " error" : ""), role: error ? "alert" : "status" }, msg);
  $("#toasts").append(t);
  setTimeout(() => t.remove(), error ? 6000 : 2800);
}

/* ---------- Material icons (Apache-2.0 path data), built with createElementNS ---------- */
const ICONS = {
  tv: "M21 3H3c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h5v2h8v-2h5c1.1 0 1.99-.9 1.99-2L23 5c0-1.1-.9-2-2-2zm0 14H3V5h18v12z",
  schedule: "M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z",
  list: "M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z",
  settings: "M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z",
  add: "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z",
  remove: "M19 13H5v-2h14v2z",
  search: "M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z",
  close: "M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z",
  apps: "M4 8h4V4H4v4zm6 12h4v-4h-4v4zm-6 0h4v-4H4v4zm0-6h4v-4H4v4zm6 0h4v-4h-4v4zm6-10v4h4V4h-4zm-6 4h4V4h-4v4zm6 6h4v-4h-4v4zm0 6h4v-4h-4v4z",
  logout: "M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z",
  back: "M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z",
  home: "M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z",
  menu: "M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z",
  info: "M11 7h2v2h-2zm0 4h2v6h-2zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z",
  input: "M21 3.01H3c-1.1 0-2 .9-2 2V9h2V4.99h18v14.03H3V15H1v4.01c0 1.1.9 1.98 2 1.98h18c1.1 0 2-.88 2-1.98v-14c0-1.11-.9-2-2-2zM11 16l4-4-4-4v3H1v2h10v3z",
  up: "M7.41 15.41L12 10.83l4.59 4.58L18 14l-6-6-6 6z",
  down: "M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6z",
  left: "M15.41 16.59L10.83 12l4.58-4.59L14 6l-6 6 6 6z",
  right: "M8.59 16.59L13.17 12 8.59 7.41 10 6l6 6-6 6z",
  volume_off: "M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z",
  rewind: "M11 18V6l-8.5 6 8.5 6zm.5-6l8.5 6V6l-8.5 6z",
  play: "M8 5v14l11-7z",
  ff: "M4 18l8.5-6L4 6v12zm9-12v12l8.5-6L13 6z",
  power: "M13 3h-2v10h2V3zm4.83 2.17l-1.42 1.42C17.99 7.86 19 9.81 19 12c0 3.87-3.13 7-7 7s-7-3.13-7-7c0-2.19 1.01-4.14 2.58-5.42L6.17 5.17C4.23 6.82 3 9.26 3 12c0 4.97 4.03 9 9 9s9-4.03 9-9c0-2.74-1.23-5.18-3.17-6.83z",
  check: "M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z",
  edit: "M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z",
  delete: "M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z",
  more: "M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z",
  upload: "M9 16h6v-6h4l-7-7-7 7h4zm-4 2h14v2H5z",
  refresh: "M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z",
  lock: "M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z",
  error: "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z",
  done: "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z",
  fullscreen: "M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z",
  camera: "M9 2L7.17 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2h-3.17L15 2H9zm3 15c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5z",
  terminal: "M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 14H4V8h16v10zm-2-1h-6v-2h6v2zM7.5 17l-1.41-1.41L8.67 13l-2.58-2.59L7.5 9l4 4-4 4z",
};
function ic(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("class", "ic"); svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", ICONS[name] || ICONS.info); svg.append(path);
  return svg;
}

/* the site icon (web/favicon.svg) doubles as the logo in the rail and on the login card */
const brandMark = title => h("div", { class: "brand-mark", title: title || null, style: "background:none;overflow:hidden" },
  h("img", { src: "/favicon.svg", alt: "", style: "width:100%;height:100%;border-radius:inherit;display:block" }));

/* ---------- theme: light/dark/auto + accent seed hue, remembered per browser ---------- */
const prefs = {
  get(k, d) { try { return localStorage.getItem(k) ?? d; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
};
const HUES = [["Blue", 262], ["Teal", 195], ["Green", 150], ["Amber", 75], ["Rose", 5], ["Violet", 300]];
function applyTheme() {
  const r = document.documentElement, mode = prefs.get("tvm-mode", "auto");
  if (mode === "auto") delete r.dataset.theme; else r.dataset.theme = mode;
  r.style.setProperty("--h", String(parseInt(prefs.get("tvm-hue", "262"), 10) || 262));
}
applyTheme();

/* ---------- helpers ---------- */
const cap = s => s ? s.charAt(0).toUpperCase() + s.slice(1) : s;

async function api(method, path, body) {
  const opt = { method, credentials: "same-origin", headers: { "X-Requested-With": "tvm" } };
  if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const r = await fetch(path, opt);
  if (r.status === 401 && path !== "/api/login") { showLogin(); throw new Error("Login required"); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(cap(data.error || ("HTTP " + r.status)));
  return data;
}
const act = (id, action, extra) => api("POST", `/api/devices/${id}/action`, { action, ...extra });

function ago(ts) {
  if (!ts) return "never";
  const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  if (s < 10) return "just now";
  if (s < 90) return s + "s ago";
  if (s < 5400) return Math.round(s / 60) + "m ago";
  if (s < 129600) return Math.round(s / 3600) + "h ago";
  return Math.round(s / 86400) + "d ago";
}
const fmtKb = kb => kb == null ? "?" : kb > 1048576 ? (kb / 1048576).toFixed(1) + " GB" : Math.round(kb / 1024) + " MB";
const fmtBytes = n => n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
const STATUS_TEXT = { online: "On", asleep: "Standby", offline: "Offline", unauthorized: "Needs approval on TV", unknown: "Checking…" };
const usable = d => !!d && (d.status === "online" || d.status === "asleep");

const APP_NAMES = {
  "com.mediatek.wwtv.tvcenter": "Live TV", "com.tcl.tv": "Live TV", "com.leanbitlab.ltvL": "Launcher",
  "com.netflix.ninja": "Netflix", "com.google.android.youtube.tv": "YouTube", "com.google.android.youtube.tvunplugged": "YouTube TV",
  "com.google.android.tvlauncher": "Android TV Home", "com.google.android.apps.tv.launcherx": "Google TV Home",
  "com.android.tv.settings": "Settings", "com.android.settings": "Settings", "com.android.vending": "Play Store",
  "com.amazon.amazonvideo.livingroom": "Prime Video", "com.disney.disneyplus": "Disney+", "com.hulu.plus": "Hulu",
  "com.spotify.tv.android": "Spotify", "com.plexapp.android": "Plex", "org.jellyfin.androidtv": "Jellyfin",
  "com.mediatek.AirplayAPK": "AirPlay", "com.google.android.apps.tv.dreamx": "Screensaver",
};
const GENERIC_SEG = new Set(["tv", "app", "apk", "android", "main", "client", "mobile", "ninja", "livingroom"]);
function appName(pkg) {
  if (!pkg) return "";
  pkg = pkg.split("/")[0];
  if (APP_NAMES[pkg]) return APP_NAMES[pkg];
  const segs = pkg.split(".");
  let seg = segs[segs.length - 1];
  for (let i = segs.length - 1; i > 0 && GENERIC_SEG.has(seg.toLowerCase()); i--) seg = segs[i - 1];
  return cap(seg.replace(/([a-z])([A-Z])/g, "$1 $2"));
}
const shortInputId = id => id.split("/").slice(-2).join("/");

const S = { devices: [], groups: [], selected: new Set(), view: "devices", filter: "", group: "", open: null, tab: "remote", timer: null,
  evFilter: "all", evSig: "", drawerUsable: null };

/* ---------- reusable pieces ---------- */
function emptyState(icon, title, text, action) {
  return h("div", { class: "empty-state" }, h("div", { class: "empty-ic" }, ic(icon)), h("h2", null, title), h("p", null, text), action);
}

function selectField(sel, compact) { return h("span", { class: "select" + (compact ? " compact" : "") }, sel); }

/* ⋮ menu: click to open, Esc or outside click to close */
function menu(items, label) {
  const btn = h("button", { class: "icon-btn small plain", "aria-label": label || "More actions", "aria-haspopup": "menu", "aria-expanded": "false" }, ic("more"));
  const pop = h("div", { class: "menu hidden", role: "menu" }, items.map(([text, fn, danger]) =>
    h("button", { role: "menuitem", class: "menu-item" + (danger ? " danger" : ""), onclick: () => { close(); fn(); } }, text)));
  const wrap = h("div", { class: "menu-wrap" }, btn, pop);
  const outside = e => { if (!wrap.contains(e.target)) close(); };
  const esc = e => { if (e.key === "Escape") { e.stopPropagation(); close(); btn.focus(); } };
  function close() { pop.classList.add("hidden"); btn.setAttribute("aria-expanded", "false"); document.removeEventListener("click", outside, true); document.removeEventListener("keydown", esc, true); }
  btn.addEventListener("click", e => {
    e.stopPropagation();
    if (!pop.classList.contains("hidden")) return close();
    pop.classList.remove("hidden"); btn.setAttribute("aria-expanded", "true");
    document.addEventListener("click", outside, true); document.addEventListener("keydown", esc, true);
    pop.querySelector("button").focus();
  });
  return wrap;
}

const wolBtn = (d, cls) => h("button", { class: "btn " + (cls || "small"), title: d.mac ? "Send a Wake-on-LAN packet to " + d.mac : "MAC address not known yet",
  disabled: !d.mac, onclick: async e => { e.stopPropagation(); try { const r = await act(d.id, "wol"); toast(r.output, !r.ok); } catch (x) { toast(x.message, true); } } }, ic("power"), "Wake over network");

function unavailable(d, what) {
  const un = d.status === "unauthorized", checking = d.status === "unknown";
  return h("div", { class: "panel empty-panel" }, h("div", { class: "empty-ic" }, ic(un ? "lock" : "tv")),
    h("h3", null, un ? "Waiting for approval" : checking ? "Checking…" : "TV is offline"),
    h("p", { class: "muted" }, un ? "Accept the “Allow USB debugging?” prompt on the TV and tick “Always allow”, then try again."
      : checking ? "Connecting to the TV." : `${what} will be available once the TV is reachable. Check that it's powered on and on the network.`),
    checking ? null : h("div", { class: "keys" },
      h("button", { class: "btn", onclick: async () => { const r = await act(d.id, "connect"); toast(r.output || (r.ok ? "Connected" : "Still unreachable"), !r.ok); } }, ic("refresh"), un ? "Try again" : "Reconnect"),
      un ? null : wolBtn(d, "")));
}

/* ---------- login ---------- */
function showLogin(msg) {
  clearInterval(S.timer);
  const err = h("p", { class: "err", role: "alert" }, msg || "");
  const pw = h("input", { type: "password", id: "pw", autocomplete: "current-password", autofocus: true });
  const go = async e => {
    e.preventDefault();
    try { await api("POST", "/api/login", { password: pw.value }); start(); }
    catch (x) { err.textContent = x.message; pw.select(); }
  };
  $("#app").replaceChildren(h("div", { class: "login-screen" }, h("form", { class: "login", onsubmit: go },
    brandMark(), h("h1", null, "TV Manager"),
    h("p", { class: "muted", style: "margin-bottom:22px" }, "Sign in to manage your TVs"),
    h("div", { class: "field" }, h("label", { for: "pw" }, "Password"), pw),
    err, h("button", { class: "btn primary", type: "submit" }, "Sign in"))));
  pw.focus();
}

/* ---------- shell ---------- */
async function start() {
  const s = await api("GET", "/api/session");
  if (!s.authenticated) return showLogin();
  S.version = s.version;
  renderShell();
  await refresh();
  clearInterval(S.timer);
  S.timer = setInterval(() => { if (!document.hidden) tick(); }, 3000);
}

const NAV = [["devices", "Devices", "tv"], ["schedules", "Schedules", "schedule"], ["events", "Activity", "list"], ["settings", "Settings", "settings"]];
const hubUrl = () => `http://${location.hostname}:8090/apps`;
const signOut = async () => { await api("POST", "/api/logout"); showLogin(); };

function renderShell() {
  const items = NAV.map(([v, label, icon]) => h("button", { class: "nav-item", "aria-current": String(S.view === v),
    onclick: () => { S.view = v; renderShell(); refresh(); } }, h("span", { class: "pill" }, ic(icon)), label));
  $("#app").replaceChildren(h("div", { class: "shell" },
    h("header", { class: "topbar" }, h("div", { class: "title" }, "TV Manager"),
      h("a", { class: "apps-pill appslink", href: hubUrl(), title: "Services hub — all apps", "aria-label": "Apps" }, ic("apps"), h("span", { class: "lbl" }, "Apps")),
      h("button", { class: "icon-btn", onclick: signOut, "aria-label": "Sign out" }, ic("logout"))),
    h("nav", { class: "nav", "aria-label": "Main" }, brandMark("TV Manager"), items),
    h("div", { class: "content" }, h("main", { class: "main", id: "main" }))));
  renderFab();
}

/* one contextual extended FAB per page (icon-only on phones) */
function renderFab() {
  $("#fab")?.remove();
  const spec = { devices: ["Add device", addDeviceDialog], schedules: ["New schedule", () => scheduleDialog()] }[S.view];
  if (spec) $(".shell").append(h("button", { class: "fab", id: "fab", "aria-label": spec[0], onclick: spec[1] }, ic("add"), h("span", { class: "fab-label" }, spec[0])));
}

async function tick() {
  if (S.view === "devices" || S.view === "schedules") await loadDevices();
  if (S.view === "events") await renderEvents();
  if (S.view === "devices") renderDevices(); // cheap; keeps cards live
  if (S.open) updateDrawerHead();
}

async function refresh() {
  await loadDevices();
  if (S.view === "devices") renderDevices();
  else if (S.view === "schedules") await renderSchedules();
  else if (S.view === "events") { S.evSig = ""; await renderEvents(); }
  else renderSettings();
}

async function loadDevices() {
  try { const d = await api("GET", "/api/devices"); S.devices = d.devices; S.groups = d.groups; } catch (e) { /* login handled */ }
}
const byId = id => S.devices.find(d => d.id === id);

/* ---------- devices view ---------- */
function statusEl(d) {
  return h("span", { class: "status s-" + d.status }, h("i", { class: "dot" }), STATUS_TEXT[d.status] || d.status);
}

function renderDevices() {
  const main = $("#main"); if (!main || S.view !== "devices") return;
  $("#fab")?.classList.toggle("hidden", !S.devices.length);
  if (!S.devices.length) {
    main.replaceChildren(h("div", { class: "page-head" }, h("h1", null, "Devices")),
      emptyState("tv", "No TVs yet", "Add a TV by its IP address. ADB debugging (network) must be enabled on it, and the first connection asks you to approve this server on the TV screen.",
        h("button", { class: "btn primary", onclick: addDeviceDialog }, ic("add"), "Add your first TV")));
    return;
  }
  const q = S.filter.toLowerCase();
  const list = S.devices.filter(d => (!S.group || d.group === S.group) &&
    (!q || [d.name, d.addr, d.model, d.group].some(x => (x || "").toLowerCase().includes(q))));
  const online = S.devices.filter(d => d.status === "online").length;
  const asleep = S.devices.filter(d => d.status === "asleep").length;
  const off = S.devices.length - online - asleep;

  // keep search box focus across live re-renders
  const prev = $("#search"); const keepFocus = prev && document.activeElement === prev; const caret = prev && prev.selectionStart;
  const search = h("label", { class: "searchbar" }, ic("search"),
    h("input", { type: "text", id: "search", placeholder: "Search devices", value: S.filter, "aria-label": "Search devices",
      oninput: e => { S.filter = e.target.value; renderDevices(); } }));

  const groupChips = S.groups.length ? h("div", { class: "chips", role: "group", "aria-label": "Filter by group" },
    h("button", { class: "chip", "aria-pressed": String(!S.group), onclick: () => { S.group = ""; renderDevices(); } }, "All"),
    S.groups.map(g => h("button", { class: "chip", "aria-pressed": String(S.group === g), onclick: () => { S.group = g; renderDevices(); } }, g))) : null;

  const sel = [...S.selected].filter(id => byId(id));
  const bulk = sel.length ? h("div", { class: "bulkbar" },
    h("strong", null, sel.length + " selected"),
    ...[["wake", "Wake"], ["sleep", "Standby"], ["home", "Home"], ["restore", "Restore input"]].map(([a, l]) =>
      h("button", { class: "btn small", onclick: () => bulk_(a, sel) }, l)),
    h("button", { class: "btn small danger", onclick: () => confirm("Reboot " + sel.length + " device(s)?") && bulk_("reboot", sel) }, "Reboot"),
    h("span", { style: "flex:1" }),
    h("button", { class: "btn small", onclick: () => { S.selected.clear(); renderDevices(); } }, "Clear")) : null;

  const cards = list.length ? h("div", { class: "grid" }, list.map(card)) :
    emptyState("search", "No matches", S.filter ? `Nothing matches “${S.filter}”.` : "No devices in this group.",
      h("button", { class: "btn", onclick: () => { S.filter = ""; S.group = ""; renderDevices(); } }, "Clear filters"));
  const stat = (cls, text) => h("span", { class: "stat " + cls }, h("i"), text);

  main.replaceChildren(
    h("div", { class: "page-head" }, h("h1", null, "Devices"),
      h("div", { class: "stats" }, stat("on", online + " on"), stat("sb", asleep + " standby"), stat("", off + " offline"))),
    h("div", { class: "toolbar" }, search, groupChips, h("span", { class: "grow" }),
      h("button", { class: "btn", onclick: () => { const all = list.every(d => S.selected.has(d.id)); list.forEach(d => all ? S.selected.delete(d.id) : S.selected.add(d.id)); renderDevices(); } }, "Select all")),
    ...(bulk ? [bulk] : []), cards);
  if (keepFocus) { const s = $("#search"); s.focus(); s.setSelectionRange(caret, caret); }
}

async function bulk_(action, ids) {
  try {
    const r = await api("POST", "/api/bulk", { action, ids });
    const bad = Object.values(r.results).filter(x => !x.ok).length;
    toast(bad ? `${cap(action)}: ${bad} of ${ids.length} failed` : `${cap(action)} sent to ${ids.length} TV${ids.length === 1 ? "" : "s"}`, !!bad);
  } catch (e) { toast(e.message, true); }
}

const powerOn = d => !d.restore.enabled ? "Off" : d.restore.last_name || "Not recorded yet";
const reconnect = d => async e => { e.stopPropagation(); const r = await act(d.id, "connect"); toast(r.output || (r.ok ? "Connected" : "Still unreachable"), !r.ok); };

function card(d) {
  const sel = S.selected.has(d.id);
  const quick = (label, a) => h("button", { class: "btn small", onclick: async e => { e.stopPropagation(); try { const r = await act(d.id, a); toast(r.ok ? label + " sent" : "Failed: " + r.output, !r.ok); } catch (x) { toast(x.message, true); } } }, label);
  const open = () => openDrawer(d.id);
  const row = (k, v, title) => [h("dt", null, k), h("dd", { title: title || null }, v)];
  const model = [[d.manufacturer, d.model].filter(Boolean).join(" ") || "–", d.android ? ` · Android ${d.android}` : ""].join("");
  let body, actions;
  if (d.status === "online") {
    body = h("dl", null, row("Model", model), row("Showing", d.input_name || appName(d.top) || "–", d.top), row("Power-on input", powerOn(d)));
  } else if (d.status === "asleep") {
    body = h("dl", null, row("Model", model), row("Power-on input", powerOn(d)), row("Last seen", ago(d.last_seen)));
  } else if (d.status === "unauthorized") {
    body = h("div", { class: "card-note" }, ic("lock"), "Accept the “Allow USB debugging?” prompt on this TV to let the manager connect.");
  } else {
    body = h("div", { class: "card-note" }, ic("tv"), d.last_seen ? `Not reachable. Last seen ${ago(d.last_seen)}.` : d.status === "unknown" ? "Checking connection…" : "Not reachable yet. Check that it's on and on the network.");
  }
  if (usable(d)) actions = h("div", { class: "btn-group full" }, quick("Wake", "wake"), quick("Standby", "sleep"), quick("Home", "home"));
  else if (d.status !== "unknown") actions = h("div", { class: "btn-group full" },
    h("button", { class: "btn small", onclick: reconnect(d) }, ic("refresh"), d.status === "unauthorized" ? "Try again" : "Reconnect"),
    d.status === "offline" ? wolBtn(d) : null);
  return h("div", { class: "card" + (sel ? " selected" : ""), tabindex: "0", role: "button", "aria-label": "Open " + d.name,
      onclick: open, onkeydown: e => { if (e.key === "Enter" && e.target === e.currentTarget) open(); } },
    h("div", { class: "card-head" },
      h("div", { class: "avatar av-" + d.status }, ic("tv")),
      h("div", { class: "title" }, h("div", { class: "name" }, d.name), h("div", { class: "mono" }, d.addr)),
      h("input", { type: "checkbox", checked: sel, "aria-label": "Select " + d.name,
        onclick: e => e.stopPropagation(), onchange: e => { e.target.checked ? S.selected.add(d.id) : S.selected.delete(d.id); renderDevices(); } })),
    h("div", { class: "card-meta" }, statusEl(d), d.group ? h("span", { class: "badge" }, d.group) : null),
    body, actions);
}

function modal(title, bodyEls, buttons) {
  const m = h("div", { class: "modal", role: "dialog", "aria-modal": "true", "aria-label": title },
    h("div", { class: "box" }, h("h2", null, title), bodyEls, h("div", { class: "actions" }, buttons)));
  m.close = () => { m.remove(); document.removeEventListener("keydown", esc_); };
  const esc_ = e => { if (e.key === "Escape") m.close(); };
  document.addEventListener("keydown", esc_);
  m.addEventListener("mousedown", e => { if (e.target === m) m.close(); });
  document.body.append(m);
  const first = m.querySelector("input,select"); if (first) first.focus();
  return m;
}

function addDeviceDialog() {
  const name = h("input", { type: "text", id: "an", placeholder: "Leave empty to use the TV's own name", autocomplete: "off" });
  const addr = h("input", { type: "text", id: "aa", placeholder: "192.168.1.50", autocomplete: "off", inputmode: "decimal" });
  const group = h("input", { type: "text", id: "ag", placeholder: "Optional, e.g. Lobby", list: "grps", autocomplete: "off" });
  const addrErr = h("p", { class: "hint err", role: "alert" });
  const submit = async () => {
    addrErr.textContent = ""; addr.removeAttribute("aria-invalid");
    try { await api("POST", "/api/devices", { name: name.value, addr: addr.value, group: group.value }); m.close(); toast("Device added"); refresh(); }
    catch (e) { addrErr.textContent = e.message; addr.setAttribute("aria-invalid", "true"); addr.focus(); }
  };
  [name, addr, group].forEach(i => i.addEventListener("keydown", e => { if (e.key === "Enter") submit(); }));
  const m = modal("Add device", [
    h("div", { class: "field" }, h("label", { for: "an" }, "Name (optional)"), name),
    h("div", { class: "field" }, h("label", { for: "aa" }, "IP address"), addr, h("span", { class: "hint" }, "Port 5555 is used unless you add one, like 192.168.1.50:5556."), addrErr),
    h("div", { class: "field" }, h("label", { for: "ag" }, "Group"), group, h("datalist", { id: "grps" }, S.groups.map(g => h("option", { value: g })))),
    h("p", { class: "muted", style: "font-size:13.5px" }, "ADB debugging (network) must be on in the TV's Developer options. The first connection asks you to approve this server on the TV screen.")], [
    h("button", { class: "btn text", onclick: () => m.close() }, "Cancel"),
    h("button", { class: "btn primary", onclick: submit }, "Add")]);
}

/* ---------- side sheet (drawer) ---------- */
const TABS = [["remote", "Remote"], ["screen", "Screen"], ["inputs", "Inputs"], ["apps", "Apps"], ["install", "Install"], ["shell", "Shell"], ["info", "Info"], ["settings", "Settings"]];
let shotTimer = null;
const cleanups = [];
function runCleanups() { clearInterval(shotTimer); while (cleanups.length) cleanups.pop()(); }

function openDrawer(id, tab) {
  closeDrawer();
  S.open = id; S.tab = tab || S.tab || "remote"; S.drawerUsable = usable(byId(id));
  const scrim = h("div", { class: "scrim", id: "scrim", onclick: closeDrawer });
  const drawer = h("aside", { class: "drawer", id: "drawer", role: "dialog", "aria-label": "Device details" },
    h("div", { class: "drawer-head", id: "dhead" }),
    h("div", { class: "tabs", role: "tablist", id: "dtabs" }),
    h("div", { class: "drawer-body", id: "dbody" }));
  document.body.append(scrim, drawer);
  document.addEventListener("keydown", drawerKeys);
  updateDrawerHead(); renderTabs(); renderTab();
}
function closeDrawer() {
  runCleanups(); S.open = null;
  document.removeEventListener("keydown", drawerKeys);
  $("#scrim")?.remove(); $("#drawer")?.remove();
}
function drawerKeys(e) { if (e.key === "Escape" && !$(".modal")) closeDrawer(); }

function updateDrawerHead() {
  const d = byId(S.open), head = $("#dhead"); if (!d || !head) return;
  head.replaceChildren(h("div", { class: "grow" }, h("h2", null, d.name), h("div", { class: "muted mono" }, d.addr + (d.group ? " · " + d.group : ""))),
    statusEl(d), h("button", { class: "icon-btn", onclick: closeDrawer, "aria-label": "Close" }, ic("close")));
  // when the TV drops off or comes back, redraw the tab so it never shows stale or dead controls
  const u = usable(d);
  if (u !== S.drawerUsable) { S.drawerUsable = u; if (S.tab !== "settings") { runCleanups(); renderTab(); } }
}
function renderTabs() {
  $("#dtabs").replaceChildren(...TABS.map(([k, l]) => h("button", { role: "tab", "aria-selected": String(S.tab === k),
    onclick: () => { S.tab = k; runCleanups(); renderTabs(); renderTab(); } }, l)));
}
function renderTab() {
  const d = byId(S.open); if (!d) return;
  const body = $("#dbody"); body.replaceChildren();
  ({ remote: tabRemote, screen: tabScreen, inputs: tabInputs, apps: tabApps, install: tabInstall, shell: tabShell, info: tabInfo, settings: tabSettings })[S.tab](body, d);
}

async function sendKey(id, key) {
  try { const r = await act(id, "key", { key }); if (!r.ok) toast("Key failed: " + r.output, true); } catch (e) { toast(e.message, true); }
}

/* arrows / Enter / Backspace / H drive the TV while the switch is on; removed when the tab goes away */
function keyboardControl(d, kb) {
  const keymap = { ArrowUp: "KEYCODE_DPAD_UP", ArrowDown: "KEYCODE_DPAD_DOWN", ArrowLeft: "KEYCODE_DPAD_LEFT", ArrowRight: "KEYCODE_DPAD_RIGHT", Enter: "KEYCODE_DPAD_CENTER", Backspace: "KEYCODE_BACK", h: "KEYCODE_HOME" };
  const onKey = e => { if (!kb.checked || !$("#drawer") || ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName) && document.activeElement !== kb) return;
    if (keymap[e.key]) { e.preventDefault(); e.stopPropagation(); sendKey(d.id, keymap[e.key]); } };
  document.addEventListener("keydown", onKey, true);
  cleanups.push(() => document.removeEventListener("keydown", onKey, true));
}

function tabRemote(body, d) {
  if (!usable(d)) return body.append(unavailable(d, "The remote"));
  const k = (kids, key, label, cls) => h("button", { class: "btn" + (cls ? " " + cls : ""), title: key.replace("KEYCODE_", ""), "aria-label": label,
    onclick: () => sendKey(d.id, key) }, kids);
  const blank = () => h("span");
  const kb = h("input", { type: "checkbox", class: "switch", role: "switch", id: "kbctl", "aria-label": "Use keyboard" });
  keyboardControl(d, kb);
  const power = (label, action, msg, cls) => h("button", { class: "btn small" + (cls ? " " + cls : ""), onclick: async () => {
    if (action === "reboot" && !confirm("Reboot " + d.name + "?")) return;
    const r = await act(d.id, action); toast(r.ok ? msg : r.output, !r.ok); } }, ic("power"), label);

  if (d.status === "asleep") body.append(h("div", { class: "note" }, ic("power"), h("span", { class: "grow" }, "This TV is in standby."),
    h("button", { class: "btn small", onclick: async () => { const r = await act(d.id, "wake"); toast(r.ok ? "Wake sent" : r.output, !r.ok); } }, "Wake it")));
  body.append(h("div", { class: "panel" }, h("div", { class: "remote" },
    h("div", { class: "remote-left" },
      h("div", { class: "pad-row" },
        h("div", { class: "pad", role: "group", "aria-label": "Directional pad" },
          blank(), k(ic("up"), "KEYCODE_DPAD_UP", "Up"), blank(),
          k(ic("left"), "KEYCODE_DPAD_LEFT", "Left"), k("OK", "KEYCODE_DPAD_CENTER", "OK", "ok"), k(ic("right"), "KEYCODE_DPAD_RIGHT", "Right"),
          blank(), k(ic("down"), "KEYCODE_DPAD_DOWN", "Down"), blank()),
        h("div", { class: "vol", role: "group", "aria-label": "Volume" },
          k(ic("add"), "KEYCODE_VOLUME_UP", "Volume up"), k(ic("volume_off"), "KEYCODE_VOLUME_MUTE", "Mute"), k(ic("remove"), "KEYCODE_VOLUME_DOWN", "Volume down"))),
      h("div", { class: "btn-group" },
        k([ic("back"), "Back"], "KEYCODE_BACK", "Back", "small"), k([ic("home"), "Home"], "KEYCODE_HOME", "Home", "small"), k([ic("menu"), "Menu"], "KEYCODE_MENU", "Menu", "small")),
      h("div", { class: "btn-group" },
        k([ic("info"), "Info"], "KEYCODE_INFO", "Info", "small"), k([ic("input"), "Input"], "KEYCODE_TV_INPUT", "Input", "small")),
      h("div", { class: "btn-group" },
        k(ic("rewind"), "KEYCODE_MEDIA_REWIND", "Rewind", "small"), k(ic("play"), "KEYCODE_MEDIA_PLAY_PAUSE", "Play/Pause", "small"), k(ic("ff"), "KEYCODE_MEDIA_FAST_FORWARD", "Fast forward", "small")),
      h("div", { class: "btn-group" }, power("Wake", "wake", "Wake sent"), power("Standby", "sleep", "Standby sent"), power("Reboot", "reboot", "Rebooting…", "danger")),
      h("label", { class: "row", for: "kbctl", style: "width:100%" }, h("span", { class: "grow" }, "Use keyboard",
        h("span", { class: "sub", style: "display:block" }, "Arrows, Enter, Backspace = Back, H = Home")), kb)),
    h("div", { class: "watch-card" }, h("div", { class: "empty-ic" }, ic("tv")), h("h3", null, "See the screen"),
      h("p", { class: "muted" }, "Watch what this TV is showing, live, while you use the remote."),
      h("button", { class: "btn primary", onclick: () => { S.tab = "screen"; runCleanups(); renderTabs(); renderTab(); } }, ic("play"), "Open screen view")))));
}

const QUALITY = [["low", "Low · 480p"], ["medium", "Medium · 720p"], ["high", "High · 1080p"]];
const concatBytes = (a, b) => { if (!a.length) return b; const o = new Uint8Array(a.length + b.length); o.set(a); o.set(b, a.length); return o; };
function findHeaderEnd(b, from) { for (let i = from; i + 3 < b.length; i++) if (b[i] === 13 && b[i + 1] === 10 && b[i + 2] === 13 && b[i + 3] === 10) return i; return -1; }

/* Live view: the server sends multipart JPEG frames; we parse them here (rather than using <img>) so errors can be shown. */
function tabScreen(body, d) {
  if (!usable(d)) return body.append(unavailable(d, "The screen view"));
  const img = h("img", { class: "live-img hidden", alt: "Live view of " + d.name });
  const overlay = h("div", { class: "viewer-overlay" });
  const badge = h("div", { class: "live-badge hidden" }, h("i"), h("span", null, "LIVE"));
  const viewer = h("div", { class: "viewer" }, img, overlay, badge);
  const quality = h("select", { "aria-label": "Quality", onchange: () => { prefs.set("tvm-quality", quality.value); if (ctrl) start(); } },
    QUALITY.map(([v, l]) => h("option", { value: v, selected: v === prefs.get("tvm-quality", "medium") }, l)));
  const toggle = h("button", { class: "btn primary", onclick: () => ctrl ? stop() : start() });
  let ctrl = null, userStopped = false, frameUrl = null, count = 0;
  const fpsTimer = setInterval(() => { if (ctrl) badge.lastChild.textContent = `LIVE · ${count} fps`; count = 0; }, 1000);
  cleanups.push(() => { userStopped = true; if (ctrl) ctrl.abort(); ctrl = null; clearInterval(fpsTimer); if (frameUrl) URL.revokeObjectURL(frameUrl); });

  function ui(state, text) {
    overlay.classList.toggle("hidden", state === "live");
    badge.classList.toggle("hidden", state !== "live");
    toggle.replaceChildren(...(state === "live" ? [ic("close"), "Stop"] : state === "connecting" ? [ic("close"), "Cancel"] : [ic("play"), "Start live view"]));
    if (state === "connecting") overlay.replaceChildren(h("div", { class: "spinner", role: "status", "aria-label": "Connecting" }), h("p", null, "Connecting to the TV…"));
    else if (state === "error" || state === "ended") overlay.replaceChildren(h("div", { class: "empty-ic" }, ic(state === "error" ? "error" : "info")), h("p", { class: "viewer-msg" }, text),
      /^No video/.test(text || "") ? h("p", { class: "viewer-sub" }, "Some TVs don't allow screen capture. It depends on the TV's firmware, and video from HDMI inputs is usually blocked.") : null,
      h("button", { class: "btn", onclick: start }, ic("refresh"), state === "error" ? "Try again" : "Resume"));
    else if (state === "idle") overlay.replaceChildren(h("button", { class: "big-play", "aria-label": "Start live view", onclick: start }, ic("play")),
      h("p", { class: "viewer-msg" }, "Watch what this TV is showing"), h("p", { class: "viewer-sub" }, "Shows the TV's interface and apps. Video from an HDMI input is usually not capturable."));
  }
  function show(blob) {
    const u = URL.createObjectURL(blob), old = frameUrl; frameUrl = u;
    img.src = u; img.classList.remove("hidden"); count++;
    if (old) setTimeout(() => URL.revokeObjectURL(old), 500);
  }
  function drain(buf) {                 // show the newest complete frame in the buffer; return the leftover bytes
    let last = null, pos = 0;
    for (;;) {
      const he = findHeaderEnd(buf, pos); if (he < 0) break;
      const m = /content-length:\s*(\d+)/i.exec(new TextDecoder().decode(buf.subarray(pos, he)));
      if (!m) { pos = he + 4; continue; }
      const n = +m[1], from = he + 4;
      if (buf.length < from + n) break;
      last = buf.subarray(from, from + n); pos = from + n;
    }
    if (last) show(new Blob([last], { type: "image/jpeg" }));
    return pos ? buf.slice(pos) : buf;
  }
  /* Fallback for browsers that cannot stream a fetch() body: let an <img> read the multipart stream itself. */
  function startWithImg() {
    const mine = ctrl = new AbortController();
    mine.signal.addEventListener("abort", () => img.removeAttribute("src"));           // dropping the src closes the connection
    img.onload = () => { if (ctrl === mine) { img.classList.remove("hidden"); ui("live"); count++; } };
    img.onerror = () => { if (ctrl === mine) { ctrl = null; img.classList.add("hidden"); ui("error", "Couldn't start the live view. The TV may be unreachable or not allow screen capture."); } };
    img.src = `/api/devices/${d.id}/live?quality=${quality.value}&t=${Date.now()}`;
  }
  async function start() {
    if (ctrl) ctrl.abort();
    userStopped = false; const mine = ctrl = new AbortController(); count = 0;
    ui("connecting");
    try {
      const r = await fetch(`/api/devices/${d.id}/live?quality=${quality.value}&raw=1`, { credentials: "same-origin", signal: mine.signal });
      if (!r.ok) { let m = "HTTP " + r.status; try { m = (await r.json()).error || m; } catch (e) { /* not json */ } throw new Error(cap(m)); }
      if (!r.body || !r.body.getReader) return startWithImg();                          // e.g. older Safari
      ui("live");
      const reader = r.body.getReader(); let buf = new Uint8Array(0);
      for (;;) { const { done, value } = await reader.read(); if (done) break; buf = drain(concatBytes(buf, value)); }
      if (ctrl === mine && !userStopped) { ctrl = null; ui("ended", "The live view stopped. It ends by itself after 30 minutes."); }
    } catch (e) {
      if (mine.signal.aborted) return;
      ctrl = null; ui("error", /^(Failed to fetch|Load failed|NetworkError)/i.test(e.message) ? "Lost the connection to the manager." : e.message);
    }
  }
  function stop() { userStopped = true; if (ctrl) ctrl.abort(); ctrl = null; img.classList.add("hidden"); ui("idle"); }
  const snapshot = () => {
    if (!img.naturalWidth || img.classList.contains("hidden")) return toast("Start the live view first", true);
    const c = document.createElement("canvas"); c.width = img.naturalWidth; c.height = img.naturalHeight; c.getContext("2d").drawImage(img, 0, 0);
    c.toBlob(b => { const a = h("a", { href: URL.createObjectURL(b), download: `${d.name}-${new Date().toISOString().replace(/[:.]/g, "-")}.jpg` });
      document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); }, "image/jpeg", 0.92);
  };

  const k = (kids, key, label, cls) => h("button", { class: "btn small" + (cls ? " " + cls : ""), title: key.replace("KEYCODE_", ""), "aria-label": label, onclick: () => sendKey(d.id, key) }, kids);
  const kb = h("input", { type: "checkbox", class: "switch", role: "switch", id: "kbscreen", "aria-label": "Use keyboard" });
  keyboardControl(d, kb);
  ui("idle");
  body.append(d.input_name ? h("div", { class: "note" }, ic("info"), h("span", { class: "grow" }, `This TV is showing the HDMI input “${d.input_name}”. TVs don't allow its video to be captured, so the view will be black. The interface and apps can be viewed.`)) : null,
    h("div", { class: "panel" }, viewer,
    h("div", { class: "viewer-tools" }, toggle, selectField(quality, true),
      h("button", { class: "icon-btn", "aria-label": "Save snapshot", title: "Save snapshot", onclick: snapshot }, ic("camera")),
      h("button", { class: "icon-btn", "aria-label": "Fullscreen", title: "Fullscreen", onclick: () => viewer.requestFullscreen && viewer.requestFullscreen() }, ic("fullscreen"))),
    h("div", { class: "mini-remote" },
      h("div", { class: "btn-group" }, k([ic("back"), "Back"], "KEYCODE_BACK", "Back"), k(ic("left"), "KEYCODE_DPAD_LEFT", "Left"), k(ic("up"), "KEYCODE_DPAD_UP", "Up"),
        k(ic("down"), "KEYCODE_DPAD_DOWN", "Down"), k(ic("right"), "KEYCODE_DPAD_RIGHT", "Right"), k("OK", "KEYCODE_DPAD_CENTER", "OK", "primary"), k([ic("home"), "Home"], "KEYCODE_HOME", "Home")),
      h("label", { class: "row", for: "kbscreen" }, h("span", { class: "grow" }, "Use keyboard", h("span", { class: "sub", style: "display:block" }, "Arrows, Enter, Backspace = Back, H = Home")), kb))));
}

const STATE_CHIP = { connected: ["Device on", "ok"], standby: ["Device in standby", ""], disconnected: ["Nothing connected", ""], unknown: ["", ""] };

async function tabInputs(body, d) {
  const box = h("div", { class: "panel" }, h("h3", null, "TV inputs"));
  const restore = h("div", { class: "panel" });
  body.append(box, restore);
  const drawRestore = dev => restore.replaceChildren(h("h3", null, "Power-on behaviour"),
    h("p", { class: "muted", style: "margin-bottom:8px" }, "When this TV wakes or boots to the launcher, return it to the last HDMI input it was using."),
    h("label", { class: "row" }, h("span", { class: "grow" }, "Restore last input on power-on"), h("input", { type: "checkbox", class: "switch", role: "switch", checked: dev.restore.enabled, "aria-label": "Restore last input on power-on",
      onchange: async e => { try { await api("PUT", "/api/devices/" + d.id, { restore: { enabled: e.target.checked } }); await loadDevices(); toast("Saved"); } catch (x) { toast(x.message, true); } } })),
    h("div", { class: "row" }, h("div", { class: "grow" }, h("div", { style: "font-weight:700" }, dev.restore.last ? (dev.restore.last_name || "Remembered input") : "Nothing remembered yet"),
        h("div", { class: "sub" + (dev.restore.last ? " mono trunc" : ""), title: dev.restore.last || "" }, dev.restore.last ? shortInputId(dev.restore.last) : "It's recorded automatically while the TV is on an HDMI input.")),
      h("button", { class: "btn small", disabled: !dev.restore.last || !usable(byId(d.id)), onclick: async () => { const r = await act(d.id, "restore"); toast(r.ok ? "Restoring…" : r.output, !r.ok); if (r.ok) settle(); } }, "Restore now"),
      h("button", { class: "btn small", disabled: !dev.restore.last, onclick: async () => { await api("PUT", "/api/devices/" + d.id, { restore: { last: null } }); await loadDevices(); drawRestore(byId(d.id)); loadInputs(); } }, "Forget")));
  drawRestore(d);
  const loadInputs = async () => {
    if (!usable(byId(d.id))) return box.replaceChildren(h("h3", null, "TV inputs"), unavailable(byId(d.id) || d, "Inputs"));
    try {
      const { inputs } = await api("GET", `/api/devices/${d.id}/inputs`);
      const dev = byId(d.id) || d;
      const rows = inputs.filter(i => i.passthrough).concat(inputs.filter(i => !i.passthrough)).map(i => {
        const isPo = i.id === dev.restore.last, [stateText, stateCls] = STATE_CHIP[i.state] || ["", ""];
        return h("div", { class: "row input-row" }, h("div", { class: "ic-tile" }, ic("input")),
          h("div", { class: "grow" }, h("div", { class: "name" }, i.name, i.active ? h("span", { class: "badge active" }, "Active") : null, isPo ? h("span", { class: "badge" }, "Power-on") : null,
              stateText ? h("span", { class: "chip-s " + stateCls }, stateText) : null),
            h("div", { class: "sub mono trunc", title: i.id }, shortInputId(i.id))),
          i.passthrough ? h("div", { class: "actions" },
            i.active ? null : h("button", { class: "btn small primary", onclick: async () => { const r = await act(d.id, "input", { input: i.id }); toast(r.ok ? "Switching to " + i.name : r.output, !r.ok); if (r.ok) settle(); } }, "Switch"),
            isPo ? null : h("button", { class: "btn small", title: "Use as the input to restore on power-on", onclick: async () => { await api("PUT", "/api/devices/" + d.id, { restore: { last: i.id } }); await loadDevices(); drawRestore(byId(d.id)); loadInputs(); toast("Will restore " + i.name); } }, "Set as power-on")) : null);
      });
      box.replaceChildren(h("h3", null, "TV inputs"), inputs.length ? h("div", { class: "list" }, rows) : h("p", { class: "muted" }, "No inputs reported. Is the TV on?"));
    } catch (e) { box.replaceChildren(h("h3", null, "TV inputs"), h("p", { class: "err" }, cap(e.message))); }
  };
  // after a switch, give the TV a moment, then refresh the active badge and the remembered input
  const settle = () => setTimeout(async () => { if (S.open !== d.id || S.tab !== "inputs") return; await loadDevices(); drawRestore(byId(d.id)); loadInputs(); }, 2500);
  loadInputs();
}

async function tabApps(body, d) {
  if (!usable(d)) return body.append(unavailable(d, "Apps"));
  let filter = "user", q = "", pkgs = [];
  const list = h("div", { class: "list" }), count = h("div", { class: "count" });
  const draw = () => {
    const shown = pkgs.filter(p => (p.name + " " + appName(p.name)).toLowerCase().includes(q.toLowerCase()));
    count.textContent = shown.length + (shown.length === 1 ? " app" : " apps") + (shown.length > 400 ? " (showing 400)" : "");
    const rows = shown.slice(0, 400).map(p => {
      const run = (a, msg) => async () => {
        try { const r = await api("POST", `/api/devices/${d.id}/packages/${p.name}`, { action: a }); toast(r.ok ? msg : (r.output || "Failed"), !r.ok); if (r.ok && ["enable", "disable", "uninstall"].includes(a)) load(); }
        catch (e) { toast(e.message, true); } };
      const label = appName(p.name);
      const clear = ["Clear data", () => confirm("Clear all data for " + label + "?") && run("clear", "Data cleared")()];
      const remove = ["Uninstall", () => confirm("Uninstall " + label + " for the user?") && run("uninstall", "Uninstalled")(), true];
      return h("div", { class: "row app-row" }, h("div", { class: "ic-tile", "aria-hidden": "true" }, label.charAt(0).toUpperCase() || "?"),
        h("div", { class: "grow" }, h("div", { class: "name" }, label, p.disabled ? h("span", { class: "chip-s warn" }, "Disabled") : null),
          h("div", { class: "sub mono trunc", title: p.name }, p.name)),
        h("div", { class: "actions" },
          p.disabled ? h("button", { class: "btn small primary", onclick: run("enable", "Enabled") }, "Enable")
            : [h("button", { class: "btn small", onclick: run("launch", "Launched") }, "Open"), h("button", { class: "btn small", onclick: run("disable", "Disabled") }, "Disable")],
          menu(p.disabled ? [clear, remove] : [["Force stop", run("stop", "Stopped")], clear, remove], "More actions for " + label)));
    });
    list.replaceChildren(...(rows.length ? rows : [h("p", { class: "muted", style: "padding:12px 8px" }, "No apps in this view.")]));
  };
  const load = async () => {
    list.replaceChildren(h("p", { class: "muted", style: "padding:12px 8px" }, "Loading…"));
    try { pkgs = (await api("GET", `/api/devices/${d.id}/packages?filter=${filter}`)).packages; draw(); } catch (e) { count.textContent = ""; list.replaceChildren(h("p", { class: "err", style: "padding:12px 8px" }, cap(e.message))); }
  };
  const sel = h("select", { "aria-label": "Package filter", onchange: e => { filter = e.target.value; load(); } },
    ...[["user", "Installed apps"], ["disabled", "Disabled"], ["system", "System"], ["all", "Everything"]].map(([v, l]) => h("option", { value: v }, l)));
  body.append(h("div", { class: "panel" }, h("div", { class: "apps-tools" }, selectField(sel, true),
    h("input", { type: "text", placeholder: "Search apps", "aria-label": "Filter packages", autocomplete: "off", oninput: e => { q = e.target.value; draw(); } }),
    h("button", { class: "icon-btn", onclick: load, "aria-label": "Reload", title: "Reload" }, ic("refresh"))), count, list));
  load();
}

function tabInstall(body, d) {
  if (!usable(d)) return body.append(unavailable(d, "Installing apps"));
  const out = h("pre", { class: "out hidden" }); const prog = h("div", { class: "bar hidden", style: "margin-top:14px" }, h("i", { style: "width:0" }));
  const result = h("div");
  const file = h("input", { type: "file", accept: ".apk,application/vnd.android.package-archive", id: "apkf", class: "visually-hidden" });
  const dzText = h("div"), dz = h("label", { class: "dropzone", for: "apkf" }, ic("upload"), dzText);
  const go = h("button", { class: "btn primary", disabled: true, style: "margin-top:14px" }, "Upload & install");
  const showFile = () => {
    const f = file.files[0];
    dzText.replaceChildren(...(f ? [h("strong", null, f.name), h("div", null, fmtBytes(f.size) + " · click to choose a different file")]
      : [h("strong", null, "Drop an APK here"), h("div", null, "or click to choose a file")]));
    go.disabled = !f;
  };
  file.addEventListener("change", showFile); showFile();
  ["dragenter", "dragover"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove("drag"); }));
  dz.addEventListener("drop", e => { if (e.dataTransfer.files.length) { file.files = e.dataTransfer.files; showFile(); } });
  go.addEventListener("click", () => {
    const f = file.files[0]; if (!f) return;
    const x = new XMLHttpRequest(); x.open("POST", `/api/devices/${d.id}/install?name=${encodeURIComponent(f.name)}`);
    x.setRequestHeader("X-Requested-With", "tvm"); x.setRequestHeader("Content-Type", "application/octet-stream");
    prog.classList.remove("hidden"); out.classList.add("hidden"); result.replaceChildren(); go.disabled = true;
    x.upload.onprogress = e => { if (e.lengthComputable) prog.firstChild.style.width = (100 * e.loaded / e.total) + "%"; };
    x.onload = () => { go.disabled = false; prog.classList.add("hidden"); let r = {}; try { r = JSON.parse(x.responseText); } catch (e) { /* not json */ }
      result.replaceChildren(h("div", { class: "banner " + (r.ok ? "ok" : "bad"), role: "status" }, ic(r.ok ? "done" : "error"), r.ok ? `Installed ${f.name}` : "Install failed"));
      out.textContent = r.output || r.error || "No output"; out.classList.remove("hidden"); toast(r.ok ? "Installed " + f.name : "Install failed", !r.ok); };
    x.onerror = () => { go.disabled = false; prog.classList.add("hidden"); toast("Upload failed", true); };
    x.send(f);
  });
  body.append(h("div", { class: "panel" }, h("h3", null, "Install an APK"), file, dz,
    h("p", { class: "muted", style: "font-size:13px;margin-top:10px" }, "Installed with adb install -r, so an existing app is updated in place and keeps its data."),
    go, prog, result, out));
}

function tabShell(body, d) {
  if (!usable(d)) return body.append(unavailable(d, "The shell"));
  const out = h("pre", { class: "out" }, "Commands run through `adb shell` on " + d.name + ".");
  const inp = h("input", { type: "text", class: "mono", placeholder: "e.g. getprop ro.build.version.release", "aria-label": "Shell command", autocomplete: "off", spellcheck: "false" });
  const hist = JSON.parse(sessionStorage.getItem("tvm-hist") || "[]"); let hi = hist.length;
  const log = [];
  const show = () => { out.textContent = log.join("\n\n"); out.scrollTop = out.scrollHeight; };
  const run = async cmd => {
    if (!cmd.trim()) return;
    hist.push(cmd); hi = hist.length; sessionStorage.setItem("tvm-hist", JSON.stringify(hist.slice(-50)));
    const i = log.push("$ " + cmd + "\n…") - 1; show();
    try { const r = await api("POST", `/api/devices/${d.id}/shell`, { cmd }); log[i] = "$ " + cmd + "\n" + (r.output.trimEnd() || "(no output)") + (r.rc ? `\n[exit ${r.rc}]` : ""); }
    catch (e) { log[i] = "$ " + cmd + "\n" + e.message; }
    if (log.length > 30) log.shift();
    show();
  };
  const submit = () => { run(inp.value); inp.value = ""; };
  inp.addEventListener("keydown", e => {
    if (e.key === "Enter") submit();
    else if (e.key === "ArrowUp" && hi > 0) { inp.value = hist[--hi]; e.preventDefault(); }
    else if (e.key === "ArrowDown") { inp.value = hi < hist.length - 1 ? hist[++hi] : ""; hi = Math.min(hi, hist.length); e.preventDefault(); } });
  const quick = [["Disabled packages", "pm list packages -d"], ["Current focus", "dumpsys window | grep mCurrentFocus"], ["Wakefulness", "dumpsys power | grep mWakefulness="], ["Storage", "df -h /data"], ["Uptime", "uptime"]];
  body.append(h("div", { class: "panel" }, h("div", { class: "shell-row" }, inp, h("button", { class: "btn primary", onclick: submit }, "Run")),
    h("div", { class: "chips", style: "margin-top:12px" }, quick.map(([l, c]) => h("button", { class: "chip", onclick: () => run(c) }, l))),
    h("div", { class: "shell-head" }, h("h3", null, "Output"), h("button", { class: "btn text small", onclick: () => { log.length = 0; out.textContent = ""; } }, "Clear")), out));
  inp.focus();
}

const PROP_LABELS = { "product.manufacturer": "Manufacturer", "product.model": "Model", "product.device": "Device", "build.version.release": "Android version",
  "build.version.sdk": "API level", "build.version.security_patch": "Security patch", "build.fingerprint": "Build", "serialno": "Serial number", "boot.hardware": "Hardware", "persist.sys.timezone": "Time zone" };

async function tabInfo(body, d) {
  if (!usable(d)) return body.append(unavailable(d, "Device info"));
  const box = h("div", { class: "panel" }, h("p", { class: "muted" }, "Loading…")); body.append(box);
  try {
    const i = await api("GET", `/api/devices/${d.id}/info`);
    const up = i.uptime_s != null ? (i.uptime_s >= 86400 ? Math.floor(i.uptime_s / 86400) + "d " : "") + Math.floor(i.uptime_s % 86400 / 3600) + "h " + Math.floor(i.uptime_s % 3600 / 60) + "m" : "–";
    const rows = [["Address", d.addr], ["IP on device", i.ip || "–"], ["Uptime", up],
      ...Object.entries(i.props).map(([k, v]) => { const key = k.replace(/^ro\./, ""); return [PROP_LABELS[key] || key, v]; })];
    const meter = (label, used, total) => total ? h("div", { class: "meter" }, h("div", { class: "row" }, h("span", { class: "grow", style: "font-weight:700" }, label),
        h("span", { class: "muted" }, `${fmtKb(used)} of ${fmtKb(total)} · ${Math.round(100 * used / total)}%`)),
      h("div", { class: "bar", role: "img", "aria-label": `${label} ${Math.round(100 * used / total)}% used` }, h("i", { style: `width:${100 * used / total}%` }))) : null;
    box.replaceChildren(meter("Storage (/data)", i.storage_kb && i.storage_kb.used, i.storage_kb && i.storage_kb.total),
      i.memory_kb && i.memory_kb.total ? meter("Memory", i.memory_kb.total - i.memory_kb.available, i.memory_kb.total) : null,
      h("table", { class: "kv" }, h("tbody", null, rows.map(([k, v]) => h("tr", null, h("th", { scope: "row" }, k), h("td", { class: "mono" }, v))))));
  } catch (e) { box.replaceChildren(h("p", { class: "err" }, cap(e.message))); }
}

function tabSettings(body, d) {
  const name = h("input", { type: "text", id: "sn", value: d.name }), addr = h("input", { type: "text", id: "sa", value: d.addr }),
    group = h("input", { type: "text", id: "sg", value: d.group, list: "grps2", placeholder: "Optional" }),
    mac = h("input", { type: "text", id: "sm", value: d.mac || "", placeholder: "aa:bb:cc:dd:ee:ff", autocomplete: "off", spellcheck: "false" });
  body.append(h("div", { class: "panel" }, h("h3", null, "Device"),
    h("div", { class: "field" }, h("label", { for: "sn" }, "Name"), name,
      d.auto_name ? h("span", { class: "hint" }, d.tv_name ? "Using the name set on the TV. Type a name here to use your own instead." : "Will use the name set on the TV once it connects.")
        : d.tv_name ? h("span", { class: "hint" }, `Name on the TV: ${d.tv_name} `, h("button", { class: "btn text small", type: "button", onclick: async () => {
            try { await api("PUT", "/api/devices/" + d.id, { auto_name: true }); await loadDevices(); updateDrawerHead(); renderTab(); toast("Using the TV's name"); } catch (e) { toast(e.message, true); } } }, "Use it")) : null),
    h("div", { class: "field" }, h("label", { for: "sa" }, "Address"), addr),
    h("div", { class: "field" }, h("label", { for: "sm" }, "MAC address (for Wake-on-LAN)"), mac,
      h("span", { class: "hint" }, d.mac ? (d.mac_auto ? "Learned from the TV. " : "") + "Used to wake the TV over the network when it is fully off. Wi-Fi-only TVs often can't be woken this way; a TV on Ethernet usually can."
        : "Learned automatically while the TV is on. You can also type it here.")),
    h("div", { class: "field" }, h("label", { for: "sg" }, "Group"), group, h("datalist", { id: "grps2" }, S.groups.map(g => h("option", { value: g })))),
    h("div", { class: "keys" },
      h("button", { class: "btn primary", onclick: async () => { try { await api("PUT", "/api/devices/" + d.id, { name: name.value, addr: addr.value, group: group.value, mac: mac.value }); await loadDevices(); updateDrawerHead(); renderTab(); toast("Saved"); } catch (e) { toast(e.message, true); } } }, "Save"),
      h("button", { class: "btn", onclick: async () => { const r = await act(d.id, "connect"); toast(r.output || (r.ok ? "Connected" : "Failed"), !r.ok); } }, ic("refresh"), "Reconnect ADB"))),
    h("div", { class: "panel" }, h("h3", null, "Remove"), h("p", { class: "muted", style: "margin-bottom:12px" }, "Removes this TV from the manager. Nothing on the TV changes."),
      h("button", { class: "btn danger", onclick: async () => { if (confirm("Remove " + d.name + " from the manager?")) { await api("DELETE", "/api/devices/" + d.id); closeDrawer(); S.selected.delete(d.id); toast("Removed"); refresh(); } } }, "Remove device")));
}

/* ---------- schedules ---------- */
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const ACTION_LABEL = { wake: "Wake", wol: "Wake over network", sleep: "Standby", reboot: "Reboot", home: "Go Home", input: "Switch input" };
function fmtTime(t) {
  const [hh, mm] = t.split(":").map(Number), full = new Date(2000, 0, 1, hh, mm).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const m = /\s?(AM|PM)$/i.exec(full);
  return [full.replace(/\s?(AM|PM)$/i, ""), m ? m[1].toUpperCase() : ""];
}

async function renderSchedules() {
  const main = $("#main"); if (!main || S.view !== "schedules") return;
  const { schedules } = await api("GET", "/api/schedules");
  const name = id => (byId(id) || { name: "(removed)" }).name;
  const head = h("div", { class: "page-head" }, h("h1", null, "Schedules"), h("p", { class: "sub" }, "Run power and input actions at set times. Times use the server's clock."));
  if (!schedules.length) {
    main.replaceChildren(head, emptyState("schedule", "No schedules yet", "Wake the lobby TVs at 7:30, put everything on standby at night, or switch an input on weekends.",
      h("button", { class: "btn primary", onclick: () => scheduleDialog() }, ic("add"), "New schedule")));
    return;
  }
  main.replaceChildren(head, h("div", { class: "sched-list" }, schedules.map(s => {
    const [t, ampm] = fmtTime(s.time), tg = s.targets.map(name);
    return h("div", { class: "sched" + (s.enabled ? "" : " paused") },
      h("div", { class: "sched-time" }, t, ampm ? h("small", null, ampm) : null),
      h("div", { class: "sched-body" }, h("div", { class: "sched-name" }, s.name, s.enabled ? null : h("span", { class: "chip-s", style: "margin-left:8px" }, "Paused")),
        h("div", { class: "sched-what" }, h("span", { class: "chip-s pri" }, ACTION_LABEL[s.action] + (s.input ? " → " + s.input.split("/").pop() : "")),
          ...tg.slice(0, 4).map(n => h("span", { class: "chip-s" }, n)), tg.length > 4 ? h("span", { class: "chip-s" }, "+" + (tg.length - 4)) : null),
        h("div", { class: "daydots", role: "img", "aria-label": s.days.length === 7 ? "Every day" : s.days.map(d => DAYS[d]).join(", ") },
          DAYS.map((l, i) => h("span", { class: s.days.includes(i) ? "on" : "" }, l.charAt(0))))),
      h("div", { class: "sched-ctl" },
        h("input", { type: "checkbox", class: "switch", role: "switch", checked: s.enabled, "aria-label": "Enabled", onchange: async e => { await api("PUT", "/api/schedules/" + s.id, { ...s, enabled: e.target.checked }); renderSchedules(); } }),
        h("button", { class: "icon-btn small", "aria-label": "Edit " + s.name, title: "Edit", onclick: () => scheduleDialog(s) }, ic("edit")),
        h("button", { class: "icon-btn small danger", "aria-label": "Delete " + s.name, title: "Delete", onclick: async () => { if (confirm("Delete schedule " + s.name + "?")) { await api("DELETE", "/api/schedules/" + s.id); renderSchedules(); } } }, ic("delete"))));
  })));
}

function scheduleDialog(s) {
  s = s || { name: "", action: "wake", time: "07:00", days: [0, 1, 2, 3, 4, 5, 6], targets: [], input: "", enabled: true };
  const name = h("input", { type: "text", id: "sn1", value: s.name, placeholder: "Morning on", autocomplete: "off" });
  const action = h("select", { id: "sa1", onchange: () => { inputField.classList.toggle("hidden", action.value !== "input"); if (action.value === "input") loadInputs(); } },
    ...Object.entries(ACTION_LABEL).map(([v, l]) => h("option", { value: v, selected: v === s.action }, l)));
  const time = h("input", { type: "time", id: "st1", value: s.time });
  const inp = h("input", { type: "text", id: "si1", value: s.input || "", placeholder: "Pick an input above, or paste a full input id", class: "mono" });
  const inputPick = h("select", { id: "si0", "aria-label": "Input", onchange: () => { if (inputPick.value) inp.value = inputPick.value; } }, h("option", { value: "" }, "Choose an input…"));
  const days = new Set(s.days), targets = new Set(s.targets);
  const allOn = () => S.devices.length > 0 && S.devices.every(x => targets.has(x.id));
  const toggleChip = (set, key) => e => { set.has(key) ? set.delete(key) : set.add(key); e.currentTarget.setAttribute("aria-pressed", String(set.has(key)));
    if (set === targets) { allChip.setAttribute("aria-pressed", String(allOn())); if (action.value === "input") loadInputs(); } };
  const dayChips = h("div", { class: "chips days" }, DAYS.map((l, i) => h("button", { type: "button", class: "chip", "aria-pressed": String(days.has(i)), onclick: toggleChip(days, i) }, l)));
  const devBtns = S.devices.map(d => h("button", { type: "button", class: "chip", "aria-pressed": String(targets.has(d.id)), onclick: toggleChip(targets, d.id) }, d.name));
  const allChip = h("button", { type: "button", class: "chip", "aria-pressed": String(allOn()),
    onclick: e => { const all = allOn(); S.devices.forEach(x => all ? targets.delete(x.id) : targets.add(x.id));
      devBtns.forEach((b, i) => b.setAttribute("aria-pressed", String(targets.has(S.devices[i].id)))); e.currentTarget.setAttribute("aria-pressed", String(!all)); if (action.value === "input") loadInputs(); } }, "All");
  const devChips = h("div", { class: "chips" }, allChip, devBtns);
  const err = h("p", { class: "err", role: "alert" });
  const inputField = h("div", { class: "field" + (s.action === "input" ? "" : " hidden") }, h("label", { for: "si0" }, "Input"), selectField(inputPick), h("span", { class: "hint" }, "Choices come from the first selected TV."),
    h("label", { for: "si1", style: "margin-top:8px" }, "Input id"), inp);
  async function loadInputs() {
    const first = [...targets][0]; if (!first) return;
    try {
      const { inputs } = await api("GET", `/api/devices/${first}/inputs`);
      inputPick.replaceChildren(h("option", { value: "" }, "Choose an input…"), ...inputs.filter(i => i.passthrough).map(i => h("option", { value: i.id, selected: i.id === inp.value }, i.name)));
    } catch (e) { /* TV offline: the manual id field still works */ }
  }
  if (s.action === "input") loadInputs();
  const m = modal(s.id ? "Edit schedule" : "New schedule", [
    h("div", { class: "field" }, h("label", { for: "sn1" }, "Name"), name),
    h("div", { class: "grid2" }, h("div", { class: "field" }, h("label", { for: "sa1" }, "Action"), selectField(action)),
      h("div", { class: "field" }, h("label", { for: "st1" }, "Time"), time)),
    inputField,
    h("div", { class: "field" }, h("label", null, "Days"), dayChips),
    h("div", { class: "field" }, h("label", null, "Devices"), devChips), err], [
    h("button", { class: "btn text", onclick: () => m.close() }, "Cancel"),
    h("button", { class: "btn primary", onclick: async () => {
      const body = { name: name.value, action: action.value, time: time.value, days: [...days], targets: [...targets], input: inp.value || null, enabled: s.enabled };
      try { await api(s.id ? "PUT" : "POST", "/api/schedules" + (s.id ? "/" + s.id : ""), body); m.close(); renderSchedules(); } catch (e) { err.textContent = e.message; } } }, "Save")]);
}

/* ---------- activity & settings ---------- */
const evIcon = e => e.level === "error" ? "error" : /^shell:/.test(e.msg) ? "terminal" : /install/.test(e.msg) ? "upload" : /schedule/.test(e.msg) ? "schedule"
  : /input|restor/.test(e.msg) ? "input" : /wake|woke|sleep|standby|reboot|offline|online|status/.test(e.msg) ? "power" : /added|removed/.test(e.msg) ? "tv" : "info";
function dayLabel(ts) {
  const d = new Date(ts * 1000), today = new Date(), yest = new Date(Date.now() - 864e5);
  const same = (a, b) => a.toDateString() === b.toDateString();
  return same(d, today) ? "Today" : same(d, yest) ? "Yesterday" : d.toLocaleDateString([], { weekday: "long", month: "short", day: "numeric" });
}

async function renderEvents() {
  const main = $("#main"); if (!main || S.view !== "events") return;
  const { events } = await api("GET", "/api/events");
  const sig = S.evFilter + "|" + events.length + "|" + (events[0] ? events[0].ts : 0);
  if (sig === S.evSig) return;            // nothing new: don't redraw (keeps scroll and focus)
  S.evSig = sig;
  const devices = [...new Set(events.map(e => e.device).filter(x => x && x !== "-"))];
  if (S.evFilter !== "all" && S.evFilter !== "errors" && !devices.includes(S.evFilter)) S.evFilter = "all";
  const shown = events.filter(e => S.evFilter === "all" || (S.evFilter === "errors" ? e.level === "error" : e.device === S.evFilter));
  const chip = (key, label) => h("button", { class: "chip", "aria-pressed": String(S.evFilter === key), onclick: () => { S.evFilter = key; S.evSig = ""; renderEvents(); } }, label);
  const groups = [];
  shown.forEach(e => { const l = dayLabel(e.ts); if (!groups.length || groups[groups.length - 1][0] !== l) groups.push([l, []]); groups[groups.length - 1][1].push(e); });
  const evRow = e => h("div", { class: "ev" + (e.level === "error" ? " bad" : "") }, h("div", { class: "ev-ic" }, ic(evIcon(e))),
    h("div", null, h("div", { class: "msg" }, cap(e.msg)), e.device && e.device !== "-" ? h("span", { class: "who" }, e.device) : null),
    h("time", { datetime: new Date(e.ts * 1000).toISOString() }, new Date(e.ts * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" })));
  main.replaceChildren(h("div", { class: "page-head" }, h("h1", null, "Activity"), h("p", { class: "sub" }, "Status changes, restores, schedule runs and every action taken here.")),
    events.length ? h("div", { class: "chips ev-filters", role: "group", "aria-label": "Filter activity" }, chip("all", "All"), chip("errors", "Errors"), devices.map(n => chip(n, n))) : null,
    ...(!events.length ? [emptyState("list", "No activity yet", "Status changes, input restores, schedule runs and actions you take will show up here.")]
      : !groups.length ? [emptyState("list", "Nothing here", "No activity matches this filter.", h("button", { class: "btn", onclick: () => { S.evFilter = "all"; S.evSig = ""; renderEvents(); } }, "Show all"))]
      : groups.flatMap(([label, evs]) => [h("div", { class: "ev-day" }, label), h("div", { class: "ev-list" }, evs.map(evRow))])));
}

function renderSettings() {
  const main = $("#main"); if (!main) return;
  const cur = h("input", { type: "password", id: "pc", autocomplete: "current-password" }), nw = h("input", { type: "password", id: "pn", autocomplete: "new-password" });
  const msg = h("p", { class: "err", role: "alert" });
  const upd = h("button", { class: "btn primary", disabled: true, onclick: async () => {
    try { await api("POST", "/api/password", { current: cur.value, new: nw.value }); cur.value = nw.value = ""; msg.textContent = ""; upd.disabled = true; toast("Password changed"); } catch (e) { msg.textContent = e.message; } } }, "Update password");
  const sync = () => { upd.disabled = !(cur.value && nw.value.length >= 8); };
  cur.addEventListener("input", sync); nw.addEventListener("input", sync);
  const mode = prefs.get("tvm-mode", "auto"), hue = parseInt(prefs.get("tvm-hue", "262"), 10);
  const setMode = m => { prefs.set("tvm-mode", m); applyTheme(); renderSettings(); };
  const setHue = v => { prefs.set("tvm-hue", String(v)); applyTheme(); renderSettings(); };
  const hueName = (HUES.find(([, v]) => v === hue) || ["Custom"])[0];
  main.replaceChildren(h("div", { class: "page-head" }, h("h1", null, "Settings")),
    h("div", { class: "settings-grid" },
      h("div", { class: "panel" }, h("h3", null, "Appearance"),
        h("div", { class: "field" }, h("label", null, "Theme"),
          h("div", { class: "btn-group", role: "group", "aria-label": "Theme" }, [["auto", "Auto"], ["light", "Light"], ["dark", "Dark"]].map(([m, l]) =>
            h("button", { class: "btn", "aria-pressed": String(mode === m), onclick: () => setMode(m) }, l)))),
        h("div", { class: "field", style: "margin-bottom:0" }, h("label", null, "Accent colour", h("span", { class: "swatch-name" }, hueName)),
          h("div", { class: "swatches", role: "group", "aria-label": "Accent colour" }, HUES.map(([n, v]) =>
            h("button", { class: "swatch", style: `--sw:${v}`, title: n, "aria-label": n, "aria-pressed": String(hue === v), onclick: () => setHue(v) }, ic("check")))))),
      h("div", { class: "panel" }, h("h3", null, "Change password"),
        h("div", { class: "field" }, h("label", { for: "pc" }, "Current password"), cur),
        h("div", { class: "field" }, h("label", { for: "pn" }, "New password"), nw, h("span", { class: "hint" }, "At least 8 characters.")),
        upd, msg),
      h("div", { class: "panel about" }, h("h3", null, "About"),
        h("p", { class: "muted" }, "TV Manager " + (S.version || "") + " manages Android TVs over ADB: remote, inputs, apps, schedules and power-on input restore."),
        h("p", { style: "margin-top:10px" }, h("a", { href: "https://github.com/douggreenak/tv-adb-manager", target: "_blank", rel: "noopener" }, "Documentation and source on GitHub")))));
}

start().catch(() => showLogin());
