"""The three twins, split by PRINCIPAL rather than by subject.

  PersonalTwin     -- principal: the worker. Holds commitments and routine
                      drafting that live in the worker's head. The employer
                      cannot read it; the store's query filter enforces this.
  ProfessionalTwin -- joint principal: worker + employer. Holds craft, voice
                      and evidence. Both principals may read; only the worker
                      may correct.
  WorkingTwin      -- principal: the employer. Acts under contract. The worker
                      holds a veto over actions that affect them; a vetoed
                      action cannot execute.

Each twin starts able to do nothing: capabilities are granted per skill by the
autonomy ladder (see ladder.py) only after measurement gates pass.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .planes import Plane, Record, UpOnlyStore


@dataclass
class ActionProposal:
    proposal_id: str
    skill: str
    action: Dict[str, Any]
    contract_ref: str
    vetoed: bool = False
    veto_reason: Optional[str] = None
    executed: bool = False


class PersonalTwin:
    """The worker's own twin. Principal: the worker."""

    def __init__(self, store: UpOnlyStore, worker_ref: str = "worker") -> None:
        self._store = store
        self._worker_ref = worker_ref
        self._seq = 0

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return "%s-%04d" % (prefix, self._seq)

    def record_commitment(self, text: str) -> str:
        rid = self._next_id("commitment")
        self._store.write(Record(rid, Plane.PERSONAL, "commitment",
                                {"text": text}, author="worker"),
                          Plane.PERSONAL)
        return rid

    def record_draft(self, text: str) -> str:
        rid = self._next_id("draft")
        self._store.write(Record(rid, Plane.PERSONAL, "draft",
                                {"text": text}, author="worker"),
                          Plane.PERSONAL)
        return rid

    def read(self, kind: Optional[str] = None) -> List[Record]:
        return self._store.query(Plane.PERSONAL, kind=kind)

    def promote_to_professional(self, record_id: str) -> Record:
        """The worker -- and only the worker -- may push a record upward."""
        return self._store.promote(record_id, Plane.PROFESSIONAL,
                                   authorized_by="worker")


class ProfessionalTwin:
    """The joint twin. Principals: worker + employer. The worker may correct."""

    def __init__(self, store: UpOnlyStore) -> None:
        self._store = store
        self._seq = 0

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return "%s-%04d" % (prefix, self._seq)

    def publish(self, kind: str, payload: Dict[str, Any], author: str) -> str:
        """Publish craft, voice or evidence to the joint plane."""
        if author not in ("worker", "employer"):
            raise ValueError("author must be 'worker' or 'employer'")
        rid = self._next_id("prof")
        self._store.write(Record(rid, Plane.PROFESSIONAL, kind, dict(payload),
                                 author=author), Plane.PROFESSIONAL)
        return rid

    def correct(self, record_id: str, correction: Dict[str, Any]) -> Record:
        """Only the worker may correct the joint twin; history is kept."""
        rec = self._store._records.get(record_id)
        if rec is None or rec.plane != Plane.PROFESSIONAL:
            raise KeyError("no professional-plane record: %s" % record_id)
        rec.history.append({"correction": dict(correction), "by": "worker"})
        rec.payload.update(correction)
        return rec

    def read(self, kind: Optional[str] = None) -> List[Record]:
        return self._store.query(Plane.PROFESSIONAL, kind=kind)


class WorkingTwin:
    """The employer's twin. Principal: the employer. Acts under contract.

    The worker holds a veto: ``execute`` refuses any vetoed proposal. The twin
    starts with no capabilities; each skill's allowed actions are granted by
    the autonomy ladder, not assumed here.
    """

    def __init__(self, store: UpOnlyStore) -> None:
        self._store = store
        self._proposals: Dict[str, ActionProposal] = {}
        self._seq = 0
        self._granted_skills: Dict[str, int] = {}  # skill -> ladder level

    def grant(self, skill: str, level: int) -> None:
        self._granted_skills[skill] = level

    def propose(self, skill: str, action: Dict[str, Any], contract_ref: str) -> ActionProposal:
        if self._granted_skills.get(skill, 0) < 1:
            raise PermissionError(
                "skill '%s' has no granted capability (level 0): propose refused" % skill
            )
        self._seq += 1
        pid = "prop-%04d" % self._seq
        prop = ActionProposal(pid, skill, dict(action), contract_ref)
        self._proposals[pid] = prop
        return prop

    def worker_veto(self, proposal_id: str, reason: str) -> ActionProposal:
        prop = self._proposals[proposal_id]
        prop.vetoed = True
        prop.veto_reason = reason
        return prop

    def execute(self, proposal_id: str) -> ActionProposal:
        prop = self._proposals[proposal_id]
        if prop.vetoed:
            raise PermissionError(
                "execute refused: worker veto stands (%s)" % prop.veto_reason
            )
        if prop.executed:
            raise ValueError("proposal already executed")
        prop.executed = True
        return prop

    def read(self, kind: Optional[str] = None) -> List[Record]:
        # The employer reads the working plane: working + professional records.
        # Personal records are excluded by the store's query filter.
        return self._store.query(Plane.WORKING, kind=kind)
