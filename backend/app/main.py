from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.services.voice_tts import warmup_kokoro_background
from app.logger import get_logger

logger = get_logger()


def create_app() -> FastAPI:
    app = FastAPI(title="CommCoach AI", version="0.1.0")

    logger.info("Starting FastAPI app: CommCoach AI")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.on_event("startup")
    async def warmup_voice() -> None:
        logger.info("Warmup: starting background TTS warmup task")
        warmup_kokoro_background()
        logger.info("Warmup: TTS warmup task requested")

    return app


app = create_app()
