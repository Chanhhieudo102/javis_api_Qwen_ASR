from app.agent.utils.run_context import run_config
from app.voice2text.constants.transcript_analysis_graph_constants import GRAPH_RUN_NAME
from app.voice2text.graphs.transcript_analysis.registry import TRANSCRIPT_ANALYSIS_GRAPH
from app.voice2text.graphs.transcript_analysis.state import TranscriptAnalysisInput
from app.voice2text.schemas.transcript_analysis_schemas import (
    TranscriptAnalysisRequest,
    TranscriptAnalysisResponse,
)


class TranscriptAnalysisGraphService:
    """Stateless service that prepares run context and invokes Transcript Analysis Graph."""

    @classmethod
    async def analyze(
        cls,
        request: TranscriptAnalysisRequest,
    ) -> TranscriptAnalysisResponse:
        """Run transcript analysis graph."""
        graph_input: TranscriptAnalysisInput = {
            "raw_transcript": request.raw_transcript,
            "language": request.language,
        }

        config = run_config(
            name=GRAPH_RUN_NAME,
            run_id=request.session_id,
            metadata={"session_id": request.session_id} if request.session_id else None,
        )

        result = await TRANSCRIPT_ANALYSIS_GRAPH.ainvoke(graph_input, config=config)

        return TranscriptAnalysisResponse(
            cleaned_transcript=result.get("cleaned_transcript", ""),
            summary=result.get("summary", ""),
            action_items=result.get("action_items", []),
        )
