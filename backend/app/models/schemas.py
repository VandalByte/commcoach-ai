from pydantic import BaseModel, Field
from typing import Literal


InterviewType = Literal["hr", "technical", "managerial", "behavioral"]


class SessionCreateResponse(BaseModel):
    session_id: str
    total_questions: int
    first_question: str
    candidate_name: str | None = None


class SessionQuestionResponse(BaseModel):
    session_id: str
    question_index: int
    total_questions: int
    question: str


class AnswerRequest(BaseModel):
    answer: str = Field(min_length=5)
    duration_seconds: float | None = Field(default=None, ge=0)
    long_pause_count: int = Field(default=0, ge=0)
    speech_confidence: float | None = Field(default=None, ge=0, le=1)


class AnswerMetrics(BaseModel):
    wpm: float = Field(ge=0)
    fillers: int = Field(ge=0)
    long_pauses: int = Field(ge=0)
    hesitation: str
    confidence_score: int = Field(ge=0, le=100)
    grammar: str
    suggestions: list[str]


class AnswerResponse(BaseModel):
    session_id: str
    question_index: int
    feedback: str
    score: int = Field(ge=0, le=10)
    metrics: AnswerMetrics
    done: bool
    next_question: str | None = None


class FinalReport(BaseModel):
    session_id: str
    average_score: float
    strengths: list[str]
    improvements: list[str]
    plan: list[str]
