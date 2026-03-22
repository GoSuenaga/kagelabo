# プロジェクト概要

VANTAN向けのVlog風広告動画を自動生成するシステム。
元々Difyで作っていたワークフローをPythonに移植中。

## 現在の進行状況（2026-03-18更新）

### 1. Vlog動画自動生成ツール（メイン作業）

**ファイル構成:**
- `vlog_engine.py` — ワークフローエンジン（Geminiスクリプト生成→fal Veo3動画生成→ElevenLabs音声→Creatomate合成）
- `vlog_app.py` — Streamlit UI（`streamlit run vlog_app.py` で起動）
- `vlog_prompt_bible.md` — プロンプト設計思想ドキュメント
- `vlogプロンプト - シート1.csv` — Vlog風プロンプトストック（92個、16カテゴリ）
- `.env` — APIキー設定（DRY_RUN=true で外部API呼ばずに動作テスト可能）

**前回やった修正:**
- Subject（"20代女性"等）→ 英語マッピング追加（Veo3は英語プロンプトのみ）
- `{{ }}` プレースホルダー置換バグ修正（人物属性だけ置換、服装等はそのまま展開）
- fal.run: 同期API → queue-based API（動画生成のタイムアウト対策）
- Creatomate: ポーリング対応（レンダリング完了まで待機）
- DRY_RUN モード追加（外部API不要でロジックテスト可能）
- APIキー未設定時の警告表示

**残タスク:**
- [ ] `streamlit run vlog_app.py` でドライラン起動テスト
- [ ] `.env` に GEMINI_API_KEY を設定（https://aistudio.google.com/apikey）
- [ ] 実APIでの通しテスト

### 2. QCギャラリーアプリ（サブ作業）

`qc-gallery-app/` にある広告クリエイティブのQCレビュー用Webアプリ。
- FastAPI + Gemini Imagen 3 で画像生成
- `qc-gallery-app/README.md` に起動手順あり

**残タスク:**
- [ ] `.env` に GEMINI_API_KEY 設定して起動テスト
- [ ] briefs.json を実案件データに差し替え

### 3. 旧Difyファイル（参考用、もう使わない）
- `vantan_fixed.yml`, `vantan_ad_workflow.yml` — 旧Difyワークフロー
- `run_vantan_workflow.gs`, `setup_vantan_spreadsheet.gs` — 旧GASスクリプト

## 再開手順

1. Cursorを開く
2. このファイル（CLAUDE.md）を開いた状態でチャットを始める
3. 「続きをやりたい」と言えばOK
