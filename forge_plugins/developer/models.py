"""
Developer implementation models for ForgeAI.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class GeneratedFile:
    """Represents a generated file asset."""

    path: str
    content: str
    file_type: str

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "path": self.path,
            "content": self.content,
            "file_type": self.file_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GeneratedFile":
        """Creates instance from dictionary."""
        return cls(
            path=data.get("path", ""),
            content=data.get("content", ""),
            file_type=data.get("file_type", ""),
        )


@dataclass
class ImplementationReport:
    """Holds the final result of the implementation execution pipeline."""

    project_id: str
    files: List[GeneratedFile] = field(default_factory=list)
    summary: str = ""
    status: str = "SUCCESS"

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "project_id": self.project_id,
            "files": [f.to_dict() for f in self.files],
            "summary": self.summary,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImplementationReport":
        """Creates instance from dictionary."""
        files_data = data.get("files") or []
        return cls(
            project_id=data.get("project_id", ""),
            files=[GeneratedFile.from_dict(f) for f in files_data],
            summary=data.get("summary", ""),
            status=data.get("status", "SUCCESS"),
        )
