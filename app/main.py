"""FastAPI 应用工厂：把路由、异常处理器都挂进来。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_v1
from app.api.v1.health import router as health_router
from app.core.exceptions import AppError, register_exception_handlers
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时建表（幂等），并确保企业档案存在。"""
    from app.services import company_service

    init_db()
    company_service.ensure_company()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="智能财务记账 Agent",
        description="企业私有财务库 + AI 记账/对账/分析",
        version="0.1.0",
        lifespan=lifespan,
    )
    register_exception_handlers(app)
    app.include_router(health_router)  # /health
    app.include_router(api_v1)  # /api/v1/*

    # 静态资源（ECharts 等前端库放本地，不依赖外网）
    app.mount("/static", StaticFiles(directory="app/web"), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        """首页：财务工作台。"""
        return FileResponse("app/web/index.html")

    return app


app = create_app()
