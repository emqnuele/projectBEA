# OBS Module

← [Back to README](../../README.md) | [Architecture](../architecture.md) | [Avatar →](avatar.md)

---

## Overview

`OBSController` is the WebSocket transport to OBS Studio: the connection and the
two kinds of source it can drive.

1. **Avatar source** — the file swapped by the `png` avatar backend.
2. **Text source** — the typewriter driven by the `obs` caption backend.

```
src/modules/obs/
└── obs_websocket.py    OBSController implementing OBSInterface
```

Which of the two are in use depends on the backends in `stage` — see the
[avatar module](avatar.md). With `model` or `vtube_studio` for the avatar and
`stage` or `off` for the caption, this module is never called.

---

## Connection

```python
obs = OBSController(host="localhost", port=4455, password="...", source_name="BeaPNG", timeout=2.0)
obs.connect()
```

`obsws-python` is synchronous: every request is a send and a blocking receive.
The engine, the voice, the call and the dashboard share one event loop, so
`OBSController` never makes a request on it. One worker thread owns the socket;
`connect()` starts it and returns at once, and `set_image`, `set_media` and
`set_text` put a request on a table and return.

- **Latest wins.** The table holds one request per (source, field). A caption
  typed faster than OBS answers only sends its newest text; the first request
  for a key keeps its place in line, so different sources still update in the
  order they were asked for.
- **Timeout.** A request that takes longer than `obs_timeout` (2 s) is given up
  on. The library matches a reply to whatever it reads next rather than by id,
  so the socket is dropped and a new one opened; the requests still on the table
  go out on it.
- **Reconnection.** A closed or unreachable OBS is retried every 3 s, doubling
  up to 30 s, with one warning per outage. Requests left on the table are sent
  once it answers, so the avatar shows the current picture when OBS comes up.
- `disconnect()` stops the worker and drops the table.
- `check()` opens a separate connection and reports whether OBS accepts it. It
  blocks up to the timeout, so only the dashboard's test endpoint (a threadpool
  handler) calls it.

---

## Source Types

Set `obs_source_type` in config:

| Value | OBS Source Type | Suitable for |
|---|---|---|
| `"image"` | Image Source | Static PNGs |
| `"media"` | Media Source (ffmpeg) | MP4, GIF, WebM |

**Image switch:**
```python
obs.set_image("data/pngs/angry/talking.png")
```

**Media switch:**
```python
obs.set_media("data/pngs/angry/talking.mp4")
```

---

## Typing Animation

`type_text()` writes a message character-by-character into the OBS text source, paginating if the message exceeds the visible area.

Cost: one `set_text` per character, each carrying the font block. The worker
collapses the ones OBS was too slow to take, but a fast OBS still receives one
request per character. The `stage` caption backend sends the line in one message
and animates it in the page; `tests/test_stage.py` asserts the difference. The
font of a text source is read once, on the worker, and cached.

**Parameters:**

| Parameter | Description |
|---|---|
| `text` | The full message to type |
| `source_name` | OBS text source name |
| `line_width` | Characters per line before wrapping |
| `max_lines` | Max visible lines |
| `base_font_size` | Starting font size |
| `min_font_size` | Minimum font size (shrinks for long text) |
| `font_step` | Font size decrement step |
| `typing_delay` | Seconds between each character |
| `min_page_duration` | Minimum seconds a page stays visible |
| `speaking_rate` | Characters per second used to estimate reading time per page (default: `12.0`). Controls the post-typing wait so that longer pages stay visible longer. |

Returns the final font size used. `ObsTextCaption` keeps it so it can clear the
source at the size the text was actually typed at — a long line shrinks to fit,
and clearing at the configured size resizes the box on screen.

The typing task and the playback task run in parallel — both are asyncio tasks,
and `Expression.interrupt()` cancels them together on barge-in.

---

## Font Management

OBS text sources have their font settings stored in OBS. The controller reads the current font settings the first time it types to a given source, caches them, and then applies font-size changes per page. This avoids resetting user-configured font family/style.

---

## Avatar swap logic

This lives in `PngAvatar` (`src/modules/avatar/png.py`), behind the avatar port.
`Expression` asks for a mood and a state and never learns there is a file:

1. `show(mood, "talking")` before speaking.
2. `show(mood, "idle")` after.

An unknown mood falls back to `"neutral"`. The states `sleeping` and `listening`
use their own entry in `avatar_map` when there is one, and otherwise fall back to
the mood's image and log a warning. Full resolution order is in the
[avatar module](avatar.md).

---

## Hot Reload

`reload_config()` updates host/port/password. If any of those changed and a client was already connected, it disconnects and reconnects automatically.
