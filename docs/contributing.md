# Contributing

← [Back to README](../README.md) | [Architecture](architecture.md)

---

## Getting a working checkout

```bash
git clone https://github.com/emqnuele/projectBEA.git
cd projectBEA
uv sync          # or: make install
```

`uv` installs Python for you, so there is no pyenv step and no virtualenv to
activate by hand. Node 18+ is only needed if you are touching the dashboard or
the Discord bot.

You do **not** need API keys to develop. The whole test suite runs without
network access — every model client, surface and transport is faked.

```bash
make test        # uv run pytest -q
make lint        # uv run ruff check src tests
```

Both have to pass before a pull request can merge. CI runs exactly these two
commands, so if they are green locally they are green there.

---

## Before you write code

Three invariants hold the system together. Breaking one of them is the kind of
change that needs discussing in an issue first, not a surprise in a diff.

**One bus.** Every sense pushes `Perception` objects onto `PerceptionBus` and
nothing gets a private channel into the consciousness. If your new surface needs
to reach her some other way, that is a design problem, not a shortcut.

**One mind.** There is a single always-on loop. Written channels run as scoped
conversation turns alongside it — one turn at a time per channel — but there is
never a second consciousness.

**One sink.** Everything she does leaves through the expression layer. That is
what makes it possible to answer "what did she actually do" by looking in one
place.

The attention rules in `src/core/attention/rules.py` are deliberately pure
functions with no IO, because that is what makes her behaviour testable. Keep
them that way.

---

## Adding things

| What | How |
|---|---|
| **A new LLM provider** | Extend `OpenAICompatibleClient`, add it to `_PROVIDERS` and `build_client()` in `src/modules/llm/factory.py` |
| **A new TTS engine** | Implement `TTSInterface`, add the branch and the CLI choice in `src/cli.py` |
| **A new skill** | Extend `Skill`, register it in `AIVtuberBrain._build_consciousness()` |
| **A new text platform** | Extend `PlatformSkill` — the roster, person cards, attention gate and scoped conversations then work with no extra code |

[Skills Overview](skills/overview.md) has the full plugin API.

---

## Tests

New behaviour needs a test. The suite is not there for coverage, it is there
because this is a system with a lot of moving parts and no way to eyeball
whether a change made her worse.

Two things worth copying from the existing tests:

**Name the test after the behaviour, not the function.**
`test_thirty_messages_a_minute_stay_under_four_model_calls` says what would be
lost if it broke. `test_attention_gate` does not.

**Fake at the boundary.** `FakeLLMClient`, `FakeExpression`, `FakeHistory` and
`RecordingEvents` already exist. Use them rather than reaching for a mocking
library — a fake that records what it was asked to do makes a much better
assertion than a call-count matcher.

---

## Pull requests

- One change per pull request. A refactor and a feature in the same diff means
  neither can be reviewed properly.
- Say what breaks if the change is wrong. That is the most useful sentence in a
  description.
- If it changes behaviour someone might be relying on, update the docs in the
  same pull request — `docs/` is the source the documentation site renders from,
  so a stale page there is a stale page in public.

Commit messages are lowercase and describe what was done, in a few words.
Look at `git log` for the shape.

---

## Reporting something broken

Include what you ran, what happened, and what you expected. If it involves a
model, say which provider and which model — most surprising behaviour turns out
to be a specific model doing something specific.

If it is a security issue — anything about the web API, which has no
authentication and binds to `127.0.0.1` for that reason — say so in the issue
title so it gets looked at first.
