// comfyvn-data-exporter.js
// ComfyVN Architect – World Lore Production Chat
// Exposes Worlds, Characters, Personas, and (best-effort) "active" selections
// Works in single-user (default-user) and multi-user (data/users/<id>) modes.

const fs = require("fs");
const path = require("path");

exports.info = {
  id: "comfyvn-data-exporter",
  name: "ComfyVN Data Exporter",
  description: "Expose ST worlds/characters/personas via HTTP for ComfyVN and live render workflows.",
  version: "1.0.0"
};

exports.init = async function (router, { config, logger }) {
  // Resolve user root for single or multi-user.
  function resolveUserRoot(query) {
    const baseData = path.resolve("data");
    // 1) Explicit query override: ?user_id=xxxx
    if (query && query.user_id) {
      const candidate = path.join(baseData, "users", query.user_id);
      if (fs.existsSync(candidate)) return candidate;
    }
    // 2) ENV override: ST_USER_ID
    if (process.env.ST_USER_ID) {
      const candidate = path.join(baseData, "users", process.env.ST_USER_ID);
      if (fs.existsSync(candidate)) return candidate;
    }
    // 3) Multi-user detection: first subdir of data/users
    const usersDir = path.join(baseData, "users");
    if (fs.existsSync(usersDir)) {
      const entries = fs.readdirSync(usersDir, { withFileTypes: true }).filter(d => d.isDirectory());
      if (entries.length > 0) return path.join(usersDir, entries[0].name);
    }
    // 4) Fallback: single-user default
    return path.join(baseData, "default-user");
  }

  function dirSafeJoin(root, sub) {
    return path.resolve(root, sub); // Use resolve for safety
  }

  function listJsonNames(folder) {
    if (!fs.existsSync(folder)) return [];
    return fs.readdirSync(folder).filter(f => f.toLowerCase().endsWith(".json"));
  }

  function readJson(fullPath, logger) {
    try {
      return JSON.parse(fs.readFileSync(fullPath, "utf8"));
    } catch (e) {
      logger.error(`[ComfyVN] Error reading JSON: ${e.message}, path: ${fullPath}`);
      return { error: "Invalid JSON or unreadable file", path: fullPath };
    }
  }

  function roots(userRoot) {
    return {
      userRoot,
      worlds: dirSafeJoin(userRoot, "worlds"),
      characters: dirSafeJoin(userRoot, "characters"),
      personas: dirSafeJoin(userRoot, "personas"),
      chats: dirSafeJoin(userRoot, "chats"),
      settings: path.resolve(userRoot, "settings.json") // Sanitize
    };
  }

  // Health check
  router.get("/comfyvn/health", (req, res) => {
    res.json({ status: "ok", plugin: "comfyvn-data-exporter", version: exports.info.version });
  });

  // Return resolved roots
  router.get("/comfyvn/roots", (req, res) => {
    try {
      const userRoot = resolveUserRoot(req.query);
      res.json(roots(userRoot));
    } catch (err) {
      logger.error(`[ComfyVN] Roots error: ${err.message}`);
      res.status(500).json({ error: "Internal error" });
    }
  });

  // Worlds
  router.get("/comfyvn/worlds", (req, res) => {
    try {
      const userRoot = resolveUserRoot(req.query);
      const r = roots(userRoot);
      res.json({ worlds: listJsonNames(r.worlds) });
    } catch (err) {
      logger.error(`[ComfyVN] Worlds list error: ${err.message}`);
      res.status(500).json({ error: "Internal error" });
    }
  });

  router.get("/comfyvn/worlds/:name", (req, res) => {
    try {
      const userRoot = resolveUserRoot(req.query);
      const r = roots(userRoot);
      const file = path.resolve(r.worlds, req.params.name);
      if (!file.startsWith(r.worlds)) return res.status(403).json({ error: "Forbidden: Invalid path" });
      if (!fs.existsSync(file)) return res.status(404).json({ error: "Not found" });
      res.json(readJson(file, logger));
    } catch (err) {
      logger.error(`[ComfyVN] World get error: ${err.message}`);
      res.status(500).json({ error: "Internal error" });
    }
  });

  // Characters (similar updates for characters and personas routes)
  router.get("/comfyvn/characters", (req, res) => {
    try {
      const userRoot = resolveUserRoot(req.query);
      const r = roots(userRoot);
      res.json({ characters: listJsonNames(r.characters) });
    } catch (err) {
      logger.error(`[ComfyVN] Characters list error: ${err.message}`);
      res.status(500).json({ error: "Internal error" });
    }
  });

  router.get("/comfyvn/characters/:name", (req, res) => {
    try {
      const userRoot = resolveUserRoot(req.query);
      const r = roots(userRoot);
      const file = path.resolve(r.characters, req.params.name);
      if (!file.startsWith(r.characters)) return res.status(403).json({ error: "Forbidden: Invalid path" });
      if (!fs.existsSync(file)) return res.status(404).json({ error: "Not found" });
      res.json(readJson(file, logger));
    } catch (err) {
      logger.error(`[ComfyVN] Character get error: ${err.message}`);
      res.status(500).json({ error: "Internal error" });
    }
  });

  // Personas (analogous corrections)
  router.get("/comfyvn/personas", (req, res) => {
    try {
      const userRoot = resolveUserRoot(req.query);
      const r = roots(userRoot);
      res.json({ personas: listJsonNames(r.personas) });
    } catch (err) {
      logger.error(`[ComfyVN] Personas list error: ${err.message}`);
      res.status(500).json({ error: "Internal error" });
    }
  });

  router.get("/comfyvn/personas/:name", (req, res) => {
    try {
      const userRoot = resolveUserRoot(req.query);
      const r = roots(userRoot);
      const file = path.resolve(r.personas, req.params.name);
      if (!file.startsWith(r.personas)) return res.status(403).json({ error: "Forbidden: Invalid path" });
      if (!fs.existsSync(file)) return res.status(404).json({ error: "Not found" });
      res.json(readJson(file, logger));
    } catch (err) {
      logger.error(`[ComfyVN] Persona get error: ${err.message}`);
      res.status(500).json({ error: "Internal error" });
    }
  });

  // Best-effort "active" snapshot
  router.get("/comfyvn/active", (req, res) => {
    try {
      const userRoot = resolveUserRoot(req.query);
      const r = roots(userRoot);

      let settings = {};
      if (fs.existsSync(r.settings)) {
        try { 
          settings = JSON.parse(fs.readFileSync(r.settings, "utf8")); 
        } catch (err) {
          logger.warn(`[ComfyVN] Settings parse warning: ${err.message}`);
          settings = {}; // Fallback to empty
        }
      }

      // Heuristics – these keys may vary by ST version; we expose raw if found.
      const activeHints = {
        activeWorld: settings.activeWorld || null,
        activeCharacter: settings.activeCharacter || settings.lastCharacter || null,
        activePersona: settings.activePersona || null
      };

      const payload = {
        roots: r,
        settingsHints: activeHints,
        // Optional: add shallow lists to help the client choose.
        worlds: listJsonNames(r.worlds),
        characters: listJsonNames(r.characters),
        personas: listJsonNames(r.personas)
      };

      res.json(payload);
    } catch (err) {
      logger.error(`[ComfyVN] Active error: ${err.message}`);
      res.status(500).json({ error: "Internal error" });
    }
  });

  logger.info("[ComfyVN] comfyvn-data-exporter initialized.");
};