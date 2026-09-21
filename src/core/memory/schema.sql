-- Bea's memory, in one transactional file.
--
-- Timestamps are REAL epoch seconds, which is what the rest of the code
-- compares against. No parsing, no timezone.

-- --- people -----------------------------------------------------------------

-- The rich card: only for people who earned one (donors, regulars, 1:1s, or
-- whoever Bea decided to remember).
CREATE TABLE IF NOT EXISTS people (
    person_id       TEXT PRIMARY KEY,
    primary_name    TEXT NOT NULL DEFAULT '',
    attitude        TEXT NOT NULL DEFAULT '',      -- how Bea feels about them
    promoted_reason TEXT NOT NULL DEFAULT '',
    -- their message count at the last profiling pass
    profiled_count  INTEGER NOT NULL DEFAULT 0,
    -- how she stands with them right now, and when that was last true. Decays
    -- toward neutral on read, so a grudge fades without anyone sweeping it.
    warmth          REAL NOT NULL DEFAULT 0,
    warmth_at       REAL NOT NULL DEFAULT 0,
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

-- The cheap tally kept for everyone: no generated content, just counts, so it
-- is affordable for thousands of chatters.
CREATE TABLE IF NOT EXISTS roster (
    identity       TEXT PRIMARY KEY REFERENCES identities(identity) ON DELETE CASCADE,
    message_count  INTEGER NOT NULL DEFAULT 0,
    donation_total REAL    NOT NULL DEFAULT 0,
    had_1on1       INTEGER NOT NULL DEFAULT 0,
    marked_by_bea  INTEGER NOT NULL DEFAULT 0,
    promoted       INTEGER NOT NULL DEFAULT 0
);

-- Distinct sessions an identity showed up in. A join table, not a counter:
-- "3+ distinct sessions" promotes a regular, and double-counting would mint
-- cards for one-time visitors.
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

-- The whole stream, keyed "platform:channel_id". Every perception the bus
-- carries is written here as it is drained, and so is everything she says
-- back: this is the only complete record of what happened, and the only thing
-- the consolidation reads.
CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_key TEXT NOT NULL,
    platform         TEXT NOT NULL DEFAULT '',
    channel_id       TEXT NOT NULL DEFAULT '',
    author_identity  TEXT,
    display_name     TEXT NOT NULL DEFAULT '',
    -- 'user' (somebody spoke) | 'bea' (she answered) | 'world' (something
    -- happened with nobody behind it: a game event, a body action, a system
    -- note). Kept apart so counting what a person said never counts the game.
    role             TEXT NOT NULL,
    -- the PerceptionKind it arrived as, and the surface it arrived on, so the
    -- consolidation can tell a telegram DM from a death in minecraft
    kind             TEXT NOT NULL DEFAULT 'chat',
    surface          TEXT NOT NULL DEFAULT '',
    -- which sitting this belongs to: the dreamer consolidates by session
    session_id       TEXT NOT NULL DEFAULT '',
    -- who she was answering, so "is this person replying to me" is a fact and
    -- not a guess. Empty when she spoke to the room rather than to a person.
    addressee_identity TEXT NOT NULL DEFAULT '',
    content          TEXT NOT NULL,
    ts               REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_key, id);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

-- Rolling summary per conversation. `last_count` is the message count at the
-- last regeneration: the trigger is a delta, not a modulo, because the counter
-- jumps by more than one and an exact multiple would be stepped over.
CREATE TABLE IF NOT EXISTS summaries (
    conversation_key TEXT PRIMARY KEY,
    summary          TEXT NOT NULL DEFAULT '',
    last_count       INTEGER NOT NULL DEFAULT 0,
    updated_at       REAL NOT NULL
);

-- The one sliding context window, mirrored as it is written.
--
-- Her working memory, not her history: what was said, who she was answering
-- and which rooms are still alive. Kept on disk so a restart is not amnesia,
-- and emptied by exactly one event — the consolidation she does in her sleep.
-- `seq` is the window's own ordering; the bridge line written by a handoff
-- is seq 0 and sorts first.
CREATE TABLE IF NOT EXISTS context_window (
    seq        INTEGER PRIMARY KEY,
    ts         REAL    NOT NULL,
    tokens     INTEGER NOT NULL DEFAULT 0,
    role       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    conv_key   TEXT    NOT NULL DEFAULT 'stage',
    author     TEXT    NOT NULL DEFAULT '',
    addressee  TEXT    NOT NULL DEFAULT ''
);

-- --- long-term memory -------------------------------------------------------

-- Embedded recollections. `source` separates what someone said from what Bea
-- said: she invents on purpose, so the two are recalled into separate blocks
-- and her own output never comes back as fact.
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

-- --- the stream plan --------------------------------------------------------

-- What the owner asked her to do on stream. Not a memory: it is an instruction
-- she is given, edited from the dashboard and read back into every prompt.
CREATE TABLE IF NOT EXISTS objectives (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT    NOT NULL,
    detail     TEXT    NOT NULL DEFAULT '',
    -- 'todo' | 'doing' | 'done' | 'dropped'
    status     TEXT    NOT NULL DEFAULT 'todo',
    -- how it went, in her words: what she reports back when she closes one
    outcome    TEXT    NOT NULL DEFAULT '',
    position   INTEGER NOT NULL DEFAULT 0,
    created_at REAL    NOT NULL,
    updated_at REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_objectives_order ON objectives(position, id);

-- Small named values that are not memories: the plan's headline ("today you
-- play minecraft with the mod team"), and the engine's own bookkeeping (which
-- night the last dream ran, which version the context window is on).
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Things she means to do later. Thin on purpose: a note and a time, so what to
-- actually say is decided with the conversation in front of her.
CREATE TABLE IF NOT EXISTS agenda (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    note             TEXT NOT NULL,
    person_id        TEXT NOT NULL DEFAULT '',
    conversation_key TEXT NOT NULL DEFAULT '',
    due_ts           REAL NOT NULL,
    created_at       REAL NOT NULL,
    done             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_agenda_due ON agenda(done, due_ts);
