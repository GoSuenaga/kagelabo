"""
kage-lab 開発プロジェクトサマリ — ボス向けスプレッドシート生成
Usage: python3 scripts/export_kage_summary.py
"""

import gspread
from gspread_formatting import (
    format_cell_range, CellFormat, Color, TextFormat,
    set_frozen, set_column_widths,
)
import time

# ── 認証 ──────────────────────────────────────────────
gc = gspread.oauth(
    credentials_filename="oauth_credentials.json",
    authorized_user_filename="token.json",
)

TITLE = "kage-lab 開発プロジェクト サマリ（2026-03-25 時点）"

sh = gc.create(TITLE)
print(f"✅ スプシ作成: {TITLE}")
print(f"   URL: https://docs.google.com/spreadsheets/d/{sh.id}/")

# ── 共通スタイル ───────────────────────────────────────
H1 = CellFormat(textFormat=TextFormat(bold=True, fontSize=16, foregroundColor=Color(0.72, 0.58, 0.42)))
H2 = CellFormat(textFormat=TextFormat(bold=True, fontSize=12, foregroundColor=Color(1, 1, 1)),
                 backgroundColor=Color(0.18, 0.20, 0.25))
TH = CellFormat(textFormat=TextFormat(bold=True, fontSize=10, foregroundColor=Color(0.72, 0.58, 0.42)),
                backgroundColor=Color(0.15, 0.17, 0.21))
DONE = CellFormat(textFormat=TextFormat(foregroundColor=Color(0.25, 0.73, 0.47)))
WIP  = CellFormat(textFormat=TextFormat(foregroundColor=Color(0.9, 0.75, 0.3)))
GRAY = CellFormat(textFormat=TextFormat(foregroundColor=Color(0.55, 0.58, 0.66)))
NOTE = CellFormat(textFormat=TextFormat(italic=True, foregroundColor=Color(0.55, 0.58, 0.66), fontSize=9))


def p():
    time.sleep(1.2)


# ================================================================
# Sheet 1: プロジェクト全体像
# ================================================================
ws = sh.sheet1
ws.update_title("全体像")

data = [
    ["kage-lab 開発プロジェクト サマリ"],
    [""],
    ["■ このプロジェクトは何か"],
    [""],
    ["「kage-lab」は、広告制作を AI で自動化・効率化するためのツール集です。"],
    ["1つのフォルダ（リポジトリ）に 4つのアプリがまとまっています。"],
    [""],
    ["アプリ名", "ひとことで", "今の状態"],
    ["KAGE（影秘書）", "Notionと連携するAI秘書チャット。スケジュール管理・タスク整理・朝ブリーフィングを提供", "✅ 本番稼働中（v0.302）"],
    ["VANTAN 動画生成", "学校広告のVlog風動画を AI で自動生成するパイプライン（台本→静止画→動画→合成）", "🔄 制作中（16本中12本完了）"],
    ["RAG（画像QC）", "リクルート広告バナーを AI で生成し、品質チェック・納品するツール", "🔄 C003キャンペーン進行中"],
    ["CCM（モバイル操作）", "iPhoneからClaude Codeを遠隔操作するツール。外出先からでも生成を開始・監視できる", "✅ 動作OK"],
    [""],
    ["■ 開発コントロールパネル"],
    [""],
    ["kage-lab のトップページ（control_panel.html）で、全アプリの起動状態を一覧表示。"],
    ["各アプリの「起動中🟢 / 停止中⚫」がひと目でわかるダッシュボードになっています。"],
    [""],
    ["■ 開発の進め方（ざっくり）"],
    [""],
    ["ステップ", "何をするか", "どこで"],
    ["1. コードを書く", "Claude Code（AI）と対話しながらプログラムを作成・修正", "PC上のClaude Code"],
    ["2. 保存する", "変更を「コミット」（セーブポイント作成）してGitHubにアップロード", "PC上のターミナル"],
    ["3. 動かす", "ローカル（自分のPC）でプログラムを実行して動画や画像を生成", "PC上のブラウザ"],
    ["4. 確認する", "生成結果をブラウザやスプシで確認、問題があれば1に戻る", "ブラウザ"],
    [""],
    ["※ KAGEだけは「Railway」という外部サーバーにデプロイ（公開）済み。"],
    ["　 それ以外のアプリはすべて自分のPC上で動かします。"],
]

ws.update("A1", data, value_input_option="RAW")
p()
format_cell_range(ws, "A1", H1)
format_cell_range(ws, "A3", H2)
format_cell_range(ws, "A8:C8", TH)
format_cell_range(ws, "A14", H2)
format_cell_range(ws, "A19", H2)
format_cell_range(ws, "A21:C21", TH)
format_cell_range(ws, "A27:A28", NOTE)
set_column_widths(ws, [("A", 220), ("B", 460), ("C", 220)])
p()

# ================================================================
# Sheet 2: 各アプリの詳細
# ================================================================
ws2 = sh.add_worksheet("アプリ詳細", rows=60, cols=4)
p()

data2 = [
    ["各アプリの詳細"],
    [""],
    # ── KAGE ──
    ["■ KAGE（影秘書）v0.302"],
    [""],
    ["項目", "内容"],
    ["何ができる？", "チャットで話しかけると、予定登録・タスク管理・アイデア記録・朝のブリーフィングなどを自動で行う"],
    ["AIエンジン", "Google Gemini 2.5 Pro"],
    ["データ保存先", "Notion（スケジュール・タスク・アイデア等 9つのデータベース）"],
    ["本番URL", "https://notion-secretary-api-production.up.railway.app/app"],
    ["サーバー", "Railway（インターネット上で24時間稼働）"],
    ["最新の改善", "ウェルカム画面の簡素化 / タスク整理の精度UP / 一般知識への回答強化"],
    ["バグ修正済み", "11件（v0.300〜v0.302の3回のアップデートで対応）"],
    ["残りの課題", "9件（夜間フロー・Notionデータ範囲拡張など）"],
    [""],
    # ── VANTAN ──
    ["■ VANTAN 動画生成（Video Studio v1.2）"],
    [""],
    ["項目", "内容"],
    ["何ができる？", "学校広告のVlog風動画を 6ステップで自動生成する"],
    ["6ステップ", "① 台本生成（AI）→ ② 静止画チェック（人間） → ③ 動画生成（AI）→ ④ ナレーション（AI）→ ⑤ SE/BGM → ⑥ 合成"],
    ["使っているAI", "台本: Gemini / 静止画: Imagen 4 / 動画: Veo3 / ナレーション: ElevenLabs / 合成: Creatomate"],
    ["現在の案件", "workflow_002: スクール別親子広告（16パターン）"],
    ["進捗", "完了12本 / 再生成1本 / 途中2本 / 未着手1本"],
    ["操作画面", "localhost:8888（自分のPCでのみ操作）"],
    ["台本管理", "Google スプレッドシート（絵コンテとして管理）"],
    [""],
    # ── RAG ──
    ["■ RAG（画像QCギャラリー）v1.0"],
    [""],
    ["項目", "内容"],
    ["何ができる？", "広告バナーをAIで生成し、品質チェック → デザイナー納品用にエクスポート"],
    ["使っているAI", "画像生成: fal.ai Flux Pro / プロンプト翻訳: Gemini"],
    ["現在の案件", "C003: PRIME向け20件"],
    ["操作画面", "localhost:8000（自分のPCでのみ操作）"],
    [""],
    # ── CCM ──
    ["■ CCM（Claude Code Mobile）v1.0"],
    [""],
    ["項目", "内容"],
    ["何ができる？", "iPhoneからClaude Codeを遠隔操作する（ダッシュボード確認・生成開始・チャット）"],
    ["仕組み", "PCでサーバーを起動 → iPhoneのブラウザからアクセス"],
    ["接続方法", "Tailscale VPN経由（セキュア）"],
]

ws2.update("A1", data2, value_input_option="RAW")
p()
format_cell_range(ws2, "A1", H1)
for r in [3, 15, 26, 33]:
    format_cell_range(ws2, f"A{r}", H2)
for r in [5, 17, 28, 35]:
    format_cell_range(ws2, f"A{r}:B{r}", TH)
set_column_widths(ws2, [("A", 160), ("B", 560)])
p()

# ================================================================
# Sheet 3: 環境の仕組み（ボス向け解説）
# ================================================================
ws3 = sh.add_worksheet("環境の仕組み", rows=50, cols=3)
p()

data3 = [
    ["環境の仕組み（非エンジニア向け解説）"],
    [""],
    ["■ 登場するもの"],
    [""],
    ["名前", "役割", "たとえるなら"],
    ["自分のPC（ローカル）", "プログラムを書いて、動かす場所。生成した動画や画像もここに保存される", "自分のデスク"],
    ["GitHub", "コードのバックアップ先。変更履歴が全部残る。いつでも過去に戻れる", "共有ファイルサーバー（履歴付き）"],
    ["Railway", "KAGEだけが動いている外部サーバー。インターネットからアクセスできる", "レンタルオフィス"],
    ["Dropbox", "生成した動画・音源ファイルを自動同期", "ファイル共有の引き出し"],
    ["Google Sheets", "台本や絵コンテの管理、このサマリもここ", "企画書・進捗表"],
    ["Notion", "KAGEのデータ保存先（スケジュール、タスク、メモ等）", "秘書の手帳"],
    [""],
    ["■ コードの流れ（Git / GitHub）"],
    [""],
    ["「Git」は、プログラムの変更を記録する仕組みです。"],
    ["Wordの「変更履歴」のプログラム版だと思ってください。"],
    [""],
    ["用語", "意味"],
    ["コミット", "「セーブポイントを作る」こと。いつでもこの時点に戻れる"],
    ["プッシュ（push）", "ローカルの変更をGitHubにアップロードすること"],
    ["プル（pull）", "GitHubの最新をローカルにダウンロードすること"],
    ["ブランチ", "コードの「別バージョン」。本流（main）を壊さずに試せる"],
    [""],
    ["つまり："],
    ["  PC上でコードを書く → コミット（保存）→ push（GitHubに送る）"],
    ["  という流れで開発が進みます。"],
    [""],
    ["■ 動画生成の流れ（VANTANの場合）"],
    [""],
    ["ステップ", "やること", "誰が"],
    ["① 台本を書く", "AIがスプシに台本（カット割り・セリフ・映像指示）を自動生成", "AI（Gemini）"],
    ["② 静止画で確認", "映像プロンプトから静止画を作り、方向性を人間がチェック", "AI + 人間"],
    ["③ 動画を作る", "OKが出た映像指示で動画を1カットずつ生成（1本4秒）", "AI（Veo3）"],
    ["④ ナレーション", "台本のセリフから音声を自動生成", "AI（ElevenLabs）"],
    ["⑤ SE/BGM", "効果音・BGMをローカルの音源ライブラリから選択", "自動選択"],
    ["⑥ 合成", "動画+音声+テロップ+ロゴを1本の動画にまとめる", "AI（Creatomate）"],
    [""],
    ["ポイント：いきなり動画を作ると時間もコストもかかるので、"],
    ["まず②の静止画で方向性を確認してから動画化します。"],
    [""],
    ["■ ファイルの管理ルール"],
    [""],
    ["種類", "保存場所", "バックアップ"],
    ["コード（プログラム）", "PC → GitHub", "GitHub に履歴付きで保存される"],
    ["APIキー（パスワード類）", "PC上の .env ファイルのみ", "GitHubには絶対に上げない"],
    ["生成した動画・画像", "PC上の output/ フォルダ", "Dropboxが自動同期"],
    ["SE/BGM音源", "PC上の clients/ フォルダ", "Dropboxが自動同期"],
    ["台本・絵コンテ", "Google スプレッドシート", "Google が自動バックアップ"],
    ["KAGEのデータ", "Notion", "Notion が自動バックアップ"],
]

ws3.update("A1", data3, value_input_option="RAW")
p()
format_cell_range(ws3, "A1", H1)
for r in [3, 13, 27, 39]:
    format_cell_range(ws3, f"A{r}", H2)
for r in [5, 18, 29, 41]:
    format_cell_range(ws3, f"A{r}:C{r}", TH)
format_cell_range(ws3, "A15:A16", NOTE)
format_cell_range(ws3, "A23:A24", NOTE)
format_cell_range(ws3, "A36:A37", NOTE)
set_column_widths(ws3, [("A", 220), ("B", 420), ("C", 200)])
p()

# ================================================================
# Sheet 4: 進捗・ステータス
# ================================================================
ws4 = sh.add_worksheet("進捗", rows=35, cols=4)
p()

data4 = [
    ["プロジェクト進捗（2026-03-25 時点）"],
    [""],
    ["■ アプリ別ステータス"],
    [""],
    ["アプリ", "バージョン", "ステータス", "次にやること"],
    ["KAGE", "v0.302", "✅ 本番稼働中", "グローバルナビ化、セッション記憶強化"],
    ["VANTAN 動画", "workflow_002", "🔄 制作中（75%）", "残4パターンの動画生成・合成"],
    ["RAG 画像QC", "v1.0", "🔄 C003進行中", "PRIME向け20件の画像生成・レビュー"],
    ["CCM", "v1.0", "✅ 動作OK", "必要に応じて機能追加"],
    [""],
    ["■ KAGE バグ修正の状況"],
    [""],
    ["ステータス", "件数", "主な内容"],
    ["✅ 修正済み", "11件", "UI文字切れ、レスポンス遅延、分類精度、一般知識対応 等"],
    ["🔄 対応中", "4件", "グローバルナビ、睡眠データ、Notionデータ範囲 等"],
    ["⏳ 未対応", "9件", "夜間フロー、影部隊構想、データ同期改善 等"],
    [""],
    ["■ VANTAN 動画 パターン別進捗"],
    [""],
    ["パターン", "動画", "合成", "ステータス"],
    ["no01", "10/11カット", "❌", "カット#02 動画欠け → Veo3クォータ回復待ち"],
    ["no02〜03", "11/11", "✅", "完了（再生成してクオリティチェック予定）"],
    ["no04", "0/11", "❌", "未着手"],
    ["no05〜14", "11/11", "✅", "完了（10パターン）"],
    ["no15", "10/11", "❌", "あと1カット"],
    ["no16", "4/11", "❌", "あと7カット"],
]

ws4.update("A1", data4, value_input_option="RAW")
p()
format_cell_range(ws4, "A1", H1)
for r in [3, 11, 18]:
    format_cell_range(ws4, f"A{r}", H2)
for r in [5, 13, 20]:
    format_cell_range(ws4, f"A{r}:D{r}", TH)
# ステータス色分け
format_cell_range(ws4, "C6", DONE)
format_cell_range(ws4, "C7", WIP)
format_cell_range(ws4, "C8", WIP)
format_cell_range(ws4, "C9", DONE)
set_column_widths(ws4, [("A", 150), ("B", 140), ("C", 140), ("D", 340)])
p()

# ================================================================
# Sheet 5: 用語集
# ================================================================
ws5 = sh.add_worksheet("用語集", rows=30, cols=2)
p()

data5 = [
    ["用語集（このプロジェクトでよく出てくる言葉）"],
    [""],
    ["用語", "意味"],
    ["kage-lab", "このプロジェクト全体の名前。4つのアプリが入った「ツール箱」"],
    ["KAGE（影秘書）", "AI秘書チャットアプリ。Notionに予定やタスクを自動保存する"],
    ["VANTAN", "バンタンの学校広告。Vlog風動画を自動生成するプロジェクト"],
    ["RAG", "リクルートエージェント広告。バナー画像をAI生成→品質チェックするツール"],
    ["CCM", "Claude Code Mobile。iPhoneからPCのAIツールを遠隔操作するアプリ"],
    [""],
    ["Git", "プログラムの変更履歴を記録する仕組み（Wordの変更履歴のプログラム版）"],
    ["GitHub", "Gitの記録をインターネット上にバックアップする場所（Googleドライブ的存在）"],
    ["コミット", "プログラムの変更を記録すること（＝セーブポイントを作る）"],
    ["プッシュ (push)", "ローカルの変更をGitHubにアップロードすること"],
    ["プル (pull)", "GitHubの最新版をローカルにダウンロードすること"],
    ["デプロイ", "プログラムをサーバーに設置して、ネットから使えるようにすること"],
    ["ローカル", "自分のPC上のこと（インターネットに公開されていない）"],
    [""],
    ["Railway", "KAGEを動かしている外部サーバー（月額課金制）"],
    ["Notion", "メモ・データベースアプリ。KAGEのデータ保存先"],
    ["Gemini", "Googleの AI。台本作成、要約、チャット応答に使用"],
    ["Veo3", "GoogleのAI動画生成。4秒の動画を1カットずつ作る"],
    ["ElevenLabs", "AI音声合成。ナレーションの自動読み上げに使用"],
    ["Creatomate", "動画合成サービス。映像+音声+テロップ+ロゴを1本にまとめる"],
    ["Imagen 4", "GoogleのAI画像生成。動画前の静止画チェックに使用"],
    ["Flux Pro", "画像生成AI。RAG（広告バナー）の生成に使用"],
    ["Claude Code", "Anthropic社のAIプログラミングツール。このプロジェクトの開発パートナー"],
    ["API", "アプリ同士がデータをやり取りするための窓口（人間は意識しなくてOK）"],
    ["スプシ", "Google スプレッドシートの略称"],
]

ws5.update("A1", data5, value_input_option="RAW")
p()
format_cell_range(ws5, "A1", H1)
format_cell_range(ws5, "A3:B3", TH)
set_column_widths(ws5, [("A", 180), ("B", 540)])
set_frozen(ws5, rows=3)
p()

print()
print("🎉 完了！ 5シート作成しました:")
print("   1. 全体像 — プロジェクトの概要と4アプリの紹介")
print("   2. アプリ詳細 — KAGE / VANTAN / RAG / CCM の詳細")
print("   3. 環境の仕組み — Git・ファイル管理の非エンジニア向け解説")
print("   4. 進捗 — ステータス・バグ修正状況・VANTAN パターン別進捗")
print("   5. 用語集 — プロジェクトで出てくる用語の辞書")
print()
print(f"📎 URL: https://docs.google.com/spreadsheets/d/{sh.id}/")
