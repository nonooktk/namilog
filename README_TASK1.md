# MI Session Task-1

MI は既存フィードバックから完全に分離し、`mi_sessions` / `mi_messages`、`/api/mi/*`、専用プロンプトと安全ゲートで実装した。メッセージ表には入力逐語を保存せず、応答中の `state_update.user_utterance_summary` を保存する。危機案内など定型文だけ `is_verbatim=true` とする。

境界のしきい値は 15 ターン（設計指定の 15〜20 の下限）とした。既存 active セッションがある開始要求は 409 ではなく既存セッションを返すため、二重開始を冪等に扱う。

設計上の「ユーザー発話保存→LLM」の順序は、逐語非保存と「LLM が返す要約を保存」の両立が不可能なため、要約が得られてから user/assistant の要約を同一短期トランザクションで追記する形にした。生のユーザー発話はDBへ一切送られない。LLM未設定時は開始・送信とも503で停止する。

## 検証結果（2026-07-18）

以下の検証を実施し、構文エラーがないこと、および既存テストを壊していないことを確認した。

- `python -m compileall app -q`: 成功（構文エラーなし）
- `pytest tests/test_mi_session.py -q`: 4 passed, 2 skipped（DBスタック未起動によるスキップ）
- `pytest -q`（全体）: 34 passed, 29 skipped（既存テストを壊していないことを確認。skip は Supabase ローカルスタック未起動によるもの）
