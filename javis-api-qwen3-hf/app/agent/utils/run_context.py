import uuid
from datetime import UTC, datetime
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.common.configs import settings


def traced_run_name(name: str, run_id: str | None = None) -> str:
    """Build a unique run_name for LangSmith tracing: <name>_<run_id>_<UTC_timestamp>.

    e.g. transcript_analysis_6d662627-5021-42d0-991b-e4bc9b09c1fe_20260826T045627Z
    """
    rid = run_id or str(uuid.uuid4())
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{name}_{rid}_{ts}"


def run_config(
    name: str,
    run_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> RunnableConfig:
    """Build LangGraph RunnableConfig with run_name, environment tags, caller metadata, and context."""
    env_name = getattr(settings, "app_env", "dev")
    config: RunnableConfig = {
        "configurable": context or {},
        "run_name": traced_run_name(name, run_id),
        "tags": [env_name, name, *(tags or [])],
        "metadata": metadata or {},
    }
    return config


