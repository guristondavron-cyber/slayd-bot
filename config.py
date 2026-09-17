import os
from dataclasses import dataclass
from typing import Dict, Tuple
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Gemini model to use - using current modern Gemini model
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
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
        name="Emerald Green (Yashil)",
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
        name="Modern Sunset (Koral)",
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
        name="Clean Minimal (Oq & Binafsha)",
        emoji="⚪",
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
}

DEFAULT_THEME = "dark_tech"
DEFAULT_SLIDE_COUNT = 5
MAX_SLIDE_COUNT = 15
MIN_SLIDE_COUNT = 3
