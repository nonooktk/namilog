"""pytest 共通フィクスチャ。

テストユーザーの用意を2モードで行う（どちらも「本人の JWT で API を叩き RLS を検証」する）:

  Mode A（推奨・本物）: Supabase ローカルスタック（`supabase start`）が起動していれば、
    `supabase status` から接続情報を取り、GoTrue でユーザーを作成→サインインして実 JWT を得る。
    ここで作るユーザーは開発専用（email/password）。本番は Google OAuth（docs/GOOGLE_OAUTH.md）。

  Mode B（フォールバック・Docker ハーネス）: 環境変数 NAMILOG_TEST_DB_URL が指す Postgres
    （tests/_harness/supabase_shim.sql で Supabase 相当の auth を再現済み）に対し、auth.users へ
    直接ユーザーを作成し、共有シークレット（NAMILOG_TEST_JWT_SECRET）で HS256 の JWT を発行する。

どちらのモードも成立しなければ、DB を要するテストは自動スキップする。
"""
from __future__ import annotations

import os
import subprocess
import time
import uuid

import pytest


# ---------------------------------------------------------------------------
# モード検出（アプリ import 前に環境変数を確定させる。config は import 時に env を読む）
# ---------------------------------------------------------------------------
def _load_stack_config() -> dict | None:
    """Mode A: `supabase status -o env` からローカルスタックの接続情報を取得する。"""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    try:
        out = subprocess.run(
            ["supabase", "status", "-o", "env"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    cfg: dict[str, str] = {}
    for line in out.stdout.splitlines():
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        cfg[k.strip()] = v.strip().strip('"')

    def pick(*suffixes: str) -> str | None:
        for key, val in cfg.items():
            for suf in suffixes:
                if key.endswith(suf):
                    return val
        return None

    api_url, db_url = pick("API_URL"), pick("DB_URL")
    jwt_secret, service_key = pick("JWT_SECRET"), pick("SERVICE_ROLE_KEY")
    anon_key = pick("ANON_KEY")
    if not (api_url and db_url and jwt_secret and service_key):
        return None
    return {
        "mode": "A",
        "api_url": api_url,
        "db_url": db_url,
        "jwt_secret": jwt_secret,
        "service_key": service_key,
        "anon_key": anon_key,
    }


def _load_harness_config() -> dict | None:
    """Mode B: Docker ハーネスの接続情報を環境変数から取得する。"""
    db_url = os.environ.get("NAMILOG_TEST_DB_URL")
    if not db_url:
        return None
    return {
        "mode": "B",
        "db_url": db_url,
        "jwt_secret": os.environ.get(
            "NAMILOG_TEST_JWT_SECRET",
            "super-secret-jwt-token-with-at-least-32-characters-long",
        ),
    }


_STACK = _load_stack_config() or _load_harness_config()

if _STACK:
    os.environ["SUPABASE_DB_URL"] = _STACK["db_url"]
    os.environ["SUPABASE_JWT_SECRET"] = _STACK["jwt_secret"]
    os.environ.pop("SUPABASE_JWKS_URL", None)
    if _STACK.get("api_url"):
        os.environ["SUPABASE_URL"] = _STACK["api_url"]

requires_stack = pytest.mark.skipif(
    _STACK is None,
    reason="Supabase ローカル/ハーネスDB が未起動のためスキップ",
)


# ---------------------------------------------------------------------------
# ユーザー作成＋トークン発行（モード別）
# ---------------------------------------------------------------------------
def _create_user_mode_a(prefix: str) -> tuple[str, str]:
    import httpx

    api = _STACK["api_url"]
    service_key = _STACK["service_key"]
    anon_key = _STACK["anon_key"] or service_key
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
    password = "dev-Password-123!"
    admin_headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(base_url=api, timeout=30) as c:
        r = c.post(
            "/auth/v1/admin/users",
            headers=admin_headers,
            json={"email": email, "password": password, "email_confirm": True},
        )
        r.raise_for_status()
        user_id = r.json()["id"]
        r2 = c.post(
            "/auth/v1/token",
            params={"grant_type": "password"},
            headers={"apikey": anon_key, "Content-Type": "application/json"},
            json={"email": email, "password": password},
        )
        r2.raise_for_status()
        token = r2.json()["access_token"]
    return user_id, token


def _create_user_mode_b(prefix: str) -> tuple[str, str]:
    import jwt
    import psycopg

    email = f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
    with psycopg.connect(_STACK["db_url"], autocommit=True) as conn:
        row = conn.execute(
            "insert into auth.users (email) values (%s) returning id", (email,)
        ).fetchone()
        user_id = str(row[0])
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": user_id,
            "role": "authenticated",
            "aud": "authenticated",
            "iat": now,
            "exp": now + 3600,
        },
        _STACK["jwt_secret"],
        algorithm="HS256",
    )
    return user_id, token


def _create_user_and_token(prefix: str) -> tuple[str, str]:
    if _STACK["mode"] == "A":
        return _create_user_mode_a(prefix)
    return _create_user_mode_b(prefix)


# ---------------------------------------------------------------------------
# フィクスチャ
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def db_url():
    """RLS 独立検証（probe）用に、テスト DB の接続文字列を返す。"""
    if _STACK is None:
        pytest.skip("DB 未起動")
    return _STACK["db_url"]


@pytest.fixture(scope="session")
def user_a():
    if _STACK is None:
        pytest.skip("DB 未起動")
    uid, token = _create_user_and_token("usera")
    return {"id": uid, "token": token, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture(scope="session")
def user_b():
    if _STACK is None:
        pytest.skip("DB 未起動")
    uid, token = _create_user_and_token("userb")
    return {"id": uid, "token": token, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def batch_headers(monkeypatch):
    """バッチ内部トークン（BATCH_INTERNAL_TOKEN）を設定し、正しいヘッダを返す。"""
    from app.config import settings

    token = "test-batch-token-xyz"
    monkeypatch.setattr(settings, "batch_internal_token", token)
    return {"X-Batch-Token": token}


@pytest.fixture
def use_fakes():
    """フェイク LLM / Open-Meteo を dependency override で差し込むヘルパ。

    テスト内で `llm, meteo = use_fakes()` のように呼び、任意のフェイクを指定できる。
    テスト終了時に override を自動クリアする。
    """
    from _fakes import FakeLLMClient, FakeMeteoGetter

    from app.deps.providers import get_llm_client, get_meteo_getter
    from app.main import app

    def _install(llm=None, meteo=None):
        llm = llm or FakeLLMClient()
        meteo = meteo or FakeMeteoGetter()
        app.dependency_overrides[get_llm_client] = lambda: llm
        app.dependency_overrides[get_meteo_getter] = lambda: meteo
        return llm, meteo

    yield _install

    # get_llm_client / get_meteo_getter は上のスコープに残っているのでそのまま片付ける。
    app.dependency_overrides.pop(get_llm_client, None)
    app.dependency_overrides.pop(get_meteo_getter, None)
