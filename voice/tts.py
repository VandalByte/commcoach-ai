from logger import get_logger
from utils.config import load_config

import re
import time
import numpy as np
import sounddevice as sd

logger = get_logger()


CONFIG = load_config()

AGENT_NAME = CONFIG.get("agent", {}).get("name", "Assistant")
TTS_CONFIG = CONFIG.get("tts", {})
PIPELINE = None


def split_sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?]) +", text)


def _as_float32_audio(audio) -> np.ndarray:
    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()

    audio_np = np.asarray(audio).squeeze()
    return audio_np.astype(np.float32, copy=False)


class KokoroTTSPipeline:
    def __init__(self, config: dict, agent_name: str) -> None:
        try:
            from kokoro import KPipeline
        except ImportError as exc:
            raise ImportError(
                "Kokoro TTS is selected but not installed. Install it with "
                "`pip install kokoro>=0.9.2 soundfile misaki[en]` and ensure "
                "`espeak-ng` is available on your system."
            ) from exc

        self.agent_name = agent_name
        self.lang_code = config.get("kokoro_lang_code", "a")
        self.voice = config.get("kokoro_voice", "af_heart")
        self.speed = float(config.get("kokoro_speed", 1.0))
        self.sample_rate = int(config.get("kokoro_sample_rate", 24000))
        self.split_pattern = config.get("kokoro_split_pattern", r"\n+")
        self.pipeline = KPipeline(
            lang_code=self.lang_code, repo_id="hexgrad/Kokoro-82M"
        )

    def speak(self, text: str) -> None:
        logger.debug("Stopping any ongoing audio playback")
        sd.stop()
        time.sleep(0.05)

        stream = None

        try:
            for i, sentence in enumerate(split_sentences(text)):
                sentence = sentence.strip()
                if not sentence:
                    logger.debug(f"Skipping empty sentence {i}")
                    continue

                logger.debug(f"Synthesizing Kokoro sentence {i + 1}")

                generator = self.pipeline(
                    sentence,
                    voice=self.voice,
                    speed=self.speed,
                    split_pattern=self.split_pattern,
                )

                for _, _, audio in generator:
                    audio_np = _as_float32_audio(audio)

                    if stream is None:
                        stream = sd.OutputStream(
                            samplerate=self.sample_rate,
                            channels=1,
                            dtype="float32",
                        )
                        stream.start()

                    stream.write(audio_np)

                if stream is not None:
                    silence = np.zeros(int(self.sample_rate * 0.15), dtype=np.float32)
                    stream.write(silence)

        finally:
            if stream is not None:
                logger.debug("Finalizing Kokoro audio stream with padding")
                stream.write(np.zeros(int(self.sample_rate * 0.2), dtype=np.float32))
                stream.stop()
                stream.close()
                logger.debug("Kokoro audio stream closed successfully")


def get_pipeline():
    global PIPELINE

    if PIPELINE is None:
        logger.info("Using Kokoro TTS pipeline")
        PIPELINE = KokoroTTSPipeline(TTS_CONFIG, AGENT_NAME)

    return PIPELINE


def speak(text: str) -> None:
    get_pipeline().speak(text)
