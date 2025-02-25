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

class OllamaHandler:
    """Handler for Ollama API interactions."""
    
    def __init__(self, logger):
        """Initialize the Ollama handler.
        
        Args:
            logger: The logger instance
        """
        self.logger = logger
        self.conversation_history = []
        self.selected_model = None
    
    def get_available_models(self):
        """Get a list of available Ollama models.
        
        Returns:
            List of model names or empty list if error
        """
        try:
            response = requests.get('http://localhost:11434/api/tags')
            if response.status_code == 200:
                models = [model['name'] for model in response.json()['models']]
                if models and self.logger:
                    self.logger.log(f"Loaded {len(models)} Ollama models", "Ollama")
                return models
            else:
                self._show_ollama_error()
                return []
        except requests.exceptions.ConnectionError:
            self._show_ollama_error()
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
            return assistant_response
        except Exception as e:
            if self.logger:
                self.logger.log(f"Error generating response: {str(e)}", "Error")
            self._show_ollama_error()
            return "Error: Could not generate response"
    
    def clear_conversation_history(self):
        """Clear the conversation history."""
        self.conversation_history = []
        if self.logger:
            self.logger.log("Conversation history cleared", "Ollama")
    
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
    
    def _show_ollama_error(self):
        """Show error message when Ollama API is not available."""
        error_msg = "Cannot connect to Ollama API. Please ensure Ollama is running with:\n\nollama serve"
        if self.logger:
            self.logger.log("Connection error: Ollama API not available", "Error")
        messagebox.showerror("Ollama Error", error_msg)
