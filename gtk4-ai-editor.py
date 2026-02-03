#!/usr/bin/env python3
"""
GTK4 AI-Powered Writing Assistant
A lightweight, customizable text editor with llama.cpp integration
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('GtkSource', '5')
from gi.repository import Gtk, GtkSource, Gio, GLib, Pango
import json
import os
import threading
import requests
from pathlib import Path

class Config:
    """Simple configuration management"""
    DEFAULT_CONFIG = {
        "llama_cpp_url": "http://localhost:8080",
        "system_prompt": "You are a helpful writing assistant. You have access to the user's files and can help with writing, editing, and improving text.",
        "temperature": 0.7,
        "max_tokens": 2000,
        "context_max_tokens": 6000,
        "editor_font": "Monospace 11",
        "theme": "cobalt"
    }
    
    @staticmethod
    def load():
        config_path = Path.home() / ".config" / "ai-writer" / "config.json"
        if config_path.exists():
            with open(config_path) as f:
                return {**Config.DEFAULT_CONFIG, **json.load(f)}
        return Config.DEFAULT_CONFIG.copy()
    
    @staticmethod
    def save(config):
        config_path = Path.home() / ".config" / "ai-writer" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)


class FileTreeItem:
    """Represents a file or folder in the tree"""
    def __init__(self, path, is_dir=False):
        self.path = Path(path)
        self.is_dir = is_dir
        self.in_context = False
        self.name = self.path.name


class AIWriter(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="AI Writing Assistant")
        self.set_default_size(1400, 900)
        
        self.config = Config.load()
        self.root_folder = None
        self.open_files = {}  # path -> GtkSourceBuffer
        self.file_contexts = set()  # Paths in AI context
        self.current_file = None
        
        self.setup_ui()
        
    def setup_ui(self):
        # Main horizontal paned (file tree | editor | AI panel)
        main_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        
        # LEFT: File tree
        file_panel = self.create_file_panel()
        main_paned.set_start_child(file_panel)
        main_paned.set_resize_start_child(False)
        main_paned.set_shrink_start_child(False)
        
        # MIDDLE + RIGHT: Editor and AI panel
        editor_ai_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        
        # MIDDLE: Editor with tabs
        editor_panel = self.create_editor_panel()
        editor_ai_paned.set_start_child(editor_panel)
        editor_ai_paned.set_resize_start_child(True)
        editor_ai_paned.set_shrink_start_child(False)
        
        # RIGHT: AI Chat panel
        ai_panel = self.create_ai_panel()
        editor_ai_paned.set_end_child(ai_panel)
        editor_ai_paned.set_resize_end_child(False)
        editor_ai_paned.set_shrink_end_child(False)
        
        main_paned.set_end_child(editor_ai_paned)
        
        # Main container with toolbar
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Toolbar
        toolbar = self.create_toolbar()
        main_box.append(toolbar)
        main_box.append(main_paned)
        
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
        
        # Separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        toolbar.append(separator)
        
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
        
        # Tree view
        self.file_store = Gtk.ListStore(str, str, bool)  # display_name, full_path, in_context
        self.file_tree = Gtk.TreeView(model=self.file_store)
        
        # Name column
        renderer_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn("Name", renderer_text, text=0)
        self.file_tree.append_column(column_text)
        
        # Context checkbox column
        renderer_toggle = Gtk.CellRendererToggle()
        renderer_toggle.connect("toggled", self.on_context_toggled)
        column_toggle = Gtk.TreeViewColumn("Context", renderer_toggle, active=2)
        self.file_tree.append_column(column_toggle)
        
        # Double-click to open file
        self.file_tree.connect("row-activated", self.on_file_activated)
        
        scrolled.set_child(self.file_tree)
        box.append(scrolled)
        
        return box
    
    def create_editor_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Tab bar (simple label for now - would need custom tab widget for multiple files)
        self.tab_label = Gtk.Label(label="No file open")
        self.tab_label.set_margin_start(6)
        self.tab_label.set_margin_top(6)
        self.tab_label.set_halign(Gtk.Align.START)
        box.append(self.tab_label)
        
        # Editor
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        
        self.source_view = GtkSource.View()
        self.source_buffer = self.source_view.get_buffer()
        
        # Configure editor
        self.source_view.set_show_line_numbers(True)
        self.source_view.set_auto_indent(True)
        self.source_view.set_indent_width(4)
        self.source_view.set_monospace(True)
        
        # Set font
        font_desc = Pango.FontDescription(self.config['editor_font'])
        self.source_view.override_font(font_desc)
        
        # Set theme
        scheme_manager = GtkSource.StyleSchemeManager.get_default()
        scheme = scheme_manager.get_scheme(self.config['theme'])
        if scheme:
            self.source_buffer.set_style_scheme(scheme)
        
        scrolled.set_child(self.source_view)
        box.append(scrolled)
        
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
    
    def load_file_tree(self):
        self.file_store.clear()
        if not self.root_folder:
            return
        
        # Load files recursively
        def add_files(path, depth=0):
            try:
                items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
                for item in items:
                    if item.name.startswith('.'):
                        continue
                    
                    display_name = "  " * depth + ("📁 " if item.is_dir() else "📄 ") + item.name
                    in_context = str(item) in self.file_contexts
                    self.file_store.append([display_name, str(item), in_context])
                    
                    if item.is_dir():
                        add_files(item, depth + 1)
            except PermissionError:
                pass
        
        add_files(self.root_folder)
    
    def on_file_activated(self, tree_view, path, column):
        model = tree_view.get_model()
        iter = model.get_iter(path)
        file_path = model.get_value(iter, 1)
        
        if os.path.isfile(file_path):
            self.open_file(file_path)
    
    def open_file(self, file_path):
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            self.source_buffer.set_text(content)
            self.current_file = file_path
            self.tab_label.set_text(os.path.basename(file_path))
            
            # Auto-detect language
            lang_manager = GtkSource.LanguageManager.get_default()
            language = lang_manager.guess_language(file_path, None)
            if language:
                self.source_buffer.set_language(language)
        except Exception as e:
            self.show_error(f"Error opening file: {e}")
    
    def on_save_file(self, button):
        if not self.current_file:
            return
        
        try:
            start = self.source_buffer.get_start_iter()
            end = self.source_buffer.get_end_iter()
            content = self.source_buffer.get_text(start, end, False)
            
            with open(self.current_file, 'w') as f:
                f.write(content)
            
            self.add_chat_message("System", f"Saved {os.path.basename(self.current_file)}")
        except Exception as e:
            self.show_error(f"Error saving file: {e}")
    
    def on_new_file(self, button):
        self.source_buffer.set_text("")
        self.current_file = None
        self.tab_label.set_text("Untitled")
    
    def on_context_toggled(self, widget, path):
        iter = self.file_store.get_iter(path)
        file_path = self.file_store.get_value(iter, 1)
        current_state = self.file_store.get_value(iter, 2)
        
        new_state = not current_state
        self.file_store.set_value(iter, 2, new_state)
        
        if new_state:
            self.file_contexts.add(file_path)
        else:
            self.file_contexts.discard(file_path)
        
        self.update_context_label()
    
    def on_clear_context(self, button):
        self.file_contexts.clear()
        # Update all checkboxes
        iter = self.file_store.get_iter_first()
        while iter:
            self.file_store.set_value(iter, 2, False)
            iter = self.file_store.iter_next(iter)
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
        if self.current_file:
            try:
                with open(self.current_file, 'r') as f:
                    content = f.read()
                context_parts.append(f"=== Current File: {os.path.basename(self.current_file)} ===\n{content}\n")
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
            if file_path not in self.file_contexts and file_path != self.current_file:
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
    
    def show_error(self, message):
        self.add_chat_message("Error", message)


class SettingsDialog(Gtk.Window):
    def __init__(self, parent, config):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_title("Settings")
        self.set_default_size(500, 400)
        
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
        
        start = self.prompt_buffer.get_start_iter()
        end = self.prompt_buffer.get_end_iter()
        self.config['system_prompt'] = self.prompt_buffer.get_text(start, end, False)
        
        Config.save(self.config)
        self.parent_window.config = self.config
        self.close()


class AIWriterApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='com.aiwriter.app')
    
    def do_activate(self):
        win = AIWriter(self)
        win.present()


if __name__ == '__main__':
    app = AIWriterApp()
    app.run(None)
