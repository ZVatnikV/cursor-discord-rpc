const I18N = {
  en: {
    subtitle: "Rich Presence for Cursor",
    disable_rpc: "Disable RPC",
    enable_rpc: "Enable RPC",
    show_elapsed: "Session timer",
    button_enabled: "GitHub button (friends see it)",
    autostart: "Start with Windows",
    hint: "details — AI activity · state — chat · workspace",
    preview: "Discord preview",
    save: "Save",
    saved: "Saved",
    rpc_on: "RPC enabled",
    rpc_off: "RPC disabled",
    rpc_disabled: "RPC disabled",
    lang: "Language",
    label_ai: "AI",
    label_chat: "Chat",
    label_ws: "Workspace",
  },
  ru: {
    subtitle: "Rich Presence для Cursor",
    disable_rpc: "Отключить RPC",
    enable_rpc: "Включить RPC",
    show_elapsed: "Таймер сессии",
    button_enabled: "Кнопка GitHub (видят друзья)",
    autostart: "Автозапуск с Windows",
    hint: "details — что делает AI · state — чат · workspace",
    preview: "Превью Discord",
    save: "Сохранить",
    saved: "Сохранено",
    rpc_on: "RPC включён",
    rpc_off: "RPC выключен",
    rpc_disabled: "RPC выключен",
    lang: "Язык",
    label_ai: "AI",
    label_chat: "Чат",
    label_ws: "Workspace",
  },
};

const $ = (id) => document.getElementById(id);

let state = {
  language: "en",
  enabled: true,
  show_elapsed: true,
  button_enabled: true,
  autostart: true,
  startedAt: Date.now(),
};

let lastDetails = "";
let toastTimer = null;

function api() {
  return window.pywebview?.api;
}

function t(key) {
  const pack = I18N[state.language] || I18N.en;
  return pack[key] || I18N.en[key] || key;
}

function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    el.textContent = t(key);
  });
  document.querySelectorAll(".seg-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.lang === state.language);
  });
  syncPower();
}

function syncPower() {
  const btn = $("powerBtn");
  btn.classList.toggle("on", !state.enabled);
  btn.querySelector(".power-label").textContent = state.enabled
    ? t("disable_rpc")
    : t("enable_rpc");
  document.body.classList.toggle("disabled", !state.enabled);
}

function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2000);
}

function flashDetails() {
  const d = $("details");
  const card = $("discordCard");
  d.classList.add("flash");
  card.classList.add("flash");
  setTimeout(() => {
    d.classList.remove("flash");
    card.classList.remove("flash");
  }, 280);
}

function fmtElapsed() {
  const sec = Math.max(0, Math.floor((Date.now() - state.startedAt) / 1000));
  const m = String(Math.floor(sec / 60)).padStart(2, "0");
  const s = String(sec % 60).padStart(2, "0");
  return `${m}:${s}`;
}

function collect() {
  return {
    language: state.language,
    enabled: state.enabled,
    show_elapsed: $("showElapsed").checked,
    button_enabled: $("buttonEnabled").checked,
    autostart: $("autostart").checked,
  };
}

async function pushConfig(partial = {}) {
  const cfg = { ...collect(), ...partial };
  state = { ...state, ...cfg };
  const a = api();
  if (a?.save_config) await a.save_config(cfg);
}

async function bootstrap() {
  const a = api();
  if (a?.get_snapshot) {
    const snap = await a.get_snapshot();
    if (snap?.config) {
      state.language = snap.config.language || "en";
      state.enabled = !!snap.config.enabled;
      state.show_elapsed = !!snap.config.show_elapsed;
      state.button_enabled = !!snap.config.button_enabled;
      state.autostart = !!snap.config.autostart;
      $("showElapsed").checked = state.show_elapsed;
      $("buttonEnabled").checked = state.button_enabled;
      $("autostart").checked = state.autostart;
    }
    if (snap?.started_at) state.startedAt = snap.started_at * 1000;
  }
  applyI18n();
  syncPower();
}

async function tick() {
  const a = api();
  if (!a?.get_snapshot) return;
  try {
    const snap = await a.get_snapshot();
    const live = snap.live || {};
    const status = snap.status || {};
    const cfg = snap.config || {};

    state.enabled = !!cfg.enabled;
    syncPower();

    const pill = $("statusPill");
    const ok = !!status.ok;
    pill.classList.toggle("ok", ok);
    $("statusText").textContent = status.msg || "…";

    if (!state.enabled) {
      $("details").textContent = t("rpc_disabled");
      $("stateLine").textContent = "";
      $("kindBadge").textContent = "OFF";
    } else {
      const details = live.details || live.activity || "—";
      const stateLine = live.state || "—";
      if (details !== lastDetails) {
        lastDetails = details;
        flashDetails();
      }
      $("details").textContent = details;
      $("stateLine").textContent = stateLine;
      $("kindBadge").textContent = (live.kind || "idle").toUpperCase();
    }

    $("chipAi").textContent = live.activity || "—";
    $("chipChat").textContent = live.chat_name || "—";
    $("chipWs").textContent = live.workspace || "—";
    $("timerChip").style.display = cfg.show_elapsed ? "" : "none";
    $("timerChip").textContent = fmtElapsed();
    $("ghBtn").classList.toggle("hidden", !cfg.button_enabled);
  } catch (_) {
    /* ignore bridge hiccups */
  }
}

function wire() {
  $("powerBtn").addEventListener("click", async () => {
    state.enabled = !state.enabled;
    syncPower();
    const a = api();
    if (a?.set_enabled) await a.set_enabled(state.enabled);
    toast(state.enabled ? t("rpc_on") : t("rpc_off"));
  });

  document.querySelectorAll(".seg-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      state.language = btn.dataset.lang;
      applyI18n();
      await pushConfig({ language: state.language });
    });
  });

  ["showElapsed", "buttonEnabled", "autostart"].forEach((id) => {
    $(id).addEventListener("change", () => pushConfig());
  });

  $("saveBtn").addEventListener("click", async () => {
    await pushConfig();
    toast(t("saved"));
    const btn = $("saveBtn");
    btn.classList.add("ok");
    setTimeout(() => btn.classList.remove("ok"), 260);
  });
}

window.addEventListener("pywebviewready", async () => {
  wire();
  await bootstrap();
  setInterval(tick, 400);
  tick();
});

// Dev fallback if opened in a normal browser
if (!window.pywebview) {
  document.addEventListener("DOMContentLoaded", () => {
    wire();
    applyI18n();
    syncPower();
  });
}
