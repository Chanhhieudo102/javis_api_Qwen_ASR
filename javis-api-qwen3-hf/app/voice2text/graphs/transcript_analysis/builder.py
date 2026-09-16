from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.clients.chat_model import ChatModel
from app.voice2text.constants.transcript_analysis_graph_constants import (
    CLEAN_PUNCTUATE_SYSTEM_PROMPT,
    SUMMARIZE_ACTIONS_SYSTEM_PROMPT,
)
from app.voice2text.enums.transcript_analysis_graph_enums import TranscriptAnalysisNodeName
from app.voice2text.graphs.transcript_analysis.nodes import (
    TranscriptAnalysisCleanPunctuateNode,
    TranscriptAnalysisSummarizeNode,
)
from app.voice2text.graphs.transcript_analysis.state import (
    TranscriptAnalysisInput,
    TranscriptAnalysisOutput,
    TranscriptAnalysisState,
)


def build(
    model: ChatModel,
    punctuate_prompt: str = CLEAN_PUNCTUATE_SYSTEM_PROMPT,
    summarize_prompt: str = SUMMARIZE_ACTIONS_SYSTEM_PROMPT,
) -> CompiledStateGraph:
    """Build and compile the Transcript Analysis StateGraph."""
    graph = StateGraph(
        TranscriptAnalysisState,
        input_schema=TranscriptAnalysisInput,
        output_schema=TranscriptAnalysisOutput,
    )

    clean_node = TranscriptAnalysisCleanPunctuateNode(model, punctuate_prompt)
    summarize_node = TranscriptAnalysisSummarizeNode(model, summarize_prompt)

    graph.add_node(TranscriptAnalysisNodeName.CLEAN_PUNCTUATE, clean_node.work)
    graph.add_node(TranscriptAnalysisNodeName.SUMMARIZE_ACTIONS, summarize_node.work)

    graph.add_edge(START, TranscriptAnalysisNodeName.CLEAN_PUNCTUATE)
    graph.add_edge(
        TranscriptAnalysisNodeName.CLEAN_PUNCTUATE,
        TranscriptAnalysisNodeName.SUMMARIZE_ACTIONS,
    )
    graph.add_edge(TranscriptAnalysisNodeName.SUMMARIZE_ACTIONS, END)

    return graph.compile()
