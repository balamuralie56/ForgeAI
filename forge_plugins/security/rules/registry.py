"""
Registry coordinating discovery and selection of configured static analysis rules.
"""

from typing import Dict, List
from .base_rule import SecurityRule

# Global registry maps rules by rule_id
_REGISTRY: Dict[str, SecurityRule] = {}


def register_rule(rule: SecurityRule) -> None:
    """Registers a rule instance into the global catalog."""
    _REGISTRY[rule.rule_id] = rule


def get_all_rules() -> List[SecurityRule]:
    """Retrieves all registered security rules."""
    return list(_REGISTRY.values())


def get_enabled_rules(enabled_map: Dict[str, bool]) -> List[SecurityRule]:
    """
    Retrieves rule instances filtered by user enable settings.
    Defaults to returning the rule if not explicitly disabled.
    """
    return [rule for rule in _REGISTRY.values() if enabled_map.get(rule.rule_id, True)]
