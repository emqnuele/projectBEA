"""Her body in VTube Studio: a Live2D model that is yours, not ours.

Nothing is bundled and nothing is required. VTube Studio is the software most
VTubers already run — Neuro-sama included — and its plugin API is a WebSocket,
so projectBEA can drive a model it never has to ship, licence or render.

The whole port is synchronous, and this backend talks over a socket, so every
call drops a message on a queue that one background task drains. Nothing the
engine does while she is speaking can be made to wait on VTube Studio.

Protocol: https://github.com/DenchiSoft/VTubeStudio
"""

import asyncio
import contextlib
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.core.expression.pcm import ENVELOPE_FPS
from src.interfaces.base_interfaces import AvatarInterface, MouthFrames
from src.modules.avatar.mouth_timeline import MouthTimeline
from src.modules.avatar.vts_life import LifeSignals, life_values
from src.utils.logger import get_logger

logger = get_logger("bea.avatar.vts")

API_NAME = "VTubeStudioPublicAPI"
API_VERSION = "1.0"

PLUGIN_NAME = "projectBEA"
PLUGIN_DEVELOPER = "projectBEA"

# where the token VTube Studio issues is kept. Not in config.json: it is a
# credential, and config.json is read by an unauthenticated endpoint.
TOKEN_FILE = Path("data/vtube_studio_token.json")

# how long to wait before trying the socket again, and the ceiling on that wait
RETRY_SECONDS = 3.0
RETRY_CEILING = 30.0


class VTubeStudioError(Exception):
    pass


def _envelope_message(param: str, value: float) -> Dict[str, Any]:
    return {
        "faceFound": False,
        # "set" rather than "add": the mouth is hers alone while she talks
        "mode": "set",
        "parameterValues": [{"id": param, "value": round(float(value), 3)}],
    }


class VTubeStudioClient:
    """One authenticated connection, and the requests projectBEA makes on it."""

    def __init__(self, host: str, port: int, token_file: Path = TOKEN_FILE):
        self.host = host
        self.port = port
        self.token_file = token_file
        self._socket = None
        # one request at a time. The mouth injects a parameter every frame while
        # the worker may be setting an expression, and a socket is a single
        # send/recv pair: without this the two read each other's answers, and
        # websockets refuses a second concurrent recv outright.
        self._turn = asyncio.Lock()

    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    @property
    def connected(self) -> bool:
        return self._socket is not None

    # --- the wire -----------------------------------------------------------

    async def _send(self, message_type: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        if self._socket is None:
            raise VTubeStudioError("not connected")
        payload: Dict[str, Any] = {
            "apiName": API_NAME,
            "apiVersion": API_VERSION,
            "requestID": uuid.uuid4().hex,
            "messageType": message_type,
        }
        if data is not None:
            payload["data"] = data

        async with self._turn:
            await self._socket.send(json.dumps(payload))
            answer = json.loads(await self._socket.recv())

        if answer.get("messageType") == "APIError":
            detail = answer.get("data", {})
            raise VTubeStudioError(f"{detail.get('errorID')}: {detail.get('message')}")
        return answer.get("data", {})

    def _stored_token(self) -> Optional[str]:
        try:
            return json.loads(self.token_file.read_text()).get("token")
        except (OSError, ValueError):
            return None

    def _store_token(self, token: str) -> None:
        try:
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            self.token_file.write_text(json.dumps({"token": token}, indent=2))
        except OSError as e:
            # not fatal: she will just have to be allowed again next time
            logger.warning(f"Could not save the VTube Studio token: {e}")

    async def connect(self) -> None:
        """Opens the socket and authenticates, asking to be allowed if needed."""
        import websockets

        self._socket = await websockets.connect(self.url, open_timeout=5, ping_interval=20)

        token = self._stored_token()
        if not token:
            logger.info("Asking VTube Studio for permission — say yes in its window.")
            data = await self._send("AuthenticationTokenRequest", {
                "pluginName": PLUGIN_NAME,
                "pluginDeveloper": PLUGIN_DEVELOPER,
            })
            token = data.get("authenticationToken")
            if not token:
                raise VTubeStudioError("VTube Studio refused the plugin")
            self._store_token(token)

        data = await self._send("AuthenticationRequest", {
            "pluginName": PLUGIN_NAME,
            "pluginDeveloper": PLUGIN_DEVELOPER,
            "authenticationToken": token,
        })
        if not data.get("authenticated"):
            # a token that no longer works is worse than none: drop it and the
            # next attempt asks for permission again instead of failing forever
            with contextlib.suppress(OSError):
                self.token_file.unlink(missing_ok=True)
            raise VTubeStudioError(data.get("reason") or "authentication refused")

        logger.info(f"Connected to VTube Studio at {self.url}")

    async def close(self) -> None:
        if self._socket is not None:
            with contextlib.suppress(Exception):
                await self._socket.close()
            self._socket = None

    # --- what projectBEA asks of it -----------------------------------------

    async def current_model(self) -> Dict[str, Any]:
        return await self._send("CurrentModelRequest")

    async def expressions(self) -> List[Dict[str, Any]]:
        data = await self._send("ExpressionStateRequest", {"details": False})
        return data.get("expressions", [])

    async def hotkeys(self) -> List[Dict[str, Any]]:
        data = await self._send("HotkeysInCurrentModelRequest", {"modelID": ""})
        return data.get("availableHotkeys", [])

    async def set_expression(self, expression_file: str, active: bool,
                             fade: float = 0.25) -> None:
        await self._send("ExpressionActivationRequest", {
            "expressionFile": expression_file,
            "fadeTime": fade,
            "active": active,
        })

    async def trigger(self, hotkey_id: str) -> None:
        await self._send("HotkeyTriggerRequest", {"hotkeyID": hotkey_id})

    async def set_parameter(self, param: str, value: float) -> None:
        await self._send("InjectParameterDataRequest", _envelope_message(param, value))

    async def inject(self, values: Sequence[Tuple[str, float]], face_found: bool = False) -> None:
        """Every parameter of one frame in one request: one round-trip, not one per parameter."""
        await self._send("InjectParameterDataRequest", {
            "faceFound": face_found,
            "mode": "set",
            "parameterValues": [{"id": name, "value": round(float(value), 3)} for name, value in values],
        })

    async def input_parameters(self) -> Dict[str, Tuple[float, float]]:
        """The input parameters this vtube studio has, with their ranges. Asked once, never per frame."""
        data = await self._send("InputParameterListRequest")
        out: Dict[str, Tuple[float, float]] = {}
        for param in data.get("defaultParameters", []) + data.get("customParameters", []):
            name = param.get("name")
            if name is not None:
                out[name] = (float(param.get("min", -1.0)), float(param.get("max", 1.0)))
        return out


class VTubeStudioAvatar(AvatarInterface):
    """The port, backed by a queue and one background task, and a pump for what moves every frame.

    The pump sends one request per frame with everything that moves: the mouth
    while there is a line, and, with `stage.vts_life`, the head, eyes and blinks
    the 3D page gives her. Each frame is due at a fixed time from the start, and
    a frame that is late is skipped rather than played late, so the mouth keeps
    the voice's time however slowly VTube Studio answers.
    """

    supports_timeline = True

    def __init__(self, config, token_file: Path = TOKEN_FILE):
        self.config = config
        self.token_file = token_file
        self._commands: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._worker: Optional[asyncio.Task] = None
        self._mouth: Optional[asyncio.Task] = None
        self._active_expression: Optional[str] = None
        # the live connection, owned by the worker task and read by the mouth
        self._connected: Optional[VTubeStudioClient] = None
        self.model: Dict[str, Any] = {}
        self._timeline = MouthTimeline()
        self._fps = ENVELOPE_FPS
        self._life: Optional[LifeSignals] = LifeSignals() if self._stage.get("vts_life") else None
        # the input parameters vtube studio reported, asked once per connection
        self._ranges: Dict[str, Tuple[float, float]] = {}

    @property
    def _stage(self) -> dict:
        return getattr(self.config, "stage", None) or {}

    def reload_config(self, config) -> None:
        self.config = config
        wanted = bool(self._stage.get("vts_life"))
        if wanted and self._life is None:
            self._life = LifeSignals()
            self._ensure_pump()
        elif not wanted and self._life is not None:
            self._life = None

    # --- the port -----------------------------------------------------------

    def show(self, mood: str, state: str) -> None:
        expression = (self._stage.get("vts_expressions") or {}).get(mood)
        self._enqueue(("expression", expression))
        # the same rule the 3D body follows: a mood may carry a behaviour, and it
        # plays when she starts talking rather than every time her face changes
        hotkey = (self._stage.get("vts_clips") or {}).get(mood)
        if hotkey and state == "talking":
            self._enqueue(("hotkey", hotkey))
        if self._life is not None:
            self._life.set_state(state)
        if state != "talking":
            self._stop_mouth()

    def perform(self, clip: str) -> None:
        """A behaviour by name: a mood that maps to a hotkey, or a hotkey id."""
        hotkey = (self._stage.get("vts_clips") or {}).get(clip, clip)
        if hotkey:
            self._enqueue(("hotkey", hotkey))

    def mouth(self, envelope: MouthFrames, fps: int = ENVELOPE_FPS) -> None:
        """A whole line, from now: VTube Studio has no clock of ours, so this backend keeps it."""
        if not len(envelope):
            return
        loop = self._loop()
        if loop is None:
            return
        self._stop_mouth()
        self._fps = max(1, int(fps))
        self._timeline.whole(list(envelope), self._fps, loop.time())
        self._ensure_pump()

    def mouth_at(self, envelope: MouthFrames, fps: int, utterance_id: str, offset_ms: int) -> None:
        loop = self._loop()
        if loop is None or not len(envelope):
            return
        self._fps = max(1, int(fps))
        self._timeline.add(utterance_id, list(envelope), self._fps, offset_ms)
        self._ensure_pump()

    def mouth_sync(self, utterance_id: str, played_ms: int) -> None:
        loop = self._loop()
        if loop is None:
            return
        self._timeline.sync(utterance_id, played_ms, loop.time())
        self._ensure_pump()

    def close(self) -> None:
        self._stop_mouth()
        self._life = None
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.cancel()

        # the socket is let go of here rather than in the worker's own clean-up:
        # a cancelled task is not guaranteed another turn when the loop is on its
        # way out, and a socket nobody closed outlives the process that opened it
        client, self._connected = self._connected, None
        loop = self._loop()
        if client is not None and loop is not None:
            loop.create_task(client.close())

    # --- internals ----------------------------------------------------------

    @staticmethod
    def _loop() -> Optional[asyncio.AbstractEventLoop]:
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            # built before the engine started; the first call from inside the
            # loop arms the worker
            return None

    def _enqueue(self, command) -> None:
        loop = self._loop()
        if loop is None:
            return
        if self._worker is None or self._worker.done():
            self._worker = loop.create_task(self._run())
        try:
            self._commands.put_nowait(command)
        except asyncio.QueueFull:
            # she is talking faster than VTube Studio can answer; the newest
            # face is the right one to keep
            with contextlib.suppress(asyncio.QueueEmpty):
                self._commands.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                self._commands.put_nowait(command)

    def _ensure_pump(self) -> None:
        loop = self._loop()
        if loop is None or self._connected is None:
            return
        if self._mouth is None or self._mouth.done():
            self._mouth = loop.create_task(self._run_pump())

    def _stop_mouth(self) -> None:
        self._timeline.clear()
        # with life on the pump keeps running and closes the mouth on its next frame
        if self._life is None and self._mouth is not None and not self._mouth.done():
            self._mouth.cancel()
            self._mouth = None

    def _mouth_values(self, frame: Optional[Sequence[float]]) -> List[Tuple[str, float]]:
        param = self._stage.get("vts_mouth_param") or "MouthOpen"
        # optional and off by default: every VTS model has a mouth that opens,
        # and only some have one that changes shape
        form = self._stage.get("vts_mouth_form_param") or ""
        how_open, shape = (frame[0], frame[1]) if frame is not None else (0.0, 0.5)
        values = [(param, how_open)]
        if form and frame is not None:
            values.append((form, shape))
        return values

    async def _run_mouth(self, frames: MouthFrames, fps: int) -> None:
        """One whole line through the pump, returning when it has been mouthed."""
        loop = asyncio.get_running_loop()
        self._fps = max(1, int(fps))
        self._timeline.whole(list(frames), self._fps, loop.time())
        await self._run_pump()

    async def _run_pump(self) -> None:
        client = self._connected
        if client is None or not client.connected:
            return
        loop = asyncio.get_running_loop()
        step = 1.0 / self._fps
        start = last = loop.time()
        tick = 0
        speaking = False
        refused: set = set()
        try:
            if self._life is not None and not self._ranges:
                self._ranges = await client.input_parameters()
                missing = [n for n in ("FaceAngleX", "EyeLeftX", "EyeOpenLeft") if n not in self._ranges]
                if missing:
                    logger.info(f"VTube Studio has no {', '.join(missing)}; that part of her life is left out.")
            while self._connected is client:
                # asyncio fires a timer up to its clock's resolution early (15.6 ms on windows): woken early is still on time
                now = max(loop.time(), start + tick * step)
                if self._life is None and self._timeline.over(now):
                    break
                values: List[Tuple[str, float]] = []
                frame = self._timeline.frame_at(now)
                mouthing = bool(self._timeline.segments)
                if mouthing or speaking:
                    values += self._mouth_values(frame)
                speaking = mouthing
                life = self._life
                if life is not None:
                    signals = life.step(now - last, frame[0] if frame is not None else 0.0)
                    values += life_values(signals, self._ranges, self._stage.get("vts_life_params") or None)
                last = now
                if values:
                    try:
                        await client.inject(values, face_found=life is not None)
                    except VTubeStudioError as e:
                        # vtube studio answered, so the socket is fine: one refused frame must not end her life or the line
                        if str(e) not in refused:
                            refused.add(str(e))
                            logger.warning(f"VTube Studio refused a frame: {e}")
                # the next frame is due at a fixed time from the start; the ones already late are skipped
                tick = max(tick + 1, int((loop.time() - start) / step) + 1)
                await asyncio.sleep(max(0.0, start + tick * step - loop.time()))
            if speaking or self._life is None:
                await client.inject(self._mouth_values(None))
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await client.inject(self._mouth_values(None))
            raise
        except Exception as e:
            logger.debug(f"Driving VTube Studio stopped: {e}")

    async def _run(self) -> None:
        """Keeps one connection alive and drains the queue over it."""
        delay = RETRY_SECONDS
        while True:
            client = VTubeStudioClient(
                self._stage.get("vts_host") or "127.0.0.1",
                int(self._stage.get("vts_port") or 8001),
                self.token_file,
            )
            try:
                await client.connect()
                self._connected = client
                self._ranges = {}
                self.model = await client.current_model()
                delay = RETRY_SECONDS
                if self._life is not None:
                    self._ensure_pump()
                await self._drain(client)
            except asyncio.CancelledError:
                await client.close()
                raise
            except Exception as e:
                logger.warning(f"VTube Studio unreachable ({e}); retrying in {delay:.0f}s.")
            finally:
                self._connected = None
                await client.close()

            await asyncio.sleep(delay)
            delay = min(delay * 2, RETRY_CEILING)

    async def _drain(self, client: VTubeStudioClient) -> None:
        while True:
            kind, value = await self._commands.get()
            if kind == "expression":
                await self._apply_expression(client, value)
            elif kind == "hotkey":
                await client.trigger(value)

    async def _apply_expression(self, client: VTubeStudioClient, expression) -> None:
        """One expression at a time: VTS keeps them on until told otherwise."""
        if expression == self._active_expression:
            return
        if self._active_expression:
            with contextlib.suppress(VTubeStudioError):
                await client.set_expression(self._active_expression, active=False)
        if expression:
            await client.set_expression(expression, active=True)
        self._active_expression = expression


async def probe(config, token_file: Path = TOKEN_FILE) -> Dict[str, Any]:
    """One-off: what model is loaded and what it can do. For the dashboard.

    A separate connection from the avatar's, so asking does not disturb a live
    stream, and so it still answers before the backend has ever been switched on.
    """
    stage = getattr(config, "stage", None) or {}
    client = VTubeStudioClient(
        stage.get("vts_host") or "127.0.0.1",
        int(stage.get("vts_port") or 8001),
        token_file,
    )
    try:
        await client.connect()
        model = await client.current_model()
        if not model.get("modelLoaded"):
            return {"ok": True, "model": None,
                    "message": "Connected, but no model is loaded in VTube Studio",
                    "expressions": [], "hotkeys": []}
        return {
            "ok": True,
            "model": model.get("modelName"),
            "message": f"Connected to {model.get('modelName')}",
            "expressions": [e.get("file") for e in await client.expressions() if e.get("file")],
            "hotkeys": [{"id": h.get("hotkeyID"), "name": h.get("name")}
                        for h in await client.hotkeys()],
        }
    except Exception as e:
        return {"ok": False, "model": None, "message": str(e)[:300],
                "expressions": [], "hotkeys": []}
    finally:
        await client.close()
