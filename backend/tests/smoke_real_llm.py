"""実 GPT-4o-mini / text-embedding-3-small の疎通スモーク（手動実行・pytest 非対象）。

pytest では conftest が OPENAI_API_KEY を空に上書きしてフェイクで検証するため、実 API は叩かない。
本スクリプトは **単体実行**（`python tests/smoke_real_llm.py`）で backend/.env の実キーを用い、
Docker ハーネス DB に対して以下を1回ずつ実走して疎通を確認する:

  1. 埋め込み生成（text-embedding-3-small）1件 → comment_embeddings 保存（1536次元）。
  2. 日次予測パイプライン（GPT-4o-mini 構造化出力）1回 → predictions upsert
     （スキーマ適合・score 1-10・advice/rationale の後段フィルタ通過）。
  3. FB チャットの GPT 危機判定（構造化出力）＋応答生成（自由記述）1往復。

前提: ハーネス DB（pgvector）が起動しスキーマ投入済みであること。実行前に環境変数で DB を指す。
セキュリティ: **API キーは一切出力しない**（設定有無のみ真偽で示す）。
"""
from __future__ import annotations

import asyncio
import os
import sys
import traceback
import uuid
from datetime import date, timedelta

# ハーネス DB を指す（.env の SUPABASE_DB_URL より環境変数を優先）。OPENAI_API_KEY は .env から読む。
os.environ.setdefault(
    "SUPABASE_DB_URL", "postgresql://postgres:postgres@127.0.0.1:5434/postgres"
)
os.environ.setdefault(
    "SUPABASE_JWT_SECRET", "super-secret-jwt-token-with-at-least-32-characters-long"
)
os.environ.setdefault("APP_ENV", "test")

import psycopg  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import close_pool, service_tx  # noqa: E402
from app.services import embeddings, prediction  # noqa: E402
from app.services.crisis import detect_crisis_llm  # noqa: E402
from app.services.guardrails import SYSTEM_PROMPT_FEEDBACK, wrap_user_data  # noqa: E402
from app.services.llm import build_llm_client  # noqa: E402


def _seed_user_and_records() -> tuple[str, list[tuple[str, date, str]]]:
    """ハーネス DB にユーザー（＋trigger で profile）と直近数日の記録を作る。"""
    today = date.today()
    base = today - timedelta(days=2)  # 予測 as-of 日
    comments = [
        "気圧が下がって頭が重い一日だった",
        "よく眠れて調子がよかった",
        "寒暖差が大きくて少しだるい",
        "仕事が立て込んで疲れた",
        "散歩したら気分が晴れた",
    ]
    seeded: list[tuple[str, date, str]] = []
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as conn:
        email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
        row = conn.execute(
            "insert into auth.users (email) values (%s) returning id", (email,)
        ).fetchone()
        uid = str(row[0])
        for i, c in enumerate(comments):
            d = base - timedelta(days=i)
            rid = conn.execute(
                """
                insert into public.daily_records (user_id, record_date, actual_score, comment)
                values (%s, %s, %s, %s) returning id
                """,
                (uid, d, 5 + (i % 3), c),
            ).fetchone()[0]
            seeded.append((str(rid), d, c))
    return uid, seeded


async def main() -> int:
    print("=== 実 LLM 疎通スモーク ===")
    print(f"OPENAI_API_KEY 設定あり: {bool(settings.openai_api_key)}")  # キー値は出さない
    print(f"chat_model={settings.openai_chat_model} / embed_model={settings.openai_embed_model}")
    client = build_llm_client()
    if client is None:
        print("NG: OPENAI_API_KEY が未設定のため実クライアントを生成できません。")
        return 1

    uid, seeded = _seed_user_and_records()
    target = date.today() - timedelta(days=1)
    ok = True

    async with service_tx() as conn:
        # 1) 埋め込み生成（1件） ------------------------------------------------
        one = [seeded[0]]  # (rid, date, comment)
        stored = await embeddings.embed_and_store(conn, uid, one, client)
        emb_row = await (
            await conn.execute(
                "select vector_dims(embedding) as dims, model from public.comment_embeddings where daily_record_id = %s",
                (seeded[0][0],),
            )
        ).fetchone()
        dims = emb_row["dims"] if emb_row else None
        print(f"[1] 埋め込み: 保存={stored}件 / 次元={dims} / model={emb_row['model'] if emb_row else None}")
        if stored != 1 or dims != embeddings.EMBEDDING_DIM:
            ok = False
            print("    NG: 埋め込みの保存件数/次元が想定外")

        # 2) 日次予測パイプライン（構造化出力） --------------------------------
        pred = await prediction.run_daily_prediction(
            conn, uid, client, target_date=target
        )
        ps = pred["predicted_score"]
        advice = pred["advice"]
        rationale = pred["rationale"]
        print(f"[2] 予測: target={pred['target_date']} score={ps} crisis_flag={pred['crisis_flag']}")
        print(f"    advice   : {advice}")
        print(f"    rationale: {rationale}")
        if not (isinstance(ps, int) and 1 <= ps <= 10):
            ok = False
            print("    NG: predicted_score が 1-10 の整数でない")
        if not advice or not rationale:
            ok = False
            print("    NG: advice/rationale が空（後段フィルタ後も本文が必要）")

    # 3) FB チャット: GPT 危機判定＋応答生成（1往復） --------------------------
    benign = "今日はなんとなく気分が落ち着かない一日でした"
    gpt_crisis = await detect_crisis_llm(client, benign)
    reply = await client.complete_text(
        system=SYSTEM_PROMPT_FEEDBACK,
        user=wrap_user_data(benign, "今回のフィードバック") + "\n共感的に短く応答してください。",
        max_tokens=200,
    )
    print(f"[3] FB: gpt_crisis(benign)={gpt_crisis} / reply='{reply}'")
    if not isinstance(gpt_crisis, bool) or not reply:
        ok = False
        print("    NG: 危機判定が真偽でない、または応答が空")

    print("=== 結果:", "PASS" if ok else "FAIL", "===")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        rc = asyncio.run(main())
    except Exception:  # noqa: BLE001 エラー時はトレースバック全文
        traceback.print_exc()
        rc = 2
    finally:
        try:
            asyncio.run(close_pool())
        except Exception:  # noqa: BLE001
            pass
    sys.exit(rc)
