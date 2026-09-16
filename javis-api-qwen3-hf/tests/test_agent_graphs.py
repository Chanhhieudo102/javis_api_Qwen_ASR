import logging

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.agent.clients.runnable_chat_model import RunnableChatModel
from app.agent.constants.model_constants import MODEL_NAME_METADATA_KEY
from app.agent.enums.model_enums import ModelPurpose
from app.agent.schemas.model_profile import ModelProfile
from app.agent.utils.run_context import traced_run_name
from app.common.constants.error_constants import ErrorConstants
from app.common.exceptions import InternalServerException
from app.voice2text.graphs.transcript_analysis.builder import build as build_analysis_graph
from app.voice2text.graphs.transcript_analysis.nodes import (
    TranscriptAnalysisCleanPunctuateNode,
    TranscriptAnalysisSummarizeNode,
)
from app.voice2text.graphs.transcript_analysis.state import TranscriptAnalysisInput


def fake_model(*reply_contents: str, model_name: str = "primary-model") -> GenericFakeChatModel:
    """Helper to build a fake chat model returning specific messages in sequence."""
    msgs = [
        AIMessage(
            content=c,
            response_metadata={MODEL_NAME_METADATA_KEY: model_name},
        )
        for c in reply_contents
    ]
    return GenericFakeChatModel(messages=iter(msgs))


def failing_model(error_msg: str = "Network timeout") -> RunnableLambda:
    """Helper that always raises an exception when invoked."""
    def _raise(*args, **kwargs):
        raise RuntimeError(error_msg)
    return RunnableLambda(_raise)


@pytest.mark.asyncio
async def test_failover_when_primary_fails():
    """1. Primary fails -> Fallback succeeds and returns response."""
    profile = ModelProfile(
        purpose=ModelPurpose.TRANSCRIPT_ANALYSIS,
        primary_model="gpt-primary",
        fallback_model="gpt-fallback",
    )
    primary = failing_model("Primary upstream failure")
    fallback = fake_model("Fallback reply content", model_name="gpt-fallback")

    chat_model = RunnableChatModel(profile=profile, primary_model=primary, fallback_model=fallback)
    result = await chat_model.ainvoke("Test input")

    assert result.content == "Fallback reply content"
    assert result.response_metadata[MODEL_NAME_METADATA_KEY] == "gpt-fallback"


@pytest.mark.asyncio
async def test_failover_logs_warning(caplog):
    """2. Failover logs a warning with primary and fallback model names."""
    profile = ModelProfile(
        purpose=ModelPurpose.TRANSCRIPT_ANALYSIS,
        primary_model="gpt-primary",
        fallback_model="gpt-fallback",
    )
    primary = failing_model("Primary failed")
    fallback = fake_model("Fallback reply", model_name="gpt-fallback")

    chat_model = RunnableChatModel(profile=profile, primary_model=primary, fallback_model=fallback)
    with caplog.at_level(logging.WARNING):
        await chat_model.ainvoke("Test input")

    assert any(
        "Failover occurred for purpose 'transcript_analysis'" in record.message
        and "gpt-primary" in record.message
        and "gpt-fallback" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_exhausted_chain_raises_typed_error():
    """3. When all models fail, raise InternalServerException with typed error."""
    profile = ModelProfile(
        purpose=ModelPurpose.TRANSCRIPT_ANALYSIS,
        primary_model="gpt-primary",
        fallback_model="gpt-fallback",
    )
    primary = failing_model("Primary connection error")
    fallback = failing_model("Fallback timeout")

    chat_model = RunnableChatModel(profile=profile, primary_model=primary, fallback_model=fallback)

    with pytest.raises(InternalServerException) as exc_info:
        await chat_model.ainvoke("Test input")

    assert exc_info.value.detail == ErrorConstants.Agent.MODEL_REQUEST_FAILED
    assert exc_info.value.__cause__ is not None


@pytest.mark.asyncio
async def test_graph_statelessness():
    """4. Run 2 does not observe or inherit any state from Run 1."""
    msg1 = AIMessage(content="Punctuation 1")
    msg2 = AIMessage(content='{"summary": "Summary 1", "action_items": ["Item 1"]}')
    msg3 = AIMessage(content="Punctuation 2")
    msg4 = AIMessage(content='{"summary": "Summary 2", "action_items": ["Item 2"]}')

    mock_llm = GenericFakeChatModel(messages=iter([msg1, msg2, msg3, msg4]))
    graph = build_analysis_graph(model=mock_llm)

    # Run 1
    input_1: TranscriptAnalysisInput = {
        "raw_transcript": "First raw transcript",
        "language": "Japanese",
    }
    result_1 = await graph.ainvoke(input_1)
    assert result_1["cleaned_transcript"] == "Punctuation 1"
    assert result_1["summary"] == "Summary 1"

    # Run 2
    input_2: TranscriptAnalysisInput = {
        "raw_transcript": "Second raw transcript",
        "language": "Japanese",
    }
    result_2 = await graph.ainvoke(input_2)
    assert result_2["cleaned_transcript"] == "Punctuation 2"
    assert result_2["summary"] == "Summary 2"
    assert "First raw transcript" not in str(result_2)


@pytest.mark.asyncio
async def test_output_schema_filters_scratch_fields():
    """5. StateGraph filters internal scratch fields using output_schema."""
    mock_llm = fake_model("Cleaned content", '{"summary": "Summary", "action_items": []}')
    graph = build_analysis_graph(model=mock_llm)

    input_data: TranscriptAnalysisInput = {
        "raw_transcript": "Raw content that should not leak to output",
        "language": "Japanese",
    }
    result = await graph.ainvoke(input_data)

    # raw_transcript and language are in TranscriptAnalysisState, but NOT in TranscriptAnalysisOutput
    assert "cleaned_transcript" in result
    assert "summary" in result
    assert "action_items" in result
    assert "raw_transcript" not in result
    assert "language" not in result


def test_node_instances_hold_config_not_request_state():
    """6. Node instances only hold configuration (__init__), never request state."""
    model = fake_model("Fake")
    punctuate_node = TranscriptAnalysisCleanPunctuateNode(model, "system prompt")
    summarize_node = TranscriptAnalysisSummarizeNode(model, "summarize prompt")

    # Instance dict should only contain configured dependencies
    assert set(punctuate_node.__dict__.keys()) == {"model", "system_prompt"}
    assert set(summarize_node.__dict__.keys()) == {"model", "system_prompt"}


def test_traced_run_name_format():
    """7. traced_run_name contains name, run_id, and UTC timestamp."""
    run_name = traced_run_name("test_graph", "req-uuid-123")
    parts = run_name.split("_")
    assert len(parts) >= 3
    assert parts[0] == "test"
    assert parts[1] == "graph"
    assert "req-uuid-123" in run_name
