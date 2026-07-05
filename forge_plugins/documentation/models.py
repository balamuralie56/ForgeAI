"""
Data models for the ForgeAI Documentation Plugin.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class GeneratedDocFile:
    """
    Immutable representation of an LLM-generated documentation file.
    """

    path: str
    content: str
    category: str  # e.g., 'project', 'developer', 'api', 'architecture', 'user', 'release', 'summary'

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "path": self.path,
            "content": self.content,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GeneratedDocFile":
        """Creates instance from dictionary."""
        return cls(
            path=data.get("path", ""),
            content=data.get("content", ""),
            category=data.get("category", ""),
        )


@dataclass
class DocumentationReport:
    """
    Data container representing the compiled documentation package output.
    """

    project_id: str
    doc_files: List[GeneratedDocFile] = field(default_factory=list)
    status: str = "PENDING"  # SUCCESS, FAILED
    summary: str = ""  # Markdown summary/dashboard index content

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "project_id": self.project_id,
            "doc_files": [df.to_dict() for df in self.doc_files],
            "status": self.status,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentationReport":
        """Creates instance from dictionary."""
        return cls(
            project_id=data.get("project_id", ""),
            doc_files=[
                GeneratedDocFile.from_dict(item) for item in data.get("doc_files", [])
            ],
            status=data.get("status", "PENDING"),
            summary=data.get("summary", ""),
        )
