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
from logger import GUILogger
from meshtastic_handler import MeshtasticHandler
from ollama_handler import OllamaHandler
from gui_components import GUIComponents

class MeshtasticOllamaGUI:
    """Main application class for the Meshtastic-Ollama Bridge GUI."""
    
    def __init__(self, root):
        """Initialize the application.
        
        Args:
            root: The tkinter root window
        """
        self.root = root
        self.root.title("Meshtastic-Ollama Bridge")
        self.root.geometry("600x800")
        
        # Initialize logger to None first
        self.logger = None
        
        # Setup GUI components
        self.setup_gui()
        
        # Initialize handlers
        self.meshtastic = MeshtasticHandler(self.logger, self.on_message_received)
        self.ollama = OllamaHandler(self.logger)
        
        # State variables
        self.conversation_started = False
        
        # Load initial data
        self.refresh_models()
        self.refresh_ports()

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
        
        # Initialize logger
        self.logger = GUILogger(self.log_text)
    
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
        
        # Status indicator
        status_frame = ttk.Frame(self.settings_frame)
        status_frame.pack(fill='x', pady=10)
        
        status_label = ttk.Label(status_frame, text="Status:")
        status_label.pack(side='left')
        
        self.status_label = ttk.Label(status_frame, text="Not Connected")
        self.status_label.pack(side='left', padx=5)
    
    def setup_conversation_tab(self):
        """Set up the conversation tab with logs and controls."""
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
            target = self.hostname_entry.get()
            if not target:
                messagebox.showerror("Error", "Please enter a hostname or IP address.")
                return

        if not target: # Should not happen if logic above is correct
            messagebox.showerror("Error", "No connection target specified.")
            return

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
            self.logger.clear()

if __name__ == "__main__":
    root = tk.Tk()
    app = MeshtasticOllamaGUI(root)
    root.mainloop()
