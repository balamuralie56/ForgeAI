"""
Service definitions and implementation for the ForgeAI Architect Plugin.
"""

import logging
import json
from abc import ABC, abstractmethod

from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.model_router.service import ModelRouterService
from forge_core.event_bus.service import EventBusService
from forge_core.event_bus.models import Event
from forge_core.memory.service import MemoryService

from forge_plugins.planner.models import ProjectPlan
from forge_plugins.planner.service import parse_json_response
from .models import ArchitectureSpecification
from .exceptions import ArchitectureInferenceError
from .components import (
    TechnologySelector,
    FolderStructureDesigner,
    ModuleDesigner,
    APIDesigner,
    DatabaseDesigner,
    SecurityDesigner,
    ADRGenerator,
    ArchitectureReportGenerator,
)

logger = logging.getLogger("ForgeAI.Plugins.Architect")


class ArchitectService(ABC):
    """
    Interface for the Architect service.
    """

    @abstractmethod
    def design_architecture(self, plan: ProjectPlan) -> ArchitectureSpecification:
        """
        Generates the software design and architecture spec based on the project plan.

        Args:
            plan (ProjectPlan): The decomposed project plan.

        Returns:
            ArchitectureSpecification: Software architecture container.
        """
        pass


class ForgeAIArchitect(ArchitectService):
    """
    Concrete Architect Service implementation.
    Delegates architectural sub-tasks to highly focused internal components.
    """

    def __init__(self, registry: ServiceRegistry) -> None:
        """
        Initializes the architect service and constructs sub-components.

        Args:
            registry (ServiceRegistry): System service container.
        """
        self._registry = registry

        # Construct modular architectural sub-components
        self.technology_selector = TechnologySelector(self._model_router)
        self.folder_designer = FolderStructureDesigner(self._model_router)
        self.module_designer = ModuleDesigner(self._model_router)
        self.api_designer = APIDesigner(self._model_router)
        self.database_designer = DatabaseDesigner(self._model_router)
        self.security_designer = SecurityDesigner(self._model_router)
        self.adr_generator = ADRGenerator(self._model_router)
        self.report_generator = ArchitectureReportGenerator()

    @property
    def _model_router(self) -> ModelRouterService:
        return self._registry.resolve(ModelRouterService)  # type: ignore[type-abstract]

    @property
    def _event_bus(self) -> EventBusService:
        return self._registry.resolve(EventBusService)  # type: ignore[type-abstract]

    @property
    def _memory(self) -> MemoryService:
        return self._registry.resolve(MemoryService)  # type: ignore[type-abstract]

    def design_architecture(self, plan: ProjectPlan) -> ArchitectureSpecification:
        logger.info(
            f"Designing software architecture spec for project: '{plan.goal.goal}'"
        )

        # 1. Format plan as JSON for LLM input context
        plan_json = json.dumps(plan.to_dict(), indent=2)

        # 2. Setup system prompting specifications
        prompt = f"""You are the Lead Software Architect AI for ForgeAI.
Your task is to design the software architecture specification based on the provided project plan.

Project Plan:
{plan_json}

You must output a single valid JSON object containing the architecture design. Do not include any explanation outside the JSON.
The JSON must adhere to the following schema:
{{
    "project_id": "Unique identifier for the project",
    "directory_structure": "ASCII directory tree structure representation",
    "modules": [
        {{
            "name": "Module Name",
            "purpose": "Purpose of this module",
            "dependencies": ["Other module names"],
            "apis": [
                {{
                    "path": "/api/v1/endpoint",
                    "method": "POST",
                    "description": "Endpoint description",
                    "request_payload_schema": "JSON schema description",
                    "response_payload_schema": "JSON schema description"
                }}
            ]
        }}
    ],
    "database_design": [
        {{
            "table_name": "Table Name",
            "columns": {{
                "column_name": "Type and constraints (e.g. VARCHAR(255) NOT NULL)"
            }},
            "primary_key": "column_name",
            "foreign_keys": {{
                "foreign_key_column": "target_table.target_column"
            }},
            "description": "Description of the table"
        }}
    ],
    "decisions": [
        {{
            "category": "Backend",
            "technology": "Python / FastAPI",
            "rationale": "Reason for selection"
        }}
    ],
    "adrs": [
        {{
            "adr_id": "ADR-001",
            "title": "Use SQLite for persistent storage",
            "status": "Accepted",
            "context": "Need simple, self-contained persistence",
            "decision": "Store project memory in local SQLite file",
            "consequences": "Zero configuration, but lacks high concurrency",
            "date": "2026-07-04"
        }}
    ],
    "mermaid_diagrams": {{
        "System Context": "Mermaid context graph text",
        "Database Schema": "Mermaid ER diagram text"
    }},
    "rationale": "Overall architecture rationale and design principles"
}}
"""

        # 3. Request architectural specs from Model Router
        try:
            response = self._model_router.generate(prompt, response_format="json")
            raw_text = response.text
        except Exception as e:
            raise ArchitectureInferenceError(
                f"Model Router generation failed during design: {e}"
            ) from e

        # 4. Resilient JSON Parse
        try:
            spec_data = parse_json_response(raw_text)
        except Exception as e:
            raise ArchitectureInferenceError(
                f"Failed to parse LLM response as JSON: {e}"
            ) from e

        # 5. Deserialize to strongly typed specification using sub-components
        try:
            project_id = spec_data.get("project_id", "")
            directory_structure = self.folder_designer.extract_structure(spec_data)
            modules = self.module_designer.extract_from_data(spec_data)
            database_design = self.database_designer.extract_from_data(spec_data)
            decisions = self.technology_selector.extract_from_data(spec_data)
            adrs = self.adr_generator.extract_from_data(spec_data)
            mermaid_diagrams = spec_data.get("mermaid_diagrams") or {}
            rationale = spec_data.get("rationale", "")

            spec = ArchitectureSpecification(
                project_id=project_id,
                directory_structure=directory_structure,
                modules=modules,
                database_design=database_design,
                decisions=decisions,
                adrs=adrs,
                mermaid_diagrams=mermaid_diagrams,
                rationale=rationale,
            )
        except Exception as e:
            raise ArchitectureInferenceError(
                f"Failed to map JSON schema to ArchitectureSpecification dataclasses: {e}"
            ) from e

        # 6. Save to memory
        spec_dict = spec.to_dict()
        self._memory.runtime.set_project_state("architecture_specification", spec_dict)
        self._memory.project.set_metadata("architecture_specification", spec_dict)

        # Record to architecture history
        self._memory.project.add_architecture_history(spec_dict)

        # 7. Publish Event
        event = Event(event_type="architect.spec_created", data=spec_dict)
        self._event_bus.publish(event)

        logger.info("Software architecture design completed successfully.")
        return spec
