"""
Prompt template loader and generator helper for the Tester Plugin.
"""

import json
import logging
from pathlib import Path
from typing import List

from forge_core.event_bus.models import Event
from forge_plugins.planner.service import parse_json_response
from forge_plugins.tester.models import GeneratedTestFile
from forge_plugins.tester.exceptions import TestingInferenceError
from forge_plugins.tester.utils.test_pipeline import TestContext

logger = logging.getLogger("ForgeAI.Plugins.Tester.Utils")


def load_prompt_and_generate(
    context: TestContext,
    prompt_name: str,
    test_type: str,
) -> List[GeneratedTestFile]:
    """
    Loads an external prompt template, formats it with plan, spec, and implementation context,
    invokes LLM generation, and maps the output JSON to a list of GeneratedTestFile objects.

    Args:
        context (TestContext): Shared pipeline context.
        prompt_name (str): Name of the prompt file (without extension).
        test_type (str): The classification for the tests generated (e.g. 'unit').

    Returns:
        List[GeneratedTestFile]: Parsed and generated test files.

    Raises:
        TestingInferenceError: If LLM generation or JSON parsing fails.
    """
    current_dir = Path(__file__).parent.parent
    prompt_path = current_dir / "prompts" / f"{prompt_name}.txt"

    if not prompt_path.exists():
        raise TestingInferenceError(f"Prompt template file not found: {prompt_path}")

    try:
        prompt_template = prompt_path.read_text(encoding="utf-8")
    except Exception as e:
        raise TestingInferenceError(
            f"Failed to read prompt template {prompt_path}: {e}"
        ) from e

    # Format planning, architecture, and code assets context into JSON for injection
    plan_json = json.dumps(context.project_plan.to_dict(), indent=2)
    spec_json = json.dumps(context.architecture.to_dict(), indent=2)
    report_json = json.dumps(context.implementation_report.to_dict(), indent=2)

    prompt = prompt_template.format(plan=plan_json, spec=spec_json, report=report_json)

    try:
        response = context.model_router.generate(prompt, response_format="json")
        raw_text = response.text
    except Exception as e:
        raise TestingInferenceError(f"Model Router generation failed: {e}") from e

    # Parse response JSON resiliently
    try:
        spec_data = parse_json_response(raw_text)
    except Exception as e:
        raise TestingInferenceError(
            f"Failed to parse LLM response JSON for step '{prompt_name}': {e}. Raw: {raw_text}"
        ) from e

    files_data = spec_data.get("files") or []
    generated_files: List[GeneratedTestFile] = []

    for item in files_data:
        try:
            item_type = item.get("test_type") or test_type
            generated_files.append(
                GeneratedTestFile(
                    path=item.get("path", ""),
                    content=item.get("content", ""),
                    test_type=item_type,
                )
            )
            # Emit file generated event
            event_data = {
                "project_id": context.architecture.project_id,
                "path": item.get("path", ""),
                "test_type": item_type,
            }
            context.event_bus.publish(
                Event(event_type="tester.file_generated", data=event_data)
            )
        except Exception as e:
            raise TestingInferenceError(
                f"Malformed test file entry in LLM response: {item}. Error: {e}"
            ) from e

    return generated_files
