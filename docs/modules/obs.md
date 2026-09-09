# OBS Module

← [Back to README](../../README.md) | [Architecture](../architecture.md) | [Avatar →](avatar.md)

---

## Overview

`OBSController` is the WebSocket transport to OBS Studio. It is **not** how Bea
appears — that is the [avatar port](avatar.md), and OBS is one of the places it
can draw to. This module owns the connection and the two kinds of source it can
drive:

1. **Avatar source** — the file swapped by the `png` avatar backend.
2. **Text source** — the typewriter driven by the `obs` caption backend.

```
src/modules/obs/
└── obs_websocket.py    OBSController implementing OBSInterface
```

Choose `stage` for the caption, or `model` / `vtube_studio` for the avatar, and
nothing here is used at all.

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

> **One request per character.** A 158-character line costs 159 WebSocket
> requests and 29.7 KB of JSON, because every one of them re-sends the font
> block. The `stage` caption backend sends the line **once** and animates it in
> the browser instead. `tests/test_stage.py` measures both.

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
and `Expression.interrupt()` cancels them together on barge-in, keeping what was
left unsaid in the resume buffer.

---

## Font Management

OBS text sources have their font settings stored in OBS. The controller reads the current font settings the first time it types to a given source, caches them, and then applies font-size changes per page. This avoids resetting user-configured font family/style.

---

## Avatar swap logic

This lives in `PngAvatar` (`src/modules/avatar/png.py`), behind the avatar port.
`Expression` asks for a mood and a state and never learns there is a file:

1. `show(mood, "talking")` before speaking.
2. `show(mood, "idle")` after.

An unknown mood falls back to `"normal"`. A **state** — `sleeping`, `listening` —
uses its own slot in `avatar_map` when there is one, and otherwise falls back to
the mood's image with a warning. It used to fall back silently, which is why the
sleeping avatar was never once seen.

---

## `clear_text()`

A convenience method on `OBSController` that sets the text source to an empty string, preserving the given font size:

```python
obs.clear_text(source_name="AIText", font_size=75)
```

It is equivalent to `set_text("", source_name, font_size=font_size)`.
`Expression` calls `set_text("", ...)` directly in most places; `clear_text()`
is a helper and the two are interchangeable.

---

## Hot Reload

`reload_config()` updates host/port/password. If any of those changed and a client was already connected, it disconnects and reconnects automatically.
