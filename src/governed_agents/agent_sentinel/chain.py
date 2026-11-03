"""Tamper-evident, append-only hash chain (WORM-style).

Contracts and findings are recorded here. There is no update or delete
API: the only mutation is append. ``verify()`` recomputes every link;
any tampering breaks the chain at the first modified entry.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


def _hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChainEntry:
    seq: int
    ts: float
    entry_type: str  # "contract" | "finding" | "gate" | "incident" | "eval" | "note"
    data: Dict[str, Any]
    prev_hash: str
    hash: str


class HashChain:
    def __init__(self) -> None:
        self._entries: List[ChainEntry] = []

    def append(self, entry_type: str, data: Dict[str, Any], ts: float) -> ChainEntry:
        seq = len(self._entries)
        prev = self._entries[-1].hash if self._entries else "GENESIS"
        body = json.dumps(
            {"seq": seq, "ts": ts, "type": entry_type, "data": data, "prev": prev},
            sort_keys=True,
        )
        entry = ChainEntry(seq=seq, ts=ts, entry_type=entry_type, data=data,
                           prev_hash=prev, hash=_hash(body))
        self._entries.append(entry)
        return entry

    def verify(self) -> Tuple[bool, int]:
        """Return (ok, first_bad_index). ok=True means the chain is intact."""
        for i, e in enumerate(self._entries):
            prev = self._entries[i - 1].hash if i else "GENESIS"
            if e.prev_hash != prev or e.seq != i:
                return False, i
            body = json.dumps(
                {"seq": e.seq, "ts": e.ts, "type": e.entry_type,
                 "data": e.data, "prev": e.prev_hash},
                sort_keys=True,
            )
            if _hash(body) != e.hash:
                return False, i
        return True, -1

    def entries(self, entry_type: str = None) -> List[ChainEntry]:
        if entry_type is None:
            return list(self._entries)
        return [e for e in self._entries if e.entry_type == entry_type]

    def __len__(self) -> int:
        return len(self._entries)
