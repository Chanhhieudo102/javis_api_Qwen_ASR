from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable, RunnableConfig

from app.agent.constants.model_constants import (
    FALLBACK_MODEL_ANSWERED_MESSAGE,
    MODEL_CHAIN_EXHAUSTED_MESSAGE,
    MODEL_NAME_METADATA_KEY,
)
from app.agent.schemas.model_profile import ModelProfile
from app.common.constants.error_constants import ErrorConstants
from app.common.exceptions import InternalServerException
from app.common.logging import get_logger

logger = get_logger(__name__)


class RunnableChatModel:
    """
    Wraps a primary ChatModel with optional fallbacks,
    failover warning logging, and failure boundary error conversion.
    """

    def __init__(
        self,
        profile: ModelProfile,
        primary_model: Runnable,
        fallback_model: Runnable | None = None,
    ) -> None:
        self.profile = profile
        self.primary_model = primary_model
        self.fallback_model = fallback_model

        if fallback_model is not None:
            self.runnable: Runnable = primary_model.with_fallbacks([fallback_model])
        else:
            self.runnable = primary_model

    async def ainvoke(
        self,
        input: list[BaseMessage] | str,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BaseMessage:
        """
        Invoke the underlying model chain with failover tracking and failure boundary.
        """
        try:
            reply = await self.runnable.ainvoke(input, config=config, **kwargs)
        except Exception as exc:
            logger.error(
                MODEL_CHAIN_EXHAUSTED_MESSAGE,
                self.profile.purpose,
                self.profile.primary_model,
                type(exc).__name__,
                exc,
            )
            raise InternalServerException(detail=ErrorConstants.Agent.MODEL_REQUEST_FAILED) from exc

        # Check if failover occurred and log once
        if hasattr(reply, "response_metadata") and isinstance(reply.response_metadata, dict):
            answered_by = reply.response_metadata.get(MODEL_NAME_METADATA_KEY, "")
            if answered_by and answered_by != self.profile.primary_model:
                logger.warning(
                    FALLBACK_MODEL_ANSWERED_MESSAGE,
                    self.profile.purpose,
                    self.profile.primary_model,
                    answered_by,
                )

        return reply
