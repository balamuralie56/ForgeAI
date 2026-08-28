"""
Computes per-principle SOLID compliance scores from a set of review findings.
"""

from typing import Dict, List, Optional
from forge_plugins.security.models import Severity
from forge_plugins.reviewer.models import ReviewFinding, SOLID_PRINCIPLES

_SEVERITY_PENALTY = {
    Severity.CRITICAL: 25.0,
    Severity.HIGH: 15.0,
    Severity.MEDIUM: 8.0,
    Severity.LOW: 3.0,
    Severity.INFO: 0.5,
}


class SolidScorer:
    """
    Derives a 0-100 compliance score per SOLID principle from the findings whose
    rule flags that principle. Liskov Substitution ("L") is always reported as
    None (not evaluated) - see forge_plugins/reviewer/models.py for why.
    """

    @classmethod
    def score(cls, findings: List[ReviewFinding]) -> Dict[str, Optional[float]]:
        """Computes the per-principle score map, including L as None."""
        working: Dict[str, float] = {p: 100.0 for p in SOLID_PRINCIPLES}

        for finding in findings:
            if finding.principle not in SOLID_PRINCIPLES:
                continue
            penalty = _SEVERITY_PENALTY.get(finding.severity, 3.0)
            working[finding.principle] = max(0.0, working[finding.principle] - penalty)

        result: Dict[str, Optional[float]] = {
            k: round(v, 2) for k, v in working.items()
        }
        result["L"] = None
        return result
