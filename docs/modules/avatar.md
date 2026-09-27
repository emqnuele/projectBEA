# Avatar Module

← [Back to README](../../README.md) | [Architecture](../architecture.md) | [OBS →](obs.md)

---

## Overview

Two ports decide how Bea reaches the screen. `Expression` calls them with a mood
and a state and never learns which backend is behind either.

```
src/modules/avatar/                          src/modules/caption/
├── factory.py   build_avatar()              ├── factory.py   build_caption()
├── png.py       PngAvatar                   ├── obs_text.py  ObsTextCaption
├── model3d.py   Model3DAvatar               ├── stage.py     StageCaption
└── vtube_studio.py  VTubeStudioAvatar       └── silent.py    SilentCaption
```

They are chosen independently: any avatar backend works with any caption
backend.

| | Avatar backends | Caption backends |
|---|---|---|
| key | `png` · `model` · `vtube_studio` | `obs` · `stage` · `off` |
| needs OBS WebSocket | `png` only | `obs` only |
| needs a browser source | `model` | `stage` |

---

## `AvatarInterface`

```python
class AvatarInterface(ABC):
    def show(self, mood: str, state: str) -> None: ...
    def perform(self, clip: str) -> None: ...
    def mouth(self, envelope: Sequence[float], fps: int) -> None: ...
    def reload_config(self, config) -> None: ...
    def close(self) -> None: ...
```

| Method | Called | Argument |
|---|---|---|
| `show` | before and after every spoken line, and on a state change | `mood` is one of `MOODS`; `state` is `idle`, `talking`, `listening`, `thinking` or `sleeping` |
| `perform` | when a mood maps to a behaviour | a clip name, resolved by the backend |
| `mouth` | once per line, **before playback starts** | the whole envelope, so the backend can pace it against its own clock |
| `close` | when the backend is swapped out, and on shutdown | — |

**The state she rests in.** `talking` is the only state the speech path chooses
for itself. The others are set by whoever knows about them — `sleeping` by the
consciousness, `listening` by the voice surface while she sits in a call — and
`Expression` remembers the last one: a line ends by going back to it, not to a
hardcoded `idle`. A state that arrives mid-line is recorded and applied when she
stops talking, so someone walking into the call cannot take her talking face off
her halfway through a word.

`thinking` is shown by the consciousness for the length of a turn somebody is
waiting on (not her own idle ticks), through `Expression.show_thinking`. It is a
face, not a place she rests: it is never stored as the resting state, it is
skipped while she speaks or sleeps, and it never touches `is_speaking`, which
barge-in reads. A backend that has nothing to show for it draws the mood's `idle`.

Three rules a backend has to hold to:

- **Every method is synchronous.** A backend that needs the network queues the
  work. Blocking here blocks the turn she is speaking in.
- **`mouth` receives the whole utterance.** Do not expect a call per frame.
- **Ignore what you cannot do.** `perform` and `mouth` are no-ops on `PngAvatar`.
  Callers never branch on the backend.

`CaptionInterface` is `say(text)` and `clear()`. `say` is awaitable because the
OBS backend animates over time and barge-in cancels it mid-sentence.

---

## Configuration

Everything lives in the `stage` block. Dashboard → **Settings → Stream** writes
the same keys.

```json
"stage": {
  "avatar_backend": "png",
  "caption_backend": "obs",
  "lipsync_fps": 30
}
```

| Key | Default | Notes |
|---|---|---|
| `avatar_backend` | `"png"` | Unknown value → `png`, with a warning. |
| `caption_backend` | `"obs"` | Unknown value → `obs`, with a warning. |
| `lipsync_fps` | `30` | Frames per second of mouth data. |

Both are hot-reloadable. `AIVtuberBrain._reload_stage` rebuilds only the port
whose backend changed, so switching the caption does not drop a loaded model or
an authenticated socket.

---

## `png`

Swaps a file in an OBS image or media source. `obs_source_type` decides which.

```json
"avatar_map": {
  "angry":    { "idle": "data/pngs/angry/idle.png", "talking": "data/pngs/angry/talking.png" },
  "sleeping": { "idle": "data/pngs/sleeping.png",   "talking": "data/pngs/sleeping.png" }
}
```

Keys are moods, plus optionally the two non-speech **states**, `sleeping` and
`listening`. Resolution order for `show(mood, state)`:

1. `avatar_map[state]` if `state` is `sleeping` or `listening` and has an entry
2. `avatar_map[mood]`, taking `talking` or `idle`
3. `avatar_map["neutral"]`
4. any entry at all

A missing state entry logs one warning per state, not per frame.

`close()` blanks the source. The image is the only thing this backend leaves
behind, and another backend taking over mid-stream would otherwise be drawn on
top of the face it replaced.

---

## `model`

Renders a VRM in a page served at `/stage`, which you add to OBS as a **Browser
Source**. The backend publishes to the stage channel; the page owns three.js.

```json
"stage": {
  "avatar_backend": "model",
  "model_path": "data/models/AvatarSample_B.vrm",
  "clips_dir": "data/clips",
  "shot": "bust",
  "mood_clips": { "angry": "lean_in" },
  "background": ""
}
```

| Key | Notes |
|---|---|
| `model_path` | Any path on this machine. Served by `GET /stage/model`; the page never touches the filesystem. |
| `clips_dir` | `.vrma` files, listed by `GET /stage/clips` and offered in the dashboard. |
| `shot` | `bust`, `half` or `full`. Computed from the `head` and `hips` bones, so it frames any model the same way regardless of its height. |
| `mood_clips` | mood → clip name. A mood without one changes expression only. |
| `idle_clip` | The clip that loops under her (`idle_loop` from `make model`). Empty means a still procedural pose. |
| `state_clips` | state → clip that loops under her in that state instead of `idle_clip`. |
| `expression_intensity` | Scales every emotion weight on the page (neutral excepted). |
| `face_blend_blink` | Turns `overrideBlink: none` into `blend` on the emotions, so a blink fades out under a face whose eyes are already shut. |
| `mouth_under_emotion` | The lip sync is scaled towards this as the emotions on her face add up to one. |
| `background` | A CSS colour behind her. Empty is transparent, which is what OBS composites over your scene. |

### Why the format matters

A plain `.glb` names bones however the artist chose — `Bip01_L_UpperArm`,
`mixamorig:LeftArm`. VRM fixes the names: 54 humanoid bones and 18 expressions
(`happy angry sad relaxed surprised`, the visemes `aa ih ou ee oh`, blinks, look
direction). Every mapping in this module is written against those names, which
is what makes it work on a model the code has never seen.

The same applies to behaviours. A `.vrma` drives bones by standard name and
carries no mesh, material or texture — a three-second clip is about 11 KB, and
it plays on any VRM.

### Checking a model

```bash
uv run python tools/inspect_vrm.py data/models/bea.vrm
```

Prints the rig, the expressions and the licence fields VRM stores inside the
file. Use it to find out before going live whether a model is missing the `aa`
viseme (her mouth cannot move) or the emotion presets (one face for every mood).
It exits non-zero when something required is absent.

`make model` downloads the default model (AvatarSample_B, VRM 1.0, by VRoid
Project) and its idle motion (`idle_loop.vrma`, from pixiv/ChatVRM) into
`data/models` and `data/clips`, both gitignored. `--all` fetches every entry of
the catalog, `--id <id>` one of them and `--list` shows them with their licences.

The catalog lives in `src/modules/avatar/catalog.py`. Every entry is pinned to a
commit or a tag, never a branch, and checked against a SHA-256: what arrives is
loaded and run by a renderer, so anything that does not match is deleted rather
than kept. A file already at that path is never overwritten — it is yours.

| id | kind | licence |
|---|---|---|
| `avatar-sample-b` (default) | model | VRoid Project (pixiv): commercial use, redistribution and changes allowed, no credit needed |
| `idle-loop` (default) | clip | pixiv/ChatVRM, MIT |
| `constraint-twist` | model | pixiv three-vrm sample, MIT |
| `seed-san` | model | VirtualCast, Inc.: commercial use and redistribution allowed, **credit required** |

### The body: a base layer and gestures

`src/web/frontend/src/stage/body.js` owns the animation mixer.

three.js averages the actions on each bone by weight and gives any weight left
below one to the bone's original value, which on a VRM is the T-pose. Two rules
follow from that:

- **A base action always holds weight one.** It is the clip for the current
  state (`state_clips`, else `idle_clip`), or, with no clip or a clip that fails
  to load, a procedural pose with the arms 21° from vertical and the elbows
  slightly bent. The procedural pose is built synchronously, so the model is
  never drawn in the T-pose while the idle clip downloads. Every base clip gets
  the procedural arm tracks merged in for any arm bone it does not animate.
  Changing base crossfades over 0.5 s.
- **A gesture is layered, not crossfaded.** A gesture usually animates a few
  bones; crossfading it against the base would fade the base out on every bone
  and drop the rest to the T-pose. Instead a gesture at fade fraction `f` gets
  weight `f / (1 - f)`: against the base at weight 1 that is exactly a share `f`
  of the bones it animates, and every other bone stays on the base. It fades in
  over 0.25 s and out over 0.3 s once it ends; a newer gesture fades the older
  one out.

The hips position track of every clip is moved so its first key sits over the
model's own hips: clips are authored on another body (`idle_loop` stands 15 cm to
one side) and the shot is framed on the rest pose. The pure parts — which clip
is the base, the re-anchoring, the procedural pose, the gesture weight — live in
`motion.js` and are tested with `node --test`.

### Life on top of the body

`src/web/frontend/src/stage/life.js` adds what no clip carries: blinking,
breathing, a weight shift, the eyes and the head. Every one of these is an
**offset** multiplied onto the pose the mixer wrote this frame, never a pose of
its own, so the idle clip underneath keeps playing. The mixer only writes a bone
whose value changed, so the page takes last frame's offsets back off before the
mixer runs (`life.undo()`), then lets the mixer write, then adds this frame's.

Each frame, in order: `life.undo()` → `body.update()` → `life.update()` → face
and mouth → `vrm.update()` → render. The step handed to everything after the
mixer is capped at 1/20 s (or the `max_fps` frame, if slower): spring bones
scale with the step, and a browser source that OBS stopped drawing for seconds
would otherwise throw the hair in one frame.

States are a table in `states.js`:

| state | what it looks like |
|---|---|
| `idle` | the gaze drifts around the camera, the eyes jump at least 0.6 s apart, 1.6 s on average, the head follows at 16 % of the angle |
| `listening` | eyes on the camera, a small nod every 2.5 s ± 0.7 s |
| `thinking` | eyes up and to one side; the head follows further (30 %) and slower, so the eyes visibly lead; fewer blinks |
| `talking` | the head dips with the loudness of her own voice |
| `sleeping` | eyes shut, the head forward, only the breathing left |

A new state's numbers are eased in over about a third of a second. Eye jumps
are a minimum gap plus an exponential wait, a rate per second rather than a
chance per frame, so they happen as often at 30 fps as at 144. While a gesture
holds the body, the head's motion is halved so the two do not add up; a gesture
whose clip drives the eyes takes the gaze once it holds more than half the body.

On VRM 0.x, which `rotateVRM0` turns 180° about y, every offset about x and z is
negated, so she nods down and looks up on both versions.

### Notes for the renderer

`src/web/frontend/src/stage/avatar.js`:

- `frustumCulled` is off on every mesh: skinned bounding boxes do not follow the
  bones, so a raised arm could otherwise be culled at the edge of the frame. A
  `VRMLookAtQuaternionProxy` is created at load for clips that drive the gaze.
- Turning the model 180° is correct for **VRM 0.x only**. `VRMUtils.rotateVRM0`
  applies it conditionally; an unconditional `rotation.y = Math.PI` faces every
  VRM 1.0 model away from the camera.
- Camera framing reads the `head` and `hips` world positions and solves the
  distance from the FOV. Hardcoding a position ties the shot to one model's
  height.
- The page is a separate Vite entry (`stage.html`). three.js is behind a dynamic
  import, so it is fetched only when `avatar_backend` is `model`. Importing from
  `src/stage/` anywhere in the dashboard would pull it into the main bundle.

---

## `vtube_studio`

Drives a VTube Studio instance over its plugin API. Nothing is bundled; the
model and the software are the user's.

```json
"stage": {
  "avatar_backend": "vtube_studio",
  "vts_host": "127.0.0.1",
  "vts_port": 8001,
  "vts_expressions": { "angry": "furious.exp3.json" },
  "vts_clips": { "happy": "hotkey-id-or-name" },
  "vts_mouth_param": "MouthOpen"
}
```

| Port call | Request |
|---|---|
| `show(mood, state)` | `ExpressionActivationRequest`, file from `vts_expressions[mood]`; on `talking`, also `HotkeyTriggerRequest` from `vts_clips[mood]` |
| `perform(clip)` | `HotkeyTriggerRequest`, id from `vts_clips[clip]`, falling back to the name itself |
| `mouth(envelope, fps)` | `InjectParameterDataRequest` on `vts_mouth_param`, one per frame, `mode: "set"` |

**Authentication.** `AuthenticationTokenRequest` prompts the user inside VTube
Studio; the token is written to `data/vtube_studio_token.json` and reused with
`AuthenticationRequest` on later sessions. A token that stops authenticating is
deleted so the next attempt asks again instead of failing forever. It is kept
out of `config.json` because `GET /config` is unauthenticated.

**Threading.** Every request holds a lock for its send and its reply: a socket is
one send/recv pair, and the mouth writes to it 30 times a second while the worker
may be setting an expression. `_run` owns one connection and drains a bounded queue over it,
reconnecting with backoff from 3s to 30s. When the queue fills, the oldest
command is dropped — the newest face is the correct one. The mouth runs in its
own task so a new line cancels the previous one.

**A behaviour per mood.** `vts_clips` is keyed by mood, exactly like `mood_clips`
on the 3D backend, and fires when she starts talking rather than on every change
of face. `perform` resolves through the same map, so a hotkey id passed straight
in still works.

**Two behaviours specific to this backend.** VTube Studio holds an expression
until told otherwise, so the adapter deactivates the previous one before
activating the next. And it has no clock shared with the engine, so this is the
only backend that paces the envelope itself.

**Discovery.** Expression files and hotkey ids are defined by whoever rigged the
model. `GET /vts/model` returns both from the connected instance so the dashboard
can offer a list.

---

## Semantic Picker

The moods and clips are no longer hardcoded strict matches. A semantic picker (`src/core/expression/picker.py`) uses a small local embedding model to map whatever expression she names to the closest valid mood or installed clip. This means if she decides to write `<do:shrug>` and the file is named `003_dismissive_wave.vrma`, the picker understands the meaning and plays the right clip, rather than failing silently. It is extremely fast, cached in memory, and prevents her natural vocabulary from breaking the visual output.

---

## Mood → expression

`src/core/expression/face.py`. `weights_for(mood)` returns a weight for every VRM
emotion, zeros included, so a face is never left wearing part of the last mood.

| mood | (valence, arousal) | weights |
|---|---|---|
| `neutral` | (0.00, 0.00) | `neutral 1.0` |
| `happy` | (0.90, 0.50) | `happy 1.0` |
| `sad` | (-0.70, -0.25) | `sad 1.0` |
| `angry` | (-0.80, 0.85) | `angry 1.0` |
| `surprised` | (-0.15, 0.85) | `surprised 0.9` |
| `disgusted` | (-0.50, 0.15) | `angry 0.45` + `sad 0.35` |
| `bored` | (-0.30, -0.70) | `relaxed 0.25` + `sad 0.35` |

VRM standardises five emotions; `MOODS` has seven. `disgusted` and `bored` are blends.

`tests/test_face.py` asserts that the weights agree with the valence/arousal
vectors in `moods.py`: a mood below -0.2 valence must weigh `sad`/`angry` above
`happy`/`relaxed`, and the reverse above +0.2. This catches the easy mistake with
`relaxed`, which means *at ease* and reads as contentment — weighting `bored`
toward it produces a face that looks pleased rather than unbothered.

The table is also checked against the sample model, when it is present, so a
weight cannot name an expression no real VRM has.

---

## Lip sync

`envelope(audio, sample_rate, fps)` in `src/core/expression/pcm.py` returns the
per-frame RMS of the audio, normalised to `[0, 1]` and rounded to three decimals.

The line is normalised against its own peak, but never against a peak below
`MOUTH_FLOOR_RMS` (0.05). Dividing by the peak alone makes every line as loud as
every other, so a whisper is drawn exactly like a shout; the floor keeps a quiet
line quiet while any normal one still opens her mouth all the way.

It is computed in `Expression._speak_local` between synthesis and playback, and
on the call route it is accumulated per sentence as each one is synthesised. It
runs on this machine because the audio is played here; the page never hears it.

Cost for six seconds at 30 fps: 180 frames, ~0.2 ms, ~1.2 KB of JSON. Small
enough to send in one message ahead of playback rather than streaming it.

`Expression._move_mouth` catches and logs any failure. A broken mouth must not
stop her from speaking.

---

## The stage channel

`src/core/stage.py`. A fan-out to however many browser sources are open, plus
the current state.

```python
channel.publish({"mood": "angry", "state": "talking"})   # merged into the state
channel.publish({"envelope": [...], "envelope_fps": 30}) # sent, not stored
channel.snapshot()                                       # what a new page receives
```

Keys in `TRANSIENT` (`envelope`, `perform`) describe a moment and are fanned out
without being stored. A page connecting mid-utterance is not made to mouth a
sentence that has already ended.

There is no backlog. OBS reloads a browser source whenever it is toggled, and a
subscriber that received a replay would act the last minute out again. A queue
that fills is dropped rather than awaited.

Saving settings publishes `{"config": public_config(...)}`, so a running page
picks up a new shot or background without being reloaded by hand. The page
reloads itself only when the change is structural — a different backend, or a
different model, which `model_id` (the file name and its mtime) detects. That
same push is what keeps the preview in the dashboard current.

| Endpoint | Returns |
|---|---|
| `GET /stage` | the page for the Browser Source |
| `GET /stage/stream` | SSE: one `snapshot`, then `patch` messages |
| `GET /stage/config` | backends, shot, lip sync rate, caption typography, `model_id` |
| `GET /stage/model` | the configured `.vrm` |
| `GET /stage/clips` | clips in `clips_dir`, each with `role`: `base` or `gesture` |
| `GET /stage/clips/{name}` | one `.vrma`; a name that escapes the folder is a 404 |
| `GET /stage/preview` | one avatar image, restricted to paths in `avatar_map` |
| `POST /test/vts` · `GET /vts/model` | VTube Studio reachability and model contents |

None of these are authenticated, so none of them return a secret.

---

## Adding a backend

1. Implement `AvatarInterface` in `src/modules/avatar/`.
2. Add a builder to `BUILDERS` in `factory.py`. Keep the import inside the
   builder so other backends do not pay for its dependencies.
3. If it needs a `publisher`, add its name to `NEEDS_PUBLISHER`. Without one the
   factory falls back to `png` rather than publishing into nothing.
4. Add it to `AVATARS` in `src/setup/wizard.py`.

`tests/test_avatar_backends.py` iterates `BUILDERS` and asserts each one builds
an `AvatarInterface`; `tests/test_setup.py` asserts the wizard never offers a
name the factory does not have.
