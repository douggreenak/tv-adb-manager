"use strict";
/* TV Manager UI. All dynamic text is set via textContent, never innerHTML. */

const $ = (s, el = document) => el.querySelector(s);

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
  const t = h("div", { class: "toast" + (error ? " error" : "") }, msg);
  $("#toasts").append(t);
  setTimeout(() => t.remove(), error ? 6000 : 2600);
}

async function api(method, path, body) {
  const opt = { method, credentials: "same-origin", headers: { "X-Requested-With": "tvm" } };
  if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const r = await fetch(path, opt);
  if (r.status === 401 && path !== "/api/login") { showLogin(); throw new Error("login required"); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || ("HTTP " + r.status));
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
const STATUS_TEXT = { online: "On", asleep: "Standby", offline: "Offline", unauthorized: "Needs approval on TV", unknown: "Checking…" };
const shortApp = top => top ? top.split("/")[0] : "–";

const S = { devices: [], groups: [], selected: new Set(), view: "devices", filter: "", group: "", open: null, tab: "remote", timer: null };

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
  $("#app").replaceChildren(h("form", { class: "login", onsubmit: go },
    h("h2", { style: "margin-bottom:14px" }, "TV Manager"),
    h("div", { class: "field" }, h("label", { for: "pw" }, "Password"), pw),
    err, h("button", { class: "btn primary", style: "width:100%;margin-top:8px", type: "submit" }, "Sign in")));
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

function renderShell() {
  const nav = ["devices", "schedules", "events", "settings"].map(v =>
    h("button", { "aria-current": String(S.view === v), onclick: () => { S.view = v; renderShell(); refresh(); } },
      { devices: "Devices", schedules: "Schedules", events: "Activity", settings: "Settings" }[v]));
  $("#app").replaceChildren(
    h("header", { class: "topbar" },
      h("div", { class: "brand" }, "TV Manager"), h("nav", { class: "nav" }, nav),
      h("a", { class: "btn small appslink", href: `http://${location.hostname}:8090/apps`, title: "Services hub \u2014 all apps" },
        Object.assign(document.createElement("span"), { innerHTML: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M4 4h4v4H4zm6 0h4v4h-4zm6 0h4v4h-4zM4 10h4v4H4zm6 0h4v4h-4zm6 0h4v4h-4zM4 16h4v4H4zm6 0h4v4h-4zm6 0h4v4h-4z"/></svg>' }), "Apps"),
      h("button", { class: "btn small", onclick: async () => { await api("POST", "/api/logout"); showLogin(); } }, "Sign out")),
    h("main", { class: "main", id: "main" }));
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
  else if (S.view === "events") await renderEvents();
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
  const q = S.filter.toLowerCase();
  const list = S.devices.filter(d => (!S.group || d.group === S.group) &&
    (!q || [d.name, d.addr, d.model, d.group].some(x => (x || "").toLowerCase().includes(q))));
  const online = S.devices.filter(d => d.status === "online").length;
  const asleep = S.devices.filter(d => d.status === "asleep").length;
  const off = S.devices.length - online - asleep;

  // keep search box focus across live re-renders
  const prev = $("#search"); const keepFocus = prev && document.activeElement === prev; const caret = prev && prev.selectionStart;
  const search = h("input", { type: "text", id: "search", placeholder: "Search devices", value: S.filter, "aria-label": "Search devices",
    style: "max-width:240px", oninput: e => { S.filter = e.target.value; renderDevices(); } });

  const groupChips = S.groups.length ? h("div", { class: "chips", role: "group", "aria-label": "Filter by group" },
    h("button", { class: "chip", "aria-pressed": String(!S.group), onclick: () => { S.group = ""; renderDevices(); } }, "All"),
    S.groups.map(g => h("button", { class: "chip", "aria-pressed": String(S.group === g), onclick: () => { S.group = g; renderDevices(); } }, g))) : null;

  const sel = [...S.selected].filter(id => byId(id));
  const bulk = sel.length ? h("div", { class: "bulkbar" },
    h("strong", null, sel.length + " selected"),
    ...[["wake", "Wake"], ["sleep", "Standby"], ["home", "Home"], ["restore", "Restore input"]].map(([a, l]) =>
      h("button", { class: "btn small", onclick: () => bulk_(a, sel) }, l)),
    h("button", { class: "btn small danger", onclick: () => confirm("Reboot " + sel.length + " device(s)?") && bulk_("reboot", sel) }, "Reboot"),
    h("span", { class: "grow", style: "flex:1" }),
    h("button", { class: "btn small", onclick: () => { S.selected.clear(); renderDevices(); } }, "Clear")) : null;

  const cards = list.length ? h("div", { class: "grid" }, list.map(card)) :
    h("div", { class: "empty" }, S.devices.length ? "No devices match." : "No devices yet. Add a TV by its IP address to get started.");

  main.replaceChildren(
    h("div", { class: "toolbar" }, search, groupChips, h("span", { class: "grow" }),
      h("div", { class: "summary" }, h("span", null, online + " on"), h("span", null, asleep + " standby"), h("span", null, off + " offline")),
      h("button", { class: "btn", onclick: () => { const all = list.every(d => S.selected.has(d.id)); list.forEach(d => all ? S.selected.delete(d.id) : S.selected.add(d.id)); renderDevices(); } }, "Select all"),
      h("button", { class: "btn primary", onclick: addDeviceDialog }, "+ Add device")),
    ...(bulk ? [bulk] : []), cards);
  if (keepFocus) { const s = $("#search"); s.focus(); s.setSelectionRange(caret, caret); }
}

async function bulk_(action, ids) {
  try {
    const r = await api("POST", "/api/bulk", { action, ids });
    const bad = Object.values(r.results).filter(x => !x.ok).length;
    toast(bad ? `${action}: ${bad} failed` : `${action}: done on ${ids.length}`, !!bad);
  } catch (e) { toast(e.message, true); }
}

function card(d) {
  const sel = S.selected.has(d.id);
  const quick = (label, a) => h("button", { class: "btn small", onclick: async e => { e.stopPropagation(); try { const r = await act(d.id, a); toast(r.ok ? label + " sent" : "Failed: " + r.output, !r.ok); } catch (x) { toast(x.message, true); } } }, label);
  const open = () => openDrawer(d.id);
  return h("div", { class: "card" + (sel ? " selected" : ""), tabindex: "0", role: "button", "aria-label": "Open " + d.name,
      onclick: open, onkeydown: e => { if (e.key === "Enter" && e.target === e.currentTarget) open(); } },
    h("div", { class: "card-head" },
      h("input", { type: "checkbox", checked: sel, "aria-label": "Select " + d.name,
        onclick: e => e.stopPropagation(), onchange: e => { e.target.checked ? S.selected.add(d.id) : S.selected.delete(d.id); renderDevices(); } }),
      h("div", { class: "title" }, h("div", { class: "name" }, d.name), h("div", { class: "muted mono" }, d.addr)),
      statusEl(d)),
    h("dl", null,
      h("dt", null, "Model"), h("dd", null, [d.manufacturer, d.model].filter(Boolean).join(" ") || "–", d.android ? ` · Android ${d.android}` : ""),
      h("dt", null, "Input"), h("dd", null, d.input_name || (d.status === "online" ? "App / launcher" : "–")),
      h("dt", null, "Showing"), h("dd", { title: d.top || "" }, shortApp(d.top)),
      h("dt", null, "Last input"), h("dd", null, d.restore.last_name ? d.restore.last_name + (d.restore.enabled ? "" : " (restore off)") : "not yet recorded"),
      h("dt", null, "Seen"), h("dd", null, ago(d.last_seen))),
    h("div", { class: "card-actions" }, quick("Wake", "wake"), quick("Standby", "sleep"), quick("Home", "home"),
      d.group ? h("span", { class: "badge", style: "margin-left:auto;align-self:center" }, d.group) : null));
}

function modal(title, bodyEls, buttons) {
  const m = h("div", { class: "modal", role: "dialog", "aria-modal": "true", "aria-label": title },
    h("div", { class: "box" }, h("h2", null, title), bodyEls, h("div", { class: "actions" }, buttons)));
  m.close = () => { m.remove(); document.removeEventListener("keydown", esc_); };
  const esc_ = e => { if (e.key === "Escape") m.close(); };
  document.addEventListener("keydown", esc_);
  document.body.append(m);
  const first = m.querySelector("input,select"); if (first) first.focus();
  return m;
}

function addDeviceDialog() {
  const name = h("input", { type: "text", id: "an", placeholder: "Lobby TV" });
  const addr = h("input", { type: "text", id: "aa", placeholder: "192.168.1.50 (port defaults to 5555)" });
  const group = h("input", { type: "text", id: "ag", placeholder: "optional", list: "grps" });
  const err = h("p", { class: "err", role: "alert" });
  const m = modal("Add device", [
    h("div", { class: "field" }, h("label", { for: "an" }, "Name"), name),
    h("div", { class: "field" }, h("label", { for: "aa" }, "IP address"), addr),
    h("div", { class: "field" }, h("label", { for: "ag" }, "Group"), group, h("datalist", { id: "grps" }, S.groups.map(g => h("option", { value: g })))),
    h("p", { class: "muted" }, "Developer options → ADB debugging (network) must be on. The first connection asks you to approve this server on the TV screen."),
    err], [
    h("button", { class: "btn", onclick: () => m.close() }, "Cancel"),
    h("button", { class: "btn primary", onclick: async () => {
      try { await api("POST", "/api/devices", { name: name.value, addr: addr.value, group: group.value }); m.close(); toast("Device added"); refresh(); }
      catch (e) { err.textContent = e.message; } } }, "Add")]);
}

/* ---------- drawer ---------- */
const TABS = [["remote", "Remote"], ["inputs", "Inputs"], ["apps", "Apps"], ["install", "Install"], ["shell", "Shell"], ["info", "Info"], ["settings", "Settings"]];
let shotTimer = null;
const cleanups = [];
function runCleanups() { clearInterval(shotTimer); while (cleanups.length) cleanups.pop()(); }

function openDrawer(id, tab) {
  closeDrawer();
  S.open = id; S.tab = tab || S.tab || "remote";
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
    statusEl(d), h("button", { class: "btn small", onclick: closeDrawer, "aria-label": "Close" }, "✕"));
}
function renderTabs() {
  $("#dtabs").replaceChildren(...TABS.map(([k, l]) => h("button", { role: "tab", "aria-selected": String(S.tab === k),
    onclick: () => { S.tab = k; runCleanups(); renderTabs(); renderTab(); } }, l)));
}
function renderTab() {
  const d = byId(S.open); if (!d) return;
  const body = $("#dbody"); body.replaceChildren();
  ({ remote: tabRemote, inputs: tabInputs, apps: tabApps, install: tabInstall, shell: tabShell, info: tabInfo, settings: tabSettings })[S.tab](body, d);
}

async function sendKey(id, key) {
  try { const r = await act(id, "key", { key }); if (!r.ok) toast("Key failed: " + r.output, true); } catch (e) { toast(e.message, true); }
}

function tabRemote(body, d) {
  const k = (label, key, extra) => h("button", { class: "btn", title: key.replace("KEYCODE_", ""), "aria-label": extra || label, onclick: () => sendKey(d.id, key) }, label);
  const blank = () => h("span");
  const img = h("img", { class: "shot hidden", alt: "Screenshot of " + d.name });
  const load = async (quiet) => {
    try {
      const r = await fetch(`/api/devices/${d.id}/screenshot?t=${Date.now()}`, { credentials: "same-origin" });
      if (!r.ok) throw new Error((await r.json()).error); img.src = URL.createObjectURL(await r.blob()); img.classList.remove("hidden");
    } catch (e) { if (!quiet) toast(e.message, true); }
  };
  const kb = h("input", { type: "checkbox", id: "kbctl" });
  const keymap = { ArrowUp: "KEYCODE_DPAD_UP", ArrowDown: "KEYCODE_DPAD_DOWN", ArrowLeft: "KEYCODE_DPAD_LEFT", ArrowRight: "KEYCODE_DPAD_RIGHT", Enter: "KEYCODE_DPAD_CENTER", Backspace: "KEYCODE_BACK", h: "KEYCODE_HOME" };
  const onKey = e => { if (!kb.checked || !$("#drawer") || ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName) && document.activeElement !== kb) return;
    if (keymap[e.key]) { e.preventDefault(); e.stopPropagation(); sendKey(d.id, keymap[e.key]); } };
  document.addEventListener("keydown", onKey, true);
  cleanups.push(() => document.removeEventListener("keydown", onKey, true));
  if (d.status === "online") load(true);

  body.append(h("div", { class: "panel" }, h("div", { class: "remote" },
    h("div", null,
      h("div", { class: "pad" }, blank(), k("▲", "KEYCODE_DPAD_UP", "Up"), blank(), k("◀", "KEYCODE_DPAD_LEFT", "Left"), k("OK", "KEYCODE_DPAD_CENTER"), k("▶", "KEYCODE_DPAD_RIGHT", "Right"), blank(), k("▼", "KEYCODE_DPAD_DOWN", "Down"), blank()),
      h("div", { class: "keys" }, k("Back", "KEYCODE_BACK"), k("Home", "KEYCODE_HOME"), k("Menu", "KEYCODE_MENU"), k("Info", "KEYCODE_INFO"), k("Input", "KEYCODE_TV_INPUT")),
      h("div", { class: "keys" }, k("Vol −", "KEYCODE_VOLUME_DOWN"), k("Vol +", "KEYCODE_VOLUME_UP"), k("Mute", "KEYCODE_VOLUME_MUTE")),
      h("div", { class: "keys" }, k("Rew", "KEYCODE_MEDIA_REWIND", "Rewind"), k("Play/Pause", "KEYCODE_MEDIA_PLAY_PAUSE"), k("FF", "KEYCODE_MEDIA_FAST_FORWARD", "Fast forward")),
      h("div", { class: "keys" },
        h("button", { class: "btn", onclick: async () => { const r = await act(d.id, "wake"); toast(r.ok ? "Wake sent" : r.output, !r.ok); } }, "Wake"),
        h("button", { class: "btn", onclick: async () => { const r = await act(d.id, "sleep"); toast(r.ok ? "Standby sent" : r.output, !r.ok); } }, "Standby"),
        h("button", { class: "btn danger", onclick: async () => { if (confirm("Reboot " + d.name + "?")) { const r = await act(d.id, "reboot"); toast(r.ok ? "Rebooting…" : r.output, !r.ok); } } }, "Reboot")),
      h("div", { class: "field", style: "margin-top:12px" }, h("label", { for: "kbctl" }, h("span", null, kb, " Use keyboard (arrows, Enter, Backspace = Back, H = Home)")))),
    h("div", null, img,
      h("div", { class: "keys" }, h("button", { class: "btn small", onclick: () => load() }, "Screenshot"),
        h("label", { class: "muted" }, h("input", { type: "checkbox", onchange: e => { clearInterval(shotTimer); if (e.target.checked) { load(true); shotTimer = setInterval(() => load(true), 3000); } } }), " Auto-refresh"))))));
}

async function tabInputs(body, d) {
  const box = h("div", { class: "panel" }, h("h3", null, "TV inputs"), h("p", { class: "muted" }, "Loading…"));
  const restore = h("div", { class: "panel" });
  body.append(box, restore);
  const drawRestore = dev => restore.replaceChildren(h("h3", null, "Power-on behaviour"),
    h("p", { class: "muted" }, "When this TV wakes or boots to the launcher, return it to the last HDMI input it was using."),
    h("div", { class: "row" }, h("label", { class: "grow" }, h("input", { type: "checkbox", checked: dev.restore.enabled,
      onchange: async e => { try { await api("PUT", "/api/devices/" + d.id, { restore: { enabled: e.target.checked } }); await loadDevices(); toast("Saved"); } catch (x) { toast(x.message, true); } } }), " Restore last input on power-on")),
    h("div", { class: "row" }, h("div", { class: "grow" }, "Remembered input", h("div", { class: "sub" }, dev.restore.last || "none yet")),
      h("button", { class: "btn small", onclick: async () => { const r = await act(d.id, "restore"); toast(r.ok ? "Restored" : r.output, !r.ok); if (r.ok) settle(); } }, "Restore now"),
      h("button", { class: "btn small", onclick: async () => { await api("PUT", "/api/devices/" + d.id, { restore: { last: null } }); await loadDevices(); drawRestore(byId(d.id)); } }, "Forget")));
  drawRestore(d);
  const loadInputs = async () => { try {
    const { inputs } = await api("GET", `/api/devices/${d.id}/inputs`);
    const rows = inputs.filter(i => i.passthrough).concat(inputs.filter(i => !i.passthrough)).map(i => h("div", { class: "row" },
      h("div", { class: "grow" }, h("strong", null, i.name), i.active ? h("span", { class: "badge", style: "margin-left:8px" }, "active") : null,
        h("div", { class: "sub mono" }, i.id + " · " + i.state)),
      i.passthrough ? [
        h("button", { class: "btn small primary", onclick: async () => { const r = await act(d.id, "input", { input: i.id }); toast(r.ok ? "Switching to " + i.name : r.output, !r.ok); if (r.ok) settle(); } }, "Switch"),
        h("button", { class: "btn small", title: "Use as the input to restore on power-on", onclick: async () => { await api("PUT", "/api/devices/" + d.id, { restore: { last: i.id } }); await loadDevices(); drawRestore(byId(d.id)); toast("Will restore " + i.name); } }, "Set as power-on")] : null));
    box.replaceChildren(h("h3", null, "TV inputs"), inputs.length ? h("div", { class: "list" }, rows) : h("p", { class: "muted" }, "No inputs reported (is the TV on?)."));
  } catch (e) { box.replaceChildren(h("h3", null, "TV inputs"), h("p", { class: "err" }, e.message)); } };
  // after a switch, give the TV a moment, then refresh the active badge and the remembered input
  const settle = () => setTimeout(async () => { if (S.open !== d.id || S.tab !== "inputs") return; await loadDevices(); drawRestore(byId(d.id)); loadInputs(); }, 2500);
  loadInputs();
}

async function tabApps(body, d) {
  let filter = "user", q = "", pkgs = [];
  const list = h("div", { class: "list" });
  const draw = () => {
    const rows = pkgs.filter(p => p.name.includes(q.toLowerCase())).slice(0, 400).map(p => {
      const run = (a, msg) => async () => {
        try { const r = await api("POST", `/api/devices/${d.id}/packages/${p.name}`, { action: a }); toast(r.ok ? msg : (r.output || "failed"), !r.ok); if (r.ok && ["enable", "disable", "uninstall"].includes(a)) load(); }
        catch (e) { toast(e.message, true); } };
      return h("div", { class: "row" }, h("div", { class: "grow mono", title: p.name }, p.name, p.disabled ? h("span", { class: "badge", style: "margin-left:8px" }, "disabled") : null),
        h("button", { class: "btn small", onclick: run("launch", "Launched") }, "Open"),
        h("button", { class: "btn small", onclick: run("stop", "Stopped") }, "Stop"),
        p.disabled ? h("button", { class: "btn small", onclick: run("enable", "Enabled") }, "Enable") : h("button", { class: "btn small", onclick: run("disable", "Disabled") }, "Disable"),
        h("button", { class: "btn small", onclick: () => confirm("Clear all data for " + p.name + "?") && run("clear", "Data cleared")() }, "Clear"),
        h("button", { class: "btn small danger", onclick: () => confirm("Uninstall " + p.name + " for the user?") && run("uninstall", "Uninstalled")() }, "Remove"));
    });
    list.replaceChildren(...(rows.length ? rows : [h("p", { class: "muted" }, "No packages.")]));
  };
  const load = async () => {
    list.replaceChildren(h("p", { class: "muted" }, "Loading…"));
    try { pkgs = (await api("GET", `/api/devices/${d.id}/packages?filter=${filter}`)).packages; draw(); } catch (e) { list.replaceChildren(h("p", { class: "err" }, e.message)); }
  };
  const sel = h("select", { "aria-label": "Package filter", onchange: e => { filter = e.target.value; load(); } },
    ...[["user", "Installed apps"], ["disabled", "Disabled"], ["system", "System"], ["all", "Everything"]].map(([v, l]) => h("option", { value: v }, l)));
  body.append(h("div", { class: "panel" }, h("div", { class: "toolbar" }, sel,
    h("input", { type: "text", placeholder: "Filter packages", "aria-label": "Filter packages", oninput: e => { q = e.target.value; draw(); }, style: "flex:1" }),
    h("button", { class: "btn small", onclick: load }, "Reload")), list));
  load();
}

function tabInstall(body, d) {
  const out = h("pre", { class: "out hidden" }); const prog = h("div", { class: "bar hidden" }, h("i", { style: "width:0" }));
  const file = h("input", { type: "file", accept: ".apk,application/vnd.android.package-archive", id: "apkf" });
  const go = h("button", { class: "btn primary", onclick: () => {
    const f = file.files[0]; if (!f) return toast("Choose an APK first", true);
    const x = new XMLHttpRequest(); x.open("POST", `/api/devices/${d.id}/install?name=${encodeURIComponent(f.name)}`);
    x.setRequestHeader("X-Requested-With", "tvm"); x.setRequestHeader("Content-Type", "application/octet-stream");
    prog.classList.remove("hidden"); out.classList.add("hidden"); go.disabled = true;
    x.upload.onprogress = e => { if (e.lengthComputable) prog.firstChild.style.width = (100 * e.loaded / e.total) + "%"; };
    x.onload = () => { go.disabled = false; prog.classList.add("hidden"); let r = {}; try { r = JSON.parse(x.responseText); } catch (e) {}
      out.textContent = r.output || r.error || "No output"; out.classList.remove("hidden"); toast(r.ok ? "Installed " + f.name : "Install failed", !r.ok); };
    x.onerror = () => { go.disabled = false; toast("Upload failed", true); };
    x.send(f);
  } }, "Upload & install");
  body.append(h("div", { class: "panel" }, h("h3", null, "Install an APK"),
    h("div", { class: "field" }, h("label", { for: "apkf" }, "APK file (installed with -r, so existing apps are updated)"), file), go, h("div", { style: "margin-top:12px" }, prog), out));
}

function tabShell(body, d) {
  const out = h("pre", { class: "out" }, "Commands run through `adb shell` on " + d.name + ".");
  const inp = h("input", { type: "text", class: "mono", placeholder: "e.g. getprop ro.build.version.release", "aria-label": "Shell command", autocomplete: "off", spellcheck: "false" });
  const hist = JSON.parse(sessionStorage.getItem("tvm-hist") || "[]"); let hi = hist.length;
  const run = async cmd => {
    if (!cmd.trim()) return;
    hist.push(cmd); hi = hist.length; sessionStorage.setItem("tvm-hist", JSON.stringify(hist.slice(-50)));
    out.textContent = "$ " + cmd + "\n…";
    try { const r = await api("POST", `/api/devices/${d.id}/shell`, { cmd }); out.textContent = "$ " + cmd + "\n" + (r.output || "(no output)") + (r.rc ? `\n[exit ${r.rc}]` : ""); }
    catch (e) { out.textContent = "$ " + cmd + "\n" + e.message; }
  };
  inp.addEventListener("keydown", e => {
    if (e.key === "Enter") { run(inp.value); inp.value = ""; }
    else if (e.key === "ArrowUp" && hi > 0) { inp.value = hist[--hi]; e.preventDefault(); }
    else if (e.key === "ArrowDown") { inp.value = hi < hist.length - 1 ? hist[++hi] : ""; hi = Math.min(hi, hist.length); e.preventDefault(); } });
  const quick = [["Disabled packages", "pm list packages -d"], ["Current focus", "dumpsys window | grep mCurrentFocus"], ["Wakefulness", "dumpsys power | grep mWakefulness="], ["Storage", "df -h /data"], ["Uptime", "uptime"]];
  body.append(h("div", { class: "panel" }, h("div", { class: "toolbar" }, inp, h("button", { class: "btn primary", onclick: () => { run(inp.value); inp.value = ""; } }, "Run")),
    h("div", { class: "chips" }, quick.map(([l, c]) => h("button", { class: "chip", onclick: () => run(c) }, l))), out));
  inp.focus();
}

async function tabInfo(body, d) {
  const box = h("div", { class: "panel" }, h("p", { class: "muted" }, "Loading…")); body.append(box);
  try {
    const i = await api("GET", `/api/devices/${d.id}/info`);
    const rows = [["Address", d.addr], ["IP on device", i.ip || "–"], ["Uptime", i.uptime_s != null ? Math.floor(i.uptime_s / 3600) + "h " + Math.floor(i.uptime_s % 3600 / 60) + "m" : "–"],
      ...Object.entries(i.props).map(([k, v]) => [k.replace(/^ro\./, ""), v])];
    const bar = (label, used, total) => total ? h("div", { style: "margin-bottom:12px" }, h("div", { class: "row", style: "border:0;padding:0 0 4px" }, h("span", { class: "grow" }, label), h("span", { class: "muted" }, fmtKb(used) + " / " + fmtKb(total))),
      h("div", { class: "bar", role: "img", "aria-label": `${label} ${Math.round(100 * used / total)}% used` }, h("i", { style: `width:${100 * used / total}%` }))) : null;
    box.replaceChildren(bar("Storage (/data)", i.storage_kb && i.storage_kb.used, i.storage_kb && i.storage_kb.total),
      i.memory_kb && i.memory_kb.total ? bar("Memory", i.memory_kb.total - i.memory_kb.available, i.memory_kb.total) : null,
      h("table", null, h("tbody", null, rows.map(([k, v]) => h("tr", null, h("th", { scope: "row" }, k), h("td", { class: "mono" }, v))))));
  } catch (e) { box.replaceChildren(h("p", { class: "err" }, e.message)); }
}

function tabSettings(body, d) {
  const name = h("input", { type: "text", id: "sn", value: d.name }), addr = h("input", { type: "text", id: "sa", value: d.addr }),
    group = h("input", { type: "text", id: "sg", value: d.group, list: "grps2" });
  body.append(h("div", { class: "panel" }, h("h3", null, "Device"),
    h("div", { class: "field" }, h("label", { for: "sn" }, "Name"), name),
    h("div", { class: "field" }, h("label", { for: "sa" }, "Address"), addr),
    h("div", { class: "field" }, h("label", { for: "sg" }, "Group"), group, h("datalist", { id: "grps2" }, S.groups.map(g => h("option", { value: g })))),
    h("div", { class: "keys" },
      h("button", { class: "btn primary", onclick: async () => { try { await api("PUT", "/api/devices/" + d.id, { name: name.value, addr: addr.value, group: group.value }); await loadDevices(); updateDrawerHead(); toast("Saved"); } catch (e) { toast(e.message, true); } } }, "Save"),
      h("button", { class: "btn", onclick: async () => { const r = await act(d.id, "connect"); toast(r.output || (r.ok ? "Connected" : "Failed"), !r.ok); } }, "Reconnect ADB"))),
    h("div", { class: "panel" }, h("h3", null, "Remove"), h("p", { class: "muted" }, "Removes this TV from the manager. Nothing on the TV changes."),
      h("button", { class: "btn danger", onclick: async () => { if (confirm("Remove " + d.name + " from the manager?")) { await api("DELETE", "/api/devices/" + d.id); closeDrawer(); S.selected.delete(d.id); toast("Removed"); refresh(); } } }, "Remove device")));
}

/* ---------- schedules ---------- */
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
async function renderSchedules() {
  const main = $("#main"); if (!main || S.view !== "schedules") return;
  const { schedules } = await api("GET", "/api/schedules");
  const name = id => (byId(id) || { name: "(removed)" }).name;
  const desc = s => ({ wake: "Wake", sleep: "Standby", reboot: "Reboot", home: "Go Home", input: "Switch input" }[s.action]) + (s.input ? " → " + s.input.split("/").pop() : "");
  main.replaceChildren(h("div", { class: "toolbar" }, h("h2", { style: "flex:1" }, "Schedules"),
    h("button", { class: "btn primary", onclick: () => scheduleDialog() }, "+ New schedule")),
    h("p", { class: "muted" }, "Times use the server's clock. Standby and wake use the same keys as the remote."),
    schedules.length ? h("div", { class: "panel" }, h("div", { class: "list" }, schedules.map(s => h("div", { class: "row" },
      h("input", { type: "checkbox", checked: s.enabled, "aria-label": "Enabled", onchange: async e => { await api("PUT", "/api/schedules/" + s.id, { ...s, enabled: e.target.checked }); } }),
      h("div", { class: "grow" }, h("strong", null, s.name), h("div", { class: "sub" }, `${s.time} · ${s.days.length === 7 ? "every day" : s.days.map(d => DAYS[d]).join(", ")} · ${desc(s)} · ${s.targets.map(name).join(", ")}`)),
      h("button", { class: "btn small", onclick: () => scheduleDialog(s) }, "Edit"),
      h("button", { class: "btn small danger", onclick: async () => { if (confirm("Delete schedule " + s.name + "?")) { await api("DELETE", "/api/schedules/" + s.id); renderSchedules(); } } }, "Delete"))))) :
      h("div", { class: "empty" }, "No schedules yet."));
}

function scheduleDialog(s) {
  s = s || { name: "", action: "wake", time: "07:00", days: [0, 1, 2, 3, 4, 5, 6], targets: [], input: "", enabled: true };
  const name = h("input", { type: "text", id: "sn1", value: s.name, placeholder: "Morning on" });
  const action = h("select", { id: "sa1", onchange: () => inp.parentElement.classList.toggle("hidden", action.value !== "input") },
    ...[["wake", "Wake"], ["sleep", "Standby"], ["reboot", "Reboot"], ["home", "Go Home"], ["input", "Switch input"]].map(([v, l]) => h("option", { value: v, selected: v === s.action }, l)));
  const time = h("input", { type: "time", id: "st1", value: s.time });
  const inp = h("input", { type: "text", id: "si1", value: s.input || "", placeholder: "full input id, e.g. com.x/.HdmiService/HW5" });
  const days = new Set(s.days), targets = new Set(s.targets);
  const dayChips = h("div", { class: "chips" }, DAYS.map((l, i) => h("button", { type: "button", class: "chip", "aria-pressed": String(days.has(i)),
    onclick: e => { days.has(i) ? days.delete(i) : days.add(i); e.target.setAttribute("aria-pressed", String(days.has(i))); } }, l)));
  const devChips = h("div", { class: "chips" }, S.devices.map(d => h("button", { type: "button", class: "chip", "aria-pressed": String(targets.has(d.id)),
    onclick: e => { targets.has(d.id) ? targets.delete(d.id) : targets.add(d.id); e.target.setAttribute("aria-pressed", String(targets.has(d.id))); } }, d.name)));
  const err = h("p", { class: "err", role: "alert" });
  const m = modal(s.id ? "Edit schedule" : "New schedule", [
    h("div", { class: "field" }, h("label", { for: "sn1" }, "Name"), name),
    h("div", { class: "field" }, h("label", { for: "sa1" }, "Action"), action),
    h("div", { class: "field" + (s.action === "input" ? "" : " hidden") }, h("label", { for: "si1" }, "Input id"), inp),
    h("div", { class: "field" }, h("label", { for: "st1" }, "Time"), time),
    h("div", { class: "field" }, h("label", null, "Days"), dayChips),
    h("div", { class: "field" }, h("label", null, "Devices"), devChips), err], [
    h("button", { class: "btn", onclick: () => m.close() }, "Cancel"),
    h("button", { class: "btn primary", onclick: async () => {
      const body = { name: name.value, action: action.value, time: time.value, days: [...days], targets: [...targets], input: inp.value || null, enabled: s.enabled };
      try { await api(s.id ? "PUT" : "POST", "/api/schedules" + (s.id ? "/" + s.id : ""), body); m.close(); renderSchedules(); } catch (e) { err.textContent = e.message; } } }, "Save")]);
}

/* ---------- activity & settings ---------- */
async function renderEvents() {
  const main = $("#main"); if (!main || S.view !== "events") return;
  const { events } = await api("GET", "/api/events");
  main.replaceChildren(h("div", { class: "toolbar" }, h("h2", null, "Activity")),
    h("div", { class: "panel" }, events.length ? h("table", null,
      h("thead", null, h("tr", null, h("th", null, "Time"), h("th", null, "Device"), h("th", null, "Event"))),
      h("tbody", null, events.map(e => h("tr", { class: e.level === "error" ? "ev-error" : "" },
        h("td", { class: "mono", style: "white-space:nowrap" }, new Date(e.ts * 1000).toLocaleTimeString()), h("td", null, e.device), h("td", null, e.msg))))) :
      h("p", { class: "muted" }, "Nothing yet.")));
}

function renderSettings() {
  const main = $("#main"); if (!main) return;
  const cur = h("input", { type: "password", id: "pc", autocomplete: "current-password" }), nw = h("input", { type: "password", id: "pn", autocomplete: "new-password" });
  const msg = h("p", { class: "err", role: "alert" });
  main.replaceChildren(h("div", { class: "toolbar" }, h("h2", null, "Settings")),
    h("div", { class: "panel", style: "max-width:420px" }, h("h3", null, "Change password"),
      h("div", { class: "field" }, h("label", { for: "pc" }, "Current password"), cur),
      h("div", { class: "field" }, h("label", { for: "pn" }, "New password (8+ characters)"), nw),
      h("button", { class: "btn primary", onclick: async () => { try { await api("POST", "/api/password", { current: cur.value, new: nw.value }); cur.value = nw.value = ""; msg.textContent = ""; toast("Password changed"); } catch (e) { msg.textContent = e.message; } } }, "Update"), msg),
    h("div", { class: "panel", style: "max-width:420px" }, h("h3", null, "About"), h("p", { class: "muted" }, "TV Manager " + (S.version || "") + " · manages Android TVs over ADB.")));
}

start().catch(() => showLogin());
