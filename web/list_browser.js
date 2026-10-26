// Kept independent of Comfy globals so the real UI can also be integration-tested.
export function attachBrowser(node, api) {
    const root = document.createElement("section");
    const shadow = root.attachShadow({ mode: "open" });
    shadow.innerHTML = `
        <style>
        :host{display:block;height:100%;min-width:0;color:#e8eaf0;font:13px system-ui,sans-serif;color-scheme:dark}
        *{box-sizing:border-box} section{height:100%;display:flex;flex-direction:column;gap:9px;padding:10px;background:#161a22;border:1px solid #343c4c;border-radius:10px;overflow:hidden}
        header{display:flex;justify-content:space-between;align-items:center;gap:8px} h3{margin:0;font-size:14px} .badge{color:#a8c7ff;font-size:11px}
        .tools{display:flex;gap:6px;flex-wrap:wrap} input,select,button{font:inherit;border:1px solid #46516a;border-radius:6px;background:#252c3b;color:inherit;padding:7px;min-width:0}
        input{flex:1;width:100px}select{flex:2;width:180px}button{cursor:pointer}button:hover{background:#323e55}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #93baff;outline-offset:2px}
        .status{color:#acb6ca;font-size:12px;min-height:16px}.status.error{color:#ffb2af}
        .grid{position:relative;display:grid;grid-template-columns:repeat(auto-fill,minmax(125px,1fr));grid-auto-rows:max-content;gap:8px;overflow:auto;flex:1;min-height:100px;align-content:start;padding:3px}
        .card{display:flex;flex-direction:column;align-self:start;padding:0;overflow:hidden;position:relative;text-align:left;border:2px solid #343e52;border-radius:8px;background:#202735}
        .card[aria-pressed=true]{border-color:#9cbeff;box-shadow:0 0 0 1px #9cbeff;background:#2d4164}
        .image{position:relative;flex:none;width:100%;aspect-ratio:4/3;background:linear-gradient(140deg,#26324b,#181d29);display:grid;place-items:center;overflow:hidden}
        img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.placeholder{color:#8e9bb5;font-size:12px;text-align:center}.number{position:absolute;top:6px;left:6px;background:#101726dc;color:white;padding:3px 6px;border-radius:4px;font-weight:700}
        .label{display:block;flex:none;width:100%;padding:8px;font-size:12px;font-weight:600;line-height:1.35;overflow-wrap:anywhere}
        .output{border-top:1px solid #343e52;padding-top:8px}.output strong{font-size:11px;color:#b6c8e8}.output p{margin:4px 0 0;line-height:1.4;max-height:82px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}
        .empty{grid-column:1/-1;color:#a6b2c9;padding:20px 6px;text-align:center}
        details{font-size:11px;color:#acb6ca}summary{cursor:pointer}.paths{overflow-wrap:anywhere;white-space:pre-line;user-select:text;padding-top:4px}
        </style>
        <section aria-label="List preview browser">
            <header><h3>Visual list browser</h3><span class="badge"></span></header>
            <div class="tools"><input type="search" placeholder="Find a title or description…" aria-label="Search entries"><select aria-label="Select entry"></select><button type="button" title="Reread text files and rescan preview images, bypassing caches">Reload files</button></div>
            <div class="status" role="status" aria-live="polite"></div>
            <details><summary>Library folders</summary><div class="paths"></div></details>
            <div class="grid" aria-label="Preview gallery"></div>
            <div class="output"><strong>SELECTED TEXT</strong><p></p></div>
        </section>`;
    const $ = (selector) => shadow.querySelector(selector);
    const grid = $(".grid"), select = $("select"), search = $("input");
    const widgets = Object.fromEntries((node.widgets ?? []).map(w => [w.name, w]));
    let data = null, updating = false, configuring = false, removed = false, generation = 0, timer;
    let connectedData = null, executedOutput = "";
    const pending = new Map();
    const starts = new Map(), outcomes = new Map(), envelopes = new WeakMap();
    let activePromptId = null, reloadNonce = "", reloadCounter = 0, writtenText;
    const revision = () => Number(node.properties?.lp_selection_revision) || 0;
    const remember = (map, key, item) => {
        map.set(key, item);
        while (map.size > 64) map.delete(map.keys().next().value);
    };
    const configure = node.configure;
    node.configure = function (...args) {
        const previous = configuring;
        configuring = true;
        try { return configure?.apply(this, args); }
        finally { configuring = previous; }
    };

    const value = (name) => widgets[name]?.value;
    const connected = () => node.inputs?.some(i => ["list_input", "text"].includes(i.name) && i.link != null);
    const status = (message, error = false) => {
        $(".status").textContent = message;
        $(".status").classList.toggle("error", error);
    };
    const set = (name, next) => {
        const widget = widgets[name];
        if (!widget) return;
        if (name === "text") writtenText = next;
        if (widget.value === next) return;
        const previous = updating;
        updating = true;
        try { widget.value = next; widget.callback?.(next); }
        finally { updating = previous; }
    };
    const mark = () => {
        node.properties ??= {};
        node.properties.lp_selection_revision = (Number(node.properties.lp_selection_revision) || 0) + 1;
        node.graph?.change?.();
        node.setDirtyCanvas?.(true, true);
    };
    const output = (entry) => (value("prefix") || "") + (value("include_title") ? entry.text : entry.description) + (value("suffix") || "");
    function selection() {
        if (!data) return;
        $(".paths").textContent = `Build: ${data.node_version || "0.2.0"}\nTexts: ${data.texts_directory || ""}\nPreviews: ${data.preview_directory || "Set preview_folder to choose a directory."}`;
        const row = Number(value("row"));
        select.value = String(row);
        grid.querySelectorAll(".card").forEach(card => card.setAttribute("aria-pressed", String(Number(card.dataset.row) === row)));
        const selectedCard = grid.querySelector('.card[aria-pressed="true"]');
        if (selectedCard) {
            const top = selectedCard.offsetTop, bottom = top + selectedCard.offsetHeight;
            if (top < grid.scrollTop) grid.scrollTop = top;
            else if (bottom > grid.scrollTop + grid.clientHeight) grid.scrollTop = bottom - grid.clientHeight;
        }
        const entry = data.entries.find(e => e.row === row);
        $(".output strong").textContent = "SELECTED TEXT";
        $(".output p").textContent = entry ? output(entry) : "Choose an available row.";
        $(".badge").textContent = `${row} / ${data.entries.length} · ${value("mode")}`;
    }
    function choose(row) {
        set("row", Number(row));
        executedOutput = "";
        mark();
        selection();
        status(`${data.entries.length} entries · Row ${row} selected`);
    }
    function render() {
        grid.replaceChildren();
        select.replaceChildren();
        if (!data) return;
        const query = search.value.trim().toLocaleLowerCase();
        const fragment = document.createDocumentFragment();
        for (const entry of data.entries) {
            const option = document.createElement("option");
            option.value = entry.row;
            option.textContent = `${String(entry.row).padStart(2, "0")} — ${entry.title || entry.description}`;
            select.append(option);
            if (query && !`${entry.number} ${entry.text}`.toLocaleLowerCase().includes(query)) continue;
            const card = document.createElement("button");
            card.type = "button";
            card.className = "card";
            card.dataset.row = entry.row;
            card.setAttribute("aria-label", option.textContent);
            card.title = entry.text;
            const image = document.createElement("div");
            image.className = "image";
            const placeholder = () => {
                image.replaceChildren();
                const label = document.createElement("span");
                label.className = "placeholder";
                label.textContent = "No preview";
                image.append(label);
            };
            if (entry.preview) {
                const img = document.createElement("img");
                img.alt = entry.title || `Row ${entry.row}`;
                img.loading = "lazy";
                img.decoding = "async";
                const query = new URLSearchParams({folder: data.folder, file: entry.preview, v: entry.version, reload: reloadNonce});
                // apiURL respects ComfyUI's configured base path (including reverse proxies).
                img.src = api.apiURL(`/luis-lists/preview?${query}`);
                img.addEventListener("error", placeholder, { once: true });
                image.append(img);
            } else placeholder();
            const number = document.createElement("span");
            number.className = "number";
            number.textContent = String(entry.row).padStart(2, "0");
            const label = document.createElement("span");
            label.className = "label";
            label.textContent = entry.title || entry.description;
            card.append(image, number, label);
            card.addEventListener("click", () => choose(entry.row));
            fragment.append(card);
        }
        grid.append(fragment);
        if (!grid.childElementCount) {
            const empty = document.createElement("p");
            empty.className = "empty";
            empty.textContent = data.entries.length ? "No entries match your search." : "Add one entry per line to your list.";
            grid.append(empty);
        }
        selection();
    }
    async function request(path, options) {
        const response = await api.fetchApi(path, { ...options, cache: "no-store" });
        const body = await response.json();
        if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
        return body;
    }
    async function load(refresh = false) {
        const ticket = ++generation;
        if (refresh) reloadNonce = `${Date.now()}-${++reloadCounter}`;
        try {
            status("Loading list…");
            if (refresh) {
                const { files } = await request(`/luis-lists/files?reload=${reloadNonce}`);
                if (removed || ticket !== generation) return;
                if (widgets.list_file) widgets.list_file.options.values = files.length ? files : ["(no files)"];
            }
            let result;
            if (connected()) {
                if (!connectedData) {
                    data = null;
                    grid.replaceChildren();
                    select.replaceChildren();
                    $(".output p").textContent = "";
                    status("Connected list: run once to load entries, then choose a row and run again.");
                    return;
                }
                result = await request("/luis-lists/parse", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({text: connectedData.text, file: value("list_file"), folder: value("preview_folder") || ""}) });
            } else if (value("source") === "File") {
                result = await request(`/luis-lists/list?${new URLSearchParams({file: value("list_file"), folder: value("preview_folder") || "", reload: reloadNonce})}`);
            } else {
                result = await request("/luis-lists/parse", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({text: value("text") || "", file: value("list_file"), folder: value("preview_folder") || ""}) });
            }
            if (removed || ticket !== generation) return;
            data = result;
            if (value("source") === "File" && !connected()) set("text", result.text);
            if (Number(value("row")) > result.entries.length && result.entries.length) { set("row", 1); mark(); }
            render();
            const count = result.entries.filter(e => e.preview).length;
            status(`${result.entries.length} entries · ${count} previews${connected() ? " · Connected list" : ""}${count ? "" : " · Check Library folders for the image location"}`);
        } catch (error) {
            if (removed || ticket !== generation) return;
            data = null;
            grid.replaceChildren();
            select.replaceChildren();
            $(".output p").textContent = "";
            status(error.message, true);
        }
    }
    function schedule() {
        clearTimeout(timer);
        // Invalidate in-flight responses immediately, before the debounce expires.
        generation++;
        timer = setTimeout(() => load(), 200);
    }
    for (const name of ["source", "list_file", "row", "mode", "include_title", "preview_folder", "text", "prefix", "suffix"]) {
        const widget = widgets[name];
        if (!widget) continue;
        const original = widget.callback;
        widget.callback = function (...args) {
            const result = original?.apply(this, args);
            if (updating || configuring || removed) return result;
            if (name === "text" && value("text") === writtenText) return result;
            executedOutput = "";
            if (name === "text" && !connected()) set("source", "Text");
            if (!["include_title", "prefix", "suffix"].includes(name)) mark();
            if (["row", "mode", "include_title", "prefix", "suffix"].includes(name)) { selection(); if (data) status(`${data.entries.length} entries · Row ${value("row")} selected`); }
            else schedule();
            return result;
        };
    }
    search.addEventListener("input", render);
    select.addEventListener("change", () => choose(select.value));
    $("button").addEventListener("click", () => load(true));
    // Keep scroll, keyboard and pointer handling local to the gallery.
    for (const event of ["pointerdown", "mousedown", "wheel", "keydown"]) root.addEventListener(event, e => e.stopPropagation());
    const widget = node.addDOMWidget("luis_preview_gallery", "luis_preview_gallery", root, {
        serialize: false, hideOnZoom: false, getMinHeight: () => 320, getMaxHeight: () => 900,
    });
    widget.serialize = false;
    const chain = (name, callback) => {
        const original = node[name];
        node[name] = function (...args) { const result = original?.apply(this, args); callback(...args); return result; };
    };
    chain("onConfigure", () => {
        // Saved v0.1 graphs contain only the original text socket. Append new sockets
        // without moving it or changing its existing connections.
        const outputs = [["text","STRING"],["list_file","STRING"],["row","INT"],
            ["title","STRING"],["description","STRING"],["image","IMAGE"]];
        for (let i = node.outputs?.length || 0; i < outputs.length; i++) node.addOutput(...outputs[i]);
        connectedData = null;
        schedule();
    });
    chain("onConnectionsChange", () => { connectedData = null; schedule(); });
    function receive(result) {
        if (!result || removed) return;
        const envelope = envelopes.get(result);
        const promptId = envelope?.promptId || result.prompt_id || activePromptId;
        const localRevision = starts.get(promptId) ?? revision();
        generation++;
        clearTimeout(timer);
        data = result;
        connectedData = result.connected || connected() ? result : null;
        set("text", result.text);
        const isCurrentSelection = revision() === localRevision;
        if (isCurrentSelection) set("row", result.selected_row);
        executedOutput = result.output;
        if (result.mode !== "Fixed") pending.set(promptId, {result, localRevision});
        render();
        status(`Used row ${result.selected_row}${result.mode !== "Fixed" ? " · Advances after successful render" : ""} · ${result.entries.length} entries${result.image_status ? ` · ${result.image_status}` : ""}`);
        $(".output strong").textContent = "LAST OUTPUT";
        $(".output p").textContent = result.output;
        node.setDirtyCanvas?.(true, true);
        if (outcomes.has(promptId)) complete(promptId, outcomes.get(promptId));
    }
    chain("onExecuted", message => {
        // The raw event supplies prompt_id even on backends without an execution context.
        const result = message?.list_preview?.[0];
        if (result) queueMicrotask(() => receive(result));
    });
    function complete(promptId, succeeded) {
        const item = pending.get(promptId);
        if (!item || removed) return;
        pending.delete(promptId);
        const {result, localRevision} = item;
        // A manual selection made while rendering takes priority over the queued result.
        if (revision() !== localRevision) return;
        if (succeeded) {
            set("row", result.next_row);
            node.graph?.change?.();
            selection();
            status(`Used row ${result.selected_row} · Next: ${result.next_row} · ${result.entries.length} entries${result.image_status ? ` · ${result.image_status}` : ""}`);
            $(".output strong").textContent = "LAST OUTPUT";
            $(".output p").textContent = result.output;
        } else status(`Render did not finish · Row ${result.selected_row} preserved`);
        node.setDirtyCanvas?.(true, true);
    }
    const started = event => {
        activePromptId = event.detail?.prompt_id;
        if (activePromptId) remember(starts, activePromptId, revision());
    };
    const executed = event => {
        const detail = event.detail;
        if (String(detail?.display_node || detail?.node) !== String(node.id)) return;
        const result = detail?.output?.list_preview?.[0];
        if (result) {
            envelopes.set(result, {promptId: detail.prompt_id});
            activePromptId = detail.prompt_id;
        }
    };
    const finished = event => {
        const promptId = event.detail?.prompt_id || activePromptId;
        remember(outcomes, promptId, event.type === "execution_success");
        complete(promptId, outcomes.get(promptId));
    };
    const idle = event => {
        if (event.detail != null) return;
        // Older ComfyUI versions finish with executing(null), without execution_success.
        const promptId = activePromptId;
        if (!outcomes.has(promptId)) remember(outcomes, promptId, true);
        complete(promptId, outcomes.get(promptId));
        activePromptId = null;
    };
    const listeners = {execution_start: started, executed, executing: idle,
        execution_success: finished, execution_error: finished, execution_interrupted: finished};
    for (const [event, handler] of Object.entries(listeners)) api.addEventListener(event, handler);
    chain("onRemoved", () => {
        removed = true; generation++; clearTimeout(timer); root.remove(); pending.clear();
        starts.clear(); outcomes.clear();
        for (const [event, handler] of Object.entries(listeners)) api.removeEventListener(event, handler);
    });
    node.setSize?.([Math.max(node.size?.[0] || 0, 540), Math.max(node.size?.[1] || 0, 820)]);
    timer = setTimeout(() => load(true), 0);
    return { root, load, choose, get data() { return data; } };
}
