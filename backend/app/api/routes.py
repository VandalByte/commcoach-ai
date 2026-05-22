from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.models.schemas import AnswerRequest, AnswerResponse, FinalReport, SessionCreateResponse, SessionQuestionResponse
from app.services.interview import interview_service
from app.services.parser import read_upload_text
from app.services.voice_stt import transcribe_audio_bytes
from app.services.voice_tts import synthesize_kokoro_wav, warmup_kokoro_background

router = APIRouter()


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1200)


def extract_candidate_name(resume_text: str) -> str | None:
    ignored = {"resume", "curriculum vitae", "cv", "profile", "summary"}
    for raw_line in resume_text.splitlines()[:12]:
        line = raw_line.strip()
        if not line or line.lower() in ignored or "@" in line or any(char.isdigit() for char in line):
            continue
        words = [word.strip(".,") for word in line.split()]
        if 1 < len(words) <= 4 and all(word[:1].isupper() for word in words if word):
            return " ".join(words)
    return None


@router.post("/sessions", response_model=SessionCreateResponse)
async def create_session(
    interview_type: str = Form("hr"),
    resume_text: str | None = Form(None),
    jd_text: str | None = Form(None),
    resume_file: UploadFile | None = File(None),
    jd_file: UploadFile | None = File(None),
):
    parsed_resume = resume_text or ""
    parsed_jd = jd_text or ""

    if resume_file is not None:
        parsed_resume = await read_upload_text(resume_file)
    if jd_file is not None:
        parsed_jd = await read_upload_text(jd_file)

    if not parsed_resume.strip() or not parsed_jd.strip():
        raise HTTPException(status_code=400, detail="Resume and JD content are required.")

    session = await interview_service.create_session(interview_type, parsed_resume, parsed_jd)

    return SessionCreateResponse(
        session_id=session.session_id,
        total_questions=len(session.questions),
        first_question=session.questions[0],
        candidate_name=extract_candidate_name(parsed_resume),
    )


@router.get("/sessions/{session_id}/question", response_model=SessionQuestionResponse)
async def get_question(session_id: str):
    session = interview_service.sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.current_index >= len(session.questions):
        raise HTTPException(status_code=400, detail="Interview completed")

    return SessionQuestionResponse(
        session_id=session_id,
        question_index=session.current_index + 1,
        total_questions=len(session.questions),
        question=session.questions[session.current_index],
    )


@router.post("/sessions/{session_id}/answer", response_model=AnswerResponse)
async def submit_answer(session_id: str, payload: AnswerRequest):
    if session_id not in interview_service.sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await interview_service.submit_answer(
        session_id,
        payload.answer,
        payload.duration_seconds,
        payload.long_pause_count,
        payload.speech_confidence,
    )
    return AnswerResponse(session_id=session_id, **result)


@router.get("/sessions/{session_id}/report", response_model=FinalReport)
async def get_report(session_id: str):
    if session_id not in interview_service.sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        return await interview_service.final_report(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/voice/tts")
async def text_to_speech(payload: TTSRequest):
    try:
        audio = synthesize_kokoro_wav(payload.text)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Kokoro TTS unavailable: {exc}") from exc

    return Response(content=audio, media_type="audio/wav")


@router.post("/voice/warmup")
async def warmup_text_to_speech():
    warmup_kokoro_background()
    return {"status": "warming"}


@router.post("/voice/stt")
async def speech_to_text(audio_file: UploadFile = File(...)):
    suffix = Path(audio_file.filename or "answer.webm").suffix or ".webm"
    audio = await audio_file.read()

    try:
        text = await run_in_threadpool(transcribe_audio_bytes, audio, suffix)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"STT unavailable: {exc}") from exc

    if not text:
        raise HTTPException(status_code=422, detail="No speech was detected in the recording.")

    return {"text": text}
