"""
Developer Document Generator step in the documentation compilation pipeline.
"""

from ..utils.doc_pipeline import DocContext, DocPipelineStep
from ..utils.prompt_helper import load_prompt_and_generate


class DeveloperDocGenerator(DocPipelineStep):
    """
    Generates local setup, installation guides, configuration guides, and troubleshooting developer docs.
    """

    @property
    def name(self) -> str:
        return "Developer Document Generator"

    def run(self, context: DocContext) -> None:
        docs = load_prompt_and_generate(context, "developer", "developer")
        context.generated_docs.extend(docs)
