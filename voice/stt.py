import numpy as np
import sounddevice as sd
import queue
import time

from faster_whisper import WhisperModel
from silero_vad import get_speech_timestamps, load_silero_vad
from logger import get_logger
from utils.config import load_config

logger = get_logger()


CONFIG = load_config()
STT = CONFIG["stt"]
VAD = CONFIG["silero_vad"]

SAMPLE_RATE = STT["sample_rate"]
BLOCK_SIZE = 512

whisper = WhisperModel(
    STT["model_size"],
    compute_type=STT["compute_type"],
)

vad_model = load_silero_vad()

audio_queue = queue.Queue()
is_speaking = False  # Stops mic audio from entering the queue while TTS is speaking


def audio_callback(indata, frames, time_info, status):
    global is_speaking

    if is_speaking:
        return

    audio_queue.put(indata.copy())


def clear_audio_queue():
    while True:
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            return


def transcribe(audio_np):
    audio_float = audio_np.astype(np.float32) / 32768.0
    segments, _ = whisper.transcribe(audio_float, language=STT["language"])

    return " ".join([seg.text for seg in segments]).strip()


def detect_speech(audio_np):
    audio_float = audio_np.astype(np.float32) / 32768.0

    return get_speech_timestamps(
        audio_float,
        vad_model,
        sampling_rate=SAMPLE_RATE,
        threshold=VAD["threshold"],
        min_speech_duration_ms=int(VAD["min_speech_duration"] * 1000),
        min_silence_duration_ms=int(VAD["min_silence_duration"] * 1000),
    )


def record_and_transcribe(callback):
    logger.debug("Listening for speech...")

    post_response_cooldown = VAD.get("post_response_cooldown", 0.5)
    max_wait_for_speech = VAD.get("max_wait_for_speech", 5.0)
    max_record_duration = VAD.get("max_record_duration", 30.0)
    end_of_utterance_silence = VAD.get(
        "end_of_utterance_silence", VAD["min_silence_duration"]
    )

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=BLOCK_SIZE,
        callback=audio_callback,
    ):
        clear_audio_queue()

        while True:
            # Wait for speech to start
            speech_chunks = []
            speech_started = False
            start_time = time.time()

            while True:
                chunk = audio_queue.get()
                speech_chunks.append(chunk.flatten())
                speech_audio = np.concatenate(speech_chunks)
                elapsed = time.time() - start_time

                if elapsed >= max_record_duration:
                    logger.warning(
                        "Recording stopped after max duration while waiting for speech"
                    )
                    break

                timestamps = detect_speech(speech_audio)

                if timestamps:
                    logger.debug("Speech detected")
                    speech_started = True
                    break

                if elapsed >= max_wait_for_speech:
                    logger.debug(
                        "No speech detected within wait window; continuing to listen"
                    )
                    break

            if not speech_started:
                clear_audio_queue()
                logger.debug("Listening for speech...")
                continue

            # Continue collecting until end of utterance silence
            while True:
                chunk = audio_queue.get()
                speech_chunks.append(chunk.flatten())
                speech_audio = np.concatenate(speech_chunks)
                elapsed = time.time() - start_time

                if elapsed >= max_record_duration:
                    logger.warning("Recording stopped after max duration")
                    break

                timestamps = detect_speech(speech_audio)
                if not timestamps:
                    continue

                last_end = timestamps[-1]["end"] / SAMPLE_RATE
                duration = len(speech_audio) / SAMPLE_RATE
                silence_after_speech = duration - last_end

                if (
                    time.time() - start_time > VAD["min_speech_duration"]
                    and silence_after_speech >= end_of_utterance_silence
                ):
                    break

            text = transcribe(speech_audio)

            if text:
                # Do not log user's spoken content — forward to callback which will print it
                callback(text)
            else:
                logger.warning("Speech detected but transcription was empty")

            if post_response_cooldown > 0:
                time.sleep(post_response_cooldown)

            clear_audio_queue()
            logger.debug("Listening for speech...")
