"""
Deterministic scaffolding for boilerplate developer-pipeline steps.

Dependency, environment, and configuration files are almost entirely
determined by the tech stack the architect already chose - there's no
judgment call left to make an LLM call for. detect_python_stack() reads the
signals architecture.decisions and architecture.database_design actually
expose; when it can't confidently name a stack, callers fall back to the
existing LLM-based generation unchanged (see prompt_helper.load_prompt_and_generate).
"""

from dataclasses import dataclass
from typing import List, Optional

from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import GeneratedFile

_FRAMEWORK_KEYWORDS = {
    "fastapi": ("fastapi",),
    "flask": ("flask",),
    "django": ("django",),
}


@dataclass(frozen=True)
class PythonStackProfile:
    """The subset of a Python project's shape that drives boilerplate content."""

    web_framework: Optional[
        str
    ]  # "fastapi" | "flask" | "django" | None (plain script/CLI)
    has_database: bool


def detect_python_stack(
    architecture: ArchitectureSpecification,
) -> Optional[PythonStackProfile]:
    """
    Scans architecture.decisions for an explicit Python signal. Returns None
    (never a guess) when the text doesn't confidently name Python - callers
    must fall back to LLM generation in that case, not template blindly.

    Args:
        architecture (ArchitectureSpecification): The chosen architecture.

    Returns:
        Optional[PythonStackProfile]: The detected profile, or None if this
        isn't confidently a Python project.
    """
    decision_text = " ".join(
        f"{d.category} {d.technology} {d.rationale}" for d in architecture.decisions
    ).lower()

    if "python" not in decision_text:
        return None

    web_framework = None
    for framework, keywords in _FRAMEWORK_KEYWORDS.items():
        if any(keyword in decision_text for keyword in keywords):
            web_framework = framework
            break

    return PythonStackProfile(
        web_framework=web_framework,
        has_database=len(architecture.database_design) > 0,
    )


def generate_dependency_files(profile: PythonStackProfile) -> List[GeneratedFile]:
    """Builds requirements.txt for the detected stack. Empty for a plain script/CLI."""
    packages: List[str] = []

    if profile.web_framework == "fastapi":
        packages += ["fastapi>=0.100.0", "uvicorn>=0.22.0"]
    elif profile.web_framework == "flask":
        packages += ["flask>=3.0.0"]
    elif profile.web_framework == "django":
        packages += ["django>=5.0.0"]

    if profile.has_database:
        if profile.web_framework == "fastapi":
            packages += ["sqlalchemy>=2.0.0", "pydantic-settings>=2.0.0"]
        elif profile.web_framework != "django":
            # Django ships its own ORM; every other framework needs one added.
            packages += ["sqlalchemy>=2.0.0"]

    content = "\n".join(packages) + ("\n" if packages else "")
    return [
        GeneratedFile(path="requirements.txt", content=content, file_type="dependency")
    ]


def generate_environment_files(profile: PythonStackProfile) -> List[GeneratedFile]:
    """Builds .env.example for the detected stack. No file at all for a plain script/CLI."""
    lines: List[str] = []

    if profile.has_database:
        lines.append("DATABASE_URL=sqlite:///./app.db")
    if profile.web_framework:
        lines.append("PORT=8000")
        lines.append("HOST=0.0.0.0")

    if not lines:
        return []

    content = "\n".join(lines) + "\n"
    return [
        GeneratedFile(path=".env.example", content=content, file_type="environment")
    ]


def generate_configuration_files(profile: PythonStackProfile) -> List[GeneratedFile]:
    """Builds src/config.py for the detected stack, mirroring it to the env file's keys."""
    if profile.has_database:
        settings_lines = ["    DATABASE_URL: str = 'sqlite:///./app.db'"]
        if profile.web_framework:
            settings_lines += [
                "    PORT: int = 8000",
                "    HOST: str = '0.0.0.0'",
            ]
        content = (
            "from pydantic_settings import BaseSettings\n\n\n"
            "class Settings(BaseSettings):\n" + "\n".join(settings_lines) + "\n\n"
            "    class Config:\n"
            "        env_file = '.env'\n\n\n"
            "settings = Settings()\n"
        )
    elif profile.web_framework:
        content = (
            "import os\n\n\n"
            "class Config:\n"
            "    PORT = int(os.getenv('PORT', '8000'))\n"
            "    HOST = os.getenv('HOST', '0.0.0.0')\n"
            "    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')\n"
        )
    else:
        content = (
            "import os\n\n\n"
            "class Config:\n"
            "    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')\n"
        )

    return [
        GeneratedFile(path="src/config.py", content=content, file_type="configuration")
    ]
