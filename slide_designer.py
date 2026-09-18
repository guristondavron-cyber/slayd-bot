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
        elif slide_data.layout == "matrix_2x2":
            _render_matrix_slide(slide, slide_data, theme, idx + 1, total_slides)
        elif slide_data.layout == "quote_highlight":
            _render_quote_slide(slide, slide_data, theme, idx + 1, total_slides)
        elif slide_data.layout == "checklist_points":
            _render_checklist_slide(slide, slide_data, theme, idx + 1, total_slides)
        elif slide_data.layout == "conclusion":
            _render_conclusion_slide(slide, slide_data, theme, idx + 1, total_slides)
        else:
            _render_cards_grid_slide(slide, slide_data, theme, idx + 1, total_slides)

        # Spiker nutqini PowerPoint Notes bo'limiga biriktirish

        if getattr(slide_data, "speaker_speech", None) or getattr(slide_data, "speaker_notes", None):
            try:
                notes_slide = slide.notes_slide
                tf_n = notes_slide.notes_text_frame
                text_parts = []
                if getattr(slide_data, "speaker_speech", None):
                    text_parts.append(f"🎤 SPIKER NUTQI:\n{slide_data.speaker_speech}")
                if getattr(slide_data, "speaker_notes", None):
                    text_parts.append(f"💡 ESLATMA:\n{slide_data.speaker_notes}")
                tf_n.text = "\n\n".join(text_parts)
            except Exception:
                pass

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


def _render_matrix_slide(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int):
    """2x2 Quadrant matritsa slaydi (4 ta bo'lim/yo'nalish)."""
    _render_header(slide, slide_data, theme, current_num, total_slides)

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


def _render_quote_slide(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int):
    """Markazlashtirilgan katta iqtibos / asosiy tezis slaydi."""
    _render_header(slide, slide_data, theme, current_num, total_slides)

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


def _render_checklist_slide(slide, slide_data: SlideContent, theme: ColorTheme, current_num: int, total_slides: int):
    """Checklist va tasdiqlangan qoidalar/punktlar slaydi."""
    _render_header(slide, slide_data, theme, current_num, total_slides)

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

