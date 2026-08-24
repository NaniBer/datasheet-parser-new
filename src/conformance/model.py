"""Result data model for the conformance harness.

A ``CheckResult`` is one rule evaluated against one part. A ``PartReport`` is the
full battery for a part — this is the machine-readable artifact rule ``V-05``
asks for. Honesty is the point: a rule with no implemented check is ``UNRUN``,
never silently ``PASS`` — an unverified part is not a passing part.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class CheckStatus(str, Enum):
    PASS = "pass"      # rule checked, satisfied
    FAIL = "fail"      # rule checked, violated
    SKIP = "skip"      # rule does not apply to this part (e.g. THT rule on SMT)
    UNRUN = "unrun"    # rule known but no automated check implemented yet


@dataclass
class CheckResult:
    """One rule evaluated against one part."""

    rule_id: str
    tier: str                       # "must" | "should"
    title: str
    status: CheckStatus
    message: str = ""
    measured: Optional[str] = None
    threshold: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class PartReport:
    """The full conformance battery for a single part."""

    part: str
    artifacts: Dict[str, str] = field(default_factory=dict)
    results: List[CheckResult] = field(default_factory=list)

    def _must(self) -> List[CheckResult]:
        return [r for r in self.results if r.tier == "must"]

    @property
    def must_total(self) -> int:
        return len(self._must())

    @property
    def must_pass(self) -> int:
        return sum(1 for r in self._must() if r.status is CheckStatus.PASS)

    @property
    def must_fail(self) -> int:
        return sum(1 for r in self._must() if r.status is CheckStatus.FAIL)

    @property
    def must_unrun(self) -> int:
        return sum(1 for r in self._must() if r.status is CheckStatus.UNRUN)

    @property
    def passes_all_must(self) -> bool:
        """A part passes only when every applicable MUST rule was checked and
        satisfied. An unchecked MUST rule blocks the pass (an unverified part is
        not a passing part — spec V-05)."""
        return all(
            r.status in (CheckStatus.PASS, CheckStatus.SKIP) for r in self._must()
        )

    def to_dict(self) -> dict:
        return {
            "part": self.part,
            "artifacts": self.artifacts,
            "summary": {
                "passes_all_must": self.passes_all_must,
                "must_total": self.must_total,
                "must_pass": self.must_pass,
                "must_fail": self.must_fail,
                "must_unrun": self.must_unrun,
            },
            "results": [r.to_dict() for r in self.results],
        }
