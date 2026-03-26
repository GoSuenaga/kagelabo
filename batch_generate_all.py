#!/usr/bin/env python3
"""
VANTAN 全16パターン一括生成スクリプト
動画(Veo3.1) → ナレーション(ElevenLabs) → 合成(Creatomate) を一気通貫で実行

使い方:
  python3 batch_generate_all.py           # 全パターン実行
  python3 batch_generate_all.py no04      # 特定パターンだけ
  python3 batch_generate_all.py no01 no15 # 複数指定
"""

import sys
import os
import json
import time
from datetime import datetime

# control_panel_server.py と同じディレクトリで実行する前提
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))
load_dotenv(os.path.join(ROOT, "apps", "vantan-video", ".env"))

# control_panel_server のモジュールを直接インポート
import control_panel_server as cps

def main():
    # カートリッジ確認
    cid = cps.get_active_cid()
    if not cid:
        print("ERROR: アクティブカートリッジがありません")
        print("  → python3 control_panel_server.py を起動して XLSX をインポートしてください")
        sys.exit(1)

    meta = cps.load_meta()
    patterns = cps.PATTERNS
    print(f"=== VANTAN バッチ生成 ===")
    print(f"カートリッジ: {cid} ({meta.get('loaded_file', '?')})")
    print(f"全パターン数: {len(patterns)}")
    print(f"出力先: {cps.get_output_base()}")
    print()

    # 対象パターンの決定
    if len(sys.argv) > 1:
        targets = sys.argv[1:]
    else:
        targets = sorted(patterns.keys())

    # 既に完了しているものをスキップするか確認
    state = cps.load_state()
    skip_done = True
    completed = []
    pending = []
    for pat_key in targets:
        if pat_key not in patterns:
            print(f"WARNING: {pat_key} はカートリッジに存在しません。スキップ。")
            continue
        pat_state = state.get(pat_key, {})
        out_dir = os.path.join(cps.get_output_base(), pat_key)
        final_exists = os.path.exists(os.path.join(out_dir, "final.mp4"))
        if final_exists and skip_done:
            completed.append(pat_key)
        else:
            pending.append(pat_key)

    print(f"完了済み（スキップ）: {len(completed)} → {', '.join(completed) or 'なし'}")
    print(f"生成対象: {len(pending)} → {', '.join(pending) or 'なし'}")
    print()

    if not pending:
        print("すべてのパターンが完了済みです。")
        return

    # API キー確認
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "")
    creatomate_key = os.getenv("CREATOMATE_API_KEY", "")

    missing = []
    if not gemini_key: missing.append("GEMINI_API_KEY")
    if not elevenlabs_key: missing.append("ELEVENLABS_API_KEY")
    if not creatomate_key: missing.append("CREATOMATE_API_KEY")

    if missing:
        print(f"ERROR: 必要な API キーが未設定: {', '.join(missing)}")
        sys.exit(1)

    # ロゴファイル確認
    schools_in_target = set()
    for pat_key in pending:
        pat = patterns[pat_key]
        schools_in_target.add(pat["school"])

    print("ロゴ確認:")
    for school in sorted(schools_in_target):
        logo_rel = cps.LOGO_MAP.get(school, "")
        if logo_rel:
            logo_full = os.path.join(ROOT, logo_rel)
            status = "OK" if os.path.exists(logo_full) else "MISSING"
            print(f"  {status}: {school}")
        else:
            print(f"  WARNING: {school} のロゴがマップにありません")
    print()

    # 生成開始
    start_time = datetime.now()
    print(f"開始: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    results = {"success": [], "error": []}

    for i, pat_key in enumerate(pending):
        pat = patterns[pat_key]
        print(f"\n[{i+1}/{len(pending)}] {pat_key} ({pat['school']} / {pat.get('child', '')})")
        print(f"  カット数: {len(pat['cuts'])}")
        pat_start = datetime.now()

        try:
            # run_pipeline は同期実行（バックグラウンドスレッドではなく直接呼ぶ）
            cps.run_pipeline(pat_key, steps=["video", "narration", "compose"])

            # 結果確認
            pat_state = cps.load_state().get(pat_key, {})
            status = pat_state.get("status", "unknown")
            message = pat_state.get("message", "")
            elapsed = (datetime.now() - pat_start).total_seconds()

            if status == "done":
                print(f"  OK: {message} ({elapsed:.0f}秒)")
                results["success"].append(pat_key)
            else:
                print(f"  ERROR: [{status}] {message} ({elapsed:.0f}秒)")
                results["error"].append(pat_key)
                # クォータ超過なら全停止
                if "quota" in message.lower() or "429" in message:
                    print(f"\n  API クォータ超過。残りのパターンを中断します。")
                    break

        except Exception as e:
            print(f"  EXCEPTION: {e}")
            results["error"].append(pat_key)

    # 最終レポート
    total_time = (datetime.now() - start_time).total_seconds()
    print(f"\n{'='*60}")
    print(f"完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"所要時間: {total_time/60:.1f}分")
    print(f"成功: {len(results['success'])} → {', '.join(results['success']) or 'なし'}")
    print(f"失敗: {len(results['error'])} → {', '.join(results['error']) or 'なし'}")
    print(f"スキップ: {len(completed)} → {', '.join(completed) or 'なし'}")

    # 結果をファイルにも保存
    report_path = os.path.join(cps.get_output_base(), "batch_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "cartridge": cid,
            "total_time_min": round(total_time / 60, 1),
            "success": results["success"],
            "error": results["error"],
            "skipped": completed,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nレポート保存: {report_path}")


if __name__ == "__main__":
    main()
