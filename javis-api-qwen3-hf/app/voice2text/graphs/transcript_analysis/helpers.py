import json
import re


def build_punctuate_prompt(raw_transcript: str, language: str) -> str:
    """Build user prompt for punctuation and normalization."""
    return f"Language: {language}\n\nRaw Transcript:\n{raw_transcript}"


def build_summarize_prompt(cleaned_transcript: str, language: str) -> str:
    """Build user prompt for meeting summarization and action items."""
    return f"Language: {language}\n\nCleaned Conversation:\n{cleaned_transcript}"


def parse_summary_and_actions(raw_output: str) -> tuple[str, list[str]]:
    """
    Parse model output expecting JSON with 'summary' and 'action_items'.
    Falls back gracefully if response has markdown blocks or plain text.
    """
    clean_json = raw_output.strip()

    # Remove markdown code fence if present
    if "```" in clean_json:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_json)
        if match:
            clean_json = match.group(1).strip()

    try:
        data = json.loads(clean_json)
        summary = data.get("summary", "")
        action_items = data.get("action_items", [])
        if not isinstance(action_items, list):
            action_items = [str(action_items)] if action_items else []
        return str(summary).strip(), [str(item).strip() for item in action_items]
    except Exception:
        # Fallback: treat whole text as summary
        return raw_output.strip(), []
