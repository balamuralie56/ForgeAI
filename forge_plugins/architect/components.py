"""
Modular sub-components for the ForgeAI Architect Plugin.
"""

import logging
from typing import Any, Dict, List
from forge_core.model_router.service import ModelRouterService

from .models import (
    TechnologyDecision,
    APISpecification,
    ModuleSpecification,
    DatabaseSchema,
    ArchitectureDecisionRecord,
    ArchitectureSpecification,
)

logger = logging.getLogger("ForgeAI.Plugins.Architect.Components")


class TechnologySelector:
    """Technology Selector component."""

    def __init__(self, model_router: ModelRouterService) -> None:
        self._model_router = model_router

    def extract_from_data(self, data: Dict[str, Any]) -> List[TechnologyDecision]:
        dec_data = data.get("decisions") or []
        return [TechnologyDecision.from_dict(d) for d in dec_data]

    def select_technologies(self, requirements: List[Any]) -> List[TechnologyDecision]:
        logger.info("TechnologySelector choosing project tech stack")
        return []


class FolderStructureDesigner:
    """Folder Structure Designer component."""

    def __init__(self, model_router: ModelRouterService) -> None:
        self._model_router = model_router

    def extract_structure(self, data: Dict[str, Any]) -> str:
        return data.get("directory_structure", "")

    def design_structure(self, goal: str) -> str:
        logger.info(f"FolderStructureDesigner mapping directory layout for: '{goal}'")
        return ""


class ModuleDesigner:
    """Module Designer component."""

    def __init__(self, model_router: ModelRouterService) -> None:
        self._model_router = model_router

    def extract_from_data(self, data: Dict[str, Any]) -> List[ModuleSpecification]:
        modules_data = data.get("modules") or []
        return [ModuleSpecification.from_dict(m) for m in modules_data]

    def design_modules(self, goal: str) -> List[ModuleSpecification]:
        logger.info(f"ModuleDesigner structuring logical modules for: '{goal}'")
        return []


class APIDesigner:
    """API Designer component."""

    def __init__(self, model_router: ModelRouterService) -> None:
        self._model_router = model_router

    def design_apis(self, modules: List[ModuleSpecification]) -> List[APISpecification]:
        logger.info("APIDesigner formulating endpoint specs")
        return []


class DatabaseDesigner:
    """Database Designer component."""

    def __init__(self, model_router: ModelRouterService) -> None:
        self._model_router = model_router

    def extract_from_data(self, data: Dict[str, Any]) -> List[DatabaseSchema]:
        db_data = data.get("database_design") or []
        return [DatabaseSchema.from_dict(d) for d in db_data]

    def design_database(self, entities: List[Any]) -> List[DatabaseSchema]:
        logger.info("DatabaseDesigner designing storage schema")
        return []


class SecurityDesigner:
    """Security Designer component."""

    def __init__(self, model_router: ModelRouterService) -> None:
        self._model_router = model_router

    def analyze_security(self, modules: List[ModuleSpecification]) -> List[str]:
        logger.info("SecurityDesigner evaluating application threat vectors")
        return []


class ADRGenerator:
    """ADR Generator component."""

    def __init__(self, model_router: ModelRouterService) -> None:
        self._model_router = model_router

    def extract_from_data(
        self, data: Dict[str, Any]
    ) -> List[ArchitectureDecisionRecord]:
        adrs_data = data.get("adrs") or []
        return [ArchitectureDecisionRecord.from_dict(a) for a in adrs_data]

    def generate_adrs(
        self, decisions: List[TechnologyDecision]
    ) -> List[ArchitectureDecisionRecord]:
        logger.info("ADRGenerator producing Architecture Decision Records")
        return []


class ArchitectureReportGenerator:
    """Architecture Report Generator component."""

    def generate_specification_report(self, spec: ArchitectureSpecification) -> str:
        logger.info(
            f"ArchitectureReportGenerator writing design overview for project: '{spec.project_id}'"
        )
        return f"# Architecture Specification - {spec.project_id}\n\n{spec.rationale}"
