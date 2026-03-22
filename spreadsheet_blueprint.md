# VANTAN 台本スプレッドシート — 完全設計図 v1.6

> このドキュメントをAI（Claude Code、Gemini等）に読み込ませることで、
> 4シート構成の台本スプレッドシートをゼロから再現できる。
> バックアップとしても機能する。

## バージョン履歴

- v1.6（2026-03-23）設計図を.mdファイルに外出し。Vlogカットにシーンテンプレートからのランダム選択を反映。カットタイプをVlog/Schoolの二択に統一（混合廃止）。
- v1.5 人物を「20歳の日本人女性」に具体化。カット1をSchoolに変更、コース別映像。
- v1.4 スタイルシートをvlog_prompt_bible.mdベースでフル更新。プロンプト注意事項3点。
- v1.3 ロゴ画像をローカルファイルパスに変更。
- v1.2 ロゴ表示列追加。バナー表示カットはテロップなし。
- v1.1 「僕が」削除。コース数20パターン。
- v1.0（2026-03-23）初版

---

## 1. 全体構成

### スプレッドシートは4シートで構成

| シート | 名前 | 役割 |
|--------|------|------|
| シート1 | 台本 | アウトプット。人間が確認・修正する |
| シート2 | スタイル | 映像ルール・演出の型の定義 |
| シート3 | クライアント情報 | スクール×コースのデータ + ロゴパス |
| シート4 | プロンプト（設計図） | このファイルへの参照リンク + バージョン情報 |

### 外部ファイル

| ファイル | 役割 |
|---------|------|
| `spreadsheet_blueprint.md`（このファイル） | 全体設計図の完全版 |
| `vlog_prompt_bible.md` | Vlogスタイルの設計思想・テンプレート集 |
| `vlogプロンプト - シート1.csv` | Vlogカット用プロンプトのストック（92個、16カテゴリ） |
| `clients/vantan/【バンタン_CA極案件】各スクール訴求内容 (2).xlsx` | クライアント元データ |
| `clients/vantan/2026/` | ロゴ画像のローカル格納先 |

---

## 2. シート1「台本」— カラム定義

| カラム | 説明 |
|--------|------|
| No | パターン番号（1スクール×1コース = 1パターン） |
| スクール名称 | スクール名（パターンの最初の行にのみ記載） |
| コース | コース名（同上） |
| カット# | 連番（1〜11） |
| カットタイプ | **Vlog** または **School** の二択（混合は使わない） |
| ナレーション | 読み上げテキスト。「（バナー表示{ロゴ}）」等の演出指示は除去済み |
| テロップ | 画面に表示する字幕。ロゴ表示カットでは空欄 |
| ロゴ表示 | ○ がついたカットはロゴ画像を画面中央にオーバーレイ。テロップは出さない |
| ロゴファイルパス | ローカルのロゴ画像ファイルパス |
| 映像プロンプト（日本語） | 人間が確認・修正する列。自然言語の文章で記述 |
| 映像プロンプト（EN） | Imagen 3 / Veoに渡す用。末尾にカメラワーク定型句を含む |

### 運用フロー

1. テンプレート × クライアント情報で全パターン自動生成
2. 人間がシート1で台本を確認・修正（映像プロンプト日本語を編集）
3. 修正した日本語から映像プロンプト（EN）を再生成
4. ENプロンプトでImagen 3により各カットの静止画を生成 → 画像チェック
5. OKならVeoで動画化 → ナレーション・テロップ統合 → 最終確認

---

## 3. シート2「スタイル」— Vlog風スタイル定義

### 3.1 コンセプト

**「作りこまない、でも美しい」**
偶然撮れた美しい瞬間の人工的な再現。広告でありながら広告に見えない。

### 3.2 三つの絶対原則

1. **iPhone 13 Aesthetic** — すべてのカットは「iPhone 13で撮ったように見える」こと。スマホ特有のわずかな歪み・自然光・手持ちの揺れ
2. **Face Not Shown** — 人物の顔は原則映さない。手元・後ろ姿・横顔の一部。視聴者が自分を投影できる余白
3. **Micro-movements** — 完全な静止NG。カメラも被写体も常にわずかに動いている

### 3.3 プロンプト構造フレームワーク

```
[ショットタイプ] + [顔の可視性] + [シーン/ロケーション] + [被写体] + [服装] + [アクション] + [カメラワーク] + [質感ルール]
```

### 3.4 ショットタイプ一覧

| タイプ | 用途 | 例 |
|--------|------|-----|
| Close-up shot | 手元・ディテール強調 | ネイル、料理、デバイス操作 |
| Medium shot | 上半身〜膝上、動作全体 | ヨガ、作業、食事 |
| Medium shot from behind | 後ろ姿、世界観提示 | 歩行、窓辺、橋の上 |
| Over the shoulder shot | 視聴者の目線に近い没入感 | 風景を眺める、手元作業 |
| Wide shot | 環境全体、ライフスタイル提示 | 部屋、街並み |
| Top-down shot | 俯瞰、フラットレイ的 | 料理、手帳、デスク |
| Extreme close-up | 質感・テクスチャ重視 | 肌、生地、食材の断面 |
| POV shot | 一人称視点 | 車窓、飛行機窓、歩行 |
| Full shot | 全身（ただし顔は隠す） | OOTD、部屋でのルーティン |
| Dutch angle shot | 傾いた構図で動的な印象 | 街歩き、移動中 |

### 3.5 顔の可視性ルール

- `face is not shown` — 顔完全非表示（デフォルト）
- `face is barely shown` — 横顔の一部、ぼかし越しなど
- `face mostly covered by phone` — 鏡自撮り専用

### 3.6 カメラワーク定型句（EN・全カット末尾に必須）

```
The camera has subtle micro-movements.
The camera work is slightly shaky, as if shot on a handheld smartphone.
[Camera Logic] The shot looks raw and unfiltered as if shot on an iPhone 13.
Natural lighting, authentic social media aesthetic.
```

### 3.7 カットタイプ定義

**Vlogカット**
- 目的: 日常感・共感・空気感を作る
- 内容: 鏡自撮り、食事、風景、電車、カフェバイト、ペットなど
- プロンプト: `vlog_prompt_bible.md` のシーンテンプレートからランダムに選択
- スクール固有の要素は入れない

**Schoolカット**
- 目的: スクールの訴求・情報伝達
- 内容: コースを連想させるシーン（ペンタブ、ゲームコントローラー等）
- 映像の質感はVlogカットと同じ（iPhone 13, 手ブレ, 自然光）

**混合は使わない。各カットはVlogかSchoolのどちらかに明確に分類する。**

### 3.8 Vlogカット用シーンテンプレート

Vlogカットの映像プロンプトは、以下のカテゴリからランダムに選択する。
同じカテゴリが連続しないように配慮する。

#### 鏡自撮り（OOTD）
```
video of an "Outfit of the Day" (OOTD). The shot is a stable, first-person
mirror selfie taken on a smartphone in the bright, naturally lit entryway
of a modern apartment. A 20-year-old Japanese woman with long brown hair,
with her face mostly covered by her phone, showcases a stylish outfit
by making small, subtle movements like shifting her weight and turning slightly.
She has great posture. [服装の詳細]
The camera has subtle micro-movements. The camera work is slightly shaky.
The camera work looks raw, unfiltered as if shot on an iPhone 13.
don't carry a bag.
```
服装バリエーション（9種）:
1. Cropped hoodie in pastel/muted tone, parachute pants, ribbed knit beanie + layered necklaces
2. Boxy blazer in olive green, wide-leg trousers + low sleek bun, minimalist silver necklace
3. Fitted white baby tee, high-waisted charcoal trousers + thin gold chain, ear cuffs
4. Oversized cable-knit cardigan, pleated midi skirt, chunky ankle boots + beret
5. Camel-tone trench coat, cream turtleneck, straight-leg dark denim + gold hoop earrings
6. Puffer vest over a hoodie, cargo joggers, trail sneakers + beanie
7. Linen blend wide-leg pants, basic tank top tucked in, woven mule sandals + stacked bracelets
8. Structured cropped denim jacket, matching straight-leg jeans, vintage band tee + tortoiseshell sunglasses
9. Flowy satin midi skirt, fitted ribbed top, strappy block heels, sleek center-part hair

#### 人物の動き
```
[ショットタイプ], face is not shown.
The scene is set in [ロケーション].
The subject is a 20-year-old Japanese woman with long brown hair.
The subject is wearing [服装].
Action: [具体的な動作].
[カメラワーク定型句]
```
動きバリエーション:
| 動作 | ロケーション |
|------|------------|
| ヨガストレッチ、ラグの上で座る | リビング、窓辺 |
| 手すりに手を置く、ネイルを見せる | 橋の上、レストラン |
| 運河を眺める、容器に触れる | 歩道橋、カフェ |
| ブランケットに包まる、腕を組む | ソファ、部屋 |
| 買い物袋を持つ | 街中 |
| ベッドメイキング、パジャマで伸び | 寝室、自宅 |
| お茶を入れる | キッチン |

#### 食事
```
A static, high-angle, top-down POV shot of a [場所] moment,
face is not shown, captured on a smartphone.
The scene is set in [キッチン/レストランの描写].
[調理動作や料理の描写]
[カメラワーク定型句]
```
バリエーション: フライパンで卵を焼く / カフェのラテアート / お茶を淹れる / 盛り付けの俯瞰

#### 風景（車窓/POV）
```
A POV shot from the back seat of a moving train.
The camera is positioned low, capturing the view outside the side window
as the train moves through [風景の描写].
The mood is [雰囲気].
The shot is stable but has subtle organic motion from the movement of the train.
Natural lighting, the aesthetic is raw and unfiltered, as if shot on a smartphone.
```

#### 風景（街スナップ）
```
An authentic, unpolished, raw and unfiltered as if shot on a smartphone.
The scene is shot by a person standing on [場所].
[風景の詳細].
[カメラワーク定型句]
```

#### ペット
```
Medium shot, face is not shown.
The scene is set in [生活空間].
A small grey cat [動作] on a soft rug.
[カメラワーク定型句]
```

### 3.9 プロンプト注意事項（重要）

1. **実物がないものは指定しない** — 校舎外観など、実際の素材がないユニークなものを指定しない。広告として正確性が大事
2. **文字情報が映り込むプロンプトは避ける** — 看板、画面のテキスト、書類の文字など。AIが変な文字を生成しやすいため
3. **人物を出す場合は必ず「Japanese」と明記** — 入れないと外国人が生成されやすい

### 3.10 やること / やらないこと

**やること:**
- 自然光を使う（Natural lighting）
- 手ブレ感を維持する（slightly shaky）
- 生活感のある小道具を画面に入れる（コーヒーカップ、観葉植物、ラグ）
- 服装のディテールを具体的に書く（色、素材、スタイル）
- 各カットに固有のアクションを1つ持たせる

**やらないこと:**
- 顔を正面から映さない
- 三脚固定のような安定しすぎた映像
- 過度なカラーグレーディング（Rawであること）
- バッグを持たせない（鏡自撮り時）
- 映画的なライティング（Ring light, studio lighting 等は禁止）
- 校舎外観など実物がない固有物の指定
- 文字・テキストが映り込む描写
- 「Japanese」なしで人物を指定

### 3.11 服装バリエーション

春夏:
- Cropped hoodie in pastel tone, parachute pants, ribbed knit beanie + layered necklaces
- Fitted white baby tee, high-waisted charcoal trousers + thin gold chain, ear cuffs
- Linen blend wide-leg pants, basic tank top tucked in, woven mule sandals + stacked bracelets

秋冬:
- Oversized cable-knit cardigan, pleated midi skirt, chunky ankle boots + beret
- Camel-tone trench coat, cream turtleneck, straight-leg dark denim + gold hoop earrings
- Puffer vest over a hoodie, cargo joggers, trail sneakers + beanie

### 3.12 Veo 3 技術パラメータ

| パラメータ | 値 | 理由 |
|-----------|-----|------|
| aspect_ratio | 9:16 | 縦型ショート動画 |
| duration | 6s | 1カット6秒 |
| resolution | 720p | SNS配信に十分 |
| generate_audio | false | 音声は別途ElevenLabsで生成 |
| プロンプト言語 | 英語のみ | Veo 3は英語プロンプトのみ対応 |

---

## 4. シート3「クライアント情報」— データソース

### カラム定義

| カラム | 説明 |
|--------|------|
| スクール名称 | スクール名 |
| コース | コース名 |
| ロゴファイルパス | ローカルのロゴ画像パス（`clients/vantan/2026/{コード}/専門部/`） |
| ナレーション | テンプレート展開済みのナレーション全文 |

### データソース
- 元データ: `clients/vantan/【バンタン_CA極案件】各スクール訴求内容 (2).xlsx`
- ユーザーが整理したデータ: https://docs.google.com/spreadsheets/d/1wtF5EQEh4uZYgt5osm0F-xwUyl1A4YzZdneneFlhgCk

### 対象
- 部: 専門部（01_専門部）のみ
- ターゲット: 本人向けのみ
- デモグラ: 16歳〜24歳 男女 → 映像上の人物は **20歳の日本人女性** で統一

---

## 5. ナレーションテンプレート

### 現在のテンプレート（働きながら学べる訴求）

```
{コース}の専門校って/お金がかかりそうって思ってたけど、/貯金がなくても大丈夫だった！/通いたいのは/{スクール名称}っていうところで…（バナー表示{ロゴ}）/働きながら学べる/バイトや仕事もできるから/学費の心配は/一切なし！/これめっちゃ嬉しい。/まずは資料請求してみて下さい！
```

### 変数
- `{コース}`: シート3のコース列から取得
- `{スクール名称}`: シート3のスクール名称列から取得
- `{ロゴ}`: スクール名称と同じ（バナー表示用）

### 適用条件
- 専門部のみ（働きながら学べるのは専門部だけ）

### ロゴ表示ルール
- `（バナー表示{ロゴ}）` が含まれるカットでロゴを画面中央にオーバーレイ
- そのカットのテロップは出さない（ロゴのみ）
- ナレーションは通常通り読み上げる

---

## 6. カット×カットタイプの割り当て

このテンプレートの11カットに対するカットタイプの割り当て:

| カット# | ナレーション概要 | カットタイプ | 映像の方針 |
|---------|----------------|------------|-----------|
| 1 | {コース}の専門校って | **School** | コースを連想させる映像（コース別に個別設定） |
| 2 | お金がかかりそうって思ってたけど | **Vlog** | シーンテンプレートからランダム選択 |
| 3 | 貯金がなくても大丈夫だった！ | **Vlog** | シーンテンプレートからランダム選択 |
| 4 | 通いたいのは | **School** | スマホ操作の手元 |
| 5 | {スクール名称}っていうところで… | **School** | 明るいモダン空間 + ロゴオーバーレイ |
| 6 | 働きながら学べる | **Vlog** | シーンテンプレートからランダム選択（カフェバイト等） |
| 7 | バイトや仕事もできるから | **Vlog** | シーンテンプレートからランダム選択 |
| 8 | 学費の心配は | **School** | 安心した雰囲気の手元 |
| 9 | 一切なし！ | **School** | ジェスチャー（後ろ姿） |
| 10 | これめっちゃ嬉しい。 | **Vlog** | シーンテンプレートからランダム選択（ガッツポーズ等） |
| 11 | まずは資料請求してみて下さい！ | **School** | スマホ操作の手元 |

Vlogカット（2,3,6,7,10）は `vlog_prompt_bible.md` のシーンテンプレートから以下のカテゴリをランダムに選択:
- 鏡自撮り（OOTD）
- 人物の動き（7バリエーション）
- 食事
- 風景（車窓/街スナップ）
- ペット

同じカテゴリが連続しないように配慮する。

---

## 7. Schoolカット — コース別カット1映像プロンプト

カット1はSchoolカットで、コースを連想させる映像を使う。
全コース個別に設定:

| コース | 映像（日本語） |
|--------|-------------|
| 語学（英語・韓国語） | 語学のテキストブックを開きペンでメモを取っている手元 |
| ホテル・観光 | おしゃれな空間でパンフレットをめくっている手元 |
| エアライン（航空・CA） | きちんとしたブラウス姿で旅行カバンの取っ手に手を添えている |
| サービス・ホスピタリティ | きれいにセットされたテーブルのナプキンを整えている手元 |
| 留学・ワーキングホリデー | パスポートと地図を持っている手元 |
| 外資・海外就職 | ノートパソコンでスマートに作業している手元 |
| グラフィック・WEB | ペンタブレットでデザイン作業をしている手元 |
| イラスト | スケッチブックにイラストを描いている手元 |
| フォト・写真 | カメラを両手で持って構えている手元 |
| 映像・映画制作 | 小さなビデオカメラを手に持っている |
| 音楽・DTM | ヘッドフォンを首にかけMIDIキーボードに手を置いている |
| スケートボード＆デザイン | スケートボードのデッキを手に持って眺めている |
| ゲーム企画 | ゲームコントローラーを持っている手元 |
| ゲームCG・3DCG | ペンタブレットで3DCGモデリングをしている手元 |
| eスポーツ | ゲーミングキーボードとマウスに手を置いている |
| イラスト・キャラクター | 液晶タブレットでキャラクターイラストを描いている手元 |
| アニメ制作 | アニメの原画用紙に鉛筆で描いている手元 |
| CG・VFX | ペンタブレットでCG作業をしている手元 |
| DTM・サウンド | MIDIコントローラーのつまみを操作している手元 |
| 謎解きクリエイター | パズルピースやカードを並べノートにアイデアを書いている |

※全カットに共通: 「20歳の日本人女性」「顔は映らない」「自然光」「iPhone 13撮影の質感」

---

## 8. 技術実装メモ（Claude Code用）

### 必要環境
- Python 3.x
- gspread（Google Sheets API）
- openpyxl（Excel読み込み）
- oauth_credentials.json + token.json（Google OAuth認証）

### ファイル構成
```
├── spreadsheet_blueprint.md    ← このファイル（設計図）
├── vlog_prompt_bible.md        ← Vlogスタイルの設計思想
├── vlogプロンプト - シート1.csv  ← Vlogプロンプトストック（92個）
├── oauth_credentials.json      ← Google OAuth認証
├── token.json                  ← 認証トークン
├── update_client_master.py     ← クライアントマスター更新スクリプト
├── clients/vantan/
│   ├── 【バンタン_CA極案件】各スクール訴求内容 (2).xlsx
│   └── 2026/                   ← ロゴ画像
│       ├── VDI/専門部/
│       ├── VGA/専門部/
│       └── ...
```

### スプレッドシート生成の流れ
1. ユーザーが整理した元データ（Google Sheets）を読み込む
2. ナレーションテンプレートの変数を展開（{コース}, {スクール名称}, {ロゴ}）
3. 「僕が通いたいのは」→「通いたいのは」に修正
4. 各カットにカットタイプ（Vlog/School）を割り当て
5. Schoolカットはコース別の映像プロンプトを設定
6. Vlogカットは `vlog_prompt_bible.md` のシーンテンプレートからランダム選択
7. ロゴ情報を `clients/vantan/2026/` から紐づけ
8. 4シート構成のスプレッドシートを生成

### 元データ
- ユーザー整理版: https://docs.google.com/spreadsheets/d/1wtF5EQEh4uZYgt5osm0F-xwUyl1A4YzZdneneFlhgCk
- クライアントマスター: https://docs.google.com/spreadsheets/d/1m6zqCVjAUaAT0LF09K9dMhBbVmyQkah1fTK9gnPooaE
