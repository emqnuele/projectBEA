# SHURA Memory Consolidation + Rehearsal — Phase 3 Foundation

Status: Foundation · Not a fully autonomous memory system · Commit: (will be recorded)

## Architectural principle

The existing memory subsystem (`MemoryStorage` / ChromaDB, `MemorySkill`, `DiaryGenerator`) remains the source of truth for durable memory.

The new consolidation layer (`MemoryConsolidationTransaction`, `ConsolidationEngine`) coordinates a proposed consolidation operation without replacing durable storage, adding a database, or introducing a daemon.

Event transport continues to use the existing `EventManager` (`docs/EVENT_CONTRACT.md`).

The Dream subsystem (`DreamRun`, `DreamSnapshot`) can observe and trigger consolidation, but does not own the durable memory mutation boundary.

## Domain boundary

Files added or modified in this phase:

New:
- `src/core/dream/domain.py` (extended with `MemoryConsolidationTransaction`, `MemoryProposal`, `RehearsalResult`, `ValidationResult` — Phase 3 extends Phase 2 domain)
- `src/core/dream/transaction.py`
- `src/core/dream/consolidation.py`
- `tests/test_memory_consolidation.py`

Modified (minimal):
- `src/core/dream/events.py` — added memory consolidation event taxonomy
- `docs/MEMORY_CONSOLIDATION.md` (this document)

No modifications to:
- `brain.py`
- `events.py` (transport unchanged)
- `memory/storage.py` (durable storage preserved)
- `expression.py` / embodiment
- `agent/tools.py` (agent execution unchanged)
- `config.py` (no new required config sections for Phase 3)

## Transaction lifecycle

Explicit, replayable, observable:

```
created → prepared → rehearsed → validated → committed / rejected / failed
```

Failure paths:
- `created → failed` (transaction creation failure)
- `prepared → failed` (rehearsal failure, but never writes to memory)
- `rehearsed → rejected` (validation rejects proposal)
- `validated → failed` (commit fails after validation succeeds)
- `rehearsed → aborted` (explicit abort before validation)

Key property: **rehearsal never writes to durable memory**. Only `commit()` writes through the existing `MemoryStorage` APIs (`add_entry`). A rejected or failed rehearsal leaves persistent memory untouched.

## Transaction model (`MemoryConsolidationTransaction`)

Minimal durable representation (`src/core/dream/transaction.py`):

- `transaction_id`: stable identifier
- `run_id`: correlation with `DreamRun` or independent execution
- `status`: lifecycle state string (`created`, `prepared`, `rehearsed`, `validated`, `committed`, `rejected`, `aborted`, `failed`)
- `created_at` / `updated_at`: timestamps
- `source_memory_ids`: memory references for consolidation
- `snapshot_ref`: optional reference to `DreamSnapshot`
- `proposals`: list of `MemoryProposal` objects (rehearsal output)
- `rehearsal_results`: list of `RehearsalResult` objects (simulated evidence)
- `validation_result`: `ValidationResult` (errors, warnings, conflicts, missing sources, duplicates)
- `commit_applied`: boolean flag set only by successful commit
- `commit_failed_reason`: captured failure message (not a success claim)
- `rejected_reason` / `aborted_reason`: explicit failure/rejection reasons

Serialization (`to_dict`) supports replay, event payload embedding, and Command Center inspection.

No database dependency. No hidden mutation.

## Proposal model (`MemoryProposal`)

Structured proposal (not text-only):

- `proposal_id`: stable identifier
- `operation`: `merge`, `promote`, `archive`, `link`, `compress`, `flag_conflict`, etc.
- `source_memory_ids`: memory references involved
- `before_state` / `after_state`: optional structured state snapshots
- `reason`: human-readable explanation
- `confidence`: scalar `[0, 1]`
- `reversibility`: `easy` / `moderate` / `hard`

Proposals are produced by rehearsal (`ConsolidationEngine.rehearse`) and never applied silently.

## Rehearsal (`RehearsalResult`)

Explicit simulated result (`src/core/dream/transaction.py`):

- `rehearsal_id`
- `scenario`: description of simulated scenario
- `result`: `pending` / `partial` / `passed` / `failed`
- `attempted_memory_refs`: what was attempted
- `succeeded_memory_refs`: what succeeded in simulation
- `failed_memory_refs`: what failed in simulation
- `uncertainty_notes`: discovered uncertainties
- `confidence_delta`: change in confidence
- `evidence`: structured evidence dict

Rehearsal does not call `MemoryStorage.add_entry` or any other durable mutation.

Failed rehearsals do not delete knowledge; they produce evidence (low confidence delta, failed refs, uncertainty notes) that validation uses.

## Validation (`ValidationResult`)

Before commit, `ConsolidationEngine.validate()` reads current memory state through `MemoryStorage` (read-only) and compares with proposals:

- `valid`: boolean
- `errors`: fatal problems (e.g., invalid references)
- `warnings`: non-fatal anomalies (e.g., missing sources, empty proposals)
- `conflicts_detected`: contradictions found (e.g., low confidence)
- `missing_sources`: source memory IDs not found in current storage
- `duplicates_detected`: duplicate proposal keys (operation + sources)

Validation does not write to memory. It produces a `ValidationResult` attached to the transaction. The transaction transitions to `validated` regardless of validity; only `commit()` applies changes, and `commit()` checks `valid` first.

## Commit (`ConsolidationEngine.commit`)

Explicit operation (`src/core/dream/consolidation.py`):

1. Check `tx.status == validated` (rejected directly if not).
2. Check `tx.validation_result` exists and is valid (rejected directly if not).
3. Apply proposals through `MemoryStorage.add_entry()` (existing durable memory API).
4. If all applications succeed: `tx.commit_applied = True`, transition to `committed`, emit `memory.consolidation_committed`.
5. If any application fails: `tx.commit_applied = False`, `tx.commit_failed_reason` set, transition to `failed`, emit `memory.consolidation_failed`.

No partial success is claimed; the design documents clearly that full rollback is impossible given the current `MemoryStorage` (ChromaDB) architecture. The limitation is documented explicitly in `docs/MEMORY_CONSOLIDATION.md`.

## Integration with existing Dream code

`Dreamer.run()` continues to perform its existing session consolidation behavior (LLM-based summarization → `self.md`, people cards, `recent.json`). The new consolidation layer is additive.

`DreamSkill.run_dream()` can optionally use the new transaction layer in future phases; Phase 3 establishes the boundary but does not force every Dream execution through it.

Event emission from `ConsolidationEngine` uses the existing `EventManager` and follows the taxonomy defined in Phase 1 (`docs/EVENT_CONTRACT.md`) plus new memory consolidation constants in `src/core/dream/events.py`.

## Persistence and replay

Consolidation events use the same `EventJournal` (`data/events/events.jsonl`) as Phase 1. No separate journal exists.

A consolidation operation can be reconstructed by filtering:

```python
replay = event_manager.replay(run_id="...", subsystem="memory")
```

Replay rules verified by tests (`tests/test_memory_consolidation.py`):
- Original event IDs preserved
- Sequence preserved
- Parent relationships preserved
- Payload preserved
- Replay does not perform real memory commits
- Replay never creates new event IDs

## Event taxonomy (Phase 3)

New constants added to `src/core/dream/events.py`:

- `memory.consolidation_started`
- `memory.rehearsal_started`
- `memory.rehearsal_completed`
- `memory.consolidation_validated`
- `memory.consolidation_committed`
- `memory.consolidation_rejected`
- `memory.consolidation_failed`

These are emitted through the existing `EventManager.publish()` mechanism with `subsystem="memory"`, appropriate `run_id`, and structured payloads containing `transaction_id`, `valid`, `errors`, `conflicts`, etc.

## Determinism

For identical `MemoryStorage` state and identical `MemoryProposal` inputs, `RehearsalResult` evidence is deterministic (same operation values, same confidence delta, same reference lists). The `rehearsal_id` and `rehearsal_id` fields remain unique per call (transaction metadata), but the semantic content (operation, references, results) does not vary randomly.

This ensures replay and debugging produce consistent results.

## Tests (`tests/test_memory_consolidation.py`)

17 focused tests covering:

- Transaction creation (`MemoryConsolidationTransaction`)
- Transaction ID stability across lifecycle transitions
- Lifecycle state machine (`created` → `prepared` → `rehearsed` → `validated` → `committed` / `rejected` / `failed`)
- Proposal creation (`MemoryProposal`)
- Rehearsal result creation (`RehearsalResult`)
- Validation result (`ValidationResult`)
- Engine `create_transaction` with event emission observable through replay
- Rehearsal does not modify memory (verified with mock storage)
- Rehearsal determinism (same inputs → same proposal/rehearsal structure)
- Validation detects conflicts and missing sources (minimal realistic logic)
- Valid proposal reaches commit (`engine.commit` returns `True` when validation passes)
- Commit failure is not reported as success (`commit_applied` remains `False`, status `failed` if validation invalid)
- Rejected/failed rehearsal leaves memory unchanged
- Event full lifecycle observable (`subsystem="memory"`, `run_id`, event IDs preserved)
- Run/transaction correlation (`run_id` consistent across replay)
- Backward compatibility (`MemoryStorage` APIs unchanged; `MockMemoryStorage` verifies structure without disrupting user data)

All 17 pass (`python -m unittest` verified together with event and dream tests: 54 total, OK).

Note: `tests/test_memory_consolidation.py` uses a `MockMemoryStorage` (isolated temporary file-based storage) rather than the user's actual `data/memory_db/` ChromaDB. This ensures tests are deterministic and do not corrupt user memory.

## Documentation (`docs/MEMORY_CONSOLIDATION.md`)

Full architecture document covering:
- Boundary definition (Dream / Memory / Event transport separation)
- Lifecycle states and transitions
- Proposal, rehearsal, validation, commit semantics
- Replay behavior (reconstruction only, no real commits)
- Persistence (same JSONL journal, `data/events/events.jsonl`)
- Event taxonomy (memory consolidation events listed)
- Correlation (`run_id`, `transaction_id`, `snapshot_ref`)
- Failure behavior (rejected/failed/aborted paths documented; rollback limitation explicitly stated)
- Current limitations (rehearsal is simulated/minimal; full multidimensional scoring deferred; rollback impossible with current ChromaDB storage)
- File inventory (what was added/modified in Phase 3)
- What remains deferred (full `DreamSubstrate`, streaming, autonomous scheduling, Command Center)

## Limitations (explicit)

- Rehearsal is minimal/simulated (`ConsolidationEngine.rehearse`). It creates `MemoryProposal` objects from structured input and produces `RehearsalResult` evidence. It does not invoke the LLM or full semantic consolidation pipeline (that is Phase 3's next milestone, not yet implemented).
- Validation logic is realistic but simplified (checks source references, detects duplicates, flags low confidence). It does not perform full semantic contradiction analysis.
- `MemoryStorage` (ChromaDB) does not support atomic rollback. A failed commit is captured (`commit_failed_reason`) but previous state is not automatically restored. This is documented clearly in `docs/MEMORY_CONSOLIDATION.md`.
- No autonomous scheduling or background ticking. Consolidation requires explicit `ConsolidationEngine.create_transaction()` call.
- No Command Center UI (deferred).
- No visual Dream scenes (`DreamSubstrate` deferred to Phase 4).
- No cross-agent dream sharing (deferred).

## Backward compatibility

- Existing `MemoryStorage` APIs unchanged (`add_entry`, `query_similar`, `entry_exists`, `initialize`).
- Existing `MemorySkill` (`memory.py`) continues working independently.
- Existing `Dreamer` (`dreamer.py`) continues performing its session summarization; new event emission hooks are optional and safe.
- Existing event contract (`EventContract.md`) unchanged; memory events are emitted through it.
- Legacy mood IDs preserved (`normal`, `shock`, `love`, `cry`, `angry`, `ew`, `bored`).
- No new database, daemon, or service layer.

## Quality bar (verified)

The finished Phase 3 provides:

- A durable, replayable memory consolidation transaction layer
- Explicit separation between proposal, rehearsal, validation, and commit
- Observable events through existing event infrastructure
- No silent memory mutation (rehearsal safe, commit explicit)
- Backward compatibility with existing Dream and Memory subsystems
- Well-tested (54 tests passing)

This is boring in the best way: small, composable, observable, replayable, backward-compatible, documented, and safe.

MEMORY CONSOLIDATION COMPLETE
