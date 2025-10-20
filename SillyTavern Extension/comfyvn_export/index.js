// SillyTavern extension: export current chat into a ComfyVN scene JSON.
(function () {
  const MODULE = "comfyvn_export";

  function nowStamp() {
    const d = new Date();
    const pad = (n) => n.toString().padStart(2, "0");
    return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
  }

  function detectEmotion(text) {
    const m = text.match(/\[\[\s*(?:e|emotion)\s*:\s*([a-z0-9_\- ]+)\s*\]\]/i);
    if (!m) {
      return { emotion: null, clean: text };
    }
    const clean = text.replace(m[0], "").trim();
    return { emotion: m[1].trim(), clean };
  }

  function speakerName(msg, ctx) {
    if (msg.is_user) {
      return "User";
    }
    try {
      const charId = ctx.characterId;
      const characters = ctx.characters || [];
      return msg.name || (characters[charId]?.name ?? "Character");
    } catch (err) {
      console.warn(`[${MODULE}] speaker lookup failed`, err);
      return msg.name || "Character";
    }
  }

  function buildRawScene(ctx, title = "") {
    const chat = ctx.chat || [];
    const out = {
      id: `scene-${nowStamp()}`,
      source: "SillyTavern",
      title: title || (ctx.characters?.[ctx.characterId]?.name ? `Chat with ${ctx.characters[ctx.characterId].name}` : ""),
      created_at: new Date().toISOString(),
      dialogue: [],
    };
    for (const msg of chat) {
      if (!msg?.mes) {
        continue;
      }
      const { emotion, clean } = detectEmotion(msg.mes);
      out.dialogue.push({
        type: "line",
        speaker: speakerName(msg, ctx),
        text: clean,
        emotion: emotion || null,
      });
    }
    return out;
  }

  function downloadJSON(obj, filename) {
    const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function doExport(namedArgs, unnamedArgs) {
    const ctx = SillyTavern.getContext();
    const title = (unnamedArgs || []).join(" ");
    const raw = buildRawScene(ctx, title);
    const fname = `comfyvn_scene_${nowStamp()}.json`;
    downloadJSON(raw, fname);
    return `Exported ${raw.dialogue.length} lines -> ${fname}`;
  }

  const { SlashCommandParser, SlashCommand, SlashCommandArgument, ARGUMENT_TYPE } = SillyTavern.getContext();
  SlashCommandParser.addCommandObject(
    SlashCommand.fromProps({
      name: "comfyvn_export",
      callback: (namedArgs, unnamedArgs) => doExport(namedArgs, unnamedArgs),
      aliases: ["cvn_export", "export_cvn"],
      returns: "Downloads a ComfyVN raw scene JSON",
      namedArgumentList: [],
      unnamedArgumentList: [
        SlashCommandArgument.fromProps({
          description: "Optional title",
          typeList: ARGUMENT_TYPE.STRING,
          isRequired: false,
        }),
      ],
      helpString: `
        <div>
          Export the current chat to a ComfyVN raw scene JSON.
          Tag emotions inline like <code>[[e:happy]]</code> to set <em>emotion</em>.
        </div>
      `,
    })
  );
})();
