from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.exceptions import FallbackExceptionGroup, ModelAPIError, UserError
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.groq import GroqProvider
from pydantic_ai.providers.openai import OpenAIProvider

from app.core.settings import settings


class QuestionPack(BaseModel):
    questions: list[str]


class AnswerEval(BaseModel):
    score: int
    feedback: str
    grammar: str
    suggestions: list[str]


class FinalEval(BaseModel):
    strengths: list[str]
    improvements: list[str]
    plan: list[str]


ollama_provider = OpenAIProvider(base_url=settings.ollama_base_url, api_key="ollama")
ollama_model = OpenAIModel(model_name=settings.ollama_model, provider=ollama_provider)

try:
    groq_provider = GroqProvider(api_key=settings.groq_api_key)
    groq_model = GroqModel(settings.groq_model, provider=groq_provider)
    model = FallbackModel(groq_model, ollama_model)
except (UserError, ImportError):
    model = ollama_model

question_agent = Agent(model=model, output_type=QuestionPack)
answer_agent = Agent(model=model, output_type=AnswerEval)
final_agent = Agent(model=model, output_type=FinalEval)


def _clip_context(text: str, limit: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}..."


async def generate_questions(interview_type: str, resume: str, jd: str, question_count: int) -> list[str]:
    resume_context = _clip_context(resume, 7000)
    jd_context = _clip_context(jd, 5000)
    prompt = f"""
You are an interview coach.
Interview type: {interview_type}
Create exactly {question_count} interview questions based on resume and JD.
Resume:\n{resume_context}\n
JD:\n{jd_context}\n
Rules:
- Questions must be specific and realistic.
- Keep each question concise.
"""
    try:
        result = await question_agent.run(prompt)
        questions = [q.strip() for q in result.output.questions if q.strip()]
        return questions[:question_count]
    except (FallbackExceptionGroup, ModelAPIError):
        return []


async def evaluate_answer(question: str, answer: str) -> AnswerEval:
    prompt = f"""
Score this answer from 0 to 10.
Question: {question}
Answer: {answer}
Return strict JSON with:
- score (int)
- feedback (string)
- grammar (string)
- suggestions (array of short strings)

Feedback should be practical and short. Grammar should call out the most important grammar or clarity issue, or say "Clear and grammatically sound" when appropriate.
"""
    try:
        result = await answer_agent.run(prompt)
        return result.output
    except (FallbackExceptionGroup, ModelAPIError):
        return AnswerEval(
            score=5,
            feedback="I could not reach the AI evaluator, so this is a neutral fallback score.",
            grammar="Grammar was not evaluated because the model request failed.",
            suggestions=["Check model connectivity, then retry this answer for richer coaching."],
        )


async def evaluate_final(questions: list[str], answers: list[str], scores: list[int]) -> FinalEval:
    qa_lines = "\n".join(
        f"Q: {q}\nA: {a}\nScore: {s}/10" for q, a, s in zip(questions, answers, scores)
    )
    prompt = f"""
You are a communication coach. Based on this interview performance summary:
{qa_lines}

Return strict JSON:
- strengths: 3 bullet-like strings
- improvements: 3 bullet-like strings
- plan: 5 actionable steps
"""
    try:
        result = await final_agent.run(prompt)
        return result.output
    except (FallbackExceptionGroup, ModelAPIError):
        avg_score = round(sum(scores) / len(scores), 2) if scores else 0
        return FinalEval(
            strengths=[
                f"You completed the mock interview with an average score of {avg_score}/10.",
                "You gave enough spoken content for delivery metrics such as pace, pauses, and fillers.",
                "You stayed engaged through the voice-based interview flow.",
            ],
            improvements=[
                "AI final-summary generation was unavailable, so review the per-answer feedback cards.",
                "Strengthen answers with a clearer situation, action, and result structure.",
                "Add more role-specific examples from your resume and the job description.",
            ],
            plan=[
                "Retry the final report when Groq or Ollama connectivity is restored.",
                "Practice each question again with a 60 to 90 second answer target.",
                "Use one concrete achievement, metric, or project example per answer.",
                "Reduce long pauses by outlining three bullet points before speaking.",
                "Review grammar suggestions in each answer card and repeat the answer once.",
            ],
        )
