# 動画生成スタイル定義

動画生成時に適用する「スタイル」の一覧。
ワークフローごとに、どのスタイルを適用するかを選択する。

---

## スタイル一覧

| ID | スタイル名 | 用途 | 適用 WF | 補正エンジン |
|----|-----------|------|---------|------------|
| `vlog` | Vlog風（iPhone/SNS） | カジュアル・親近感 | workflow_001 | なし（素のプロンプト） |
| `cinema` | ドキュメンタリー映画風 | エモーショナル・高品質 | workflow_002 | CINEMA_SUFFIX |
| `dp_engine` | DP補正エンジン | 最高品質の実写表現 | workflow_002（選択適用） | prompt_correction_engine.md |

---

## Style: `vlog`

iPhone/スマホ撮影風。SNS広告向け。
```
The camera work is slightly shaky, as if shot on a handheld smartphone.
The shot looks raw and unfiltered as if shot on an iPhone 13.
Natural lighting, authentic social media aesthetic.
```
**注意:** エモーショナルストーリー版には不向き（ユーザーフィードバック済み）

---

## Style: `cinema`

ドキュメンタリー映画タッチ。浅い被写界深度、前ボケ後ろボケ。
```
Shot on a high-end cinema camera with anamorphic lens.
Shallow depth of field, natural bokeh.
Documentary film aesthetic, warm cinematic color grading.
Subtle natural camera movement. No text, no logos, no signage.
```

---

## Style: `dp_engine`（DP補正エンジン）

Veo 3.1 向け最高品質プロンプト変換。
素朴なシーン記述を、撮影監督レベルのテクニカル・プロンプトに変換する。

### 制約（依拠性の排除）
- 特定のアーティスト名、監督名、作品名は一切使用しない
- 物理的なライティング用語と光学用語のみで「ルック」を再現
- 既存IPに酷似した固有名詞を避ける

### プロンプト構成（5レイヤー）

| # | レイヤー | 内容 | キーワード例 |
|---|---------|------|-------------|
| 1 | Core Subject | 主体（素材、質感、年齢、服装の繊維） | — |
| 2 | Cinematography | 撮影技法 | 35mm/85mm lens, f/1.8, Anamorphic, Shallow DOF |
| 3 | Lighting | ライティング | Volumetric lighting, Global illumination, Subsurface scattering, Ray-traced reflections |
| 4 | Atmosphere | 空気感 | Micro-dust, Soft haze, Color temperature (Kelvin), Organic film grain |
| 5 | Motion Control | 動き制御 | Subtle handheld camera shake, Focus pulling, 24fps cinematic cadence |

### 出力ルール
- 言語: **英語**（API解釈精度向上）
- 形式: カンマ区切りの高密度キーワード or 短文連結

### 適用判断
- **毎回自動適用ではない**。カットの内容・意図に応じて適用度合いを判断する。
- スプシの「動画のムード」列と合わせて、どのスタイルをどの程度入れるか決める。

---

## ワークフローとスタイルの対応

| ワークフロー | デフォルトスタイル | 補正エンジン | 備考 |
|------------|-----------------|------------|------|
| workflow_001（Vlog風20本） | `vlog` | なし | 完了済み |
| workflow_002（スクール別親子） | `cinema` | `dp_engine`（選択適用） | 進行中 |

---

## 更新履歴

- 2026-03-24: 初版作成。vlog / cinema / dp_engine の3スタイル定義
