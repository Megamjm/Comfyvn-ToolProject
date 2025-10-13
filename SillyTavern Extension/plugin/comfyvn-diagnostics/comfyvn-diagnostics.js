// comfyvn-diagnostics.js
// ComfyVN Diagnostics Plugin v1.1
// ✅ Confirms plugin initialization, router registration, and endpoint accessibility
// Works with SillyTavern ≥ 1.13.x plugin loader (graceful param handling)

const fs = require("fs");
const path = require("path");

// ---------------------------------------------------------------------------
// 🪵 Logging setup
// ---------------------------------------------------------------------------
const LOG_PATH = path.resolve("logs", "plugin_diagnostics.log");
fs.mkdirSync(path.dirname(LOG_PATH), { recursive: true });

function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  fs.appendFileSync(LOG_PATH, line);
  console.log("[ComfyVN-Diagnostics]", msg);
}

// ---------------------------------------------------------------------------
// 📦 Plugin Metadata
// ---------------------------------------------------------------------------
exports.info = {
  id: "comfyvn-diagnostics",
  name: "ComfyVN Diagnostics",
  description: "Verifies SillyTavern plugin registration, router state, and API routing.",
  version: "1.1.0"
};

// ---------------------------------------------------------------------------
// 🚀 Initialization
// ---------------------------------------------------------------------------
exports.init = async function (router, api = {}) {
  // Defensive destructuring to prevent “Cannot destructure property 'config'” errors
  const { config = {}, logger = console } = api;

  try {
    log("🔧 Plugin init() called.");
    log("📦 Plugin info: " + JSON.stringify(exports.info));

    // -----------------------------------------------------------------------
    // 🧠 Health and Ping Endpoints
    // -----------------------------------------------------------------------
    router.get("/health", (req, res) => {
      log("GET /health called.");
      res.json({ ok: true, plugin: "comfyvn-diagnostics", version: exports.info.version });
    });

    router.get("/ping", (req, res) => {
      const payload = { pong: true, timestamp: Date.now() };
      log("GET /ping called → " + JSON.stringify(payload));
      res.json(payload);
    });

    // -----------------------------------------------------------------------
    // 🔍 Route summary logging
    // -----------------------------------------------------------------------
    const routeCount = Array.isArray(router.stack) ? router.stack.length : 0;
    log(`✅ Routes registered: ${routeCount}`);
    if (router.stack) {
      router.stack.forEach(r => {
        if (r.route?.path) log("  • " + r.route.path);
      });
    }

    log("🧩 Expecting routes under /api/plugins/comfyvn-diagnostics/");
    log("✅ comfyvn-diagnostics initialized successfully.");

  } catch (err) {
    const msg = "❌ Error in comfyvn-diagnostics.init: " + err.stack;
    log(msg);
    if (logger && typeof logger.error === "function") logger.error(msg);
  }
};
