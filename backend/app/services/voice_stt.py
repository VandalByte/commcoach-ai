from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import tomllib


WHISPER_MODEL: Any | None = None


def _load_stt_config() -> dict[str, Any]:
    config_path = Path(__file__).resolve().parents[3] / "config.toml"
    if not config_path.exists():
        return {}

    with config_path.open("rb") as config_file:
        return tomllib.load(config_file).get("stt", {})


def transcribe_audio_bytes(audio: bytes, suffix: str = ".webm") -> str:
    global WHISPER_MODEL

    if not audio:
        raise ValueError("Audio is required for STT.")

    config = _load_stt_config()
    if WHISPER_MODEL is None:
        from faster_whisper import WhisperModel

        WHISPER_MODEL = WhisperModel(
            config.get("model_size", "medium"),
            compute_type=config.get("compute_type", "float16"),
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_audio:
        temp_audio.write(audio)
        temp_path = Path(temp_audio.name)

    try:
        segments, _ = WHISPER_MODEL.transcribe(
            str(temp_path),
            language=config.get("language", "en"),
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
    finally:
        temp_path.unlink(missing_ok=True)
