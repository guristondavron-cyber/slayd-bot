from image_service import fetch_ai_image_sync
import os
from typing import Optional, List, Tuple, Any, Dict
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION

import config
from config import ColorTheme
from gemini_service import (
    PresentationContent,
    SlideContent,
    CardItem,
    StatItem,
    ComparisonColumn,
)


FONT_FAMILY_TITLE = "Arial"
FONT_FAMILY_BODY = "Calibri"


import hashlib
import json
import logging
import subprocess
import urllib.parse
from typing import Optional, List
import requests
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def generate_themes_showcase_image() -> str:
    """Barcha 10 ta mavzuning real vizual ko'rinishini aks ettiruvchi yuqori sifatli rasmni yaratadi."""
    os.makedirs(config.ASSETS_DIR, exist_ok=True)
    out_path = os.path.join(config.ASSETS_DIR, "themes_showcase.png")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 20000:
        return out_path

    W, H = 1200, 680
    img = Image.new("RGB", (W, H), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)

    # Accent top bar
    draw.rectangle([(0, 0), (W, 8)], fill=(56, 189, 248))
    draw.text((40, 25), "PROFESSIONAL TAQDIMOT MAVZULARI (10 XIL ZAMONAVIY DIZAYN)", fill=(248, 250, 252))
    draw.text((40, 50), "Har bir mavzu alohida ranglar uyg'unligi, kontrast va infografikaga ega", fill=(148, 163, 184))

    themes_list = list(config.THEMES.values())
    card_w = 215
    card_h = 240
    gap_x = 18
    gap_y = 20
    start_x = 25
    start_y = 90

    for idx, th in enumerate(themes_list):
        row = idx // 5
        col = idx % 5
        x = start_x + col * (card_w + gap_x)
        y = start_y + row * (card_h + gap_y)

        # Card background
        draw.rounded_rectangle([(x, y), (x + card_w, y + card_h)], radius=12, fill=th.bg_color, outline=th.primary, width=2)
        # Accent top bar
        draw.rounded_rectangle([(x + 2, y + 2), (x + card_w - 2, y + 8)], radius=4, fill=th.primary)
        # Inner mock card
        draw.rounded_rectangle([(x + 12, y + 55), (x + card_w - 12, y + card_h - 15)], radius=8, fill=th.card_bg, outline=th.card_border, width=1)

        # Emoji & Theme title
        th_title = th.name.split("(")[0].strip()
        draw.text((x + 15, y + 18), f"{th.emoji} {th_title}", fill=th.text_title)

        # Mode badge
        mode_text = "DARK" if th.dark_mode else "LIGHT"
        draw.rounded_rectangle([(x + card_w - 55, y + 18), (x + card_w - 12, y + 36)], radius=4, fill=th.badge_bg)
        draw.text((x + card_w - 48, y + 21), mode_text, fill=th.badge_text)

        # Mini elements
        draw.rounded_rectangle([(x + 22, y + 70), (x + 90, y + 86)], radius=4, fill=th.badge_bg)
        draw.text((x + 28, y + 72), "SLAYD 01", fill=th.badge_text)

        draw.rounded_rectangle([(x + 22, y + 98), (x + card_w - 30, y + 108)], radius=2, fill=th.text_title)
        draw.rounded_rectangle([(x + 22, y + 115), (x + card_w - 60, y + 121)], radius=2, fill=th.text_muted)

        draw.rounded_rectangle([(x + 22, y + 135), (x + card_w // 2 + 5, y + 185)], radius=4, fill=th.bg_color, outline=th.primary, width=1)
        draw.rounded_rectangle([(x + card_w // 2 + 15, y + 135), (x + card_w - 22, y + 185)], radius=4, fill=th.bg_color, outline=th.secondary, width=1)
        draw.text((x + 30, y + 145), "85%", fill=th.primary)
        draw.text((x + card_w // 2 + 25, y + 145), "3.5X", fill=th.secondary)

        for c_i, color in enumerate([th.primary, th.secondary, th.badge_bg]):
            dot_x = x + 25 + c_i * 20
            draw.ellipse([(dot_x, y + 205), (dot_x + 12, y + 217)], fill=color)

    img.save(out_path, "PNG", quality=95)
    return out_path


def fetch_topic_image(keyword: str) -> Optional[str]:
    """Mavzuga mos real fotosuratni yuklab oladi va keshlaydi."""
    if not keyword:
        return None
    clean_kw = "".join(c for c in keyword if c.isalnum() or c in (" ", "_", "-")).strip()
    if not clean_kw:
        return None

    file_hash = hashlib.md5(clean_kw.encode("utf-8")).hexdigest()
    cached_path = os.path.join(config.IMAGE_CACHE_DIR, f"{file_hash}.jpg")
    if os.path.exists(cached_path) and os.path.getsize(cached_path) > 2000:
        return cached_path

    # 1. Pollinations AI orqali mavzuga mos rasm generatsiya qilish
    try:
        encoded_kw = urllib.parse.quote(clean_kw.replace(" ", "_"))
        pol_url = f"https://image.pollinations.ai/prompt/{encoded_kw}?width=800&height=600&nologo=true"
        r = requests.get(pol_url, timeout=3.0)
        if r.status_code == 200 and len(r.content) > 3000:
            with open(cached_path, "wb") as f:
                f.write(r.content)
            return cached_path
    except Exception:
        pass

    # 2. Picsum Photos orqali zaxira foto
    try:
        seed = abs(hash(clean_kw)) % 1000
        picsum_url = f"https://picsum.photos/seed/{seed}/800/600"
        r = requests.get(picsum_url, timeout=2.5)
        if r.status_code == 200 and len(r.content) > 3000:
            with open(cached_path, "wb") as f:
                f.write(r.content)
            return cached_path
    except Exception:
        pass

    return None


def create_presentation_file(
    content: PresentationContent,
    theme_key: str = "dark_tech",
    output_path: Optional[str] = None,
    author_name: Optional[str] = None,
    logo_path: Optional[str] = None,
) -> str:
    """
    PresentationContent obyektidan 16:9 formatdagi chiroyli PPTX faylini yaratadi.
    """
    theme = config.THEMES.get(theme_key, config.THEMES[config.DEFAULT_THEME])
    prs = Presentation()
    
    # 16:9 Widescreen o'lchamlari (13.333 x 7.5 dyuym)
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    
    blank_layout = prs.slide_layouts[6]  # Toza bo'sh slayd layouti
    
    total_slides = len(content.slides)
    
    for idx, slide_data in enumerate(content.slides):
        slide = prs.slides.add_slide(blank_layout)
        _render_slide_background(slide, theme, prs.slide_width, prs.slide_height)
        
        # Slayd layout turiga qarab chizish
        if slide_data.layout == "title_slide" or idx == 0:
            _render_title_slide(slide, slide_data, theme, prs.slide_width, prs.slide_height, author_name=author_name, logo_path=logo_path)
        elif slide_data.layout == "chart_slide" or (slide_data.layout == "stats_metrics" and idx % 2 == 1 and slide_data.stats):
            _render_chart_slide(slide, slide_data, theme, idx + 1, total_slides, author_name=author_name, logo_path=logo_path)
        elif slide_data.layout == "stats_metrics" and slide_data.stats:
            _render_stats_slide(slide, slide_data, theme, idx + 1, total_slides, author_name=author_name, logo_path=logo_path)
        elif slide_data.layout == "comparison" and (slide_data.comparison_col1 or slide_data.comparison_col2):
            _render_comparison_slide(slide, slide_data, theme, idx + 1, total_slides, author_name=author_name, logo_path=logo_path)
        elif slide_data.layout == "timeline_steps" and slide_data.steps:
            _render_timeline_slide(slide, slide_data, theme, idx + 1, total_slides, author_name=author_name, logo_path=logo_path)
        elif slide_data.layout == "matrix_2x2":
            _render_matrix_slide(slide, slide_data, theme, idx + 1, total_slides, author_name=author_name, logo_path=logo_path)
        elif slide_data.layout == "quote_highlight":
            _render_quote_slide(slide, slide_data, theme, idx + 1, total_slides, author_name=author_name, logo_path=logo_path)
        elif slide_data.layout == "checklist_points":
            _render_checklist_slide(slide, slide_data, theme, idx + 1, total_slides, author_name=author_name, logo_path=logo_path)
        elif slide_data.layout == "conclusion":
            _render_conclusion_slide(slide, slide_data, theme, idx + 1, total_slides, author_name=author_name, logo_path=logo_path)
        elif slide_data.image_keyword and (idx % 2 == 1 or idx == 1):
            ai_img = fetch_ai_image_sync(slide_data.image_keyword)
            if ai_img and os.path.exists(ai_img):
                _render_split_image_slide(slide, slide_data, theme, idx + 1, total_slides, ai_img, author_name=author_name, logo_path=logo_path)
            else:
                _render_cards_grid_slide(slide, slide_data, theme, idx + 1, total_slides, author_name=author_name, logo_path=logo_path)
        else:
            _render_cards_grid_slide(slide, slide_data, theme, idx + 1, total_slides, author_name=author_name, logo_path=logo_path)

    # Chiqish fayli nomini belgilash
    if not output_path:
        safe_topic = "".join(c for c in content.topic if c.isalnum() or c in (" ", "_", "-")).strip()
        safe_topic = safe_topic[:30].replace(" ", "_") or "presentation"
        os.makedirs("generated_slides", exist_ok=True)
        output_path = os.path.join("generated_slides", f"{safe_topic}_{theme_key}.pptx")

    prs.save(output_path)
    return output_path


def generate_speaker_speech_file(content: PresentationContent, output_path: Optional[str] = None) -> str:
    """Spiker uchun so'zma-so'z to'liq nutq matnini alohida faylga saqlaydi."""
    lines = [
        f"🎤 TAQDIMOT UCHUN TO'LIQ SPIKER NUTQI (MA'RUZA MATNI)",
        f"Mavzu: {content.topic}",
        f"Slaydlar soni: {len(content.slides)} ta",
        "=" * 60,
        "",
    ]
    for i, s in enumerate(content.slides):
        lines.append(f"📌 {i+1}-SLAYD: {s.title.upper()}")
        if s.subtitle:
            lines.append(f"   Izoh: {s.subtitle}")
        speech = getattr(s, "speaker_speech", None) or getattr(s, "speaker_notes", None) or "Ushbu slayddagi faktlar va asosiy tushunchalarni tinglovchilarga tushuntirib bering."
        lines.append(f"   🗣 NUTQ MATNI:")
        lines.append(f"   \"{speech}\"")
        lines.append("")
        if s.cards:
            lines.append("   📋 Asosiy punktlar:")
            for c in s.cards:
                lines.append(f"   • {c.title}: {c.description}")
        elif s.stats:
            lines.append("   📊 Ko'rsatkichlar:")
            for st in s.stats:
                lines.append(f"   • {st.number} - {st.label} ({st.description or ''})")
        elif s.comparison_col1 and s.comparison_col2:
            lines.append("   ⚖️ Taqqoslash:")
            lines.append(f"     [{s.comparison_col1.header}]: {', '.join(s.comparison_col1.points)}")
            lines.append(f"     [{s.comparison_col2.header}]: {', '.join(s.comparison_col2.points)}")
        elif s.steps:
            lines.append("   🚀 Ketma-ket qadamlar:")
            for step in s.steps:
                lines.append(f"   • {step.title}: {step.description}")
        elif getattr(s, "matrix_items", None):
            lines.append("   🔲 Matritsa yo'nalishlari:")
            for mi in s.matrix_items:
                lines.append(f"   • {mi.title}: {mi.description}")
        elif getattr(s, "checklist", None):
            lines.append("   ✅ Muhim qoidalar / Tekshiruv:")
            for cl in s.checklist:
                lines.append(f"   ✓ {cl}")
        elif getattr(s, "quote_text", None):
            lines.append(f"   💬 Iqtibos: \"{s.quote_text}\" ({getattr(s, 'quote_author', '') or ''})")
        lines.append("-" * 60)
        lines.append("")

    if not output_path:
        safe_topic = "".join(c for c in content.topic if c.isalnum() or c in (" ", "_", "-")).strip()
        safe_topic = safe_topic[:30].replace(" ", "_") or "speech"
        os.makedirs("generated_slides", exist_ok=True)
        output_path = os.path.join("generated_slides", f"{safe_topic}_nutq.txt")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return output_path



def _render_slide_background(slide, theme: ColorTheme, width, height):
    """Slayd orqa foni va tepa qismidagi nafis accent chizig'i."""
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, width, height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = RGBColor(*theme.bg_color)
    bg.line.fill.background()

    # Tepa qismidagi yorqin dekorativ chiziq
    accent_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, width, Inches(0.08))
    accent_bar.fill.solid()
    accent_bar.fill.fore_color.rgb = RGBColor(*theme.primary)
    accent_bar.line.fill.background()


def _render_header(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int, author_name: Optional[str] = None, logo_path: Optional[str] = None):
    """Har bir slayd uchun standart zamonaviy header va footer."""
    # Logo mavjud bo'lsa yuqori o'ng burchakka joylashtirish
    if logo_path and os.path.exists(logo_path):
        try:
            slide.shapes.add_picture(logo_path, Inches(11.2), Inches(0.4), height=Inches(0.65))
        except Exception:
            pass

    # Kategoriya tegi (Badge Pill)
    badge = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(0.9),
        Inches(0.45),
        Inches(2.5),
        Inches(0.38),
    )
    badge.fill.solid()
    badge.fill.fore_color.rgb = RGBColor(*theme.badge_bg)
    badge.line.color.rgb = RGBColor(*theme.primary)
    badge.line.width = Pt(1)
    
    tf_b = badge.text_frame
    tf_b.word_wrap = True
    p_b = tf_b.paragraphs[0]
    p_b.text = (slide_data.category_badge or "ASOSIY").upper()
    p_b.font.size = Pt(10)
    p_b.font.bold = True
    p_b.font.name = FONT_FAMILY_TITLE
    p_b.font.color.rgb = RGBColor(*theme.badge_text)
    p_b.alignment = PP_ALIGN.CENTER

    # Slayd Sarlavhasi va Subtitle
    title_box = slide.shapes.add_textbox(Inches(0.9), Inches(0.95), Inches(10.2 if (logo_path and os.path.exists(logo_path)) else 11.5), Inches(1.3))
    tf_t = title_box.text_frame
    tf_t.word_wrap = True
    tf_t.margin_left = tf_t.margin_right = tf_t.margin_top = tf_t.margin_bottom = 0

    p_title = tf_t.paragraphs[0]
    p_title.text = slide_data.title
    p_title.font.size = Pt(26)
    p_title.font.bold = True
    p_title.font.name = FONT_FAMILY_TITLE
    p_title.font.color.rgb = RGBColor(*theme.text_title)

    if slide_data.subtitle:
        p_sub = tf_t.add_paragraph()
        p_sub.text = slide_data.subtitle
        p_sub.font.size = Pt(14)
        p_sub.font.name = FONT_FAMILY_BODY
        p_sub.font.color.rgb = RGBColor(*theme.text_muted)
        p_sub.space_before = Pt(4)

    # Footer (Slayd raqami va brending)
    footer_box = slide.shapes.add_textbox(Inches(0.9), Inches(6.9), Inches(11.5), Inches(0.4))
    tf_f = footer_box.text_frame
    p_f = tf_f.paragraphs[0]
    author_tag = f"  •  👨‍💻 Tayyorladi: {author_name}" if author_name else ""
    p_f.text = f"@SlaydchiAkabot  •  Slayd {current_num} / {total_slides}{author_tag}"
    p_f.font.size = Pt(10)
    p_f.font.name = FONT_FAMILY_BODY
    p_f.font.color.rgb = RGBColor(*theme.text_muted)


def _render_title_slide(slide, slide_data: SlideContent, theme: ColorTheme, width, height, author_name: Optional[str] = None, logo_path: Optional[str] = None):
    """Zamonaviy Title (Muqova) slaydi real rasm va mualliflik bilan."""
    # Markazdagi katta karta / konteyner
    card_w = Inches(11.5)
    card_h = Inches(5.8)
    card_left = Inches(0.9)
    card_top = Inches(0.85)

    container = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        card_left,
        card_top,
        card_w,
        card_h,
    )
    container.fill.solid()
    container.fill.fore_color.rgb = RGBColor(*theme.card_bg)
    container.line.color.rgb = RGBColor(*theme.card_border)
    container.line.width = Pt(1.5)

    # Logo mavjud bo'lsa sarlavha kartasi yuqori o'ngiga joylashtirish
    if logo_path and os.path.exists(logo_path):
        try:
            slide.shapes.add_picture(logo_path, card_left + card_w - Inches(1.8), card_top + Inches(0.45), height=Inches(0.75))
        except Exception:
            pass

    # Mavzuga mos rasm yuklash va o'ng tomonga joylashtirish
    img_kw = getattr(slide_data, "image_keyword", None) or slide_data.title
    img_path = fetch_topic_image(img_kw) if img_kw else None

    text_width = card_w - Inches(1.6)
    if img_path and os.path.exists(img_path):
        try:
            img_w = Inches(4.3)
            img_h = Inches(4.8)
            img_left = card_left + card_w - img_w - Inches(0.5)
            img_top = card_top + Inches(0.5)
            slide.shapes.add_picture(img_path, img_left, img_top, img_w, img_h)
            text_width = Inches(5.9)
        except Exception:
            pass

    # Kategoriya tegi
    badge = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        card_left + Inches(0.8),
        card_top + Inches(0.8),
        Inches(3.2),
        Inches(0.45),
    )
    badge.fill.solid()
    badge.fill.fore_color.rgb = RGBColor(*theme.badge_bg)
    badge.line.color.rgb = RGBColor(*theme.primary)
    badge.line.width = Pt(1)
    
    tf_b = badge.text_frame
    p_b = tf_b.paragraphs[0]
    p_b.text = (slide_data.category_badge or "TAQDIMOT").upper()
    p_b.font.size = Pt(11)
    p_b.font.bold = True
    p_b.font.name = FONT_FAMILY_TITLE
    p_b.font.color.rgb = RGBColor(*theme.badge_text)
    p_b.alignment = PP_ALIGN.CENTER

    # Asosiy Katta Sarlavha
    title_box = slide.shapes.add_textbox(
        card_left + Inches(0.8),
        card_top + Inches(1.5),
        text_width,
        Inches(2.2),
    )
    tf_t = title_box.text_frame
    tf_t.word_wrap = True
    p_t = tf_t.paragraphs[0]
    p_t.text = slide_data.title
    p_t.font.size = Pt(36) if img_path else Pt(40)
    p_t.font.bold = True
    p_t.font.name = FONT_FAMILY_TITLE
    p_t.font.color.rgb = RGBColor(*theme.text_title)

    if slide_data.subtitle:
        p_sub = tf_t.add_paragraph()
        p_sub.text = slide_data.subtitle
        p_sub.font.size = Pt(16)
        p_sub.font.name = FONT_FAMILY_BODY
        p_sub.font.color.rgb = RGBColor(*theme.text_muted)
        p_sub.space_before = Pt(10)

    # Muallif / Brending yoki Takeaway
    if author_name:
        author_box = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            card_left + Inches(0.8),
            card_top + Inches(4.7),
            Inches(4.5),
            Inches(0.5),
        )
        author_box.fill.solid()
        author_box.fill.fore_color.rgb = RGBColor(*theme.badge_bg)
        author_box.line.color.rgb = RGBColor(*theme.secondary)
        author_box.line.width = Pt(1)

        tf_a = author_box.text_frame
        p_a = tf_a.paragraphs[0]
        p_a.text = f"👨‍💻 Tayyorladi: {author_name}"
        p_a.font.size = Pt(12)
        p_a.font.bold = True
        p_a.font.name = FONT_FAMILY_TITLE
        p_a.font.color.rgb = RGBColor(*theme.secondary)
        p_a.alignment = PP_ALIGN.CENTER
    elif slide_data.highlight_takeaway:
        hl_box = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            card_left + Inches(0.8),
            card_top + Inches(4.4),
            text_width,
            Inches(0.9),
        )
        hl_box.fill.solid()
        hl_box.fill.fore_color.rgb = RGBColor(*theme.bg_color)
        hl_box.line.color.rgb = RGBColor(*theme.primary)
        hl_box.line.width = Pt(1)

        tf_hl = hl_box.text_frame
        tf_hl.word_wrap = True
        p_hl = tf_hl.paragraphs[0]
        p_hl.text = f"💡 {slide_data.highlight_takeaway}"
        p_hl.font.size = Pt(13)
        p_hl.font.name = FONT_FAMILY_BODY
        p_hl.font.color.rgb = RGBColor(*theme.text_body)
        p_hl.alignment = PP_ALIGN.LEFT



def _render_split_image_slide(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int, image_path: str, author_name: Optional[str] = None, logo_path: Optional[str] = None):
    """60/40 Split layout: chapda aniq ma'lumotlar va kartalar, o'ngda fotorealistik AI rasm."""
    _render_header(slide, slide_data, theme, current_num, total_slides, author_name=author_name, logo_path=logo_path)

    items = slide_data.cards or []
    if not items:
        items = [
            CardItem(title="Asosiy tushuncha", description=slide_data.title, badge="01"),
            CardItem(title="Amaliy ahamiyat", description=slide_data.subtitle or "Muhim strategik omil", badge="02")
        ]

    count = min(len(items), 3)
    left_w = Inches(6.8)
    left_start = Inches(0.9)
    content_top = Inches(2.4)
    total_h = Inches(4.3)
    gap = Inches(0.25)
    card_h = (total_h - gap * (count - 1)) / count

    for i in range(count):
        item = items[i]
        c_top = content_top + i * (card_h + gap)

        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left_start, c_top, left_w, card_h)
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(*theme.card_bg)
        card.line.color.rgb = RGBColor(*theme.card_border)
        card.line.width = Pt(1.5)

        tbox = slide.shapes.add_textbox(left_start + Inches(0.25), c_top + Inches(0.12), left_w - Inches(0.5), card_h - Inches(0.24))
        tf = tbox.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

        p_b = tf.paragraphs[0]
        p_b.text = (item.badge or f"0{i+1}").upper()
        p_b.font.size = Pt(10)
        p_b.font.bold = True
        p_b.font.name = FONT_FAMILY_TITLE
        p_b.font.color.rgb = RGBColor(*theme.secondary)

        p_t = tf.add_paragraph()
        p_t.text = item.title
        p_t.font.size = Pt(15)
        p_t.font.bold = True
        p_t.font.name = FONT_FAMILY_TITLE
        p_t.font.color.rgb = RGBColor(*theme.text_title)
        p_t.space_before = Pt(3)
        p_t.space_after = Pt(3)

        p_d = tf.add_paragraph()
        p_d.text = item.description
        p_d.font.size = Pt(12)
        p_d.font.name = FONT_FAMILY_BODY
        p_d.font.color.rgb = RGBColor(*theme.text_body)

    # O'ng tomonda AI rasm
    right_left = Inches(8.0)
    img_w = Inches(4.4)
    img_h = Inches(4.3)

    img_frame = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, right_left, content_top, img_w, img_h)
    img_frame.fill.solid()
    img_frame.fill.fore_color.rgb = RGBColor(*theme.card_bg)
    img_frame.line.color.rgb = RGBColor(*theme.primary)
    img_frame.line.width = Pt(2)

    if image_path and os.path.exists(image_path):
        try:
            slide.shapes.add_picture(image_path, right_left + Inches(0.08), content_top + Inches(0.08), img_w - Inches(0.16), img_h - Inches(0.16))
        except Exception as e:
            logger.warning(f"PPTX rasm joylashda ogohlantirish: {e}")


def _render_cards_grid_slide(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int, author_name: Optional[str] = None, logo_path: Optional[str] = None):
    """3 yoki 4 ta kartochkali zamonaviy grid layout."""
    _render_header(slide, slide_data, theme, current_num, total_slides, author_name=author_name, logo_path=logo_path)

    items = slide_data.cards or []
    if not items:
        items = [CardItem(title="Asosiy punkt", description=slide_data.title, badge="01")]

    count = min(len(items), 4)
    total_w = Inches(11.5)
    gap = Inches(0.3)
    card_w = (total_w - gap * (count - 1)) / count
    card_top = Inches(2.5)
    card_h = Inches(4.1)

    for i in range(count):
        item = items[i]
        left = Inches(0.9) + i * (card_w + gap)

        # Karta konteyneri
        card = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            left,
            card_top,
            card_w,
            card_h,
        )
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(*theme.card_bg)
        card.line.color.rgb = RGBColor(*theme.card_border)
        card.line.width = Pt(1.5)

        # Kartaning tepa qismidagi dekorativ chiziq
        c_accent = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            left + Inches(0.2),
            card_top + Inches(0.2),
            Inches(0.8),
            Inches(0.08),
        )
        c_accent.fill.solid()
        c_accent.fill.fore_color.rgb = RGBColor(*theme.primary)
        c_accent.line.fill.background()

        # Matn konteyneri
        tbox = slide.shapes.add_textbox(
            left + Inches(0.25),
            card_top + Inches(0.4),
            card_w - Inches(0.5),
            card_h - Inches(0.6),
        )
        tf = tbox.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

        # Karta tegi (Badge)
        badge_text = item.badge or f"0{i+1}"
        p_badge = tf.paragraphs[0]
        p_badge.text = badge_text.upper()
        p_badge.font.size = Pt(11)
        p_badge.font.bold = True
        p_badge.font.name = FONT_FAMILY_TITLE
        p_badge.font.color.rgb = RGBColor(*theme.secondary)

        # Karta Sarlavhasi
        p_title = tf.add_paragraph()
        p_title.text = item.title
        p_title.font.size = Pt(17)
        p_title.font.bold = True
        p_title.font.name = FONT_FAMILY_TITLE
        p_title.font.color.rgb = RGBColor(*theme.text_title)
        p_title.space_before = Pt(8)
        p_title.space_after = Pt(8)

        # Karta Tavsifi
        p_desc = tf.add_paragraph()
        p_desc.text = item.description
        p_desc.font.size = Pt(13)
        p_desc.font.name = FONT_FAMILY_BODY
        p_desc.font.color.rgb = RGBColor(*theme.text_body)


def _render_stats_slide(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int, author_name: Optional[str] = None, logo_path: Optional[str] = None):
    """Statistika va raqamlar infografikasi slaydi."""
    _render_header(slide, slide_data, theme, current_num, total_slides, author_name=author_name, logo_path=logo_path)

    stats = slide_data.stats or []
    count = min(len(stats), 4)
    total_w = Inches(11.5)
    gap = Inches(0.35)
    card_w = (total_w - gap * (count - 1)) / count
    card_top = Inches(2.6)
    card_h = Inches(3.9)

    for i in range(count):
        stat = stats[i]
        left = Inches(0.9) + i * (card_w + gap)

        card = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            left,
            card_top,
            card_w,
            card_h,
        )
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(*theme.card_bg)
        card.line.color.rgb = RGBColor(*theme.card_border)
        card.line.width = Pt(1.5)

        tbox = slide.shapes.add_textbox(
            left + Inches(0.25),
            card_top + Inches(0.4),
            card_w - Inches(0.5),
            card_h - Inches(0.6),
        )
        tf = tbox.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

        # Katta Raqam / Ko'rsatkich
        p_num = tf.paragraphs[0]
        p_num.text = stat.number
        p_num.font.size = Pt(40)
        p_num.font.bold = True
        p_num.font.name = FONT_FAMILY_TITLE
        p_num.font.color.rgb = RGBColor(*theme.primary)

        # Qisqa ko'rsatkich sarlavhasi
        p_label = tf.add_paragraph()
        p_label.text = stat.label
        p_label.font.size = Pt(16)
        p_label.font.bold = True
        p_label.font.name = FONT_FAMILY_TITLE
        p_label.font.color.rgb = RGBColor(*theme.text_title)
        p_label.space_before = Pt(8)
        p_label.space_after = Pt(6)

        # Tavsif
        if stat.description:
            p_desc = tf.add_paragraph()
            p_desc.text = stat.description
            p_desc.font.size = Pt(12)
            p_desc.font.name = FONT_FAMILY_BODY
            p_desc.font.color.rgb = RGBColor(*theme.text_muted)


def _render_chart_slide(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int, author_name: Optional[str] = None, logo_path: Optional[str] = None):
    """Haqiqiy PowerPoint diagrammasi (ustunli yoki doiraviy) bilan boyitilgan tahliliy slayd."""
    _render_header(slide, slide_data, theme, current_num, total_slides, author_name=author_name, logo_path=logo_path)

    # Chap tomonda: Tahlil va xulosalar kartochkasi
    card_left = Inches(0.9)
    card_top = Inches(2.4)
    card_w = Inches(4.2)
    card_h = Inches(4.2)

    container = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        card_left,
        card_top,
        card_w,
        card_h,
    )
    container.fill.solid()
    container.fill.fore_color.rgb = RGBColor(*theme.card_bg)
    container.line.color.rgb = RGBColor(*theme.card_border)
    container.line.width = Pt(1.5)

    tbox = slide.shapes.add_textbox(card_left + Inches(0.3), card_top + Inches(0.3), card_w - Inches(0.6), card_h - Inches(0.6))
    tf = tbox.text_frame
    tf.word_wrap = True

    p0 = tf.paragraphs[0]
    p0.text = "📊 ASOSIY DINAMIKA"
    p0.font.size = Pt(12)
    p0.font.bold = True
    p0.font.name = FONT_FAMILY_TITLE
    p0.font.color.rgb = RGBColor(*theme.primary)

    stats = slide_data.stats or []
    if stats:
        for st in stats[:3]:
            p_s = tf.add_paragraph()
            p_s.text = f"• {st.label}: {st.number}"
            p_s.font.size = Pt(13)
            p_s.font.bold = True
            p_s.font.name = FONT_FAMILY_TITLE
            p_s.font.color.rgb = RGBColor(*theme.text_title)
            p_s.space_before = Pt(6)

            if st.description:
                p_sd = tf.add_paragraph()
                p_sd.text = f"  {st.description[:60]}"
                p_sd.font.size = Pt(11)
                p_sd.font.name = FONT_FAMILY_BODY
                p_sd.font.color.rgb = RGBColor(*theme.text_muted)
    else:
        p_desc = tf.add_paragraph()
        p_desc.text = slide_data.subtitle or "Ma'lumotlar tahlili va ko'rsatkichlar nisbati diagrammada aks ettirilgan."
        p_desc.font.size = Pt(13)
        p_desc.font.name = FONT_FAMILY_BODY
        p_desc.font.color.rgb = RGBColor(*theme.text_body)
        p_desc.space_before = Pt(8)

    # O'ng tomonda: Haqiqiy PowerPoint diagrammasi
    chart_left = Inches(5.4)
    chart_top = Inches(2.4)
    chart_w = Inches(7.0)
    chart_h = Inches(4.2)

    chart_data = CategoryChartData()
    categories = []
    values = []

    if stats:
        for st in stats[:5]:
            categories.append(st.label[:16])
            clean_digits = "".join(c for c in st.number if c.isdigit() or c == ".")
            try:
                val = float(clean_digits) if clean_digits else 50.0
            except ValueError:
                val = 50.0
            values.append(val if val > 0 else 25.0)
    else:
        categories = ["1-Chorak", "2-Chorak", "3-Chorak", "4-Chorak"]
        values = [25.0, 50.0, 75.0, 95.0]

    chart_data.categories = categories
    series_name = getattr(slide_data, "category_badge", "Ko'rsatkichlar") or "Ko'rsatkichlar"
    chart_data.add_series(series_name, values)

    is_pie = getattr(slide_data, "chart_type", "") == "pie"
    chart_type = XL_CHART_TYPE.PIE if is_pie else XL_CHART_TYPE.COLUMN_CLUSTERED

    chart_shape = slide.shapes.add_chart(
        chart_type, chart_left, chart_top, chart_w, chart_h, chart_data
    )
    chart = chart_shape.chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.legend.include_in_layout = False

    try:
        plot = chart.plots[0]
        plot.has_data_labels = True
    except Exception:
        pass


def _render_comparison_slide(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int, author_name: Optional[str] = None, logo_path: Optional[str] = None):
    """Ikki ustunli solishtirish (Masalan: An'anaviy vs Innovatsion) slaydi."""
    _render_header(slide, slide_data, theme, current_num, total_slides, author_name=author_name, logo_path=logo_path)

    col1 = slide_data.comparison_col1 or ComparisonColumn(header="Variant A", points=["Standart imkoniyatlar"])
    col2 = slide_data.comparison_col2 or ComparisonColumn(header="Variant B", points=["Kengaytirilgan imkoniyatlar"])

    card_w = Inches(5.6)
    card_h = Inches(4.2)
    card_top = Inches(2.4)
    gap = Inches(0.3)

    cols = [
        (col1, Inches(0.9), theme.card_bg, theme.card_border, theme.text_muted, "✕ "),
        (col2, Inches(0.9) + card_w + gap, theme.card_bg, theme.primary, theme.primary, "✓ "),
    ]

    for col_data, left, c_bg, border_color, accent_color, bullet_icon in cols:
        card = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            left,
            card_top,
            card_w,
            card_h,
        )
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(*c_bg)
        card.line.color.rgb = RGBColor(*border_color)
        card.line.width = Pt(2)

        tbox = slide.shapes.add_textbox(
            left + Inches(0.4),
            card_top + Inches(0.35),
            card_w - Inches(0.8),
            card_h - Inches(0.7),
        )
        tf = tbox.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

        # Ustun tegi
        if col_data.badge:
            p_b = tf.paragraphs[0]
            p_b.text = col_data.badge.upper()
            p_b.font.size = Pt(11)
            p_b.font.bold = True
            p_b.font.name = FONT_FAMILY_TITLE
            p_b.font.color.rgb = RGBColor(*accent_color)
            p_header = tf.add_paragraph()
        else:
            p_header = tf.paragraphs[0]

        # Ustun Sarlavhasi
        p_header.text = col_data.header
        p_header.font.size = Pt(22)
        p_header.font.bold = True
        p_header.font.name = FONT_FAMILY_TITLE
        p_header.font.color.rgb = RGBColor(*theme.text_title)
        p_header.space_after = Pt(14)

        # Punktlar
        for pt in col_data.points:
            p_pt = tf.add_paragraph()
            p_pt.text = f"{bullet_icon}{pt}"
            p_pt.font.size = Pt(14)
            p_pt.font.name = FONT_FAMILY_BODY
            p_pt.font.color.rgb = RGBColor(*theme.text_body)
            p_pt.space_after = Pt(8)


def _render_timeline_slide(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int, author_name: Optional[str] = None, logo_path: Optional[str] = None):
    """Bosqichma-bosqich jarayon yoki timeline slaydi."""
    _render_header(slide, slide_data, theme, current_num, total_slides, author_name=author_name, logo_path=logo_path)

    steps = slide_data.steps or []
    count = min(len(steps), 4)
    total_w = Inches(11.5)
    gap = Inches(0.3)
    card_w = (total_w - gap * (count - 1)) / count
    card_top = Inches(2.6)
    card_h = Inches(3.9)

    for i in range(count):
        step = steps[i]
        left = Inches(0.9) + i * (card_w + gap)

        card = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            left,
            card_top,
            card_w,
            card_h,
        )
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(*theme.card_bg)
        card.line.color.rgb = RGBColor(*theme.card_border)
        card.line.width = Pt(1.5)

        # Bosqich raqami aylana ko'rinishida
        circle = slide.shapes.add_shape(
            MSO_SHAPE.OVAL,
            left + Inches(0.3),
            card_top + Inches(0.3),
            Inches(0.65),
            Inches(0.65),
        )
        circle.fill.solid()
        circle.fill.fore_color.rgb = RGBColor(*theme.primary)
        circle.line.fill.background()

        tf_c = circle.text_frame
        p_c = tf_c.paragraphs[0]
        p_c.text = str(i + 1)
        p_c.font.size = Pt(14)
        p_c.font.bold = True
        p_c.font.color.rgb = RGBColor(*theme.bg_color)
        p_c.alignment = PP_ALIGN.CENTER

        # Matn konteyneri
        tbox = slide.shapes.add_textbox(
            left + Inches(0.3),
            card_top + Inches(1.15),
            card_w - Inches(0.6),
            card_h - Inches(1.3),
        )
        tf = tbox.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

        # Bosqich tegi
        p_badge = tf.paragraphs[0]
        p_badge.text = (step.badge or f"QADAM {i+1}").upper()
        p_badge.font.size = Pt(10)
        p_badge.font.bold = True
        p_badge.font.color.rgb = RGBColor(*theme.secondary)

        # Bosqich Sarlavhasi
        p_title = tf.add_paragraph()
        p_title.text = step.title
        p_title.font.size = Pt(17)
        p_title.font.bold = True
        p_title.font.color.rgb = RGBColor(*theme.text_title)
        p_title.space_before = Pt(4)
        p_title.space_after = Pt(8)

        # Bosqich Tavsifi
        p_desc = tf.add_paragraph()
        p_desc.text = step.description
        p_desc.font.size = Pt(13)
        p_desc.font.name = FONT_FAMILY_BODY
        p_desc.font.color.rgb = RGBColor(*theme.text_body)


def _render_conclusion_slide(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int, author_name: Optional[str] = None, logo_path: Optional[str] = None):
    """Xulosa, muhim iqtibos va asosiy chaqiriq slaydi."""
    _render_header(slide, slide_data, theme, current_num, total_slides, author_name=author_name, logo_path=logo_path)

    card_w = Inches(11.5)
    card_left = Inches(0.9)

    # Asosiy katta xulosa kartasi
    main_h = Inches(2.2)
    main_top = Inches(2.4)

    main_card = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        card_left,
        main_top,
        card_w,
        main_h,
    )
    main_card.fill.solid()
    main_card.fill.fore_color.rgb = RGBColor(*theme.card_bg)
    main_card.line.color.rgb = RGBColor(*theme.primary)
    main_card.line.width = Pt(2)

    tbox = slide.shapes.add_textbox(
        card_left + Inches(0.5),
        main_top + Inches(0.4),
        card_w - Inches(1.0),
        main_h - Inches(0.8),
    )
    tf = tbox.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

    p_quote = tf.paragraphs[0]
    p_quote.text = slide_data.highlight_takeaway or "Katta natijalar bugungi to'g'ri qarorlardan boshlanadi."
    p_quote.font.size = Pt(22)
    p_quote.font.bold = True
    p_quote.font.italic = True
    p_quote.font.name = FONT_FAMILY_TITLE
    p_quote.font.color.rgb = RGBColor(*theme.primary)

    # Pastki 2 ta qisqa xulosa kartalari
    cards = slide_data.cards or [
        CardItem(title="Muhim Xulosa", description="Amalga oshirilgan tahlillar strategik yo'nalish to'g'riligini ko'rsatmoqda.", badge="Strategiya"),
        CardItem(title="Keyingi Qadamlar", description="Loyihani to'liq quvvatda ishga tushirishga tayyormiz.", badge="Harakat"),
    ]

    count = min(len(cards), 2)
    sub_w = (card_w - Inches(0.4)) / 2
    sub_top = Inches(4.85)
    sub_h = Inches(1.8)

    for i in range(count):
        c_item = cards[i]
        c_left = card_left + i * (sub_w + Inches(0.4))

        sub_card = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            c_left,
            sub_top,
            sub_w,
            sub_h,
        )
        sub_card.fill.solid()
        sub_card.fill.fore_color.rgb = RGBColor(*theme.card_bg)
        sub_card.line.color.rgb = RGBColor(*theme.card_border)
        sub_card.line.width = Pt(1.5)

        s_tbox = slide.shapes.add_textbox(
            c_left + Inches(0.3),
            sub_top + Inches(0.25),
            sub_w - Inches(0.6),
            sub_h - Inches(0.5),
        )
        s_tf = s_tbox.text_frame
        s_tf.word_wrap = True
        s_tf.margin_left = s_tf.margin_right = s_tf.margin_top = s_tf.margin_bottom = 0

        p_t = s_tf.paragraphs[0]
        p_t.text = c_item.title
        p_t.font.size = Pt(16)
        p_t.font.bold = True
        p_t.font.name = FONT_FAMILY_TITLE
        p_t.font.color.rgb = RGBColor(*theme.text_title)

        p_d = s_tf.add_paragraph()
        p_d.text = c_item.description
        p_d.font.size = Pt(12)
        p_d.font.name = FONT_FAMILY_BODY
        p_d.font.color.rgb = RGBColor(*theme.text_body)
        p_d.space_before = Pt(4)


def _render_matrix_slide(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int, author_name: Optional[str] = None, logo_path: Optional[str] = None):
    """2x2 Quadrant matritsa slaydi (4 ta bo'lim/yo'nalish)."""
    _render_header(slide, slide_data, theme, current_num, total_slides, author_name=author_name, logo_path=logo_path)

    items = slide_data.matrix_items or slide_data.cards or []
    default_badges = ["01", "02", "03", "04"]
    default_titles = ["Strategik Yo'nalish", "Innovatsion Yechim", "Resurslar & Imkoniyat", "Natijadorlik & O'sish"]
    default_descs = [
        "Bozor tahlili va yangi imkoniyatlarni chuqur o'rganish orqali to'g'ri strategiya tanlash.",
        "Zamonaviy AI va raqamli texnologiyalarni amaliyotga joriy etish.",
        "Mavjud moddiy, texnik va insoniy resurslarni maqsadli taqsimlash.",
        "Uzoq muddatli barqarorlik va yuqori samaradorlik ko'rsatkichlariga erishish.",
    ]

    full_items = []
    for i in range(4):
        if i < len(items):
            full_items.append(items[i])
        else:
            full_items.append(CardItem(title=default_titles[i], description=default_descs[i], badge=default_badges[i]))

    col_w = Inches(5.6)
    row_h = Inches(1.95)
    gap_x = Inches(0.3)
    gap_y = Inches(0.25)
    start_x = Inches(0.9)
    start_y = Inches(2.45)

    positions = [
        (start_x, start_y),                          # Top-left
        (start_x + col_w + gap_x, start_y),          # Top-right
        (start_x, start_y + row_h + gap_y),          # Bottom-left
        (start_x + col_w + gap_x, start_y + row_h + gap_y),  # Bottom-right
    ]

    for idx, (c_left, c_top) in enumerate(positions):
        item = full_items[idx]

        # Karta foni
        card = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            c_left,
            c_top,
            col_w,
            row_h,
        )
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(*theme.card_bg)
        card.line.color.rgb = RGBColor(*theme.card_border)
        card.line.width = Pt(1.5)

        # Tepasida kichik rangli badge pill
        badge_val = item.badge or f"0{idx+1}"
        badge_shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            c_left + Inches(0.3),
            c_top + Inches(0.2),
            Inches(1.2),
            Inches(0.32),
        )
        badge_shape.fill.solid()
        badge_shape.fill.fore_color.rgb = RGBColor(*theme.badge_bg)
        badge_shape.line.color.rgb = RGBColor(*theme.primary)
        badge_shape.line.width = Pt(1)

        tf_b = badge_shape.text_frame
        tf_b.word_wrap = True
        p_b = tf_b.paragraphs[0]
        p_b.text = badge_val.upper()
        p_b.font.size = Pt(10)
        p_b.font.bold = True
        p_b.font.name = FONT_FAMILY_TITLE
        p_b.font.color.rgb = RGBColor(*theme.badge_text)
        p_b.alignment = PP_ALIGN.CENTER

        # Matn konteyneri
        tbox = slide.shapes.add_textbox(
            c_left + Inches(0.3),
            c_top + Inches(0.58),
            col_w - Inches(0.6),
            row_h - Inches(0.68),
        )
        tf = tbox.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

        p_title = tf.paragraphs[0]
        p_title.text = item.title
        p_title.font.size = Pt(15)
        p_title.font.bold = True
        p_title.font.name = FONT_FAMILY_TITLE
        p_title.font.color.rgb = RGBColor(*theme.text_title)

        p_desc = tf.add_paragraph()
        p_desc.text = item.description
        p_desc.font.size = Pt(12)
        p_desc.font.name = FONT_FAMILY_BODY
        p_desc.font.color.rgb = RGBColor(*theme.text_body)
        p_desc.space_before = Pt(4)


def _render_quote_slide(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int, author_name: Optional[str] = None, logo_path: Optional[str] = None):
    """Markazlashtirilgan katta iqtibos / asosiy tezis slaydi."""
    _render_header(slide, slide_data, theme, current_num, total_slides, author_name=author_name, logo_path=logo_path)

    card_w = Inches(11.5)
    card_h = Inches(4.15)
    card_left = Inches(0.9)
    card_top = Inches(2.45)

    # Katta qabul qiluvchi karta
    card = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        card_left,
        card_top,
        card_w,
        card_h,
    )
    card.fill.solid()
    card.fill.fore_color.rgb = RGBColor(*theme.card_bg)
    card.line.color.rgb = RGBColor(*theme.primary)
    card.line.width = Pt(2)

    # Chap tomondagi vertikal dekorativ chiziq
    left_accent = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        card_left + Inches(0.5),
        card_top + Inches(0.5),
        Inches(0.12),
        card_h - Inches(1.0),
    )
    left_accent.fill.solid()
    left_accent.fill.fore_color.rgb = RGBColor(*theme.primary)
    left_accent.line.fill.background()

    # Katta tirnoq belgisi (decorative quote icon)
    q_icon_box = slide.shapes.add_textbox(
        card_left + Inches(0.85),
        card_top + Inches(0.2),
        Inches(1.5),
        Inches(1.0),
    )
    tf_q = q_icon_box.text_frame
    p_q = tf_q.paragraphs[0]
    p_q.text = "“"
    p_q.font.size = Pt(72)
    p_q.font.bold = True
    p_q.font.name = FONT_FAMILY_TITLE
    p_q.font.color.rgb = RGBColor(*theme.secondary)

    # Iqtibos matni
    quote_body = slide_data.quote_text or slide_data.highlight_takeaway or slide_data.subtitle or slide_data.title
    tbox = slide.shapes.add_textbox(
        card_left + Inches(0.9),
        card_top + Inches(1.3),
        card_w - Inches(1.5),
        Inches(1.8),
    )
    tf = tbox.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

    p_text = tf.paragraphs[0]
    p_text.text = f'"{quote_body}"'
    p_text.font.size = Pt(22)
    p_text.font.bold = True
    p_text.font.italic = True
    p_text.font.name = FONT_FAMILY_TITLE
    p_text.font.color.rgb = RGBColor(*theme.text_title)

    # Muallif / Manba tegi
    author = slide_data.quote_author or "Strategik xulosa va tahliliy qarash"
    badge_shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        card_left + Inches(0.9),
        card_top + Inches(3.3),
        Inches(4.5),
        Inches(0.45),
    )
    badge_shape.fill.solid()
    badge_shape.fill.fore_color.rgb = RGBColor(*theme.badge_bg)
    badge_shape.line.color.rgb = RGBColor(*theme.secondary)
    badge_shape.line.width = Pt(1)

    tf_ab = badge_shape.text_frame
    tf_ab.word_wrap = True
    p_ab = tf_ab.paragraphs[0]
    p_ab.text = f"—  {author}"
    p_ab.font.size = Pt(12)
    p_ab.font.bold = True
    p_ab.font.name = FONT_FAMILY_TITLE
    p_ab.font.color.rgb = RGBColor(*theme.secondary)
    p_ab.alignment = PP_ALIGN.CENTER


def _render_checklist_slide(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int, author_name: Optional[str] = None, logo_path: Optional[str] = None):
    """Checklist va tasdiqlangan qoidalar/punktlar slaydi."""
    _render_header(slide, slide_data, theme, current_num, total_slides, author_name=author_name, logo_path=logo_path)

    items = slide_data.checklist or []
    if not items and slide_data.cards:
        items = [f"{c.title}: {c.description}" for c in slide_data.cards]
    if not items:
        items = [
            "Barcha tahliliy ko'rsatkichlar va ma'lumotlar to'liq tekshirildi",
            "Belgilangan strategik reja va maqsadlarga to'liq moslik ta'minlandi",
            "Potentsial xatarlar oldindan baholanib, chora-tadbirlar ishlab chiqildi",
            "Keyingi bosqichga o'tish uchun barcha zaruriy resurslar va jamoa tayyor",
        ]

    count = min(len(items), 5)
    total_w = Inches(11.5)
    total_h = Inches(4.15)
    gap = Inches(0.18)
    row_h = (total_h - gap * (count - 1)) / count
    left = Inches(0.9)
    top_base = Inches(2.45)

    for i in range(count):
        item_text = items[i]
        row_top = top_base + i * (row_h + gap)

        # Qator foni kartasi
        row_card = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            left,
            row_top,
            total_w,
            row_h,
        )
        row_card.fill.solid()
        row_card.fill.fore_color.rgb = RGBColor(*theme.card_bg)
        row_card.line.color.rgb = RGBColor(*theme.card_border)
        row_card.line.width = Pt(1)

        # Chap tomondagi [ ✓ ] belgisi nishoni
        icon_w = Inches(0.48)
        icon_h = Inches(0.42)
        icon_top = row_top + (row_h - icon_h) / 2
        icon_left = left + Inches(0.3)

        icon_badge = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            icon_left,
            icon_top,
            icon_w,
            icon_h,
        )
        icon_badge.fill.solid()
        icon_badge.fill.fore_color.rgb = RGBColor(*theme.badge_bg)
        icon_badge.line.color.rgb = RGBColor(*theme.primary)
        icon_badge.line.width = Pt(1.5)

        tf_i = icon_badge.text_frame
        p_i = tf_i.paragraphs[0]
        p_i.text = "✓"
        p_i.font.size = Pt(14)
        p_i.font.bold = True
        p_i.font.color.rgb = RGBColor(*theme.primary)
        p_i.alignment = PP_ALIGN.CENTER

        # Matn konteyneri
        text_w = total_w - Inches(1.2)
        tbox = slide.shapes.add_textbox(
            left + Inches(0.95),
            row_top + Inches(0.1),
            text_w,
            row_h - Inches(0.2),
        )
        tf = tbox.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

        p_t = tf.paragraphs[0]
        p_t.text = item_text
        p_t.font.size = Pt(14)
        p_t.font.name = FONT_FAMILY_BODY
        p_t.font.color.rgb = RGBColor(*theme.text_title)


def get_render_font(size: int, bold: bool = False, italic: bool = False) -> ImageFont.ImageFont:
    """Windows, Linux va Docker muhitlarida eng mos TrueType shriftni aniqlaydi va yuklaydi."""
    candidates = []
    if bold and italic:
        candidates = [
            "C:/Windows/Fonts/arialbi.ttf",
            "C:/Windows/Fonts/calibriz.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
        ]
    elif bold:
        candidates = [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ]
    elif italic:
        candidates = [
            "C:/Windows/Fonts/ariali.ttf",
            "C:/Windows/Fonts/calibrii.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
        ]
    else:
        candidates = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]

    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size=size)
            except Exception:
                pass

    font_name = "arialbd.ttf" if bold else "arial.ttf"
    try:
        return ImageFont.truetype(font_name, size=size)
    except Exception:
        pass

    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    max_width: int,
    font: ImageFont.ImageFont,
    fill: Tuple[int, int, int],
    line_spacing: int = 4,
    max_lines: Optional[int] = None,
) -> int:
    """Matnni ko'rsatilgan kenglik bo'yicha so'zma-so'z o'rab, qatorma-qator chizadi.
    Tugallangan Y koordinatasini qaytaradi.
    """
    if not text:
        return y

    words = str(text).split()
    lines = []
    current_line = []

    for word in words:
        test_line = " ".join(current_line + [word])
        try:
            bbox = draw.textbbox((0, 0), test_line, font=font)
            line_w = bbox[2] - bbox[0]
        except Exception:
            line_w = len(test_line) * (getattr(font, "size", 16) * 0.55)

        if line_w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []

    if current_line:
        lines.append(" ".join(current_line))

    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines:
            lines[-1] = lines[-1].rstrip(" .,!?:;") + "..."

    cur_y = y
    for line in lines:
        draw.text((x, cur_y), line, font=font, fill=fill)
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_h = bbox[3] - bbox[1]
        except Exception:
            line_h = getattr(font, "size", 16)
        cur_y += max(line_h, 14) + line_spacing

    return cur_y


def render_slide_to_image(
    slide_data: SlideContent,
    theme: ColorTheme,
    current_num: int,
    total_slides: int,
    author_name: Optional[str] = None,
    logo_path: Optional[str] = None,
) -> Image.Image:
    """Ixtiyoriy bitta slaydni 1280x720 o'lchamdagi yuqori sifatli rasmga aylantiradi."""
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), color=theme.bg_color)
    draw = ImageDraw.Draw(img)

    # Shriftlar
    f_badge = get_render_font(13, bold=True)
    f_title = get_render_font(28, bold=True)
    f_sub = get_render_font(16, italic=True)
    f_card_title = get_render_font(18, bold=True)
    f_body = get_render_font(14)
    f_body_bold = get_render_font(14, bold=True)
    f_footer = get_render_font(13)

    # Yuqori bezak chizig'i
    draw.rectangle([(0, 0), (W, 8)], fill=theme.primary)

    # Asosiy konteyner
    draw.rounded_rectangle([(60, 50), (W - 60, H - 50)], radius=18, fill=theme.card_bg, outline=theme.card_border, width=2)

    # Badge va raqam
    badge_text = (slide_data.category_badge or "SLAYD").upper()
    try:
        bbox_b = draw.textbbox((0, 0), f"📌 {badge_text}", font=f_badge)
        badge_w = max(bbox_b[2] - bbox_b[0] + 28, 100)
    except Exception:
        badge_w = len(badge_text) * 10 + 40

    draw.rounded_rectangle([(100, 75), (100 + badge_w, 110)], radius=6, fill=theme.badge_bg, outline=theme.primary, width=1)
    draw.text((114, 84), f"📌 {badge_text}", font=f_badge, fill=theme.badge_text)

    num_text = f"📊 {current_num} / {total_slides}"
    try:
        bbox_n = draw.textbbox((0, 0), num_text, font=f_badge)
        num_w = max(bbox_n[2] - bbox_n[0] + 28, 90)
    except Exception:
        num_w = 90

    draw.rounded_rectangle([(115 + badge_w, 75), (115 + badge_w + num_w, 110)], radius=6, fill=theme.bg_color, outline=theme.secondary, width=1)
    draw.text((129 + badge_w, 84), num_text, font=f_badge, fill=theme.secondary)

    # Agar logotip bo'lsa yuqori o'ng burchakka joylashtirish
    if logo_path and os.path.exists(logo_path):
        try:
            logo_img = Image.open(logo_path)
            logo_img.thumbnail((150, 48), Image.Resampling.LANCZOS)
            if logo_img.mode in ("RGBA", "LA") or (logo_img.mode == "P" and "transparency" in logo_img.info):
                img.paste(logo_img, (W - 240, 75), mask=logo_img.convert("RGBA").split()[3])
            else:
                img.paste(logo_img, (W - 240, 75))
        except Exception:
            pass

    # Sarlavha (Title) — hech qachon shafqatsiz kesilmaydi, so'zma-so'z o'raladi!
    title_end_y = draw_wrapped_text(
        draw=draw,
        text=slide_data.title,
        x=100,
        y=125,
        max_width=W - 200,
        font=f_title,
        fill=theme.text_title,
        line_spacing=4,
        max_lines=2
    )

    # Subtitle
    if slide_data.subtitle:
        sub_end_y = draw_wrapped_text(
            draw=draw,
            text=slide_data.subtitle,
            x=100,
            y=title_end_y + 4,
            max_width=W - 200,
            font=f_sub,
            fill=theme.text_muted,
            line_spacing=3,
            max_lines=2
        )
        content_top = max(sub_end_y + 16, 220)
    else:
        content_top = max(title_end_y + 16, 210)

    content_bottom = H - 95

    # ------------------ LAYOUTLAR BO'YICHA KONTENT CHIZISH ------------------
    if slide_data.layout == "title_slide" or current_num == 1:
        # Chap qism: Katta reja va maqsad kartasi
        draw.rounded_rectangle([(100, content_top), (760, content_bottom)], radius=14, fill=theme.bg_color, outline=theme.card_border, width=2)
        draw.text((130, content_top + 25), "🌟 TAQDIMOT REJASI & MAQSADI", font=f_card_title, fill=theme.primary)
        
        y_c = content_top + 65
        y_c = draw_wrapped_text(draw, f"📌 Mavzu: {slide_data.title}", 130, y_c, 590, f_body_bold, theme.text_title, line_spacing=4, max_lines=2)
        if slide_data.subtitle:
            y_c = draw_wrapped_text(draw, f"💡 Tavsif: {slide_data.subtitle}", 130, y_c + 6, 590, f_body, theme.text_muted, line_spacing=3, max_lines=3)
        
        draw.text((130, y_c + 10), f"📊 Slaydlar hajmi: {total_slides} ta to'liq professional slayd", font=f_body_bold, fill=theme.secondary)

        if author_name:
            draw.rounded_rectangle([(130, content_bottom - 55), (550, content_bottom - 15)], radius=8, fill=theme.badge_bg, outline=theme.secondary, width=1)
            draw.text((150, content_bottom - 43), f"👨‍💻 Tayyorladi: {author_name}", font=f_badge, fill=theme.secondary)

        # O'ng qism: Standartlar va xususiyatlar kartasi
        draw.rounded_rectangle([(785, content_top), (W - 100, content_bottom)], radius=14, fill=theme.bg_color, outline=theme.primary, width=2)
        draw.text((815, content_top + 25), f"{theme.emoji} {theme.name}", font=f_card_title, fill=theme.primary)
        
        features = [
            "✓ Zamonaviy 16:9 Widescreen format",
            "✓ @SlaydchiAkabot professional kontent",
            "✓ To'liq Spiker Nutqi (Har bir slaydga)",
            "✓ PowerPoint (.pptx) & Yuqori sifatli PDF",
            "✓ Tahrirlash va tarjima qilish imkoniyati"
        ]
        f_y = content_top + 75
        for feat in features:
            draw.text((815, f_y), feat, font=f_body, fill=theme.text_body)
            f_y += 40

    elif slide_data.layout == "quote_highlight" or (slide_data.quote_text and not slide_data.cards):
        # Iqtibos slaydi (Foydalanuvchi skrinshotidagi slayd!)
        draw.rounded_rectangle([(100, content_top), (W - 100, content_bottom)], radius=16, fill=theme.bg_color, outline=theme.primary, width=2)
        draw.rounded_rectangle([(125, content_top + 30), (133, content_bottom - 30)], radius=4, fill=theme.primary)
        
        # Tirnoq belgisi
        f_q_icon = get_render_font(56, bold=True)
        draw.text((155, content_top + 15), "“", font=f_q_icon, fill=theme.secondary)

        # To'liq iqtibos matni (so'zma-so'z o'raladi, 5 qatorgacha to'liq sig'diriladi!)
        quote_body = slide_data.quote_text or slide_data.highlight_takeaway or slide_data.subtitle or slide_data.title
        f_quote = get_render_font(23, bold=True, italic=True)
        quote_end_y = draw_wrapped_text(
            draw=draw,
            text=f'"{quote_body}"',
            x=165,
            y=content_top + 80,
            max_width=W - 300,
            font=f_quote,
            fill=theme.text_title,
            line_spacing=8,
            max_lines=5
        )

        # Muallif / Manba
        author = slide_data.quote_author or author_name or "Strategik xulosa va tahliliy qarash"
        f_auth = get_render_font(15, bold=True)
        try:
            bbox_a = draw.textbbox((0, 0), f"—  {author}", font=f_auth)
            auth_w = min(bbox_a[2] - bbox_a[0] + 40, W - 320)
        except Exception:
            auth_w = 260
        auth_y = max(quote_end_y + 25, content_bottom - 60)
        draw.rounded_rectangle([(165, auth_y), (165 + auth_w, auth_y + 38)], radius=8, fill=theme.badge_bg, outline=theme.secondary, width=1)
        draw.text((185, auth_y + 10), f"—  {author}", font=f_auth, fill=theme.secondary)

    elif slide_data.layout == "chart_slide":
        left_w = 420
        draw.rounded_rectangle([(100, content_top), (100 + left_w, content_bottom)], radius=14, fill=theme.bg_color, outline=theme.card_border, width=2)
        draw.text((125, content_top + 25), "📊 ASOSIY STATISTIKA", font=f_card_title, fill=theme.primary)
        stats = slide_data.stats or []
        for s_i, st in enumerate(stats[:3]):
            s_y = content_top + 70 + s_i * 90
            draw.text((125, s_y), f"• {st.label}: {st.number}", font=f_body_bold, fill=theme.text_title)
            if st.description:
                draw_wrapped_text(draw, st.description, 140, s_y + 24, left_w - 60, f_body, theme.text_muted, line_spacing=2, max_lines=2)

        chart_x = 100 + left_w + 30
        chart_w = W - 100 - chart_x
        draw.rounded_rectangle([(chart_x, content_top), (chart_x + chart_w, content_bottom)], radius=14, fill=theme.bg_color, outline=theme.primary, width=2)
        draw.text((chart_x + 30, content_top + 25), "📈 O'sish va Dinamika Diagrammasi", font=f_card_title, fill=theme.primary)

        chart_base_y = content_bottom - 50
        max_bar_h = content_bottom - content_top - 120
        bar_items = stats[:4] if stats else [StatItem(number="75%", label="1-Bosqich"), StatItem(number="90%", label="2-Bosqich")]
        num_b = len(bar_items)
        bw = int((chart_w - 60 - 25 * (num_b - 1)) / max(num_b, 1))

        for b_i, b_item in enumerate(bar_items):
            bx = chart_x + 30 + b_i * (bw + 25)
            clean_digits = "".join(c for c in b_item.number if c.isdigit() or c == ".")
            try:
                percent = float(clean_digits) if clean_digits else 50.0
            except ValueError:
                percent = 50.0
            percent = min(max(percent, 15.0), 100.0)
            bh = int(max_bar_h * (percent / 100.0))
            by = chart_base_y - bh

            col = theme.primary if b_i % 2 == 0 else theme.secondary
            draw.rounded_rectangle([(bx, by), (bx + bw, chart_base_y)], radius=6, fill=col)
            draw.text((bx + 10, by - 24), b_item.number, font=f_body_bold, fill=theme.text_title)
            draw.text((bx + 5, chart_base_y + 10), b_item.label[:14], font=f_body, fill=theme.text_muted)

    elif slide_data.stats and (slide_data.layout == "stats_metrics" or len(slide_data.stats) >= 2):
        st_list = slide_data.stats[:4]
        num_cards = max(len(st_list), 1)
        card_w = int((W - 200 - 20 * (num_cards - 1)) / num_cards)
        f_stat_num = get_render_font(44, bold=True)
        f_stat_lbl = get_render_font(17, bold=True)

        for i, st in enumerate(st_list):
            c_x = 100 + i * (card_w + 20)
            draw.rounded_rectangle([(c_x, content_top), (c_x + card_w, content_bottom)], radius=14, fill=theme.bg_color, outline=theme.card_border, width=2)
            draw.rounded_rectangle([(c_x + 2, content_top + 2), (c_x + card_w - 2, content_top + 6)], radius=2, fill=theme.primary if i % 2 == 0 else theme.secondary)
            draw.text((c_x + 20, content_top + 25), st.number, font=f_stat_num, fill=theme.primary)
            draw_wrapped_text(draw, st.label, c_x + 20, content_top + 85, card_w - 40, f_stat_lbl, theme.text_title, line_spacing=3, max_lines=2)
            if st.description:
                draw_wrapped_text(draw, st.description, c_x + 20, content_top + 145, card_w - 40, f_body, theme.text_muted, line_spacing=4, max_lines=6)

    elif slide_data.comparison_col1 and slide_data.comparison_col2:
        col_w = int((W - 200 - 25) / 2)
        cols = [
            (slide_data.comparison_col1, 100, theme.text_muted, "✕"),
            (slide_data.comparison_col2, 100 + col_w + 25, theme.primary, "✓"),
        ]
        for c_data, c_x, hl_color, icon in cols:
            draw.rounded_rectangle([(c_x, content_top), (c_x + col_w, content_bottom)], radius=14, fill=theme.bg_color, outline=theme.card_border, width=2)
            draw.text((c_x + 25, content_top + 25), f"{icon}  {c_data.header}", font=f_card_title, fill=hl_color)
            p_y = content_top + 75
            for pt in c_data.points[:5]:
                p_y = draw_wrapped_text(draw, f"• {pt}", c_x + 25, p_y, col_w - 50, f_body, theme.text_body, line_spacing=3, max_lines=3) + 8

    elif slide_data.steps and (slide_data.layout == "timeline_steps" or len(slide_data.steps) >= 2):
        st_list = slide_data.steps[:4]
        num_cards = max(len(st_list), 1)
        card_w = int((W - 200 - 18 * (num_cards - 1)) / num_cards)
        for i, step in enumerate(st_list):
            c_x = 100 + i * (card_w + 18)
            draw.rounded_rectangle([(c_x, content_top), (c_x + card_w, content_bottom)], radius=14, fill=theme.bg_color, outline=theme.card_border, width=2)
            draw.rounded_rectangle([(c_x + 20, content_top + 20), (c_x + 64, content_top + 64)], radius=22, fill=theme.primary)
            draw.text((c_x + 36, content_top + 30), str(i + 1), font=f_card_title, fill=theme.bg_color)
            t_y = draw_wrapped_text(draw, step.title, c_x + 20, content_top + 80, card_w - 40, f_card_title, theme.text_title, line_spacing=3, max_lines=2)
            draw_wrapped_text(draw, step.description, c_x + 20, t_y + 8, card_w - 40, f_body, theme.text_body, line_spacing=4, max_lines=7)

    elif slide_data.layout == "matrix_2x2" or (getattr(slide_data, "matrix_items", None) and len(slide_data.matrix_items) == 4):
        items = slide_data.matrix_items or slide_data.cards[:4]
        m_w = int((W - 200 - 20) / 2)
        m_h = int((content_bottom - content_top - 16) / 2)
        coords = [
            (100, content_top),
            (100 + m_w + 20, content_top),
            (100, content_top + m_h + 16),
            (100 + m_w + 20, content_top + m_h + 16),
        ]
        for i, m_item in enumerate(items[:4]):
            mx, my = coords[i]
            draw.rounded_rectangle([(mx, my), (mx + m_w, my + m_h)], radius=12, fill=theme.bg_color, outline=theme.card_border, width=2)
            b_val = (m_item.badge or f"0{i+1}").upper()
            draw.text((mx + 20, my + 15), b_val, font=get_render_font(12, bold=True), fill=theme.secondary)
            t_y = draw_wrapped_text(draw, m_item.title, mx + 20, my + 35, m_w - 40, f_card_title, theme.text_title, line_spacing=2, max_lines=1)
            draw_wrapped_text(draw, m_item.description, mx + 20, t_y + 6, m_w - 40, f_body, theme.text_body, line_spacing=3, max_lines=4)

    elif slide_data.checklist and (slide_data.layout == "checklist_points" or len(slide_data.checklist) >= 3):
        items = slide_data.checklist[:5]
        item_h = int((content_bottom - content_top - 12 * (len(items) - 1)) / max(len(items), 1))
        for i, itm in enumerate(items):
            i_y = content_top + i * (item_h + 12)
            draw.rounded_rectangle([(100, i_y), (W - 100, i_y + item_h)], radius=10, fill=theme.bg_color, outline=theme.card_border, width=1)
            draw.text((125, i_y + int(item_h / 2) - 10), "✓", font=f_card_title, fill=theme.primary)
            draw_wrapped_text(draw, itm, 160, i_y + 12, W - 280, f_body, theme.text_body, line_spacing=3, max_lines=2)

    elif slide_data.layout == "conclusion":
        draw.rounded_rectangle([(100, content_top), (W - 100, content_bottom)], radius=16, fill=theme.bg_color, outline=theme.primary, width=2)
        draw.text((135, content_top + 25), "🎯 ASOSIY XULOSA VA TAVSIYALAR", font=f_card_title, fill=theme.primary)
        
        takeaway = slide_data.highlight_takeaway or slide_data.quote_text or slide_data.subtitle or slide_data.title
        y_next = draw_wrapped_text(draw, takeaway, 135, content_top + 70, W - 270, get_render_font(20, bold=True), theme.text_title, line_spacing=6, max_lines=3)
        
        cards = slide_data.cards or []
        if cards:
            c_top = y_next + 25
            c_h = content_bottom - c_top - 15
            if c_h > 80:
                n_c = min(len(cards), 3)
                cw = int((W - 270 - 16 * (n_c - 1)) / n_c)
                for i, c_item in enumerate(cards[:n_c]):
                    cx = 135 + i * (cw + 16)
                    draw.rounded_rectangle([(cx, c_top), (cx + cw, c_top + c_h)], radius=10, fill=theme.card_bg, outline=theme.card_border, width=1)
                    t_y = draw_wrapped_text(draw, c_item.title, cx + 15, c_top + 15, cw - 30, f_card_title, theme.secondary, line_spacing=2, max_lines=1)
                    draw_wrapped_text(draw, c_item.description, cx + 15, t_y + 6, cw - 30, f_body, theme.text_body, line_spacing=3, max_lines=4)

    else:
        # Standart cards_grid yoki 60/40 Split rasm
        cards = slide_data.cards or [CardItem(title="Asosiy mazmun", description=slide_data.title, badge="01")]
        cards = cards[:4]
        
        ai_img_path = fetch_ai_image_sync(slide_data.image_keyword) if slide_data.image_keyword else None
        if ai_img_path and os.path.exists(ai_img_path) and (current_num % 2 == 0 or current_num == 2):
            left_w = 640
            left_cards = cards[:3]
            n_c = max(len(left_cards), 1)
            c_h = int((content_bottom - content_top - 14 * (n_c - 1)) / n_c)
            for i, card in enumerate(left_cards):
                c_y = content_top + i * (c_h + 14)
                draw.rounded_rectangle([(100, c_y), (100 + left_w, c_y + c_h)], radius=12, fill=theme.bg_color, outline=theme.card_border, width=2)
                badge_t = (card.badge or f"0{i+1}").upper()
                draw.text((120, c_y + 14), badge_t, font=get_render_font(12, bold=True), fill=theme.secondary)
                t_end = draw_wrapped_text(draw, card.title, 120, c_y + 35, left_w - 40, f_card_title, theme.text_title, line_spacing=2, max_lines=1)
                draw_wrapped_text(draw, card.description, 120, t_end + 6, left_w - 40, f_body, theme.text_body, line_spacing=3, max_lines=4)

            # O'ng tomonda AI Rasm
            img_x = 100 + left_w + 25
            img_w = W - 100 - img_x
            draw.rounded_rectangle([(img_x, content_top), (img_x + img_w, content_bottom)], radius=14, fill=theme.bg_color, outline=theme.primary, width=2)
            try:
                loaded_img = Image.open(ai_img_path).convert("RGB")
                loaded_img = loaded_img.resize((img_w - 16, content_bottom - content_top - 16), Image.Resampling.LANCZOS)
                img.paste(loaded_img, (img_x + 8, content_top + 8))
            except Exception as e:
                logger.warning(f"Preview AI rasm chizishda ogohlantirish: {e}")
        else:
            num_cards = max(len(cards), 1)
            card_w = int((W - 200 - 20 * (num_cards - 1)) / num_cards)
            for i, card in enumerate(cards):
                c_x = 100 + i * (card_w + 20)
                draw.rounded_rectangle([(c_x, content_top), (c_x + card_w, content_bottom)], radius=14, fill=theme.bg_color, outline=theme.card_border, width=2)
                draw.rounded_rectangle([(c_x + 2, content_top + 2), (c_x + card_w - 2, content_top + 6)], radius=2, fill=theme.primary if i % 2 == 0 else theme.secondary)
                badge_t = (card.badge or f"0{i+1}").upper()
                draw.text((c_x + 18, content_top + 18), badge_t, font=get_render_font(12, bold=True), fill=theme.secondary)
                t_end = draw_wrapped_text(draw, card.title, c_x + 18, content_top + 40, card_w - 36, f_card_title, theme.text_title, line_spacing=3, max_lines=2)
                draw_wrapped_text(draw, card.description, c_x + 18, t_end + 8, card_w - 36, f_body, theme.text_body, line_spacing=4, max_lines=8)

    # Footer
    author_ft = f"  •  Muallif: {author_name}" if author_name else ""
    draw.text((100, H - 75), f"@SlaydchiAkabot  •  Slayd {current_num} / {total_slides}  •  {theme.name}{author_ft}", font=f_footer, fill=theme.text_muted)

    return img


def generate_slide_preview_image(
    content: PresentationContent,
    theme_key: str = "dark_tech",
    author_name: Optional[str] = None,
    logo_path: Optional[str] = None,
) -> str:
    """Slayd 1 ning yuqori sifatli visual prevyusini (1280x720) rasm qilib yaratadi."""
    theme = config.THEMES.get(theme_key, config.THEMES[config.DEFAULT_THEME])
    safe_topic = "".join(c for c in content.topic if c.isalnum() or c in (" ", "_", "-")).strip()
    safe_topic = safe_topic[:25].replace(" ", "_") or "presentation"
    os.makedirs(config.GENERATED_DIR, exist_ok=True)
    out_path = os.path.join(config.GENERATED_DIR, f"preview_{safe_topic}_{theme_key}.png")

    s1 = content.slides[0] if content.slides else SlideContent(layout="title_slide", category_badge="TAQDIMOT", title=content.topic)
    img = render_slide_to_image(
        slide_data=s1,
        theme=theme,
        current_num=1,
        total_slides=len(content.slides),
        author_name=author_name,
        logo_path=logo_path,
    )
    img.save(out_path, "PNG", quality=95)
    return out_path


def generate_all_slides_preview_images(
    content: PresentationContent,
    theme_key: str = "dark_tech",
    author_name: Optional[str] = None,
    logo_path: Optional[str] = None,
) -> List[str]:
    """Barcha slaydlarni yuqori sifatli 1280x720 PNG rasmlari ko'rinishida generatsiya qiladi."""
    theme = config.THEMES.get(theme_key, config.THEMES[config.DEFAULT_THEME])
    safe_topic = "".join(c for c in content.topic if c.isalnum() or c in (" ", "_", "-")).strip()
    safe_topic = safe_topic[:20].replace(" ", "_") or "presentation"
    os.makedirs(config.GENERATED_DIR, exist_ok=True)

    image_paths = []
    total_slides = len(content.slides)
    for idx, slide_data in enumerate(content.slides):
        out_path = os.path.join(config.GENERATED_DIR, f"slide_{safe_topic}_{theme_key}_{idx+1}.png")
        img = render_slide_to_image(
            slide_data=slide_data,
            theme=theme,
            current_num=idx + 1,
            total_slides=total_slides,
            author_name=author_name,
            logo_path=logo_path,
        )
        img.save(out_path, "PNG", quality=95)
        image_paths.append(out_path)

    return image_paths


def convert_pptx_to_pdf(
    pptx_path: str,
    content: Optional[PresentationContent] = None,
    theme_key: str = "dark_tech",
    author_name: Optional[str] = None,
) -> Optional[str]:
    """PPTX faylini PDF ga o'giradi (LibreOffice headless yoki Visual Pillow renderer orqali)."""
    pdf_path = pptx_path.rsplit(".", 1)[0] + ".pdf"
    out_dir = os.path.dirname(pptx_path) or "."

    # 1. LibreOffice headless sinab ko'rish (agar serverda soffice mavjud bo'lsa, 100% PowerPoint bilan bir xil chiqadi)
    try:
        res = subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", pptx_path, "--outdir", out_dir],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=25,
        )
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1000:
            logger.info("LibreOffice orqali 100% mukammal PDF yaratildi.")
            return pdf_path
    except Exception as se:
        logger.info(f"soffice mavjud emas yoki ogohlantirish: {se}. Visual Pillow PDF ga o'tilmoqda.")

    # 2. Agar kontent mavjud bo'lsa, yuqori sifatli 16:9 visual PDF yaratish
    if content and content.slides:
        try:
            res = create_presentation_pdf(
                content=content,
                theme_key=theme_key,
                output_path=pdf_path,
                author_name=author_name,
            )
            if res and os.path.exists(res) and os.path.getsize(res) > 1000:
                return res
        except Exception as e:
            logger.warning(f"create_presentation_pdf xatoligi: {e}")

    # 3. ReportLab zaxira varianti
    if not content:
        return None

    try:
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=landscape(letter),
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36,
        )
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "PdfTitle",
            parent=styles["Title"],
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#0f172a"),
        )
        heading_style = ParagraphStyle(
            "PdfHeading",
            parent=styles["Heading2"],
            fontSize=15,
            leading=19,
            textColor=colors.HexColor("#1e40af"),
        )
        body_style = ParagraphStyle(
            "PdfBody",
            parent=styles["Normal"],
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#334155"),
        )
        speech_style = ParagraphStyle(
            "PdfSpeech",
            parent=styles["Italic"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#475569"),
        )

        story = []
        author_info = f" • Muallif: {author_name}" if author_name else ""
        story.append(Paragraph(f"<b>{content.topic}</b>", title_style))
        story.append(Paragraph(f"Taqdimot slaydlar to'plami ({len(content.slides)} ta slayd){author_info}", body_style))
        story.append(Spacer(1, 15))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563eb"), spaceAfter=15))

        for idx, slide in enumerate(content.slides):
            badge = (slide.category_badge or f"SLAYD {idx+1}").upper()
            story.append(Paragraph(f"<b>[{badge}] {slide.title}</b>", heading_style))
            if slide.subtitle:
                story.append(Paragraph(f"<i>{slide.subtitle}</i>", body_style))
            story.append(Spacer(1, 6))

            if slide.cards:
                for c in slide.cards:
                    story.append(Paragraph(f"• <b>{c.title}:</b> {c.description}", body_style))
            elif slide.stats:
                for st in slide.stats:
                    story.append(Paragraph(f"• <b>{st.number}</b> - {st.label}: {st.description or ''}", body_style))
            elif slide.steps:
                for step in slide.steps:
                    story.append(Paragraph(f"• <b>{step.title}:</b> {step.description}", body_style))
            elif getattr(slide, "matrix_items", None):
                for mi in slide.matrix_items:
                    story.append(Paragraph(f"• <b>{mi.title}:</b> {mi.description}", body_style))
            elif getattr(slide, "checklist", None):
                for cl in slide.checklist:
                    story.append(Paragraph(f"✓ {cl}", body_style))

            if getattr(slide, "speaker_speech", None):
                story.append(Spacer(1, 4))
                story.append(Paragraph(f"🎤 <i>Spiker nutqi: \"{slide.speaker_speech}\"</i>", speech_style))

            story.append(Spacer(1, 10))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceAfter=10))

        doc.build(story)
        if os.path.exists(pdf_path):
            return pdf_path
    except Exception as e:
        logger.error(f"ReportLab PDF generatsiyasida xatolik: {e}")

    return None




def create_presentation_pdf(
    content: PresentationContent,
    theme_key: str = "dark_tech",
    output_path: Optional[str] = None,
    author_name: Optional[str] = None,
    logo_path: Optional[str] = None,
) -> Optional[str]:
    """
    Barcha slaydlarni toza, yuqori aniqlikdagi (1280x720) va shriftlari surilmaydigan
    mukammal PDF fayliga aylantiradi. 100% mustaqil, tezkor va barqaror.
    """
    if not content or not content.slides:
        return None

    theme = config.THEMES.get(theme_key, config.THEMES[config.DEFAULT_THEME])
    total_slides = len(content.slides)

    images = []
    for idx, s_data in enumerate(content.slides):
        img = render_slide_to_image(
            slide_data=s_data,
            theme=theme,
            current_num=idx + 1,
            total_slides=total_slides,
            author_name=author_name,
            logo_path=logo_path,
        )
        if img.mode != "RGB":
            img = img.convert("RGB")
        images.append(img)

    if not output_path:
        safe_topic = "".join(c for c in content.topic if c.isalnum() or c in (" ", "_", "-")).strip()
        safe_topic = safe_topic[:30].replace(" ", "_") or "presentation"
        os.makedirs("generated_slides", exist_ok=True)
        output_path = os.path.join("generated_slides", f"{safe_topic}_{theme_key}.pdf")

    if images:
        images[0].save(
            output_path,
            save_all=True,
            append_images=images[1:],
            resolution=150.0,
            quality=95
        )
        return output_path

    return None
