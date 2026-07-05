"""
Project Document Generator step in the documentation compilation pipeline.
"""

from ..utils.doc_pipeline import DocContext, DocPipelineStep
from ..utils.prompt_helper import load_prompt_and_generate


class ProjectDocGenerator(DocPipelineStep):
    """
    Generates high-level project repository documentation (README.md, CHANGELOG.md, etc.).
    """

    @property
    def name(self) -> str:
        return "Project Document Generator"

    def run(self, context: DocContext) -> None:
        docs = load_prompt_and_generate(context, "project", "project")
        context.generated_docs.extend(docs)
