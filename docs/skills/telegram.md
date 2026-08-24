# Telegram Skill

← [Skills Overview](overview.md) | [Back to README](../../README.md)

---

## What it does

Bea reads and answers Telegram — private chats and groups — as one more place
where she has conversations. It runs **in-process**: Telegram is text only, so
unlike Discord there is no second runtime to babysit.

```
src/core/skills/telegram/
├── surface.py    TelegramSkill — lifecycle, senses, one tool
└── handlers.py   pure extraction: is_bot_called, message_text, display_name…
```

`TelegramSkill` extends [`PlatformSkill`](overview.md#two-shapes-of-skill). All
it owes is `platform = "telegram"`, an `Author` builder and `send_text` — the
roster, person cards, attention gate and scoped conversation turns work on top
of that with no Telegram-specific code, because they are keyed on `Author` and
`conversation_key`.

---

## The handlers decide nothing

`handlers.py` is deliberately thin. It extracts the text, works out whether Bea
was called, builds the identity and deposits a perception — then returns. The
attention gate decides whether she reacts; a scoped turn decides what she says.
A handler that reasons is a handler that duplicates the mind.

`is_bot_called()` is pure and tested against a table of cases rather than
against Telegram: `@username` mention, a reply to one of her messages, a trigger
word (fuzzy, whole-word), or a private chat where everything is for her.

---

## How a message flows

```
telegram update
    └─ _on_message (thin)
          ├─ allowed chat?          allowed_chats, empty = every chat
          ├─ Author(platform="telegram", native_id=<user id>)
          ├─ is_dm / mentions_self / reply_to_self flags
          └─ bus.put(Perception(CHAT, conversation_key="telegram:<chat_id>"))
                  └─ attention gate → scoped conversation turn
```

Polling runs with `concurrent_updates(True)`: several chats are read at once and
the per-conversation scheduler is what keeps each single chat serialized. Bea
answers one turn at a time per chat, several chats in parallel.

Replies go out through the humanizer — one line per message, with a typing pause
between them. Telegram reactions are not used (`supports_reactions = False`).

---

## Tools

| Tool | Where |
|---|---|
| `telegram_send_message(chat_id, text)` | the live loop — writing somewhere unprompted |
| `reply`, `send_message`, `say_nothing` | a scoped turn, with the ids already bound |

---

## Configuration

```json
"telegram": {
  "enabled": false,
  "token": "",
  "owner_id": "",
  "allowed_chats": []
}
```

| Key | Description |
|---|---|
| `token` | Bot token. Prefer the `TELEGRAM_TOKEN` env var — env always wins |
| `owner_id` | Your Telegram user id; messages from it count as the owner, which bypasses cooldown and quiet hours |
| `allowed_chats` | Chat ids Bea may read. **Empty means every chat she is added to** |

Trigger words come from `attention.trigger_words`, not from this block — they
are the same names everywhere.

---

## Setup

1. Create a bot with [@BotFather](https://t.me/botfather) and copy the token.
2. Put `TELEGRAM_TOKEN` in `.env`.
3. For groups, disable BotFather's privacy mode if you want her to read
   everything rather than only messages that mention her.
4. Toggle the skill on in the dashboard.
