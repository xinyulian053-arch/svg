from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.diagram import router as diagram_router
from app.core.config import get_settings
from app.core.logger import setup_logging


settings = get_settings()
app_root = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str((app_root / "templates").resolve()))


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str((app_root / "static").resolve())), name="static")

app.include_router(diagram_router)


@app.get("/")
async def index_page() -> RedirectResponse:
    return RedirectResponse(url="/diagram-generator", status_code=307)


@app.get("/diagram-generator", response_class=HTMLResponse)
async def diagram_generator_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="diagram_generator.html",
        context={"request": request, "app_name": settings.app_name},
    )

