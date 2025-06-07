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
from pubsub import pub
from tkinter import messagebox

class MeshtasticHandler:
    """Handler for Meshtastic device interactions."""
    
    def __init__(self, logger, on_message_received=None, connection_type="serial"):
        """Initialize the Meshtastic handler.
        
        Args:
            logger: The logger instance
            on_message_received: Callback function for received messages
            connection_type: "serial" or "network"
        """
        self.logger = logger
        self.connection_type = connection_type
        self.interface = None
        self.is_connected = False
        self.channels = {}
        self.selected_channel = 0
        self.on_message_received = on_message_received
        self.MAX_MESSAGE_LENGTH = 200
        
    def get_connection_targets(self):
        """Get a list of available connection targets (serial ports or network hosts).
        
        Returns:
            List of target names formatted for display
        """
        if self.connection_type == "network":
            # Network discovery is not implemented in this step
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
                
            try:
                if self.connection_type == "serial":
                    self.interface = meshtastic.serial_interface.SerialInterface(
                        devPath=port
                    )
                elif self.connection_type == "network":
                    self.interface = meshtastic.tcp_interface.TCPInterface(
                        hostname=port
                    )
                else:
                    if self.logger:
                        self.logger.log(f"Unsupported connection type: {self.connection_type}", "Error")
                    return False
            except serial.serialutil.SerialException as e:
                if platform.system() == 'Windows':
                    error_msg = ("Could not open serial port. Make sure no other program is using it.\n"
                                "Try closing other applications or restarting the device.")
                    if self.logger:
                        self.logger.log(f"Serial port error: {str(e)}", "Error")
                    messagebox.showerror("Connection Error", error_msg)
                else:
                    if self.logger:
                        self.logger.log(f"Serial port error: {str(e)}", "Error")
                    messagebox.showerror("Connection Error", str(e))
                return False
            
            self.is_connected = True
            if self.logger:
                self.logger.log("Connected to device", "Meshtastic")
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.log(f"Connection error: {str(e)}", "Error")
            messagebox.showerror("Connection Error", str(e))
            return False
    
    def disconnect(self):
        """Disconnect from the Meshtastic device."""
        if self.interface:
            self.interface.close()
        self.is_connected = False
        if self.logger:
            self.logger.log("Disconnected from device", "Meshtastic")
    
    def send_message(self, text):
        """Send a message over Meshtastic.
        
        Args:
            text: The text message to send
            
        Returns:
            True if message sent successfully, False otherwise
        """
        if not self.is_connected or not self.interface:
            if self.logger:
                self.logger.log("Cannot send message: Not connected", "Error")
            return False
            
        try:
            self._send_split_text(text)
            return True
        except Exception as e:
            if self.logger:
                self.logger.log(f"Error sending message: {str(e)}", "Error")
            return False
    
    def _send_split_text(self, text):
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
                time.sleep(0.2)
            except Exception as e:
                if self.logger:
                    self.logger.log(f"Error sending chunk {index+1}: {str(e)}", "Error")
                raise
    
    def get_channels(self):
        """Get available channels from the connected device.
        
        Returns:
            List of channel names
        """
        channel_names = ["Primary"]
        
        try:
            if hasattr(self.interface, 'nodes'):
                for node_id, node in self.interface.nodes.items():
                    if hasattr(node, 'channels'):
                        self.channels = node.channels
                        # Add named channels to the list
                        for channel in self.channels:
                            if hasattr(channel, 'settings') and channel.settings.name:
                                channel_names.append(channel.settings.name)
                        
                        if len(channel_names) > 1 and self.logger:
                            self.logger.log(f"Found {len(channel_names)-1} additional channels", "Meshtastic")
                        break
        except Exception as e:
            if self.logger:
                self.logger.log(f"Error loading channels: {str(e)}", "Error")
        
        # Always ensure Primary channel is selected by default
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
