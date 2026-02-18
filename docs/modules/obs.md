# OBS Module

← [Back to README](../../README.md) | [Architecture](../architecture.md)

---

## Overview

The OBS module connects to OBS Studio via WebSocket and controls two types of sources in real time:

1. **Avatar source** — swaps the image/video file to reflect Bea's current mood and speaking state.
2. **Text source** — animates text with a typewriter effect for the speech bubble overlay.

```
src/modules/obs/
└── obs_websocket.py    OBSController implementing OBSInterface
```

---

## Connection

```python
obs = OBSController(host="localhost", port=4455, password="...", source_name="BeaPNG")
obs.connect()
```

If OBS is not running, the connection fails gracefully with a warning. The rest of the engine continues normally without OBS output.

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

Returns the final font size used (stored by the brain to correctly clear the source afterward).

The typing task and TTS playback task run in parallel — they are both launched as asyncio tasks and cancelled together if an interrupt arrives.

---

## Font Management

OBS text sources have their font settings stored in OBS. The controller reads the current font settings the first time it types to a given source, caches them, and then applies font-size changes per page. This avoids resetting user-configured font family/style.

---

## Avatar Swap Logic

When a response is generated with a given `mood`:

1. Brain looks up `(idle_path, talking_path)` from `png_map` for that mood.
2. Before speaking: `set_media(talking_path)` (or `set_image`).
3. After speaking: `set_media(idle_path)`.

If the mood is unknown, it falls back to `"normal"`.

---

## `clear_text()`

A convenience method on `OBSController` that sets the text source to an empty string, preserving the given font size:

```python
obs.clear_text(source_name="AIText", font_size=75)
```

It is equivalent to `set_text("", source_name, font_size=font_size)`. The brain calls `set_text("", ...)` directly in most places; `clear_text()` is provided as a helper and can be used interchangeably.

---

## Hot Reload

`reload_config()` updates host/port/password. If any of those changed and a client was already connected, it disconnects and reconnects automatically.
