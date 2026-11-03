"""Safe checkpoints ("memento" pattern).

State is classified before capture:

- Restore  : progress markers (iteration, best-so-far artifact, best score).
             Written back on restore.
- Anchor    : hash-chained audit ledger. Capture only the head hash + entry
             count to prove no rewind; the ledger itself is NEVER written
             back (it is append-only).
- Rebuild   : derived data (score history, critique cache). Never captured;
             record the regeneration recipe instead.

Health gate: a checkpoint taken while unhealthy is provisional and is never
a restore target. Rollback is allowed only for plausible fault categories
(resource, logic) — never for configuration (could reinstate a revoked
secret), dependency, or transient (a retry is cheaper than a rewind).
"""

import copy
from dataclasses import dataclass, field


class StateClass:
    RESTORE = "restore"
    ANCHOR = "anchor"
    REBUILD = "rebuild"


ROLLBACK_ALLOWED = {"resource", "logic"}
ROLLBACK_DENIED_REASON = {
    "configuration": "rollback denied: could reinstate a revoked secret or bad config",
    "dependency": "rollback denied: the fault is external; rewind changes nothing",
    "transient": "rollback denied: retry is cheaper than rewind",
}


class CheckpointError(Exception):
    pass


@dataclass
class Checkpoint:
    seq: int
    iteration: int
    healthy: bool
    provisional: bool
    restore_payload: dict      # StateClass.RESTORE content
    anchor: dict               # {"ledger_head": str, "ledger_count": int}
    rebuild_recipe: str        # how to regenerate StateClass.REBUILD content


class CheckpointManager:
    def __init__(self):
        self._checkpoints = []
        self._seq = 0

    def capture(self, iteration, best_plan, best_score, ledger, healthy=True):
        """Classify and capture. Unhealthy -> provisional (never a target)."""
        ckpt = Checkpoint(
            seq=self._seq,
            iteration=iteration,
            healthy=bool(healthy),
            provisional=not healthy,
            restore_payload={
                "class": StateClass.RESTORE,
                "iteration": iteration,
                "best_plan": copy.deepcopy(best_plan),
                "best_score": best_score,
            },
            anchor={
                "class": StateClass.ANCHOR,
                "ledger_head": ledger.head_hash(),
                "ledger_count": ledger.count(),
            },
            rebuild_recipe=(
                "Rebuild derived data (score history, critique cache) by "
                "replaying the append-only audit ledger from genesis; "
                "recompute per-critic scores from the restored best plan."
            ),
        )
        self._seq += 1
        self._checkpoints.append(ckpt)
        return ckpt

    def latest_restorable(self):
        for ckpt in reversed(self._checkpoints):
            if not ckpt.provisional:
                return ckpt
        return None

    def restore(self, ckpt, fault_category, ledger):
        """Write back RESTORE state only. Enforces health gate and policy."""
        if ckpt.provisional:
            raise CheckpointError(
                "restore refused: checkpoint %d is provisional (taken while unhealthy)"
                % ckpt.seq
            )
        if fault_category not in ROLLBACK_ALLOWED:
            raise CheckpointError(
                ROLLBACK_DENIED_REASON.get(
                    fault_category,
                    "rollback denied for fault category '%s'" % fault_category,
                )
            )
        # Anchor check: ledger must be an intact extension of the anchor.
        if not ledger.verify():
            raise CheckpointError("restore refused: audit ledger chain is broken")
        if ledger.count() < ckpt.anchor["ledger_count"]:
            raise CheckpointError("restore refused: ledger was rewound")
        return copy.deepcopy(ckpt.restore_payload)
