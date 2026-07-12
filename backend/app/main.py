"""なみログ バックエンド エントリポイント（FastAPI）。

全データアクセスの入口を FastAPI に一本化する（P-1）。フロントは Supabase を直読みしない。
認証は全 API で Supabase JWT を検証する（§1.3）。
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import close_pool
from .routers import factors, history, home, profile, records


@asynccontextmanager
async def lifespan(app: FastAPI):
    # プールは遅延生成（初回リクエスト時）。ここでは終了処理のみ登録する。
    yield
    await close_pool()


app = FastAPI(title="なみログ API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile.router)
app.include_router(records.router)
app.include_router(factors.router)
app.include_router(home.router)
app.include_router(history.router)


@app.get("/health", tags=["meta"])
async def health():
    """疎通確認用（認証不要）。"""
    return {"status": "ok"}
