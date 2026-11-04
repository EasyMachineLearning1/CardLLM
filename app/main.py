"""Точка входа FastAPI-приложения.

Компоненты:
- POST /api/generate  — принимает данные прибора, генерирует карточку через GigaChat;
- GET  /api/health    — healthcheck;
- GET  /              — веб-форма (static/index.html).

Обработка ошибок (требования заказчика):
- некорректный входной JSON / пустые обязательные поля — 422 с понятным сообщением;
- ошибки GigaChat API и невалидный ответ модели — 502;
- характеристики карточки формируются ТОЛЬКО из входных данных (specs_builder),
  поэтому модель не может их выдумать.
"""
import logging
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.models.schemas import GenerateRequest, GenerateResponse
from app.services.card_service import CardGenerationService
from app.services.formatter import FormatterError
from app.services.gigachat_client import GigaChatAPIError, GigaChatClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@lru_cache
def get_giga_client() -> GigaChatClient:
    """Singleton-фабрика клиента GigaChat (создаётся при первом обращении)."""
    return GigaChatClient(get_settings())


def get_card_service() -> CardGenerationService:
    """FastAPI-зависимость: сервис генерации карточек (легко подменить в тестах)."""
    return CardGenerationService(get_giga_client(), get_settings().gigachat_model)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Сервис карточек запускается, модель=%s", get_settings().gigachat_model)
    yield
    await get_giga_client().aclose()
    logger.info("Сервис остановлен")


app = FastAPI(
    title="CardsService — генератор карточек приборов",
    description="FastAPI + GigaChat: приём данных прибора и генерация карточки (JSON/Markdown)",
    version="0.2.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Понятный ответ на некорректный входной JSON и пустые обязательные поля."""
    errors = [
        {"field": ".".join(str(loc) for loc in err.get("loc", [])),
         "message": err.get("msg", "")}
        for err in exc.errors()
    ]
    logger.warning("Некорректный входной запрос: %s", errors)
    return JSONResponse(
        status_code=422,
        content={"detail": "Некорректные входные данные: проверьте JSON и обязательные поля (name, manufacturer).", "errors": errors},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Фолбэк на необработанные исключения."""
    logger.exception("Необработанное исключение: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Внутренняя ошибка сервера"})


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """Веб-форма ввода характеристик прибора.

    Cache-Control: no-cache — браузер всегда перепроверяет версию страницы,
    чтобы после обновления сервиса не использовался устаревший JavaScript.
    """
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Healthcheck."""
    return {"status": "ok", "model": get_settings().gigachat_model}


@app.post("/api/generate", response_model=GenerateResponse)
async def generate(
    request: GenerateRequest,
    service: CardGenerationService = Depends(get_card_service),
) -> GenerateResponse:
    """Принять данные прибора и вернуть готовую карточку.

    Вся бизнес-логика (промпт, запрос к модели, разбор, рендер) — в
    :class:`CardGenerationService`; эндпоинт только принимает/отдаёт HTTP.
    """
    try:
        return await service.generate_card(request)
    except GigaChatAPIError as exc:
        logger.error("Ошибка GigaChat API: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except FormatterError as exc:
        logger.error("Модель дважды вернула невалидный ответ: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Модель не смогла сформировать корректную карточку, попробуйте повторить запрос",
        ) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=get_settings().app_host, port=get_settings().app_port, reload=get_settings().app_debug)
