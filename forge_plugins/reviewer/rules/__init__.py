"""
Static AST review rule definitions. Auto-imports modules to trigger registries.
"""

from .base_rule import ReviewRule
from .registry import register_rule, get_all_rules, get_enabled_rules

# Import rule modules to execute registration decorators
from . import long_function_rule as long_function_rule
from . import too_many_parameters_rule as too_many_parameters_rule
from . import god_class_rule as god_class_rule
from . import deep_nesting_rule as deep_nesting_rule
from . import magic_number_rule as magic_number_rule
from . import missing_docstring_rule as missing_docstring_rule
from . import mutable_default_arg_rule as mutable_default_arg_rule
from . import type_check_chain_rule as type_check_chain_rule
from . import fat_interface_rule as fat_interface_rule
from . import concrete_dependency_rule as concrete_dependency_rule

__all__ = [
    "ReviewRule",
    "register_rule",
    "get_all_rules",
    "get_enabled_rules",
]
