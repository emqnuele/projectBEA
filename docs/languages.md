# Languages

← [Back to README](../README.md) | [Configuration](configuration.md) | [TTS](modules/tts.md) | [STT](modules/stt.md)

---

## Two questions, two answers

Language is decided in two places, and they answer different questions.

**What she says** is decided per conversation, in the prompt: she answers in the
language she was written to. A message in Italian is answered in Italian even
when the line above it was English. One turn can answer several conversations at
once, so this cannot be a single global setting — a batch carrying a Telegram DM
in Italian and a Twitch line in English is answered correctly in each.

**What she hears, and what she reaches for when nobody has written to her**, is
`config.language`. It pins the transcriber, and it names the language she uses
for the idle monologue, a spontaneous line, or narrating Minecraft to an empty
room. `auto` — the default — lets the transcriber detect, and names no fallback.

```
config.language ──┬──► whisper_code() ──► the transcriber's language pin
                  │
                  ├──► directive()   ──► the ## LANGUAGE block in the system prompt
                  │
                  ├──► write_in()    ──► what the diary, dreamer, profiler and
                  │                      handoff write their output in
                  │
                  └──► providers     ──► which voice engines can be used at all
```

---

## `src/core/language.py`

One resolver. Nothing else parses a language code.

| Function | Returns |
|---|---|
| `resolve(raw)` | a supported code, or `AUTO` |
| `named(raw)` | the `Language`, or `None` for `AUTO` |
| `endonym(raw)` | what the language calls itself (`日本語`) |
| `whisper_code(raw)` | a code to pin a transcriber to, or `None` to detect |
| `options()` | `(code, label)` pairs for a menu, `AUTO` first |
| `directive(raw)` | the `## LANGUAGE` block for the system prompt |
| `speaks_first(raw)` | the line for a turn with nobody to mirror, or `""` |
| `write_in(raw)` | one line telling a background pass which language to write in |

`resolve` accepts a bare code (`it`), a regional tag (`it-IT`, `ja_JP`), an
endonym (`Italiano`, `日本語`), and legacy spellings (`jp` → `ja`). Anything it
cannot place resolves to `AUTO` rather than raising, so a typo in config.json
costs detection rather than her voice.

`whisper_code` returns `None` rather than the string `"auto"`: every transcriber
reads a missing language as "detect it" and rejects the literal.

### Supported

`en` `it` `ja` `es` `fr` `de` `pt` `zh` `ko`

Adding one is a row in `LANGUAGES`, plus voices for it in
`src/modules/tts/providers.py` on any engine that can say it.

---

## Voice engines

An engine does not decide a language. `src/modules/tts/providers.py` holds one
`VoiceProvider` row per engine — its voices, the language each voice speaks, and
whatever else that engine needs to be told — and every caller asks it rather
than reading config fields directly.

| Function | Returns |
|---|---|
| `for_config(config)` | the engine this config selects |
| `voice_for(config)` | the `Voice` that will actually be used |
| `speaks(provider, code)` | whether it has any voice in that language |
| `for_language(code)` | the engines that can speak it |
| `voices_for(provider, code)` | its voices in that language |
| `plan_for_language(config, code)` | the config fields that would move it to that language |
| `warnings(config)` | what is wrong with this combination, in plain words |

`voice_for` returns the configured voice whenever one is set — a chosen voice is
never swapped for one the language implies. `plan_for_language` returns changes
rather than applying them, so the wizard writes them as part of an answer and
the settings API offers them as `suggested`.

| Engine | Languages |
|---|---|
| EdgeTTS | `en` `it` `ja` `es` `fr` `de` `pt` `zh` `ko` |
| Kokoro | `en` |
| Orpheus | `en` |

EdgeTTS has an open catalogue: any valid voice id works, and its language is
read from the locale in the id. The listed voices are a shortlist for the menus.

Kokoro and Orpheus have closed catalogues — only the listed ids exist. Kokoro's
voice pack is English-only; the multilingual v1.0 pack needs a `kokoro-onnx`
release that requires `numpy>=2`, which conflicts with this project's
`numpy<2.0.0` pin.

> An EdgeTTS voice given text outside its language returns no audio, not an
> accent. `warnings(config)` is surfaced by the setup wizard, by `POST /config`
> and by `make doctor` for exactly this reason.

### Adding an engine

1. Extend `TTSInterface` in `src/modules/tts/`.
2. Add a `VoiceProvider` row to `providers.py` listing its voices and their
   languages.
3. Add a builder to `BUILDERS` in `factory.py`. It is handed the `Voice` to use.

The setup menus, the dashboard, the warnings and the diagnostic are all
generated from the row. `tests/test_tts_providers.py` fails if a row has no
builder, a builder has no row, or a row names a config field that does not exist.

---

## Transcribers

All three resolve `config.language` through `whisper_code` before it reaches a
provider, so the same config.json behaves identically on each. The local one
additionally checks the code against the languages its build of whisper has,
falling back to detection with a warning.

See [STT modules](modules/stt.md).

---

## Prompts

Every prompt in `data/prompts/` is editable and survives an update.

The system prompt is composed as **soul → language directive → operating manual
→ active skill sections**. The directive belongs in this cached half: it says to
mirror, which is true for the whole session, and a volatile line at the top of a
request costs the provider's prompt cache on every turn.

`directive()` returns the same block whatever `config.language` says. The
language she *opens* in is `speaks_first()`, added to the per-turn briefing only
on turns where no perception in the batch has an author. Whether anyone has
written to her is something the loop knows, so it is stated rather than left for
the model to infer — the same reasoning as the `[WHERE YOU ARE]` block.

The shipped prompts are written in English and the directive carries the
language. To change her voice and register in another language, point
`soul_path` at your own file — the directive still applies.

### Placeholders

No prompt spells her name out. Available in every prompt file:

`{name}` `{pronouns}` `{subject}` `{object}` `{possessive}`

`{date}` and `{language}` are additionally substituted in `diary.md` and
`dreamer.md`.

`tests/test_prompt_language.py` fails if a shipped prompt hardcodes the default
name.

### Background passes

The diary, the dreamer, the person profiler and the context handoff read a
conversation and write facts into memory, which are then injected back into her
context by retrieval. Each is given `write_in(config.language)` so what it
stores is in the same language as the conversation it came from.

| Pass | Prompt |
|---|---|
| Diary | `data/prompts/diary.md` |
| Dreamer | `data/prompts/dreamer.md` |
| Person profiler | `PERSON_PROMPT` in `src/core/memory/profiler.py` |
| Context handoff | `HANDOFF_SYSTEM` in `src/core/mind/handoff.py` |

---

## Scripts written without spaces

Japanese and Chinese separate neither words nor sentences the way a European
language does. `src/utils/text_utils.py` holds what the rest of the engine needs
to know about that:

| Function | Used by |
|---|---|
| `sentences(text)` | speech chunking and written-message splitting, so both agree on where a sentence ends |
| `display_width(text)` | anything with a length budget — a kana occupies two columns |
| `wrap_to_width(text, width)` | the caption box, which breaks mid-run where there is no space to break on |
| `written_without_spaces(text)` | deciding whether "leave the long word whole" applies |
| `CJK` | the character ranges, for anything matching against them |

`SENTENCE_END` treats `。！？` as terminators that need no following space,
alongside `. ! ? …` which do.

The attention gate (`src/utils/text_match.py`) matches trigger words on a
boundary that a kana or a kanji satisfies, so `ベアちゃん` matches `ベア` while
`beautiful` still does not match `bea`.
