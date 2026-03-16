import asyncio
from typing import Dict, Optional, Union
from pathlib import Path
from obsws_python import ReqClient
from src.interfaces.base_interfaces import OBSInterface
from src.utils.text_utils import fit_text_for_box
from src.utils.logger import get_logger

logger = get_logger("bea.obs")

class OBSController(OBSInterface):
    def __init__(self, host: str, port: int, password: str, source_name: str) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.source_name = source_name
        self.client: Optional[ReqClient] = None
        self._font_cache: Dict[str, Dict[str, object]] = {}
    
    def reload_config(self, config) -> None:
        """Reconnects if critical connection details changed."""
        changed = False
        if config.obs_host != self.host:
            self.host = config.obs_host
            changed = True
        if config.obs_port != self.port:
            self.port = config.obs_port
            changed = True
        if config.obs_password != self.password:
            self.password = config.obs_password
            changed = True
        
        # source name update is safe to do always
        if config.obs_avatar_source != self.source_name:
            self.source_name = config.obs_avatar_source
        
        if changed and self.client:
             logger.info("Connection details changed. Reconnecting...")
             self.disconnect()
             self.connect()
    
    def connect(self):
        try:
            self.client = ReqClient(host=self.host, port=self.port, password=self.password)
            logger.info(f"Connected to OBS WebSocket at {self.host}:{self.port}")
        except ConnectionRefusedError:
             logger.warning(f"OBS not connected. Is it open? (Connection Refused at {self.host}:{self.port})")
             self.client = None
        except Exception as e:
            if "WinError 10061" in str(e):
                 logger.warning(f"OBS not connected. Is it open? (Connection Refused at {self.host}:{self.port})")
            else:
                 logger.error(f"Failed to connect to OBS: {e}")
            self.client = None

    def disconnect(self):
        if self.client:
            ws = getattr(self.client, "base_client", None)
            if ws and hasattr(ws, "ws"):
                ws.ws.close()
            logger.info("Disconnected from OBS")

    def set_image(self, image_path: Union[str, Path]) -> None:
        if not self.client:
            return
        self.client.set_input_settings(
            name=self.source_name,
            settings={"file": str(image_path)},
            overlay=True,
        )

    def set_media(self, media_path: Union[str, Path]) -> None:
        if not self.client:
            return
        # for ffmpeg_source, 'local_file' is usually the key
        self.client.set_input_settings(
            name=self.source_name,
            settings={"local_file": str(media_path)},
            overlay=True,
        )

    def _get_text_font(self, text_source: str) -> Dict[str, object]:
        if not self.client:
            return {}
        if text_source not in self._font_cache:
            try:
                raw = self.client.send(
                    "GetInputSettings",
                    {"inputName": text_source},
                    raw=True,
                )
                font = {}
                if isinstance(raw, dict):
                    font = raw.get("inputSettings", {}).get("font", {})
                if isinstance(font, dict):
                    self._font_cache[text_source] = font
                else:
                    self._font_cache[text_source] = {}
            except Exception:
                self._font_cache[text_source] = {}
        return self._font_cache.get(text_source, {})

    def set_text(self, text: str, source_name: str, font_size: Optional[int] = None) -> None:
        if not self.client:
            return
        settings: Dict[str, object] = {"text": text}
        font = self._get_text_font(source_name)
        if font_size is not None:
            font = {**font, "size": font_size} if isinstance(font, dict) else {"size": font_size}
        if font:
            settings["font"] = font
            self._font_cache[source_name] = font
        self.client.set_input_settings(
            name=source_name,
            settings=settings,
            overlay=True,
        )

    async def type_text(self, text: str, source_name: str, **kwargs) -> int:
        """
        Kwargs can include:
        - line_width: int
        - max_lines: int (forced to 2 or more ideally)
        - base_font_size: int
        - min_font_size: int
        - font_step: int
        - typing_delay: float (delay between chars)
        - speaking_rate: float (chars per second for reading duration estimate)
        """
        line_width = kwargs.get("line_width", 42)
        max_lines = kwargs.get("max_lines", 2)
        base_font_size = kwargs.get("base_font_size", 75)
        min_font_size = kwargs.get("min_font_size", 20)
        font_step = kwargs.get("font_step", 2)
        typing_delay = kwargs.get("typing_delay", 0.03)
        min_page_duration = kwargs.get("min_page_duration", 2.0)
        speaking_rate = kwargs.get("speaking_rate", 12.0) # approx 12 chars/sec = slow speaking

        # use new pagination function
        from src.utils.text_utils import paginate_text_for_box

        logger.debug(f"type_text called. Len: {len(text)}, max_lines: {max_lines}, width: {line_width}")

        pages, font_size = paginate_text_for_box(
            text,
            line_width=line_width,
            max_lines=max_lines,
            base_font_size=base_font_size,
            min_font_size=min_font_size,
            font_step=font_step,
        )
        
        logger.debug(f"Pagination result: {len(pages)} pages.")
        if len(pages) > 1:
             logger.debug(f"Page 1: {pages[0][:20]}...")

        safe_typing_delay = max(0.001, typing_delay)
        
        for idx, page_text in enumerate(pages):
            logger.debug(f"Displaying Page {idx+1}/{len(pages)}")
            
            # 1. Type out this page
            
            # calculate duration for this page
            page_len = len(page_text)
            estimated_duration = page_len / max(1.0, speaking_rate)
            
            # animation time (typing)
            typing_duration = page_len * safe_typing_delay
            
            # we want the page to stay visible for `estimated_duration`.
            
            wait_time = max(0.0, estimated_duration - typing_duration)
            
            # ensure minimun display duration (especially for short pages)
            total_duration = typing_duration + wait_time
            if total_duration < min_page_duration:
                # add the missing time to wait_time
                wait_time += (min_page_duration - total_duration)

            current_displayed = ""
            for char_idx in range(1, len(page_text) + 1):
                current_displayed = page_text[:char_idx]
                self.set_text(current_displayed, source_name, font_size=font_size)
                if safe_typing_delay > 0:
                    await asyncio.sleep(safe_typing_delay)
            
            # ensure full text is set
            self.set_text(page_text, source_name, font_size=font_size)
            
            # wait for reading/speaking
            if idx < len(pages) - 1:
                logger.debug(f"Waiting {wait_time:.2f}s before next page...")
                await asyncio.sleep(wait_time)
                self.set_text("", source_name, font_size=font_size)
        
        return font_size

    def clear_text(self, source_name: str, font_size: int) -> None:
        self.set_text("", source_name, font_size=font_size)
