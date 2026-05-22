from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import tomllib
from app.logger import get_logger

logger = get_logger()


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
    logger.info(
        "STT: transcribe request received",
        extra={"bytes": len(audio), "suffix": suffix},
    )
    if WHISPER_MODEL is None:
        logger.info(
            "STT: loading Whisper model",
            extra={"model_size": config.get("model_size", "medium")},
        )
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
        transcript = " ".join(segment.text.strip() for segment in segments).strip()
        logger.info("STT: transcription complete", extra={"length": len(transcript)})
        return transcript
    finally:
        temp_path.unlink(missing_ok=True)
