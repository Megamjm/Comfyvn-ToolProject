// comfyvn-data-exporter.js
// ComfyVN Architect — SillyTavern Plugin Bridge v2.0
// Provides: worlds, characters, personas, chats, active state
// Compatible with SillyTavern >= 1.13.x (plugin router API)

const fs = require("fs");
const path = require("path");

// ---------------------------------------------------------------------------
// 🪵 Logging setup
// ---------------------------------------------------------------------------
const LOG_PATH = path.resolve("logs", "comfyvn_data_exporter.log");
fs.mkdirSync(path.dirname(LOG_PATH), { recursive: true });

function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  fs.appendFileSync(LOG_PATH, line);
  console.log("[ComfyVN-Exporter]", msg);
}

// ---------------------------------------------------------------------------
// 📦 Plugin Metadata
// ---------------------------------------------------------------------------
exports.info = {
  id: "comfyvn-data-exporter",
  name: "ComfyVN Data Exporter",
  description: "Expose ST worlds, characters, personas, chats, and active info for ComfyVN integration.",
  version: "2.0.0",
};

// ---------------------------------------------------------------------------
// 🚀 Initialization
// ---------------------------------------------------------------------------
exports.init = async function (router, api = {}) {
  const { config = {}, logger = console } = api;
  log("🔧 comfyvn-data-exporter.init() called");

  // -------------------------------------------------------------------------
  // 🗂 Path helpers
  // -------------------------------------------------------------------------
  function resolveUserRoot(query) {
    const baseData = path.resolve("data");
    if (query?.user_id) {
      const custom = path.join(baseData, "users", query.user_id);
      if (fs.existsSync(custom)) return custom;
    }
    if (process.env.ST_USER_ID) {
      const envUser = path.join(baseData, "users", process.env.ST_USER_ID);
      if (fs.existsSync(envUser)) return envUser;
    }
    const usersDir = path.join(baseData, "users");
    if (fs.existsSync(usersDir)) {
      const entries = fs.readdirSync(usersDir, { withFileTypes: true }).filter(d => d.isDirectory());
      if (entries.length > 0) return path.join(usersDir, entries[0].name);
    }
    return path.join(baseData, "default-user");
  }

  function safeList(folder) {
    if (!fs.existsSync(folder)) return [];
    return fs.readdirSync(folder).filter(f => f.toLowerCase().endsWith(".json"));
  }

  function readJson(fullPath) {
    try {
      return JSON.parse(fs.readFileSync(fullPath, "utf8"));
    } catch (err) {
      log(`⚠️ Failed to parse JSON: ${err.message}`);
      return { error: "invalid_json" };
    }
  }

  function getRoots(userRoot) {
    return {
      userRoot,
      worlds: path.join(userRoot, "worlds"),
      characters: path.join(userRoot, "characters"),
      personas: path.join(userRoot, "personas"),
      chats: path.join(userRoot, "chats"),
      settings: path.join(userRoot, "settings.json"),
    };
  }

  // -------------------------------------------------------------------------
  // 🩺 Health check
  // -------------------------------------------------------------------------
  router.get("/health", (req, res) => {
    log("GET /health called");
    res.json({ ok: true, plugin: "comfyvn-data-exporter", version: exports.info.version });
  });

  // -------------------------------------------------------------------------
  // 🌍 Worlds
  // -------------------------------------------------------------------------
  router.get("/worlds", (req, res) => {
    try {
      const userRoot = resolveUserRoot(req.query);
      const r = getRoots(userRoot);
      res.json({ worlds: safeList(r.worlds) });
    } catch (err) {
      log(`❌ Worlds error: ${err.message}`);
      res.status(500).json({ error: "Internal error" });
    }
  });

  router.get("/worlds/:name", (req, res) => {
    try {
      const userRoot = resolveUserRoot(req.query);
      const r = getRoots(userRoot);
      const file = path.join(r.worlds, req.params.name);
      if (!fs.existsSync(file)) return res.status(404).json({ error: "World not found" });
      res.json(readJson(file));
    } catch (err) {
      log(`❌ World read error: ${err.message}`);
      res.status(500).json({ error: "Internal error" });
    }
  });

  // -------------------------------------------------------------------------
  // 🧍 Characters
  // -------------------------------------------------------------------------
  router.get("/characters", (req, res) => {
    try {
      const userRoot = resolveUserRoot(req.query);
      const r = getRoots(userRoot);
      res.json({ characters: safeList(r.characters) });
    } catch (err) {
      log(`❌ Characters error: ${err.message}`);
      res.status(500).json({ error: "Internal error" });
    }
  });

  // -------------------------------------------------------------------------
  // 🪞 Personas
  // -------------------------------------------------------------------------
  router.get("/personas", (req, res) => {
    try {
      const userRoot = resolveUserRoot(req.query);
      const r = getRoots(userRoot);
      res.json({ personas: safeList(r.personas) });
    } catch (err) {
      log(`❌ Personas error: ${err.message}`);
      res.status(500).json({ error: "Internal error" });
    }
  });

  // -------------------------------------------------------------------------
  // 💬 Chats
  // -------------------------------------------------------------------------
  router.get("/chats", (req, res) => {
    try {
      const userRoot = resolveUserRoot(req.query);
      const r = getRoots(userRoot);
      res.json({ chats: safeList(r.chats) });
    } catch (err) {
      log(`❌ Chats error: ${err.message}`);
      res.status(500).json({ error: "Internal error" });
    }
  });

  // -------------------------------------------------------------------------
  // 🧠 Active snapshot
  // -------------------------------------------------------------------------
  router.get("/active", (req, res) => {
    try {
      const userRoot = resolveUserRoot(req.query);
      const r = getRoots(userRoot);
      let settings = {};
      if (fs.existsSync(r.settings)) {
        try {
          settings = JSON.parse(fs.readFileSync(r.settings, "utf8"));
        } catch (err) {
          log(`⚠️ Settings parse failed: ${err.message}`);
        }
      }

      const payload = {
        roots: r,
        activeWorld: settings.activeWorld || null,
        activeCharacter: settings.activeCharacter || settings.lastCharacter || null,
        activePersona: settings.activePersona || null,
        timestamp: Date.now(),
      };
      res.json(payload);
    } catch (err) {
      log(`❌ Active error: ${err.message}`);
      res.status(500).json({ error: "Internal error" });
    }
  });

  // -------------------------------------------------------------------------
  // ✅ Completion Log
  // -------------------------------------------------------------------------
  const count = Array.isArray(router.stack) ? router.stack.length : 0;
  log(`✅ comfyvn-data-exporter initialized with ${count} routes.`);
};
