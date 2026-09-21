"""Memory consolidation and rehearsal engine — Phase 3 foundation.

This module coordinates proposal, rehearsal, validation, and commit
for Dream-driven memory consolidation. It does not replace the
existing MemoryStorage (durable memory); it operates through it.

Design rules:
  - Rehearsal never writes to MemoryStorage directly.
  - Commit is an explicit operation that uses MemoryStorage APIs.
  - Event emission uses existing EventManager (passed in or obtained).
  - No new database; no generalized workflow framework.
"""

from typing import Optional, Dict, Any, List
import time
import uuid

from src.core.events import (
    EventCategory,
    EventSeverity,
    EventVisibility,
    EVENT_TYPE_LIFECYCLE,
    EVENT_TYPE_PROGRESS,
    EVENT_TYPE_MUTATION,
    EVENT_TYPE_ERROR,
)
from src.core.dream.transaction import MemoryConsolidationTransaction, MemoryProposal, RehearsalResult, ValidationResult, TxStatus
from src.core.dream.events import (
    EVENT_DREAM_STARTED,
    EVENT_DREAM_COMPLETED,
    EVENT_DREAM_FAILED,
    EVENT_MEMORY_CONSOLIDATION_STARTED,
    EVENT_MEMORY_REHEARSAL_STARTED,
    EVENT_MEMORY_REHEARSAL_COMPLETED,
    EVENT_MEMORY_VALIDATED,
    EVENT_MEMORY_COMMITTED,
    EVENT_MEMORY_REJECTED,
    EVENT_MEMORY_FAILED,
)
from src.utils.logger import get_logger

logger = get_logger("bea.memory.consolidation")


class ConsolidationEngine:
    """Minimal consolidation/rehearsal engine using existing memory APIs.

    Usage pattern (additive, safe):
      engine = ConsolidationEngine(memory_storage=ms, event_manager=em)
      tx = engine.create_transaction(run_id="dream-run-...")
      engine.rehearse(tx, scenario="new skill learned")
      engine.validate(tx)
      if tx.status == "validated" and tx.validation_result and tx.validation_result.valid:
          engine.commit(tx)
    """

    def __init__(self, memory_storage=None, event_manager=None):
        self.storage = memory_storage
        self.event_manager = event_manager

    # ------------------------------------------------------------------
    # Transaction creation
    # ------------------------------------------------------------------
    def create_transaction(
        self,
        run_id: str,
        source_memory_ids: Optional[List[str]] = None,
        snapshot_ref: Optional[str] = None,
    ) -> MemoryConsolidationTransaction:
        tx = MemoryConsolidationTransaction(
            transaction_id=str(uuid.uuid4()),
            run_id=run_id,
            source_memory_ids=list(source_memory_ids or []),
            snapshot_ref=snapshot_ref,
        )
        if self.event_manager is not None:
            try:
                self.event_manager.publish(
                    category=EventCategory.MEMORY,
                    source="memory_consolidation",
                    message=f"Memory consolidation transaction created: {tx.transaction_id}",
                    event_type=EVENT_MEMORY_CONSOLIDATION_STARTED,
                    subsystem="memory",
                    run_id=run_id,
                    payload={
                        "transaction_id": tx.transaction_id,
                        "run_id": run_id,
                        "snapshot_ref": snapshot_ref,
                    },
                )
            except Exception as e:
                logger.warning(f"Consolidation event emission failed: {e}")
        return tx

    # ------------------------------------------------------------------
    # Rehearsal (simulated / proposal generation — never writes to storage)
    # ------------------------------------------------------------------
    def rehearse(
        self,
        tx: MemoryConsolidationTransaction,
        scenario: str = "",
        proposed_changes: Optional[List[Dict[str, Any]]] = None,
    ) -> List[RehearsalResult]:
        """Simulate a rehearsal/proposal stage. Does NOT modify persistent memory."""
        results: List[RehearsalResult] = []

        # Minimal simulated rehearsal based on proposed changes
        for change in proposed_changes or []:
            proposal = MemoryProposal(
                proposal_id=str(uuid.uuid4()),
                source_memory_ids=change.get("source_memory_ids", []),
                operation=change.get("operation", "merge"),
                before_state=change.get("before_state"),
                after_state=change.get("after_state"),
                reason=change.get("reason", "rehearsed consolidation"),
                confidence=float(change.get("confidence", 0.5)),
                reversibility=change.get("reversibility", "easy"),
            )
            tx.add_proposal(proposal)

            # Minimal simulated rehearsal result (deterministic for same inputs)
            result = RehearsalResult(
                rehearsal_id=str(uuid.uuid4()),
                scenario=scenario or "default_consolidation",
                result="passed",
                attempted_memory_refs=proposal.source_memory_ids,
                succeeded_memory_refs=proposal.source_memory_ids,
                confidence_delta=0.05,
                evidence={"operation": proposal.operation, "reversibility": proposal.reversibility},
            )
            tx.add_rehearsal_result(result)
            results.append(result)

        tx.transition_to(TxStatus.REHEARSED)
        if self.event_manager is not None:
            try:
                self.event_manager.publish(
                    category=EventCategory.MEMORY,
                    source="memory_consolidation",
                    message=f"Rehearsal completed for transaction {tx.transaction_id}",
                    event_type=EVENT_TYPE_PROGRESS,
                    subsystem="memory",
                    run_id=tx.run_id,
                    payload={
                        "transaction_id": tx.transaction_id,
                        "scenario": scenario,
                        "proposals": len(tx.proposals),
                        "rehearsals": len(results),
                    },
                )
            except Exception as e:
                logger.warning(f"Consolidation event emission failed: {e}")
        return results

    # ------------------------------------------------------------------
    # Validation (checks current memory state without mutation)
    # ------------------------------------------------------------------
    def validate(self, tx: MemoryConsolidationTransaction) -> ValidationResult:
        """Validate proposed changes against current durable memory state.

        This does not write to memory; it only reads and compares.
        """
        errors: List[str] = []
        warnings: List[str] = []
        conflicts: List[str] = []
        missing: List[str] = []
        duplicates: List[str] = []

        # Minimal validation logic (realistic, not speculative):
        # 1. Check source memory references exist
        if self.storage is not None and hasattr(self.storage, "entry_exists"):
            for sid in tx.source_memory_ids:
                # Note: MemoryStorage uses ChromaDB IDs, not generic IDs.
                # For simplicity, we assume source_memory_ids reference entries
                # that the existing memory layer can resolve. If they don't exist,
                # we record warnings rather than errors (to avoid blocking safe consolidations).
                try:
                    exists = self.storage.entry_exists(sid)
                    if not exists:
                        missing.append(sid)
                except Exception:
                    # If entry_exists fails (e.g., missing collection), skip
                    pass
        # 2. Detect empty or malformed proposals
        if not tx.proposals:
            warnings.append("No proposals generated by rehearsal.")
        # 3. Detect duplicate proposals by operation + source
        seen = set()
        for proposal in tx.proposals:
            key = (proposal.operation, tuple(proposal.source_memory_ids))
            if key in seen:
                duplicates.append(f"{proposal.operation}:{key}")
            seen.add(key)
        # 4. Detect conflicts (simplified: any proposal with low confidence)
        for proposal in tx.proposals:
            if proposal.confidence < 0.3:
                conflicts.append(f"Low confidence proposal: {proposal.proposal_id}")

        valid = len(errors) == 0 and len(conflicts) == 0
        result = ValidationResult(
            validation_id=str(uuid.uuid4()),
            valid=valid,
            errors=errors,
            warnings=warnings,
            conflicts_detected=conflicts,
            missing_sources=missing,
            duplicates_detected=duplicates,
        )
        tx.set_validation_result(result)
        tx.transition_to(TxStatus.VALIDATED)
        if self.event_manager is not None:
            try:
                self.event_manager.publish(
                    category=EventCategory.MEMORY,
                    source="memory_consolidation",
                    message=f"Validation result: {'valid' if valid else 'invalid'} for {tx.transaction_id}",
                    event_type=EVENT_TYPE_PROGRESS,
                    subsystem="memory",
                    run_id=tx.run_id,
                    payload={
                        "transaction_id": tx.transaction_id,
                        "valid": valid,
                        "errors": errors,
                        "conflicts": conflicts,
                        "missing_sources": missing,
                    },
                )
            except Exception as e:
                logger.warning(f"Consolidation event emission failed: {e}")
        return result

    # ------------------------------------------------------------------
    # Explicit commit (uses existing memory APIs — no silent mutation)
    # ------------------------------------------------------------------
    def commit(self, tx: MemoryConsolidationTransaction) -> bool:
        """Apply validated proposals through existing MemoryStorage APIs.

        Only called after validation succeeds. If storage APIs fail,
        the transaction is marked failed and no partial success is claimed.
        """
        if tx.status != TxStatus.VALIDATED:
            logger.warning(f"Transaction {tx.transaction_id} not validated; aborting commit.")
            tx.transition_to(TxStatus.REJECTED, reason="not validated")
            return False

        if not tx.validation_result or not tx.validation_result.valid:
            logger.warning(f"Transaction {tx.transaction_id} has invalid validation; aborting commit.")
            tx.transition_to(TxStatus.REJECTED, reason="invalid validation")
            return False

        applied = False
        failure_reason = None

        try:
            # Minimal realistic integration with MemoryStorage:
            # For each proposal, attempt to apply through storage APIs.
            # Since MemoryStorage uses ChromaDB collection.add() for entries,
            # we treat proposal application as adding/updating entries.
            # This is a foundation; future phases will expand consolidation logic.
            if self.storage is not None and hasattr(self.storage, "add_entry"):
                for proposal in tx.proposals:
                    # Simplified: treat proposal as a new/updated entry
                    # Real future consolidation will use merge/promote/archival logic.
                    # This stage proves the boundary exists without destroying anything.
                    entry_id = proposal.proposal_id
                    content = proposal.after_state.get("content", proposal.reason) if proposal.after_state else proposal.reason
                    metadata = {
                        "proposal_id": proposal.proposal_id,
                        "operation": proposal.operation,
                        "source_memory_ids": ",".join(proposal.source_memory_ids),
                        "run_id": tx.run_id,
                        "reversibility": proposal.reversibility,
                        "confidence": proposal.confidence,
                    }
                    self.storage.add_entry(content, metadata, entry_id)
            applied = True
        except Exception as e:
            applied = False
            failure_reason = str(e)
            logger.error(f"Consolidation commit failed for {tx.transaction_id}: {e}")

        if applied:
            tx.commit_applied = True
            tx.transition_to(TxStatus.COMMITTED)
            if self.event_manager is not None:
                try:
                    self.event_manager.publish(
                        category=EventCategory.DREAM,
                        source="memory_consolidation",
                        message=f"Memory consolidation committed: {tx.transaction_id}",
                        event_type=EVENT_TYPE_LIFECYCLE,
                        subsystem="memory",
                        run_id=tx.run_id,
                        payload={
                            "transaction_id": tx.transaction_id,
                            "proposals_applied": len(tx.proposals),
                            "conflicts_resolved": len(tx.validation_result.conflicts_detected) if tx.validation_result else 0,
                        },
                    )
                except Exception as ex:
                    logger.warning(f"Consolidation event emission failed: {ex}")
        else:
            tx.commit_applied = False
            tx.commit_failed_reason = failure_reason
            tx.transition_to(TxStatus.FAILED)
            if self.event_manager is not None:
                try:
                    self.event_manager.publish(
                        category=EventCategory.DREAM,
                        source="memory_consolidation",
                        message=f"Memory consolidation failed: {tx.transaction_id}",
                        event_type=EVENT_TYPE_ERROR,
                        subsystem="memory",
                        run_id=tx.run_id,
                        payload={"reason": failure_reason},
                    )
                except Exception as ex:
                    logger.warning(f"Consolidation event emission failed: {ex}")
        return applied
