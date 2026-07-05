"""
Data models for the ForgeAI Git Plugin.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GitCommit:
    """Represents a single atomic git commit produced by the pipeline."""

    sha: str
    message: str
    files: List[str] = field(default_factory=list)
    author: str = "ForgeAI"
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "sha": self.sha,
            "message": self.message,
            "files": self.files,
            "author": self.author,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GitCommit":
        """Creates instance from dictionary."""
        return cls(
            sha=data.get("sha", ""),
            message=data.get("message", ""),
            files=data.get("files", []),
            author=data.get("author", "ForgeAI"),
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class GitTag:
    """Represents a semantic version tag applied to the repository."""

    name: str
    sha: str
    annotation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "name": self.name,
            "sha": self.sha,
            "annotation": self.annotation,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GitTag":
        """Creates instance from dictionary."""
        return cls(
            name=data.get("name", ""),
            sha=data.get("sha", ""),
            annotation=data.get("annotation", ""),
        )


@dataclass
class SemverBump:
    """Represents a semantic version bump recommendation produced by LLM analysis."""

    current: str
    recommended: str
    bump_type: str  # MAJOR, MINOR, PATCH
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "current": self.current,
            "recommended": self.recommended,
            "bump_type": self.bump_type,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SemverBump":
        """Creates instance from dictionary."""
        return cls(
            current=data.get("current", "0.0.0"),
            recommended=data.get("recommended", "0.0.1"),
            bump_type=data.get("bump_type", "PATCH"),
            rationale=data.get("rationale", ""),
        )


@dataclass
class GitHubPR:
    """Represents a GitHub Pull Request created by the plugin."""

    url: str
    number: int
    title: str
    branch: str
    base: str = "main"

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "url": self.url,
            "number": self.number,
            "title": self.title,
            "branch": self.branch,
            "base": self.base,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GitHubPR":
        """Creates instance from dictionary."""
        return cls(
            url=data.get("url", ""),
            number=data.get("number", 0),
            title=data.get("title", ""),
            branch=data.get("branch", ""),
            base=data.get("base", "main"),
        )


@dataclass
class GitReport:
    """Data container representing the complete Git Plugin output for a project."""

    project_id: str
    commits: List[GitCommit] = field(default_factory=list)
    tags: List[GitTag] = field(default_factory=list)
    semver: Optional[SemverBump] = None
    pr: Optional[GitHubPR] = None
    changelog: str = ""
    ci_manifest: Dict[str, Any] = field(default_factory=dict)
    status: str = "PENDING"  # SUCCESS, FAILED
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "project_id": self.project_id,
            "commits": [c.to_dict() for c in self.commits],
            "tags": [t.to_dict() for t in self.tags],
            "semver": self.semver.to_dict() if self.semver else None,
            "pr": self.pr.to_dict() if self.pr else None,
            "changelog": self.changelog,
            "ci_manifest": self.ci_manifest,
            "status": self.status,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GitReport":
        """Creates instance from dictionary."""
        semver_data = data.get("semver")
        pr_data = data.get("pr")
        return cls(
            project_id=data.get("project_id", ""),
            commits=[GitCommit.from_dict(c) for c in data.get("commits", [])],
            tags=[GitTag.from_dict(t) for t in data.get("tags", [])],
            semver=SemverBump.from_dict(semver_data) if semver_data else None,
            pr=GitHubPR.from_dict(pr_data) if pr_data else None,
            changelog=data.get("changelog", ""),
            ci_manifest=data.get("ci_manifest", {}),
            status=data.get("status", "PENDING"),
            summary=data.get("summary", ""),
        )
