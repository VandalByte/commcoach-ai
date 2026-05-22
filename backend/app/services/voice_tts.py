from __future__ import annotations

from io import BytesIO
from pathlib import Path
from threading import Lock, Thread
from typing import Any

import tomllib
from app.logger import get_logger

logger = get_logger()


PIPELINE: Any | None = None
WARMED_UP = False
WARMUP_LOCK = Lock()


def _load_tts_config() -> dict[str, Any]:
    config_path = Path(__file__).resolve().parents[3] / "config.toml"
    if not config_path.exists():
        return {}

    with config_path.open("rb") as config_file:
        return tomllib.load(config_file).get("tts", {})


def synthesize_kokoro_wav(text: str) -> bytes:
    global PIPELINE

    if not text.strip():
        raise ValueError("Text is required for TTS.")

    config = _load_tts_config()
    logger.info("TTS: synthesize request", extra={"text_length": len(text)})
    sample_rate = int(config.get("kokoro_sample_rate", 24000))
    voice = config.get("kokoro_voice", "af_heart")
    speed = float(config.get("kokoro_speed", 1.0))
    split_pattern = config.get("kokoro_split_pattern", r"\n+")
    lang_code = config.get("kokoro_lang_code", "a")

    if PIPELINE is None:
        logger.info("TTS: loading Kokoro pipeline", extra={"lang": lang_code})
        from kokoro import KPipeline

        PIPELINE = KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M")

    import numpy as np
    import soundfile as sf

    chunks = []
    generator = PIPELINE(text, voice=voice, speed=speed, split_pattern=split_pattern)
    for _, _, audio in generator:
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()
        chunks.append(np.asarray(audio).squeeze().astype(np.float32, copy=False))

    if not chunks:
        logger.error("TTS: Kokoro did not return audio")
        raise RuntimeError("Kokoro did not return audio.")

    output = BytesIO()
    sf.write(output, np.concatenate(chunks), sample_rate, format="WAV")
    return output.getvalue()


def warmup_kokoro() -> None:
    global WARMED_UP

    if WARMED_UP:
        return

    with WARMUP_LOCK:
        if WARMED_UP:
            return
        logger.info("TTS: performing warmup synthesis")
        synthesize_kokoro_wav("Ready.")
        WARMED_UP = True


def warmup_kokoro_background() -> None:
    if WARMED_UP:
        return
    logger.info("TTS: starting background warmup thread")
    Thread(target=warmup_kokoro, daemon=True).start()
