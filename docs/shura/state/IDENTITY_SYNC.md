# Identity Synchronization Procedure

Purpose: keep SHURA's identity portable across runtime changes without leaking identity into implementation.

Canonical authority (live): `~/.hermes/SOUL.md` (loaded by Hermes at session start).
Repository mirror: `data/prompts/soul.md` (primary repo identity kernel).
Repo reference copies: `docs/shura/SOUL.md`, `docs/shura/OPERATING.md`, `.shura/agents/constitution.md`.

Rule: identity layer (soul.md / operating.md) is never edited in-place without a documented reason and a regression check against the identity test in `soul.md` §14 (specific attention, useful friction, continuity, refusal to manufacture certainty). Implementation files (`brain.py`, `expression.py`, provider adapters, avatar code) must reference identity by path/import, never embed identity text directly.

Sync protocol:
1. Edit live `~/.hermes/SOUL.md` first (runtime source of truth).
2. Mirror to `data/prompts/soul.md` with `diff` view saved to `docs/shura/state/IDENTITY_SYNC.md`.
3. Update reference copies (`docs/shura/SOUL.md`) only after mirror is verified.
4. Never edit `brain.py`, `express.py`, or avatar exports to change identity behavior; extend via prompts/config.
5. Before any model/provider change, verify identity file timestamps match; document drift in `docs/shura/state/current-state.md`.

Legacy mood preservation: `normal/shock/love/cry/angry/ew/bored` remain load-bearing for PNG/OBS until a Live2D/state abstraction replaces them (per AGENTS.md). Any identity edit must not remove or rename these IDs; it may extend interpretation (e.g., emotional continuity model) but must preserve the interface.

Verification: `git diff docs/shura/state/IDENTITY_SYNC.md` must show reason + identity test reference before any identity change is committed.
