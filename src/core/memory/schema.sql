-- Bea's memory, in one transactional file.
--
-- Replaces five stores that could not stay in sync: a Chroma collection for the
-- diary plus roster.json, people.json, recent.json and self.md — each rewritten
-- whole on every single write, with no atomicity across them (promoting someone
-- touched two files, and a crash between them left a half-promoted person).
--
-- Timestamps are REAL epoch seconds, matching what the rest of the code already
-- compares against (`time.time() - last_seen`). No parsing, no timezone.

-- --- people -----------------------------------------------------------------

-- The rich card: only for people who earned one (donors, regulars, 1:1s, or
-- whoever Bea decided to remember).
CREATE TABLE IF NOT EXISTS people (
    person_id       TEXT PRIMARY KEY,
    primary_name    TEXT NOT NULL DEFAULT '',
    attitude        TEXT NOT NULL DEFAULT '',      -- how Bea feels about them
    promoted_reason TEXT NOT NULL DEFAULT '',
    -- how many of their messages existed at the last profiling pass. The first
    -- card is worth building early (until it exists Bea has no idea who they
    -- are); refreshes can be far rarer, since people don't change weekly.
    profiled_count  INTEGER NOT NULL DEFAULT 0,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);

-- One row per account. `identity` is "platform:native_id" and is the source of
-- truth; display_name is cosmetic and changes. Several identities may point at
-- the same person — that is the cross-platform merge.
CREATE TABLE IF NOT EXISTS identities (
    identity     TEXT PRIMARY KEY,
    person_id    TEXT REFERENCES people(person_id) ON DELETE SET NULL,
    platform     TEXT NOT NULL,
    native_id    TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    first_seen   REAL NOT NULL,
    last_seen    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_identities_person ON identities(person_id);
CREATE INDEX IF NOT EXISTS idx_identities_name ON identities(display_name);

-- The cheap tally kept for EVERYONE, thousands of chatters included: it carries
-- no generated content, it just counts, so the system can decide who is worth a
-- card. An INSERT per message instead of rewriting the whole file.
CREATE TABLE IF NOT EXISTS roster (
    identity       TEXT PRIMARY KEY REFERENCES identities(identity) ON DELETE CASCADE,
    message_count  INTEGER NOT NULL DEFAULT 0,
    donation_total REAL    NOT NULL DEFAULT 0,
    had_1on1       INTEGER NOT NULL DEFAULT 0,
    marked_by_bea  INTEGER NOT NULL DEFAULT 0,
    promoted       INTEGER NOT NULL DEFAULT 0
);

-- Distinct sessions an identity showed up in. A join table rather than a
-- denormalised counter: "3+ distinct sessions" is what promotes a regular, and a
-- counter that can double-count would mint cards for one-time visitors.
CREATE TABLE IF NOT EXISTS roster_sessions (
    identity   TEXT NOT NULL REFERENCES identities(identity) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    PRIMARY KEY (identity, session_id)
);

-- What Bea knows about a person. UNIQUE keeps the dreamer from re-adding the
-- same fact every night.
CREATE TABLE IF NOT EXISTS facts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id  TEXT NOT NULL REFERENCES people(person_id) ON DELETE CASCADE,
    text       TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'dreamer',  -- 'dreamer' | 'bea' | 'seed'
    created_at REAL NOT NULL,
    UNIQUE (person_id, text)
);
CREATE INDEX IF NOT EXISTS idx_facts_person ON facts(person_id, id);

-- --- conversations ----------------------------------------------------------

-- Per-conversation history, keyed "platform:channel_id". This is what a scoped
-- conversation turn reads instead of the live loop's context.
CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_key TEXT NOT NULL,
    platform         TEXT NOT NULL DEFAULT '',
    channel_id       TEXT NOT NULL DEFAULT '',
    author_identity  TEXT,
    display_name     TEXT NOT NULL DEFAULT '',
    role             TEXT NOT NULL,               -- 'user' | 'bea'
    content          TEXT NOT NULL,
    ts               REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_key, id);

-- Rolling summary per conversation. `last_count` is the message count at the
-- last regeneration: the trigger is a DELTA, not a modulo on the total, because
-- the check only runs when Bea answers and the counter jumps — an exact multiple
-- would be stepped over and the summary would never refresh.
CREATE TABLE IF NOT EXISTS summaries (
    conversation_key TEXT PRIMARY KEY,
    summary          TEXT NOT NULL DEFAULT '',
    last_count       INTEGER NOT NULL DEFAULT 0,
    updated_at       REAL NOT NULL
);

-- --- long-term memory -------------------------------------------------------

-- Embedded recollections. `source` is the important column: 'person' is
-- something someone actually said, 'bea' is something SHE said. Bea invents on
-- purpose — if her own output came back as fact, the fiction would compound into
-- incoherence. They are recalled into two separate, labelled blocks.
CREATE TABLE IF NOT EXISTS memories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scope        TEXT NOT NULL,                   -- 'diary' | 'conversation' | 'person'
    scope_key    TEXT NOT NULL DEFAULT '',
    who_identity TEXT,
    who_name     TEXT NOT NULL DEFAULT '',
    text         TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT 'person' CHECK (source IN ('person', 'bea')),
    embedding    BLOB,
    tags         TEXT NOT NULL DEFAULT '',
    created_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope, scope_key, id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_dedup ON memories(scope, scope_key, text);

-- Which model produced the vectors in store. Vectors from different models are
-- not comparable, so a change means re-embedding everything.
CREATE TABLE IF NOT EXISTS memory_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- --- volatile / self --------------------------------------------------------

-- "Right now" facts that decay on their own. No sweeper job: expired rows are
-- simply not selected, and pruned opportunistically.
CREATE TABLE IF NOT EXISTS hot_facts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'dreamer',   -- 'morning_pass' | 'dreamer' | 'live'
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    UNIQUE (text, source)
);

-- What Bea has learned about HERSELF. Separate from her soul, which never moves.
CREATE TABLE IF NOT EXISTS self_facts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL
);

-- The few structured bits the morning pass needs (birthday, ...) without
-- parsing prose out of self.md.
CREATE TABLE IF NOT EXISTS self_profile (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- --- sessions ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    title      TEXT NOT NULL DEFAULT '',
    started_at REAL NOT NULL,
    ended_at   REAL,
    dreamed    INTEGER NOT NULL DEFAULT 0
);
