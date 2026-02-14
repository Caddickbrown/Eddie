/* ── Journally Web – Frontend ─────────────────────────────────────────────── */

(function () {
    "use strict";

    // ── State ────────────────────────────────────────────────────────────────
    let config = {};
    let rootFolder = "";
    let tabs = [];          // { path, name, editor, modified, el }
    let activeTabIndex = -1;
    let contextFiles = new Set();

    // ── DOM refs ─────────────────────────────────────────────────────────────
    const $filePanel    = document.getElementById("file-panel");
    const $aiPanel      = document.getElementById("ai-panel");
    const $fileTree     = document.getElementById("file-tree");
    const $tabBar       = document.getElementById("tab-bar");
    const $editorCont   = document.getElementById("editor-container");
    const $chatHistory  = document.getElementById("chat-history");
    const $chatInput    = document.getElementById("chat-input");
    const $ctxLabel     = document.getElementById("context-label");

    // ── Init ─────────────────────────────────────────────────────────────────
    async function init() {
        config = await api("/api/config");
        applyConfigToUI();
        if (config.default_folder) {
            rootFolder = config.default_folder;
            await loadFileTree(rootFolder);
        }
        lucide.createIcons();
        bindEvents();
    }

    function applyConfigToUI() {
        // Panel visibility
        setPanelVisible($filePanel, "btn-toggle-files", config.show_file_panel !== false);
        setPanelVisible($aiPanel, "btn-toggle-ai", config.show_ai_panel !== false);
        // Apply theme
        applyTheme(config.theme || "layan-dark");
    }

    function applyTheme(themeKey) {
        // Remove existing theme link if any
        const existing = document.getElementById("theme-stylesheet");
        if (existing) existing.remove();

        // Create new theme link
        const link = document.createElement("link");
        link.id = "theme-stylesheet";
        link.rel = "stylesheet";
        link.href = `/api/theme/${themeKey}`;
        document.head.appendChild(link);
    }

    function setPanelVisible(panel, btnId, visible) {
        const btn = document.getElementById(btnId);
        const dividers = { "btn-toggle-files": "divider-left", "btn-toggle-ai": "divider-right" };
        const divider = document.getElementById(dividers[btnId]);
        if (visible) {
            panel.classList.remove("hidden");
            if (divider) divider.classList.remove("hidden");
            btn.classList.add("active");
        } else {
            panel.classList.add("hidden");
            if (divider) divider.classList.add("hidden");
            btn.classList.remove("active");
        }
    }

    // ── API helper ───────────────────────────────────────────────────────────
    async function api(url, opts) {
        const res = await fetch(url, opts);
        return res.json();
    }

    async function postJSON(url, body) {
        return api(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
    }

    // ── Events ───────────────────────────────────────────────────────────────
    function bindEvents() {
        // Toolbar
        document.getElementById("btn-open-folder").addEventListener("click", openFolderDialog);
        document.getElementById("btn-new-file").addEventListener("click", newFileDialog);
        document.getElementById("btn-save").addEventListener("click", saveCurrentTab);
        document.getElementById("btn-close-tab").addEventListener("click", closeCurrentTab);
        document.getElementById("btn-toggle-files").addEventListener("click", () => togglePanel($filePanel, "btn-toggle-files"));
        document.getElementById("btn-toggle-ai").addEventListener("click", () => togglePanel($aiPanel, "btn-toggle-ai"));
        document.getElementById("btn-clear-ctx").addEventListener("click", clearContext);
        document.getElementById("btn-settings").addEventListener("click", openSettings);
        document.getElementById("btn-scripts").addEventListener("click", toggleScriptsMenu);
        
        // Close scripts menu when clicking outside
        document.addEventListener("click", (e) => {
            const dropdown = document.querySelector(".scripts-dropdown");
            if (dropdown && !dropdown.contains(e.target)) {
                document.getElementById("scripts-menu").classList.add("hidden");
            }
        });

        // AI chat
        document.getElementById("btn-send").addEventListener("click", sendChat);
        $chatInput.addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(); });

        // Settings modal
        document.getElementById("settings-close").addEventListener("click", closeSettings);
        document.getElementById("settings-cancel").addEventListener("click", closeSettings);
        document.getElementById("settings-save").addEventListener("click", saveSettings);
        document.getElementById("set-clear-folder").addEventListener("click", () => {
            document.getElementById("set-default-folder").value = "";
        });
        document.getElementById("set-browse-folder").addEventListener("click", () => {
            openFolderBrowser(document.getElementById("set-default-folder").value, (selected) => {
                document.getElementById("set-default-folder").value = selected;
            });
        });

        // Open-folder modal
        document.getElementById("folder-close").addEventListener("click", closeFolderDialog);
        document.getElementById("folder-cancel").addEventListener("click", closeFolderDialog);
        document.getElementById("folder-open").addEventListener("click", doOpenFolder);
        document.getElementById("folder-path-input").addEventListener("keydown", (e) => {
            if (e.key === "Enter") doOpenFolder();
        });
        document.getElementById("folder-browse-btn").addEventListener("click", () => {
            openFolderBrowser(document.getElementById("folder-path-input").value, (selected) => {
                document.getElementById("folder-path-input").value = selected;
            });
        });

        // Folder browser modal
        document.getElementById("fbrowser-close").addEventListener("click", closeFolderBrowser);
        document.getElementById("fbrowser-cancel").addEventListener("click", closeFolderBrowser);
        document.getElementById("fbrowser-select").addEventListener("click", confirmFolderBrowser);
        document.getElementById("fbrowser-up").addEventListener("click", folderBrowserUp);

        // New-file modal
        document.getElementById("newfile-close").addEventListener("click", closeNewFileDialog);
        document.getElementById("newfile-cancel").addEventListener("click", closeNewFileDialog);
        document.getElementById("newfile-create").addEventListener("click", doNewFile);
        document.getElementById("newfile-name").addEventListener("keydown", (e) => {
            if (e.key === "Enter") doNewFile();
        });

        // Script output modal
        document.getElementById("script-output-close").addEventListener("click", closeScriptOutput);
        document.getElementById("script-output-ok").addEventListener("click", closeScriptOutput);

        // Keyboard shortcuts
        document.addEventListener("keydown", (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "s") {
                e.preventDefault();
                saveCurrentTab();
            }
        });

        // Divider drag
        initDivider("divider-left", $filePanel, "width", 150, 500);
        initDivider("divider-right", $aiPanel, "width", 200, 600, true);
    }

    // ── Panel toggle ─────────────────────────────────────────────────────────
    function togglePanel(panel, btnId) {
        const visible = panel.classList.contains("hidden");
        setPanelVisible(panel, btnId, visible);
    }

    // ── Divider drag ─────────────────────────────────────────────────────────
    function initDivider(dividerId, panel, prop, min, max, fromRight) {
        const div = document.getElementById(dividerId);
        if (!div) return;
        let startX, startW;
        div.addEventListener("mousedown", (e) => {
            e.preventDefault();
            startX = e.clientX;
            startW = panel.getBoundingClientRect().width;
            div.classList.add("active");
            const onMove = (e2) => {
                const dx = fromRight ? startX - e2.clientX : e2.clientX - startX;
                panel.style.width = Math.min(max, Math.max(min, startW + dx)) + "px";
            };
            const onUp = () => {
                div.classList.remove("active");
                document.removeEventListener("mousemove", onMove);
                document.removeEventListener("mouseup", onUp);
            };
            document.addEventListener("mousemove", onMove);
            document.addEventListener("mouseup", onUp);
        });
    }

    // ── File Tree ────────────────────────────────────────────────────────────
    async function loadFileTree(folder) {
        const data = await api(`/api/files/tree?folder=${encodeURIComponent(folder)}`);
        rootFolder = data.root || folder;
        $fileTree.innerHTML = "";
        if (data.tree.length) {
            const ul = buildTreeUL(data.tree);
            $fileTree.appendChild(ul);
        } else {
            $fileTree.innerHTML = '<div style="padding:12px;color:var(--text-muted);font-size:13px;">No files. Open a folder first.</div>';
        }
    }

    function buildTreeUL(nodes) {
        const ul = document.createElement("ul");
        for (const node of nodes) {
            const li = document.createElement("li");
            const row = document.createElement("div");
            row.className = "tree-row";

            if (node.is_dir) {
                // Toggle arrow
                const toggle = document.createElement("span");
                toggle.className = "tree-toggle";
                toggle.textContent = "▶";
                row.appendChild(toggle);

                const icon = document.createElement("span");
                icon.className = "tree-icon";
                icon.textContent = "📁";
                row.appendChild(icon);

                const name = document.createElement("span");
                name.className = "tree-name";
                name.textContent = node.name;
                row.appendChild(name);

                li.appendChild(row);

                // Children
                if (node.children && node.children.length) {
                    const childUL = buildTreeUL(node.children);
                    childUL.className = "tree-children";
                    li.appendChild(childUL);

                    row.addEventListener("click", () => {
                        childUL.classList.toggle("open");
                        toggle.classList.toggle("open");
                    });
                }
            } else {
                // Spacer for alignment
                const spacer = document.createElement("span");
                spacer.style.width = "16px";
                spacer.style.flexShrink = "0";
                row.appendChild(spacer);

                const icon = document.createElement("span");
                icon.className = "tree-icon";
                icon.textContent = "📄";
                row.appendChild(icon);

                const name = document.createElement("span");
                name.className = "tree-name";
                name.textContent = node.name;
                name.addEventListener("dblclick", () => openFile(node.path));
                row.appendChild(name);

                // Context checkbox
                const ctx = document.createElement("input");
                ctx.type = "checkbox";
                ctx.className = "tree-ctx";
                ctx.checked = contextFiles.has(node.path);
                ctx.title = "Include in AI context";
                ctx.addEventListener("change", () => {
                    if (ctx.checked) contextFiles.add(node.path);
                    else contextFiles.delete(node.path);
                    updateContextLabel();
                });
                row.appendChild(ctx);

                // Single click also opens file
                row.addEventListener("click", (e) => {
                    if (e.target !== ctx) openFile(node.path);
                });

                li.appendChild(row);
            }
            ul.appendChild(li);
        }
        return ul;
    }

    // ── Tabs & Editor ────────────────────────────────────────────────────────
    async function openFile(path) {
        // Check if already open
        const existing = tabs.findIndex(t => t.path === path);
        if (existing >= 0) { switchTab(existing); return; }

        const data = await api(`/api/files/read?path=${encodeURIComponent(path)}`);
        if (data.error) { addChatMessage("error", data.error); return; }

        createTab(path, data.content);
    }

    function createTab(path, content) {
        const name = path ? path.split(/[\\/]/).pop() : "Untitled";
        const mode = guessMode(name);

        // Create CodeMirror instance (hidden until active)
        const wrapper = document.createElement("div");
        wrapper.style.cssText = "position:absolute;inset:0;display:none;";
        $editorCont.appendChild(wrapper);

        const editor = CodeMirror(wrapper, {
            value: content || "",
            mode: mode,
            theme: "material-darker",
            lineNumbers: config.show_line_numbers !== false,
            lineWrapping: config.wrap_text !== false,
            indentUnit: 4,
            tabSize: 4,
            indentWithTabs: false,
            autoCloseBrackets: true,
        });

        const tab = { path, name, editor, modified: false, wrapperEl: wrapper, tabEl: null };

        editor.on("change", () => {
            if (!tab.modified) {
                tab.modified = true;
                updateTabLabel(tab);
            }
        });

        tabs.push(tab);
        renderTabBar();
        switchTab(tabs.length - 1);
    }

    function switchTab(index) {
        if (index < 0 || index >= tabs.length) return;
        activeTabIndex = index;
        tabs.forEach((t, i) => {
            t.wrapperEl.style.display = i === index ? "block" : "none";
        });
        // Refresh the visible editor
        tabs[index].editor.refresh();
        renderTabBar();
    }

    function renderTabBar() {
        $tabBar.innerHTML = "";
        tabs.forEach((t, i) => {
            const el = document.createElement("div");
            el.className = "tab" + (i === activeTabIndex ? " active" : "");
            const label = (t.modified ? "● " : "") + t.name;
            el.innerHTML = `<span class="tab-label">${escHTML(label)}</span><span class="tab-close" title="Close">&times;</span>`;
            el.querySelector(".tab-label").addEventListener("click", () => switchTab(i));
            el.querySelector(".tab-close").addEventListener("click", (e) => { e.stopPropagation(); closeTab(i); });
            $tabBar.appendChild(el);
            t.tabEl = el;
        });
    }

    function updateTabLabel(tab) {
        if (tab.tabEl) {
            const label = (tab.modified ? "● " : "") + tab.name;
            tab.tabEl.querySelector(".tab-label").textContent = label;
        }
    }

    function closeTab(index) {
        const tab = tabs[index];
        tab.wrapperEl.remove();
        tabs.splice(index, 1);
        if (tabs.length === 0) {
            activeTabIndex = -1;
        } else if (activeTabIndex >= tabs.length) {
            activeTabIndex = tabs.length - 1;
        } else if (activeTabIndex > index) {
            activeTabIndex--;
        } else if (activeTabIndex === index) {
            activeTabIndex = Math.min(index, tabs.length - 1);
        }
        if (activeTabIndex >= 0) {
            tabs[activeTabIndex].wrapperEl.style.display = "block";
            tabs[activeTabIndex].editor.refresh();
        }
        renderTabBar();
    }

    function closeCurrentTab() {
        if (activeTabIndex >= 0) closeTab(activeTabIndex);
    }

    async function saveCurrentTab() {
        if (activeTabIndex < 0) return;
        const tab = tabs[activeTabIndex];
        if (!tab.path) {
            addChatMessage("system", "Use 'New File' to create a file first.");
            return;
        }
        const content = tab.editor.getValue();
        const res = await postJSON("/api/files/save", { path: tab.path, content });
        if (res.error) {
            addChatMessage("error", res.error);
        } else {
            tab.modified = false;
            updateTabLabel(tab);
            addChatMessage("system", `Saved ${tab.name}`);
        }
    }

    function guessMode(filename) {
        const ext = filename.split(".").pop().toLowerCase();
        const map = {
            js: "javascript", mjs: "javascript", jsx: "javascript",
            ts: "javascript", tsx: "javascript",
            py: "python", pyw: "python",
            md: "markdown", mkd: "markdown",
            html: "htmlmixed", htm: "htmlmixed",
            css: "css", scss: "css", less: "css",
            xml: "xml", svg: "xml",
            json: "javascript",
            c: "text/x-csrc", h: "text/x-csrc",
            cpp: "text/x-c++src", hpp: "text/x-c++src",
            java: "text/x-java",
            sh: "shell", bash: "shell", zsh: "shell",
        };
        return map[ext] || "text/plain";
    }

    // ── Context ──────────────────────────────────────────────────────────────
    function updateContextLabel() {
        const n = contextFiles.size;
        $ctxLabel.textContent = `Context: ${n} file${n !== 1 ? "s" : ""}`;
    }

    function clearContext() {
        contextFiles.clear();
        updateContextLabel();
        // Uncheck all checkboxes
        $fileTree.querySelectorAll(".tree-ctx").forEach(cb => cb.checked = false);
    }

    // ── AI Chat ──────────────────────────────────────────────────────────────
    async function sendChat() {
        const msg = $chatInput.value.trim();
        if (!msg) return;
        $chatInput.value = "";
        addChatMessage("user", msg);

        // Build context file list: checked files + current file
        const ctx = [...contextFiles];
        if (activeTabIndex >= 0 && tabs[activeTabIndex].path) {
            const cur = tabs[activeTabIndex].path;
            if (!ctx.includes(cur)) ctx.push(cur);
        }

        addChatMessage("system", "Thinking…");

        try {
            const data = await postJSON("/api/ai/chat", { message: msg, context_files: ctx });
            // Remove "Thinking…"
            const last = $chatHistory.lastElementChild;
            if (last && last.classList.contains("system") && last.textContent.includes("Thinking")) {
                last.remove();
            }
            if (data.error) {
                addChatMessage("error", data.error);
            } else {
                addChatMessage("ai", data.response);
            }
        } catch (err) {
            // Remove "Thinking…"
            const last = $chatHistory.lastElementChild;
            if (last && last.classList.contains("system")) last.remove();
            addChatMessage("error", "Network error: " + err.message);
        }
    }

    function addChatMessage(type, text) {
        const div = document.createElement("div");
        div.className = "chat-msg " + type;
        if (type === "user" || type === "ai") {
            const sender = document.createElement("div");
            sender.className = "chat-sender";
            sender.textContent = type === "user" ? "You" : "AI";
            div.appendChild(sender);
        }
        const body = document.createElement("div");
        body.textContent = text;
        div.appendChild(body);
        $chatHistory.appendChild(div);
        $chatHistory.scrollTop = $chatHistory.scrollHeight;
    }

    // ── Open Folder dialog ───────────────────────────────────────────────────
    function openFolderDialog() {
        document.getElementById("folder-path-input").value = rootFolder || "";
        document.getElementById("folder-overlay").classList.remove("hidden");
        document.getElementById("folder-path-input").focus();
    }
    function closeFolderDialog() {
        document.getElementById("folder-overlay").classList.add("hidden");
    }
    async function doOpenFolder() {
        const path = document.getElementById("folder-path-input").value.trim();
        if (!path) return;
        closeFolderDialog();
        rootFolder = path;
        await loadFileTree(path);
        // Close scripts menu if open
        document.getElementById("scripts-menu").classList.add("hidden");
    }

    // ── New File dialog ──────────────────────────────────────────────────────
    function newFileDialog() {
        document.getElementById("newfile-name").value = "";
        document.getElementById("newfile-overlay").classList.remove("hidden");
        document.getElementById("newfile-name").focus();
    }
    function closeNewFileDialog() {
        document.getElementById("newfile-overlay").classList.add("hidden");
    }
    async function doNewFile() {
        const name = document.getElementById("newfile-name").value.trim();
        if (!name) return;
        closeNewFileDialog();

        if (!rootFolder) {
            // No root folder — just open an in-memory tab
            createTab(null, "");
            return;
        }

        const fullPath = rootFolder + (rootFolder.endsWith("/") || rootFolder.endsWith("\\") ? "" : "/") + name;
        const res = await postJSON("/api/files/new", { path: fullPath });
        if (res.error) {
            addChatMessage("error", res.error);
        } else {
            await loadFileTree(rootFolder);
            createTab(fullPath, "");
        }
    }

    // ── Settings dialog ──────────────────────────────────────────────────────
    function openSettings() {
        document.getElementById("set-url").value = config.llama_cpp_url || "";
        document.getElementById("set-prompt").value = config.system_prompt || "";
        document.getElementById("set-temp").value = config.temperature ?? 0.7;
        document.getElementById("set-max-tokens").value = config.max_tokens ?? 2000;
        document.getElementById("set-font").value = config.editor_font || "";
        document.getElementById("set-line-numbers").checked = config.show_line_numbers !== false;
        document.getElementById("set-wrap").checked = config.wrap_text !== false;
        document.getElementById("set-default-folder").value = config.default_folder || "";
        document.getElementById("set-show-files").checked = config.show_file_panel !== false;
        document.getElementById("set-show-ai").checked = config.show_ai_panel !== false;
        document.getElementById("set-theme").value = config.theme || "layan-dark";
        document.getElementById("settings-overlay").classList.remove("hidden");
    }

    function closeSettings() {
        document.getElementById("settings-overlay").classList.add("hidden");
    }

    async function saveSettings() {
        const updated = {
            llama_cpp_url:    document.getElementById("set-url").value.trim(),
            system_prompt:    document.getElementById("set-prompt").value,
            temperature:      parseFloat(document.getElementById("set-temp").value) || 0.7,
            max_tokens:       parseInt(document.getElementById("set-max-tokens").value) || 2000,
            editor_font:      document.getElementById("set-font").value.trim() || "Monospace 11",
            show_line_numbers:document.getElementById("set-line-numbers").checked,
            wrap_text:        document.getElementById("set-wrap").checked,
            theme:            document.getElementById("set-theme").value,
            default_folder:   document.getElementById("set-default-folder").value.trim(),
            show_file_panel:  document.getElementById("set-show-files").checked,
            show_ai_panel:    document.getElementById("set-show-ai").checked,
        };

        config = await postJSON("/api/config", updated);
        closeSettings();

        // Apply to open editors
        tabs.forEach(t => {
            t.editor.setOption("lineNumbers", config.show_line_numbers !== false);
            t.editor.setOption("lineWrapping", config.wrap_text !== false);
        });

        // Apply theme if changed
        applyTheme(config.theme || "layan-dark");

        addChatMessage("system", "Settings saved.");
    }

    // ── Folder Browser ───────────────────────────────────────────────────────
    let fbrowserCallback = null;
    let fbrowserCurrent = "";

    function openFolderBrowser(startPath, onSelect) {
        fbrowserCallback = onSelect;
        document.getElementById("fbrowser-overlay").classList.remove("hidden");
        loadFolderBrowser(startPath || "");
    }

    function closeFolderBrowser() {
        document.getElementById("fbrowser-overlay").classList.add("hidden");
        fbrowserCallback = null;
    }

    function confirmFolderBrowser() {
        if (fbrowserCallback && fbrowserCurrent) {
            fbrowserCallback(fbrowserCurrent);
        }
        closeFolderBrowser();
    }

    function folderBrowserUp() {
        if (!fbrowserCurrent) return;
        // Go to parent by loading the browse endpoint with current path's parent
        // The API returns parent for us, so just fetch current and use its parent
        const pathEl = document.getElementById("fbrowser-current-path");
        const parent = pathEl.dataset.parent || "";
        loadFolderBrowser(parent);
    }

    async function loadFolderBrowser(path) {
        const data = await api(`/api/files/browse?path=${encodeURIComponent(path)}`);
        fbrowserCurrent = data.current || "";

        const pathEl = document.getElementById("fbrowser-current-path");
        pathEl.textContent = fbrowserCurrent || "(select a drive)";
        pathEl.dataset.parent = data.parent || "";

        // Disable Up button at root
        document.getElementById("fbrowser-up").disabled = !data.parent && !!fbrowserCurrent;

        const list = document.getElementById("fbrowser-list");
        list.innerHTML = "";

        if (!data.dirs || data.dirs.length === 0) {
            list.innerHTML = '<div class="fbrowser-empty">No subdirectories</div>';
            return;
        }

        for (const dir of data.dirs) {
            const item = document.createElement("div");
            item.className = "fbrowser-item";
            item.innerHTML = `<span class="fb-icon">\uD83D\uDCC1</span><span class="fb-name">${escHTML(dir.name)}</span>`;
            item.addEventListener("dblclick", () => loadFolderBrowser(dir.path));
            item.addEventListener("click", () => {
                // Single click selects this subfolder as the target
                list.querySelectorAll(".fbrowser-item").forEach(el => el.classList.remove("selected"));
                item.classList.add("selected");
                fbrowserCurrent = dir.path;
                pathEl.textContent = dir.path;
            });
            list.appendChild(item);
        }
    }

    // ── Scripts ─────────────────────────────────────────────────────────────
    async function toggleScriptsMenu() {
        const menu = document.getElementById("scripts-menu");
        const isHidden = menu.classList.contains("hidden");
        
        if (isHidden) {
            await loadScriptsList();
            menu.classList.remove("hidden");
        } else {
            menu.classList.add("hidden");
        }
    }

    async function loadScriptsList() {
        const list = document.getElementById("scripts-list");
        list.innerHTML = '<div class="script-item empty">Loading...</div>';

        try {
            const data = await api(`/api/scripts/list?folder=${encodeURIComponent(rootFolder || "")}`);
            list.innerHTML = "";

            if (data.error) {
                list.innerHTML = `<div class="script-item empty">${escHTML(data.error)}</div>`;
                return;
            }

            if (!data.scripts || data.scripts.length === 0) {
                list.innerHTML = '<div class="script-item empty">No scripts found. Create a "scripts" folder in your project.</div>';
                return;
            }

            for (const script of data.scripts) {
                const item = document.createElement("div");
                item.className = "script-item";
                item.textContent = script.name;
                item.addEventListener("click", () => runScript(script.path));
                list.appendChild(item);
            }
        } catch (err) {
            list.innerHTML = `<div class="script-item empty">Error: ${escHTML(err.message)}</div>`;
        }
    }

    async function runScript(scriptPath) {
        document.getElementById("scripts-menu").classList.add("hidden");
        addChatMessage("system", `Running script: ${scriptPath.split(/[\\/]/).pop()}...`);

        try {
            const data = await postJSON("/api/scripts/run", { path: scriptPath });
            showScriptOutput(scriptPath, data);
        } catch (err) {
            showScriptOutput(scriptPath, { error: err.message, stdout: "", stderr: "", returncode: -1 });
        }
    }

    function showScriptOutput(scriptPath, result) {
        const title = document.getElementById("script-output-title");
        const content = document.getElementById("script-output-content");
        
        title.textContent = `Script: ${scriptPath.split(/[\\/]/).pop()}`;
        
        let output = "";
        if (result.error) {
            output = `Error: ${result.error}\n\n`;
        }
        if (result.stdout) {
            output += `=== STDOUT ===\n${result.stdout}\n\n`;
        }
        if (result.stderr) {
            output += `=== STDERR ===\n${result.stderr}\n\n`;
        }
        if (result.returncode !== undefined) {
            output += `Return code: ${result.returncode}`;
        }
        if (!output) {
            output = "No output";
        }
        
        content.textContent = output;
        document.getElementById("script-output-overlay").classList.remove("hidden");
    }

    function closeScriptOutput() {
        document.getElementById("script-output-overlay").classList.add("hidden");
    }

    // ── Util ─────────────────────────────────────────────────────────────────
    function escHTML(s) {
        const d = document.createElement("div");
        d.textContent = s;
        return d.innerHTML;
    }

    // ── Boot ─────────────────────────────────────────────────────────────────
    init();
})();
