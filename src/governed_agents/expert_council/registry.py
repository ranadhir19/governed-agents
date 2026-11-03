"""Append-only expert registry with a hash-chained audit log."""

import hashlib
import json


def _digest(entry, prev):
    blob = json.dumps({"prev": prev, "entry": entry}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


class Registry:
    def __init__(self):
        self.entries = []

    def append(self, expert_id, action, payload):
        prev = self.entries[-1]["hash"] if self.entries else "genesis"
        entry = {"seq": len(self.entries), "expert_id": expert_id,
                 "action": action, "payload": payload}
        entry["hash"] = _digest(entry, prev)
        entry["prev"] = prev
        self.entries.append(entry)
        return entry

    def for_expert(self, expert_id):
        return [e for e in self.entries if e["expert_id"] == expert_id]

    def verify(self):
        prev = "genesis"
        for e in self.entries:
            body = {k: v for k, v in e.items() if k not in ("hash", "prev")}
            if _digest(body, prev) != e["hash"]:
                return False
            prev = e["hash"]
        return True
