# Eddie

A writing-focused text editor for Linux and macOS with an integrated AI assistant. Eddie uses GTK4 and GtkSourceView for the UI and connects to a local [llama.cpp](https://github.com/ggerganov/llama.cpp) server for chat completions, so you can work on drafts and get help without sending data to the cloud.

## Features

- **Three-panel layout** — File tree | Editor | AI chat
- **File context** — Checkboxes next to files to include them in AI context
- **@-mentions** — Type `@filename.md` in chat to reference specific files
- **Current file auto-context** — The file you’re editing is always included in context
- **Syntax highlighting** — GtkSourceView with 300+ languages
- **Settings** — System prompt, temperature, and llama.cpp URL
- **Config persistence** — Stored in `~/.config/ai-writer/config.json`

## Requirements

- Python 3
- GTK 4 and GtkSourceView 5 (via PyGObject)
- A running llama.cpp server with a compatible model

## Setup

### 1. Install dependencies

**Ubuntu / Debian:**

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-gtksource-5
```

**macOS (Homebrew):**

```bash
brew install gtk4 gtksourceview5 pygobject3
```

**Python packages:**

```bash
pip install requests
```

### 2. Start the llama.cpp server

Download [llama.cpp](https://github.com/ggerganov/llama.cpp) and a GGUF model, then run the server, for example:

```bash
./server -m /path/to/your/model.gguf -c 4096 --port 8080
```

### 3. Run Eddie

```bash
python gtk4-ai-editor.py
```

## How to use

1. **Open folder** — Click **Open Folder** to set your project root.
2. **Set context** — Use the checkboxes next to files to include them in the AI context.
3. **Edit** — Double-click a file in the tree to open it in the editor.
4. **Chat** — Type in the chat box; use `@filename` to reference files.
5. **Save** — Click **Save** or use **Ctrl+S** (when supported).

## Example AI queries

- “Summarize @chapter1.md”
- “Make this paragraph more concise” (uses the current file)
- “What are the main themes across all selected files?”
- “Help me write a conclusion for this essay”

## Settings

In **Settings** you can change:

- **llama.cpp URL** — Default `http://localhost:8080`
- **System prompt** — Instructions for the AI (e.g. tone, focus)
- **Temperature** — Sampling temperature (0–2)

## Roadmap

- **Multi-file editing** — Tabs or notebook for multiple open files; AI suggestions across files
- **Apply AI changes** — Parse code blocks from replies, “Apply” button, optional diff view
- **Script runner** — Terminal panel to run scripts (e.g. Python) with current file or selection as input
