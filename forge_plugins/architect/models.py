"""
Architect design specification models for ForgeAI.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class TechnologyDecision:
    """Design technology decision."""

    category: str
    technology: str
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "category": self.category,
            "technology": self.technology,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TechnologyDecision":
        """Creates instance from dictionary."""
        return cls(
            category=data.get("category", ""),
            technology=data.get("technology", ""),
            rationale=data.get("rationale", ""),
        )


@dataclass
class APISpecification:
    """REST API route layout specification."""

    path: str
    method: str
    description: str
    request_payload_schema: str
    response_payload_schema: str

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "path": self.path,
            "method": self.method,
            "description": self.description,
            "request_payload_schema": self.request_payload_schema,
            "response_payload_schema": self.response_payload_schema,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "APISpecification":
        """Creates instance from dictionary."""
        return cls(
            path=data.get("path", ""),
            method=data.get("method", ""),
            description=data.get("description", ""),
            request_payload_schema=data.get("request_payload_schema", ""),
            response_payload_schema=data.get("response_payload_schema", ""),
        )


@dataclass
class ModuleSpecification:
    """Logical code module layout definition."""

    name: str
    purpose: str
    dependencies: List[str] = field(default_factory=list)
    apis: List[APISpecification] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "name": self.name,
            "purpose": self.purpose,
            "dependencies": self.dependencies,
            "apis": [api.to_dict() for api in self.apis],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModuleSpecification":
        """Creates instance from dictionary."""
        apis_data = data.get("apis") or []
        return cls(
            name=data.get("name", ""),
            purpose=data.get("purpose", ""),
            dependencies=data.get("dependencies") or [],
            apis=[APISpecification.from_dict(api) for api in apis_data],
        )


@dataclass
class DatabaseSchema:
    """Durable database table scheme representation."""

    table_name: str
    columns: Dict[str, str] = field(default_factory=dict)
    primary_key: str = ""
    foreign_keys: Dict[str, str] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "table_name": self.table_name,
            "columns": self.columns,
            "primary_key": self.primary_key,
            "foreign_keys": self.foreign_keys,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DatabaseSchema":
        """Creates instance from dictionary."""
        return cls(
            table_name=data.get("table_name", ""),
            columns=data.get("columns") or {},
            primary_key=data.get("primary_key", ""),
            foreign_keys=data.get("foreign_keys") or {},
            description=data.get("description", ""),
        )


@dataclass
class ArchitectureDecisionRecord:
    """Architectural decision log matching ADR framework."""

    adr_id: str
    title: str
    status: str
    context: str
    decision: str
    consequences: str
    date: str

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "adr_id": self.adr_id,
            "title": self.title,
            "status": self.status,
            "context": self.context,
            "decision": self.decision,
            "consequences": self.consequences,
            "date": self.date,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArchitectureDecisionRecord":
        """Creates instance from dictionary."""
        return cls(
            adr_id=data.get("adr_id", ""),
            title=data.get("title", ""),
            status=data.get("status", ""),
            context=data.get("context", ""),
            decision=data.get("decision", ""),
            consequences=data.get("consequences", ""),
            date=data.get("date", ""),
        )


@dataclass
class ArchitectureSpecification:
    """Comprehensive design specification mapping system files."""

    project_id: str = ""
    directory_structure: str = ""
    modules: List[ModuleSpecification] = field(default_factory=list)
    database_design: List[DatabaseSchema] = field(default_factory=list)
    decisions: List[TechnologyDecision] = field(default_factory=list)
    adrs: List[ArchitectureDecisionRecord] = field(default_factory=list)
    mermaid_diagrams: Dict[str, str] = field(default_factory=dict)
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "project_id": self.project_id,
            "directory_structure": self.directory_structure,
            "modules": [module.to_dict() for module in self.modules],
            "database_design": [db.to_dict() for db in self.database_design],
            "decisions": [dec.to_dict() for dec in self.decisions],
            "adrs": [adr.to_dict() for adr in self.adrs],
            "mermaid_diagrams": self.mermaid_diagrams,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArchitectureSpecification":
        """Creates instance from dictionary."""
        modules_data = data.get("modules") or []
        db_data = data.get("database_design") or []
        dec_data = data.get("decisions") or []
        adrs_data = data.get("adrs") or []

        return cls(
            project_id=data.get("project_id", ""),
            directory_structure=data.get("directory_structure", ""),
            modules=[ModuleSpecification.from_dict(m) for m in modules_data],
            database_design=[DatabaseSchema.from_dict(d) for d in db_data],
            decisions=[TechnologyDecision.from_dict(dec) for dec in dec_data],
            adrs=[ArchitectureDecisionRecord.from_dict(a) for a in adrs_data],
            mermaid_diagrams=data.get("mermaid_diagrams") or {},
            rationale=data.get("rationale", ""),
        )
