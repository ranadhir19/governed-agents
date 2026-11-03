"""Shared blackboard: the board's coordination surface.

Specialists post their ranked candidates; the chief architect, critic, and
policy checker all read from the same board. No hidden state.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class BoardNote:
    author: str
    kind: str
    payload: Any


class Blackboard:
    def __init__(self):
        self.notes: List[BoardNote] = []

    def post(self, author: str, kind: str, payload: Any) -> None:
        self.notes.append(BoardNote(author=author, kind=kind, payload=payload))

    def read(self, kind: str) -> List[BoardNote]:
        return [n for n in self.notes if n.kind == kind]

    def snapshot(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        for n in self.notes:
            out.setdefault(n.kind, []).append(n.author)
        return out
