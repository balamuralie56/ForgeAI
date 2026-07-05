"""
Strongly typed planning models for the ForgeAI Planner Plugin.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List


@dataclass(frozen=True)
class ProjectGoal:
    """
    Represents the user's high-level goal.
    """

    goal: str
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the goal to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectGoal":
        """Deserializes from a dictionary."""
        return cls(goal=data.get("goal", ""), description=data.get("description", ""))


@dataclass(frozen=True)
class Requirement:
    """
    Represents a specific system requirement.
    """

    requirement_id: str
    description: str
    is_functional: bool
    priority: str  # HIGH, MEDIUM, LOW
    dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the requirement to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Requirement":
        """Deserializes from a dictionary."""
        return cls(
            requirement_id=data.get("requirement_id", ""),
            description=data.get("description", ""),
            is_functional=data.get("is_functional", True),
            priority=data.get("priority", "MEDIUM"),
            dependencies=data.get("dependencies", []),
        )


@dataclass(frozen=True)
class ClarificationQuestion:
    """
    Represents a question raised to clarify ambiguity in goal requirements.
    """

    question_id: str
    question: str
    context: str
    assumed_answer: str

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the question to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClarificationQuestion":
        """Deserializes from a dictionary."""
        return cls(
            question_id=data.get("question_id", ""),
            question=data.get("question", ""),
            context=data.get("context", ""),
            assumed_answer=data.get("assumed_answer", ""),
        )


@dataclass(frozen=True)
class Milestone:
    """
    Represents a major milestone in project implementation.
    """

    milestone_id: str
    title: str
    description: str
    tasks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the milestone to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Milestone":
        """Deserializes from a dictionary."""
        return cls(
            milestone_id=data.get("milestone_id", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            tasks=data.get("tasks", []),
        )


@dataclass(frozen=True)
class Task:
    """
    Represents a specific task in the project plan.
    """

    task_id: str
    name: str
    description: str
    milestone_id: str
    dependencies: List[str] = field(default_factory=list)
    estimated_duration_hours: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the task to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """Deserializes from a dictionary."""
        return cls(
            task_id=data.get("task_id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            milestone_id=data.get("milestone_id", ""),
            dependencies=data.get("dependencies", []),
            estimated_duration_hours=float(data.get("estimated_duration_hours", 1.0)),
        )


@dataclass(frozen=True)
class TaskDependency:
    """
    Represents a dependency connection between two tasks.
    """

    task_id: str
    depends_on_task_id: str
    dependency_type: str = "finish_to_start"

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the dependency to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskDependency":
        """Deserializes from a dictionary."""
        return cls(
            task_id=data.get("task_id", ""),
            depends_on_task_id=data.get("depends_on_task_id", ""),
            dependency_type=data.get("dependency_type", "finish_to_start"),
        )


@dataclass(frozen=True)
class ProjectPlan:
    """
    Represents the full structural project plan.
    """

    goal: ProjectGoal
    requirements: List[Requirement] = field(default_factory=list)
    clarifications: List[ClarificationQuestion] = field(default_factory=list)
    milestones: List[Milestone] = field(default_factory=list)
    tasks: List[Task] = field(default_factory=list)
    dependencies: List[TaskDependency] = field(default_factory=list)
    estimated_order: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the project plan to a nested dictionary."""
        return {
            "goal": self.goal.to_dict(),
            "requirements": [r.to_dict() for r in self.requirements],
            "clarifications": [c.to_dict() for c in self.clarifications],
            "milestones": [m.to_dict() for m in self.milestones],
            "tasks": [t.to_dict() for t in self.tasks],
            "dependencies": [d.to_dict() for d in self.dependencies],
            "estimated_order": self.estimated_order,
            "risks": self.risks,
            "assumptions": self.assumptions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectPlan":
        """Deserializes a project plan from a nested dictionary."""
        goal_data = data.get("goal") or {}
        return cls(
            goal=ProjectGoal.from_dict(goal_data),
            requirements=[
                Requirement.from_dict(r) for r in data.get("requirements", [])
            ],
            clarifications=[
                ClarificationQuestion.from_dict(c)
                for c in data.get("clarifications", [])
            ],
            milestones=[Milestone.from_dict(m) for m in data.get("milestones", [])],
            tasks=[Task.from_dict(t) for t in data.get("tasks", [])],
            dependencies=[
                TaskDependency.from_dict(d) for d in data.get("dependencies", [])
            ],
            estimated_order=data.get("estimated_order", []),
            risks=data.get("risks", []),
            assumptions=data.get("assumptions", []),
        )
