import os
from pathlib import Path

from router.openrouter import _http_client

BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "whisper-large-v3-turbo"

# No decoding prompt is sent. Whisper's prompt is a context hint, not an instruction, and on
# short or quiet clips it gets echoed straight into the transcript.


class GroqExtractor:
    """Speech-to-text for voice notes. Groq serves Whisper on a free tier."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        from openai import OpenAI

        self.model = model or os.environ.get("GROQ_AUDIO_MODEL", DEFAULT_MODEL)
        self.client = OpenAI(base_url=BASE_URL, api_key=api_key, http_client=_http_client())

    def text_for(self, media_id: str, file_path: Path | None) -> str:
        if not file_path or not file_path.exists():
            return ""
        with open(file_path, "rb") as clip:
            result = self.client.audio.transcriptions.create(
                model=self.model,
                file=clip,
                temperature=0,
                response_format="text",
            )
        text = result if isinstance(result, str) else result.text
        return text.strip()
