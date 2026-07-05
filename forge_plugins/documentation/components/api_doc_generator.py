"""
API Document Generator step in the documentation compilation pipeline.
"""

from ..utils.doc_pipeline import DocContext, DocPipelineStep
from ..utils.prompt_helper import load_prompt_and_generate


class ApiDocGenerator(DocPipelineStep):
    """
    Generates API references, REST specs, database schema tables, and data models docs.
    """

    @property
    def name(self) -> str:
        return "API Document Generator"

    def run(self, context: DocContext) -> None:
        docs = load_prompt_and_generate(context, "api", "api")
        context.generated_docs.extend(docs)
