from pydantic import BaseModel, Field

from app.agent.enums.model_enums import ModelPurpose


class ModelProfile(BaseModel):
    """Configuration profile for a specific model purpose."""

    purpose: ModelPurpose
    primary_model: str = Field(..., description="Primary LLM model name")
    fallback_model: str | None = Field(default=None, description="Fallback LLM model name if primary fails")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: float = Field(default=60.0, gt=0.0)

    model_config = {
        "frozen": True,
    }
