"""
Prompt template loader and generator helper for the Developer Plugin.
"""

import json
import logging
from pathlib import Path
from typing import List

from forge_plugins.planner.service import parse_json_response
from forge_plugins.developer.models import GeneratedFile
from forge_plugins.developer.exceptions import DeveloperInferenceError
from forge_plugins.developer.utils.pipeline import ImplementationContext

logger = logging.getLogger("ForgeAI.Plugins.Developer.Utils")


def load_prompt_and_generate(
    context: ImplementationContext,
    prompt_name: str,
    file_type: str,
) -> List[GeneratedFile]:
    """
    Loads an external prompt template, formats it, invokes LLM generation,
    and maps the output to a list of GeneratedFile objects.

    Args:
        context (ImplementationContext): Shared pipeline context.
        prompt_name (str): Name of the prompt file (without extension).
        file_type (str): The file type classification (e.g., "code").

    Returns:
        List[GeneratedFile]: Parsed and generated files.

    Raises:
        DeveloperInferenceError: If LLM generation or JSON parsing fails.
    """
    current_dir = Path(__file__).parent.parent
    prompt_path = current_dir / "prompts" / f"{prompt_name}.txt"

    if not prompt_path.exists():
        raise DeveloperInferenceError(f"Prompt template file not found: {prompt_path}")

    try:
        prompt_template = prompt_path.read_text(encoding="utf-8")
    except Exception as e:
        raise DeveloperInferenceError(
            f"Failed to read prompt template {prompt_path}: {e}"
        ) from e

    # Format planning/architecture context into JSON for injection
    plan_json = json.dumps(context.project_plan.to_dict(), indent=2)
    spec_json = json.dumps(context.architecture.to_dict(), indent=2)

    prompt = prompt_template.format(plan=plan_json, spec=spec_json)

    try:
        response = context.model_router.generate(prompt)
        raw_text = response.text
    except Exception as e:
        raise DeveloperInferenceError(f"Model Router generation failed: {e}") from e

    # Parse response JSON resiliently
    try:
        spec_data = parse_json_response(raw_text)
    except Exception as e:
        raise DeveloperInferenceError(
            f"Failed to parse LLM response JSON for step '{prompt_name}': {e}. Raw: {raw_text}"
        ) from e

    files_data = spec_data.get("files") or []
    generated_files: List[GeneratedFile] = []

    for item in files_data:
        try:
            # Enforce the step's file type if not specified or incorrect
            item_type = item.get("file_type") or file_type
            generated_files.append(
                GeneratedFile(
                    path=item.get("path", ""),
                    content=item.get("content", ""),
                    file_type=item_type,
                )
            )
        except Exception as e:
            raise DeveloperInferenceError(
                f"Malformed file entry in LLM response: {item}. Error: {e}"
            ) from e

    return generated_files
