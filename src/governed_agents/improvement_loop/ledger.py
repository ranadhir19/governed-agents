"""Append-only hash-chained audit ledger.

Every significant loop event (proposal, critique, revision, checkpoint,
fault, healing action, gate decision, termination) is appended. Each entry
commits to the previous entry's hash, so tampering or rewind is detectable.
"""

import hashlib
import json


class AuditLedger:
    """Minimal hash-chained ledger. Append-only: no update or delete API."""

    GENESIS = "GENESIS"

    def __init__(self, name="ledger"):
        self.name = name
        self._entries = []
        self._head = self.GENESIS

    def append(self, event_type, payload=None):
        payload = payload or {}
        seq = len(self._entries)
        body = json.dumps(
            {"seq": seq, "prev": self._head, "type": event_type, "payload": payload},
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        self._entries.append(
            {
                "seq": seq,
                "prev": self._head,
                "hash": digest,
                "type": event_type,
                "payload": payload,
            }
        )
        self._head = digest
        return digest

    def head_hash(self):
        return self._head

    def count(self):
        return len(self._entries)

    def entries(self):
        return list(self._entries)

    def verify(self):
        """Recompute the whole chain. True iff intact and correctly ordered."""
        prev = self.GENESIS
        for e in self._entries:
            body = json.dumps(
                {
                    "seq": e["seq"],
                    "prev": e["prev"],
                    "type": e["type"],
                    "payload": e["payload"],
                },
                sort_keys=True,
                default=str,
            )
            if hashlib.sha256(body.encode("utf-8")).hexdigest() != e["hash"]:
                return False
            if e["prev"] != prev:
                return False
            prev = e["hash"]
        return True
