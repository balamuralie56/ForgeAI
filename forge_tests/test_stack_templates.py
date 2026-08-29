"""
Unit tests for the developer plugin's boilerplate stack templates.
Verifies stack detection stays conservative (never guesses) and that the
templated dependency/environment/configuration output tracks the detected
profile correctly.
"""

import unittest

from forge_plugins.architect.models import (
    ArchitectureSpecification,
    DatabaseSchema,
    TechnologyDecision,
)
from forge_plugins.developer.utils.stack_templates import (
    PythonStackProfile,
    detect_python_stack,
    generate_configuration_files,
    generate_dependency_files,
    generate_environment_files,
)


def _spec(decisions=None, has_database=False) -> ArchitectureSpecification:
    return ArchitectureSpecification(
        project_id="test-project",
        decisions=decisions or [],
        database_design=(
            [DatabaseSchema(table_name="users", columns={"id": "INTEGER"})]
            if has_database
            else []
        ),
    )


class TestDetectPythonStack(unittest.TestCase):
    """Stack detection must never guess - only fire on an explicit Python signal."""

    def test_empty_decisions_returns_none(self) -> None:
        self.assertIsNone(detect_python_stack(_spec()))

    def test_no_python_mention_returns_none(self) -> None:
        spec = _spec(
            decisions=[
                TechnologyDecision(
                    category="Backend",
                    technology="Node.js / Express",
                    rationale="Fast IO",
                )
            ]
        )
        self.assertIsNone(detect_python_stack(spec))

    def test_plain_python_no_framework(self) -> None:
        spec = _spec(
            decisions=[
                TechnologyDecision(
                    category="Language", technology="Python", rationale="Stdlib CLI"
                )
            ]
        )
        profile = detect_python_stack(spec)
        self.assertIsNotNone(profile)
        self.assertIsNone(profile.web_framework)
        self.assertFalse(profile.has_database)

    def test_detects_fastapi(self) -> None:
        spec = _spec(
            decisions=[
                TechnologyDecision(
                    category="Backend",
                    technology="Python / FastAPI",
                    rationale="Async, typed",
                )
            ]
        )
        profile = detect_python_stack(spec)
        self.assertEqual(profile.web_framework, "fastapi")

    def test_detects_flask(self) -> None:
        spec = _spec(
            decisions=[
                TechnologyDecision(
                    category="Backend", technology="Python/Flask", rationale="Simple"
                )
            ]
        )
        profile = detect_python_stack(spec)
        self.assertEqual(profile.web_framework, "flask")

    def test_detects_django(self) -> None:
        spec = _spec(
            decisions=[
                TechnologyDecision(
                    category="Backend",
                    technology="Python Django",
                    rationale="Batteries included",
                )
            ]
        )
        profile = detect_python_stack(spec)
        self.assertEqual(profile.web_framework, "django")

    def test_case_insensitive(self) -> None:
        spec = _spec(
            decisions=[
                TechnologyDecision(
                    category="Backend", technology="PYTHON / FASTAPI", rationale="x"
                )
            ]
        )
        profile = detect_python_stack(spec)
        self.assertEqual(profile.web_framework, "fastapi")

    def test_has_database_reflects_database_design(self) -> None:
        spec = _spec(
            decisions=[
                TechnologyDecision(
                    category="Language", technology="Python", rationale="x"
                )
            ],
            has_database=True,
        )
        profile = detect_python_stack(spec)
        self.assertTrue(profile.has_database)


class TestGenerateDependencyFiles(unittest.TestCase):
    def test_plain_cli_has_no_third_party_packages(self) -> None:
        files = generate_dependency_files(
            PythonStackProfile(web_framework=None, has_database=False)
        )
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].path, "requirements.txt")
        self.assertEqual(files[0].file_type, "dependency")
        self.assertEqual(files[0].content, "")

    def test_fastapi_with_database_includes_sqlalchemy_and_pydantic(self) -> None:
        files = generate_dependency_files(
            PythonStackProfile(web_framework="fastapi", has_database=True)
        )
        content = files[0].content
        self.assertIn("fastapi", content)
        self.assertIn("uvicorn", content)
        self.assertIn("sqlalchemy", content)
        self.assertIn("pydantic-settings", content)

    def test_django_with_database_excludes_sqlalchemy(self) -> None:
        files = generate_dependency_files(
            PythonStackProfile(web_framework="django", has_database=True)
        )
        content = files[0].content
        self.assertIn("django", content)
        self.assertNotIn("sqlalchemy", content)

    def test_fastapi_without_database_excludes_sqlalchemy(self) -> None:
        files = generate_dependency_files(
            PythonStackProfile(web_framework="fastapi", has_database=False)
        )
        content = files[0].content
        self.assertIn("fastapi", content)
        self.assertNotIn("sqlalchemy", content)


class TestGenerateEnvironmentFiles(unittest.TestCase):
    def test_plain_cli_produces_no_file(self) -> None:
        files = generate_environment_files(
            PythonStackProfile(web_framework=None, has_database=False)
        )
        self.assertEqual(files, [])

    def test_database_only_sets_database_url_but_not_port(self) -> None:
        files = generate_environment_files(
            PythonStackProfile(web_framework=None, has_database=True)
        )
        content = files[0].content
        self.assertIn("DATABASE_URL", content)
        self.assertNotIn("PORT", content)

    def test_framework_only_sets_port_but_not_database_url(self) -> None:
        files = generate_environment_files(
            PythonStackProfile(web_framework="flask", has_database=False)
        )
        content = files[0].content
        self.assertIn("PORT", content)
        self.assertIn("HOST", content)
        self.assertNotIn("DATABASE_URL", content)

    def test_framework_and_database_sets_all(self) -> None:
        files = generate_environment_files(
            PythonStackProfile(web_framework="fastapi", has_database=True)
        )
        content = files[0].content
        self.assertIn("DATABASE_URL", content)
        self.assertIn("PORT", content)
        self.assertIn("HOST", content)


class TestGenerateConfigurationFiles(unittest.TestCase):
    def test_plain_cli_minimal_config(self) -> None:
        files = generate_configuration_files(
            PythonStackProfile(web_framework=None, has_database=False)
        )
        self.assertEqual(files[0].path, "src/config.py")
        self.assertEqual(files[0].file_type, "configuration")
        self.assertIn("LOG_LEVEL", files[0].content)
        self.assertNotIn("pydantic", files[0].content)

    def test_database_uses_pydantic_settings(self) -> None:
        files = generate_configuration_files(
            PythonStackProfile(web_framework="fastapi", has_database=True)
        )
        content = files[0].content
        self.assertIn("pydantic_settings", content)
        self.assertIn("DATABASE_URL", content)
        self.assertIn("PORT", content)

    def test_framework_without_database_skips_pydantic(self) -> None:
        files = generate_configuration_files(
            PythonStackProfile(web_framework="flask", has_database=False)
        )
        content = files[0].content
        self.assertNotIn("pydantic", content)
        self.assertIn("PORT", content)

    def test_database_without_framework_skips_port(self) -> None:
        files = generate_configuration_files(
            PythonStackProfile(web_framework=None, has_database=True)
        )
        content = files[0].content
        self.assertIn("DATABASE_URL", content)
        self.assertNotIn("PORT", content)


if __name__ == "__main__":
    unittest.main()
