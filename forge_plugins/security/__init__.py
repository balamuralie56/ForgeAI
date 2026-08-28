"""
ForgeAI Security Plugin.
Provides credentials scanning, static code rule auditing, license analysis, and SARIF exports.
"""

from .plugin import SecurityPlugin
from .service import SecurityService, ForgeAISecurity
from .models import SecurityFinding, SecurityReport, SecurityManifest, Severity
from .exceptions import SecurityError, SecurityValidationError, SecurityAnalysisError

__all__ = [
    "SecurityPlugin",
    "SecurityService",
    "ForgeAISecurity",
    "SecurityFinding",
    "SecurityReport",
    "SecurityManifest",
    "Severity",
    "SecurityError",
    "SecurityValidationError",
    "SecurityAnalysisError",
]
