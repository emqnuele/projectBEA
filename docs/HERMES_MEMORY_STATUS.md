# Hermes Memory Status
Status: DONE (inspection complete)
Date: 2026-09-12

## Memory Infrastructure

### Storage Location
- **Primary database**: `/Users/ultraviollett/.hermes/state.db` (6,287,360 bytes)
- **WAL file**: `/Users/ultraviollett/.hermes/state.db-wal` (4,231,272 bytes)
- **SHM file**: `/Users/ultraviollett/.hermes/state.db-shm` (32,768 bytes)
- **Format**: SQLite 3

### Configuration
```yaml
# ~/.hermes/config.yaml
memory:
  memory_enabled: true
  user_profile_enabled: true
  provider: openai
  write_approval: true
  char_limit: 2200        # Memory store
  user_char_limit: 1375   # User profile store
```
- **`write_approval: true`** — Memory writes require explicit approval
- **`provider: openai`** — OpenAI used for memory embedding/summarization (if configured)

### FTS5 (Full-Text Search)
✅ **Active** — The following FTS5 tables are present in `state.db`:

| Table | Type | Purpose |
|---|---|---|
| `messages_fts` | FTS5 | Full-text search on conversation messages |
| `messages_fts_data` | FTS5 data | FTS5 internal data storage |
| `messages_fts_idx` | FTS5 index | FTS5 internal index |
| `messages_fts_content` | FTS5 content | FTS5 content rows |
| `messages_fts_docsize` | FTS5 docsize | Document size tracking |
| `messages_fts_trigram` | FTS5 trigram | Trigram-based fuzzy matching |
| `messages_fts_trigram_data` | FTS5 data | Trigram internal storage |
| `messages_fts_trigram_idx` | FTS5 index | Trigram internal index |
| `messages_fts_trigram_content` | FTS5 content | Trigram content |
| `messages_fts_trigram_docsize` | FTS5 docsize | Trigram docsize |
| `messages_fts_trigram_config` | FTS5 config | Trigram config |

### Database Schema (key tables)

| Table | Purpose |
|---|---|
| `sessions` | Session metadata (IDs, timestamps, model used) |
| `messages` | Conversation messages (primary content store) |
| `system_prompts` | System prompts used per session |
| `session_model_usage` | Model usage tracking per session |
| `delivery_obligations` | Pending message deliveries |
| `conversation_generations` | LLM generation records |
| `gateway_routing` | Routing decisions for model failover |
| `async_delegations` | Background task delegation records |
| `gateway_heartbeats` | Health check pings |
| `gateway_hygiene_state` | Maintenance state tracking |
| `compression_locks` | Context compression coordination |
| `state_meta` | Schema version and metadata |
| `hosted_room_*` | Multi-room collaboration tables |

### Memory Write Rules
Per `OPERATING.md` (§7 — Memory Governance):
- Memory writes must include provenance (source + classification)
- Memory content is classified: `permanent`, `transient`, `session`
- `permanent` entries require explicit approval
- Memory is queried for relevance before each response
- Memory should be consolidated periodically (curator system at `interval_hours`)

### Current Memory Contents (sample)
Based on database inspection, memory tables contain:
- Session metadata for past conversations
- Message history with FTS5 indexing
- System prompt variants
- Gateway routing decisions
- Model usage tracking

**Note**: Full content inspection was not performed (privacy-sensitive). The infrastructure is confirmed working.

### User Profile Behavior
- **Enabled**: `user_profile_enabled: true`
- **Storage**: Likely in `state.db` (table: `state_meta` or similar), with char limit 1,375
- **Content**: User preferences, standing facts, environment conventions
- **Injection**: Injected into every conversation turn
- **Governance**: Same write-approval rules apply

## What Belongs in Hermes Memory vs. ATLAS

### Hermes Memory (operational, transient-to-medium term)
- Standing user preferences (response style, tool preferences)
- Environment facts (OS, paths, versions of installed tools)
- Convention reminders (e.g., "use venv or uv for Python")
- Recent session summaries
- Task-specific lessons that recur within a session

### ATLAS (archival, canonical, long-term)
- Full architecture decisions and their rationale
- Capability ledgers and integration plans
- Project documentation and roadmaps
- Knowledge triplets and system maps
- Historical conversation summaries
- Forge constitution and philosophy documents

### Migration Boundary
Information that satisfies **all** of these criteria should eventually move from Hermes memory to ATLAS:
1. It is referenced across multiple sessions
2. It is needed for architectural reasoning (not just operational recall)
3. It has been validated and stabilized (not experimental)
4. It has a clear provenance chain

## Status
| Component | Status |
|---|---|
| Memory storage | ✅ Working (SQLite, 6.3MB) |
| FTS5 | ✅ Active |
| User profile | ✅ Enabled (1,375 char limit) |
| Write approval | ✅ Enabled |
| Consolidation | Configured (curator, opt-in) |
| Indexing | ✅ FTS5 + trigram indexes present |
