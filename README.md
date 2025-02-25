# Meshtastic-Ollama Bridge

A GUI application that bridges Meshtastic mesh network communication with Ollama's local AI models, enabling AI-powered responses over Meshtastic networks.

## Features

- Connect to Meshtastic devices over serial connection
- Select and use any locally available Ollama model
- Automatic message splitting for long responses
- Real-time message logging
- Maintains conversation context for coherent AI responses

## Prerequisites

- Python 3.x
- Ollama installed and running (`ollama serve`)
- A Meshtastic-compatible device
- Required Python packages (see requirements.txt)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/strwdr/meshtastic-ollama-bridge
cd meshtastic-ollama-bridge
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Ensure Ollama is running:
```bash
ollama serve
```

## Usage

1. Start the application:
```bash
python ollama_meshtastic.py
```

2. Select your Ollama model from the dropdown
3. Choose your Meshtastic device's serial port
4. Click "Connect" to start the bridge
5. Messages received through Meshtastic will automatically be processed by the selected Ollama model, and responses will be sent back through the mesh network

## Notes

- Maximum message length is set to 200 characters, with automatic splitting for longer messages
- The application maintains conversation history for context-aware responses
- Make sure your Meshtastic device is properly configured and connected before starting the application

## License

This project is licensed under the GNU General Public License v3.0 - see the LICENSE file for details.

Note: This project uses the Meshtastic Python library which is also licensed under the GNU General Public License v3.0. As required by the GPL, any modifications or derivative works must also be distributed under the same license terms.
