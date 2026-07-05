"""
ForgeAI Documentation Plugin package.
Exposes core services, exceptions, and models.
"""

from .service import DocumentationService, ForgeAIDocumentation
from .models import DocumentationReport, GeneratedDocFile
from .exceptions import (
    DocumentationError,
    DocValidationError,
    DocInferenceError,
    DocWriteError,
)
from .plugin import DocumentationPlugin

__all__ = [
    "DocumentationPlugin",
    "DocumentationService",
    "ForgeAIDocumentation",
    "DocumentationReport",
    "GeneratedDocFile",
    "DocumentationError",
    "DocValidationError",
    "DocInferenceError",
    "DocWriteError",
]
