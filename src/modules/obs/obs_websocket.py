"""OBS over its WebSocket, without ever making the engine wait for it.

`obsws-python` is synchronous: every request is a send and a blocking receive.
Called from the event loop, each one froze the brain, the voice and the call
for a full round-trip to OBS — and with no timeout, forever if OBS hung. So one
worker thread owns the socket and every public method only leaves the request
on a table and returns.

The table keeps one request per (source, field): a caption typed faster than
OBS answers only needs its newest text, and an avatar swapped three times only
needs the last picture. The first request for a key keeps its place in line, so
different sources still update in the order they were asked for.

The library matches a reply to whatever it reads next, not by id, so after a
timeout the late reply would answer the next request. The worker drops the
socket on any failure but an answer from OBS, opens a new one, and sends the
failed request once more unless a newer one for the same field replaced it.
"""

import asyncio
import logging
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, Hashable, Optional, Union

from obsws_python import ReqClient
from obsws_python.error import OBSSDKRequestError

from src.interfaces.base_interfaces import OBSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.obs")

# the library dumps a full traceback when obs is simply closed; the worker says it in one line
logging.getLogger("obsws_python").setLevel(logging.CRITICAL)

# how long one request may take before the socket is given up on
DEFAULT_TIMEOUT = 2.0

# how long to wait before trying the socket again, and the ceiling on that wait
RETRY_SECONDS = 3.0
RETRY_CEILING = 30.0

Job = Callable[[Any], None]

# how long a shutdown waits for what was already asked to reach obs
FLUSH_CEILING = 1.0


def _refused(error: Exception) -> bool:
    return isinstance(error, ConnectionRefusedError) or "WinError 10061" in str(error)


class OBSController(OBSInterface):
    def __init__(self, host: str, port: int, password: str, source_name: str,
                 timeout: float = DEFAULT_TIMEOUT, client_factory: Optional[Callable[..., Any]] = None) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.source_name = source_name
        self.timeout = timeout
        self._factory = client_factory or ReqClient
        # the live connection; only the worker opens it, anyone may drop it
        self.client: Optional[Any] = None
        self._font_cache: Dict[str, Dict[str, Any]] = {}
        self._jobs: "OrderedDict[Hashable, Job]" = OrderedDict()
        # a request the worker has taken off the table and not finished yet
        self._busy = False
        # requests that failed once and were sent again: a second failure drops them
        self._retried: set = set()
        # sources obs said it has no way to take, warned about once each
        self._refusals: set = set()
        self._wake = threading.Condition()
        self._thread: Optional[threading.Thread] = None
        # bumped by disconnect: a worker from an older generation stops
        self._generation = 0
        # sockets opened so far: a caller that skips repeats knows a new one may have missed its last request
        self.connections = 0

    # --- lifecycle ----------------------------------------------------------

    def reload_config(self, config) -> None:
        """New connection details reconnect; a renamed source applies at once."""
        details = (config.obs_host, config.obs_port, config.obs_password)
        changed = details != (self.host, self.port, self.password)
        self.host, self.port, self.password = details
        self.timeout = float(getattr(config, "obs_timeout", self.timeout) or DEFAULT_TIMEOUT)
        if config.obs_avatar_source != self.source_name:
            self.source_name = config.obs_avatar_source
        # a source renamed or created since deserves its own warning if obs still refuses it
        self._refusals.clear()
        if changed and self._running():
            logger.info("Connection details changed. Reconnecting...")
            self._drop_client()
            with self._wake:
                self._wake.notify_all()

    def connect(self) -> None:
        """Starts the worker that opens the socket. Returns at once."""
        if self._running():
            return
        generation = self._generation
        self._thread = threading.Thread(target=self._run, args=(generation,), daemon=True, name="obs")
        self._thread.start()

    def disconnect(self) -> None:
        # what the shutdown just asked for, the picture taken down and the caption cleared, goes out first
        self._flush(min(self.timeout, FLUSH_CEILING))
        # dropped here, not merely closed: a caption still in flight afterwards
        # must find no socket rather than raise on one nobody is reading
        with self._wake:
            self._generation += 1
            self._jobs.clear()
            self._wake.notify_all()
        self._thread = None
        if self._drop_client():
            logger.info("Disconnected from OBS")

    def check(self) -> bool:
        """Whether OBS accepts a connection right now. Blocks up to the timeout: never call it on the loop."""
        try:
            client = self._open()
        except Exception as e:
            logger.warning(f"OBS not reachable at {self.host}:{self.port}: {e}")
            return False
        self._close(client)
        return True

    @property
    def connected(self) -> bool:
        return self.client is not None

    # --- the port -----------------------------------------------------------

    def set_image(self, image_path: Union[str, Path]) -> None:
        source, path = self.source_name, str(image_path)
        self._submit((source, "file"), lambda client: client.set_input_settings(
            name=source, settings={"file": path}, overlay=True))

    def set_media(self, media_path: Union[str, Path]) -> None:
        # for ffmpeg_source, 'local_file' is usually the key
        source, path = self.source_name, str(media_path)
        self._submit((source, "local_file"), lambda client: client.set_input_settings(
            name=source, settings={"local_file": path}, overlay=True))

    def set_text(self, text: str, source_name: str, font_size: Optional[int] = None) -> None:
        def job(client) -> None:
            settings: Dict[str, object] = {"text": text}
            font = self._text_font(client, source_name)
            if font_size is not None:
                font = {**font, "size": font_size}
            if font:
                settings["font"] = font
                self._font_cache[source_name] = font
            client.set_input_settings(name=source_name, settings=settings, overlay=True)
        self._submit((source_name, "text"), job)

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
        from src.utils.text_utils import paginate_text_for_box

        line_width = kwargs.get("line_width", 42)
        max_lines = kwargs.get("max_lines", 2)
        base_font_size = kwargs.get("base_font_size", 75)
        min_font_size = kwargs.get("min_font_size", 20)
        font_step = kwargs.get("font_step", 2)
        typing_delay = kwargs.get("typing_delay", 0.03)
        min_page_duration = kwargs.get("min_page_duration", 2.0)
        speaking_rate = kwargs.get("speaking_rate", 12.0)

        pages, font_size = paginate_text_for_box(
            text,
            line_width=line_width,
            max_lines=max_lines,
            base_font_size=base_font_size,
            min_font_size=min_font_size,
            font_step=font_step,
        )
        logger.debug(f"type_text: {len(text)} chars, {len(pages)} page(s)")

        safe_typing_delay = max(0.001, typing_delay)
        for idx, page_text in enumerate(pages):
            typing_duration = len(page_text) * safe_typing_delay
            wait_time = max(0.0, len(page_text) / max(1.0, speaking_rate) - typing_duration)
            # a short page still stays up long enough to be read
            if typing_duration + wait_time < min_page_duration:
                wait_time += min_page_duration - (typing_duration + wait_time)

            for char_idx in range(1, len(page_text) + 1):
                self.set_text(page_text[:char_idx], source_name, font_size=font_size)
                await asyncio.sleep(safe_typing_delay)
            self.set_text(page_text, source_name, font_size=font_size)

            if idx < len(pages) - 1:
                await asyncio.sleep(wait_time)
                self.set_text("", source_name, font_size=font_size)

        return font_size

    # --- the worker ---------------------------------------------------------

    def _running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _flush(self, seconds: float) -> None:
        """Waits up to `seconds` for the requests already on the table, while there is a socket to send them on."""
        deadline = time.monotonic() + seconds
        with self._wake:
            while (self._jobs or self._busy) and self.client is not None and self._running():
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                self._wake.wait(left)

    def _submit(self, key: Hashable, job: Job) -> None:
        with self._wake:
            # the newest value wins, the oldest request keeps its place in line
            self._jobs[key] = job
            self._wake.notify()

    def _open(self):
        return self._factory(host=self.host, port=self.port, password=self.password, timeout=self.timeout)

    @staticmethod
    def _close(client) -> None:
        ws = getattr(getattr(client, "base_client", None), "ws", None)
        if ws is not None:
            try:
                ws.close()
            except Exception as e:
                logger.debug(f"closing the OBS socket failed: {e}")

    def _drop_client(self) -> bool:
        client, self.client = self.client, None
        if client is None:
            return False
        self._close(client)
        return True

    def _run(self, generation: int) -> None:
        delay = RETRY_SECONDS
        warned = False
        while generation == self._generation:
            if self.client is None:
                try:
                    client = self._open()
                except Exception as e:
                    # said once per outage, not on every retry of it
                    if not warned:
                        if _refused(e):
                            logger.warning(f"OBS not connected. Is it open? (Connection Refused at {self.host}:{self.port})")
                        else:
                            logger.warning(f"OBS not connected ({self.host}:{self.port}): {e}")
                        warned = True
                    with self._wake:
                        self._wake.wait(delay)
                    delay = min(delay * 2, RETRY_CEILING)
                    continue
                if generation != self._generation:
                    self._close(client)
                    return
                self.client = client
                self.connections += 1
                delay = RETRY_SECONDS
                warned = False
                logger.info(f"Connected to OBS WebSocket at {self.host}:{self.port}")

            with self._wake:
                while not self._jobs and generation == self._generation and self.client is not None:
                    self._wake.wait()
                if generation != self._generation or self.client is None or not self._jobs:
                    continue
                key, job = self._jobs.popitem(last=False)
                self._busy = True

            client = self.client
            started = time.perf_counter()
            try:
                if client is None:
                    raise ConnectionError("the socket was dropped under the request")
                job(client)
                self._retried.discard(key)
            except OBSSDKRequestError as e:
                # obs answered, so the socket is still in step; a missing source would otherwise reconnect per character
                if key not in self._refusals:
                    self._refusals.add(key)
                    logger.warning(f"OBS refused a request for {key[0] if isinstance(key, tuple) else key!r}: {e}")
            except Exception as e:
                logger.warning(f"OBS request failed after {(time.perf_counter() - started) * 1000:.0f} ms "
                               f"({type(e).__name__}: {e}); reconnecting.")
                self._retry(key, job, generation)
                if self.client is client:
                    self._drop_client()
            finally:
                with self._wake:
                    self._busy = False
                    self._wake.notify_all()

    def _retry(self, key: Hashable, job: Job, generation: int) -> None:
        """Puts a failed request back at the front, once, unless a newer one for its field is already waiting."""
        with self._wake:
            if generation != self._generation:
                return
            if key in self._retried or key in self._jobs:
                self._retried.discard(key)
                return
            self._retried.add(key)
            self._jobs[key] = job
            self._jobs.move_to_end(key, last=False)

    def _text_font(self, client, source: str) -> Dict[str, Any]:
        """The font the text source already has, read once, so resizing keeps its face."""
        if source not in self._font_cache:
            font: Any = {}
            try:
                raw = client.send("GetInputSettings", {"inputName": source}, raw=True)
                if isinstance(raw, dict):
                    font = raw.get("inputSettings", {}).get("font", {})
            except OBSSDKRequestError as e:
                # obs answered, it just has no such input: a timeout is not caught here, the worker must see it
                logger.debug(f"reading the font of {source!r} failed: {e}")
            self._font_cache[source] = font if isinstance(font, dict) else {}
        return self._font_cache.get(source, {})
