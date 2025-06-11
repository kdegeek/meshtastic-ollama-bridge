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

import ollama
import requests
from tkinter import messagebox
import json
import os

class OllamaHandler:
    """Handler for Ollama API interactions."""
    
    def __init__(self, logger, history_filepath="conversation_history.json"):
        """Initialize the Ollama handler.
        
        Args:
            logger: The logger instance
            history_filepath: Path to the conversation history JSON file
        """
        self.logger = logger
        self.selected_model = None
        self.history_filepath = history_filepath
        self.conversation_history = [] # Initialize as empty list
        self._load_conversation_history() # Load history at the end of init
    
    def _load_conversation_history(self):
        """Loads conversation history from the specified JSON file."""
        if os.path.exists(self.history_filepath):
            try:
                with open(self.history_filepath, 'r') as f:
                    loaded_history = json.load(f)

                # Validation
                if isinstance(loaded_history, list) and \
                   all(isinstance(item, dict) and 'role' in item and 'content' in item for item in loaded_history):
                    self.conversation_history = loaded_history
                    if self.logger:
                        self.logger.log(f"Loaded {len(self.conversation_history)} messages from {self.history_filepath}", "Ollama")
                else:
                    if self.logger:
                        self.logger.log(f"Invalid format in {self.history_filepath}. Starting with empty history.", "Error")
                    self.conversation_history = []
            except json.JSONDecodeError as e:
                if self.logger:
                    self.logger.log(f"Error decoding JSON from {self.history_filepath}: {e}. Starting with empty history.", "Error")
                self.conversation_history = []
            except IOError as e:
                if self.logger:
                    self.logger.log(f"IOError reading {self.history_filepath}: {e}. Starting with empty history.", "Error")
                self.conversation_history = []
            except Exception as e:
                if self.logger:
                    self.logger.log(f"Unexpected error loading history from {self.history_filepath}: {e}. Starting fresh.", "Error", exc_info=True)
                self.conversation_history = []
        else:
            if self.logger:
                self.logger.log(f"No history file found at {self.history_filepath}. Starting with empty history.", "Info")
            self.conversation_history = []

    def _save_conversation_history(self):
        """Saves the current conversation history to the JSON file."""
        try:
            with open(self.history_filepath, 'w') as f:
                json.dump(self.conversation_history, f, indent=4)
            if self.logger:
                self.logger.log(f"Conversation history saved to {self.history_filepath}", "Ollama")
        except IOError as e:
            if self.logger:
                self.logger.log(f"IOError writing history to {self.history_filepath}: {e}", "Error")
        except Exception as e:
            if self.logger:
                self.logger.log(f"Unexpected error saving history to {self.history_filepath}: {e}", "Error", exc_info=True)

    def get_available_models(self):
        """Get a list of available Ollama models.
        
        Returns:
            List of model names or empty list if error
        """
        try:
            response = requests.get('http://localhost:11434/api/tags')
            response.raise_for_status() # Will raise an HTTPError if the HTTP request returned an unsuccessful status code
            models_data = response.json().get('models', [])
            models = [model['name'] for model in models_data]
            if models and self.logger:
                self.logger.log(f"Loaded {len(models)} Ollama models: {', '.join(models)}", "Ollama")
            elif not models and self.logger:
                self.logger.log("No Ollama models found or returned by API.", "Warning")
            return models
        except requests.exceptions.ConnectionError as e:
            if self.logger:
                self.logger.log(f"Ollama API connection error: {e}", "Error")
            self._show_ollama_error("Connection Error", f"Could not connect to Ollama API at http://localhost:11434. Ensure Ollama is running.\nDetails: {e}")
            return []
        except requests.exceptions.Timeout as e:
            if self.logger:
                self.logger.log(f"Ollama API request timed out: {e}", "Error")
            self._show_ollama_error("Timeout Error", f"Request to Ollama API timed out.\nDetails: {e}")
            return []
        except requests.exceptions.RequestException as e: # Catch other request-related errors
            if self.logger:
                self.logger.log(f"Ollama API request error: {e}", "Error")
            self_show_ollama_error("API Request Error", f"An error occurred while requesting data from Ollama API.\nDetails: {e}")
            return []
        except Exception as e: # Catch other potential errors like JSON parsing
            if self.logger:
                self.logger.log(f"Error processing Ollama models response: {e}", "Error")
            self._show_ollama_error("Processing Error", f"Failed to process response from Ollama API.\nDetails: {e}")
            return []
    
    def set_model(self, model_name):
        """Set the active Ollama model.
        
        Args:
            model_name: The name of the model to use
        """
        self.selected_model = model_name
        if self.logger:
            self.logger.log(f"Selected model: {model_name}", "Ollama")
    
    def get_response(self, prompt):
        """Get a response from Ollama for the given prompt.
        
        Args:
            prompt: The user's message to send to Ollama
            
        Returns:
            The AI's response text
        """
        if not self.selected_model:
            if self.logger:
                self.logger.log("No model selected", "Error")
            return "Error: No model selected"
            
        self.conversation_history.append({"role": "user", "content": prompt})
        try:
            if self.logger:
                self.logger.log(f"Sending prompt to {self.selected_model}", "Ollama")
            response = ollama.chat(
                model=self.selected_model,
                messages=self.conversation_history
            )
            assistant_response = response["message"]["content"]
            self.conversation_history.append(
                {"role": "assistant", "content": assistant_response}
            )
            if self.logger:
                self.logger.log(f"Ollama response: {assistant_response[:100]}...", "Ollama") # Log snippet
            self._save_conversation_history() # Save after successful interaction
            return assistant_response
        except ollama.ResponseError as e:
            if self.logger:
                self.logger.log(f"Ollama API ResponseError: {e.status_code} - {e.error}", "Error")
            # self._show_ollama_error("Ollama Response Error", f"Ollama API returned an error: {e.error} (Status: {e.status_code})")
            return f"Error: Ollama API - {e.error}"
        except requests.exceptions.ConnectionError as e: # ollama client might raise this if server disappears mid-request
            if self.logger:
                self.logger.log(f"Ollama API connection error during chat: {e}", "Error")
            # self._show_ollama_error("Connection Error", f"Could not connect to Ollama API during chat. Ensure Ollama is running.\nDetails: {e}")
            return "Error: Connection to Ollama lost"
        except requests.exceptions.Timeout as e:
            if self.logger:
                self.logger.log(f"Ollama API timeout during chat: {e}", "Error")
            return "Error: Ollama request timed out"
        except requests.exceptions.RequestException as e:
            if self.logger:
                self.logger.log(f"Ollama API request error during chat: {e}", "Error")
            return f"Error: Ollama API request failed - {e}"
        except Exception as e:
            if self.logger:
                self.logger.log(f"Generic error generating response from Ollama: {str(e)}", "Error", exc_info=True)
            # self._show_ollama_error("Ollama Error", f"An unexpected error occurred while getting a response from Ollama.\nDetails: {str(e)}")
            return "Error: Could not generate response"
    
    def clear_conversation_history(self):
        """Clear the conversation history."""
        self.conversation_history = []
        if self.logger:
            self.logger.log("Conversation history cleared", "Ollama")
        self._save_conversation_history() # Save after clearing
    
    def get_conversation_history(self):
        """Get the current conversation history.
        
        Returns:
            List of conversation messages
        """
        return self.conversation_history
    
    def get_conversation_length(self):
        """Get the number of messages in the conversation history.
        
        Returns:
            Number of messages
        """
        return len(self.conversation_history)
    
    def _show_ollama_error(self, title="Ollama Error", message=None):
        """Show error message related to Ollama.

        Args:
            title: The title for the messagebox.
            message: The error message to display. If None, a default message is used.
        """
        default_msg = "Cannot connect to Ollama API. Please ensure Ollama is running (e.g. 'ollama serve')."
        final_message = message if message else default_msg

        if self.logger: # Logger might not be initialized if error occurs very early
            self.logger.log(f"{title}: {final_message}", "Error")
        else:
            print(f"OllamaHandler Error (Logger not available): {title} - {final_message}")

        # Displaying messagebox can be problematic if called from non-GUI thread.
        # Consider a more robust way to bubble this up if handlers are used outside GUI.
        # For now, keep it as is, assuming it's mostly called from GUI context or where messagebox is acceptable.
        try:
            # Check if we are in Tkinter's main thread or if root window exists
            # This is a simplistic check; a more robust solution might involve passing a GUI callback
            if messagebox._show is not None: # Check if tkinter is available and configured
                 messagebox.showerror(title, final_message)
            else:
                print("Error: Tkinter messagebox not available for Ollama error.")
        except Exception as e:
            print(f"Error displaying Ollama error messagebox: {e}")
