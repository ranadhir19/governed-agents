"""The registry: one JSON file, one answer per project.

Storage is deliberately plain: a JSON file plus validation, no
database. A corrupt store never crashes the reader (graceful
degradation). Features added to the vocabulary later appear on
existing records automatically (schema evolution).
"""

import json
import os

from .validation import RegistryValidationError, validate_project
from .vocabulary import FEATURES, STORE_VERSION


class Registry:
    def __init__(self, path):
        self.path = path
        self.store_corrupt = False
        self.corrupt_error = None
        self._records = {}
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            data = {"version": STORE_VERSION, "projects": []}
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            # Graceful degradation: a corrupt store never crashes the reader.
            self.store_corrupt = True
            self.corrupt_error = "%s: %s" % (type(exc).__name__, exc)
            data = {"version": STORE_VERSION, "projects": []}
        projects = data.get("projects", []) if isinstance(data, dict) else []
        for raw in projects:
            if not isinstance(raw, dict):
                continue
            try:
                evolved = self._evolve(raw)
                self._records[evolved["name"]] = evolved
            except RegistryValidationError:
                # Skip records that no longer validate instead of crashing.
                continue

    def _evolve(self, raw):
        """Schema evolution: fill defaults so old records gain new fields."""
        rec = dict(raw)
        features = rec.get("features")
        if isinstance(features, dict):
            merged = {name: False for name in FEATURES}
            merged.update({k: bool(v) for k, v in features.items() if k in FEATURES})
            rec["features"] = merged
        elif isinstance(features, (list, tuple, set)):
            rec["features"] = [f for f in features if f in FEATURES]
        # 'mfa_exception' defaults to None; 'application_url' to None.
        rec.setdefault("mfa_exception", None)
        rec.setdefault("application_url", None)
        return validate_project(rec)

    def _persist(self):
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        payload = {
            "version": STORE_VERSION,
            "projects": [self._records[name] for name in sorted(self._records)],
        }
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, self.path)
        self.store_corrupt = False
        self.corrupt_error = None

    def save(self, record):
        """Validate then persist. A bad save is refused and never written."""
        normalized = validate_project(record)
        self._records[normalized["name"]] = normalized
        self._persist()
        return normalized

    def get(self, name):
        return self._records.get(name)

    def list(self):
        return [self._records[name] for name in sorted(self._records)]

    def remove(self, name):
        if name in self._records:
            del self._records[name]
            self._persist()
            return True
        return False

    def __len__(self):
        return len(self._records)
