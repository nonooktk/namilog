"""認証まわりのテスト。未認証 401 はスタック不要（DB に触れない経路）。"""
from __future__ import annotations


def test_health_no_auth(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_missing_token_returns_401(client):
    """トークン無しは 401（§3.2）。"""
    r = client.get("/api/profile")
    assert r.status_code == 401


def test_invalid_token_returns_401(client):
    r = client.get("/api/profile", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert r.status_code == 401
