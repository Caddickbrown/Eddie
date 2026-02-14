"""
Journally Web – Flask backend
Provides API routes for file operations, AI proxy, and config management.
"""

import json
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

import requests as http_requests

app = Flask(__name__)

# ── Config helpers ────────────────────────────────────────────────────────────

def _config_path():
    if sys.platform == "win32":
        return Path.home() / "AppData" / "Roaming" / "ai-writer" / "config.json"
    return Path.home() / ".config" / "ai-writer" / "config.json"


DEFAULT_CONFIG = {
    "llama_cpp_url": "http://localhost:8080",
    "system_prompt": (
        "You are a helpful writing assistant. You have access to the user's "
        "files and can help with writing, editing, and improving text."
    ),
    "temperature": 0.7,
    "max_tokens": 2000,
    "context_max_tokens": 6000,
    "editor_font": "Monospace 11",
    "theme": "layan-dark",
    "show_line_numbers": True,
    "wrap_text": True,
    "default_folder": "",
    "show_file_panel": True,
    "show_ai_panel": True,
}


def load_config():
    path = _config_path()
    if path.exists():
        with open(path) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)


# ── Page routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── Config API ────────────────────────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(load_config())


@app.route("/api/config", methods=["POST"])
def set_config():
    cfg = load_config()
    cfg.update(request.json)
    save_config(cfg)
    return jsonify(cfg)


# ── File tree API ─────────────────────────────────────────────────────────────

def _build_tree(root: Path):
    """Return a nested dict representing the directory tree."""
    entries = []
    try:
        for item in sorted(root.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if item.name.startswith("."):
                continue
            node = {
                "name": item.name,
                "path": str(item),
                "is_dir": item.is_dir(),
            }
            if item.is_dir():
                node["children"] = _build_tree(item)
            entries.append(node)
    except PermissionError:
        pass
    return entries


@app.route("/api/files/browse", methods=["GET"])
def browse_folders():
    """List subdirectories of a given path for the folder browser.

    Query params:
      path – directory to list (empty → list filesystem roots / home)
    Returns { current, parent, dirs: [{name, path}] }
    """
    target = request.args.get("path", "").strip()

    # If no path provided, return sensible roots
    if not target:
        if sys.platform == "win32":
            import string
            drives = []
            for letter in string.ascii_uppercase:
                dp = f"{letter}:\\"
                if os.path.isdir(dp):
                    drives.append({"name": dp, "path": dp})
            return jsonify({"current": "", "parent": "", "dirs": drives})
        else:
            target = str(Path.home())

    p = Path(target)
    if not p.is_dir():
        return jsonify({"current": target, "parent": "", "dirs": [], "error": "Not a directory"}), 400

    parent = str(p.parent) if p.parent != p else ""
    dirs = []
    try:
        for item in sorted(p.iterdir(), key=lambda x: x.name.lower()):
            if item.is_dir() and not item.name.startswith("."):
                dirs.append({"name": item.name, "path": str(item)})
    except PermissionError:
        pass

    return jsonify({"current": str(p), "parent": parent, "dirs": dirs})


@app.route("/api/files/tree", methods=["GET"])
def file_tree():
    folder = request.args.get("folder", "")
    if not folder:
        cfg = load_config()
        folder = cfg.get("default_folder", "")
    if not folder or not Path(folder).is_dir():
        return jsonify({"tree": [], "root": ""})
    return jsonify({"tree": _build_tree(Path(folder)), "root": folder})


@app.route("/api/files/read", methods=["GET"])
def read_file_api():
    fpath = request.args.get("path", "")
    if not fpath or not os.path.isfile(fpath):
        return jsonify({"error": "File not found"}), 404
    try:
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return jsonify({"path": fpath, "content": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/files/save", methods=["POST"])
def save_file_api():
    data = request.json
    fpath = data.get("path", "")
    content = data.get("content", "")
    if not fpath:
        return jsonify({"error": "No path provided"}), 400
    try:
        Path(fpath).parent.mkdir(parents=True, exist_ok=True)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        return jsonify({"ok": True, "path": fpath})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/files/new", methods=["POST"])
def new_file_api():
    data = request.json
    fpath = data.get("path", "")
    if not fpath:
        return jsonify({"error": "No path provided"}), 400
    if os.path.exists(fpath):
        return jsonify({"error": "File already exists"}), 409
    try:
        Path(fpath).parent.mkdir(parents=True, exist_ok=True)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write("")
        return jsonify({"ok": True, "path": fpath})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── AI proxy ──────────────────────────────────────────────────────────────────

# ── Scripts API ──────────────────────────────────────────────────────────────

@app.route("/api/scripts/list", methods=["GET"])
def list_scripts():
    """List .py files in the scripts/ folder of the current project."""
    folder = request.args.get("folder", "")
    if not folder:
        cfg = load_config()
        folder = cfg.get("default_folder", "")
    
    if not folder or not Path(folder).is_dir():
        return jsonify({"scripts": [], "error": "No folder open"})
    
    scripts_dir = Path(folder) / "scripts"
    if not scripts_dir.is_dir():
        return jsonify({"scripts": [], "error": "No 'scripts' folder found"})
    
    try:
        py_files = sorted(scripts_dir.glob("*.py"))
        scripts = [{"name": f.name, "path": str(f)} for f in py_files]
        return jsonify({"scripts": scripts})
    except Exception as e:
        return jsonify({"scripts": [], "error": str(e)})


@app.route("/api/scripts/run", methods=["POST"])
def run_script():
    """Run a Python script and return its output."""
    import subprocess
    data = request.json
    script_path = data.get("path", "")
    
    if not script_path or not os.path.isfile(script_path):
        return jsonify({"error": "Script not found", "stdout": "", "stderr": "", "returncode": -1}), 404
    
    try:
        # Determine working directory (scripts folder if script is in one)
        script_dir = Path(script_path).parent
        cwd = str(script_dir) if script_dir.name == "scripts" else None
        
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return jsonify({
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "returncode": result.returncode,
        })
    except subprocess.TimeoutExpired:
        return jsonify({
            "error": "Script timed out after 300 seconds",
            "stdout": "",
            "stderr": "Script timed out after 300 seconds.",
            "returncode": -1,
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
        })


# ── Theme API ────────────────────────────────────────────────────────────────

@app.route("/api/theme/<theme_key>")
def get_theme(theme_key):
    """Serve the CSS file for a theme, converted from GTK CSS to web CSS."""
    themes_dir = Path(__file__).resolve().parent.parent / "themes"
    theme_map = {
        "layan-dark": "layan-dark/layan-dark.css",
        "cream-navy": "cream-navy/cream-navy.css",
    }
    
    if theme_key not in theme_map:
        return "/* Theme not found */", 404
    
    css_path = themes_dir / theme_map[theme_key]
    if not css_path.exists():
        return "/* Theme file not found */", 404
    
    # Read GTK CSS
    with open(css_path, "r", encoding="utf-8") as f:
        gtk_css = f.read()
    
    # Extract color variables
    import re
    color_vars = {}
    for match in re.finditer(r"@define-color\s+(\w+)\s+([^;]+);", gtk_css):
        var_name = match.group(1)
        var_value = match.group(2).strip()
        color_vars[var_name] = var_value
    
    # Create web-compatible CSS with color variables
    web_css = "/* Web theme converted from GTK CSS */\n\n:root {\n"
    for var_name, var_value in color_vars.items():
        web_css += f"    --{var_name}: {var_value};\n"
    web_css += "}\n\n"
    
    # Apply theme-specific styles
    if theme_key == "layan-dark":
        web_css += """
body {
    background: var(--theme_bg_color);
    color: var(--theme_fg_color);
}
#toolbar {
    background: linear-gradient(to right, var(--gradient_top), var(--gradient_mid));
    color: var(--theme_selected_fg_color);
    border-bottom: 1px solid rgba(0,0,0,0.2);
}
.panel {
    background: var(--sidebar_color);
}
.panel-header {
    background: var(--sidebar_color);
    color: var(--text-secondary);
}
#editor-panel {
    background: var(--theme_bg_color);
}
#tab-bar {
    background: var(--sidebar_color);
}
.tab.active {
    background: var(--theme_bg_color);
    border-bottom-color: var(--primary_color);
}
#toolbar button {
    background: var(--surface_color);
    color: rgba(255,255,255,0.8);
    border-color: var(--border_color);
}
#toolbar button:hover {
    background: rgba(86, 87, 245, 0.25);
    border-color: rgba(86, 87, 245, 0.4);
}
#toolbar button.toggle-btn.active {
    background: rgba(86, 87, 245, 0.35);
    border-color: rgba(86, 87, 245, 0.5);
}
.modal {
    background: var(--surface_color);
    color: rgba(255,255,255,0.8);
    border-color: var(--border_color);
}
.modal-body input, .modal-body textarea, .modal-body select {
    background: var(--theme_base_color);
    color: var(--theme_fg_color);
    border-color: var(--border_color);
}
.modal-body input:focus, .modal-body textarea:focus, .modal-body select:focus {
    border-color: var(--primary_color);
}
#chat-input {
    background: var(--theme_base_color);
    color: var(--theme_fg_color);
    border-color: var(--border_color);
}
#chat-input:focus {
    border-color: var(--primary_color);
}
.chat-msg.ai {
    background: var(--theme_base_color);
}
.chat-msg.user {
    background: rgba(86, 87, 245, 0.25);
}
.tree-row:hover {
    background: rgba(86, 87, 245, 0.12);
}
"""
    elif theme_key == "cream-navy":
        web_css += """
body {
    background: var(--theme_bg_color);
    color: var(--theme_fg_color);
}
#toolbar {
    background: var(--primary_color);
    color: var(--theme_selected_fg_color);
    border-bottom: 1px solid var(--deep_navy);
}
.panel {
    background: var(--sidebar_color);
}
.panel-header {
    background: var(--sidebar_color);
    color: var(--text-secondary);
}
#editor-panel {
    background: var(--theme_bg_color);
}
#tab-bar {
    background: var(--surface_color);
}
.tab.active {
    background: var(--theme_bg_color);
    border-bottom-color: var(--primary_color);
}
#toolbar button {
    background: var(--surface_color);
    color: var(--theme_fg_color);
    border-color: var(--border_color);
}
#toolbar button:hover {
    background: var(--craft_tan);
    color: var(--ink_dark);
    border-color: rgba(27,42,74,0.25);
}
#toolbar button.toggle-btn.active {
    background: var(--primary_color);
    color: var(--theme_selected_fg_color);
    border-color: var(--primary_color);
}
.modal {
    background: var(--lighter_bg);
    color: var(--theme_fg_color);
    border-color: var(--border_color);
}
.modal-body input, .modal-body textarea, .modal-body select {
    background: var(--lighter_bg);
    color: var(--theme_fg_color);
    border-color: var(--border_color);
}
.modal-body input:focus, .modal-body textarea:focus, .modal-body select:focus {
    border-color: var(--accent_color);
}
#chat-input {
    background: var(--lighter_bg);
    color: var(--theme_fg_color);
    border-color: var(--border_color);
}
#chat-input:focus {
    border-color: var(--accent_color);
}
.chat-msg.ai {
    background: var(--lighter_bg);
}
.chat-msg.user {
    background: rgba(27, 42, 74, 0.15);
}
.tree-row:hover {
    background: rgba(27, 42, 74, 0.05);
}
"""
    
    return web_css, 200, {"Content-Type": "text/css"}


@app.route("/api/ai/chat", methods=["POST"])
def ai_chat():
    """Proxy chat request to the llama.cpp server."""
    cfg = load_config()
    data = request.json
    user_message = data.get("message", "")
    context_files = data.get("context_files", [])

    # Build messages list
    messages = [{"role": "system", "content": cfg["system_prompt"]}]

    # Build file context
    context_parts = []
    for fp in context_files:
        if os.path.isfile(fp):
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                context_parts.append(f"=== {os.path.basename(fp)} ===\n{content}\n")
            except Exception:
                pass
    if context_parts:
        messages.append({"role": "system", "content": "Files in context:\n" + "\n".join(context_parts)})

    messages.append({"role": "user", "content": user_message})

    try:
        resp = http_requests.post(
            f"{cfg['llama_cpp_url']}/v1/chat/completions",
            json={
                "messages": messages,
                "temperature": cfg["temperature"],
                "max_tokens": cfg["max_tokens"],
            },
            timeout=120,
        )
        if resp.status_code == 200:
            ai_msg = resp.json()["choices"][0]["message"]["content"]
            return jsonify({"response": ai_msg})
        return jsonify({"error": f"API error: {resp.status_code}"}), 502
    except http_requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to llama.cpp server."}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
