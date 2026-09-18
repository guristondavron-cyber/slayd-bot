import os
from dataclasses import dataclass
from typing import Dict, Tuple
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Gemini model to use - using fast, reliable and modern Gemini model
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
ADMIN_ID = os.getenv("ADMIN_ID", "").strip()



@dataclass(frozen=True)
class ColorTheme:
    id: str
    name: str
    emoji: str
    bg_color: Tuple[int, int, int]
    card_bg: Tuple[int, int, int]
    primary: Tuple[int, int, int]
    secondary: Tuple[int, int, int]
    text_title: Tuple[int, int, int]
    text_body: Tuple[int, int, int]
    text_muted: Tuple[int, int, int]
    badge_bg: Tuple[int, int, int]
    badge_text: Tuple[int, int, int]
    card_border: Tuple[int, int, int]
    dark_mode: bool = True


THEMES: Dict[str, ColorTheme] = {
    "dark_tech": ColorTheme(
        id="dark_tech",
        name="Dark Tech (Neon moviy)",
        emoji="🌙",
        bg_color=(15, 23, 42),       # Slate 900
        card_bg=(30, 41, 59),        # Slate 800
        primary=(56, 189, 248),      # Sky 400
        secondary=(129, 140, 248),   # Indigo 400
        text_title=(248, 250, 252),  # Slate 50
        text_body=(226, 232, 240),   # Slate 200
        text_muted=(148, 163, 184),  # Slate 400
        badge_bg=(14, 116, 144),     # Cyan 700
        badge_text=(224, 242, 254),  # Cyan 100
        card_border=(51, 65, 85),    # Slate 700
        dark_mode=True,
    ),
    "cyberpunk": ColorTheme(
        id="cyberpunk",
        name="Cyberpunk (Neon Pink & Cyan)",
        emoji="⚡️",
        bg_color=(13, 10, 26),       # Deep Violet Black
        card_bg=(28, 20, 52),        # Dark Purple Card
        primary=(244, 63, 94),       # Neon Rose 500
        secondary=(34, 211, 238),    # Neon Cyan 400
        text_title=(255, 255, 255),  # Pure White
        text_body=(241, 232, 254),   # Soft Lavender
        text_muted=(168, 139, 214),  # Muted Purple
        badge_bg=(131, 24, 67),      # Deep Magenta
        badge_text=(254, 205, 211),  # Light Rose
        card_border=(76, 29, 149),   # Violet 900
        dark_mode=True,
    ),
    "corporate_blue": ColorTheme(
        id="corporate_blue",
        name="Corporate Blue (Biznes)",
        emoji="💼",
        bg_color=(248, 250, 252),     # Slate 50
        card_bg=(255, 255, 255),      # White
        primary=(30, 64, 175),        # Blue 800
        secondary=(2, 132, 199),      # Sky 600
        text_title=(15, 23, 42),      # Slate 900
        text_body=(51, 65, 85),       # Slate 700
        text_muted=(100, 116, 139),   # Slate 500
        badge_bg=(224, 242, 254),     # Sky 100
        badge_text=(3, 105, 161),     # Sky 700
        card_border=(226, 232, 240),  # Slate 200
        dark_mode=False,
    ),
    "emerald_green": ColorTheme(
        id="emerald_green",
        name="Emerald Green (Zumrad)",
        emoji="🌿",
        bg_color=(6, 44, 34),         # Deep Emerald
        card_bg=(13, 63, 50),         # Dark Emerald Card
        primary=(52, 211, 153),       # Emerald 400
        secondary=(110, 231, 183),    # Emerald 300
        text_title=(240, 253, 244),   # Emerald 50
        text_body=(209, 250, 229),    # Emerald 100
        text_muted=(110, 231, 183),   # Emerald 300
        badge_bg=(6, 78, 59),         # Emerald 800
        badge_text=(167, 243, 208),   # Emerald 200
        card_border=(20, 83, 67),     # Emerald 700
        dark_mode=True,
    ),
    "modern_coral": ColorTheme(
        id="modern_coral",
        name="Modern Sunset (Koral & Oltin)",
        emoji="🌅",
        bg_color=(24, 24, 27),        # Zinc 900
        card_bg=(39, 39, 42),         # Zinc 800
        primary=(251, 113, 133),      # Rose 400
        secondary=(251, 146, 60),     # Orange 400
        text_title=(255, 255, 255),   # Pure White
        text_body=(228, 228, 231),    # Zinc 200
        text_muted=(161, 161, 170),   # Zinc 400
        badge_bg=(136, 19, 55),       # Rose 900
        badge_text=(254, 205, 211),   # Rose 200
        card_border=(63, 63, 70),     # Zinc 700
        dark_mode=True,
    ),
    "clean_minimal": ColorTheme(
        id="clean_minimal",
        name="Silicon Valley (Oq & Indigo)",
        emoji="☀️",
        bg_color=(250, 250, 250),     # Neutral 50
        card_bg=(255, 255, 255),      # White
        primary=(79, 70, 229),        # Indigo 600
        secondary=(124, 58, 237),     # Violet 600
        text_title=(17, 24, 39),      # Gray 900
        text_body=(55, 65, 81),       # Gray 700
        text_muted=(107, 114, 128),   # Gray 500
        badge_bg=(238, 242, 255),     # Indigo 50
        badge_text=(67, 56, 202),     # Indigo 700
        card_border=(229, 231, 235),  # Gray 200
        dark_mode=False,
    ),
    "warm_editorial": ColorTheme(
        id="warm_editorial",
        name="Warm Editorial (Krem & Qahva)",
        emoji="☕️",
        bg_color=(245, 241, 232),     # Warm Cream/Linen
        card_bg=(255, 253, 249),      # Soft Ivory Card
        primary=(180, 83, 9),         # Amber 700
        secondary=(120, 53, 15),      # Warm Russet
        text_title=(41, 37, 36),      # Stone 900
        text_body=(68, 64, 60),       # Stone 700
        text_muted=(120, 113, 108),   # Stone 500
        badge_bg=(254, 243, 199),     # Amber 100
        badge_text=(146, 64, 14),     # Amber 800
        card_border=(231, 229, 220),  # Stone 200
        dark_mode=False,
    ),
    "midnight_gold": ColorTheme(
        id="midnight_gold",
        name="Midnight Gold (Qora & Oltin)",
        emoji="👑",
        bg_color=(12, 12, 15),        # True Black 950
        card_bg=(24, 24, 29),         # Deep Onyx Card
        primary=(234, 179, 8),        # Champagne Gold 500
        secondary=(250, 204, 21),     # Yellow 400
        text_title=(254, 252, 232),   # Yellow 50
        text_body=(229, 231, 235),    # Gray 200
        text_muted=(156, 163, 175),   # Gray 400
        badge_bg=(113, 63, 18),       # Dark Gold
        badge_text=(254, 240, 138),   # Light Gold
        card_border=(66, 52, 22),     # Gold Muted Border
        dark_mode=True,
    ),
    "sapphire_ocean": ColorTheme(
        id="sapphire_ocean",
        name="Sapphire Ocean (Chuqur Moviy)",
        emoji="🌊",
        bg_color=(10, 25, 47),        # Navy 950
        card_bg=(23, 42, 69),         # Ocean Navy Card
        primary=(100, 255, 218),      # Aquamarine Neon
        secondary=(56, 189, 248),     # Sky 400
        text_title=(230, 241, 255),   # Bright Ice
        text_body=(204, 214, 246),    # Soft Slate Blue
        text_muted=(136, 146, 176),   # Muted Blue
        badge_bg=(17, 34, 64),        # Deep Blue
        badge_text=(100, 255, 218),   # Aqua
        card_border=(35, 53, 84),     # Border Navy
        dark_mode=True,
    ),
    "ruby_luxury": ColorTheme(
        id="ruby_luxury",
        name="Ruby Luxury (Yoqut Qizil)",
        emoji="🍷",
        bg_color=(30, 10, 18),        # Deep Ruby Wine
        card_bg=(48, 18, 29),         # Ruby Card
        primary=(244, 63, 94),        # Rose 500
        secondary=(251, 113, 133),    # Rose 400
        text_title=(255, 241, 242),   # Rose 50
        text_body=(254, 205, 211),    # Rose 200
        text_muted=(225, 29, 72),     # Rose 600
        badge_bg=(76, 5, 25),         # Deep Burgundy
        badge_text=(254, 226, 226),   # Pale Rose
        card_border=(102, 14, 38),    # Burgundy Border
        dark_mode=True,
    ),
}

DEFAULT_THEME = "dark_tech"
DEFAULT_SLIDE_COUNT = 5
MAX_SLIDE_COUNT = 25
MIN_SLIDE_COUNT = 1

# Taqdimotning ixtisoslashgan rejimlari
PRESENTATION_MODES: Dict[str, Dict[str, str]] = {
    "general": {
        "id": "general",
        "name": "⚡️ Umumiy / Erkin taqdimot",
        "desc": "Universal, har qanday mavzuga mos erkin va qiziqarli taqdimot.",
        "icon": "⚡️",
    },
    "education": {
        "id": "education",
        "name": "🎓 Ta'lim & Referat (Maktab / Talaba)",
        "desc": "Ilmiy tushunchalar, nazariya, amaliy tahlil va adabiyotlar bilan akademik rejim.",
        "icon": "🎓",
    },
    "business": {
        "id": "business",
        "name": "💼 Biznes & Pitch Deck (Startap / Investor)",
        "desc": "Muammo, yechim, bozor hajmi, biznes model, raqobat va moliyaviy rejalar.",
        "icon": "💼",
    },
    "analytics": {
        "id": "analytics",
        "name": "📊 Tahliliy Hisobot & Statistika",
        "desc": "Raqamlar, KPIlar, solishtirmalar, dinamika va xulosalarga qaratilgan chuqur hisobot.",
        "icon": "📊",
    },
}

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
IMAGE_CACHE_DIR = os.path.join(os.path.dirname(__file__), "image_cache")
GENERATED_DIR = os.path.join(os.path.dirname(__file__), "generated_slides")

for d in [ASSETS_DIR, IMAGE_CACHE_DIR, GENERATED_DIR]:
    os.makedirs(d, exist_ok=True)
