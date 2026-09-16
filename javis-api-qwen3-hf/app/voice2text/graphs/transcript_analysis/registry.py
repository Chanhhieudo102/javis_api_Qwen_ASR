import os

from langgraph.graph.state import CompiledStateGraph

from app.agent.enums.model_enums import ModelPurpose
from app.agent.models import build_chat_model
from app.agent.schemas.model_profile import ModelProfile
from app.voice2text.graphs.transcript_analysis import builder

TRANSCRIPT_ANALYSIS_PROFILE = ModelProfile(
    purpose=ModelPurpose.TRANSCRIPT_ANALYSIS,
    primary_model=os.getenv("LLM_MODEL_TRANSCRIPT_ANALYSIS", "gpt-4o-mini"),
    fallback_model=os.getenv("LLM_MODEL_TRANSCRIPT_ANALYSIS_FALLBACK", None),
    temperature=0.0,
    timeout_seconds=60.0,
)


def build_transcript_analysis_graph() -> CompiledStateGraph:
    """Build and compile the process-wide singleton transcript analysis graph."""
    model = build_chat_model(TRANSCRIPT_ANALYSIS_PROFILE)
    return builder.build(model=model)


TRANSCRIPT_ANALYSIS_GRAPH: CompiledStateGraph = build_transcript_analysis_graph()
