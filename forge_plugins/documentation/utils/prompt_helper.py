"""
Prompt template loading and response parsing helpers for the Documentation Plugin.
"""

import json
import logging
from pathlib import Path
from typing import List

from forge_core.event_bus.models import Event
from forge_plugins.planner.service import parse_json_response
from ..models import GeneratedDocFile
from ..exceptions import DocInferenceError
from .doc_pipeline import DocContext

logger = logging.getLogger("ForgeAI.Plugins.Documentation.Utils")


def load_prompt_and_generate(
    context: DocContext,
    prompt_name: str,
    category: str,
) -> List[GeneratedDocFile]:
    """
    Loads an external prompt template, formats it with context parameters,
    invokes LLM generation, and maps the output JSON to a list of GeneratedDocFile objects.

    Args:
        context (DocContext): Shared pipeline context.
        prompt_name (str): Name of the prompt file (without extension).
        category (str): The documentation category (e.g. 'api').

    Returns:
        List[GeneratedDocFile]: Parsed and generated documentation files.

    Raises:
        DocInferenceError: If LLM generation or JSON parsing fails.
    """
    current_dir = Path(__file__).parent.parent
    prompt_path = current_dir / "prompts" / f"{prompt_name}.txt"

    if not prompt_path.exists():
        raise DocInferenceError(f"Prompt template file not found: {prompt_path}")

    try:
        prompt_template = prompt_path.read_text(encoding="utf-8")
    except Exception as e:
        raise DocInferenceError(
            f"Failed to read prompt template {prompt_path}: {e}"
        ) from e

    # Format planning, architecture, implementation files, and test results into JSON for model injection
    plan_json = json.dumps(context.project_plan.to_dict(), indent=2)
    spec_json = json.dumps(context.architecture.to_dict(), indent=2)
    report_json = json.dumps(context.implementation_report.to_dict(), indent=2)
    test_report_json = json.dumps(context.test_report.to_dict(), indent=2)

    prompt = prompt_template.format(
        plan=plan_json,
        spec=spec_json,
        report=report_json,
        test_report=test_report_json,
    )

    try:
        response = context.model_router.generate(prompt)
        raw_text = response.text
    except Exception as e:
        raise DocInferenceError(f"Model Router generation failed: {e}") from e

    # Parse response JSON resiliently
    try:
        spec_data = parse_json_response(raw_text)
    except Exception as e:
        raise DocInferenceError(
            f"Failed to parse LLM response JSON for step '{prompt_name}': {e}. Raw: {raw_text}"
        ) from e

    files_data = spec_data.get("files") or []
    generated_docs: List[GeneratedDocFile] = []

    for item in files_data:
        try:
            if not isinstance(item, dict):
                raise ValueError("Item entry must be a JSON dictionary.")
            path = item.get("path")
            content = item.get("content")
            if not path or not content or not isinstance(path, str) or not isinstance(content, str):
                raise ValueError("Each entry must define non-empty 'path' and 'content' strings.")
            
            item_category = item.get("category") or category
            generated_docs.append(
                GeneratedDocFile(
                    path=path,
                    content=content,
                    category=item_category,
                )
            )
            # Emit file generated event
            event_data = {
                "project_id": context.architecture.project_id,
                "path": item.get("path", ""),
                "category": item_category,
            }
            context.event_bus.publish(
                Event(event_type="documentation.file_generated", data=event_data)
            )
        except Exception as e:
            raise DocInferenceError(
                f"Malformed document entry in LLM response: {item}. Error: {e}"
            ) from e

    return generated_docs
