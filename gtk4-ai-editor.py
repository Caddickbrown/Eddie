#!/usr/bin/env python3
"""
GTK4 AI-Powered Writing Assistant
A lightweight, customizable text editor with llama.cpp integration
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('GtkSource', '5')
from gi.repository import Gtk, GtkSource, Gio, GLib, Gdk, Pango
import json
import os
import subprocess
import sys
import threading
import requests
from pathlib import Path


def _config_path():
    """Config file path; Windows uses AppData/Roaming, Unix uses ~/.config."""
    if sys.platform == "win32":
        return Path.home() / "AppData" / "Roaming" / "ai-writer" / "config.json"
    return Path.home() / ".config" / "ai-writer" / "config.json"


class Config:
    """Simple configuration management"""
    DEFAULT_CONFIG = {
        "llama_cpp_url": "http://localhost:8080",
        "system_prompt": "You are a helpful writing assistant. You have access to the user's files and can help with writing, editing, and improving text.",
        "temperature": 0.7,
        "max_tokens": 2000,
        "context_max_tokens": 6000,
        "editor_font": "Monospace 11",
        "theme": "layan-dark",
        "show_line_numbers": True,
        "wrap_text": True
    }
    
    @staticmethod
    def load():
        config_path = _config_path()
        if config_path.exists():
            with open(config_path) as f:
                return {**Config.DEFAULT_CONFIG, **json.load(f)}
        return Config.DEFAULT_CONFIG.copy()
    
    @staticmethod
    def save(config):
        config_path = _config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)


class EditorTab:
    """Represents an open file tab"""
    def __init__(self, file_path=None):
        self.file_path = file_path
        self.modified = False
        
        # Create source view and buffer
        self.source_view = GtkSource.View()
        self.source_buffer = self.source_view.get_buffer()
        
        # Track modifications
        self.source_buffer.connect("modified-changed", self.on_modified_changed)
        
    def on_modified_changed(self, buffer):
        self.modified = buffer.get_modified()
    
    def get_display_name(self):
        if self.file_path:
            name = os.path.basename(self.file_path)
            return f"*{name}" if self.modified else name
        return "*Untitled" if self.modified else "Untitled"


class AIWriter(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="AI Writing Assistant")
        self.set_default_size(1400, 900)
        
        self.config = Config.load()
        self.root_folder = None
        self.file_contexts = set()  # Paths in AI context
        
        # Tab management
        self.tabs = []  # List of EditorTab objects
        self.current_tab_index = -1
        
        # Panel visibility
        self.file_panel_visible = True
        self.ai_panel_visible = True
        
        self.setup_ui()
        self.create_new_tab()  # Start with one empty tab
        
    def setup_ui(self):
        # Main horizontal paned (file tree | editor | AI panel)
        self.main_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        
        # LEFT: File tree
        self.file_panel = self.create_file_panel()
        self.main_paned.set_start_child(self.file_panel)
        self.main_paned.set_resize_start_child(False)
        self.main_paned.set_shrink_start_child(False)
        
        # MIDDLE + RIGHT: Editor and AI panel
        self.editor_ai_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        
        # MIDDLE: Editor with tabs
        editor_panel = self.create_editor_panel()
        self.editor_ai_paned.set_start_child(editor_panel)
        self.editor_ai_paned.set_resize_start_child(True)
        self.editor_ai_paned.set_shrink_start_child(False)
        
        # RIGHT: AI Chat panel
        self.ai_panel = self.create_ai_panel()
        self.editor_ai_paned.set_end_child(self.ai_panel)
        self.editor_ai_paned.set_resize_end_child(False)
        self.editor_ai_paned.set_shrink_end_child(False)
        
        self.main_paned.set_end_child(self.editor_ai_paned)
        
        # Main container with toolbar
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Toolbar
        toolbar = self.create_toolbar()
        main_box.append(toolbar)
        main_box.append(self.main_paned)
        
        self.set_child(main_box)
    
    def create_toolbar(self):
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.set_margin_start(6)
        toolbar.set_margin_end(6)
        toolbar.set_margin_top(6)
        toolbar.set_margin_bottom(6)
        
        # Open folder button
        open_btn = Gtk.Button(label="Open Folder")
        open_btn.connect("clicked", self.on_open_folder)
        toolbar.append(open_btn)
        
        # New file button
        new_btn = Gtk.Button(label="New File")
        new_btn.connect("clicked", self.on_new_file)
        toolbar.append(new_btn)
        
        # Save button
        save_btn = Gtk.Button(label="Save")
        save_btn.connect("clicked", self.on_save_file)
        toolbar.append(save_btn)
        
        # Close tab button
        close_btn = Gtk.Button(label="Close Tab")
        close_btn.connect("clicked", self.on_close_tab)
        toolbar.append(close_btn)
        
        # Separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        toolbar.append(separator)
        
        # Toggle file panel
        toggle_files_btn = Gtk.ToggleButton(label="Files")
        toggle_files_btn.set_active(True)
        toggle_files_btn.connect("toggled", self.on_toggle_file_panel)
        toolbar.append(toggle_files_btn)
        
        # Toggle AI panel
        toggle_ai_btn = Gtk.ToggleButton(label="AI")
        toggle_ai_btn.set_active(True)
        toggle_ai_btn.connect("toggled", self.on_toggle_ai_panel)
        toolbar.append(toggle_ai_btn)
        
        # Separator
        separator2 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        toolbar.append(separator2)
        
        # Scripts button (popover with list of scripts in project's scripts/ folder)
        self.scripts_popover = Gtk.Popover()
        self.scripts_popover.connect("show", self._refresh_scripts_popover)
        scripts_btn = Gtk.MenuButton(label="Scripts")
        scripts_btn.set_popover(self.scripts_popover)
        toolbar.append(scripts_btn)
        
        # Context label
        self.context_label = Gtk.Label(label="Context: 0 files")
        toolbar.append(self.context_label)
        
        # Clear context button
        clear_ctx_btn = Gtk.Button(label="Clear Context")
        clear_ctx_btn.connect("clicked", self.on_clear_context)
        toolbar.append(clear_ctx_btn)
        
        # Spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        toolbar.append(spacer)
        
        # Settings button
        settings_btn = Gtk.Button(label="Settings")
        settings_btn.connect("clicked", self.on_settings)
        toolbar.append(settings_btn)
        
        return toolbar
    
    def create_file_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_size_request(250, -1)
        
        # Header
        header = Gtk.Label(label="Files")
        header.set_margin_start(6)
        header.set_margin_end(6)
        header.set_margin_top(6)
        header.set_halign(Gtk.Align.START)
        header.set_markup("<b>Files</b>")
        box.append(header)
        
        # Scrolled window for tree
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        
        # Tree store: display_name, full_path, in_context (hierarchical for collapsible folders)
        self.file_store = Gtk.TreeStore(str, str, bool)
        self.file_tree = Gtk.TreeView(model=self.file_store)
        
        # Name column
        renderer_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn("Name", renderer_text, text=0)
        self.file_tree.append_column(column_text)
        
        # Context checkbox column (only meaningful for files)
        renderer_toggle = Gtk.CellRendererToggle()
        renderer_toggle.connect("toggled", self.on_context_toggled)
        column_toggle = Gtk.TreeViewColumn("Ctx", renderer_toggle, active=2)
        self.file_tree.append_column(column_toggle)
        
        # Double-click to open file
        self.file_tree.connect("row-activated", self.on_file_activated)
        
        scrolled.set_child(self.file_tree)
        box.append(scrolled)
        
        return box
    
    def create_editor_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Tab bar with scrolling
        tab_scroll = Gtk.ScrolledWindow()
        tab_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        tab_scroll.set_size_request(-1, 40)
        
        self.tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        tab_scroll.set_child(self.tab_box)
        box.append(tab_scroll)
        
        # Editor stack (holds all open editors)
        self.editor_stack = Gtk.Stack()
        self.editor_stack.set_vexpand(True)
        box.append(self.editor_stack)
        
        return box
    
    def create_ai_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_size_request(400, -1)
        
        # Header
        header = Gtk.Label(label="AI Assistant")
        header.set_margin_start(6)
        header.set_margin_end(6)
        header.set_margin_top(6)
        header.set_halign(Gtk.Align.START)
        header.set_markup("<b>AI Assistant</b>")
        box.append(header)
        
        # Chat history
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_margin_start(6)
        scrolled.set_margin_end(6)
        
        self.chat_view = Gtk.TextView()
        self.chat_view.set_editable(False)
        self.chat_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.chat_view.set_margin_start(6)
        self.chat_view.set_margin_end(6)
        self.chat_buffer = self.chat_view.get_buffer()
        
        scrolled.set_child(self.chat_view)
        box.append(scrolled)
        
        # Input area
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        input_box.set_margin_start(6)
        input_box.set_margin_end(6)
        input_box.set_margin_bottom(6)
        input_box.set_margin_top(6)
        
        self.ai_input = Gtk.Entry()
        self.ai_input.set_placeholder_text("Ask the AI... (use @filename to reference files)")
        self.ai_input.set_hexpand(True)
        self.ai_input.connect("activate", self.on_send_to_ai)
        input_box.append(self.ai_input)
        
        send_btn = Gtk.Button(label="Send")
        send_btn.connect("clicked", self.on_send_to_ai)
        input_box.append(send_btn)
        
        box.append(input_box)
        
        return box
    
    def create_new_tab(self, file_path=None):
        """Create a new editor tab"""
        tab = EditorTab(file_path)
        
        # Configure the editor view
        self.configure_editor_view(tab.source_view)
        
        # Add to stack
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(tab.source_view)
        
        tab_name = f"tab_{len(self.tabs)}"
        self.editor_stack.add_named(scrolled, tab_name)
        
        # Create tab button
        tab_button = Gtk.Button(label=tab.get_display_name())
        tab_button.connect("clicked", lambda w: self.switch_to_tab(len(self.tabs)))
        
        # Track modified state to update button label
        tab.source_buffer.connect("modified-changed", 
                                  lambda b: tab_button.set_label(tab.get_display_name()))
        
        self.tab_box.append(tab_button)
        
        self.tabs.append(tab)
        self.switch_to_tab(len(self.tabs) - 1)
        
        return tab
    
    def configure_editor_view(self, view):
        """Apply configuration to an editor view"""
        view.add_css_class("source-editor")
        view.set_show_line_numbers(self.config['show_line_numbers'])
        view.set_auto_indent(True)
        view.set_indent_width(4)
        view.set_monospace(True)
        view.set_wrap_mode(Gtk.WrapMode.WORD if self.config['wrap_text'] else Gtk.WrapMode.NONE)

        # Set theme
        scheme_manager = GtkSource.StyleSchemeManager.get_default()
        scheme = scheme_manager.get_scheme(self.config['theme'])
        if scheme:
            view.get_buffer().set_style_scheme(scheme)
    
    def switch_to_tab(self, index):
        """Switch to the specified tab"""
        if 0 <= index < len(self.tabs):
            self.current_tab_index = index
            self.editor_stack.set_visible_child_name(f"tab_{index}")
            
            # Update tab button styles (simple highlight)
            for i, child in enumerate(list(self.tab_box)):
                if i == index:
                    child.add_css_class("suggested-action")
                else:
                    child.remove_css_class("suggested-action")
    
    def get_current_tab(self):
        """Get the currently active tab"""
        if 0 <= self.current_tab_index < len(self.tabs):
            return self.tabs[self.current_tab_index]
        return None
    
    def on_toggle_file_panel(self, button):
        """Toggle file panel visibility"""
        self.file_panel_visible = button.get_active()
        self.file_panel.set_visible(self.file_panel_visible)
    
    def on_toggle_ai_panel(self, button):
        """Toggle AI panel visibility"""
        self.ai_panel_visible = button.get_active()
        self.ai_panel.set_visible(self.ai_panel_visible)
    
    def _get_scripts_dir(self):
        """Return Path to project's scripts folder, or None."""
        if not self.root_folder:
            return None
        scripts_dir = self.root_folder / "scripts"
        return scripts_dir if scripts_dir.is_dir() else None
    
    def _refresh_scripts_popover(self, popover):
        """Rebuild popover with list of .py files in scripts/ folder (called when popover is shown)."""
        child = self.scripts_popover.get_child()
        if child:
            self.scripts_popover.set_child(None)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        scripts_dir = self._get_scripts_dir()
        if not scripts_dir:
            label = Gtk.Label(label="Open a folder that contains a 'scripts' folder.")
            label.set_wrap(True)
            label.set_max_width_chars(35)
            box.append(label)
        else:
            py_files = sorted(scripts_dir.glob("*.py"))
            if not py_files:
                label = Gtk.Label(label="No .py files in scripts/")
                box.append(label)
            else:
                listbox = Gtk.ListBox()
                for p in py_files:
                    row = Gtk.ListBoxRow()
                    row.set_child(Gtk.Label(label=p.name))
                    row.script_path = str(p)  # store for _on_script_selected
                    listbox.append(row)
                listbox.connect("row-activated", self._on_script_selected)
                scrolled = Gtk.ScrolledWindow()
                scrolled.set_min_content_height(120)
                scrolled.set_child(listbox)
                box.append(scrolled)
        self.scripts_popover.set_child(box)
    
    def _on_script_selected(self, listbox, row):
        """Run the selected script and show output."""
        path = getattr(row, "script_path", None)
        if path:
            self.scripts_popover.popdown()
            self._run_script(path)
    
    def _run_script(self, script_path):
        """Run script in background thread, then show output dialog."""
        scripts_dir = self._get_scripts_dir()
        cwd = str(scripts_dir) if scripts_dir else None
        
        def run():
            try:
                result = subprocess.run(
                    [sys.executable, script_path],
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                GLib.idle_add(
                    self._show_script_output,
                    script_path,
                    result.stdout or "",
                    result.stderr or "",
                    result.returncode,
                )
            except subprocess.TimeoutExpired:
                GLib.idle_add(
                    self._show_script_output,
                    script_path,
                    "",
                    "Script timed out after 300 seconds.",
                    -1,
                )
            except Exception as e:
                GLib.idle_add(
                    self._show_script_output,
                    script_path,
                    "",
                    str(e),
                    -1,
                )
        
        threading.Thread(target=run, daemon=True).start()
    
    def _show_script_output(self, script_path, stdout, stderr, returncode):
        """Show dialog with script output."""
        dialog = Gtk.Window()
        dialog.set_transient_for(self)
        dialog.set_modal(True)
        dialog.set_title(f"Script: {os.path.basename(script_path)}")
        dialog.set_default_size(500, 400)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        text = Gtk.TextView()
        text.set_editable(False)
        text.set_monospace(True)
        text.set_wrap_mode(Gtk.WrapMode.CHAR)
        buf = text.get_buffer()
        if stdout:
            buf.insert(buf.get_end_iter(), stdout)
        if stderr:
            buf.insert(buf.get_end_iter(), "\n--- stderr ---\n" + stderr)
        buf.insert(buf.get_end_iter(), f"\n\nExit code: {returncode}")
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_child(text)
        box.append(scrolled)
        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda w: dialog.destroy())
        box.append(close_btn)
        dialog.set_child(box)
        dialog.present()
    
    def on_open_folder(self, button):
        dialog = Gtk.FileDialog.new()
        dialog.select_folder(callback=self.on_folder_selected)
    
    def on_folder_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                self.root_folder = Path(folder.get_path())
                self.load_file_tree()
        except GLib.Error:
            pass
    
    def _add_tree_node(self, parent_iter, path):
        """Add a file or folder row; if folder, add children recursively (collapsible)."""
        if path.name.startswith('.'):
            return
        is_dir = path.is_dir()
        display = ("📁 " if is_dir else "📄 ") + path.name
        in_context = (str(path) in self.file_contexts) if not is_dir else False
        row_iter = self.file_store.append(parent_iter, [display, str(path), in_context])
        if is_dir:
            try:
                for item in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                    self._add_tree_node(row_iter, item)
            except PermissionError:
                pass

    def load_file_tree(self):
        self.file_store.clear()
        if not self.root_folder:
            return
        self._add_tree_node(None, self.root_folder)
    
    def on_file_activated(self, tree_view, path, column):
        model = tree_view.get_model()
        iter = model.get_iter(path)
        file_path = model.get_value(iter, 1)
        
        if os.path.isfile(file_path):
            self.open_file(file_path)
    
    def open_file(self, file_path):
        """Open a file in a new tab or switch to existing tab"""
        # Check if already open
        for i, tab in enumerate(self.tabs):
            if tab.file_path == file_path:
                self.switch_to_tab(i)
                return
        
        # Open in new tab
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            tab = self.create_new_tab(file_path)
            tab.source_buffer.set_text(content)
            tab.source_buffer.set_modified(False)
            
            # Auto-detect language
            lang_manager = GtkSource.LanguageManager.get_default()
            language = lang_manager.guess_language(file_path, None)
            if language:
                tab.source_buffer.set_language(language)
        except Exception as e:
            self.show_error(f"Error opening file: {e}")
    
    def on_save_file(self, button):
        """Save the current tab"""
        tab = self.get_current_tab()
        if not tab:
            return
        
        if not tab.file_path:
            # Need to show save dialog
            dialog = Gtk.FileDialog.new()
            dialog.save(callback=self.on_file_save_dialog)
            return
        
        self.save_tab(tab)
    
    def on_file_save_dialog(self, dialog, result):
        """Handle save dialog result"""
        try:
            file = dialog.save_finish(result)
            if file:
                tab = self.get_current_tab()
                if tab:
                    tab.file_path = file.get_path()
                    self.save_tab(tab)
        except GLib.Error:
            pass
    
    def save_tab(self, tab):
        """Save a specific tab to disk"""
        try:
            start = tab.source_buffer.get_start_iter()
            end = tab.source_buffer.get_end_iter()
            content = tab.source_buffer.get_text(start, end, False)
            
            with open(tab.file_path, 'w') as f:
                f.write(content)
            
            tab.source_buffer.set_modified(False)
            self.add_chat_message("System", f"Saved {os.path.basename(tab.file_path)}")
        except Exception as e:
            self.show_error(f"Error saving file: {e}")
    
    def on_new_file(self, button):
        """Create a new empty tab"""
        self.create_new_tab()
    
    def on_close_tab(self, button):
        """Close the current tab"""
        if self.current_tab_index < 0 or not self.tabs:
            return
        
        tab = self.tabs[self.current_tab_index]
        
        # Check if modified
        if tab.modified:
            # TODO: Show confirmation dialog
            pass
        
        # Remove from UI
        tab_name = f"tab_{self.current_tab_index}"
        self.editor_stack.remove(self.editor_stack.get_child_by_name(tab_name))
        
        # Remove tab button
        child = list(self.tab_box)[self.current_tab_index]
        self.tab_box.remove(child)
        
        # Remove from tabs list
        self.tabs.pop(self.current_tab_index)
        
        # Renumber remaining tabs
        for i in range(self.current_tab_index, len(self.tabs)):
            old_name = f"tab_{i+1}"
            new_name = f"tab_{i}"
            child = self.editor_stack.get_child_by_name(old_name)
            if child:
                # GTK4 doesn't have a direct rename, so we need to work around it
                pass
        
        # Switch to adjacent tab
        if self.tabs:
            new_index = min(self.current_tab_index, len(self.tabs) - 1)
            self.switch_to_tab(new_index)
        else:
            self.current_tab_index = -1
            # Create a new empty tab
            self.create_new_tab()
    
    def on_context_toggled(self, widget, path):
        row_iter = self.file_store.get_iter(path)
        file_path = self.file_store.get_value(row_iter, 1)
        if not os.path.isfile(file_path):
            return  # Only files can be in context
        current_state = self.file_store.get_value(row_iter, 2)
        new_state = not current_state
        self.file_store.set_value(row_iter, 2, new_state)
        if new_state:
            self.file_contexts.add(file_path)
        else:
            self.file_contexts.discard(file_path)
        self.update_context_label()
    
    def _clear_context_in_tree(self, model, path, row_iter):
        """Walk tree and set all in_context to False."""
        model.set_value(row_iter, 2, False)
        return False  # continue

    def on_clear_context(self, button):
        self.file_contexts.clear()
        self.file_store.foreach(self._clear_context_in_tree)
        self.update_context_label()
    
    def update_context_label(self):
        count = len(self.file_contexts)
        self.context_label.set_text(f"Context: {count} file{'s' if count != 1 else ''}")
    
    def on_send_to_ai(self, widget):
        user_message = self.ai_input.get_text().strip()
        if not user_message:
            return
        
        self.ai_input.set_text("")
        self.add_chat_message("You", user_message)
        
        # Parse @mentions and add to context temporarily
        mentioned_files = self.parse_mentions(user_message)
        
        # Start AI request in background thread
        thread = threading.Thread(target=self.send_to_llama, args=(user_message, mentioned_files))
        thread.daemon = True
        thread.start()
    
    def parse_mentions(self, text):
        """Extract @filename mentions from text"""
        import re
        mentions = re.findall(r'@([\w\-\.]+)', text)
        mentioned_paths = []
        
        if self.root_folder:
            for mention in mentions:
                # Search for file in tree
                for file_path in Path(self.root_folder).rglob(mention):
                    if file_path.is_file():
                        mentioned_paths.append(str(file_path))
                        break
        
        return mentioned_paths
    
    def build_context(self, mentioned_files):
        """Build context from selected files and current file"""
        context_parts = []
        
        # Add current file
        tab = self.get_current_tab()
        if tab and tab.file_path:
            try:
                start = tab.source_buffer.get_start_iter()
                end = tab.source_buffer.get_end_iter()
                content = tab.source_buffer.get_text(start, end, False)
                context_parts.append(f"=== Current File: {os.path.basename(tab.file_path)} ===\n{content}\n")
            except:
                pass
        
        # Add explicitly selected context files
        for file_path in self.file_contexts:
            if os.path.isfile(file_path):
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                    context_parts.append(f"=== {os.path.basename(file_path)} ===\n{content}\n")
                except:
                    pass
        
        # Add mentioned files
        for file_path in mentioned_files:
            if file_path not in self.file_contexts and (not tab or file_path != tab.file_path):
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                    context_parts.append(f"=== {os.path.basename(file_path)} ===\n{content}\n")
                except:
                    pass
        
        return "\n".join(context_parts)
    
    def send_to_llama(self, user_message, mentioned_files):
        """Send request to llama.cpp server"""
        try:
            context = self.build_context(mentioned_files)
            
            # Build messages
            messages = [
                {"role": "system", "content": self.config['system_prompt']},
            ]
            
            if context:
                messages.append({"role": "system", "content": f"Files in context:\n{context}"})
            
            messages.append({"role": "user", "content": user_message})
            
            # Send to llama.cpp
            response = requests.post(
                f"{self.config['llama_cpp_url']}/v1/chat/completions",
                json={
                    "messages": messages,
                    "temperature": self.config['temperature'],
                    "max_tokens": self.config['max_tokens']
                },
                timeout=120
            )
            
            if response.status_code == 200:
                data = response.json()
                ai_response = data['choices'][0]['message']['content']
                GLib.idle_add(self.add_chat_message, "AI", ai_response)
            else:
                GLib.idle_add(self.add_chat_message, "Error", f"API error: {response.status_code}")
        
        except requests.exceptions.ConnectionError:
            GLib.idle_add(self.add_chat_message, "Error", "Cannot connect to llama.cpp server. Is it running on port 8080?")
        except Exception as e:
            GLib.idle_add(self.add_chat_message, "Error", f"Error: {str(e)}")
    
    def add_chat_message(self, sender, message):
        """Add message to chat view"""
        end_iter = self.chat_buffer.get_end_iter()
        self.chat_buffer.insert(end_iter, f"\n[{sender}]\n{message}\n")
        
        # Auto-scroll to bottom
        mark = self.chat_buffer.create_mark(None, self.chat_buffer.get_end_iter(), False)
        self.chat_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)
    
    def on_settings(self, button):
        dialog = SettingsDialog(self, self.config)
        dialog.present()
    
    def apply_settings(self):
        """Apply settings to all open editors"""
        apply_app_theme(self.config.get('theme', 'layan-dark'))
        apply_editor_font(self.config)
        for tab in self.tabs:
            self.configure_editor_view(tab.source_view)
    
    def show_error(self, message):
        self.add_chat_message("Error", message)


class SettingsDialog(Gtk.Window):
    def __init__(self, parent, config):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_title("Settings")
        self.set_default_size(500, 500)
        
        self.parent_window = parent
        self.config = config.copy()
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        
        # llama.cpp URL
        url_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        url_label = Gtk.Label(label="llama.cpp URL:")
        url_label.set_size_request(150, -1)
        url_label.set_halign(Gtk.Align.START)
        self.url_entry = Gtk.Entry()
        self.url_entry.set_text(self.config['llama_cpp_url'])
        self.url_entry.set_hexpand(True)
        url_box.append(url_label)
        url_box.append(self.url_entry)
        box.append(url_box)
        
        # System prompt
        prompt_label = Gtk.Label(label="System Prompt:")
        prompt_label.set_halign(Gtk.Align.START)
        box.append(prompt_label)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_size_request(-1, 150)
        self.prompt_view = Gtk.TextView()
        self.prompt_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.prompt_buffer = self.prompt_view.get_buffer()
        self.prompt_buffer.set_text(self.config['system_prompt'])
        scrolled.set_child(self.prompt_view)
        box.append(scrolled)
        
        # Temperature
        temp_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        temp_label = Gtk.Label(label="Temperature:")
        temp_label.set_size_request(150, -1)
        temp_label.set_halign(Gtk.Align.START)
        self.temp_spin = Gtk.SpinButton()
        self.temp_spin.set_range(0.0, 2.0)
        self.temp_spin.set_increments(0.1, 0.1)
        self.temp_spin.set_digits(1)
        self.temp_spin.set_value(self.config['temperature'])
        temp_box.append(temp_label)
        temp_box.append(self.temp_spin)
        box.append(temp_box)

        # Editor font
        font_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        font_label = Gtk.Label(label="Editor Font:")
        font_label.set_size_request(150, -1)
        font_label.set_halign(Gtk.Align.START)
        self.font_entry = Gtk.Entry()
        self.font_entry.set_text(self.config.get('editor_font', 'Monospace 11'))
        self.font_entry.set_placeholder_text("e.g. Monospace 11")
        self.font_entry.set_hexpand(True)
        font_box.append(font_label)
        font_box.append(self.font_entry)
        box.append(font_box)

        # Show line numbers checkbox
        self.line_numbers_check = Gtk.CheckButton(label="Show Line Numbers")
        self.line_numbers_check.set_active(self.config['show_line_numbers'])
        box.append(self.line_numbers_check)

        # Wrap text checkbox
        self.wrap_text_check = Gtk.CheckButton(label="Wrap Text")
        self.wrap_text_check.set_active(self.config['wrap_text'])
        box.append(self.wrap_text_check)

        # Theme selector
        theme_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        theme_label = Gtk.Label(label="Theme:")
        theme_label.set_size_request(150, -1)
        theme_label.set_halign(Gtk.Align.START)
        self.theme_dropdown = Gtk.DropDown()
        theme_keys = list(AVAILABLE_THEMES.keys())
        theme_labels = [k.replace('-', ' ').title() for k in theme_keys]
        self.theme_dropdown.set_model(Gtk.StringList.new(theme_labels))
        current = self.config.get('theme', 'layan-dark')
        if current in theme_keys:
            self.theme_dropdown.set_selected(theme_keys.index(current))
        self._theme_keys = theme_keys
        theme_box.append(theme_label)
        theme_box.append(self.theme_dropdown)
        box.append(theme_box)

        # Buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        button_box.set_halign(Gtk.Align.END)
        button_box.set_margin_top(12)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda w: self.close())
        button_box.append(cancel_btn)

        save_btn = Gtk.Button(label="Save")
        save_btn.connect("clicked", self.on_save)
        button_box.append(save_btn)

        box.append(button_box)

        self.set_child(box)

    def on_save(self, button):
        self.config['llama_cpp_url'] = self.url_entry.get_text()
        self.config['temperature'] = self.temp_spin.get_value()
        self.config['editor_font'] = self.font_entry.get_text().strip() or "Monospace 11"
        self.config['show_line_numbers'] = self.line_numbers_check.get_active()
        self.config['wrap_text'] = self.wrap_text_check.get_active()
        self.config['theme'] = self._theme_keys[self.theme_dropdown.get_selected()]

        start = self.prompt_buffer.get_start_iter()
        end = self.prompt_buffer.get_end_iter()
        self.config['system_prompt'] = self.prompt_buffer.get_text(start, end, False)

        Config.save(self.config)
        self.parent_window.config = self.config
        self.parent_window.apply_settings()
        self.close()


def _app_dir():
    """Return the directory containing this script (for bundled assets)."""
    return Path(__file__).resolve().parent


# ── Theme registry ───────────────────────────────────────────────────────────
# Maps a theme key to (theme_subfolder, css_filename, sourceview_scheme_id).
AVAILABLE_THEMES = {
    "layan-dark":  ("layan-dark",  "layan-dark.css",  "layan-dark"),
    "cream-navy":  ("cream-navy",  "cream-navy.css",  "cream-navy"),
}


def _themes_dir():
    """Return the themes/ directory."""
    return _app_dir() / "themes"

_active_css_provider = None  # keeps a ref so we can remove+replace it
_active_font_provider = None


def _register_source_schemes():
    """Register every theme subfolder on the GtkSourceView search path."""
    manager = GtkSource.StyleSchemeManager.get_default()
    search_path = manager.get_search_path() or []
    for _key, (subfolder, _css, _scheme) in AVAILABLE_THEMES.items():
        d = str(_themes_dir() / subfolder)
        if d not in search_path:
            manager.prepend_search_path(d)


def apply_app_theme(theme_key):
    """Load (or hot-swap) the GTK4 CSS for *theme_key*."""
    global _active_css_provider
    display = Gdk.Display.get_default()

    # Remove the old provider if one is active
    if _active_css_provider is not None:
        Gtk.StyleContext.remove_provider_for_display(display, _active_css_provider)
        _active_css_provider = None

    entry = AVAILABLE_THEMES.get(theme_key)
    if entry is None:
        return
    subfolder, css_file, _scheme_id = entry
    css_path = _themes_dir() / subfolder / css_file
    if not css_path.exists():
        return

    provider = Gtk.CssProvider()
    provider.load_from_path(str(css_path))
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
    _active_css_provider = provider


def apply_editor_font(config):
    """Apply editor font from config via CSS (e.g. 'Monospace 11' -> 11pt Monospace)."""
    global _active_font_provider
    display = Gdk.Display.get_default()

    if _active_font_provider is not None:
        Gtk.StyleContext.remove_provider_for_display(display, _active_font_provider)
        _active_font_provider = None

    font_css = config.get("editor_font", "Monospace 11").strip()
    parts = font_css.split()
    if len(parts) >= 2 and parts[-1].isdigit():
        size, fam = parts[-1], " ".join(parts[:-1])
        font_css = f'{size}pt "{fam}"'
    provider = Gtk.CssProvider()
    provider.load_from_string(f".source-editor {{ font: {font_css}; }}")
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
    _active_font_provider = provider


class AIWriterApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id='com.aiwriter.app',
            flags=Gio.ApplicationFlags.NON_UNIQUE
        )

    def do_activate(self):
        _register_source_schemes()
        config = Config.load()
        apply_app_theme(config.get('theme', 'layan-dark'))
        apply_editor_font(config)
        win = AIWriter(self)
        win.present()


if __name__ == '__main__':
    import sys
    app = AIWriterApp()
    app.run(sys.argv)