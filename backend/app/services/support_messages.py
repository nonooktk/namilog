"""相談窓口の案内文言（ARCHITECTURE.md §7.4）。

**確定版（2026-07-12）**: 窓口の名称・電話番号・受付時間は [[マイメロディ]] が確定し、
[[シナモロール]] の QA で再確認済み。正本は デザイン仕様.md 6.5「確定版」。
いずれも厚生労働省の公式ページで一次確認済み（確認日 2026-07-12）。

出典（2026-07-12 確認）:
  - よりそいホットライン: 厚生労働省「電話相談窓口｜まもろうよ こころ」
    https://www.mhlw.go.jp/mamorouyokokoro/soudan/tel/
  - こころの健康相談統一ダイヤル: 厚生労働省「こころの健康相談統一ダイヤル｜自殺対策」
    https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/hukushi_kaigo/seikatsuhogo/jisatsu/kokoro_dial.html

トーン方針（§7.4 / デザイン 6.1）: 責めない・命令しない・柔らかい語尾。非侵襲・やさしく。
介入・通報はしない。窓口の番号・受付時間に変更があればリリース前の最終 QA で再確認する運用。

窓口・番号を集約しておき、確定内容に変更があればこのファイルのみ差し替えれば全経路
（ホーム／体調入力／FB チャット）へ反映される。
"""
from __future__ import annotations

# 導入文（デザイン 6.5・トーン再点検の結果そのまま確定）。
CRISIS_SUPPORT_INTRO = (
    "もし今、つらい気持ちが大きくなっているなら、ひとりで抱えなくて大丈夫。"
    "よかったら話してみてね。"
)

# 掲載窓口（確定・2件）。表示文言（受付時間の短文）はデザイン 6.5 準拠。
# こころの健康相談統一ダイヤルは受付時間が地域差ありのため、断定的な時間表記をせず
# 「お住まいの地域により異なります」と正直に添える（誤案内による「かけたのに繋がらない」回避）。
CRISIS_SUPPORT_CONTACTS: tuple[dict[str, str], ...] = (
    {
        "name": "よりそいホットライン",
        "phone": "0120-279-338",
        "hours": "24時間・通話無料",
    },
    {
        "name": "こころの健康相談統一ダイヤル",
        "phone": "0570-064-556",
        "hours": "受付時間はお住まいの地域により異なります",
    },
)

# バックエンド経路（FB チャットの assistant 応答など）で1本のテキストとして添える確定文言。
CRISIS_SUPPORT_TEXT = (
    CRISIS_SUPPORT_INTRO
    + "\n"
    + "\n".join(
        f"・{c['name']}: {c['phone']}（{c['hours']}）" for c in CRISIS_SUPPORT_CONTACTS
    )
)


def crisis_support_text() -> str:
    """危機案内に添える文言を返す（将来 UI/経路ごとに出し分ける拡張点をここに集約）。"""
    return CRISIS_SUPPORT_TEXT
