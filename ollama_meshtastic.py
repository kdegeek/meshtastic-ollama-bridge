# Copyright (C) 2025 Jakub Budrewicz
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import tkinter as tk
from tkinter import ttk, messagebox
import platform
import os
from threading import Thread
from logger import GUILogger
from meshtastic_handler import MeshtasticHandler
from ollama_handler import OllamaHandler
from gui_components import GUIComponents
from web_server import start_flask_app
from config_manager import load_settings, save_settings, DEFAULT_SETTINGS
from tkinter import filedialog

class MeshtasticOllamaGUI:
    """Main application class for the Meshtastic-Ollama Bridge GUI."""
    
    def __init__(self, root):
        """Initialize the application.
        
        Args:
            root: The tkinter root window
        """
        self.root = root
        self.root.title("Meshtastic-Ollama Bridge")
        self.root.geometry("600x800") # Consider making this configurable too eventually

        # Load application settings
        self.settings_filepath = "settings.json"
        self.app_settings = load_settings(self.settings_filepath)

        # Initialize logger to None first, it will be created after log_text widget
        self.logger = None
        
        # Setup GUI components (which creates self.log_text)
        self.setup_gui()
        
        # Now initialize logger as self.log_text exists
        self.logger = GUILogger(self.log_text)
        self.schedule_log_processing() # Start processing the log queue

        # Initialize handlers, passing the reconnection callback to MeshtasticHandler
        self.meshtastic = MeshtasticHandler(
            self.logger,
            self.on_message_received,
            reconnection_status_callback=self.update_reconnection_status # New callback
        )
        self.ollama = OllamaHandler(self.logger)
        
        # State variables
        self.conversation_started = False
        # web_service_enabled is now loaded from app_settings, apply it after UI setup
        self.web_service_enabled = tk.BooleanVar()
        self.flask_thread = None
        
        # Apply loaded settings to UI elements
        # This needs to be after all UI elements are created by setup_gui -> setup_settings_tab
        self.apply_settings_to_ui(self.app_settings)

        # Update context length from potentially loaded history
        self.update_context_length()

        # Load dynamic data like models and ports AFTER applying static settings
        self.refresh_models() # This might re-set model if "" was loaded, which is fine
        self.refresh_ports()  # This might re-set port if "" was loaded

        # Graceful exit
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)


    def apply_settings_to_ui(self, settings_to_apply):
        """Applies loaded or imported settings to the UI components."""
        if self.logger:
            self.logger.log("Applying settings to UI.", "Info")

        # Ollama Model
        self.model_combo.set(settings_to_apply.get("ollama_model", DEFAULT_SETTINGS["ollama_model"]))

        # Meshtastic Connection Type
        self.connection_type_combo.set(settings_to_apply.get("meshtastic_connection_type", DEFAULT_SETTINGS["meshtastic_connection_type"]))
        self.on_connection_type_change() # This is crucial to show/hide port or host entry

        # Meshtastic Serial Port (only if type is Serial)
        if self.connection_type_combo.get() == "Serial":
            self.port_combo.set(settings_to_apply.get("meshtastic_serial_port", DEFAULT_SETTINGS["meshtastic_serial_port"]))

        # Meshtastic Network Host (only if type is Network)
        if self.connection_type_combo.get() == "Network":
            self.hostname_entry.delete(0, tk.END)
            self.hostname_entry.insert(0, settings_to_apply.get("meshtastic_network_host", DEFAULT_SETTINGS["meshtastic_network_host"]))

        # Web Service Enabled
        self.web_service_enabled.set(settings_to_apply.get("web_service_enabled", DEFAULT_SETTINGS["web_service_enabled"]))
        # self.toggle_web_service() # Optionally auto-start web service if enabled, or let user do it. For now, just set the checkbox.

        # Selected Tab
        try:
            self.notebook.select(settings_to_apply.get("selected_tab_index", DEFAULT_SETTINGS["selected_tab_index"]))
        except tk.TclError: # Handle cases where tab index might be invalid (e.g. if tabs change in future)
            if self.logger:
                self.logger.log(f"Invalid tab index in settings: {settings_to_apply.get('selected_tab_index')}. Defaulting to 0.", "Warning")
            self.notebook.select(DEFAULT_SETTINGS["selected_tab_index"])

    def gather_current_settings(self):
        """Gathers current settings from UI components into a dictionary."""
        settings = {
            "ollama_model": self.model_combo.get(),
            "meshtastic_connection_type": self.connection_type_combo.get(),
            "meshtastic_serial_port": self.port_combo.get() if self.connection_type_combo.get() == "Serial" else "",
            "meshtastic_network_host": self.hostname_entry.get() if self.connection_type_combo.get() == "Network" else "",
            "web_service_enabled": self.web_service_enabled.get(),
            "selected_tab_index": self.notebook.index(self.notebook.select()) # Get current selected tab index
        }
        return settings

    def setup_gui(self):
        """Set up the GUI components."""
        # Create main notebook with tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create Settings tab
        self.settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_frame, text="Settings")
        
        # Create Conversation tab
        self.conversation_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.conversation_frame, text="Conversation")
        
        # Setup the settings tab
        self.setup_settings_tab()
        
        # Setup the conversation tab
        self.setup_conversation_tab()
        
    def schedule_log_processing(self):
        """Periodically process the GUILogger's queue."""
        if self.logger: # Ensure logger is initialized
            self.logger.process_log_queue()
        self.root.after(100, self.schedule_log_processing) # Check every 100ms

    def update_reconnection_status(self, is_reconnecting, attempt_message=None):
        """Update the status label based on reconnection attempts."""
        if is_reconnecting:
            status_text = "Reconnecting"
            if attempt_message:
                status_text += f": {attempt_message}"
            self.status_label.config(text=status_text, foreground="orange")
        else:
            # Reconnection attempt finished, check current actual connection status
            if self.meshtastic.is_connected:
                connection_type = self.connection_type_combo.get()
                self.status_label.config(text=f"Connected via {connection_type}", foreground="green")
            else:
                self.status_label.config(text="Connection Failed", foreground="red")
        self.root.update_idletasks() # Ensure UI updates immediately

    def setup_settings_tab(self):
        """Set up the settings tab with Ollama and Meshtastic settings."""
        # Create frames for Ollama and Meshtastic settings
        settings_label = ttk.Label(self.settings_frame, text="Configure your connection settings", font=("TkDefaultFont", 12))
        settings_label.pack(pady=10)
        
        # Ollama Settings Section
        ollama_frame = GUIComponents.create_labeled_frame(self.settings_frame, "Ollama Settings")
        
        # Model Selection
        model_label = ttk.Label(ollama_frame, text="Select AI Model:")
        model_label.pack(anchor='w', pady=(5, 0))
        
        self.model_combo = GUIComponents.create_combobox(ollama_frame)
        
        self.refresh_models_btn = GUIComponents.create_button(
            ollama_frame, "Refresh Models", self.refresh_models, pady=5
        )
        
        # Meshtastic Settings Section
        meshtastic_frame = GUIComponents.create_labeled_frame(self.settings_frame, "Meshtastic Settings")
        
        # Connection Type Selection
        connection_type_label = ttk.Label(meshtastic_frame, text="Connection Type:")
        connection_type_label.pack(anchor='w', pady=(5,0))
        self.connection_type_combo = GUIComponents.create_combobox(
            meshtastic_frame, values=["Serial", "Network"]
        )
        self.connection_type_combo.set("Serial") # Default value
        self.connection_type_combo.bind('<<ComboboxSelected>>', self.on_connection_type_change)

        # Port Selection (Serial)
        self.port_label = ttk.Label(meshtastic_frame, text="Select Device Port:")
        self.port_label.pack(anchor='w', pady=(5, 0))
        
        self.port_combo = GUIComponents.create_combobox(meshtastic_frame)
        
        self.refresh_ports_btn = GUIComponents.create_button(
            meshtastic_frame, "Refresh Ports", self.refresh_ports, pady=5
        )
        
        # Hostname Input (Network)
        self.hostname_label = ttk.Label(meshtastic_frame, text="Enter Hostname/IP:")
        self.hostname_label.pack(anchor='w', pady=(5,0))
        self.hostname_entry = GUIComponents.create_entry(meshtastic_frame)

        # Initially hide network-specific widgets
        self.hostname_label.pack_forget()
        self.hostname_entry.pack_forget()

        # Channel Selection
        channel_label = ttk.Label(meshtastic_frame, text="Select Channel:")
        channel_label.pack(anchor='w', pady=(5, 0))
        
        self.channel_combo = GUIComponents.create_combobox(meshtastic_frame, state="disabled")
        self.channel_combo.bind('<<ComboboxSelected>>', self.on_channel_select)
        
        # Connection button
        self.connect_btn = GUIComponents.create_button(
            meshtastic_frame, "Connect", self.toggle_connection, pady=10
        )
        
        # Web Service Toggle
        web_service_frame = GUIComponents.create_labeled_frame(self.settings_frame, "Web Service")
        self.web_service_check = ttk.Checkbutton(
            web_service_frame,
            text="Enable Web Service (Experimental)",
            variable=self.web_service_enabled,
            command=self.toggle_web_service
        )
        self.web_service_check.pack(anchor='w', padx=5, pady=5)

        # Status indicator
        status_frame = ttk.Frame(self.settings_frame)
        status_frame.pack(fill='x', pady=10)
        
        status_label = ttk.Label(status_frame, text="Status:")
        status_label.pack(side='left')
        
        self.status_label = ttk.Label(status_frame, text="Not Connected")
        self.status_label.pack(side='left', padx=5)

        # Settings Import/Export Section
        config_io_frame = GUIComponents.create_labeled_frame(self.settings_frame, "Configuration Management")

        self.import_settings_btn = GUIComponents.create_button(
            config_io_frame, "Import Settings", self.import_settings_action, side='left', padx=5, pady=5
        )
        self.export_settings_btn = GUIComponents.create_button(
            config_io_frame, "Export Settings", self.export_settings_action, side='left', padx=5, pady=5
        )

    def setup_conversation_tab(self):
        """Set up the conversation tab with logs and controls."""
        # Ensure handlers are initialized before any potential web service start
        if not self.meshtastic:
             self.meshtastic = MeshtasticHandler(self.logger, self.on_message_received)
        if not self.ollama:
            self.ollama = OllamaHandler(self.logger)

        # Conversation controls
        controls_frame = ttk.Frame(self.conversation_frame)
        controls_frame.pack(fill='x', pady=10)
        
        # Start/Stop conversation button
        self.start_conv_btn = GUIComponents.create_button(
            controls_frame, "Start Conversation", self.start_conversation, 
            side='left', padx=5, state='disabled'
        )
        
        # Context management
        context_frame = ttk.Frame(controls_frame)
        context_frame.pack(side='right')
        
        self.view_context_btn = GUIComponents.create_button(
            context_frame, "View Context", self.view_context, side='left', padx=5
        )
        
        self.clear_context_btn = GUIComponents.create_button(
            context_frame, "Clear Context", self.clear_context, side='left'
        )
        
        # Context length indicator
        context_info_frame = ttk.Frame(self.conversation_frame)
        context_info_frame.pack(fill='x', pady=(0, 5))
        
        self.context_length_label = ttk.Label(context_info_frame, text="Context: 0 messages")
        self.context_length_label.pack(side='left')
        
        # Clear logs button
        self.clear_logs_btn = GUIComponents.create_button(
            context_info_frame, "Clear Logs", self.clear_logs, side='right'
        )
        
        # Message log
        log_frame = ttk.LabelFrame(self.conversation_frame, text="Message Log")
        log_frame.pack(fill='both', expand=True, pady=5)
        
        self.log_text = GUIComponents.create_text_widget(log_frame)
        
    # ===== UI Action Methods =====
    
    def refresh_models(self):
        """Refresh the list of available Ollama models."""
        models = self.ollama.get_available_models()
        self.model_combo['values'] = models
        if models:
            self.model_combo.set(models[0])
    
    def refresh_ports(self):
        """Refresh the list of available connection targets (serial ports)."""
        selected_type = self.connection_type_combo.get()
        if selected_type == "Serial":
            ports = self.meshtastic.get_connection_targets() # Use renamed method
            self.port_combo['values'] = ports
            if ports:
                self.port_combo.set(ports[0])
            else:
                self.port_combo.set('') # Clear if no ports found
        # For "Network", do nothing for now (no discovery)
    
    def on_connection_type_change(self, event=None):
        """Handle changes in connection type selection."""
        selected_type = self.connection_type_combo.get()
        if selected_type == "Serial":
            self.port_label.pack(anchor='w', pady=(5, 0))
            self.port_combo.pack(fill='x', padx=5, pady=(0,5))
            self.refresh_ports_btn.pack(fill='x', padx=5, pady=5)

            self.hostname_label.pack_forget()
            self.hostname_entry.pack_forget()
            self.refresh_ports() # Populate serial ports
        elif selected_type == "Network":
            self.port_label.pack_forget()
            self.port_combo.pack_forget()
            self.refresh_ports_btn.pack_forget()

            self.hostname_label.pack(anchor='w', pady=(5,0))
            self.hostname_entry.pack(fill='x', padx=5, pady=(0,5))
            self.port_combo.set('') # Clear port selection
            self.hostname_entry.delete(0, tk.END) # Clear hostname entry

    def toggle_connection(self):
        """Connect to or disconnect from the Meshtastic device."""
        if self.meshtastic.is_connected:
            self.disconnect()
        else:
            self.connect()
    
    def connect(self):
        """Connect to the Meshtastic device."""
        # Get selected model and set it
        model = self.model_combo.get()
        if not model:
            messagebox.showerror("Error", "Please select an Ollama model")
            return
        self.ollama.set_model(model)
        
        # Get selected model and set it
        model = self.model_combo.get()
        if not model:
            messagebox.showerror("Error", "Please select an Ollama model")
            return
        self.ollama.set_model(model)

        connection_type = self.connection_type_combo.get()
        self.meshtastic.connection_type = connection_type.lower() # Update handler's connection type

        target = None
        if connection_type == "Serial":
            target = self.port_combo.get()
            if not target:
                messagebox.showerror("Error", "Please select a serial port.")
                return
        elif connection_type == "Network":
            target = self.hostname_entry.get().strip() # Remove leading/trailing whitespace
            if not target:
                messagebox.showerror("Error", "Please enter a hostname or IP address.")
                return
            # Basic validation for hostname/IP: no whitespace within, and some minimal length.
            # This is not a comprehensive validation.
            if ' ' in target or len(target) < 3:
                messagebox.showerror("Invalid Input", "Hostname/IP address cannot contain spaces and must be at least 3 characters long.")
                return
            # A more robust validation might involve regex or a library, but keeping it simple for now.
            # Example: import re; if not re.match(r"^[a-zA-Z0-9.-]+$", target): ...

        if not target: # Should not happen if logic above is correct
            messagebox.showerror("Error", "No connection target specified.")
            return

        # Update status label before attempting to connect
        self.status_label.config(text=f"Connecting to {target}...", foreground="blue")
        self.root.update_idletasks() # Ensure UI updates immediately

        if self.meshtastic.connect(target):
            self.connect_btn.config(text="Disconnect")
            self.status_label.config(text=f"Connected via {connection_type}")
            self.status_label.config(foreground="green")
            self.root.after(2000, self.update_channels)
            # Switch to conversation tab after successful connection
            self.notebook.select(1)  # Select the conversation tab (index 1)
        else:
            self.status_label.config(text="Connection Failed")
            self.status_label.config(foreground="red")
            # Do not switch tab if connection failed
    
    def disconnect(self):
        """Disconnect from the Meshtastic device."""
        self.meshtastic.disconnect()
        self.conversation_started = False
        self.connect_btn.config(text="Connect")
        self.status_label.config(text="Not Connected")
        self.status_label.config(foreground="black")
        self.channel_combo.set('')
        self.channel_combo.config(state='disabled')
        self.start_conv_btn.config(state='disabled')
        # Reset connection type combo to Serial and refresh UI for it
        # This ensures a consistent state if user tries to connect again
        # self.connection_type_combo.set("Serial")
        # self.on_connection_type_change() # Update UI based on "Serial"
    
    def update_channels(self):
        """Update the channel selection dropdown."""
        channel_names = self.meshtastic.get_channels()
        self.channel_combo.config(state='readonly')
        self.channel_combo['values'] = channel_names
        if channel_names:
            self.channel_combo.set(channel_names[0]) # Default to first channel (usually Primary)
            self.meshtastic.set_channel(channel_names[0]) # Ensure handler also knows
            self.start_conv_btn.config(state='normal')
        else:
            self.channel_combo.set('')
            self.channel_combo.config(state='disabled')
            self.start_conv_btn.config(state='disabled')
    
    def on_channel_select(self, event):
        """Handle channel selection event."""
        selected = self.channel_combo.get()
        if selected:
            self.meshtastic.set_channel(selected)
    
    def on_message_received(self, text):
        """Handle received messages from Meshtastic."""
        if self.conversation_started:
            response_text = self.ollama.get_response(text)
            self.logger.log(response_text, "AI Response")
            self.meshtastic.send_message(response_text)
            self.update_context_length()
    
    def start_conversation(self):
        """Start or stop the conversation."""
        if not self.meshtastic.is_connected:
            messagebox.showerror("Error", "Please connect to a device first")
            return
            
        if not self.conversation_started:
            # Start conversation
            model_name = self.ollama.selected_model
            greeting = f"Hello! I'm running with the {model_name} model. How can I help you?"
            
            # Send the greeting
            success = self.meshtastic.send_message(greeting)
            
            if success:
                self.conversation_started = True
                self.logger.log(greeting, "AI Greeting")
                self.start_conv_btn.config(text="Stop Conversation")
                self.logger.log("Conversation started")
            else:
                self.logger.log("Failed to start conversation", "Error")
        else:
            # Stop conversation
            self.conversation_started = False
            self.start_conv_btn.config(text="Start Conversation")
            self.logger.log("Conversation stopped")
    
    def view_context(self):
        """View the conversation context."""
        history = self.ollama.get_conversation_history()
        GUIComponents.create_context_viewer(self.root, history)
    
    def clear_context(self):
        """Clear the conversation context."""
        if messagebox.askyesno("Clear Context", 
                             "Are you sure you want to clear the conversation context?"):
            self.ollama.clear_conversation_history()
            self.update_context_length()
    
    def update_context_length(self):
        """Update the context length display."""
        count = self.ollama.get_conversation_length()
        self.context_length_label.config(text=f"Context: {count} messages")
    
    def clear_logs(self):
        """Clear the message logs."""
        if messagebox.askyesno("Clear Logs", "Are you sure you want to clear the message log?"):
            if self.logger: # Ensure logger is initialized
                self.logger.clear()

    def on_closing(self):
        """Handle window closing event for graceful shutdown."""
        if self.logger:
            self.logger.log("Application shutting down...", "Info")

        # Save current settings before exiting
        current_ui_settings = self.gather_current_settings()
        save_settings(current_ui_settings, self.settings_filepath)
        if self.logger:
            self.logger.log(f"Current settings saved to {self.settings_filepath}", "Info")

        if self.meshtastic:
            self.meshtastic.disconnect() # Disconnect Meshtastic interface

        if self.flask_thread and self.flask_thread.is_alive():
            if self.logger:
                self.logger.log("Flask web service (daemon thread) will terminate with the application.", "Info")
            # As noted before, graceful Flask shutdown is complex; daemon thread handles exit.

        self.root.destroy() # Close the Tkinter window

    def import_settings_action(self):
        """Handles the 'Import Settings' button action."""
        filepath = filedialog.askopenfilename(
            title="Import Settings File",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not filepath:
            return # User cancelled

        try:
            loaded_s = load_settings(filepath)
            self.app_settings.update(loaded_s) # Merge imported settings
            self.apply_settings_to_ui(self.app_settings)
            # Save imported settings as the new default for this application instance
            save_settings(self.app_settings, self.settings_filepath)
            if self.logger:
                self.logger.log(f"Settings imported from {filepath} and applied.", "Info")
            messagebox.showinfo("Import Successful", f"Settings successfully imported from {filepath} and applied.")
        except Exception as e:
            if self.logger:
                self.logger.log(f"Error importing settings from {filepath}: {e}", "Error")
            messagebox.showerror("Import Failed", f"Could not import settings from {filepath}.\nError: {e}")

    def export_settings_action(self):
        """Handles the 'Export Settings' button action."""
        filepath = filedialog.asksaveasfilename(
            title="Export Settings File",
            defaultextension=".json",
            initialfile="ollama_meshtastic_settings.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not filepath:
            return # User cancelled

        current_s = self.gather_current_settings()
        if save_settings(current_s, filepath):
            if self.logger:
                self.logger.log(f"Current settings exported to {filepath}.", "Info")
            messagebox.showinfo("Export Successful", f"Current settings successfully exported to {filepath}.")
        else:
            if self.logger:
                self.logger.log(f"Failed to export settings to {filepath}.", "Error")
            messagebox.showerror("Export Failed", f"Could not export settings to {filepath}.")

    def toggle_web_service(self):
        """Start or stop the Flask web service."""
        if self.web_service_enabled.get():
            if not self.meshtastic or not self.ollama:
                self.logger.log("Handlers not initialized. Cannot start web service.", "Error")
                messagebox.showerror("Error", "Handlers not initialized. Connect to Meshtastic and select an Ollama model first.")
                self.web_service_enabled.set(False) # Uncheck the box
                return

            if not self.flask_thread or not self.flask_thread.is_alive():
                self.logger.log("Starting Flask web service...", "Info")
                # Ensure handlers are passed to the thread
                self.flask_thread = Thread(target=start_flask_app, args=(self.meshtastic, self.ollama), daemon=True)
                self.flask_thread.start()
                self.logger.log("Flask web service started in a separate thread.", "Info")
            else:
                self.logger.log("Web service thread is already running.", "Info")
        else:
            if self.flask_thread and self.flask_thread.is_alive():
                self.logger.log("Stopping Flask web service (placeholder - proper shutdown TBD)...", "Info")
                # Proper shutdown of a Flask dev server from another thread is non-trivial.
                # For now, we rely on daemon=True to exit when the main app exits.
                # A more robust solution might involve a shutdown endpoint or other IPC.
                # self.flask_thread.join(timeout=1) # Example, but not effective for dev server
                # Forcing exit like this is not clean:
                # if hasattr(self.flask_thread, '_stop'): self.flask_thread._stop()
                self.logger.log("Web service thread will terminate when the application closes (due to daemon=True).", "Info")
            else:
                self.logger.log("Web service is not running or thread is not alive.", "Info")


if __name__ == "__main__":
    root = tk.Tk()
    app = MeshtasticOllamaGUI(root)
    root.mainloop()
