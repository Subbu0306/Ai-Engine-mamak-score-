"""FastAPI Application layer, endpoints, error envelopes, and CapacityGate."""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
from fastapi import FastAPI, File, Form, Header, Request, UploadFile, status
from fastapi.responses import JSONResponse
from mamakscore.cache import ReplayCache
from mamakscore.comparison import compare_assessments
from mamakscore.config import Settings, get_settings
from mamakscore.contracts import ComparisonRequest
from mamakscore.errors import ErrorCode, ServiceError
from mamakscore.pipeline import EvaluationPipeline
from mamakscore.provider import OfflineProvider, OpenAIProvider
from mamakscore.rubric import load_rubric


class CapacityGate:
    """Limits concurrent job execution to protect worker thread pools."""

    def __init__(self, max_concurrency: int = 4, timeout: float = 0.1):
        self.max_concurrency = max_concurrency
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(max_concurrency)

    async def acquire(self) -> None:
        try:
            await asyncio.wait_for(self.semaphore.acquire(), timeout=self.timeout)
        except asyncio.TimeoutError:
            raise ServiceError(
                ErrorCode.OVER_CAPACITY,
                "Server is at maximum processing capacity. Please retry shortly.",
            )

    def release(self) -> None:
        self.semaphore.release()

gate = CapacityGate()

def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Factory function to build and return the FastAPI application instance."""
    return app
def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Factory function to build and return the FastAPI application instance."""
    return app

def build_pipeline(settings: Settings) -> EvaluationPipeline:
    rubric = load_rubric()
    if settings.provider == "openai" and settings.openai_api_key:
        provider = OpenAIProvider
        api_key=settings.openai_api_key,
        model_name=settings.openai_model,
        
    else:
        provider = OfflineProvider(rubric)

    cache = ReplayCache(settings.cache_db_path, enabled=settings.cache_enabled)
    return EvaluationPipeline(
        rubric=rubric,
        provider=provider,
        cache=cache,
        expose_confidence=settings.expose_confidence,
    )


app = FastAPI(title="MamakScore AI Engine API")


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID", "unknown")
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response

@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError):
    status_code = status.HTTP_400_BAD_REQUEST
    if exc.code == ErrorCode.UNSUPPORTED_FILE:
        status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    elif exc.code == ErrorCode.OVER_CAPACITY:
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
    elif exc.code == ErrorCode.AUTH_ERROR:
        status_code = status.HTTP_401_UNAUTHORIZED
    elif exc.field == "confidential":
        status_code = status.HTTP_403_FORBIDDEN
    elif exc.code in (
        ErrorCode.APPLICATION_MISMATCH,
        ErrorCode.UNGROUNDED_EVIDENCE,
        ErrorCode.INVALID_MODEL_OUTPUT,
    ):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return JSONResponse(status_code=status_code, content={"error": exc.to_dict()})

@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> Dict[str, str]:
    return {"ready": "true"}


@app.post("/api/evaluate")
async def evaluate(
    application_id: str = Form(...),
    pitch_deck: UploadFile = File(...),
    financial_model: Optional[UploadFile] = File(None),
    data_classification: Optional[str] = Form(None),
) -> Dict[str, Any]:
    deck_bytes = await pitch_deck.read()
    model_bytes = await financial_model.read() if financial_model else None

    # Check for confidential marking first (must return HTTP 403)
    if (data_classification and data_classification.lower() == "confidential") or b"CONFIDENTIAL" in deck_bytes[:500]:
        raise ServiceError(
            ErrorCode.INVALID_REQUEST,
            "Confidential documents are not supported for public evaluation.",
            field="confidential",
        )

    # Check valid PDF
    if not (pitch_deck.filename or "").lower().endswith(".pdf") or not deck_bytes.startswith(b"%PDF-"):
        raise ServiceError(
            ErrorCode.UNSUPPORTED_FILE,
            "Pitch deck must be a valid PDF file.",
            field="pitch_deck",
        )

    settings = get_settings()
    pipe = build_pipeline(settings)

    await gate.acquire()
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            pipe.evaluate,
            application_id,
            deck_bytes,
            pitch_deck.filename or "deck.pdf",
            model_bytes,
            financial_model.filename if financial_model else None,
        )
        res_dict = result.model_dump(mode="json")
        res_dict["mamak_score"] = f"{float(result.mamak_score):.1f}"
        return {
            "api_version": "1.0",
            "assessment": res_dict,
        }
    finally:
        gate.release()


@app.post("/api/compare")
def compare(request: ComparisonRequest) -> Dict[str, Any]:
    res = compare_assessments(request)
    comp_dict = res.model_dump(mode="json") if hasattr(res, "model_dump") else res
    return {"comparison": comp_dict}