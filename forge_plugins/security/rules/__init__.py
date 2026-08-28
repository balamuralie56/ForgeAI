"""
Static AST rule definitions. Auto-imports modules to trigger registries.
"""

from .base_rule import SecurityRule
from .registry import register_rule, get_all_rules, get_enabled_rules

# Import rule modules to execute registration decorators
from . import eval_rule as eval_rule
from . import exec_rule as exec_rule
from . import shell_rule as shell_rule
from . import pickle_rule as pickle_rule
from . import weak_crypto_rule as weak_crypto_rule
from . import hardcoded_password_rule as hardcoded_password_rule
from . import sql_injection_rule as sql_injection_rule
from . import temp_file_rule as temp_file_rule

__all__ = [
    "SecurityRule",
    "register_rule",
    "get_all_rules",
    "get_enabled_rules",
]
