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
import datetime
import queue

class GUILogger:
    """Logger class that writes to a tkinter Text widget in a thread-safe manner."""
    
    def __init__(self, text_widget):
        """Initialize the logger with a tkinter Text widget.
        
        Args:
            text_widget: A tkinter Text widget where logs will be displayed
        """
        self.text_widget = text_widget
        self.log_queue = queue.Queue()
        # Define color tags for different log levels
        self.text_widget.tag_config("Info", foreground="black")
        self.text_widget.tag_config("Error", foreground="red")
        self.text_widget.tag_config("Warning", foreground="orange")
        self.text_widget.tag_config("Meshtastic", foreground="blue")
        self.text_widget.tag_config("Ollama", foreground="green")
        self.text_widget.tag_config("AI Response", foreground="purple")
        self.text_widget.tag_config("Received", foreground="brown")
        self.text_widget.tag_config("AI Greeting", foreground="dark cyan")
    
    def log(self, message, level="Info"): # Changed 'source' to 'level' for consistency
        """Queue a log message to be processed by the GUI thread.
        
        Args:
            message: The message to log
            level: The log level (e.g., "Info", "Error", "Meshtastic", "Ollama")
                   This will also be used as the tag for coloring.
        """
        self.log_queue.put((message, level))

    def process_log_queue(self):
        """Process messages from the log queue and display them in the Text widget.
        This method should be called from the main GUI thread.
        """
        while not self.log_queue.empty():
            try:
                message, level = self.log_queue.get_nowait()

                timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                # Use level as the source/tag for the message
                formatted_message = f"[{timestamp}] {level}: {message}\n"

                # Ensure the tag exists, default to "Info" tag if not
                tag_to_apply = level if level in self.text_widget.tag_names() else "Info"

                self.text_widget.config(state=tk.NORMAL) # Enable writing
                self.text_widget.insert(tk.END, formatted_message, (tag_to_apply,))
                self.text_widget.config(state=tk.DISABLED) # Disable writing to prevent user edits
                self.text_widget.see(tk.END)

            except queue.Empty:
                break # Should not happen with the while loop condition, but good practice
            except Exception as e:
                # Fallback for any unexpected error during logging
                print(f"Error processing log queue: {e}")
                # Try to log the error itself, but without tags to avoid loops if tags are the issue
                try:
                    self.text_widget.config(state=tk.NORMAL)
                    self.text_widget.insert(tk.END, f"Logging Error: {e}\n")
                    self.text_widget.config(state=tk.DISABLED)
                    self.text_widget.see(tk.END)
                except:
                    pass # Avoid recursive errors
    
    def clear(self):
        """Clear all logs from the text widget and the queue."""
        # Clear the queue
        while not self.log_queue.empty():
            try:
                self.log_queue.get_nowait()
            except queue.Empty:
                break

        # Clear the text widget
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete(1.0, tk.END)
        self.text_widget.config(state=tk.DISABLED)
        # Optionally, log that logs were cleared (this will be queued and processed)
        self.log("Log cleared", "Info")
