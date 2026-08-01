"""The run's evidence store.

One store per run, shared by its tasks so that the same question is not asked twice. Sharing facts
is not sharing obligations: a completeness gate must charge only the task that owns the subject
(capability + ecosystem), never every consumer of the store. It is also the run's audit record —
and it is never read back as an input by a later run: a journal that becomes a source of truth
keeps one run's mistake alive forever.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path

from agent.evidence.record import Evidence, Reliability, Subject


class EvidenceStore:
    def __init__(self) -> None:
        self._records: list[Evidence] = []
        self._by_question: dict[tuple[str, str], Evidence] = {}
        self._lock = threading.Lock()
        """Guards concurrent prep/analysis writes when ecosystems run in parallel."""

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    def __iter__(self) -> Iterator[Evidence]:
        with self._lock:
            return iter(list(self._records))

    def add(self, record: Evidence) -> Evidence:
        """Record a fact. A verified answer replaces an earlier unverified one, never the reverse.

        Within a run the same question about the same subject must have one answer: two conflicting
        answers in one report are worse than none, because a reader cannot tell which was used.
        """
        with self._lock:
            key = (record.question, record.subject.key())
            existing = self._by_question.get(key)
            if existing is not None and existing.is_verified:
                return existing
            if existing is not None:
                self._records.remove(existing)
            self._records.append(record)
            self._by_question[key] = record
            return record

    def find(self, question: str, subject: Subject) -> Evidence | None:
        with self._lock:
            return self._by_question.get((question, subject.key()))

    def keys(self) -> frozenset[str]:
        """Every record a finding may cite. Anything else was not established by this run."""
        with self._lock:
            return frozenset(record.key for record in self._records if record.is_verified)

    def reliabilities(self) -> dict[str, Reliability]:
        with self._lock:
            return {record.key: record.reliability for record in self._records}

    def unverified(self) -> tuple[Evidence, ...]:
        with self._lock:
            return tuple(record for record in self._records if not record.is_verified)

    def failures(self) -> tuple[Evidence, ...]:
        """Unverified facts whose reason is a failure rather than a documented gap."""
        with self._lock:
            return tuple(
                record
                for record in self._records
                if not record.is_verified and record.reason is not None and record.reason.is_failure
            )

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            lines = [json.dumps(record.as_json(), ensure_ascii=False) for record in self._records]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return path
