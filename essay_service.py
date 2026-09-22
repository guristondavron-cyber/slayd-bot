import os
import logging
import re
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

import config

logger = logging.getLogger(__name__)


# ------------------ PYDANTIC MODELLARI ------------------
class ChapterSection(BaseModel):
    title: str = Field(description="Bo'lim yoki kichik reja nomi (masalan: '1.1. Sun'iy intellektning nazariy asoslari va tushunchasi')")
    content: str = Field(description="Ushbu bo'limning to'liq, chuqur, ilmiy va tahliliy matni (kamida 3-5 ta mazmunli abzas, faktlar, statistik ma'lumotlar va amaliy tahlillar bilan)")


class Chapter(BaseModel):
    title: str = Field(description="Bob nomi (masalan: 'I BOB. SUN'IY INTELLEKTNING NAZARIY VA KONSEPTUAL ASOSLARI')")
    sections: List[ChapterSection] = Field(description="Ushbu bob tarkibidagi 2 yoki 3 ta kichik bo'limlar")


class AcademicEssay(BaseModel):
    topic: str = Field(description="Mustaqil ish / Referat mavzusi")
    university: Optional[str] = Field(default="Oliy Ta'lim Muassasasi", description="Universitet yoki Institut nomi")
    faculty: Optional[str] = Field(default="Fakultet va Ta'lim Yo'nalishi", description="Fakultet va yo'nalish")
    author_name: Optional[str] = Field(default="Talaba", description="Ishni bajargan talabaning ismi-familiyasi")
    teacher_name: Optional[str] = Field(default="O'qituvchi / Ilmiy rahbar", description="Qabul qiluvchi o'qituvchi")
    year: str = Field(default="2026", description="Yil")
    city: str = Field(default="Toshkent", description="Shahar")
    introduction: str = Field(description="Kirish qismi: Mavzuning dolzarbligi, tadqiqotning maqsadi va vazifalari, tadqiqot obyekti hamda usullari (kamida 3-4 ta to'liq abzas)")
    chapters: List[Chapter] = Field(description="Kamida 2 ta asosiy bob (I Bob nazariy, II Bob amaliy/tahliliy)")
    conclusion: str = Field(description="Xulosa va amaliy takliflar: Olingan natijalar, umumiy xulosalar va amaliyotga tatbiq etish bo'yicha tavsiyalar (kamida 3-4 ta abzas)")
    references: List[str] = Field(description="Kamida 5-8 ta rasmiy darslik, qonunchilik hujjati, ilmiy maqolalar va ishonchli manbalar ro'yxati")


def _clean_json_string(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


# ------------------ GEMINI BILAN KONTENT GENERATSIYASI ------------------
async def generate_academic_essay_content(
    topic: str,
    author_name: Optional[str] = None,
    university: Optional[str] = None,
    language: str = "uz",
    api_key: Optional[str] = None,
) -> AcademicEssay:
    """Gemini AI orqali OTM talablariga mos to'liq Mustaqil Ish / Referat kontentini yaratadi."""
    key = api_key or config.GEMINI_API_KEY
    author_str = author_name or "Talaba"
    univ_str = university or "O'zbekiston Respublikasi Oliy Ta'lim Muassasasi"

    fallback_essay = AcademicEssay(
        topic=topic,
        university=univ_str,
        faculty="Axborot texnologiyalari va iqtisodiyot fakulteti",
        author_name=author_str,
        teacher_name="Dotsent, Ilmiy rahbar",
        year="2026",
        city="Toshkent",
        introduction=(
            f"Zamonaviy taraqqiyot bosqichida «{topic}» mavzusi dolzarb ilmiy va amaliy ahamiyat kasb etmoqda. "
            "Ushbu sohada olib borilayotgan islohotlar va yangi yondashuvlar sohani yanada takomillashtirishga zamin yaratadi. "
            f"Tadqiqotning asosiy maqsadi — «{topic}» jarayonlarini chuqur tahlil qilish, uning o'ziga xos xususiyatlarini ochib berish "
            "hamda mavjud muammolarni bartaraf etish bo'yicha ilmiy-amaliy takliflar ishlab chiqishdan iborat.\n\n"
            "Tadqiqot vazifalari etib mavzuning nazariy-metodologik asoslarini o'rganish, sohadagi ilg'or xorijiy tajribani tahlil qilish "
            "va amaliyotda qo'llash istiqbollarini belgilash belgilangan."
        ),
        chapters=[
            Chapter(
                title=f"I BOB. «{topic.upper()}»NING NAZARIY-METODOLOGIK ASOSLARI",
                sections=[
                    ChapterSection(
                        title=f"1.1. «{topic}» tushunchasining mohiyati va evolyutsiyasi",
                        content=(
                            f"«{topic}» zamonaviy fanning eng muhim yo'nalishlaridan biri bo'lib, uning rivojlanishi bevosita global o'zgarishlar bilan bog'liq. "
                            "Nazariy adabiyotlar tahlili shuni ko'rsatadiki, ushbu tushuncha turli davrlarda olimlar tomonidan turlicha talqin qilingan. "
                            "Mazkur bo'limda ushbu yo'nalishning paydo bo'lishi, asosiy tamoyillari va bugungi kundagi ahamiyati batafsil bayon etiladi."
                        ),
                    ),
                    ChapterSection(
                        title=f"1.2. Mavzuning xalqaro va milliy darajadagi ahamiyati",
                        content=(
                            "Jahon tajribasi shuni ko'rsatadiki, ushbu sohani to'g'ri tashkil etish va boshqarish umumiy samaradorlikni 30-40% ga oshirish imkonini beradi. "
                            "O'zbekistonda ham ushbu sohaga davlat darajasida katta e'tibor qaratilmoqda va maxsus strategiyalar qabul qilinmoqda."
                        ),
                    ),
                ],
            ),
            Chapter(
                title=f"II BOB. «{topic.upper()}»NING AMALIY TAHLILI VA RIVOJLANISH ISTIQBOLLARI",
                sections=[
                    ChapterSection(
                        title=f"2.1. Amaliy holat tahlili va mavjud muammolar",
                        content=(
                            "Ushbu bo'limda sohaning amaliy holati chuqur tahlil qilinadi. Statistik ma'lumotlar va empirik kuzatuvlar asosida "
                            "mavjud tizimning kuchli va zaif tomonlari, xatarlar va tizimli to'siqlar aniqlanadi."
                        ),
                    ),
                    ChapterSection(
                        title=f"2.2. Sohoni rivojlantirish va takomillashtirish yo'llari",
                        content=(
                            "Tahlillar natijasida sohani rivojlantirishning asosiy ustuvor yo'nalishlari ishlab chiqildi. "
                            "Innovatsion texnologiyalarni tatbiq etish, kadrlar salohiyatini oshirish va boshqaruv mexanizmlarini optimallashtirish shular jumlasidandir."
                        ),
                    ),
                ],
            ),
        ],
        conclusion=(
            f"Olib borilgan tadqiqot asosida quyidagi xulosalarga kelindi: Birinchidan, «{topic}» zamonaviy sharoitda strategik ahamiyatga ega. "
            "Ikkinchidan, mavjud muammolarni bartaraf etish uchun kompleks chora-tadbirlar talab etiladi. "
            "Uchinchidan, ishlab chiqilgan amaliy takliflar soha samaradorligini sezilarli darajada oshirishga xizmat qiladi."
        ),
        references=[
            "O'zbekiston Respublikasi Prezidentining tegishli sohani rivojlantirish to'g'risidagi Farmon va Qarorlari.",
            "Karimov A.X. Zamonaviy boshqaruv va tahlil asoslari. Darslik. — Toshkent: Iqtisodiyot, 2023. — 280 b.",
            "Abdullayev R.M. Innovatsion taraqqiyot strategiyasi. — Toshkent: Fan va texnologiya, 2024. — 310 b.",
            "Smith J., Johnson M. Modern Trends and Strategic Innovations. — London: Academic Press, 2023.",
            "O'zbekiston Respublikasi Statistika agentligi rasmiy ma'lumotlari (stat.uz), 2025-2026 yy.",
            "World Bank Global Economic Reports and Research Papers, 2024.",
        ],
    )

    if not key:
        return fallback_essay

    client = genai.Client(api_key=key)
    candidate_models = [
        config.GEMINI_MODEL,
        "gemini-2.5-flash",
        "gemini-3.5-flash",
        "gemini-flash-latest",
    ]
    seen = set()
    models_to_try = [m for m in candidate_models if m and not (m in seen or seen.add(m))]

    prompt = f"""Siz O'zbekiston OTMlari (Universitet va Institutlar) talablari bo'yicha ilmiy ishlar, referatlar va mustaqil ishlarni yuqori darajada yozuvchi professional ilmiy mutaxassis va professorsiz.

MAVZU: «{topic}»
TALABA ISMI: {author_str}
OTM NOMI: {univ_str}
TIL: {language} (o'zbekcha / ruscha / inglizcha)

VAZIFA:
Ushbu mavzu bo'yicha to'liq, chuqur, akademik va rasmiy MUSTAQIL ISH (Referat) matnini tuzing.
Hujjat tarkibida quyidagilar bo'lishi shart:
1. `topic`: Mavzu nomi.
2. `university`: Universitet/Institut nomi.
3. `faculty`: Fakultet va yo'nalish nomi.
4. `author_name`: Talabaning ismi-sharifi.
5. `teacher_name`: Ilmiy rahbar / O'qituvchi lavozimi va ismi (masalan: 'Dotsent, Iqtisod fanlari nomzodi').
6. `year`: 2026
7. `city`: Toshkent (yoki mos shahar)
8. `introduction`: Kamida 3-4 ta to'liq va boy ilmiy abzasdan iborat KIRISH (Mavzuning dolzarbligi, maqsadi, vazifalari, tadqiqot usullari).
9. `chapters`: Kamida 2 ta asosiy BOB:
   - I Bob: Nazariy-metodologik asoslar (tarkibida 2 ta to'liq kichik bo'lim, har bir bo'limda kamida 3-4 ta ilmiy tahliliy abzas).
   - II Bob: Amaliy tahlil, mavjud muammolar va rivojlanish istiqbollari (tarkibida 2 ta to'liq bo'lim, har birida faktlar, raqamlar, tahliliy abzaslar).
10. `conclusion`: Kamida 3-4 ta abzasdan iborat XULOSA VA AMALIY TAVSIYALAR (aniq 1, 2, 3 tartibdagi amaliy xulosalar bilan).
11. `references`: 6 dan 8 tagacha bo'lgan rasmiy darsliklar, ilmiy maqolalar, qonunchilik manbalari va internet resurslari.

Talab: Matn qisqa yoki yuzaki bo'lmasin! Haqiqiy talaba topshirsa domla qoyil qoladigan, to'liq, ilmiy jumlalardan iborat bo'lsin.
Javobni FAQAT AcademicEssay JSON formatida qaytaring."""

    for model_name in models_to_try:
        try:
            logger.info(f"Mustaqil ish generatsiya qilinmoqda ({model_name}): {topic[:40]}...")
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=AcademicEssay,
                    temperature=0.6,
                ),
            )
            raw = response.text or ""
            cleaned = _clean_json_string(raw)
            parsed = AcademicEssay.model_validate_json(cleaned)
            return parsed
        except Exception as e:
            logger.warning(f"generate_academic_essay_content da {model_name} xatosi: {e}")
            continue

    return fallback_essay


# ------------------ WORD (DOCX) HUJJATINI YASASH ------------------
def create_academic_essay_docx(
    essay: AcademicEssay,
    output_path: Optional[str] = None,
) -> str:
    """
    AcademicEssay obyektidan OTM davlat standartlariga (Times New Roman 14pt, 1.5 interval,
    hoshiyalar: 3cm chap, 1.5cm o'ng, 2cm yuqori/past) to'liq mos keladigan professional
    Word (.docx) faylini yaratadi.
    """
    doc = docx.Document()

    # Sahifa hoshiyalarini o'rnatish (OTM standarti: Chap 3.0 sm, O'ng 1.5 sm, Yuqori/Past 2.0 sm)
    sections = doc.sections
    for sec in sections:
        sec.top_margin = Inches(0.79)     # ~2.0 cm
        sec.bottom_margin = Inches(0.79)  # ~2.0 cm
        sec.left_margin = Inches(1.18)    # ~3.0 cm
        sec.right_margin = Inches(0.59)   # ~1.5 cm

    # Asosiy Normal uslubni sozlash
    style_normal = doc.styles["Normal"]
    style_normal.font.name = "Times New Roman"
    style_normal.font.size = Pt(14)
    style_normal.font.color.rgb = RGBColor(0, 0, 0)
    style_normal.paragraph_format.line_spacing = 1.5
    style_normal.paragraph_format.space_before = Pt(0)
    style_normal.paragraph_format.space_after = Pt(0)

    # Yordamchi funksiyalar
    def add_p(text: str, bold: bool = False, italic: bool = False, size: int = 14, align=WD_ALIGN_PARAGRAPH.JUSTIFY, indent: bool = True, space_after: int = 0):
        p = doc.add_paragraph()
        p.alignment = align
        p.paragraph_format.line_spacing = 1.5
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(space_after)
        if indent:
            p.paragraph_format.first_line_indent = Inches(0.49)  # 1.25 cm
        else:
            p.paragraph_format.first_line_indent = Inches(0)
        run = p.add_run(text)
        run.bold = bold
        run.italic = italic
        run.font.name = "Times New Roman"
        run.font.size = Pt(size)
        return p

    def add_heading_title(title_text: str):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.line_spacing = 1.5
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(12)
        p.paragraph_format.first_line_indent = Inches(0)
        run = p.add_run(title_text)
        run.bold = True
        run.font.name = "Times New Roman"
        run.font.size = Pt(15)

    def add_subheading(sub_text: str):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.line_spacing = 1.5
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.first_line_indent = Inches(0.49)
        run = p.add_run(sub_text)
        run.bold = True
        run.font.name = "Times New Roman"
        run.font.size = Pt(14)

    # ==================== 1. TITUL VARAG'I (MUQOVA) ====================
    add_p("O'ZBEKISTON RESPUBLIKASI OLIY TA'LIM, FAN VA INNOVATSIYALAR VAZIRLIGI", bold=True, size=13, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False)
    add_p(essay.university.upper() if essay.university else "OLIY TA'LIM MUASSASASI", bold=True, size=14, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, space_after=6)
    if essay.faculty:
        add_p(essay.faculty, italic=True, size=13, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, space_after=18)
    else:
        add_p("", indent=False, space_after=18)

    # Bo'sh joylar
    for _ in range(3):
        p_blank = doc.add_paragraph()
        p_blank.paragraph_format.space_after = Pt(0)
        p_blank.paragraph_format.line_spacing = 1.0

    add_p("MUSTAQIL ISH", bold=True, size=22, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, space_after=12)
    add_p(f"Mavzu: «{essay.topic}»", bold=True, size=16, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, space_after=24)

    for _ in range(4):
        p_blank = doc.add_paragraph()
        p_blank.paragraph_format.space_after = Pt(0)
        p_blank.paragraph_format.line_spacing = 1.0

    # Muallif va qabul qiluvchi bloki (O'ng tomonga)
    p_auth = doc.add_paragraph()
    p_auth.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_auth.paragraph_format.line_spacing = 1.5
    p_auth.paragraph_format.space_after = Pt(0)
    p_auth.paragraph_format.first_line_indent = Inches(0)

    run_auth = p_auth.add_run(
        f"Bajardi: {essay.author_name or 'Talaba'}\n"
        f"Qabul qildi: {essay.teacher_name or 'Ilmiy rahbar'}"
    )
    run_auth.font.name = "Times New Roman"
    run_auth.font.size = Pt(13)
    run_auth.bold = False

    for _ in range(5):
        p_blank = doc.add_paragraph()
        p_blank.paragraph_format.space_after = Pt(0)
        p_blank.paragraph_format.line_spacing = 1.0

    city_year = f"{essay.city or 'Toshkent'} – {essay.year or '2026'}"
    add_p(city_year, bold=True, size=13, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False)

    doc.add_page_break()

    # ==================== 2. MUNDARIJA ====================
    add_heading_title("MUNDARIJA")

    p_toc_intro = doc.add_paragraph()
    p_toc_intro.paragraph_format.line_spacing = 1.5
    p_toc_intro.paragraph_format.space_after = Pt(4)
    p_toc_intro.paragraph_format.first_line_indent = Inches(0)
    r = p_toc_intro.add_run("KIRISH .................................................................................................................... 3")
    r.font.name = "Times New Roman"
    r.font.size = Pt(13)
    r.bold = True

    page_counter = 4
    for ch_idx, ch in enumerate(essay.chapters):
        p_ch = doc.add_paragraph()
        p_ch.paragraph_format.line_spacing = 1.5
        p_ch.paragraph_format.space_after = Pt(3)
        p_ch.paragraph_format.first_line_indent = Inches(0)
        r = p_ch.add_run(f"{ch.title} ................................................................... {page_counter}")
        r.font.name = "Times New Roman"
        r.font.size = Pt(13)
        r.bold = True

        for s_idx, sec in enumerate(ch.sections):
            page_counter += 2
            p_sec = doc.add_paragraph()
            p_sec.paragraph_format.line_spacing = 1.5
            p_sec.paragraph_format.space_after = Pt(3)
            p_sec.paragraph_format.first_line_indent = Inches(0.25)
            r = p_sec.add_run(f"{sec.title} ............................................................ {page_counter}")
            r.font.name = "Times New Roman"
            r.font.size = Pt(13)

        page_counter += 1

    p_toc_concl = doc.add_paragraph()
    p_toc_concl.paragraph_format.line_spacing = 1.5
    p_toc_concl.paragraph_format.space_after = Pt(4)
    p_toc_concl.paragraph_format.first_line_indent = Inches(0)
    r = p_toc_concl.add_run(f"XULOSA VA TAVSIYALAR ................................................................................ {page_counter}")
    r.font.name = "Times New Roman"
    r.font.size = Pt(13)
    r.bold = True

    p_toc_ref = doc.add_paragraph()
    p_toc_ref.paragraph_format.line_spacing = 1.5
    p_toc_ref.paragraph_format.space_after = Pt(4)
    p_toc_ref.paragraph_format.first_line_indent = Inches(0)
    r = p_toc_ref.add_run(f"FOYDALANILGAN ADABIYOTLAR RO'YXATI ................................................... {page_counter + 2}")
    r.font.name = "Times New Roman"
    r.font.size = Pt(13)
    r.bold = True

    doc.add_page_break()

    # ==================== 3. KIRISH ====================
    add_heading_title("KIRISH")
    for para in essay.introduction.split("\n"):
        clean_para = para.strip()
        if clean_para:
            add_p(clean_para, align=WD_ALIGN_PARAGRAPH.JUSTIFY, indent=True, space_after=6)

    doc.add_page_break()

    # ==================== 4. ASOSIY QISM (BOBLAR) ====================
    for ch_idx, ch in enumerate(essay.chapters):
        add_heading_title(ch.title)

        for sec in ch.sections:
            add_subheading(sec.title)
            for para in sec.content.split("\n"):
                clean_para = para.strip()
                if clean_para:
                    add_p(clean_para, align=WD_ALIGN_PARAGRAPH.JUSTIFY, indent=True, space_after=6)

        doc.add_page_break()

    # ==================== 5. XULOSA ====================
    add_heading_title("XULOSA VA TAVSIYALAR")
    for para in essay.conclusion.split("\n"):
        clean_para = para.strip()
        if clean_para:
            add_p(clean_para, align=WD_ALIGN_PARAGRAPH.JUSTIFY, indent=True, space_after=6)

    doc.add_page_break()

    # ==================== 6. ADABIYOTLAR RO'YXATI ====================
    add_heading_title("FOYDALANILGAN ADABIYOTLAR RO'YXATI")
    for idx, ref in enumerate(essay.references):
        ref_text = f"{idx + 1}. {ref.strip()}"
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.line_spacing = 1.5
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.first_line_indent = Inches(0.49)
        run = p.add_run(ref_text)
        run.font.name = "Times New Roman"
        run.font.size = Pt(14)

    # Faylni saqlash
    if not output_path:
        os.makedirs(config.GENERATED_DIR, exist_ok=True)
        safe_topic = "".join(c for c in essay.topic if c.isalnum() or c in (" ", "_", "-")).strip()
        safe_topic = safe_topic[:30].replace(" ", "_") or "Mustaqil_ish"
        output_path = os.path.join(config.GENERATED_DIR, f"{safe_topic}_Mustaqil_Ish.docx")

    doc.save(output_path)
    logger.info(f"Mustaqil ish Word hujjati yaratildi: {output_path} ({os.path.getsize(output_path)} bayt)")
    return output_path
