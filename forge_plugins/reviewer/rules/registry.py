"""
Registry coordinating discovery and selection of configured review rules.
"""

from typing import Dict, List
from .base_rule import ReviewRule

# Global registry maps rules by rule_id
_REGISTRY: Dict[str, ReviewRule] = {}


def register_rule(rule: ReviewRule) -> None:
    """Registers a rule instance into the global catalog."""
    _REGISTRY[rule.rule_id] = rule


def get_all_rules() -> List[ReviewRule]:
    """Retrieves all registered review rules."""
    return list(_REGISTRY.values())


def get_enabled_rules(enabled_map: Dict[str, bool]) -> List[ReviewRule]:
    """
    Retrieves rule instances filtered by user enable settings.
    Defaults to returning the rule if not explicitly disabled.
    """
    return [rule for rule in _REGISTRY.values() if enabled_map.get(rule.rule_id, True)]
