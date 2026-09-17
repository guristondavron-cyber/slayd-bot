import os
from typing import Optional
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

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


def create_presentation_file(
    content: PresentationContent,
    theme_key: str = "dark_tech",
    output_path: Optional[str] = None,
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
            _render_title_slide(slide, slide_data, theme, prs.slide_width, prs.slide_height)
        elif slide_data.layout == "stats_metrics" and slide_data.stats:
            _render_stats_slide(slide, slide_data, theme, idx + 1, total_slides)
        elif slide_data.layout == "comparison" and (slide_data.comparison_col1 or slide_data.comparison_col2):
            _render_comparison_slide(slide, slide_data, theme, idx + 1, total_slides)
        elif slide_data.layout == "timeline_steps" and slide_data.steps:
            _render_timeline_slide(slide, slide_data, theme, idx + 1, total_slides)
        elif slide_data.layout == "conclusion":
            _render_conclusion_slide(slide, slide_data, theme, idx + 1, total_slides)
        else:
            # Standart cards_grid layout
            _render_cards_grid_slide(slide, slide_data, theme, idx + 1, total_slides)

    # Chiqish fayli nomini belgilash
    if not output_path:
        safe_topic = "".join(c for c in content.topic if c.isalnum() or c in (" ", "_", "-")).strip()
        safe_topic = safe_topic[:30].replace(" ", "_") or "presentation"
        os.makedirs("generated_slides", exist_ok=True)
        output_path = os.path.join("generated_slides", f"{safe_topic}_{theme_key}.pptx")

    prs.save(output_path)
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


def _render_header(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int):
    """Har bir slayd uchun standart zamonaviy header va footer."""
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
    title_box = slide.shapes.add_textbox(Inches(0.9), Inches(0.95), Inches(11.5), Inches(1.3))
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
    p_f.text = f"✨ Gemini AI  •  Slayd {current_num} / {total_slides}"
    p_f.font.size = Pt(10)
    p_f.font.name = FONT_FAMILY_BODY
    p_f.font.color.rgb = RGBColor(*theme.text_muted)


def _render_title_slide(slide, slide_data: SlideContent, theme: ColorTheme, width, height):
    """Zamonaviy Title (Muqova) slaydi."""
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
        card_w - Inches(1.6),
        Inches(2.2),
    )
    tf_t = title_box.text_frame
    tf_t.word_wrap = True
    p_t = tf_t.paragraphs[0]
    p_t.text = slide_data.title
    p_t.font.size = Pt(40)
    p_t.font.bold = True
    p_t.font.name = FONT_FAMILY_TITLE
    p_t.font.color.rgb = RGBColor(*theme.text_title)

    if slide_data.subtitle:
        p_sub = tf_t.add_paragraph()
        p_sub.text = slide_data.subtitle
        p_sub.font.size = Pt(18)
        p_sub.font.name = FONT_FAMILY_BODY
        p_sub.font.color.rgb = RGBColor(*theme.text_muted)
        p_sub.space_before = Pt(12)

    # Pastki qismdagi ajralib turuvchi Callout blok
    if slide_data.highlight_takeaway:
        hl_box = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            card_left + Inches(0.8),
            card_top + Inches(4.0),
            card_w - Inches(1.6),
            Inches(1.1),
        )
        hl_box.fill.solid()
        hl_box.fill.fore_color.rgb = RGBColor(*theme.bg_color)
        hl_box.line.color.rgb = RGBColor(*theme.primary)
        hl_box.line.width = Pt(1)

        tf_hl = hl_box.text_frame
        tf_hl.word_wrap = True
        p_hl = tf_hl.paragraphs[0]
        p_hl.text = f"💡 {slide_data.highlight_takeaway}"
        p_hl.font.size = Pt(14)
        p_hl.font.name = FONT_FAMILY_BODY
        p_hl.font.color.rgb = RGBColor(*theme.text_body)
        p_hl.alignment = PP_ALIGN.LEFT


def _render_cards_grid_slide(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int):
    """3 yoki 4 ta kartochkali zamonaviy grid layout."""
    _render_header(slide, slide_data, theme, current_num, total_slides)

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


def _render_stats_slide(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int):
    """Statistika va raqamlar infografikasi slaydi."""
    _render_header(slide, slide_data, theme, current_num, total_slides)

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


def _render_comparison_slide(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int):
    """Ikki ustunli solishtirish (Masalan: An'anaviy vs Innovatsion) slaydi."""
    _render_header(slide, slide_data, theme, current_num, total_slides)

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


def _render_timeline_slide(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int):
    """Bosqichma-bosqich jarayon yoki timeline slaydi."""
    _render_header(slide, slide_data, theme, current_num, total_slides)

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


def _render_conclusion_slide(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int):
    """Xulosa, muhim iqtibos va asosiy chaqiriq slaydi."""
    _render_header(slide, slide_data, theme, current_num, total_slides)

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
