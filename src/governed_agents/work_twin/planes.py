"""Principal planes and up-only data flow, enforced as a query filter in code.

Three planes, ordered by principal:
  PERSONAL     (0) -- principal: the worker. The employer cannot read it.
  PROFESSIONAL (1) -- joint principal: worker + employer. The worker can correct it.
  WORKING      (2) -- principal: the employer. Acts under contract, with a worker veto.

Data flows UP, never down. This is not an instruction to the model; it is a
filter in ``UpOnlyStore.query``: a query issued from a plane can only return
records that live on planes the requestor plane is allowed to read, and the
allowed set never includes a lower plane. Records move up only through
``promote()``, which requires worker authorization when leaving PERSONAL.
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional


class Plane(IntEnum):
    PERSONAL = 0
    PROFESSIONAL = 1
    WORKING = 2


# The up-only lattice. A query from plane P may read records on these planes.
# Note WORKING can read PROFESSIONAL (joint) but never PERSONAL.
_READABLE = {
    Plane.PERSONAL: frozenset({Plane.PERSONAL}),
    Plane.PROFESSIONAL: frozenset({Plane.PROFESSIONAL}),
    Plane.WORKING: frozenset({Plane.WORKING, Plane.PROFESSIONAL}),
}


@dataclass
class Record:
    record_id: str
    plane: Plane
    kind: str
    payload: Dict[str, Any]
    author: str  # "worker" or "employer"
    promoted_from: Optional[Plane] = None
    history: List[Dict[str, Any]] = field(default_factory=list)


class UpOnlyStore:
    """A record store where the direction of data flow is enforced by code."""

    def __init__(self) -> None:
        self._records: Dict[str, Record] = {}
        self._audit: List[Dict[str, Any]] = []
        self._seq = 0

    def _log(self, event: str, detail: Dict[str, Any]) -> None:
        self._seq += 1
        self._audit.append({"seq": self._seq, "event": event, **detail})

    def write(self, record: Record, requestor_plane: Plane) -> None:
        """A plane may only write records that belong to itself."""
        if record.plane != requestor_plane:
            raise PermissionError(
                "write refused: plane %s cannot write a %s-plane record"
                % (requestor_plane.name, record.plane.name)
            )
        if record.record_id in self._records:
            raise ValueError("duplicate record_id: %s" % record.record_id)
        self._records[record.record_id] = record
        self._log("write", {"record_id": record.record_id, "plane": record.plane.name})

    def query(self, requestor_plane: Plane, kind: Optional[str] = None) -> List[Record]:
        """The up-only filter. No query can pull records down across a principal boundary."""
        allowed = _READABLE[requestor_plane]
        out = [
            r for r in self._records.values()
            if r.plane in allowed and (kind is None or r.kind == kind)
        ]
        self._log("query", {
            "requestor": requestor_plane.name,
            "kind": kind,
            "returned": len(out),
            "planes_seen": sorted({r.plane.name for r in out}),
        })
        return out

    def promote(self, record_id: str, to_plane: Plane, authorized_by: str) -> Record:
        """Move a record UP the lattice. Downward moves are refused in code.

        Promotion out of PERSONAL requires the worker's authorization; the
        employer cannot pull personal records upward by querying.
        """
        rec = self._records.get(record_id)
        if rec is None:
            raise KeyError("unknown record: %s" % record_id)
        if to_plane <= rec.plane:
            raise ValueError(
                "promote() only moves records UP (from %s to %s refused)"
                % (rec.plane.name, to_plane.name)
            )
        if rec.plane == Plane.PERSONAL and authorized_by != "worker":
            raise PermissionError(
                "personal-plane records promote only on worker authorization"
            )
        new_id = "%s@%s" % (record_id, to_plane.name.lower())
        promoted = Record(
            record_id=new_id,
            plane=to_plane,
            kind=rec.kind,
            payload=dict(rec.payload),
            author=rec.author,
            promoted_from=rec.plane,
            history=rec.history + [{"promoted_to": to_plane.name, "by": authorized_by}],
        )
        self._records[new_id] = promoted
        self._log("promote", {
            "from": record_id, "to": new_id,
            "from_plane": rec.plane.name, "to_plane": to_plane.name,
            "authorized_by": authorized_by,
        })
        return promoted

    def audit(self) -> List[Dict[str, Any]]:
        return list(self._audit)
