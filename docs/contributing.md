# Contributing

ProjectBEA is one always-on consciousness that perceives, remembers, decides and
acts. Most of what makes it work is not the code in any one file. It is three
rules about how the files talk to each other. This page is those rules, and what
it takes to get a change merged.

← [README](../README.md) · [Architecture](architecture.md) · [Skills API](skills/overview.md)

---

## Where to start

If you are looking for something to pick up:

- **[good first issue](https://github.com/emqnuele/projectBEA/labels/good%20first%20issue)** for something scoped, where the surrounding code is already tested.
- **[help wanted](https://github.com/emqnuele/projectBEA/labels/help%20wanted)** for real work, with no hand-holding attached.

Issues carry an `area:` label: `area: attention`, `area: memory`,
`area: minecraft`, `area: skills`, `area: web/ui`, `area: llm/tts`,
`area: install`, `area: docs`. Pick the area you actually want to read.

The most useful contributions, in order:

1. **A new surface.** Extend `PlatformSkill` and she is on it. The roster,
   person cards, attention gate and scoped conversations come for free.
2. **A new TTS engine or LLM provider.** Both are one interface and one branch.
3. **A failing test for something she gets wrong.** A reproduction is worth more
   than a fix built on a guess.

## Issue first, or straight to a pull request

Open a pull request directly for anything local: a bug fix, a provider, a skill,
a docs correction, a test.

Open an issue first if the change touches how the system is put together:
anything that breaks one of the three invariants below, changes the on-disk
schema, changes `config.json`, or adds a dependency. Those are worth agreeing on
before you spend an evening on them.

---

## A working checkout

```bash
git clone https://github.com/emqnuele/projectBEA.git
cd projectBEA
uv sync          # or: make install
```

`uv` installs Python for you, so there is no pyenv step and no virtualenv to
activate by hand. Node 18+ is only needed if you are touching the dashboard or
the Discord bot.

You do **not** need API keys to develop. The whole test suite runs without
network access, because every model client, surface and transport is faked.

```bash
make test        # uv run pytest -q
make lint        # uv run ruff check src tests
```

Both have to pass before a pull request can merge. CI runs exactly these two
commands, so green locally is green there.

---

## The three invariants

These hold the system together. Breaking one is the kind of change that needs an
issue first, not a surprise in a diff.

**One bus.** Every sense pushes `Perception` objects onto `PerceptionBus`, and
nothing gets a private channel into the consciousness. If a new surface needs to
reach her some other way, that is a design problem, not a shortcut.

**One mind.** There is a single always-on loop. Written channels run as scoped
conversation turns alongside it, one turn at a time per channel, but there is
never a second consciousness.

**One sink.** Everything she does leaves through the expression layer. That is
what makes it possible to answer "what did she actually do" by looking in one
place.

One more, smaller but load-bearing: the attention rules in
`src/core/attention/rules.py` are pure functions with no IO, because that is what
makes her behaviour testable. Keep them that way.

---

## Adding things

| What | How |
|---|---|
| **A new LLM provider** | Extend `OpenAICompatibleClient`, add it to `_PROVIDERS` and `build_client()` in `src/modules/llm/factory.py` |
| **A new TTS engine** | Implement `TTSInterface`, add the branch and the CLI choice in `src/cli.py` |
| **A new skill** | Extend `Skill`, register it in `AIVtuberBrain._build_consciousness()` |
| **A new text platform** | Extend `PlatformSkill`, and the roster, person cards, attention gate and scoped conversations then work with no extra code |
| **A change to `data/prompts/soul.md`** | Update `SHIPPED_SOUL_SHA256` in `src/core/persona.py` to match. The test fails with the value to paste |

[Skills Overview](skills/overview.md) has the full plugin API.

The soul hash is the one thing in this repository that has to be edited in two
places. It is what separates "still the character we ship" from "someone wrote
their own", and it cannot be derived at runtime: reading the live file compares
it to itself, a value in the database goes stale the next time an update changes
the file, and reading it out of git assumes a `.git` that a tarball install does
not have. So it travels with the code, and a test stops it drifting.

---

## Tests

New behaviour needs a test. The suite is not there for coverage, it is there
because this is a system with a lot of moving parts and no way to eyeball
whether a change made her worse.

Two things worth copying from the tests that already exist:

**Name the test after the behaviour, not the function.**
`test_thirty_messages_a_minute_stay_under_four_model_calls` says what would be
lost if it broke. `test_attention_gate` does not.

**Fake at the boundary.** `FakeLLMClient`, `FakeExpression`, `FakeHistory` and
`RecordingEvents` already exist. Use them rather than reaching for a mocking
library. A fake that records what it was asked to do makes a much better
assertion than a call-count matcher.

---

## Pull requests

- One change per pull request. A refactor and a feature in the same diff means
  neither can be reviewed properly.
- Say what breaks if the change is wrong. That is the most useful sentence in a
  description.
- If it changes behaviour someone might be relying on, update the docs in the
  same pull request. `docs/` is what the documentation site renders, so a stale
  page there is a stale page in public.

Commit messages are lowercase and say what was done, in a few words. Look at
`git log` for the shape.

---

## Reporting a bug

Include what you ran, what happened, and what you expected. If a model is
involved, say which provider and which model. Most surprising behaviour turns
out to be one specific model doing one specific thing.

**Do not open a public issue for a security problem.** See
[SECURITY.md](../SECURITY.md).
