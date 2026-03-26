"""
ペルソナ定義（5通り）
各パターンにランダム割り当てして、動画のバリエーションを出す。
人物外見だけでなく、生活空間・光・季節感・アクションも変える。
"""

PERSONAS = [
    {
        "id": "A",
        "label": "都会マンション・朝の光",
        "child_boy": "a 15-year-old Japanese boy with slightly wavy dark brown hair, wearing a navy blue hoodie and khaki chinos, athletic build",
        "child_girl": "a 16-year-old Japanese girl with long wavy dark brown hair tied in a low ponytail, wearing a cream-colored oversized knit and wide-leg jeans, tall and slender build",
        "parent_female": "a 40-year-old Japanese woman with short bob-cut black hair, wearing a light gray knit sweater and navy slacks, petite build",
        "parent_male": "a 42-year-old Japanese man with short cropped graying black hair, wearing a charcoal crew-neck sweater and dark jeans, broad-shouldered build",
        "home_scene": "Modern high-rise apartment with floor-to-ceiling windows, early morning golden light casting long shadows across a clean minimalist interior. Indoor plants near the window.",
        "parent_worry_scene": "Standing in a sleek kitchen island area, morning coffee in hand, gazing out at a vast cityscape through a large window. Soft morning haze over the buildings.",
        "hope_scene": "Warm morning sunlight gradually flooding through sheer white curtains, dust particles floating gently in the light beams. A quiet, hopeful moment.",
        "discovery_scene": "Sitting at a wooden dining table with a laptop, golden hour light from a west-facing window illuminating the screen. Indoor plants casting soft shadows on the wall.",
        "together_scene": "Walking side by side through a tree-lined sidewalk in a residential neighborhood, dappled sunlight filtering through fresh green leaves above.",
        "future_scene": "Wide shot of a spring cityscape at golden hour, cherry blossom petals floating past modern buildings, warm sky gradient from orange to soft blue.",
    },
    {
        "id": "B",
        "label": "郊外一軒家・午後の光",
        "child_boy": "a 16-year-old Japanese boy with messy medium-length black hair covering his forehead, wearing a black graphic tee and dark jogger pants, lean build",
        "child_girl": "a 15-year-old Japanese girl with twin braids of dark brown hair, wearing a pastel pink hoodie and black leggings, small and energetic build",
        "parent_female": "a 43-year-old Japanese woman with shoulder-length straight black hair with a side part, wearing a denim shirt and white cotton pants, slim build",
        "parent_male": "a 44-year-old Japanese man with neat short black hair with a few gray strands, wearing a light blue oxford shirt and khaki pants, lean build",
        "home_scene": "A cozy suburban house with warm wooden floors, afternoon sunlight pouring through a large sliding glass door leading to a small garden. Books and cushions scattered on a low sofa.",
        "parent_worry_scene": "Sitting on the edge of a sofa in the living room, looking through a rain-speckled window at a quiet garden. Soft overcast light creating an introspective atmosphere.",
        "hope_scene": "Rain stopping outside, a single ray of sunlight breaking through clouds and illuminating wet leaves in the garden. Peaceful transition from gray to warm tones.",
        "discovery_scene": "Lying on a couch with a tablet, scrolling through content. Late afternoon light streaming diagonally across the room, creating warm geometric patterns on the wall.",
        "together_scene": "Riding bicycles together along a quiet riverside path, late afternoon sun backlighting their silhouettes. Cherry blossoms lining the river bank.",
        "future_scene": "Panoramic view of a rural landscape at sunset, green rice paddies reflecting golden sky, a winding road leading toward distant mountains.",
    },
    {
        "id": "C",
        "label": "和モダン・夕方の光",
        "child_boy": "a 16-year-old Japanese boy with neatly styled short dark brown hair with a center part, wearing a white henley shirt and gray tapered pants, slender build",
        "child_girl": "a 15-year-old Japanese girl with short pixie-cut black hair with subtle highlights, wearing a lavender blouse and white denim shorts, petite build",
        "parent_female": "a 45-year-old Japanese woman with a wavy bob dyed warm auburn, wearing a camel-colored turtleneck and dark brown corduroy skirt, petite build",
        "parent_male": "a 47-year-old Japanese man with salt-and-pepper short hair and glasses, wearing a navy polo shirt and beige chinos, average build",
        "home_scene": "A Japanese-modern interior with tatami flooring, shoji screen doors partially open, warm evening light creating soft shadows. A low chabudai table with tea cups.",
        "parent_worry_scene": "Kneeling at a low table near a shoji screen, evening amber light filtering through the translucent panels. A contemplative, traditional atmosphere with modern touches.",
        "hope_scene": "Evening sky visible through an open engawa veranda, gradient from deep blue to warm amber. Wind chimes gently swaying. A moment of quiet serenity.",
        "discovery_scene": "Sitting at a modern desk area tucked in a Japanese-style room, warm desk lamp creating a pool of golden light. Laptop screen glowing softly.",
        "together_scene": "Sharing a quiet moment on an engawa veranda overlooking a small Japanese garden, evening golden hour light. Tea cups between them.",
        "future_scene": "A traditional Japanese garden at dusk, stone lantern glowing softly, cherry blossoms floating on a still pond reflecting the amber sky.",
    },
    {
        "id": "D",
        "label": "カフェ風リビング・曇りの柔らかい光",
        "child_boy": "a 15-year-old Japanese boy with a short buzz-cut and slightly tanned skin, wearing an olive green bomber jacket over a white tee and black skinny jeans, stocky build",
        "child_girl": "a 16-year-old Japanese girl with medium-length layered dark hair with curtain bangs, wearing a mustard yellow cardigan over a white camisole and floral skirt, average build",
        "parent_female": "a 41-year-old Japanese woman with long straight dark hair pulled back in a loose bun, wearing a striped mariniere top and navy chinos, medium build",
        "parent_male": "a 38-year-old Japanese man with neat medium-length black hair, wearing a white linen shirt rolled at the sleeves and dark navy trousers, fit build",
        "home_scene": "A cafe-style living room with exposed brick walls, pendant Edison bulb lighting, and large arched windows. Soft diffused overcast light. Succulents and vintage decor on wooden shelves.",
        "parent_worry_scene": "Leaning against a bookshelf near a window, arms crossed, looking down pensively. Soft overcast diffused light wrapping around the room. Vintage clock on the wall.",
        "hope_scene": "Overcast clouds slowly parting outside a window, soft white light gradually brightening the room. A small bird landing on the window ledge.",
        "discovery_scene": "Sitting at a rustic wooden desk in a cozy corner with a laptop, warm Edison bulb overhead. Surrounded by potted plants and photo frames.",
        "together_scene": "Browsing together at a weekend flea market or outdoor bookstall, surrounded by warm earth-toned tents and soft diffused daylight.",
        "future_scene": "Wide shot of a spring park with diverse trees in bloom, soft overcast light creating even illumination, people enjoying a peaceful afternoon in the distance.",
    },
    {
        "id": "E",
        "label": "海辺の街・朝焼け",
        "child_boy": "a 16-year-old Japanese boy with thick wavy black hair pushed back, wearing a white chef-style collarless shirt and dark navy pants, sturdy build",
        "child_girl": "a 15-year-old Japanese girl with long straight dark brown hair with blunt bangs, wearing a pale blue apron over a white long-sleeve tee and black pants, delicate build",
        "parent_female": "a 46-year-old Japanese woman with elegantly pinned-up dark hair with silver streaks, wearing a moss green wrap blouse and charcoal slacks, slender and tall build",
        "parent_male": "a 45-year-old Japanese man with short silver-streaked hair combed back, wearing a beige linen blazer over a white tee and gray slacks, dignified build",
        "home_scene": "A bright seaside-town house with white-painted walls and light blue accents, wide open windows letting in salty ocean breeze and early morning light. Seashells on the windowsill.",
        "parent_worry_scene": "Standing on a small balcony overlooking a quiet harbor at dawn, distant fishing boats on calm water. Cool blue-to-pink gradient sky. A thoughtful solitary moment.",
        "hope_scene": "Sunrise over the ocean, warm golden light breaking through low clouds on the horizon. Waves gently lapping at a sandy shore. Pure, hopeful, new beginning.",
        "discovery_scene": "Sitting near a window seat with an ocean view, laptop on a small table, morning light reflecting off the water creating dancing patterns on the ceiling.",
        "together_scene": "Walking together along a quiet morning beach, footprints in wet sand, gentle waves nearby. Warm golden sunrise light from the side.",
        "future_scene": "Wide cinematic shot of a coastal town at sunrise, pastel-colored buildings along a harbor, fishing boats rocking gently, sky painted in warm pink and gold.",
    },
]

# パターンへのペルソナ割り当て（16パターンに5ペルソナを分散）
import random
random.seed(42)  # 再現性のためシード固定

def assign_personas(pattern_count=16):
    """16パターンに5ペルソナをなるべく均等に、隣接重複なしで割り当て"""
    # 各ペルソナ3回ずつ（15）+ 1つ追加で16
    base = list(range(5)) * 3 + [0]  # A×4, B×3, C×3, D×3, E×3
    # 隣接重複を避けつつシャッフル
    for _ in range(1000):
        random.shuffle(base)
        if all(base[i] != base[i+1] for i in range(len(base)-1)):
            break
    return base[:pattern_count]

PATTERN_PERSONA_MAP = assign_personas()

def get_persona_for_pattern(pattern_no: int, child_gender: str = "boy") -> dict:
    """
    パターン番号（1-16）に対応するペルソナを取得。
    child_gender: "boy" or "girl"
    """
    idx = PATTERN_PERSONA_MAP[(pattern_no - 1) % len(PATTERN_PERSONA_MAP)]
    p = PERSONAS[idx].copy()
    p["child"] = p[f"child_{child_gender}"]
    return p


if __name__ == "__main__":
    print("=== ペルソナ割り当て ===\n")
    genders = ['boy','girl','boy','girl','boy','girl','boy','girl',
               'boy','girl','boy','girl','boy','girl','boy','girl']
    for i in range(16):
        p = get_persona_for_pattern(i + 1, genders[i])
        child_short = p['child'].split(',')[0]
        print(f"  No.{str(i+1).zfill(2)}: ペルソナ{p['id']}（{p['label']}）")
        print(f"         子={child_short}")
        print(f"         舞台={p['home_scene'][:60]}...")
        print()
