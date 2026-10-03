# FastAPI contract, controlled errors and bounded capacity.
from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import partial
from pathlib import PurePath
from typing import Any

import anyio
from fastapi import FastAPI, File, Form, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .cache import ReplayCache
from .comparison import compare_assessments
from .config import Settings
from .contracts import ComparisonRequest, ErrorDetail, ErrorEnvelope, EvaluationEnvelope
from .errors import ErrorCode, ServiceError
from .extraction import ExtractionLimits
from .pipeline import EvaluationPipeline
from .provider import OfflineProvider, OpenAICompatibleProvider
from .rubric import load_rubric

REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def build_pipeline(settings: Settings) -> EvaluationPipeline:
    rubric = load_rubric(settings.rubric_path)
    provider: Any
    if settings.mode == "offline":
        provider = OfflineProvider(rubric, "deck.pdf")
    else:
        provider = OpenAICompatibleProvider(
            settings.llm_base_url or "",
            settings.llm_api_key or "",
            settings.llm_model or "",
            vision_model=settings.vision_model,
            timeout=settings.provider_timeout_seconds,
        )
    return EvaluationPipeline(
        rubric,
        provider,
        cache=ReplayCache(settings.cache_path, settings.cache_enabled),
        extraction_limits=ExtractionLimits(max_pdf_bytes=settings.max_pdf_bytes),
        expose_confidence=settings.expose_provisional_confidence,
    )


class CapacityGate:
    def __init__(self, limit: int, wait_seconds: float) -> None:
        self._semaphore = asyncio.Semaphore(limit)
        self.wait_seconds = wait_seconds

    async def acquire(self) -> None:
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=self.wait_seconds)
        except TimeoutError as exc:
            raise ServiceError(
                ErrorCode.OVER_CAPACITY,
                "The service is at capacity; retry shortly.",
                retryable=True,
                status_code=429,
            ) from exc

    def release(self) -> None:
        self._semaphore.release()


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    chunks = []
    total = 0
    while chunk := await upload.read(65536):
        total += len(chunk)
        if total > limit:
            raise ServiceError(
                ErrorCode.FILE_TOO_LARGE,
                "An uploaded file exceeds the configured size limit.",
                field=upload.filename,
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _safe_name(value: str | None, fallback: str) -> str:
    name = PurePath(value or fallback).name
    name = "".join(c if c.isprintable() and c not in "\\/" else "_" for c in name)
    return name[:255] or fallback


def _error(request: Request, exc: ServiceError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    envelope = ErrorEnvelope(
        request_id=request_id,
        generated_at=datetime.now(UTC),
        error=ErrorDetail(
            code=exc.code.value,
            message=str(exc),
            field=exc.field,
            retryable=exc.retryable,
            details=exc.details,
        ),
    )
    headers = {"X-Request-ID": request_id}
    if exc.code == ErrorCode.OVER_CAPACITY:
        headers["Retry-After"] = "1"
    return JSONResponse(
        status_code=exc.status_code, content=envelope.model_dump(mode="json"), headers=headers
    )


def create_app(
    settings: Settings | None = None, pipeline: EvaluationPipeline | None = None
) -> FastAPI:
    settings = settings or Settings()
    gate = CapacityGate(settings.max_concurrency, settings.queue_wait_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.pipeline = pipeline or build_pipeline(settings)
        yield

    app = FastAPI(title="MamakScore AI Engine", version="1.0", lifespan=lifespan)

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        supplied = request.headers.get("X-Request-ID", "")
        request.state.request_id = supplied if REQUEST_ID.fullmatch(supplied) else str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
        return _error(request, exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error(
            request,
            ServiceError(
                ErrorCode.INVALID_REQUEST,
                "The request did not match the API contract.",
                details={"errors": len(exc.errors())},
            ),
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        print(
            json.dumps(
                {
                    "level": "error",
                    "request_id": getattr(request.state, "request_id", None),
                    "exception_type": type(exc).__name__,
                }
            )
        )
        return _error(
            request,
            ServiceError(
                ErrorCode.INTERNAL_ERROR, "The evaluation could not be completed.", status_code=500
            ),
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready(request: Request) -> dict[str, Any]:
        return {
            "status": "ready",
            "mode": settings.mode,
            "rubric_version": request.app.state.pipeline.rubric.version,
        }

    @app.post("/api/evaluate", response_model=EvaluationEnvelope)
    async def evaluate(
        request: Request,
        application_id: str = Form(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"),
        pitch_deck: UploadFile = File(),
        financial_model: UploadFile | None = File(default=None),
        use_cache: bool = Form(False),
        data_classification: str = Form("public"),
    ) -> EvaluationEnvelope:
        if data_classification not in {"public", "synthetic", "confidential"}:
            raise ServiceError(
                ErrorCode.INVALID_REQUEST,
                "Unknown data classification.",
                field="data_classification",
            )
        if (
            data_classification == "confidential"
            and not settings.confidential_processing_authorized
        ):
            raise ServiceError(
                ErrorCode.INVALID_REQUEST,
                "Confidential processing requires recorded written authorisation.",
                field="data_classification",
                status_code=403,
            )
        deck_name = _safe_name(pitch_deck.filename, "deck.pdf")
        if not deck_name.casefold().endswith(".pdf"):
            raise ServiceError(
                ErrorCode.UNSUPPORTED_FILE,
                "Only PDF pitch decks are supported.",
                field="pitch_deck",
                status_code=415,
            )
        finance_name = None
        if financial_model:
            finance_name = _safe_name(financial_model.filename, "financial-model.xlsx")
            if not finance_name.casefold().endswith(".xlsx"):
                raise ServiceError(
                    ErrorCode.UNSUPPORTED_FILE,
                    "Only XLSX financial models are supported.",
                    field="financial_model",
                    status_code=415,
                )
        deck = await _read_limited(pitch_deck, settings.max_pdf_bytes)
        finance = (
            await _read_limited(financial_model, settings.max_xlsx_bytes)
            if financial_model
            else None
        )
        if len(deck) + (len(finance) if finance else 0) > settings.max_total_bytes:
            raise ServiceError(
                ErrorCode.FILE_TOO_LARGE, "The combined upload exceeds the configured limit."
            )
        await gate.acquire()
        try:
            operation = partial(
                request.app.state.pipeline.evaluate,
                application_id,
                deck,
                deck_name,
                finance,
                finance_name,
                use_cache,
            )
            try:
                result = await asyncio.wait_for(
                    anyio.to_thread.run_sync(operation, abandon_on_cancel=True),
                    timeout=settings.request_timeout_seconds,
                )
            except TimeoutError as exc:
                raise ServiceError(
                    ErrorCode.PROVIDER_TIMEOUT,
                    "The evaluation exceeded its deadline.",
                    retryable=True,
                    status_code=504,
                ) from exc
        finally:
            gate.release()
        return EvaluationEnvelope(
            request_id=request.state.request_id, generated_at=datetime.now(UTC), assessment=result
        )

    @app.post("/api/compare")
    async def compare(request: Request, payload: ComparisonRequest) -> dict[str, Any]:
        return {
            "api_version": "1.0",
            "request_id": request.state.request_id,
            "generated_at": datetime.now(UTC),
            "comparison": compare_assessments(payload),
        }

    return app


app = create_app()
