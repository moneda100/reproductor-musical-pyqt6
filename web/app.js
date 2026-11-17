/**
 * Compañero web de Music Player Pro (PWA).
 *
 * El navegador es "un dispositivo más": se empareja con el mismo código de
 * 6 dígitos y habla el mismo protocolo WebSocket versionado (v1).
 */

const PROTOCOL_VERSION = 1;
const STORAGE_KEY = "musicplayerpro.session";

const state = {
  hubUrl: localStorage.getItem("musicplayerpro.hub") || "",
  deviceId: localStorage.getItem("musicplayerpro.deviceId") || "",
  token: localStorage.getItem("musicplayerpro.token") || "",
  householdId: localStorage.getItem("musicplayerpro.householdId") || "",
  socket: null,
  backoff: 1000,
  reconnectTimer: null,
  playback: {
    owner_device_id: null,
    track_key: null,
    state: "stopped",
    position_ms: 0,
    volume: 70,
    queue: [],
    queue_index: 0,
    revision: 0,
  },
  localPosition: 0,
  localPositionAt: 0,
};

const $ = (id) => document.getElementById(id);

/* ------------------------------------------------------------------ */
/* Utilidades                                                          */
/* ------------------------------------------------------------------ */
function toast(message) {
  const element = $("toast");
  element.textContent = message;
  element.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.add("hidden"), 3200);
}

function formatTime(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function setStatus(online, text) {
  const pill = $("status-pill");
  pill.textContent = text || (online ? "Conectado" : "Sin conexión");
  pill.classList.toggle("pill-online", online);
  pill.classList.toggle("pill-offline", !online);
}

function newId() {
  return (crypto.randomUUID?.() || String(Date.now()) + Math.random()).replace(/[^a-z0-9]/gi, "");
}

function saveSession() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    deviceId: state.deviceId,
    token: state.token,
    householdId: state.householdId,
  }));
}

/* ------------------------------------------------------------------ */
/* WebSocket                                                           */
/* ------------------------------------------------------------------ */
function wsUrl() {
  const base = state.hubUrl.replace(/\/$/, "");
  if (base.startsWith("https://")) return "wss://" + base.slice(8) + "/v1/ws";
  if (base.startsWith("http://")) return "ws://" + base.slice(7) + "/v1/ws";
  return "ws://" + base + "/v1/ws";
}

function connect() {
  if (!state.hubUrl || !state.token) {
    setStatus(false, "Sin configurar");
    return;
  }
  clearTimeout(state.reconnectTimer);
  setStatus(false, "Conectando…");
  const socket = new WebSocket(wsUrl());
  state.socket = socket;

  socket.addEventListener("open", () => {
    state.backoff = 1000;
    send("hello", {
      device_id: state.deviceId,
      token: state.token,
      since: Number(localStorage.getItem("musicplayerpro.cursor") || 0),
    });
  });

  socket.addEventListener("message", (event) => {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch {
      return;
    }
    handleMessage(message);
  });

  socket.addEventListener("close", () => {
    setStatus(false, "Sin conexión");
    scheduleReconnect();
  });

  socket.addEventListener("error", () => socket.close());
}

function scheduleReconnect() {
  const delay = Math.min(state.backoff, 60000) * (0.75 + Math.random() * 0.5);
  state.backoff = Math.min(state.backoff * 2, 60000);
  state.reconnectTimer = setTimeout(connect, delay);
}

function send(type, payload = {}) {
  if (!state.socket || state.socket.readyState !== WebSocket.OPEN) return false;
  state.socket.send(JSON.stringify({ v: PROTOCOL_VERSION, t: type, id: newId(), ...payload }));
  return true;
}

function handleMessage(message) {
  switch (message.t) {
    case "hello_ok":
      setStatus(true, "Conectado");
      localStorage.setItem("musicplayerpro.cursor", String(message.cursor || 0));
      state.playback.owner_device_id = message.owner_device_id;
      renderOwner();
      break;
    case "hello_error":
      setStatus(false, "Sin autorización");
      toast(message.error || "El relay rechazó la conexión");
      break;
    case "playback_state":
      state.playback = { ...state.playback, ...message };
      localPosition = state.playback.position_ms || 0;
      localPositionAt = Date.now();
      render();
      break;
    case "command":
      // El web es controlador: el dueño es quien aplica el comando.
      if (message.cmd === "takeover") {
        state.playback.owner_device_id = state.deviceId;
        renderOwner();
      }
      break;
    case "command_result":
      if (!message.ok) toast(message.error || "El comando falló");
      break;
    case "mutation_applied":
      localStorage.setItem("musicplayerpro.cursor", String(message.seq || 0));
      loadLibrary();
      break;
    case "pong":
      break;
    default:
      break;
  }
}

function sendCommand(cmd, args = {}) {
  if (!send("command", { cmd, args, cmd_id: newId() })) {
    toast("Sin conexión con el hub");
  }
}

/* ------------------------------------------------------------------ */
/* Emparejado                                                         */
/* ------------------------------------------------------------------ */
async function pairWithCode(code) {
  const base = state.hubUrl.replace(/\/$/, "");
  if (!base) {
    toast("Configura primero la URL del hub");
    return;
  }
  try {
    const response = await fetch(`${base}/v1/pairing/claim`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, name: navigator.userAgent.slice(0, 60), platform: "web" }),
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      toast(detail.detail || "El código no es válido");
      return;
    }
    const data = await response.json();
    state.deviceId = data.device_id;
    state.token = data.token;
    state.householdId = data.household_id;
    localStorage.setItem("musicplayerpro.deviceId", state.deviceId);
    localStorage.setItem("musicplayerpro.token", state.token);
    localStorage.setItem("musicplayerpro.householdId", state.householdId);
    saveSession();
    toast("Emparejado con éxito");
    connect();
  } catch (error) {
    toast(`No se pudo emparejar: ${error.message}`);
  }
}

async function loadDevices() {
  const base = state.hubUrl.replace(/\/$/, "");
  if (!base || !state.token) return;
  try {
    const response = await fetch(`${base}/v1/devices`, {
      headers: { Authorization: `Bearer ${state.token}` },
    });
    if (!response.ok) return;
    const data = await response.json();
    const list = $("devices");
    list.innerHTML = "";
    for (const device of data.devices || []) {
      const item = document.createElement("li");
      item.innerHTML = `<span>${device.name || device.id.slice(0, 8)}</span>
        <span class="meta">${device.platform}${device.is_current ? " · este dispositivo" : ""}</span>`;
      list.appendChild(item);
    }
  } catch {
    /* sin conexión */
  }
}

async function loadLibrary() {
  const base = state.hubUrl.replace(/\/$/, "");
  if (!base || !state.token) return;
  try {
    const response = await fetch(`${base}/v1/sync/snapshot?since=0`, {
      headers: { Authorization: `Bearer ${state.token}` },
    });
    if (!response.ok) return;
    const data = await response.json();
    renderLibrary(data.items || []);
  } catch {
    /* sin conexión */
  }
}

/* ------------------------------------------------------------------ */
/* Render                                                              */
/* ------------------------------------------------------------------ */
function render() {
  const playback = state.playback;
  $("btn-play").textContent = playback.state === "playing" ? "⏸" : "▶";
  const duration = playback.duration_ms || 0;
  $("position").textContent = formatTime(localPosition / 1000);
  $("duration").textContent = formatTime(duration / 1000);
  const percent = duration > 0 ? Math.min(100, (localPosition / duration) * 100) : 0;
  $("progress-fill").style.width = `${percent}%`;

  const queue = $("queue");
  queue.innerHTML = "";
  (playback.queue || []).forEach((key, index) => {
    const item = document.createElement("li");
    item.innerHTML = `<span>${index + 1}. ${key}</span>`;
    queue.appendChild(item);
  });
}

function renderOwner() {
  const isOwner = state.playback.owner_device_id === state.deviceId;
  $("owner-note").textContent = isOwner
    ? "Este dispositivo controla la reproducción."
    : "Control remoto: los comandos los aplica el dispositivo propietario.";
}

function renderLibrary(items) {
  const list = $("library-items");
  list.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("li");
    empty.innerHTML = '<span class="meta">Sin elementos todavía</span>';
    list.appendChild(empty);
    return;
  }
  for (const item of items) {
    const payload = item.payload || {};
    const name = payload.name || payload.title || item.item_id;
    const row = document.createElement("li");
    row.innerHTML = `<span>${name}</span><span class="meta">${item.kind}</span>`;
    list.appendChild(row);
  }
}

/* ------------------------------------------------------------------ */
/* Navegación                                                          */
/* ------------------------------------------------------------------ */
function showView(name) {
  for (const view of document.querySelectorAll(".view")) view.classList.add("hidden");
  const target = document.getElementById(`view-${name}`);
  if (target) target.classList.remove("hidden");
  for (const nav of document.querySelectorAll(".nav")) {
    nav.classList.toggle("active", nav.dataset.view === name);
  }
  if (name === "settings") {
    loadDevices();
  } else if (name === "library") {
    loadLibrary();
  }
}

/* ------------------------------------------------------------------ */
/* Arranque                                                            */
/* ------------------------------------------------------------------ */
function bindEvents() {
  $("btn-play").addEventListener("click", () => {
    sendCommand(state.playback.state === "playing" ? "pause" : "play");
  });
  $("btn-next").addEventListener("click", () => sendCommand("next"));
  $("btn-prev").addEventListener("click", () => sendCommand("prev"));
  $("btn-pair").addEventListener("click", () => {
    pairWithCode($("pair-code").value.trim());
  });
  $("btn-takeover").addEventListener("click", () => sendCommand("takeover"));
  $("btn-disconnect").addEventListener("click", () => {
    state.token = "";
    state.householdId = "";
    localStorage.removeItem("musicplayerpro.token");
    localStorage.removeItem("musicplayerpro.householdId");
    if (state.socket) state.socket.close();
    setStatus(false, "Desconectado");
  });
  $("hub-url").addEventListener("change", (event) => {
    state.hubUrl = event.target.value.trim();
    localStorage.setItem("musicplayerpro.hub", state.hubUrl);
    connect();
  });

  for (const nav of document.querySelectorAll(".nav")) {
    nav.addEventListener("click", () => showView(nav.dataset.view));
  }
  for (const tab of document.querySelectorAll(".tab")) {
    tab.addEventListener("click", () => {
      for (const other of document.querySelectorAll(".tab")) other.classList.remove("active");
      tab.classList.add("active");
      loadLibrary();
    });
  }
}

function start() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    if (saved.deviceId) state.deviceId = saved.deviceId;
    if (saved.token) state.token = saved.token;
    if (saved.householdId) state.householdId = saved.householdId;
  } catch {
    /* sesión corrupta: se ignora */
  }

  $("hub-url").value = state.hubUrl;
  bindEvents();
  showView("now-playing");

  setInterval(() => {
    if (state.playback.state === "playing") {
      localPosition = Date.now() - localPositionAt + (state.playback.position_ms || 0);
      localPositionAt = Date.now();
    }
    render();
  }, 1000);

  if (state.hubUrl && state.token) connect();

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
}

start();
