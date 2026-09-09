# Avatar Module

← [Back to README](../../README.md) | [Architecture](../architecture.md) | [OBS →](obs.md)

---

## Overview

How Bea appears on screen is a **port**, not a setting buried in the speech path.
`Expression` hands down what she *is* — a mood and a state — and a backend
decides what that means.

```
src/modules/avatar/
├── factory.py       build_avatar(config, obs, publisher)
├── png.py           PngAvatar          one image per mood, swapped in OBS
├── model3d.py       Model3DAvatar      a VRM drawn in a browser source
└── vtube_studio.py  VTubeStudioAvatar  your Live2D model, over the VTS API

src/modules/caption/
├── factory.py       build_caption(config, obs, publisher)
├── obs_text.py      ObsTextCaption     typed into an OBS text source
├── stage.py         StageCaption       typed in the browser source
└── silent.py        SilentCaption      no words at all
```

The two choices are independent. "PNG avatar with the nicer browser caption" and
"3D body with the bubble still in OBS" are both setups people want, so neither
is allowed to imply the other.

---

## The contract

`src/interfaces/base_interfaces.py`:

```python
class AvatarInterface(ABC):
    def show(self, mood: str, state: str) -> None: ...   # idle|talking|listening|sleeping
    def perform(self, clip: str) -> None: ...            # a named behaviour
    def mouth(self, envelope, fps: int) -> None: ...     # loudness per frame, in [0,1]
    def reload_config(self, config) -> None: ...
    def close(self) -> None: ...
```

Three things are deliberate:

**Every method is synchronous.** A backend that needs the network queues the
work. Nothing the engine does while she is speaking waits on a socket.

**`mouth` takes the whole utterance, not one value per frame.** A page can
replay it against its own clock; a backend that needs a stream paces it itself.

**A backend may ignore what it cannot do.** `PngAvatar.perform` and
`PngAvatar.mouth` are no-ops, and say so. That is why nothing above the port
has to ask which backend is running.

`CaptionInterface` is `say(text)` (awaitable, because the OBS backend animates
over time and barge-in cancels it mid-sentence) and `clear()`.

---

## Choosing a backend

Dashboard → **Settings → Stream**, or `config.json`:

```json
"stage": {
  "avatar_backend": "png",      // png | model | vtube_studio
  "caption_backend": "obs"      // obs | stage | off
}
```

Both are hot-reloadable: the engine rebuilds only the port that changed, so
switching the caption does not drop a loaded 3D model. An unknown name falls
back to the default with a warning rather than leaving her invisible.

---

## `png` — one image per mood

What projectBEA has always done. `avatar_map` holds an `idle` and a `talking`
path per mood, and the backend swaps the file in an OBS image or media source.

States get their own slot when you give them one:

```json
"avatar_map": {
  "angry":    { "idle": "data/pngs/angry/idle.png", "talking": "data/pngs/angry/talking.png" },
  "sleeping": { "idle": "data/pngs/sleeping.png",   "talking": "data/pngs/sleeping.png" }
}
```

`sleeping` and `listening` are **states, not moods**. Without a slot the backend
falls back to the mood's image and warns once — it used to fall back silently,
which is why the sleeping avatar was never once seen.

---

## `model` — a 3D VRM

The model is rendered by a page you point an OBS **Browser Source** at:
`http://127.0.0.1:8000/stage`. The engine publishes expression weights, a
behaviour name and a loudness envelope; the page owns three.js.

```json
"stage": {
  "avatar_backend": "model",
  "model_path": "data/models/VRM1_Constraint_Twist_Sample.vrm",
  "clips_dir": "data/clips",
  "shot": "bust",
  "mood_clips": { "angry": "lean_in" },
  "lipsync_fps": 30,
  "background": ""
}
```

### Why VRM and not glTF

A plain `.glb` names its bones however the artist felt like: `Bip01_L_UpperArm`,
`mixamorig:LeftArm`, `braccio_sx`. **VRM standardises the names** — 54 humanoid
bones and 18 expressions (five emotions, five visemes, blinks, look direction).
That is the whole reason a mapping written today works on a model you download
next year, and the reason behaviours are portable at all.

### Getting a model

**No model ships with projectBEA.** It is 11 MB of binary that most people
replace with their own, and the repository is a bad place for either — the same
call `.gitignore` already makes for the speech models.

```bash
make model      # fetches pixiv's free VRM 1.0 sample and one .vrma clip
```

Then read what it allows, which is a thing only VRM lets you do:

```bash
uv run python tools/inspect_vrm.py data/models/*.vrm
```

```
  Licence, as the file itself declares it
    authors:  pixiv Inc.
    avatarPermission: everyone — anyone may use this avatar
    commercialUsage: corporation — companies may use it commercially
    creditNotation: unnecessary — no credit required
    allowRedistribution: yes

  Rig: 54 humanoid bones
  Expressions: 18 presets
    emotions: happy, angry, sad, relaxed, surprised, neutral
    visemes:  aa, ih, ou, ee, oh
```

Run the same tool on your own model before you go live. It tells you what is
missing — no `aa` viseme means her mouth cannot move; no emotions means one face
for every mood.

To make your own: **VRoid Studio** is free, runs on macOS and Windows, and
exports VRM with all 18 expressions already wired.

### Behaviours

A `.vrma` clip drives humanoid bones **by standard name**, so it carries no mesh,
no material and no texture — 11 KB for three seconds. That is why a clip library
can ship with the repo while a model cannot. Drop clips in `clips_dir`; they
appear by name in the dashboard, and `mood_clips` picks one per mood.

### Two traps worth knowing

Both were found by looking at the thing on screen, and both are handled in
`src/web/frontend/src/stage/avatar.js`:

- **The 180° turn belongs to VRM 0.x only.** `VRMUtils.rotateVRM0` applies it
  where it is due. An unconditional `rotation.y = Math.PI` shows you the back of
  the head of every VRM 1.0 model.
- **The camera is framed off the `head` bone**, never off hardcoded numbers.
  That is what makes one `shot` setting frame a 1.4 m model and a 1.8 m one the
  same way.

---

## `vtube_studio` — your own Live2D model

Nothing is bundled and nothing is required. VTube Studio is what most VTubers
already run; if you have it, projectBEA drives it over its plugin API.

```json
"stage": {
  "avatar_backend": "vtube_studio",
  "vts_host": "127.0.0.1",
  "vts_port": 8001,
  "vts_expressions": { "angry": "furious.exp3.json" },
  "vts_clips": { "lean_in": "hotkey-id-or-name" },
  "vts_mouth_param": "MouthOpen"
}
```

| Port call | VTube Studio request |
|---|---|
| `show(mood, state)` | `ExpressionActivationRequest` with `vts_expressions[mood]` |
| `perform(clip)` | `HotkeyTriggerRequest` with `vts_clips[clip]` |
| `mouth(envelope, fps)` | `InjectParameterDataRequest` on `vts_mouth_param`, one per frame |

Turn the API on in VTube Studio (**Settings → Start API**). The first time she
connects it asks you to allow the plugin; say yes, and the token is stored in
`data/vtube_studio_token.json` — gitignored, and never in `config.json`, which is
served by an unauthenticated endpoint.

Expressions and hotkeys are named by **whoever rigged your model**, so the
dashboard reads them from the connected model and offers them as a list rather
than a text box. Press **Test the connection** to fill it.

Two differences from the other backends, both handled inside the adapter:

- VTube Studio has no clock of ours, so this is the one backend that **paces the
  mouth itself**, one message per frame.
- VTS leaves an expression on until told otherwise, so the adapter **turns the
  previous one off** before activating the next.

---

## Lip sync

`envelope()` in `src/core/expression/pcm.py` is the per-frame RMS of the audio
she is about to say, normalised to `[0, 1]`. Not a phoneme model and not a
viseme classifier: the shape of the line, which is all a mouth needs.

It is computed on this machine because the audio is played on this machine and
the page never hears it. Six seconds of speech is **180 frames, about 0.2 ms and
1.2 KB of JSON** — small enough to send whole, ahead of playback, so the page can
run it off its own clock instead of waiting for 30 messages a second.

A lip sync failure is logged and swallowed: a mouth that breaks must never stop
her from speaking.

---

## The mood → face table

`src/core/expression/face.py` turns a mood into VRM expression weights, the same
way `prosody.py` turns it into a way of speaking.

| mood | (valence, arousal) | weights |
|---|---|---|
| `normal` | (0.00, 0.00) | `neutral 1.0` |
| `shock` | (-0.15, 0.85) | `surprised 0.9` |
| `love` | (0.90, 0.50) | `happy 1.0` |
| `cry` | (-0.70, -0.25) | `sad 1.0` |
| `angry` | (-0.80, 0.85) | `angry 1.0` |
| `ew` | (-0.50, 0.15) | `angry 0.45` + `sad 0.35` |
| `bored` | (-0.30, -0.70) | `relaxed 0.25` + `sad 0.35` |

Bea has seven moods; VRM standardises five emotions. `ew` and `bored` have no
preset of their own and are blends — the only judgement calls in the file.

`tests/test_face.py` checks every row against the valence/arousal vectors in
`moods.py`, and it earns its keep: the first draft of `bored` was
`relaxed 0.7`, and the test rejected it with *"bored feels bad but looks good"*.
`relaxed` in VRM means *at ease*, so she came out looking pleased to be ignoring
you. It is the kind of mistake you do not catch by eye and everybody catches on
stream.

---

## The stage channel

`src/core/stage.py` is the fan-out to the browser source. Deliberately **not**
`EventManager`: that one replays a backlog to every new subscriber, which is
right for a dashboard reading a log and wrong here — OBS reloads a browser
source whenever you toggle it, and a replay would have her act out the last
minute of the stream again.

A page that connects gets **one snapshot** of how she looks now, and patches
after that. Keys like `envelope` and `perform` describe a moment rather than a
state and are never stored, so a page that reconnects does not mouth a sentence
nobody is saying.

| Endpoint | What it is |
|---|---|
| `GET /stage` | the page to point a Browser Source at |
| `GET /stage/stream` | SSE: one snapshot, then patches |
| `GET /stage/config` | what the page needs to draw her — never a secret |
| `GET /stage/model` | the configured `.vrm` |
| `GET /stage/clips` | the behaviours installed, by name |
| `GET /stage/clips/{name}` | one `.vrma` |
| `GET /stage/preview` | one avatar image, for the dashboard preview |

---

## Adding a backend

1. Implement `AvatarInterface` in `src/modules/avatar/`.
2. Add a builder to `BUILDERS` in `factory.py`. Put the import **inside** the
   builder, so choosing another backend never pays for yours.
3. If it needs somewhere to publish, add its name to `NEEDS_PUBLISHER`.
4. Add it to `AVATARS` in `src/setup/wizard.py`.

`tests/test_avatar_backends.py` walks `BUILDERS` and checks every registered
backend honours the port, so step 1 cannot be half-done.
