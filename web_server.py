from flask import Flask, request, jsonify
import logging

# Placeholder for handler instances
meshtastic_handler = None
ollama_handler = None

# Configure basic logging for the web server
log = logging.getLogger('werkzeug') # Get Flask's default logger
log.setLevel(logging.INFO)

def create_flask_app():
    app = Flask(__name__)

    @app.route('/send_message', methods=['POST'])
    def send_message_route():
        global meshtastic_handler
        log.info("Received request for /send_message")
        if not meshtastic_handler:
            log.error("Meshtastic handler not initialized")
            return jsonify({"status": "error", "message": "Meshtastic handler not available"}), 500

        data = request.json
        if not data or 'text' not in data: # Changed 'message' to 'text' to match potential client
            log.warning("No 'text' provided in /send_message request body")
            return jsonify({"status": "error", "message": "Request body must be JSON and include 'text' field"}), 400

        message_text = data['text']
        log.info(f"Calling Meshtastic_handler.send_message with: {message_text}")

        try:
            success = meshtastic_handler.send_message(message_text)
            if success:
                log.info("Message sent successfully via Meshtastic")
                return jsonify({"status": "success", "message": "Message sent"})
            else:
                log.error("Failed to send message via Meshtastic (handler returned False)")
                return jsonify({"status": "error", "message": "Failed to send message"}), 500
        except Exception as e:
            log.error(f"Exception calling Meshtastic_handler.send_message: {e}", exc_info=True)
            return jsonify({"status": "error", "message": f"Error sending message: {str(e)}"}), 500

    @app.route('/ollama_response', methods=['POST'])
    def ollama_response_route():
        global ollama_handler
        log.info("Received request for /ollama_response")
        if not ollama_handler:
            log.error("Ollama handler not initialized")
            return jsonify({"status": "error", "message": "Ollama handler not available"}), 500

        data = request.json
        if not data or 'prompt' not in data:
            log.warning("No 'prompt' provided in /ollama_response request body")
            return jsonify({"status": "error", "message": "Request body must be JSON and include 'prompt' field"}), 400

        prompt_text = data['prompt']
        log.info(f"Calling Ollama_handler.get_response with: {prompt_text}")

        try:
            response = ollama_handler.get_response(prompt_text)
            if response:
                log.info(f"Received response from Ollama: {response}")
                return jsonify({"status": "success", "response": response})
            else:
                log.error("Failed to get response from Ollama (handler returned empty or None)")
                return jsonify({"status": "error", "message": "Failed to get response from Ollama"}), 500
        except Exception as e:
            log.error(f"Exception calling Ollama_handler.get_response: {e}", exc_info=True)
            return jsonify({"status": "error", "message": f"Error getting Ollama response: {str(e)}"}), 500

    return app

def start_flask_app(meshtastic_h, ollama_h):
    global meshtastic_handler, ollama_handler
    meshtastic_handler = meshtastic_h
    ollama_handler = ollama_h

    app = create_flask_app()

    log.info("Starting Flask web server...")
    # Note: Using Flask's default development server (Werkzeug)
    # In production, a more robust WSGI server (like Gunicorn or uWSGI) should be used.
    # host='0.0.0.0' makes it accessible from other devices on the network.
    # debug=False is important as debug mode can have security implications and is not ideal for threads.
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
        log.info("Flask web server stopped.")
    except Exception as e:
        log.error(f"Flask web server failed to start or crashed: {e}", exc_info=True)

if __name__ == '__main__':
    # This is for testing the web server independently
    # You would typically not run it this way in the main application
    class MockHandler:
        def __init__(self, name):
            self.name = name
            self.logger = logging.getLogger(name) # Basic logger for mock
            logging.basicConfig(level=logging.INFO) # Ensure logs are visible

        def send_message(self, text):
            self.logger.info(f"{self.name} received send_message: {text}")
            return True

        def get_response(self, prompt):
            self.logger.info(f"{self.name} received get_response: {prompt}")
            return f"Mock response to: {prompt}"

    print("Starting Flask app independently for testing...")
    mock_meshtastic = MockHandler("MockMeshtastic")
    mock_ollama = MockHandler("MockOllama")
    start_flask_app(mock_meshtastic, mock_ollama)
