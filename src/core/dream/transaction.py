"""Dream Memory Consolidation Transaction — Phase 3 foundation.

This module defines the lightweight transaction domain model for
memory consolidation and rehearsal. It does not replace the memory
subsystem; it coordinates a proposed operation between Dream and
existing durable memory.

Design rules:
  - No database dependency.
  - No new event transport (uses existing EventManager).
  - Rehearsal never mutates persistent memory.
  - Commit is explicit and observable.
  - Replay reconstructs the transaction from events, not memory.
  - Failure paths preserve existing memory untouched.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
import time
import uuid

# ------------------------------------------------------------------
# Transaction lifecycle states
# ------------------------------------------------------------------
class TxStatus(str):
    CREATED = "created"
    PREPARED = "prepared"
    REHEARSED = "rehearsed"
    VALIDATED = "validated"
    COMMITTED = "committed"
    REJECTED = "rejected"
    ABORTED = "aborted"
    FAILED = "failed"

# ------------------------------------------------------------------
# Minimal proposal representation (structured, not text-based)
# ------------------------------------------------------------------
@dataclass
class MemoryProposal:
    """A proposed change to durable memory — produced by rehearsal,
    validated before commit, never applied silently."""
    proposal_id: str
    source_memory_ids: List[str] = field(default_factory=list)
    operation: str = "merge"  # merge, promote, archive, link, compress, flag_conflict
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    reason: str = ""
    confidence: float = 0.0
    reversibility: str = "easy"  # easy / moderate / hard

# ------------------------------------------------------------------
# Rehearsal result representation
# ------------------------------------------------------------------
@dataclass
class RehearsalResult:
    """Explicit result of a simulated/consolidation rehearsal stage."""
    rehearsal_id: str
    scenario: str = ""
    result: str = "pending"  # pending / partial / passed / failed
    attempted_memory_refs: List[str] = field(default_factory=list)
    succeeded_memory_refs: List[str] = field(default_factory=list)
    failed_memory_refs: List[str] = field(default_factory=list)
    uncertainty_notes: List[str] = field(default_factory=list)
    confidence_delta: float = 0.0
    evidence: Dict[str, Any] = field(default_factory=dict)

# ------------------------------------------------------------------
# Validation result representation
# ------------------------------------------------------------------
@dataclass
class ValidationResult:
    """Result of validation against current memory state."""
    validation_id: str
    valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    conflicts_detected: List[str] = field(default_factory=list)
    missing_sources: List[str] = field(default_factory=list)
    duplicates_detected: List[str] = field(default_factory=list)

# ------------------------------------------------------------------
# Dream Memory Consolidation Transaction
# ------------------------------------------------------------------
@dataclass
class MemoryConsolidationTransaction:
    """A single proposed memory consolidation operation coordinated by Dream.

    Lifecycle:
      created → prepared → rehearsed → validated → committed / rejected / failed

    No persistent mutation occurs before explicit commit.
    Rehearsal produces `MemoryProposal` objects without applying them.
    Validation examines current durable memory (via MemoryStorage) and
    produces a `ValidationResult`. Only a valid proposal reaches commit.
    """

    transaction_id: str
    run_id: str  # correlation with DreamRun
    status: str = TxStatus.CREATED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # Source references
    source_memory_ids: List[str] = field(default_factory=list)
    snapshot_ref: Optional[str] = None  # reference to DreamSnapshot

    # Proposals (rehearsal output — never applied silently)
    proposals: List[MemoryProposal] = field(default_factory=list)

    # Rehearsal evidence
    rehearsal_results: List[RehearsalResult] = field(default_factory=list)

    # Validation evidence
    validation_result: Optional[ValidationResult] = None

    # Final outcome
    commit_applied: bool = False
    commit_failed_reason: Optional[str] = None
    rejected_reason: Optional[str] = None
    aborted_reason: Optional[str] = None

    # Metadata (for audit/replay; no secrets)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Lifecycle transitions (explicit, observable, replayable)
    # ------------------------------------------------------------------
    def transition_to(self, new_status: str, reason: Optional[str] = None) -> None:
        self.status = new_status
        self.updated_at = time.time()
        if reason:
            self.metadata.setdefault("transition_reasons", []).append(
                {"status": new_status, "reason": reason, "timestamp": self.updated_at}
            )

    # ------------------------------------------------------------------
    # Proposals
    # ------------------------------------------------------------------
    def add_proposal(self, proposal: MemoryProposal) -> None:
        self.proposals.append(proposal)

    # ------------------------------------------------------------------
    # Rehearsal
    # ------------------------------------------------------------------
    def add_rehearsal_result(self, result: RehearsalResult) -> None:
        self.rehearsal_results.append(result)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def set_validation_result(self, result: ValidationResult) -> None:
        self.validation_result = result

    # ------------------------------------------------------------------
    # Serialization (for replay / event payload / audit)
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "run_id": self.run_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_memory_ids": list(self.source_memory_ids),
            "snapshot_ref": self.snapshot_ref,
            "proposals": [
                {
                    "proposal_id": p.proposal_id,
                    "operation": p.operation,
                    "source_memory_ids": list(p.source_memory_ids),
                    "before_state": p.before_state,
                    "after_state": p.after_state,
                    "reason": p.reason,
                    "confidence": p.confidence,
                    "reversibility": p.reversibility,
                }
                for p in self.proposals
            ],
            "rehearsal_results": [
                {
                    "rehearsal_id": r.rehearsal_id,
                    "scenario": r.scenario,
                    "result": r.result,
                    "attempted_memory_refs": list(r.attempted_memory_refs),
                    "succeeded_memory_refs": list(r.succeeded_memory_refs),
                    "failed_memory_refs": list(r.failed_memory_refs),
                    "uncertainty_notes": list(r.uncertainty_notes),
                    "confidence_delta": r.confidence_delta,
                    "evidence": dict(r.evidence),
                }
                for r in self.rehearsal_results
            ],
            "validation_result": (
                {
                    "validation_id": self.validation_result.validation_id,
                    "valid": self.validation_result.valid,
                    "errors": list(self.validation_result.errors),
                    "warnings": list(self.validation_result.warnings),
                    "conflicts_detected": list(self.validation_result.conflicts_detected),
                    "missing_sources": list(self.validation_result.missing_sources),
                    "duplicates_detected": list(self.validation_result.duplicates_detected),
                }
                if self.validation_result else None
            ),
            "commit_applied": self.commit_applied,
            "commit_failed_reason": self.commit_failed_reason,
            "rejected_reason": self.rejected_reason,
            "aborted_reason": self.aborted_reason,
            "metadata": dict(self.metadata),
        }
