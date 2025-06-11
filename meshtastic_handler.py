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

import meshtastic
import meshtastic.serial_interface
import meshtastic.tcp_interface
import serial.tools.list_ports
import platform
import time
import queue # Added for outgoing message queue
from pubsub import pub
from tkinter import messagebox

class MeshtasticHandler:
    """Handler for Meshtastic device interactions."""
    
    def __init__(self, logger, on_message_received=None, connection_type="serial", reconnection_status_callback=None):
        """Initialize the Meshtastic handler.
        
        Args:
            logger: The logger instance
            on_message_received: Callback function for received messages
            connection_type: "serial" or "network"
            reconnection_status_callback: Callback for UI updates during reconnection
        """
        self.logger = logger
        self.connection_type = connection_type
        self.reconnection_status_callback = reconnection_status_callback
        self.interface = None
        self.is_connected = False
        self.channels = {}
        self.selected_channel = 0
        self.on_message_received = on_message_received
        self.MAX_MESSAGE_LENGTH = 200
        self.last_known_port = None # For reconnection
        self.reconnecting = False # Flag to prevent multiple reconnection loops
        self.outgoing_message_queue = queue.Queue()
        
    def get_connection_targets(self):
        """Get a list of available connection targets (serial ports or network hosts).
        
        Returns:
            List of target names formatted for display
        """
        if self.connection_type == "network":
            # For network connections, GUI handles the input, so no targets to list here.
            return []

        # Serial connection type
        if platform.system() == 'Windows':
            # On Windows, show both port and description
            ports = []
            for port in serial.tools.list_ports.comports():
                # Only show COM ports
                if 'COM' in port.device:
                    # Show both port name and description
                    port_str = f"{port.device} ({port.description})"
                    ports.append(port_str)
        else:
            # On Unix systems, just show the device path
            ports = [port.device for port in serial.tools.list_ports.comports()]
            
        if ports and self.logger:
            self.logger.log(f"Found {len(ports)} serial ports")
        elif self.logger:
            self.logger.log("No serial ports found", "Warning")
            
        return ports
    
    def connect(self, port):
        """Connect to a Meshtastic device.
        
        Args:
            port: The serial port to connect to
            
        Returns:
            True if connection successful, False otherwise
        """
        if self.is_connected:
            return True
            
        if not port:
            if self.logger:
                self.logger.log("No port selected", "Error")
            return False
            
        try:
            if self.logger:
                self.logger.log(f"Connecting to device on {port}", "Meshtastic")

            # Subscribe to Meshtastic events
            pub.subscribe(self._on_receive, "meshtastic.receive")
            pub.subscribe(self._on_connection, "meshtastic.connection.established")

            # Extract just the port name on Windows
            if self.connection_type == "serial" and platform.system() == 'Windows' and ' (' in port:
                port = port.split(' (')[0]

            MAX_RETRIES = 3
            RETRY_DELAY = 3  # seconds

            for attempt in range(MAX_RETRIES):
                try:
                    if self.logger:
                        self.logger.log(f"Connection attempt {attempt + 1}/{MAX_RETRIES}", "Meshtastic")

                    if self.connection_type == "serial":
                        self.interface = meshtastic.serial_interface.SerialInterface(
                            devPath=port
                        )
                    elif self.connection_type == "network":
                        # For network, 'port' is the hostname/IP
                        self.interface = meshtastic.tcp_interface.TCPInterface(
                            hostname=port
                        )
                    else:
                        if self.logger:
                            self.logger.log(f"Unsupported connection type: {self.connection_type}", "Error")
                        return False

                    # If connection is successful, break the loop
                    self.is_connected = True
                    self.last_known_port = port # Store for potential reconnection
                    if self.logger:
                        self.logger.log(f"Connected to device on {self.last_known_port}", "Meshtastic")

                    # Attempt to process outgoing queue on successful connection
                    if not self.outgoing_message_queue.empty():
                        self.logger.log("Connection established. Processing outgoing message queue...", "Meshtastic")
                        self._process_outgoing_queue()
                    return True

                except serial.serialutil.SerialException as e:
                    if platform.system() == 'Windows':
                        error_msg = ("Could not open serial port. Make sure no other program is using it.\n"
                                     "Try closing other applications or restarting the device.")
                        if self.logger:
                            self.logger.log(f"Serial port error: {str(e)}", "Error")
                        # Display error only on the last attempt for serial
                        if attempt == MAX_RETRIES -1:
                             messagebox.showerror("Connection Error", error_msg)
                    else:
                        if self.logger:
                            self.logger.log(f"Serial port error: {str(e)}", "Error")
                        if attempt == MAX_RETRIES -1:
                            messagebox.showerror("Connection Error", str(e))
                    # For serial, no retry, Meshtastic library handles this well enough.
                    return False
                except (meshtastic.MeshtasticError, ConnectionRefusedError, TimeoutError) as e: # socket.timeout inherits from OSError, TimeoutError is more general
                    if self.logger:
                        self.logger.log(f"Connection attempt {attempt + 1} failed: {str(e)}", "Error")
                    if attempt < MAX_RETRIES - 1:
                        if self.logger:
                            self.logger.log(f"Retrying in {RETRY_DELAY} seconds...", "Meshtastic")
                        time.sleep(RETRY_DELAY)
                    else:
                        if self.logger:
                            self.logger.log("Max connection retries reached.", "Error")
                        messagebox.showerror("Connection Error", f"Failed to connect after {MAX_RETRIES} attempts: {str(e)}")
                        return False
                except Exception as e: # Catch any other unexpected errors
                    if self.logger:
                        self.logger.log(f"An unexpected error occurred during connection: {str(e)}", "Error")
                    messagebox.showerror("Connection Error", f"An unexpected error occurred: {str(e)}")
                    return False
            
            return False # Should not be reached if logic is correct

        except Exception as e: # Outer try-except for issues like pubsub subscription
            if self.logger:
                self.logger.log(f"Connection setup error: {str(e)}", "Error")
            messagebox.showerror("Connection Setup Error", str(e))
            return False
    
    def disconnect(self):
        """Disconnect from the Meshtastic device."""
        if self.interface:
            try:
                self.interface.close()
            except Exception as e:
                if self.logger:
                    self.logger.log(f"Error closing Meshtastic interface: {e}", "Error")
        self.interface = None # Ensure interface is cleared
        self.is_connected = False
        self.last_known_port = None # Clear last known port on explicit disconnect
        self.reconnecting = False # Stop any reconnection attempts
        if self.logger:
            self.logger.log("Disconnected from device", "Meshtastic")

    def attempt_reconnection(self):
        """Attempt to reconnect to the Meshtastic device using the last known port."""
        if not self.last_known_port:
            if self.logger:
                self.logger.log("No last known port to attempt reconnection.", "Warning")
            return False

        if self.reconnecting:
            if self.logger:
                self.logger.log("Reconnection already in progress.", "Info")
            return False # Avoid parallel reconnection attempts

        self.reconnecting = True
        if self.logger:
            self.logger.log(f"Attempting to reconnect to {self.last_known_port}...", "Meshtastic")
        if self.reconnection_status_callback:
            self.reconnection_status_callback(True, f"Attempting to reach {self.last_known_port}...")


        reconnection_retries = 3
        reconnection_delay = [5, 10, 20]  # seconds

        for i in range(reconnection_retries):
            if not self.reconnecting: # Check if disconnect was called during wait
                self.logger.log("Reconnection cancelled by disconnect().", "Info")
                if self.reconnection_status_callback:
                    self.reconnection_status_callback(False) # Update UI
                return False

            attempt_msg = f"Attempt {i + 1}/{reconnection_retries}"
            if self.logger:
                self.logger.log(f"Reconnection: {attempt_msg}", "Meshtastic")
            if self.reconnection_status_callback:
                self.reconnection_status_callback(True, attempt_msg)

            # We directly call self.interface creation here to bypass some of self.connect's initial checks
            # and to have more direct control over the reconnection process for UI feedback.
            # However, self.connect() already has its own retry logic for the initial connection.
            # For simplicity here, we are just retrying the full self.connect().
            if self.connect(self.last_known_port):
                if self.logger:
                    self.logger.log(f"Successfully reconnected to {self.last_known_port}", "Meshtastic")
                self.reconnecting = False
                if self.reconnection_status_callback:
                    self.reconnection_status_callback(False) # Success

                # Attempt to process outgoing queue on successful reconnection
                if not self.outgoing_message_queue.empty():
                    self.logger.log("Reconnected. Processing outgoing message queue...", "Meshtastic")
                    self._process_outgoing_queue()
                return True

            if i < reconnection_retries - 1 and self.reconnecting:
                retry_wait_msg = f"Retrying in {reconnection_delay[i]}s..."
                if self.logger:
                    self.logger.log(f"Reconnection attempt failed. {retry_wait_msg}", "Warning")
                if self.reconnection_status_callback:
                    self.reconnection_status_callback(True, f"Failed. {retry_wait_msg}")
                time.sleep(reconnection_delay[i])
            elif not self.reconnecting: # disconnect() might have been called during sleep
                 self.logger.log("Reconnection cancelled during sleep by disconnect().", "Info")
                 if self.reconnection_status_callback:
                    self.reconnection_status_callback(False)
                 return False

        if self.logger:
            self.logger.log(f"Failed to reconnect to {self.last_known_port} after {reconnection_retries} attempts.", "Error")
        self.reconnecting = False
        self.is_connected = False # Ensure this is false if all attempts fail
        if self.reconnection_status_callback:
            self.reconnection_status_callback(False) # Failure
        # pub.sendMessage("meshtastic.reconnection.failed")
        return False

    def send_message(self, text):
        """Send a message over Meshtastic.
        
        Args:
            text: The text message to send
            
        Returns:
            True if message sent successfully, False otherwise
        """
        original_text_for_queue = text # Keep the original full text for queuing if send fails

        if not self.is_connected or not self.interface:
            if self.logger:
                self.logger.log("Send_message: Not connected. Attempting to reconnect...", "Warning")
            
            # Try to reconnect if possible
            reconnection_successful = False
            if self.last_known_port and not self.reconnecting:
                reconnection_successful = self.attempt_reconnection()

            if reconnection_successful:
                if self.logger:
                    self.logger.log("Reconnected. Proceeding with send_message.", "Meshtastic")
                # Continue to send the message after successful reconnection
            else: # Reconnection not possible or failed
                self.logger.log("Cannot send message: Not connected. Queuing message.", "Error")
                self.outgoing_message_queue.put(original_text_for_queue)
                self.logger.log(f"Message queued. Queue size: {self.outgoing_message_queue.qsize()}", "Info")
                return False # Indicate immediate sending failed

        # Re-check connection status after potential reconnection attempt
        if not self.is_connected or not self.interface:
            self.logger.log("Send_message: Still not connected. Queuing message.", "Error")
            self.outgoing_message_queue.put(original_text_for_queue)
            self.logger.log(f"Message queued. Queue size: {self.outgoing_message_queue.qsize()}", "Info")
            return False

        try:
            self._send_split_text(text) # 'text' here is the original full text
            return True
        except meshtastic.MeshtasticError as e:
            if self.logger:
                self.logger.log(f"MeshtasticError sending message: {str(e)}. Assuming disconnection.", "Error")
            self.is_connected = False # Assume connection lost
            self.logger.log("Connection lost during send. Queuing message.", "Warning")
            self.outgoing_message_queue.put(original_text_for_queue) # Queue the original full message
            self.logger.log(f"Message queued due to MeshtasticError. Queue size: {self.outgoing_message_queue.qsize()}", "Info")

            # pub.sendMessage("meshtastic.connection.lost", interface=self.interface) # Notify GUI if needed
            if self.last_known_port and not self.reconnecting: # Attempt to restore connection for future operations or next queue processing
                self.attempt_reconnection()
            return False # Message sending failed for now
        except Exception as e: # For other non-Meshtastic errors (e.g., programming errors)
            if self.logger:
                self.logger.log(f"Generic error sending message: {str(e)}", "Error", exc_info=True)
            # Do not queue for generic errors as they might not be connection related.
            return False
    
    def _send_split_text(self, text_to_send): # Renamed arg to avoid clash
        """Split and send a long text message over Meshtastic.
        
        Args:
            text: The text message to send
        """
        chunks = [text[i:i+self.MAX_MESSAGE_LENGTH] 
                 for i in range(0, len(text), self.MAX_MESSAGE_LENGTH)]
        
        total_chunks = len(chunks)
        if self.logger:
            self.logger.log(f"Splitting message into {total_chunks} chunks", "Meshtastic")
        
        for index, chunk in enumerate(chunks):
            if total_chunks > 1:
                chunk = f"({index+1}/{total_chunks}) {chunk}"
            try:
                self.interface.sendText(
                    text=chunk,
                    channelIndex=self.selected_channel,
                    wantAck=True
                )
                time.sleep(0.2) # Keep small delay for radio politeness
            except meshtastic.MeshtasticError as e: # More specific error
                if self.logger:
                    self.logger.log(f"MeshtasticError sending chunk {index+1}/{total_chunks}: {str(e)}", "Error")
                raise # Propagate to send_message which will handle queuing and reconnection
            except Exception as e: # Other errors during chunk sending
                if self.logger:
                    self.logger.log(f"Generic error sending chunk {index+1}/{total_chunks}: {str(e)}", "Error", exc_info=True)
                # This error is not necessarily a connection issue, so send_message should not queue.
                # We re-raise it so send_message's generic Exception handler catches it.
                raise
    
    def _process_outgoing_queue(self):
        """Process messages from the outgoing queue."""
        if self.reconnecting: # Don't process if already trying to reconnect
            self.logger.log("Queue processing skipped: reconnection in progress.", "Info")
            return

        if not self.is_connected:
            self.logger.log("Queue processing skipped: not connected.", "Warning")
            # Attempt to reconnect if not already doing so, as we have messages to send
            if self.last_known_port and not self.reconnecting:
                self.logger.log("Attempting to reconnect to process queue...", "Info")
                self.attempt_reconnection()
            return

        self.logger.log(f"Processing outgoing message queue. Size: {self.outgoing_message_queue.qsize()}", "Meshtastic")

        processed_count = 0
        while not self.outgoing_message_queue.empty() and self.is_connected:
            try:
                text = self.outgoing_message_queue.get_nowait()
                self.logger.log(f"Attempting to send queued message: '{text[:50]}...'", "Meshtastic")

                self._send_split_text(text) # This now directly takes the full text

                self.logger.log(f"Successfully sent queued message: '{text[:50]}...'", "Meshtastic")
                self.outgoing_message_queue.task_done() # Mark as processed
                processed_count +=1
            except meshtastic.MeshtasticError as e:
                self.logger.log(f"MeshtasticError sending queued message: {str(e)}. Re-queuing.", "Error")
                self.outgoing_message_queue.put(text) # Re-queue the message
                self.is_connected = False # Assume connection lost
                self.logger.log("Connection lost during queued send. Attempting to reconnect...", "Warning")
                if self.last_known_port and not self.reconnecting:
                    self.attempt_reconnection() # Attempt to restore for next cycle
                break # Stop processing queue if a send fails due to connection
            except queue.Empty: # Should ideally not happen with while not empty()
                self.logger.log("Outgoing message queue is empty (concurrently).", "Info")
                break
            except Exception as e: # Other errors
                self.logger.log(f"Unexpected error sending queued message '{text[:50]}...': {str(e)}. Message might be lost.", "Error", exc_info=True)
                # Decide if this message should be re-queued or discarded. For now, discard.
                self.outgoing_message_queue.task_done() # Avoid infinite loop for non-connection errors
                # Potentially log as lost or move to a dead-letter queue

        if processed_count > 0:
            self.logger.log(f"Finished processing {processed_count} messages from queue. Remaining: {self.outgoing_message_queue.qsize()}", "Meshtastic")
        elif self.is_connected and self.outgoing_message_queue.empty():
             self.logger.log("Outgoing message queue is empty.", "Info")
        elif not self.is_connected:
            self.logger.log(f"Queue processing stopped due to disconnection. Remaining: {self.outgoing_message_queue.qsize()}", "Warning")


    def get_channels(self):
        """Get available channels from the connected device.
        
        Returns:
            List of channel names
        """
        channel_names = ["Primary"] # Default channel

        if not self.is_connected or not self.interface:
            if self.logger:
                self.logger.log("Get_channels: Not connected. Attempting to reconnect...", "Warning")
            if self.last_known_port and not self.reconnecting:
                if self.attempt_reconnection():
                    if self.logger:
                        self.logger.log("Reconnected. Proceeding with get_channels.", "Meshtastic")
                else:
                    self.logger.log("Reconnection failed. Cannot get channels.", "Error")
                    return channel_names # Return default
            else:
                self.logger.log("Cannot get channels: Not connected and no reconnection possible/in progress.", "Error")
                return channel_names # Return default
        
        # Re-check connection status
        if not self.is_connected or not self.interface:
             self.logger.log("Get_channels: Still not connected after checking. Returning default channels.", "Error")
             return channel_names


        try:
            # Accessing self.interface.nodes directly can sometimes cause issues
            # if the internal state is not perfectly synced.
            # Using a more direct way if available, or ensuring robust error handling.
            # For now, we rely on the existing structure but add error handling.
            if hasattr(self.interface, 'nodes') and self.interface.nodes:
                # Iterate safely over a copy of items if modification during iteration is a concern
                for node_id, node_info in list(self.interface.nodes.items()):
                    if hasattr(node_info, 'channels') and node_info.channels:
                        self.channels = node_info.channels
                        for ch_index, ch in enumerate(node_info.channels): # ch can be simple dict or object
                            if hasattr(ch, 'settings') and hasattr(ch.settings, 'name') and ch.settings.name:
                                channel_names.append(ch.settings.name)
                            # Fallback if channel name is not present but channel exists
                            # elif hasattr(ch, 'index'): # Assuming 'index' or similar attribute
                            #    channel_names.append(f"Channel {ch.index}")
                        if len(channel_names) > 1 and self.logger: # More than just "Primary"
                            self.logger.log(f"Found {len(channel_names)-1} additional named channels", "Meshtastic")
                        break # Found channels from one node, assuming this is sufficient
            else:
                if self.logger:
                    self.logger.log("No nodes found or interface has no 'nodes' attribute.", "Warning")

        except meshtastic.MeshtasticError as e:
            if self.logger:
                self.logger.log(f"MeshtasticError getting channels: {str(e)}. Assuming disconnection.", "Error")
            self.is_connected = False # Assume connection lost
            # pub.sendMessage("meshtastic.connection.lost", interface=self.interface) # Notify GUI
            if self.last_known_port and not self.reconnecting:
                self.attempt_reconnection() # Attempt to restore for future
            return ["Primary"] # Return default on error
        except Exception as e:
            if self.logger:
                self.logger.log(f"Generic error getting channels: {str(e)}", "Error")
            # Depending on the error, could also set is_connected = False
            return ["Primary"] # Return default on error
        
        # Ensure Primary channel (index 0) is always available and selected by default
        self.selected_channel = 0
        if self.logger:
            self.logger.log("Primary channel selected by default", "Meshtastic")
            
        return channel_names
    
    def set_channel(self, channel_name):
        """Set the active channel by name.
        
        Args:
            channel_name: The name of the channel to set
            
        Returns:
            True if channel was set, False otherwise
        """
        if channel_name == "Primary":
            self.selected_channel = 0
            if self.logger:
                self.logger.log(f"Switched to channel: Primary")
            return True
        else:
            # Find channel index by name
            for i, channel in enumerate(self.channels):
                if hasattr(channel, 'settings') and channel.settings.name == channel_name:
                    self.selected_channel = i
                    if self.logger:
                        self.logger.log(f"Switched to channel: {channel_name}")
                    return True
        
        if self.logger:
            self.logger.log(f"Channel not found: {channel_name}", "Error")
        return False
    
    def _on_receive(self, packet):
        """Handle received Meshtastic messages.
        
        Args:
            packet: The received packet data
        """
        if "decoded" in packet and "text" in packet["decoded"]:
            text = packet["decoded"]["text"]
            if self.logger:
                self.logger.log(text, "Received")
            
            if self.on_message_received:
                self.on_message_received(text)
    
    def _on_connection(self, interface, topic=pub.AUTO_TOPIC):
        """Handle Meshtastic connection established event.
        
        Args:
            interface: The Meshtastic interface
            topic: The pubsub topic
        """
        if self.logger:
            self.logger.log("Connection established", "Meshtastic")
