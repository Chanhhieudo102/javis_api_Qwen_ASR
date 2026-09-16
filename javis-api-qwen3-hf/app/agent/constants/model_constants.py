"""Model provider and failover logging constants."""

MODEL_NAME_METADATA_KEY = "model_name"
FALLBACK_MODEL_ANSWERED_MESSAGE = (
    "Failover occurred for purpose '%s': Primary model '%s' failed, answered by fallback model '%s'"
)
MODEL_CHAIN_EXHAUSTED_MESSAGE = (
    "All models exhausted in chain for purpose '%s' (primary: '%s'). Error: %s: %s"
)
