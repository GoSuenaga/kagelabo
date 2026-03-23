# VANTAN Vlog広告動画 生成パッケージ
# 2026-03-23

## 概要

バンタン（VANTAN）専門部向けのVlog風広告動画を自動生成するための完全なパッケージ。
このパッケージの内容をClaude Codeに渡せば、同じ動画を再現できる。

## 生成結果

全20パターン × 11カット = 220カットの動画 + 20本の完成動画を生成。

| No | スクール | コース | 完成動画 |
|----|---------|--------|---------|
| 1 | バンタン外語＆ホテル観光学院 | 語学（英語・韓国語） | 7020KB |
| 2 | バンタン外語＆ホテル観光学院 | ホテル・観光 | 6793KB |
| 3 | バンタン外語＆ホテル観光学院 | エアライン（航空・CA） | 6298KB |
| 4 | バンタン外語＆ホテル観光学院 | サービス・ホスピタリティ | 6223KB |
| 5 | バンタン外語＆ホテル観光学院 | 留学・ワーキングホリデー | 6062KB |
| 6 | バンタン外語＆ホテル観光学院 | 外資・海外就職 | 6240KB |
| 7 | バンタンデザイン研究所 | グラフィック・WEB | 5717KB |
| 8 | バンタンデザイン研究所 | イラスト | 4639KB |
| 9 | バンタンデザイン研究所 | フォト・写真 | 5820KB |
| 10 | バンタンデザイン研究所 | 映像・映画制作 | 5386KB |
| 11 | バンタンデザイン研究所 | 音楽・DTM | 5404KB |
| 12 | バンタンデザイン研究所 | スケートボード＆デザイン | 5467KB |
| 13 | バンタンゲームアカデミー | ゲーム企画 | 4877KB |
| 14 | バンタンゲームアカデミー | ゲームCG・3DCG | 5905KB |
| 15 | バンタンゲームアカデミー | eスポーツ | 4375KB |
| 16 | バンタンゲームアカデミー | イラスト・キャラクター | 5931KB |
| 17 | バンタンゲームアカデミー | アニメ制作 | 5837KB |
| 18 | バンタンゲームアカデミー | CG・VFX | 5196KB |
| 19 | バンタンゲームアカデミー | DTM・サウンド | 5340KB |
| 20 | バンタンゲームアカデミー | 謎解きクリエイター | 5896KB |

## パッケージ内容

```
packages/20260323_vantan_v1/
├── README.md                    ← このファイル
├── spreadsheet_blueprint.md     ← 完全な設計図（v1.7）
├── generate_all.py              ← 全パターン一括生成スクリプト
├── vlog_prompt_bible.md         ← Vlogスタイルの設計思想・テンプレート集
├── update_client_master.py      ← クライアントマスター更新スクリプト
├── .env.example                 ← APIキー設定テンプレート
└── prompt_rules.md              ← プロンプト作成ルール（学んだこと全集）
```

## 再現手順

### 前提条件
- Python 3.x
- 以下のAPIキーが`.env`に設定されていること:
  - GEMINI_API_KEY（Google AI Studio）
  - FAL_API_KEY（fal.ai — Veo3, ElevenLabs）
  - CREATOMATE_API_KEY（動画合成）
- Google OAuth認証（oauth_credentials.json + token.json）
- pipパッケージ: gspread, google-genai, openpyxl, requests, python-dotenv

### 手順

1. **クライアント情報の準備**
   ```
   clients/vantan/ にExcelファイルとロゴ画像を配置
   clients/vantan/se/ にSE（効果音）ファイルを配置
   ```

2. **台本スプレッドシートの生成**
   - 元データ（スクール×コース一覧）をGoogle Sheetsに用意
   - `spreadsheet_blueprint.md` の設計に従ってスプレッドシートを自動生成
   - 4シート構成: 台本 / スタイル / クライアント情報 / プロンプト（設計図）

3. **動画一括生成**
   ```
   python3 generate_all.py
   ```
   - 各パターンの処理: 動画生成（Veo3標準版）→ ナレーション（ElevenLabs）→ SE選択 → 合成（Creatomate）
   - 出力: output/no01/final.mp4 〜 output/no20/final.mp4

## 動画生成フロー

```
台本テンプレート × クライアント情報
    ↓ スプレッドシート自動生成（4シート構成）
映像プロンプト（EN）
    ↓ Veo3標準版で動画生成（4秒、9:16、720p、1カットずつ順番に）
ナレーションテキスト
    ↓ ElevenLabs（fal.ai経由）で音声生成
SE（効果音）
    ↓ ローカルからランダム選択（冒頭/商材名/他スクリプト）
Creatomateで合成
    ↓ 動画 + 音声 + テロップ（中央） + ロゴ + SE → 1本の完成動画
```

## 使用API・モデル

| 用途 | サービス | モデル/エンドポイント |
|------|---------|---------------------|
| 動画生成 | fal.ai | fal-ai/veo3（標準版） |
| ナレーション | fal.ai | fal-ai/elevenlabs/tts/eleven-v3 |
| 動画合成 | Creatomate | POST /v1/renders |
| ファイルアップロード | fal.ai | rest.alpha.fal.ai/storage/upload/initiate |
| スプレッドシート | Google Sheets API | gspread (OAuth) |

## プロンプトルール（重要）

1. 実物がないもの（校舎外観等）は指定しない
2. 文字情報が映り込むプロンプトは避ける
3. 人物を出す場合は必ず「Japanese」と明記
4. 全カットに必ず動きの指示を入れる
5. ロゴ表示カットの動画プロンプトにロゴ指示を入れない（「No text, no logos, no signage」を入れる）
6. 手指のクローズアップは避ける（指の破綻リスク）

## ナレーションテンプレート

```
{コース}の専門校って/お金がかかりそうって思ってたけど、/貯金がなくても大丈夫だった！/通いたいのは/{スクール名称}っていうところで…（バナー表示{ロゴ}）/働きながら学べる/バイトや仕事もできるから/学費の心配は/一切なし！/これめっちゃ嬉しい。/まずは資料請求してみて下さい！
```

適用条件: 専門部のみ（働きながら学べるのは専門部だけ）

## スプレッドシート

- 元データ: https://docs.google.com/spreadsheets/d/1wtF5EQEh4uZYgt5osm0F-xwUyl1A4YzZdneneFlhgCk
- 台本（v1.6）: https://docs.google.com/spreadsheets/d/1yyvxMYsaChW1nnnua1owfRuk673keHkoK3zvVVnIDKQ
- クライアントマスター: https://docs.google.com/spreadsheets/d/1m6zqCVjAUaAT0LF09K9dMhBbVmyQkah1fTK9gnPooaE

## 生成日時
2026-03-23
