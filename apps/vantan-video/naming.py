"""
Vantan バナー/動画 命名モジュール
ルールの詳細: clients/vantan/naming_rules.md
"""
from datetime import datetime

# === マスタデータ（naming_rules.md と同期すること） ===

SCHOOL_CODE = {
    "バンタンデザイン研究所": "VDI",
    "バンタンゲームアカデミー": "VGA",
    "ヴィーナスアカデミー": "VA",
    "バンタンヴィーナスアカデミー": "VA",
    "バンタンクリエイターアカデミー": "VCA",
    "レコールバンタン": "LV",
    "KADOKAWAドワンゴ情報工科学院": "KDG",
    "KADOKAWAアニメ・声優アカデミー": "KAA",
    "KADOKAWAマンガアカデミー": "KMA",
    "バンタンミュージックアカデミー": "VMA",
    "バンタン外語＆ホテル観光学院": "VFA",
    "バンタン高等学院": "GAKUIN",
    "バンタン渋谷美容学院": "VBG",
    "バンタン芸術学院": "VAA",
    "バンタンデザイン研究所FH": "VDIFH",
    "バンタン国際製菓カフェ和洋調理学院": "VIA",
    "バンタン韓国語教室": "VKS",
    "ZETA DIVISION GAMING ACADEMY": "ZGA",
    "バンタンZETA DIVISION GAMING ACADEMY": "ZGA",
    "バンタンポータル": "PORTAL",
    "バンタンオール": "BRAND",
}

DEPT_CODE = {
    "専門部": "PRO",
    "高等部": "HS",
    "キャリア": "CC",
    "大学部": "U",
    "中等部": "J",
    "なし": "N",
    "高等部スケボー": "SK",
    "キャリア適職診断": "CCT",
}

CATEGORY_CODE = {
    "親向け記事": "_oyakiji",
    "本人向け記事": "_honnin_kiji",
    "グラフィックデザイン": "_graphicdesign",
    "ファッション": "_fashion",
    "デザイン": "_design",
    "デザイン&イラスト": "_design_illust",
    "ヘアメイク": "_hairmake",
    "韓国メイク": "_koreanmake",
    "キャラクターデザイン": "_character",
    "ゲーム制作": "_gameseisaku",
    "e-sports": "_esports",
    "ゲームプログラミング": "_gameprogram",
    "マネージャー": "_manager",
    "動画制作（VCA）": "_vca_moviecreator",
    "映像クリエイター（VDI)": "_vdi_moviecreator",
    "トータルビューティー": "_totalbeauty",
    "ビューティープロデュース": "_beautyproduce",
    "声優マネージャー": "_seiyu_manager",
    "3Dグラフィック": "_3d",
    "カフェ": "_cafe",
    "製菓": "_patisserie",
    "調理ブランドプロデュース": "_foodbrandproduce",
    "カフェ開業": "_cafe_opening",
    "飲食店開業": "_insyoku_opening",
    "DSA": "_dsa",
    "インテリア": "_interior",
    "サウンド": "_sound",
    "フォト": "_photo",
    "映画・映像": "_movie",
    "指名": "_simei",
    "プログラミング": "_programming",
    "トップデザイナー実践": "_topdesigner",
    "地方開業": "_localopening",
    "クリエイター": "_creator",
    "イベント": "_event",
    "VDIオール": "_vdi_all",
    "エンタメ": "_entame",
    "Youtuber": "_youtuber",
    "アニメ": "_anime",
    "ワイン": "_wine",
    "SNSマーケティング": "_snsmarke",
}

# 分野略称（キー: "{スクール略}{部}_{分野名}"）
FIELD_CODE = {
    "VDI専門部_グラフィック": "graphic",
    "VDI専門部_デザイン": "design",
    "VDI専門部_イラスト": "illust",
    "VDI専門部_フォト": "photo",
    "VDI専門部_ファッション": "fashion",
    "VDI専門部_映画・映像": "video",
    "VDI専門部_ヘアメイク": "hairmake",
    "VDI専門部_サウンド": "sound",
    "VDI専門部_ランジェリー": "lingerie",
    "VDI高等部_イラスト": "illust",
    "VDI高等部_デザイン": "design",
    "VDI高等部_ファッション": "fashion",
    "VDI高等部_美容": "beauty",
    "VDI高等部_ヘアメイク": "hairmake",
    "VDI高等部_映像": "video",
    "VDIキャリア_インテリア": "interior",
    "VDIキャリア_SNSマーケ": "snsmarketing",
    "VDIキャリア_webデザイン": "webdesign",
    "VGA専門部_eスポーツ": "esports",
    "VGA専門部_ゲーム": "game",
    "VGA専門部_アニメ": "anime",
    "VGA専門部_サウンド": "sound",
    "VGA専門部_CG": "cg",
    "VGA専門部_キャラクターデザイン": "characterdesign",
    "VGA専門部_イラスト": "illust",
    "VGA高等部_eスポーツ": "esports",
    "VGA高等部_アニメ": "anime",
    "VA専門部_トータルビューティー": "totalbeauty",
    "VA高等部_親向け": "parent",
}

# [TBD] マーク
TBD = "[TBD]"


def generate_banner_name(
    school: str,
    dept: str = "専門部",
    field: str = None,
    category: str = None,
    size: str = "7201280",
    seq: int = None,
    creator: str = None,
    area: str = None,
    carousel: str = "",
    date_str: str = None,
) -> dict:
    """
    バナー名を生成する。

    Returns:
        {
            "name": "20260323_VDI_PRO_[TBD]_[TBD]_7201280_200001_[TBD]_[TBD]",
            "parts": { ... },
            "tbd_fields": ["field", "category", ...]
        }
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")

    school_code = SCHOOL_CODE.get(school, TBD)
    dept_code = DEPT_CODE.get(dept, TBD)

    # 分野
    field_code = TBD
    if field:
        key = f"{school_code}{dept}_{field}"
        field_code = FIELD_CODE.get(key, TBD)

    # カテゴリ
    cat_code = CATEGORY_CODE.get(category, TBD) if category else TBD

    # 連番
    seq_str = str(seq) if seq else TBD

    # 制作担当
    creator_str = creator if creator else TBD

    # 地名
    area_str = area if area else TBD

    parts = {
        "date": date_str,
        "school": school_code,
        "dept": dept_code,
        "field": field_code,
        "category": cat_code,
        "size": size,
        "seq": seq_str,
        "creator": creator_str,
        "area": area_str,
        "carousel": carousel,
    }

    # TBDフィールドを集める
    tbd_fields = [k for k, v in parts.items() if TBD in str(v)]

    name = f"{date_str}_{school_code}_{dept_code}_{field_code}{cat_code}_{size}_{seq_str}_{creator_str}_{area_str}{carousel}"

    return {"name": name, "parts": parts, "tbd_fields": tbd_fields}


def generate_names_for_workflow(patterns: dict, base_seq: int = 200001) -> list:
    """
    workflow_002 の全パターンにバナー名を生成。

    Args:
        patterns: { "no01": {"school": "...", "field": "...", ...}, ... }
        base_seq: 連番の開始番号

    Returns:
        [{"pattern": "no01", "name": "...", "tbd_fields": [...], ...}, ...]
    """
    results = []
    seq = base_seq
    for pat_key in sorted(patterns.keys()):
        pat = patterns[pat_key]
        result = generate_banner_name(
            school=pat.get("school", ""),
            dept="専門部",
            field=pat.get("field"),
            category=None,  # TBD
            size="7201280",
            seq=seq,
            creator=None,   # TBD
            area=None,       # TBD
        )
        result["pattern"] = pat_key
        results.append(result)
        seq += 1
    return results


# --- CLI テスト ---
if __name__ == "__main__":
    # テスト
    test_schools = [
        "バンタンデザイン研究所",
        "バンタンゲームアカデミー",
        "ヴィーナスアカデミー",
        "バンタンクリエイターアカデミー",
        "レコールバンタン",
        "KADOKAWAアニメ・声優アカデミー",
        "KADOKAWAマンガアカデミー",
        "バンタンミュージックアカデミー",
    ]
    print("=== バナー名テスト ===\n")
    for i, school in enumerate(test_schools, 200001):
        r = generate_banner_name(school=school, seq=i)
        tbd_mark = f"  ← TBD: {', '.join(r['tbd_fields'])}" if r["tbd_fields"] else ""
        print(f"  {r['name']}{tbd_mark}")
