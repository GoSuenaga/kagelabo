# VANTAN 動画パイプライン

Vlog 風広告の生成スクリプト・設定・CSV です。

## 実行の前提

- **作業ディレクトリはこのフォルダ**（相対パス・`.env` の `VLOG_CSV_PATH` が cwd 依存のため）。

```bash
cd apps/vantan-video
# .env はリポジトリルートまたはこのフォルダ（プロジェクト方針に合わせる）
python -m streamlit run vlog_app.py   # UI
python generate_wf002_no01_final.py   # 例: バッチ
```

## 依存関係

- `requirements-workspace-legacy.txt` … 旧ルートの最小依存（FastAPI 系）。**Streamlit・google-generativeai 等は別途 `pip install` が必要な場合があります**（`vlog_engine.py` の import を確認してください）。
- スプレッドシート連携・Dropbox 等はルートの `.env.example` を参照。

## 関連

- スナップショット一式: `packages/20260323_vantan_v1/`
- 生成物（mp4 等）: Git 管理外（ルート `.gitignore` の `output/`）
