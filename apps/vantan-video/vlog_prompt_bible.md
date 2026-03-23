# Vlog風動画プロンプト バイブル

> このドキュメントは、Vlog風広告動画の「クリエイティブの核」を定義する。
> すべての動画生成プロンプトは、ここに記された原則・構造・テンプレートに従うこと。

---

## 1. クリエイティブ哲学

### コンセプト: 「作りこまない、でも美しい」

このVlog動画の本質は **"偶然撮れた美しい瞬間"の人工的な再現** にある。
広告でありながら広告に見えない。スマホで何気なく撮った日常が、そのまま洗練された映像になっている——その境界線のギリギリに立つこと。

### 3つの絶対原則

1. **iPhone 13 Aesthetic** — すべてのカットは「iPhone 13で撮ったように見える」こと。映画的な完璧さではなく、スマホ特有のわずかな歪み・自然光・手持ちの揺れが必要
2. **Face Not Shown** — 人物の顔は原則として映さない。手元・後ろ姿・横顔の一部で十分。視聴者が自分を投影できる余白を残す
3. **Micro-movements** — 完全な静止画はNG。カメラも被写体も、常にわずかに動いている。生きている映像であること

---

## 2. プロンプト構造の解剖

### 共通フレームワーク

すべてのプロンプトは以下の要素で構成される:

```
[ショットタイプ] + [顔の可視性] + [シーン/ロケーション] + [被写体 {{変数}}] + [服装 {{変数}}] + [アクション] + [カメラワーク] + [質感ルール]
```

### 各要素の詳細

#### ショットタイプ（カメラポジション）
| タイプ | 用途 | 例 |
|--------|------|-----|
| Close-up shot | 手元・ディテール強調 | ネイル、料理、デバイス操作 |
| Medium shot | 上半身〜膝上、動作全体 | ヨガ、作業、食事 |
| Medium shot from behind | 後ろ姿、世界観提示 | 歩行、窓辺、橋の上 |
| Over the shoulder shot | 視聴者の目線に近い没入感 | 風景を眺める、手元作業 |
| Wide shot | 環境全体、ライフスタイル提示 | 部屋、街並み、駅 |
| Top-down shot | 俯瞰、フラットレイ的 | 料理、手帳、デスク |
| Extreme close-up | 質感・テクスチャ重視 | 肌、生地、食材の断面 |
| POV shot | 一人称視点 | 車窓、飛行機窓、歩行 |
| Full shot | 全身（ただし顔は隠す） | OOTD、部屋でのルーティン |
| Dutch angle shot | 傾いた構図で動的な印象 | 街歩き、移動中 |

#### 顔の可視性ルール
- `face is not shown` — 顔完全非表示（デフォルト）
- `face is barely shown` — 横顔の一部、ぼかし越しなど
- `face mostly covered by phone` — 鏡自撮り専用
- `##` マーカー付き — 特に厳密に顔を隠す指示

#### 変数プレースホルダー `{{ }}`
二重波括弧 `{{ }}` はランタイムで置換される動的パラメータ:
- **人物属性**: `{{A Japanese woman in her early 20's with long brown hair}}`
- **服装**: `{{Grey t-shirt and striped pajama pants}}`
- **季節対応の衣装**: `{{Cropped hoodie in pastel or muted tone, parachute pants}}`
- **シーン固有の小道具**: `{{a plate of thinly sliced raw beef}}`

#### カメラワーク定型句（必須）
```
The camera has subtle micro-movements.
The camera work is slightly shaky, as if shot on a handheld smartphone.
[Camera Logic] The shot looks raw and unfiltered as if shot on an iPhone 13.
Natural lighting, authentic social media aesthetic.
```

---

## 3. シーンカテゴリ別テンプレート

### 3.1 鏡自撮り（Mirror Selfie / OOTD）

**目的**: ファッション訴求。「今日のコーデ」を自然に見せる

**構造パターン**:
```
video of an "Outfit of the Day" (OOTD).
The shot is a stable, first-person mirror selfie taken on a smartphone
in the bright, naturally lit entryway of a modern Tokyo City apartment.
{{人物属性}}, with her face mostly covered by her phone,
showcases a stylish and climate-appropriate [アイテム]
by making small, subtle movements like shifting her weight and turning slightly.
{{外見描写}}, and has great posture.
{{服装の詳細}}
The camera has subtle micro-movements.
The camera work is slightly shaky.
The camera work looks raw, unfiltered as if shot on an iPhone 13.
don't carry a bag.
```

**バリエーション（服装の例）**:
- Cropped hoodie in pastel or muted tone, parachute pants, ribbed knit beanie + layered necklaces
- Boxy blazer in olive green, wide-leg trousers + low sleek bun, minimalist silver necklace
- Fitted white baby tee, high-waisted charcoal trousers + thin gold chain, ear cuffs
- Oversized cable-knit cardigan, pleated midi skirt, chunky ankle boots + beret
- Camel-tone trench coat, cream turtleneck, straight-leg dark denim + gold hoop earrings
- Puffer vest over a hoodie, cargo joggers, trail sneakers + beanie + crossbody micro-bag

**設計意図**:
- 顔はスマホで隠す（=モデル不要、誰でも自分に見える）
- 体重移動・微回転のみの最小限の動き（=ポージングではなく自然体）
- 「don't carry a bag」は手ぶら＝コーデそのものに集中させる工夫

---

### 3.2 人物[動き]（Human Actions）

**目的**: 日常動作の美的切り取り。ライフスタイルの空気感を伝える

**構造パターン**:
```
[ショットタイプ], face is not shown.
The scene is set in [ロケーション].
The subject is {{人物属性}}
The subject is wearing {{服装}}
Action: [具体的な動作の描写]
The camera has subtle micro-movements.
The camera work is slightly shaky, as if shot on a handheld smartphone.
[Camera Logic] The shot looks raw and unfiltered as if shot on an iPhone 13.
Natural lighting, authentic social media aesthetic.
```

**動きのバリエーション集**（7段階の粒度で展開）:

| サブカテゴリ | 動作例 | ロケーション例 |
|------------|--------|--------------|
| 動き1 | ヨガストレッチ、ラグの上で座る | リビング、窓辺 |
| 動き2 | 手すりに手を置く、ネイルを見せる | 橋の上、レストラン |
| 動き3 | 運河を眺める、容器に触れる | 歩道橋、カフェ |
| 動き4 | ブランケットに包まる、腕を組む | ソファ、部屋 |
| 動き5 | 買い物袋を持つ、ノートPCを操作 | 街中、オフィス |
| 動き6 | ベッドメイキング、パジャマで伸び | 寝室、自宅 |
| 動き7 | お茶を入れる、夜のドライブ | キッチン、車内 |

**設計意図**:
- 7つのスロットで「1日の流れ」を表現可能（朝のヨガ→外出→仕事→夜のリラックス）
- 各スロットは独立しているため、ランダムに組み合わせても違和感が出にくい
- 服装と場所の組み合わせで季節・TPOを暗示する

---

### 3.3 食事（Food / Cooking）

**目的**: 食のシズル感。「おいしそう」→「こんな生活したい」の導線

**構造パターンA（料理シーン）**:
```
A static, high-angle, top-down POV shot of a home cooking moment,
face is not shown, captured on a smartphone.
The scene is set in [キッチンの描写].
[調理動作の詳細な描写]
Cooking sounds: [音の描写]
The camera has subtle micro-movements.
The camera work looks raw, unfiltered as if shot on an iPhone 13.
```

**構造パターンB（食事シーン）**:
```
[ショットタイプ], face is not shown.
The scene is set in [食事場所].
Action: Showing {{料理の描写}}
The camera has subtle micro-movements.
The camera work is slightly shaky, as if shot on a handheld smartphone.
[Camera Logic] The shot looks raw and unfiltered as if shot on an iPhone 13.
Natural lighting, authentic social media aesthetic.
```

**食事バリエーション**:
- 自炊: フライパンで卵を焼く、野菜を切る、味噌汁を注ぐ
- 外食: ラーメンの湯気、焼肉の網、カフェのラテアート
- おやつ: コンビニスイーツ開封、お茶を淹れる
- 食材: 断面のクローズアップ、盛り付けの俯瞰

**音のディテール**（食事カテゴリ固有）:
```
Cooking sounds: sizzling oil and gentle clinking of the spatula against the pan
```
→ 音の指定があるのは食事カテゴリのみ。食の臨場感は音が命

---

### 3.4 作業（Work / Desk）

**目的**: 「集中している姿」の美しさ。プロフェッショナル感の演出

**構造パターン**:
```
[ショットタイプ], face is not shown.
The scene is set in [作業環境].
The subject is {{人物属性}}
Action: [作業動作]
The camera has subtle micro-movements.
The camera work is slightly shaky, as if shot on a handheld smartphone.
[Camera Logic] The shot looks raw and unfiltered as if shot on an iPhone 13.
Natural lighting, authentic social media aesthetic.
```

**作業バリエーション**:

| シーン | 手元の動き | 環境ディテール |
|--------|-----------|--------------|
| デスクワーク | キーボードタイピング | 白いコーヒーカップ、観葉植物 |
| クリエイティブ作業 | ペンタブ操作、スケッチ | ピンクのノートPC、付箋 |
| スマホ操作 | 画面スクロール、メモ入力 | カフェ、電車内 |
| 読書 | ページをめくる | ソファ、窓辺の光 |
| 手作業 | 手帳に書く、シール貼り | ウッドテーブル、文具 |

---

### 3.5 ペット（Pet）

**目的**: 感情のフック。動物のかわいさで視聴者の心を掴む

**構造パターン**:
```
Medium shot, face is not shown.
The scene is set in [生活空間].
Action: {{ペットの動作}}
The camera has subtle micro-movements.
The camera work is slightly shaky, as if shot on a handheld smartphone.
[Camera Logic] The shot looks raw and unfiltered as if shot on an iPhone 13.
Natural lighting, authentic social media aesthetic.
```

**ペットバリエーション**:
- 猫: グレーのラグの上で丸くなる、自動トイレの横で座る、窓辺で外を眺める
- 犬: リビングで伏せる、飼い主の足元で寝る
- 小動物: ケージの中で餌を食べる

**設計意図**:
- ペットが主役だが、あくまで「飼い主のVlog」の体裁
- 部屋のインテリアも映り込ませてライフスタイル訴求を兼ねる

---

### 3.6 風景（Scenery / Location）

**目的**: 空気感の転換。カット間のブリッジ、世界観の提示

**構造パターンA（歩行者視点）**:
```
An authentic, unpolished, raw and unfiltered as if shot on a smartphone.
The scene is shot by a person standing on [場所の描写].
[風景の詳細]
The camera has subtle micro-movements.
The camera work is slightly shaky, as if shot on a handheld smartphone.
[Camera Logic] The shot looks raw and unfiltered as if shot on an iPhone 13.
Natural lighting, authentic social media aesthetic.
```

**構造パターンB（車窓 / POV）**:
```
A POV shot from the back seat of a moving [乗り物].
The camera is positioned low, capturing the view outside the side window
as the [乗り物] drives/flies through [風景].
The mood is [雰囲気].
The shot is stable but has subtle organic motion
from the movement of the [乗り物].
Natural lighting, the aesthetic is raw and unfiltered, as if shot on a smartphone.
```

**構造パターンC（街スナップ）**:
```
Wide shot of the street scene, face is not shown.
The scene is set in {{都市の描写}}
[通行人・車両・看板の描写]
The camera has subtle micro-movements.
```

**風景バリエーション**:

| サブカテゴリ | ロケーション例 | 時間帯 |
|------------|--------------|--------|
| 風景1 | 橋の上、歩道、展望台 | 日中、夕方 |
| 風景2 | 車窓、飛行機窓 | 日中（空と雲） |
| 風景3 | 交差点、花火、駅ホーム | 夜、祭り |

---

## 4. 変数置換ルール

### `{{ }}` プレースホルダーの運用規則

プロンプト内の `{{ }}` は実行時にユーザー入力値で置換される。

#### 置換対象の変数一覧

| 変数カテゴリ | 例 | 置換元 |
|------------|-----|--------|
| 人物属性 | `{{A Japanese woman in her early 20's}}` | `subject` パラメータ |
| 服装 | `{{Grey t-shirt and striped pajama pants}}` | 季節・キーワードからLLMが生成 |
| 料理・小道具 | `{{a plate of thinly sliced raw beef}}` | キーワードからLLMが生成 |
| 場所 | `{{A busy city intersection with a crosswalk}}` | キーワードからLLMが生成 |

#### 置換時の注意

1. **人物属性は広告主のターゲット層に合わせる** — 20代女性向けなら `A Japanese woman in her early 20's`、社会人男性なら `A Japanese man in his late 20's`
2. **服装は季節パラメータに連動** — 春夏ならリネン・サンダル、秋冬ならニット・ブーツ
3. **LLMが置換する場合もテンプレートの「型」を壊さない** — ショットタイプやカメラワークの定型句は固定

---

## 5. カット構成の設計思想

### 1本の動画 = 10〜12カットの組み合わせ

各カットはカテゴリからランダムに選ばれるが、以下のバランスを保つ:

| 割合 | カテゴリ | 役割 |
|------|---------|------|
| 30〜40% | 人物[動き] | メインコンテンツ、日常の描写 |
| 10〜15% | 鏡自撮り | フック、ファッション訴求 |
| 10〜15% | 食事 | 生活感、シズル |
| 10〜15% | 作業 | プロ感、集中力 |
| 5〜10% | ペット | 感情フック |
| 15〜20% | 風景 | ブリッジ、世界観 |

### カット間のトランジション
- `crossfade` (0.1秒) でつなぐ — Vlogの自然な流れを維持
- 急なカット切り替えは避ける（広告感が出るため）

---

## 6. 品質を支える暗黙ルール

### やること
- 自然光を使う（Natural lighting）
- 手ブレ感を維持する（slightly shaky）
- 生活感のある小道具を画面に入れる（コーヒーカップ、観葉植物、ラグ）
- 服装のディテールを具体的に書く（色、素材、ブランド感）
- 各カットに固有のアクションを1つ持たせる

### やらないこと
- 顔を正面から映さない
- 三脚固定のような安定しすぎた映像
- 過度なカラーグレーディング（Rawであること）
- バッグを持たせない（鏡自撮り時）
- 映画的なライティング（Ring light, studio lighting 等は禁止）

---

## 7. Veo 3 向け実装メモ

### API仕様との対応

| パラメータ | 値 | 理由 |
|-----------|-----|------|
| aspect_ratio | 9:16 | 縦型ショート動画 |
| duration | 6s | 1カット6秒 × 10〜12カット = 60〜72秒の動画 |
| resolution | 720p | SNS配信に十分、生成コスト最適化 |
| generate_audio | false | 音声は別途ElevenLabsで生成 |

### プロンプトの英語出力ルール
- Veo 3は英語プロンプトのみ対応
- `{{ }}` 内も含めすべて英語で出力すること
- 日本語のコンセプト（エモい、シズル感等）は英語の映像用語に翻訳する

---

## 付録: 全テンプレート一覧

> 以下はCSVから抽出したプロンプト原文。`{{ }}` 内は実行時に置換される変数。

### A. 鏡自撮り（9バリエーション）

各行は同一構造で**服装のみ差し替え**。衣装バリエーションのストックとして使う。

**固定部分**:
```
video of an "Outfit of the Day" (OOTD). The shot is a stable, first-person
mirror selfie taken on a smartphone in the bright, naturally lit entryway
of a modern Tokyo City apartment. {{人物属性}}, with her face mostly covered
by her phone, showcases a stylish and climate-appropriate [item] by making
small, subtle movements like shifting her weight and turning slightly.
{{外見}}, and has great posture. {{服装}}
The camera has subtle micro-movements. The camera work is slightly shaky.
The camera work looks raw, unfiltered as if shot on an iPhone 13.
don't carry a bag.
```

**服装バリエーション**:
1. Cropped hoodie in pastel/muted tone, parachute pants, ribbed knit beanie + layered necklaces, soft makeup, bowl cut or slicked back hair
2. Boxy blazer in olive green, wide-leg trousers + low sleek bun, minimalist silver necklace
3. Fitted white baby tee, high-waisted charcoal trousers + thin gold chain, ear cuffs, tousled waves
4. Oversized cable-knit cardigan, pleated midi skirt, chunky ankle boots + beret, delicate pendant necklace
5. Camel-tone trench coat, cream turtleneck, straight-leg dark denim + gold hoop earrings, polished low ponytail
6. Puffer vest over a hoodie, cargo joggers, trail sneakers + beanie, crossbody micro-bag
7. Linen blend wide-leg pants, basic tank top tucked in, woven mule sandals + stacked bracelets, half-up bun
8. Structured cropped denim jacket, matching straight-leg jeans, vintage band tee + tortoiseshell sunglasses, messy bun
9. Flowy satin midi skirt, fitted ribbed top, strappy block heels + small shoulder bag, sleek center-part hair

### B〜F: カテゴリ別全プロンプト

> 量が膨大なため、実装時はCSVをそのまま読み込んで使用する。
> このドキュメントは「なぜそう書かれているか」の設計思想を伝えることが目的。
> 実データは `vlogプロンプト - シート1.csv` を正とする。

---

## サウンド設計（BGM・SE）

### BGM基本ルール

1. **音量**: 動画全体に薄く小さな音量でかける。ナレーションやSEの邪魔をしない程度に留める（Creatomateで `volume: 8〜12%` を目安）
2. **楽器**: ピアノソロを基本とする。おとなしめで上品な音色
3. **調性**: メジャーキーまたはセブンスコード程度。マイナーキーは使わない
4. **Mood別3パターン**:
   - `01_hopeful` — C major / 70 BPM / 静か→温かい→希望→着地（明るく前向きな動画向け）
   - `02_tender` — G major / 65 BPM / アルペジオ→メロディ→戻る（親子の温かさ、優しい動画向け）
   - `03_reflective` — F major / 60 BPM / ミニマル→Maj7→希望の一音（考えさせる・内省的な動画向け）
5. **BGMファイル置き場**: `clients/vantan/bgm/{mood}/` に格納

### SE基本ルール

1. **4カテゴリ**:
   - `01_impact` — インパクト（転換・発見・希望が開ける瞬間）
   - `02_negative` — おとなしめ（不安・心配・切ない場面）
   - `03_neutral` — 普通（説明・情景描写）
   - `04_tiktok` — TikTokでよく使われる定番の音（掴み・CTA）
2. **音色方針**: オーケストラ楽器系が基本。メジャー/セブンス調性。丁寧で上品な音
3. **連続同一SE禁止**: 隣り合うカットで同じSEファイルが使われないようにする
4. **SEファイル置き場**: `clients/vantan/se/真面目バージョン/{カテゴリ}/`
5. **命名規則**: `se##_英語名.mp3`（##は各カテゴリ内の通し番号）
