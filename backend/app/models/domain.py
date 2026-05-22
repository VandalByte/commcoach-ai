from dataclasses import dataclass, field


@dataclass
class InterviewSession:
    session_id: str
    interview_type: str
    questions: list[str]
    current_index: int = 0
    answers: list[str] = field(default_factory=list)
    scores: list[int] = field(default_factory=list)
    feedback: list[str] = field(default_factory=list)
    metrics: list[dict] = field(default_factory=list)
