import uuid
import re
from typing import Any

from app.core.settings import settings
from app.models.domain import InterviewSession
from app.models.schemas import FinalReport
from app.services.agents import evaluate_answer, evaluate_final, generate_questions


class InterviewService:
    def __init__(self) -> None:
        self.sessions: dict[str, InterviewSession] = {}

    def _fallback_questions(self, interview_type: str) -> list[str]:
        common_questions = [
            "Tell me about yourself and your fit for this role.",
            "Walk me through a project or experience from your resume that best matches this job.",
            "What are your strongest skills for this role, and how have you used them recently?",
            "Describe a challenge you faced at work or in a project and how you handled it.",
            "Why are you interested in this role and this company?",
        ]

        if interview_type == "technical":
            common_questions[2] = "Explain a technical decision you made recently and the tradeoffs you considered."
        elif interview_type == "managerial":
            common_questions[2] = "How do you prioritize work and communicate progress when multiple deadlines compete?"
        elif interview_type == "behavioral":
            common_questions[2] = "Tell me about a time you received feedback and changed your approach."

        return common_questions

    async def create_session(self, interview_type: str, resume_text: str, jd_text: str) -> InterviewSession:
        session_id = str(uuid.uuid4())
        requested_count = max(settings.questions_per_session, settings.min_questions_per_session)

        questions = await generate_questions(
            interview_type=interview_type,
            resume=resume_text,
            jd=jd_text,
            question_count=requested_count,
        )

        for fallback_question in self._fallback_questions(interview_type):
            if len(questions) >= requested_count:
                break
            if fallback_question not in questions:
                questions.append(fallback_question)

        questions = questions[:requested_count]

        session = InterviewSession(session_id=session_id, interview_type=interview_type, questions=questions)
        self.sessions[session_id] = session
        return session

    def _calculate_delivery_metrics(
        self,
        answer: str,
        duration_seconds: float | None = None,
        long_pause_count: int = 0,
        speech_confidence: float | None = None,
    ) -> dict[str, Any]:
        words = re.findall(r"\b[\w'-]+\b", answer.lower())
        filler_terms = {
            "um",
            "uh",
            "erm",
            "hmm",
            "like",
            "basically",
            "actually",
            "literally",
            "you know",
            "i mean",
            "sort of",
            "kind of",
        }
        text = f" {answer.lower()} "
        fillers = sum(1 for word in words if word in filler_terms)
        fillers += sum(text.count(f" {phrase} ") for phrase in filler_terms if " " in phrase)

        minutes = max((duration_seconds or 0) / 60, 0.01)
        wpm = round(len(words) / minutes, 1) if duration_seconds else 0

        hesitation_points = fillers + (long_pause_count * 2)
        if hesitation_points >= 8:
            hesitation = "High"
        elif hesitation_points >= 4:
            hesitation = "Moderate"
        else:
            hesitation = "Low"

        pace_penalty = 0
        if duration_seconds:
            if wpm < 90:
                pace_penalty = 12
            elif wpm > 180:
                pace_penalty = 8

        confidence_from_speech = int((speech_confidence or 0.78) * 100)
        confidence_score = max(
            0,
            min(100, confidence_from_speech - fillers * 2 - long_pause_count * 5 - pace_penalty),
        )

        return {
            "wpm": wpm,
            "fillers": fillers,
            "long_pauses": long_pause_count,
            "hesitation": hesitation,
            "confidence_score": confidence_score,
        }

    async def submit_answer(
        self,
        session_id: str,
        answer: str,
        duration_seconds: float | None = None,
        long_pause_count: int = 0,
        speech_confidence: float | None = None,
    ) -> dict[str, Any]:
        session = self.sessions[session_id]
        current_question = session.questions[session.current_index]
        eval_result = await evaluate_answer(current_question, answer)
        metrics = self._calculate_delivery_metrics(answer, duration_seconds, long_pause_count, speech_confidence)
        metrics.update(
            {
                "grammar": eval_result.grammar,
                "suggestions": eval_result.suggestions,
            }
        )

        session.answers.append(answer)
        session.scores.append(eval_result.score)
        session.feedback.append(eval_result.feedback)
        session.metrics.append(metrics)
        session.current_index += 1

        done = session.current_index >= len(session.questions)
        next_question = None if done else session.questions[session.current_index]

        return {
            "feedback": eval_result.feedback,
            "score": eval_result.score,
            "metrics": metrics,
            "done": done,
            "next_question": next_question,
            "question_index": session.current_index,
        }

    async def final_report(self, session_id: str) -> FinalReport:
        session = self.sessions[session_id]
        if not session.scores:
            raise ValueError("No answers submitted yet.")

        summary = await evaluate_final(session.questions, session.answers, session.scores)
        avg_score = round(sum(session.scores) / len(session.scores), 2)

        return FinalReport(
            session_id=session_id,
            average_score=avg_score,
            strengths=summary.strengths,
            improvements=summary.improvements,
            plan=summary.plan,
        )


interview_service = InterviewService()
