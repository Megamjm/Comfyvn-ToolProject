// [ComfyVN Debug] Script loaded - Start of file

const CONFIG_KEYS = {
    pluginBase: "comfyvn.pluginBase",
    comfyEndpoint: "comfyvn.endpoint",
};

function getPluginBase() {
    return localStorage.getItem(CONFIG_KEYS.pluginBase) || "/api/plugins/comfyvn-data-exporter";
}

function getComfyEndpoint() {
    return localStorage.getItem(CONFIG_KEYS.comfyEndpoint) || "http://127.0.0.1:8001/st/import";
}

function setConfig({ pluginBase, comfyEndpoint }) {
    if (pluginBase !== undefined) {
        localStorage.setItem(CONFIG_KEYS.pluginBase, pluginBase || "/api/plugins/comfyvn-data-exporter");
    }
    if (comfyEndpoint !== undefined) {
        localStorage.setItem(CONFIG_KEYS.comfyEndpoint, comfyEndpoint || "http://127.0.0.1:8001/st/import");
    }
}

function buildPluginUrl(path = "") {
    const base = getPluginBase();
    const cleanPath = path.replace(/^\//, "");
    if (/^https?:\/\//i.test(base)) {
        const trimmed = base.replace(/\/$/, "");
        return cleanPath ? `${trimmed}/${cleanPath}` : trimmed;
    }
    const trimmed = base.replace(/\/$/, "");
    return cleanPath ? `${trimmed}/${cleanPath}` : trimmed;
}

// [ComfyVN Debug] Constants defined

async function fetchJSON(url) {
    console.log("[ComfyVN Debug] Entering fetchJSON with url:", url);
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
}

async function postJSON(url, body) {
    console.log("[ComfyVN Debug] Entering postJSON with url:", url);
    const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json().catch(() => ({}));
}

function toast(msg, ok = true) {
    console.log("[ComfyVN Debug] Displaying toast:", msg);
    const t = document.createElement("div");
    t.className = `comfyvn-toast ${ok ? "ok" : "fail"}`;
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2600);
}

async function syncCategory(type) {
    console.log("[ComfyVN Debug] Syncing category:", type);
    try {
        const data = await fetchJSON(buildPluginUrl(type));
        console.log("[ComfyVN Debug] Fetched data for", type);
        await postJSON(getComfyEndpoint(), { type, data });
        toast(`✅ Synced ${type} with ComfyVN.`);
    } catch (err) {
        console.warn(`[ComfyVN] Sync error for ${type}:`, err);
        toast(`❌ Sync failed for ${type}.`, false);
    }
}

async function syncActive() {
    console.log("[ComfyVN Debug] Syncing active state");
    try {
        const data = await fetchJSON(buildPluginUrl("active"));
        console.log("[ComfyVN Debug] Fetched active data");
        await postJSON(getComfyEndpoint(), { type: "active", data });
        toast("✅ Active state synced.");
    } catch (err) {
        toast("❌ Failed to sync active state.", false);
    }
}

async function checkPlugin() {
    console.log("[ComfyVN Debug] Checking plugin health");
    try {
        const res = await fetchJSON(buildPluginUrl("health"));
        console.log("[ComfyVN Debug] Health check response:", res);
        console.log("[ComfyVN] Plugin connected:", res);
        toast("🔗 Plugin connected.", true);
    } catch (err) {
        console.warn("[ComfyVN] Plugin unreachable:", err);
        toast("⚠️ Plugin not reachable. Check comfyvn-data-exporter.js", false);
    }
}

function buildPanel(container) {
    console.log("[ComfyVN Debug] Building panel");
    if (document.getElementById("comfyvn_container")) {
        console.log("[ComfyVN Debug] Container already exists - Skipping build");
        return;
    }

    const extensionContainer = document.createElement("div");
    extensionContainer.id = "comfyvn_container";
    extensionContainer.className = "extension_container";

    const drawer = document.createElement("div");
    drawer.className = "inline-drawer comfyvn-settings";

    const header = document.createElement("div");
    header.className = "inline-drawer-toggle inline-drawer-header";
    header.innerHTML = `
        <b>ComfyVN Bridge</b>
        <div class="inline-drawer-icon fa-solid interactable down fa-circle-chevron-down" tabindex="0" role="button"></div>
    `;
    drawer.appendChild(header);

    const content = document.createElement("div");
    content.className = "inline-drawer-content";
    content.style.display = "none";  // Start collapsed
    content.innerHTML = `
        <div class="comfyvn-controls">
            <div class="comfyvn-config">
                <label>Plugin Base</label>
                <input id="comfyvn-pluginBase" type="text" value="${getPluginBase()}">
                <label>ComfyVN Endpoint</label>
                <input id="comfyvn-endpoint" type="text" value="${getComfyEndpoint()}">
                <button id="comfyvn-saveConfig">Save Settings</button>
            </div>
            <button id="comfyvn-syncWorlds">Sync Worlds</button>
            <button id="comfyvn-syncChars">Sync Characters</button>
            <button id="comfyvn-syncPersonas">Sync Personas</button>
            <button id="comfyvn-syncActive">Sync Active</button>
            <button id="comfyvn-checkPlugin">Check Plugin</button>
        </div>
    `;
    drawer.appendChild(content);

    extensionContainer.appendChild(drawer);

    if (container) {
        container.appendChild(extensionContainer);
        console.log("[ComfyVN Debug] Extension container appended");
    } else {
        console.warn("[ComfyVN Debug] No container found");
    }

    // Bind toggle event
    const toggleIcon = header.querySelector(".inline-drawer-icon");
    toggleIcon.addEventListener("click", () => {
        console.log("[ComfyVN Debug] Toggle clicked");
        if (content.style.display === "block") {
            content.style.display = "none";
            toggleIcon.classList.remove("up", "fa-circle-chevron-up");
            toggleIcon.classList.add("down", "fa-circle-chevron-down");
        } else {
            content.style.display = "block";
            toggleIcon.classList.remove("down", "fa-circle-chevron-down");
            toggleIcon.classList.add("up", "fa-circle-chevron-up");
        }
    });

    // Bind button events
    content.querySelector("#comfyvn-syncWorlds").onclick = () => syncCategory("worlds");
    content.querySelector("#comfyvn-syncChars").onclick = () => syncCategory("characters");
    content.querySelector("#comfyvn-syncPersonas").onclick = () => syncCategory("personas");
    content.querySelector("#comfyvn-syncActive").onclick = () => syncActive();
    content.querySelector("#comfyvn-checkPlugin").onclick = () => checkPlugin();
    content.querySelector("#comfyvn-saveConfig").onclick = () => {
        const pluginInput = content.querySelector("#comfyvn-pluginBase");
        const endpointInput = content.querySelector("#comfyvn-endpoint");
        setConfig({ pluginBase: pluginInput.value.trim(), comfyEndpoint: endpointInput.value.trim() });
        toast("💾 ComfyVN bridge settings saved.");
    };

    console.log("[ComfyVN] Panel mounted.");
    console.log("[ComfyVN Debug] Panel built, toggle bound, events bound");
}

function mountWhenExtensionsPanelAppears() {
    console.log("[ComfyVN Debug] Starting mount observer");
    const existing = document.querySelector("#extensions_settings");
    if (existing) {
        console.log("[ComfyVN Debug] Settings container found immediately");
        buildPanel(existing);
        return;
    }

    const observer = new MutationObserver(() => {
        console.log("[ComfyVN Debug] Mutation observed - Checking for container");
        const container = document.querySelector("#extensions_settings");
        if (container) {
            console.log("[ComfyVN Debug] Container detected via observer");
            observer.disconnect();
            buildPanel(container);
        }
    });

    observer.observe(document.body, { childList: true, subtree: true });
    console.log("[ComfyVN Debug] Observer started");
}

// Run initialization directly
console.log("[ComfyVN Debug] Extension loaded - Calling mount function");
mountWhenExtensionsPanelAppears();
console.log("[ComfyVN Debug] End of file");
