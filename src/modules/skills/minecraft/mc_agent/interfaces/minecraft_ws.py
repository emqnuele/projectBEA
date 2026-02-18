import websocket
import threading
import time
import json
from typing import Callable, Optional
from ..utils.logger import setup_logger

logger = setup_logger("MinecraftWS")

class MinecraftClient:
    def __init__(self, url: str, on_message_callback: Callable[[dict], None]):
        self.url = url
        self.on_message_callback = on_message_callback
        self.ws: Optional[websocket.WebSocketApp] = None
        self.keep_running = True
        self.thread = threading.Thread(target=self._run_forever, daemon=True)
        self.is_connected = False

    def stop(self):
        """Stops the connection loop and closes the socket."""
        logger.info("Stopping MinecraftClient...")
        self.keep_running = False
        if self.ws:
            self.ws.close()
        if self.thread.is_alive():
            self.thread.join(timeout=0.1)
        logger.info("MinecraftClient stopped.")

    def connect(self):
        """Starts the connection thread."""
        logger.info(f"Starting connection thread for {self.url}")
        self.thread.start()

    def _run_forever(self):
        """Internal loop to maintain connection."""
        while self.keep_running:
            try:
                logger.info(f"Connecting to Minecraft at {self.url}...")
                self.ws = websocket.WebSocketApp(
                    self.url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                self.ws.run_forever()
                
                if self.keep_running:
                    logger.warning("Connection lost. Retrying in 5 seconds...")
                    time.sleep(5)
            except Exception as e:
                logger.error(f"Connection loop error: {e}")
                time.sleep(5)
            except SystemExit:
                logger.info("MinecraftClient thread exiting (SystemExit).")
                self.keep_running = False
                break

    def send(self, data: dict):
        """Sends a JSON dictionary to the WebSocket."""
        if self.ws and self.is_connected:
            try:
                payload = json.dumps(data)
                self.ws.send(payload)
                logger.debug(f"Sent: {payload[:100]}...")
            except Exception as e:
                logger.error(f"Failed to send data: {e}")
        else:
            logger.warning("Attempted to send data while disconnected.")

    def _on_open(self, ws):
        self.is_connected = True
        logger.info("Connected to Minecraft Mod!")

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            try:
                self.on_message_callback(data)
            except Exception as e:
                logger.error(f"Error in message callback: {e}")
        except json.JSONDecodeError:
            logger.error(f"Received invalid JSON: {message}")
        except Exception as e:
            logger.error(f"Unexpected error in _on_message: {e}")

    def _on_error(self, ws, error):
        logger.error(f"WebSocket Error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        self.is_connected = False
        logger.info("Disconnected from Minecraft.")
