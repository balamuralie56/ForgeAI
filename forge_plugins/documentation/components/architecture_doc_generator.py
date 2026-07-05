"""
Architecture Document Generator step in the documentation compilation pipeline.
"""

from ..utils.doc_pipeline import DocContext, DocPipelineStep
from ..utils.prompt_helper import load_prompt_and_generate


class ArchitectureDocGenerator(DocPipelineStep):
    """
    Generates Mermaid software design blueprints, plugins flow chart, and ADR review documents.
    """

    @property
    def name(self) -> str:
        return "Architecture Document Generator"

    def run(self, context: DocContext) -> None:
        docs = load_prompt_and_generate(context, "architecture", "architecture")
        context.generated_docs.extend(docs)
