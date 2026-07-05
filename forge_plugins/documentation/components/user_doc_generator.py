"""
User Document Generator step in the documentation compilation pipeline.
"""

from ..utils.doc_pipeline import DocContext, DocPipelineStep
from ..utils.prompt_helper import load_prompt_and_generate


class UserDocGenerator(DocPipelineStep):
    """
    Generates Quick Start tutorials, user manual reference notes, and FAQs.
    """

    @property
    def name(self) -> str:
        return "User Document Generator"

    def run(self, context: DocContext) -> None:
        docs = load_prompt_and_generate(context, "user", "user")
        context.generated_docs.extend(docs)
