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
import textwrap
from PIL import Image, ImageDraw, ImageFont

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



def _infer_domain_metadata(topic: str) -> dict:
    t = topic.lower()
    if any(w in t for w in ["tarix", "temur", "bobur", "xonlik", "davlat", "urush", "madaniyat", "meros", "alloma", "navoiy", "falsafa"]):
        return {
            "faculty": "Tarix va gumanitar fanlar fakulteti",
            "subject": "Tarixiy va ijtimoiy-gumanitar fanlar",
            "refs": [
                f"{topic} tarixi va manbashunosligi. Darslik. — Toshkent: Fan va texnologiya, 2024. — 310 b.",
                "O'zbekiston tarixi: qadimgi davrdan bugungi kungacha. Akademik nashr. — Toshkent: O'zbekiston, 2023. — 420 b.",
                "Sohaga oid tarixiy qo'lyozmalar, manbalar va arxiv hujjatlari to'plami, 2024.",
                "Temur tuzuklari va davlat boshqaruvi merosi. — Toshkent: Adabiyot, 2023. — 256 b.",
                "Sharq allomalari va mutafakkirlari ilmiy merosi. — Samarqand: Zarafshon, 2024. — 190 b.",
                "O'zbekiston Respublikasi Fanlar akademiyasi Tarix instituti ilmiy to'plamlari, 2025.",
            ]
        }
    elif any(w in t for w in ["tibbiyot", "kasallik", "yurak", "qon", "davolash", "anatomiya", "klinika", "dorivor", "salomatlik"]):
        return {
            "faculty": "Davolash ishi va tibbiy profilaktika fakulteti",
            "subject": "Klinik va nazariy tibbiyot",
            "refs": [
                f"{topic}: etiologiyasi, patogenezi va klinik kechishi. Darslik. — Toshkent: Tibbiyot nashriyoti, 2024. — 380 b.",
                "Klinik diagnostika va zamonaviy davolash standartlari. — Toshkent: Yangi asr avlodi, 2023. — 450 b.",
                "Jahon sog'liqni saqlash tashkiloti (JSST) tavsiyalari va ilmiy hisobotlari, 2024-2025 yy.",
                "Ichki kasalliklar propedevtikasi va zamonaviy terapiya asoslari. — Toshkent: Fan, 2024. — 320 b.",
                "O'zbekiston Respublikasi Sog'liqni saqlash vazirligi klinik protokollari to'plami, 2025.",
                "Eksperimental va klinik tibbiyot jurnali ilmiy maqolalari, 2024.",
            ]
        }
    elif any(w in t for w in ["huquq", "qonun", "jinoyat", "sud", "fuqarolik", "konstitutsiya", "advokat"]):
        return {
            "faculty": "Yuridik va huquqshunoslik fakulteti",
            "subject": "Huquqshunoslik va davlat huquqi",
            "refs": [
                f"{topic}: nazariya va amaliyot. Darslik. — Toshkent: Yuridik adabiyotlar, 2024. — 340 b.",
                "O'zbekiston Respublikasi Konstitutsiyasi va qonunchilik hujjatlari to'plami. — Toshkent: Adolat, 2024.",
                "O'zbekiston Respublikasining tegishli Kodekslari va rasmiy sharhlari, 2024-2025 yy.",
                "Sud va huquqni muhofaza qiluvchi organlar faoliyatining huquqiy asoslari. — Toshkent: TDYuU, 2023. — 280 b.",
                "Xalqaro huquqiy me'yorlar va qiyosiy qonunchilik tahlili. — Toshkent: Huquq, 2024.",
                "Huquqiy axborot portali (lex.uz) me'yoriy hujjatlari, 2025.",
            ]
        }
    elif any(w in t for w in ["pedagogika", "ta'lim", "tarbiya", "maktab", "metod", "dars", "o'qituvchi", "psixologiya"]):
        return {
            "faculty": "Pedagogika va psixologiya fakulteti",
            "subject": "Zamonaviy pedagogik texnologiyalar",
            "refs": [
                f"{topic}: o'qitish metodikasi va zamonaviy yondashuvlar. — Toshkent: O'qituvchi, 2024. — 290 b.",
                "Uzluksiz ta'lim tizimida innovatsion pedagogik texnologiyalar. — Toshkent: Fan va texnologiya, 2023. — 315 b.",
                "Pedagogik mahorat va psixologiya asoslari. Darslik. — Toshkent: Iste'dod, 2024. — 260 b.",
                "Ilg'or xalqaro ta'lim tajribalari va dars ishlanmalari to'plami, 2024.",
                "Ta'lim sifatini baholash va ta'lim to'g'risidagi qonunchilik asoslari, 2025.",
            ]
        }
    elif any(w in t for w in ["iqtisod", "moliya", "bank", "buxgalteriya", "soliq", "marketing", "menejment", "bozor"]):
        return {
            "faculty": "Iqtisodiyot va moliya fakulteti",
            "subject": "Iqtisodiy tahlil va boshqaruv",
            "refs": [
                f"{topic}: nazariya, amaliyot va tahlil. Darslik. — Toshkent: Iqtisod-Moliya, 2024. — 350 b.",
                "Makroiqtisodiy barqarorlik va moliya bozorlari taraqqiyoti. — Toshkent: Fan, 2023. — 280 b.",
                "O'zbekiston Respublikasi Statistika agentligi ma'lumotlari (stat.uz), 2025-2026 yy.",
                "Zamonaviy korporativ boshqaruv va investitsiyalar tahlili. — Toshkent: Iqtisodiyot, 2024. — 320 b.",
                "Iqtisodiy islohotlar va sohani modernizatsiyalash strategiyasi. — Toshkent: Yangi asr, 2024.",
            ]
        }
    else:
        return {
            "faculty": "Tabiiy va ijtimoiy-gumanitar fanlar fakulteti",
            "subject": "Soha nazariyasi va amaliyoti",
            "refs": [
                f"{topic}: ilmiy-nazariy asoslar va amaliy tahlil. Darslik. — Toshkent: Fan va texnologiya, 2024. — 310 b.",
                "Zamonaviy ilmiy tadqiqotlar va innovatsion metodologiya. — Toshkent: Universitet, 2023. — 275 b.",
                "Sohaga oid me'yoriy-uslubiy qo'llanmalar va ilmiy maqolalar to'plami, 2024.",
                "Xalqaro ilmiy jurnallar va konferensiya materiallari tahlili, 2024-2025 yy.",
                "Sohani rivojlantirishning strategik istiqbollari va amaliy tavsiyalar. — Toshkent: O'zbekiston, 2024.",
            ]
        }


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

    domain_meta = _infer_domain_metadata(topic)

    fallback_essay = AcademicEssay(
        topic=topic,
        university=univ_str,
        faculty=domain_meta["faculty"],
        author_name=author_str,
        teacher_name="Dotsent, Ilmiy rahbar",
        year="2026",
        city="Toshkent",
        introduction=(
            f"Oliy ta'lim muassasalarida «{topic}» mavzusini tadqiq etish bugungi kunda nazariy va amaliy jihatdan dolzarb ahamiyat kasb etmoqda. "
            f"Ushbu yo'nalish {domain_meta['subject'].lower()} tizimida muhim o'rin tutib, sohaning asosiy qonuniyatlari va istiqbollarini belgilab beradi.\n\n"
            f"Tadqiqotning asosiy maqsadi — «{topic}» doirasidagi konseptual asoslarni o'rganish, sohadagi mavjud holatni tahlil qilish hamda samaradorlikni oshirish bo'yicha ilmiy xulosalar ishlab chiqishdan iborat. "
            "Ish davomida mavzuga oid asosiy ilmiy manbalar, xalqaro va mahalliy me'yorlar qiyosiy tahlil qilinib, shaxsiy ilmiy takliflar bayon etilgan."
        ),
        chapters=[
            Chapter(
                title=f"I BOB. «{topic.upper()}»NING ILMIY-NAZARIY ASOSLARI VA MOHIYATI",
                sections=[
                    ChapterSection(
                        title=f"1.1. «{topic}» tushunchasining nazariy mohiyati va shakllanish bosqichlari",
                        content=(
                            f"«{topic}» tushunchasining ilmiy poydevorini o'rganish shuni ko'rsatadiki, mazkur soha ko'p yillik tadqiqotlar va ilmiy izlanishlar natijasida takomillashib kelgan. "
                            f"Ilmiy adabiyotlarda {topic.lower()} bo'yicha turlicha konseptual yondashuvlar mavjud bo'lib, ularning har biri mavzuning o'ziga xos qirralarini ochib beradi.\n\n"
                            "Nazariy qonuniyatlarni solishtirish orqali ushbu sohaning fundamental qoidalari tizimlashtiriladi. "
                            "Bu esa mavzuni yanada chuqurroq anglash va uni amaliyot bilan bog'lashda muhim zamin yaratadi."
                        ),
                    ),
                    ChapterSection(
                        title=f"1.2. {topic} ning zamonaviy fanda tutgan o'rni va asosiy tamoyillari",
                        content=(
                            f"Har qanday ilmiy nazariyaning ahamiyati uning amaliy hayotdagi samaradorligi bilan belgilanadi. "
                            f"{topic} doirasidagi ilg'or tamoyillarni qo'llash tizimdagi noaniqliklarni kamaytiradi va aniq natijalarga erishishni ta'minlaydi.\n\n"
                            "Bugungi kunda sohadagi ilg'or tajribalarni umumlashtirish orqali samaradorlikni sezilarli darajada oshirish imkoniyatlari mavjud. "
                            "Bu jarayon uzluksiz yangilanish va zamonaviy usullardan unumli foydalanishni taqozo etadi."
                        ),
                    ),
                ],
            ),
            Chapter(
                title=f"II BOB. «{topic.upper()}»NING AMALIY TAHLILI VA TAKOMILLASHTIRISH YO'LLARI",
                sections=[
                    ChapterSection(
                        title=f"2.1. {topic} bo'yicha amaliy holat tahlili va uchrayotgan masalalar",
                        content=(
                            f"Amaliyot tahlili shuni ko'rsatadiki, «{topic}» sohasida ijobiy siljishlar bilan bir qatorda hal etilishi lozim bo'lgan qator vazifalar mavjud. "
                            "Xususan, uslubiy ta'minotni yanada boyitish va yangi yondashuvlarni kengroq tatbiq etish zarurati ko'zga tashlanadi.\n\n"
                            "Mavjud holatni kompleks o'rganish orqali jarayonlarning samaradorligiga ta'sir etuvchi asosiy omillar aniqlandi va tizimlashtirildi."
                        ),
                    ),
                    ChapterSection(
                        title=f"2.2. {topic} samaradorligini oshirish bo'yicha ilmiy-amaliy takliflar",
                        content=(
                            f"Olib borilgan tadqiqot natijalari asosida «{topic}» yo'nalishini takomillashtirish bo'yicha bir qator amaliy tavsiyalar ishlab chiqildi. "
                            "Birinchidan, jarayonlarga zamonaviy axborot va tahliliy vositalarni keng jalb etish maqsadga muvofiqdir.\n\n"
                            "Ikkinchidan, sohada monitoring va sifat nazoratini kuchaytirish yuzaga kelishi mumkin bo'lgan kamchiliklarning oldini oladi. "
                            "Mazkur tavsiyalar soha samaradorligini sifat jihatidan yangi bosqichga ko'tarishga xizmat qiladi."
                        ),
                    ),
                ],
            ),
        ],
        conclusion=(
            f"Xulosa qilib aytganda, «{topic}» mavzusida olib borilgan ushbu mustaqil ish sohaning nazariy va amaliy ahamiyati nihoyatda yuqori ekanligini tasdiqlaydi.\n\n"
            f"Ishda ilgari surilgan ilmiy-nazariy xulosalar va amaliy tavsiyalar {domain_meta['subject'].lower()} sohasida yangi yutuqlarga erishishda foydali qo'llanma bo'lib xizmat qiladi. "
            "Tadqiqot natijalari kelgusida mazkur yo'nalishni yanada chuqurroq o'rganish uchun mustahkam ilmiy asos yaratadi."
        ),
        references=domain_meta["refs"],
    )

    if not key:
        return fallback_essay

    client = genai.Client(api_key=key)
    candidate_models = [
        config.GEMINI_MODEL,
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-flash-latest",
    ]
    seen = set()
    models_to_try = [m for m in candidate_models if m and not (m in seen or seen.add(m))]

    prompt = f"""Sen — O'zbekistonning nufuzli OTM talabasisan. Berilgan mavzu bo'yicha Oliy ta'lim standartlariga (OTM) to'liq mos keladigan, chuqur ilmiy-tadqiqot darajasidagi MUSTAQIL ISH / REFERAT tayyorlashing kerak.

MAVZU: «{topic}»
TALABA ISMI: {author_str}
OTM NOMI: {univ_str}
FAKULTET YO'NALISHI: {domain_meta['faculty']}
TIL: {language} (o'zbekcha adabiy tilda, lotin alifbosida)

QAT'IY TALABLAR (100% MAVZUGA SADOQAT VA AKADEMIK SIFAT):
1. MAVZUGA 100% CHUQUR MOSLIK:
   - Matnning har bir qatori, sarlavhalari, bo'limlari va xulosalari AYNAN «{topic}» MAVZUSIGA BAXSHIDA BO'LISHI SHART!
   - Soha terminologiyasidan to'g'ri va savodli foydalaning (Tarix bo'lsa tarixiy voqealar va allomalar; Tibbiyot bo'lsa tibbiy atamalar; Huquq bo'lsa qonunlar; Pedagogika bo'lsa ta'lim metodikasi va h.k.).
   - Noo'rin yoki mavzuga aloqasiz umumiy shablonlarni aslo ishlatmang!

2. AKADEMIK DARAJA VA ILMIY USLUB:
   - Matn savodli, tahliliy va ilmiy dalillarga boy bo'lsin.
   - Har bir kichik bo'limda kamida 3-4 ta mazmunli, chuqur tahliliy abzas bo'lsin.
   - Adabiyotlar ro'yxatida aynan shu sohaga oid nufuzli darsliklar, ilmiy maqolalar va rasmiy manbalar bo'lsin.

3. HUJJAT TUZILISHI:
   - `topic`: «{topic}»
   - `university`: OTM nomi
   - `faculty`: Mavzuga mos fakultet nomi ({domain_meta['faculty']})
   - `author_name`: {author_str}
   - `teacher_name`: Ilmiy rahbar / O'qituvchi lavozimi va ismi
   - `year`: 2026
   - `city`: Toshkent (yoki tegishli shahar)
   - `introduction`: Mavzuning dolzarbligi, maqsadi, vazifalari va obyekti (kamida 3-4 ta abzas)
   - `chapters`: Kamida 2 ta asosiy BOB:
      * I Bob: Mavzuning nazariy va konseptual asoslari (2 ta kichik bo'lim)
      * II Bob: Mavzuning amaliy tahlili va takomillashtirish yo'llari (2 ta kichik bo'lim)
   - `conclusion`: Ilmiy xulosalar va amaliy tavsiyalar (kamida 3-4 ta abzas)
   - `references`: 6 dan 8 tagacha bo'lgan rasmiy va sohaga oid darsliklar ro'yxati

Javobni FAQAT AcademicEssay JSON formatida qaytar."""

    system_prompt = (
        "Siz Oliy Ta'lim Muassasasi ilmiy xodimi va talabasisiz. "
        f"Mavzu: «{topic}». Berilgan mavzuni chuqur ilmiy-akademik tilda, aniq faktlar, tahlillar va adabiyotlar bilan yoriting. "
        "Umumiy qoliplardan qoching, butun matn mavzuga 100% sodiq bo'lsin."
    )

    for model_name in models_to_try:
        try:
            logger.info(f"Mustaqil ish generatsiya qilinmoqda ({model_name}): {topic[:40]}...")
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=AcademicEssay,
                    temperature=0.7,
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


# ------------------ QO'LDA DAFTARGA YOZILGAN (HANDWRITTEN) VARIANT ------------------
def get_handwriting_font(size: int = 28):
    """Qo'lyozma shriftini oladi (assets papkasi, tizim shrifti yoki default)."""
    candidates = [
        os.path.join(config.ASSETS_DIR, "fonts", "segoepr.ttf"),
        os.path.join(os.path.dirname(__file__), "assets", "fonts", "segoepr.ttf"),
        r"C:\Windows\Fonts\segoepr.ttf",
        r"C:\Windows\Fonts\segoesc.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def create_handwritten_essay_pdf(
    essay: AcademicEssay,
    output_pdf_path: Optional[str] = None,
    paper_type: str = "blank",
) -> tuple:
    """
    AcademicEssay obyektidan A4 formatdagi oq qog'ozga ko'k ruchka siyohida
    qo'lda yozilgandek ko'p sahifali PDF hujjat va 1-sahifa rasm previewini yaratadi.
    Qaytaradi: (pdf_path, preview_image_path)
    """
    PAGE_W = 1654
    PAGE_H = 2338
    MARGIN_LEFT = 200
    MARGIN_RIGHT = 120
    MARGIN_TOP = 140
    MARGIN_BOTTOM = 140
    MAX_W = PAGE_W - MARGIN_LEFT - MARGIN_RIGHT
    START_Y = 160
    MAX_Y = PAGE_H - MARGIN_BOTTOM

    LINE_H = 56
    HEADING_LINE_H = 68

    INK_COLOR = (18, 52, 138)
    HEADING_COLOR = (12, 38, 120)
    BG_COLOR = (255, 255, 255)
    RULED_LINE_COLOR = (230, 235, 245)

    font_text = get_handwriting_font(30)
    font_bold = get_handwriting_font(32)
    font_subhead = get_handwriting_font(36)
    font_head = get_handwriting_font(42)
    font_title = get_handwriting_font(50)

    pages: List[Image.Image] = []
    current_page_idx = 1

    def new_page(is_cover: bool = False):
        nonlocal current_page_idx
        img = Image.new("RGB", (PAGE_W, PAGE_H), color=BG_COLOR)
        draw = ImageDraw.Draw(img)

        if paper_type == "lined":
            for y_line in range(START_Y, PAGE_H - MARGIN_BOTTOM, LINE_H):
                draw.line([(MARGIN_LEFT - 20, y_line + 38), (PAGE_W - MARGIN_RIGHT + 20, y_line + 38)], fill=RULED_LINE_COLOR, width=1)

        if not is_cover:
            p_text = f"- {current_page_idx} -"
            w_p = draw.textlength(p_text, font=font_text)
            draw.text(((PAGE_W - w_p) // 2, 70), p_text, fill=INK_COLOR, font=font_text)
            current_page_idx += 1

        pages.append(img)
        return img, draw

    # 1. TITUL VARAG'I (A4 Formatdagi Muqova)
    img_cover, draw_cover = new_page(is_cover=True)
    univ_text = essay.university or "O'ZBEKISTON RESPUBLIKASI OLIY TA'LIM MUASSASASI"
    ministry = "O'zbekiston Respublikasi Oliy ta'lim, fan va innovatsiyalar vazirligi"

    y = 180
    for line in textwrap.wrap(ministry, width=50):
        w = draw_cover.textlength(line, font=font_text)
        draw_cover.text(((PAGE_W - w) // 2, y), line, fill=INK_COLOR, font=font_text)
        y += LINE_H

    y += 20
    for line in textwrap.wrap(univ_text, width=44):
        w = draw_cover.textlength(line, font=font_bold)
        draw_cover.text(((PAGE_W - w) // 2, y), line, fill=HEADING_COLOR, font=font_bold)
        y += LINE_H

    if essay.faculty:
        y += 10
        for line in textwrap.wrap(essay.faculty, width=48):
            w = draw_cover.textlength(line, font=font_text)
            draw_cover.text(((PAGE_W - w) // 2, y), line, fill=INK_COLOR, font=font_text)
            y += LINE_H

    y = 820
    title_label = "MUSTAQIL ISH"
    w = draw_cover.textlength(title_label, font=font_title)
    draw_cover.text(((PAGE_W - w) // 2, y), title_label, fill=HEADING_COLOR, font=font_title)

    y += int(LINE_H * 1.8)
    topic_header = f"Mavzu: «{essay.topic}»"
    for line in textwrap.wrap(topic_header, width=38):
        w = draw_cover.textlength(line, font=font_head)
        draw_cover.text(((PAGE_W - w) // 2, y), line, fill=INK_COLOR, font=font_head)
        y += HEADING_LINE_H

    y = 1520
    auth_x = PAGE_W - 680
    draw_cover.text((auth_x, y), "Bajardi:", fill=INK_COLOR, font=font_text)
    y += LINE_H
    author_str = essay.author_name or "Talaba"
    for line in textwrap.wrap(author_str, width=28):
        draw_cover.text((auth_x + 30, y), line, fill=HEADING_COLOR, font=font_bold)
        y += LINE_H

    y += 20
    draw_cover.text((auth_x, y), "Qabul qildi:", fill=INK_COLOR, font=font_text)
    y += LINE_H
    teacher_str = essay.teacher_name or "Ilmiy rahbar / O'qituvchi"
    for line in textwrap.wrap(teacher_str, width=28):
        draw_cover.text((auth_x + 30, y), line, fill=HEADING_COLOR, font=font_bold)
        y += LINE_H

    city_year = f"{essay.city or 'Toshkent'} – {essay.year or '2026'}"
    w = draw_cover.textlength(city_year, font=font_bold)
    draw_cover.text(((PAGE_W - w) // 2, PAGE_H - 180), city_year, fill=INK_COLOR, font=font_bold)

    current_img, current_draw = new_page(is_cover=False)
    current_y = START_Y

    def add_line(text, font=font_text, color=INK_COLOR, indent=False, center=False):
        nonlocal current_img, current_draw, current_y
        if current_y > MAX_Y:
            current_img, current_draw = new_page(is_cover=False)
            current_y = START_Y

        if center:
            w = current_draw.textlength(text, font=font)
            x = (PAGE_W - w) // 2
        else:
            x = MARGIN_LEFT + (75 if indent else 0)

        current_draw.text((x, current_y), text, fill=color, font=font)
        current_y += LINE_H

    def add_paragraph(text, font=font_text, color=INK_COLOR):
        nonlocal current_y
        words = text.split()
        if not words:
            return

        line_words = []
        is_first = True
        for w in words:
            test_line = " ".join(line_words + [w])
            indent_px = 75 if is_first else 0
            if current_draw.textlength(test_line, font=font) + indent_px <= MAX_W:
                line_words.append(w)
            else:
                add_line(" ".join(line_words), font=font, color=color, indent=is_first)
                is_first = False
                line_words = [w]
        if line_words:
            add_line(" ".join(line_words), font=font, color=color, indent=is_first)

        current_y += int(LINE_H * 0.4)

    def add_heading(text):
        nonlocal current_y
        if current_y > MAX_Y - 200:
            current_img, current_draw = new_page(is_cover=False)
            current_y = START_Y
        else:
            current_y += int(LINE_H * 0.6)
        add_line(text, font=font_head, color=HEADING_COLOR, center=True)
        current_y += int(LINE_H * 0.6)

    def add_subheading(text):
        nonlocal current_y
        if current_y > MAX_Y - 150:
            current_img, current_draw = new_page(is_cover=False)
            current_y = START_Y
        else:
            current_y += int(LINE_H * 0.4)
        add_line(text, font=font_subhead, color=HEADING_COLOR, indent=False)
        current_y += int(LINE_H * 0.3)

    # 2. MUNDARIJA
    add_heading("MUNDARIJA")
    add_line("KIRISH .......................................................................... 3-bet", font=font_bold)
    current_y += int(LINE_H * 0.3)

    p_counter = 4
    for ch in essay.chapters:
        add_line(f"{ch.title} .......................................................... {p_counter}-bet", font=font_bold)
        current_y += int(LINE_H * 0.2)
        for sec in ch.sections:
            add_line(f"   {sec.title} ................................................. {p_counter}-bet", font=font_text)
        p_counter += 2
        current_y += int(LINE_H * 0.3)

    add_line(f"XULOSA VA TAVSIYALAR .......................................... {p_counter}-bet", font=font_bold)
    current_y += int(LINE_H * 0.2)
    add_line(f"FOYDALANILGAN ADABIYOTLAR ................................. {p_counter + 1}-bet", font=font_bold)

    # 3. KIRISH
    current_img, current_draw = new_page(is_cover=False)
    current_y = START_Y
    add_heading("KIRISH")
    for para in essay.introduction.split("\n"):
        p = para.strip()
        if p:
            add_paragraph(p)

    # 4. BOBLAR
    for ch in essay.chapters:
        current_img, current_draw = new_page(is_cover=False)
        current_y = START_Y
        add_heading(ch.title)
        for sec in ch.sections:
            add_subheading(sec.title)
            for para in sec.content.split("\n"):
                p = para.strip()
                if p:
                    add_paragraph(p)

    # 5. XULOSA
    current_img, current_draw = new_page(is_cover=False)
    current_y = START_Y
    add_heading("XULOSA VA TAVSIYALAR")
    for para in essay.conclusion.split("\n"):
        p = para.strip()
        if p:
            add_paragraph(p)

    # 6. ADABIYOTLAR
    current_img, current_draw = new_page(is_cover=False)
    current_y = START_Y
    add_heading("FOYDALANILGAN ADABIYOTLAR RO'YXATI")
    for idx, ref in enumerate(essay.references):
        ref_text = f"{idx + 1}. {ref.strip()}"
        add_paragraph(ref_text)

    # Fayllarni saqlash
    os.makedirs(config.GENERATED_DIR, exist_ok=True)
    safe_topic = "".join(c for c in essay.topic if c.isalnum() or c in (" ", "_", "-")).strip()
    safe_topic = safe_topic[:30].replace(" ", "_") or "Mustaqil_Ish"

    if not output_pdf_path:
        output_pdf_path = os.path.join(config.GENERATED_DIR, f"{safe_topic}_A4_Qolda_Yozilgan.pdf")

    preview_img_path = os.path.join(config.GENERATED_DIR, f"{safe_topic}_preview_p1.png")
    if pages:
        pages[0].save(preview_img_path)
        pages[0].save(
            output_pdf_path,
            save_all=True,
            append_images=pages[1:],
            resolution=150.0,
        )

    logger.info(f"A4 formatda qo'lda yozilgan Mustaqil Ish PDF yaratildi: {output_pdf_path} ({len(pages)} sahifa)")
    return output_pdf_path, preview_img_path

