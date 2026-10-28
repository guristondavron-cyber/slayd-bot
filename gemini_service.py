import json
import logging
import re
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

import config

logger = logging.getLogger(__name__)


class CardItem(BaseModel):
    title: str = Field(description="Karta yoki punktning sarlavhasi (2-5 so'z)")
    description: str = Field(description="Loyiha yoki punkt haqida tushunarli, mazmunli qisqa izoh (15-25 so'z)")
    badge: Optional[str] = Field(default=None, description="Qisqa belgi yoki kategoriya (masalan: '01', 'Afzallik', 'Yechim', 'Muhim')")


class StatItem(BaseModel):
    number: str = Field(description="Diqqatni tortuvchi raqam yoki foiz (masalan: '85%', '3.5X', '$12M', '100K+', '24/7')")
    label: str = Field(description="Raqam nimaniki ekanligi haqida qisqa sarlavha (2-4 so'z)")
    description: Optional[str] = Field(default=None, description="Qo'shimcha qisqa izoh (1 jumla)")


class ComparisonColumn(BaseModel):
    header: str = Field(description="Ustun sarlavhasi (masalan: 'An'anaviy usul', 'AI yechimi', 'Afzalliklar')")
    badge: Optional[str] = Field(default=None, description="Ustun holati belgisi (masalan: 'Eski', 'Yangi', 'Oddiy')")
    points: List[str] = Field(description="3-4 ta asosiy punktlar ro'yxati")


class SlideContent(BaseModel):
    layout: Literal[
        "title_slide",
        "cards_grid",
        "stats_metrics",
        "chart_slide",
        "comparison",
        "timeline_steps",
        "matrix_2x2",
        "quote_highlight",
        "checklist_points",
        "conclusion",
    ] = Field(description="Slaydning vizual joylashuv turi")
    category_badge: str = Field(description="Slayd tepasidagi kichik kategoriya tegi (masalan: 'KIRISH', 'MUAMMO', 'YECHIM', 'STATISTIKA', 'BOSQICHLAR', 'XULOSA')")
    title: str = Field(description="Slaydning asosiy sarlavhasi (kuchli, jozibali, 4-8 so'z)")
    subtitle: Optional[str] = Field(default=None, description="Sarlavhani to'ldiruvchi qisqa izoh yoki savol (10-15 so'z)")
    
    # cards_grid uchun (3 yoki 4 ta karta)
    cards: Optional[List[CardItem]] = Field(default=None, description="cards_grid yoki umumiy punktlar uchun kartalar")
    
    # stats_metrics va chart_slide uchun (3 yoki 4 ta statistika)
    stats: Optional[List[StatItem]] = Field(default=None, description="stats_metrics va chart_slide uchun 3-4 ta muhim raqamlar")
    chart_type: Optional[str] = Field(default="column", description="chart_slide uchun: 'column' (ustunli) yoki 'pie' (doiraviy)")
    
    # comparison uchun
    comparison_col1: Optional[ComparisonColumn] = Field(default=None, description="Solishtirishning 1-ustuni")
    comparison_col2: Optional[ComparisonColumn] = Field(default=None, description="Solishtirishning 2-ustuni")
    
    # timeline_steps uchun
    steps: Optional[List[CardItem]] = Field(default=None, description="Ketma-ket 3-4 ta bosqich yoki harakatlar rejasi")
    
    # quote_highlight uchun
    quote_text: Optional[str] = Field(default=None, description="Diqqatni tortuvchi asosiy iqtibos yoki g'oya (1-2 jumla)")
    quote_author: Optional[str] = Field(default=None, description="Iqtibos muallifi yoki manbasi (masalan: 'Stiv Jobs', 'Bozor Tahlili', 'Ekspert')")

    # checklist_points uchun
    checklist: Optional[List[str]] = Field(default=None, description="3-5 ta amaliy tavsiya, qoida yoki tasdiqlangan punktlar ro'yxati")

    # matrix_2x2 uchun
    matrix_items: Optional[List[CardItem]] = Field(default=None, description="2x2 matritsa uchun roppa-rosa 4 ta karta")

    # Rasm va vizualizatsiya
    image_keyword: Optional[str] = Field(default=None, description="Ushbu slayd mavzusiga mos inglizcha 2-4 so'zdan iborat aniq foto qidiruv so'zi (masalan: 'artificial intelligence robot', 'cotton harvest machine')")

    # conclusion / call to action
    highlight_takeaway: Optional[str] = Field(default=None, description="Asosiy chaqiriq, yakuniy xulosa yoki iqtibos")
    speaker_notes: Optional[str] = Field(default=None, description="Spiker uchun qisqa maslahat")
    speaker_speech: Optional[str] = Field(default=None, description="Spiker sahnada tinglovchilarga aytib berishi kerak bo'lgan 2-4 jumlalik jonli, ta'sirchan nutq matni")


class PresentationContent(BaseModel):
    topic: str = Field(description="Taqdimotning umumiy mavzusi")
    language: str = Field(default="uz", description="Taqdimot tili")
    slides: List[SlideContent] = Field(description="Belgilangan miqdordagi slaydlar ketma-ketligi")


def build_system_prompt(
    topic: str,
    slide_count: int,
    language: str = "uz",
    with_speech: bool = True,
    mode: str = "general",
) -> str:
    lang_instruction = {
        "uz": "Barcha matnlar, sarlavhalar va tushuntirishlar o'zbek adabiy tilida (lotin alifbosida), juda chiroyli va professional uslubda bo'lsin.",
        "ru": "Все тексты, заголовки и описания должны быть на грамотном русском языке.",
        "en": "All texts, headings, and explanations must be in clear, professional English.",
    }.get(language, "O'zbek tilida yozing.")

    speech_instruction = (
        "Har bir slayd uchun 'speaker_speech' maydoniga spiker minbarda turib tinglovchilarga aytib berishi kerak bo'lgan 2-4 jumlalik jonli, ta'sirchan nutq matnini yozing."
        if with_speech
        else "Spiker nutqi talab qilinmaydi, 'speaker_speech' maydonini bo'sh (null) qoldiring."
    )

    mode_guidelines = {
        "education": (
            "TAQDIMOT YO'NALISHI: TA'LIM, DARSLIK VA AKADEMIK REFERAT.\n"
            "- Taqdimot strukturasi: Mavzuning dolzarbligi va maqsadi -> Ilmiy-nazariy asoslar va qonuniyatlar -> Asosiy tushunchalar va terminlar -> Amaliy tahlil va misollar -> Solishtirma jadval -> Xulosa va tavsiyalar -> Foydalanilgan manbalar va adabiyotlar.\n"
            "- Talabalar va tinglovchilar uchun chuqur ilmiy asoslangan, faktlarga boy akademik tilda yozing."
        ),
        "business": (
            "TAQDIMOT YO'NALISHI: BIZNES, STRATEGIYA VA INVESTITSIYA.\n"
            "- Taqdimot strukturasi: Bozor tahlili -> Strategik yo'nalishlar -> Asosiy ko'rsatkichlar -> Raqobat ustunliklari -> Rivojlanish rejasi.\n"
            "- Aniq tahliliy, moliyaviy va strategik atamalar, ko'rsatkichlardan foydalaning."
        ),
        "analytics": (
            "TAQDIMOT YO'NALISHI: TAHLILIY HISOBOT VA STATISTIKA.\n"
            "- Taqdimot strukturasi: Asosiy strategik KPIlar -> O'sish dinamikasi va tahliliy trendlar -> Qiyosiy ko'rsatkichlar -> Tahliliy xulosalar.\n"
            "- Aniq foizlar, nisbatlar, jadvallar va chuqur tahliliy faktlarga asoslaning."
        ),
        "general": (
            "TAQDIMOT YO'NALISHI: PROFESSIONAL AKADEMIK VA EXECUTIVE TAQDIMOT.\n"
            "- Mavzuning eng muhim, qiziqarli, mazmunli va ta'sirchan jihatlarini ochib bering."
        ),
    }.get(mode, "Professional taqdimot tayyorlang.")

    return f"""Siz jahon miqyosidagi yetakchi taqdimot dizayneri va professional spikersiz.
Siz yaratgan taqdimotlar xuddi professional ekspert tomonidan soatlab ijodiy o'ylab topilgandek, jonli, ta'sirchan, zamonaviy va chuqur mantiqqa ega bo'lishi shart.

MAVZU: "{topic}"

{mode_guidelines}

TIL TALABI:
{lang_instruction}

MUHIM QAT'IY TALABLAR (MAVZUGA TO'LIQ SADOQAT VA DIZAYN):
1. MAVZUGA 100% SADOQAT VA CHUQUR MOSLIK:
   - Taqdimotning 1-slaydidanoq oxirgi slaydigacha BARCHA matnlar, sarlavhalar, punktlar, faktlar va tahlillar AYNAN BERILGAN MAVZU: "{topic}" GA BAXSHIDA BO'LISHI SHART!
   - Agar mavzu Tarix bo'lsa — tarixiy shaxslar, sanalar, davlat boshqaruvi, janglar va meros haqida yozing.
   - Agar mavzu Tibbiyot yoki Biologiya bo'lsa — inson a'zolari, kasalliklar, hujayra, davolash va anatomik ilmiy ma'lumotlarni yozing.
   - Agar mavzu Adabiyot yoki Til bo'lsa — asarlar, g'azallar, mualliflar va til qoidalari haqida yozing.
   - Agar mavzu Texnologiya/Dasturlash bo'lsa — arxitektura, kod, algoritmlar va texnologik yechimlarni yozing.
   - Boshqa sohalarga oid mavzularda hech qachon noo'rin biznes/startap andozalarini ("Bozor hajmi", "Xarajat qisqarishi", "ROI", "Bozor tahlili") aralashtirmang! Mavzuning o'z sohasiga xos tushunchalarni yoriting.

2. JAMI SLAYDLAR SONI: 'slides' ro'yxatida ANIQ VA ROPPA-ROSA {slide_count} TA SLAYD BO'LISHI SHART!
   - Kam ham, ko'p ham bo'lmasin. Aniq {slide_count} ta unikal slayd.

3. VIZUAL RASM KALIT SO'ZLARI ('image_keyword'):
   - HAR BIR SLAYD uchun 'image_keyword' maydoniga USHBU SLAYD MAVZUSIGA 100% MOS KELUVCHI, INGLIZ TILIDAGI 3-5 TA ANIQ SO'Z KIRITING (Hech qachon null yoki bo'sh qoldirmang!).
   - Masalan: Tarix uchun — "ancient Samarkand Registan Timur monument historical 4k", Tibbiyot uchun — "human cardiovascular system heart medical illustration scientific", Biologiya uchun — "plant cell microscope biology laboratory 4k".
   - Bu kalit so'zlar bo'yicha slaydlarga fotorealistik va mavzuga to'liq mos rasmlar yuklanadi.

4. INSON DIZAYNERI USLUBI — KUCHLI VA MAZMUNLI SARLAVHALAR:
   - "Kirish", "Asosiy tushuncha", "Omil 1", "Strategiya 2" kabi zerikarli va qolip so'zlar QAT'IYAN MAN ETILADI!
   - Sarlavhalar o'quvchi diqqatini darhol jalb qiluvchi, mavzuning tub mohiyatini ochib beruvchi bo'lsin.
   - Kategoriya tegi ('category_badge') 1-2 so'zdan iborat professional belgi bo'lsin (masalan: 'ILMIY ASOS', 'CHUQUR TAHLIL', 'TARAQQIYOT BOSQICHI', 'XULOSA').
   - Har bir karta yoki punktning izohi 15-25 ta so'zdan iborat, aniq atamalar, ma'lumotlar va amaliy tavsiyalar bilan to'ldirilsin.

5. HAR BIR SLAYDNING VIZUAL STRUKTURASI ALMASHIB TURISHI SHART:
   - Ketma-ket bir xil layout ishlatilmasin!
   - Foydalaniladigan layout turlari: "title_slide", "cards_grid", "chart_slide", "stats_metrics", "comparison", "timeline_steps", "matrix_2x2", "quote_highlight", "checklist_points", "conclusion".

6. JONLI VA TA'SIRCHAN SPIKER NUTQI ('speaker_speech'):
   - {speech_instruction}
"""


def _clean_json_string(text: str) -> str:
    """Extract JSON object from response even if enclosed in markdown code blocks."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    
    # Try finding the first { and last }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1]
    
    return text


def _get_extra_thematic_slides(topic: str, language: str = "uz", with_speech: bool = True) -> List[SlideContent]:
    """Slaydlar soni kam chiqqan taqdirda mavzuga 100% mos va unikal boyituvchi sifatli slaydlar bazasi."""
    short_t = topic if len(topic) < 40 else topic[:40] + "..."
    clean_t = re.sub(r"[^a-zA-Z0-9\s]", " ", topic).strip()
    safe_kw = " ".join(clean_t.split()[:4]) or "presentation topic"
    spk = lambda s: s if with_speech else None

    return [
        SlideContent(
            layout="cards_grid",
            category_badge="CHUQUR ILMIY TAHLIL",
            title=f"{short_t}: Asosiy Konseptual Tamoyillar",
            subtitle=f"{short_t} mavzusining mohiyatini belgilab beruvchi fundamental yo'nalishlar",
            cards=[
                CardItem(title="Nazariy Poydevor", description=f"{short_t} sohasidagi ilmiy-nazariy tushunchalar va asosiy qonuniyatlar tizimi.", badge="01. Asos"),
                CardItem(title="Tizimli Aloqadorlik", description=f"{short_t} doirasidagi barcha elementlarning o'zaro uzviy bog'liqligi va uyg'unligi.", badge="02. Tizim"),
                CardItem(title="Amaliy Samaradorlik", description=f"{short_t} bo'yicha ishlab chiqilgan yondashuvlarning hayotiy qo'llanilishi va natijadorligi.", badge="03. Natija"),
            ],
            image_keyword=f"{safe_kw} concepts theory analysis high quality",
            speaker_speech=spk(f"Ushbu slaydda {short_t} mavzusining asosiy poydevori bo'lgan konseptual tamoyillarni ko'rib chiqamiz."),
        ),
        SlideContent(
            layout="comparison",
            category_badge="QIYOSIY TAHLIL",
            title=f"{short_t}: Klassik vs Zamonaviy Yondashuv",
            subtitle=f"{short_t} bo'yicha an'anaviy qarashlar hamda zamonaviy ilg'or tajribalar solishtiruvi",
            comparison_col1=ComparisonColumn(
                header="An'anaviy Qarashlar",
                badge="Klassik",
                points=[
                    f"{short_t} bo'yicha dastlabki nazariy tushunchalar",
                    "Cheklangan manbalar va an'anaviy usullar",
                    "Vaqt va resurs talab etuvchi tajribalar",
                ],
            ),
            comparison_col2=ComparisonColumn(
                header="Ilg'or Yechimlar",
                badge="Zamonaviy",
                points=[
                    f"{short_t} ning zamonaviy ilmiy va amaliy ahamiyati",
                    "Yangi texnologiyalar va kengaytirilgan imkoniyatlar",
                    "Tezkor moslashuvchanlik va yuqori samaradorlik",
                ],
            ),
            image_keyword=f"{safe_kw} modern scientific comparison research",
            speaker_speech=spk(f"{short_t} bo'yicha klassik va zamonaviy yondashuvlarni solishtirganda, yangi usullarning afzalliklari yaqqol ko'rinadi."),
        ),
        SlideContent(
            layout="timeline_steps",
            category_badge="TARAQQIYOT BOSQICHLARI",
            title=f"{short_t}: Rivojlanish Yo'l Xaritasi",
            subtitle=f"{short_t} ni tizimli ravishda o'rganish va hayotga tatbiq etish qadamlari",
            steps=[
                CardItem(title="1. Dastlabki O'rganish", description=f"{short_t} ning kelib chiqishi va asosiy manbalarini tahlil qilish.", badge="1-Qadam"),
                CardItem(title="2. Chuqur Tadqiqot", description=f"{short_t} dagi qonuniyatlar va amaliy omillarni solishtirish.", badge="2-Qadam"),
                CardItem(title="3. Amaliy Sinov", description=f"{short_t} bo'yicha ilg'or tajribalarni amaliyotga joriy etish.", badge="3-Qadam"),
                CardItem(title="4. Kengaytirish", description=f"{short_t} natijalarini to'liq mustahkamlash va keng joriy qilish.", badge="4-Qadam"),
            ],
            image_keyword=f"{safe_kw} timeline progression documentary",
            speaker_speech=spk(f"{short_t} ni tizimli amalga oshirish to'rtta muhim bosqichga tayanadi."),
        ),
        SlideContent(
            layout="matrix_2x2",
            category_badge="4 TA ASOSIY USTUN",
            title=f"{short_t}: Barqarorlik Matritsasi",
            subtitle=f"{short_t} mavzusini 4 ta asosiy burchak bo'yicha kompleks tahlili",
            matrix_items=[
                CardItem(title="Ilmiy Asos", description=f"{short_t} ning ishonchli nazariy va faktik dalillarga asoslanganligi.", badge="01. Nazariya"),
                CardItem(title="Metodologiya", description=f"{short_t} ni o'rganishda qo'llaniladigan samarali vositalar.", badge="02. Metod"),
                CardItem(title="Amaliy Tajriba", description=f"{short_t} bo'yicha mahalliy va xalqaro tajribalarni qo'llash.", badge="03. Amaliyot"),
                CardItem(title="Istiqbolli Natija", description=f"{short_t} ning kelajakdagi yangi rivojlanish marralari.", badge="04. Istiqbol"),
            ],
            image_keyword=f"{safe_kw} matrix pillars structure",
            speaker_speech=spk(f"Ushbu matritsa orqali biz {short_t} ning to'rtta mustahkam ustunini ko'rishimiz mumkin."),
        ),
        SlideContent(
            layout="quote_highlight",
            category_badge="ASOSIY FALSAFA",
            title=f"{short_t}: Bosh Ilmiy G'oya",
            subtitle=f"{short_t} ning chuqur ma'nosi va strategik ahamiyati",
            quote_text=f"\"{short_t} — bu soha taraqqiyotini yangi bosqichga olib chiquvchi va kelajakdagi yutuqlarni belgilab beruvchi mustahkam poydevordir.\"",
            quote_author=f"{short_t} Ekspert Xulosasi",
            highlight_takeaway=f"{short_t} bo'yicha tizimli yondashuv har qanday qiyin vazifaning to'g'ri yechimidir.",
            image_keyword=f"{safe_kw} philosophy wisdom reflection",
            speaker_speech=spk(f"Ushbu g'oya {short_t} ning barcha maqsad va intilishlarini to'liq ifodalaydi."),
        ),
        SlideContent(
            layout="checklist_points",
            category_badge="AMALIY TAVSIYALAR",
            title=f"{short_t}: Muvaffaqiyat Qoidalari",
            subtitle=f"{short_t} bo'yicha kutilgan yuksak natijalarga erishish mezonlari",
            checklist=[
                f"{short_t} ning barcha qonuniyatlariga qat'iy va izchil amal qilish",
                f"{short_t} jarayonlarini doimiy monitoring va tahlil qilib borish",
                f"{short_t} sohasidagi yangi xalqaro ilmiy tajribalarni o'rganish",
                f"{short_t} natijalarini amaliyotga uzluksiz tatbiq etish",
            ],
            image_keyword=f"{safe_kw} checklist success guidelines",
            speaker_speech=spk(f"Mana shu to'rtta asosiy qoidaga amal qilish {short_t} bo'yicha muvaffaqiyat garovidir."),
        ),
    ]


def _ensure_slide_count(
    presentation: PresentationContent,
    target_count: int,
    topic: str,
    language: str = "uz",
    with_speech: bool = True,
) -> PresentationContent:
    """Slaydlar soni foydalanuvchi so'ragan aniq target_count ga teng bo'lishini 100% kafolatlaydi."""
    slides = presentation.slides
    if len(slides) == target_count:
        return presentation

    if len(slides) > target_count:
        conclusion = next((s for s in reversed(slides) if s.layout == "conclusion"), slides[-1])
        new_slides = slides[: target_count - 1]
        new_slides.append(conclusion)
        presentation.slides = new_slides
        return presentation

    # Agar kam bo'lsa:
    conclusion = None
    if slides and slides[-1].layout == "conclusion":
        conclusion = slides.pop()

    extra_pool = _get_extra_thematic_slides(topic, language, with_speech=with_speech)
    pool_idx = 0
    while len(slides) < (target_count - (1 if conclusion else 0)):
        template = extra_pool[pool_idx % len(extra_pool)]
        slides.append(template.model_copy(deep=True))
        pool_idx += 1

    if conclusion:
        slides.append(conclusion)
    elif len(slides) < target_count:
        slides.append(
            SlideContent(
                layout="conclusion",
                category_badge="XULOSA",
                title="Xulosalar va Keyingi Qadamlar",
                subtitle="Mavzu bo'yicha asosiy xulosa va istiqbollar",
                highlight_takeaway="\"Eng yaxshi investitsiya — bu bilim va rivojlanishdir.\"",
                cards=[
                    CardItem(title="Katta Imkoniyatlar", description="Harakatni bugundan boshlash yetakchilik garovidir.", badge="Natija"),
                    CardItem(title="Savol-Javob", description="E'tiboringiz uchun rahmat, savollaringizni berishingiz mumkin.", badge="Aloqa"),
                ],
                speaker_speech="E'tiboringiz uchun katta rahmat! Agar savollaringiz bo'lsa, mamnuniyat bilan javob berishga tayyorman." if with_speech else None,
            )
        )

    presentation.slides = slides[:target_count]
    return presentation


async def generate_presentation_with_gemini(
    topic: str,
    slide_count: int = 5,
    language: str = "uz",
    with_speech: bool = True,
    mode: str = "general",
    api_key: Optional[str] = None,
    use_search: bool = False,
) -> PresentationContent:
    """Gemini API orqali ko'p modelli zanjir (fallback chain) va Google Search grounding bilan taqdimot generatsiya qiladi."""
    key = api_key or config.GEMINI_API_KEY
    if not key:
        raise ValueError(
            "GEMINI_API_KEY topilmadi! Iltimos, .env fayliga GEMINI_API_KEY kalitini kiriting yoki botga yuboring."
        )

    client = genai.Client(api_key=key)
    prompt = build_system_prompt(topic, slide_count, language, with_speech=with_speech, mode=mode)

    candidate_models = [
        config.GEMINI_MODEL,
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-flash-latest",
    ]
    seen = set()
    models_to_try = [m for m in candidate_models if m and not (m in seen or seen.add(m))]

    last_error = None

    # 1. Agar use_search faollashtirilgan bo'lsa, Google Search grounding bilan sinab ko'ramiz
    if use_search:
        for model_name in models_to_try[:2]:
            try:
                logger.info(f"Gemini {model_name} Google Search grounding bilan ishga tushirilmoqda: {topic}...")
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        tools=[types.Tool(google_search=types.GoogleSearch())],
                        response_mime_type="application/json",
                        response_schema=PresentationContent,
                        temperature=0.7,
                    ),
                )
                raw_text = response.text or ""
                cleaned_json = _clean_json_string(raw_text)
                presentation = PresentationContent.model_validate_json(cleaned_json)
                return _ensure_slide_count(presentation, slide_count, topic, language, with_speech=with_speech)
            except Exception as se:
                logger.warning(f"Google Search grounding xatosi ({model_name}): {se}. Standart rejimga o'tilmoqda...")

    # 2. Standart strukturaviy generatsiya
    for model_name in models_to_try:
        try:
            logger.info(f"Gemini {model_name} orqali {slide_count} ta slayd yaratilmoqda (rejim: {mode}, nutq: {with_speech})...")
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=PresentationContent,
                    temperature=0.7,
                ),
            )
            raw_text = response.text or ""
            cleaned_json = _clean_json_string(raw_text)
            presentation = PresentationContent.model_validate_json(cleaned_json)
            return _ensure_slide_count(presentation, slide_count, topic, language, with_speech=with_speech)
        except Exception as e:
            logger.warning(f"Model {model_name} da xatolik yuz berdi: {e}. Keyingi modelga o'tilmoqda...")
            last_error = e
            continue

    for model_name in models_to_try[:2]:
        try:
            logger.info(f"Fallback text JSON call: {model_name}...")
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt + f"\n\nQAT'IY TALAB: Javobni faqat va faqat to'g'ri JSON formatida qaytaring. 'slides' massivida ROPPA-ROSA {slide_count} ta slayd bo'lsin.",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7,
                ),
            )
            cleaned_json = _clean_json_string(response.text or "{}")
            presentation = PresentationContent.model_validate_json(cleaned_json)
            return _ensure_slide_count(presentation, slide_count, topic, language, with_speech=with_speech)
        except Exception as e:
            last_error = e
            continue

    logger.error(f"Barcha modellar sinab ko'rildi, oxirgi xatolik: {last_error}")
    return generate_mock_presentation(topic, slide_count=slide_count, language=language, with_speech=with_speech)


def build_document_prompt(doc_text: str, slide_count: int, language: str = "uz", with_speech: bool = True) -> str:
    lang_instruction = {
        "uz": "Barcha matnlar va sarlavhalar o'zbek adabiy tilida (lotin alifbosida) bo'lsin.",
        "ru": "Все тексты и заголовки должны быть на качественном русском языке.",
        "en": "All texts and headings must be in clear, professional English.",
    }.get(language, "O'zbek tilida yozing.")

    speech_instruction = (
        "Har bir slayd uchun 'speaker_speech' maydoniga spiker tinglovchilarga aytib berishi kerak bo'lgan 2-4 jumlalik jonli nutq matnini yozing."
        if with_speech
        else "Spiker nutqi talab qilinmaydi, 'speaker_speech' maydonini bo'sh (null) qoldiring."
    )

    return f"""Siz professional taqdimotlar tahlilchisisiz.
Quyida berilgan hujjat/maqola matnidan eng muhim asosiy g'oyalar, xulosalar, faktlar va statistikani ajratib olib, 
aynan shu manba asosida ROPPA-ROSA {slide_count} TA SLAYDDAN IBORAT va har bir slaydi turfa xil zamonaviy dizaynga ega taqdimot kontentini tayyorlang.

MANBA HUJJAT MATNI:
\"\"\"
{doc_text[:12000]}
\"\"\"

TIL TALABI:
{lang_instruction}

MUHIM QOIDALAR:
1. Jami roppa-rosa {slide_count} ta slayd tuzing. 'slides' massivida aniq {slide_count} ta element bo'lishi SHART.
2. Har bir slayd mazmuniga qarab har xil layout tanlang: "title_slide", "cards_grid", "chart_slide", "stats_metrics", "comparison", "timeline_steps", "matrix_2x2", "quote_highlight", "checklist_points", "conclusion".
3. {speech_instruction}
"""


async def generate_presentation_from_document(
    doc_text: str,
    slide_count: int = 5,
    language: str = "uz",
    with_speech: bool = True,
    mode: str = "general",
    api_key: Optional[str] = None,
) -> PresentationContent:
    """Foydalanuvchi yuklagan PDF yoki Word matni asosida slaydlar yaratadi."""
    key = api_key or config.GEMINI_API_KEY
    first_line = doc_text.splitlines()[0][:30] if doc_text else "Hujjat Tahlili"
    if not key:
        return generate_mock_presentation(first_line, slide_count=slide_count, language=language, with_speech=with_speech, mode=mode)

    client = genai.Client(api_key=key)
    prompt = build_document_prompt(doc_text, slide_count, language, with_speech=with_speech)

    candidate_models = [
        config.GEMINI_MODEL,
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-flash-latest",
    ]
    seen = set()
    models_to_try = [m for m in candidate_models if m and not (m in seen or seen.add(m))]

    for model_name in models_to_try:
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=PresentationContent,
                    temperature=0.7,
                ),
            )
            cleaned_json = _clean_json_string(response.text or "")
            presentation = PresentationContent.model_validate_json(cleaned_json)
            return _ensure_slide_count(presentation, slide_count, first_line, language, with_speech=with_speech)
        except Exception as e:
            logger.warning(f"generate_presentation_from_document {model_name} fallback: {e}")
            continue

    return generate_mock_presentation(first_line, slide_count=slide_count, language=language, with_speech=with_speech, mode=mode)


def generate_mock_presentation(
    topic: str,
    slide_count: int = 5,
    language: str = "uz",
    with_speech: bool = True,
    mode: str = "general",
) -> PresentationContent:
    """Offline yoki favqulodda holatlar uchun mavzuga 100% mos professional slaydlar to'plami."""
    short_t = topic if len(topic) < 40 else topic[:40] + "..."
    clean_t = re.sub(r"[^a-zA-Z0-9\s]", " ", topic).strip()
    safe_kw = " ".join(clean_t.split()[:4]) or "presentation topic"
    spk = lambda s: s if with_speech else None

    base_slides = [
        SlideContent(
            layout="title_slide",
            category_badge="AKADEMIK TAQDIMOT",
            title=short_t,
            subtitle=f"{short_t}: Nazariy asoslar, tizimli tahlil va amaliy istiqbollar",
            highlight_takeaway=f"{short_t} bo'yicha kompleks tahliliy taqdimot",
            image_keyword=f"{safe_kw} documentary historical realistic 4k",
            speaker_speech=spk(f"Assalomu alaykum hurmatli qatnashchilar! Bugungi taqdimotimiz {short_t} mavzusiga bag'ishlanadi."),
        ),
        SlideContent(
            layout="cards_grid",
            category_badge="ASOSIY YO'NALISHLAR",
            title=f"{short_t}: Muhim Asoslar va Tamoyillar",
            subtitle=f"{short_t} mavzusini tushunish va o'rganishda e'tibor qaratiladigan sohalar",
            cards=[
                CardItem(
                    title="Nazariy Asos",
                    description=f"{short_t} ning fundamental tushunchalari va ilmiy qoidalari majmuasi.",
                    badge="01",
                ),
                CardItem(
                    title="Tizimli Tahlil",
                    description=f"{short_t} bo'yicha to'plangan ma'lumotlarni mantiqiy tartibda o'rganish.",
                    badge="02",
                ),
                CardItem(
                    title="Amaliy Ahamiyat",
                    description=f"{short_t} ning zamonaviy jamiyat va soha rivojidagi hayotiy o'rni.",
                    badge="03",
                ),
            ],
            image_keyword=f"{safe_kw} research analysis conceptual",
            speaker_speech=spk(f"Ushbu slaydda {short_t} ning eng muhim uchta asosiy ustunini ko'rib chiqamiz."),
        ),
        SlideContent(
            layout="comparison",
            category_badge="QIYOSIY TAHLIL",
            title=f"{short_t}: Yondashuvlar Solishtiruvi",
            subtitle=f"{short_t} bo'yicha an'anaviy qarashlar hamda zamonaviy ilg'or uslublar",
            comparison_col1=ComparisonColumn(
                header="Klassik Qarashlar",
                badge="An'anaviy",
                points=[
                    f"{short_t} bo'yicha dastlabki nazariy tushunchalar",
                    "Cheklangan manbalar va an'anaviy uslub",
                    "Vaqt talab etuvchi tahlil jarayoni",
                ],
            ),
            comparison_col2=ComparisonColumn(
                header="Zamonaviy Tajriba",
                badge="Ilg'or",
                points=[
                    f"{short_t} ning yangi ilmiy kashfiyotlar bilan boyitilishi",
                    "Keng qamrovli raqamli va amaliy imkoniyatlar",
                    "Yuqori aniqlik va tizimli xulosalar",
                ],
            ),
            image_keyword=f"{safe_kw} comparison modern historic",
            speaker_speech=spk(f"{short_t} bo'yicha an'anaviy va zamonaviy yondashuvlarni solishtirish yangi imkoniyatlarni ko'rsatadi."),
        ),
        SlideContent(
            layout="timeline_steps",
            category_badge="BOSQICHLAR",
            title=f"{short_t}: Taraqqiyot Yo'li",
            subtitle=f"{short_t} ning shakllanishi va rivojlanish bosqichlari ketma-ketligi",
            steps=[
                CardItem(title="1. Dastlabki Shakllanish", description=f"{short_t} ning ildizlari va asosiy omillari.", badge="1-Bosqich"),
                CardItem(title="2. Rivojlanish Davri", description=f"{short_t} bo'yicha tizimli tajribalarning to'planishi.", badge="2-Bosqich"),
                CardItem(title="3. Zamonaviy Bosqich", description=f"{short_t} ning bugungi kundagi faol o'rganilishi.", badge="3-Bosqich"),
                CardItem(title="4. Kelajak Marralari", description=f"{short_t} yuzasidan yangi kutilayotgan natijalar.", badge="4-Bosqich"),
            ],
            image_keyword=f"{safe_kw} timeline progress architecture",
            speaker_speech=spk(f"{short_t} taraqqiyot yo'li bosqichma-bosqich takomillashib borganini ko'rishimiz mumkin."),
        ),
        SlideContent(
            layout="quote_highlight",
            category_badge="MUHIM FALSAFA",
            title=f"{short_t}: Bosh Ilmiy Fikr",
            subtitle=f"{short_t} mavzusining chuqur ma'nosi va strategik ahamiyati",
            quote_text=f"\"{short_t} — bu soha rivojining poydevori va yangi marralar kalitidir.\"",
            quote_author=f"{short_t} Ekspert Xulosasi",
            highlight_takeaway=f"{short_t} bo'yicha har bir yangi bilim kelajakdagi muvaffaqiyat garovidir.",
            image_keyword=f"{safe_kw} knowledge philosophy insight",
            speaker_speech=spk(f"Ushbu xulosa {short_t} ning butun mohiyatini ifodalaydi."),
        ),
        SlideContent(
            layout="checklist_points",
            category_badge="TAVSIYALAR",
            title=f"{short_t}: Asosiy Qoidalar",
            subtitle=f"{short_t} bo'yicha muvaffaqiyatga erishishning muhim talablari",
            checklist=[
                f"{short_t} bo'yicha to'plangan ilmiy manbalarni tahlil qilish",
                f"{short_t} qonuniyatlariga doimiy ravishda amal qilish",
                f"{short_t} sohasidagi xalqaro tajribalarni o'rganish",
                f"{short_t} ning yangi amaliy natijalarini joriy etish",
            ],
            image_keyword=f"{safe_kw} guidelines checklist advice",
            speaker_speech=spk(f"Mana shu to'rtta asosiy qoidaga amal qilish yuqori natijalarni ta'minlaydi."),
        ),
        SlideContent(
            layout="conclusion",
            category_badge="XULOSA",
            title=f"{short_t}: Yakuniy Xulosalar",
            subtitle=f"{short_t} bo'yicha umumiy xulosalar va kelajak istiqbollari",
            highlight_takeaway=f"{short_t} bo'yicha to'g'ri tushuncha va izlanish doimiy o'sish garovidir.",
            cards=[
                CardItem(title="Ilmiy Xulosa", description=f"{short_t} mavzusi dolzarb va chuqur ahamiyatga ega ekanligi isbotlandi.", badge="Xulosa"),
                CardItem(title="Savol-Javob", description="E'tiboringiz uchun rahmat, savollaringizni berishingiz mumkin.", badge="Yakun"),
            ],
            image_keyword=f"{safe_kw} conclusion success future",
            speaker_speech=spk(f"E'tiboringiz uchun katta rahmat! {short_t} bo'yicha savollaringiz bo'lsa, javob berishga tayyorman."),
        ),
    ]

    return _ensure_slide_count(
        PresentationContent(topic=topic, language=language, slides=base_slides),
        target_count=slide_count,
        topic=topic,
        language=language,
        with_speech=with_speech,
    )



async def translate_presentation_content(
    content: PresentationContent,
    target_lang: str,
    api_key: Optional[str] = None,
) -> PresentationContent:
    """Mavjud taqdimot kontentini boshqa tilga (uz, ru, en) 100% tartibini saqlagan holda tarjima qiladi."""
    target_names = {
        "uz": "o'zbek adabiy tili (lotin alifbosida)",
        "ru": "грамотный русский язык",
        "en": "professional English",
    }
    lang_name = target_names.get(target_lang, "o'zbek tili")
    
    key = api_key or config.GEMINI_API_KEY
    if not key:
        return content

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

    current_json = content.model_dump_json(indent=2)
    prompt = f"""Siz professional taqdimotlar tarjimoni va muharririsiz.
Quyida berilgan taqdimot JSON ma'lumotlarini {lang_name}ga to'liq, sifatli va adabiy tarzda tarjima qiling.

MUHIM SHARTLAR:
1. JSON sxemasi va tuzilishi to'liq saqlansin. Slaydlar soni va ularning 'layout' qiymatlari aslo o'zgarmasin.
2. Barcha sarlavhalar, subtitrlar, kartochka matnlari ('title', 'description', 'badge'), statistika yozuvlari ('label', 'description'), bosqichlar ('title', 'description'), iqtiboslar, xulosalar va agar mavjud bo'lsa spiker nutqi ('speaker_speech') {lang_name}ga tarjima qilinsin.
3. 'language' maydoniga "{target_lang}" yozilsin.
4. Javobni FAQAT va FAQAT to'g'ri PresentationContent JSON formatida qaytaring, boshqa hech qanday izoh qo'shmang.

ASL TAQDIMOT KONTENTI:
{current_json}
"""

    for model_name in models_to_try:
        try:
            logger.info(f"Taqdimot {target_lang} tiliga tarjima qilinmoqda ({model_name})...")
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=PresentationContent,
                    temperature=0.3,
                ),
            )
            raw = response.text or ""
            cleaned = _clean_json_string(raw)
            translated = PresentationContent.model_validate_json(cleaned)
            translated.language = target_lang
            return translated
        except Exception as e:
            logger.warning(f"Tarjimada {model_name} da xatolik: {e}")
            continue

    logger.error("Tarjima amalga oshmadi, asl kontent qaytarilmoqda.")
    return content


async def tweak_single_slide(
    slide: SlideContent,
    instruction: str,
    language: str = "uz",
    api_key: Optional[str] = None,
) -> SlideContent:
    """Muayyan bitta slaydni foydalanuvchining ko'rsatmasi asosida AI yordamida tahrirlaydi."""
    key = api_key or config.GEMINI_API_KEY
    if not key:
        return slide

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

    current_slide_json = slide.model_dump_json(indent=2)
    prompt = f"""Siz professional taqdimotlar dizayneri va muharririsiz.
Mavjud slayd ma'lumotlari (JSON):
{current_slide_json}

FOYDALANUVCHINING TAHRIR BO'YICHA KO'RSATMASI:
"{instruction}"

TIL: {language}

VAZIFA:
Foydalanuvchi ko'rsatmasiga qat'iy amal qilgan holda ushbu slaydni takomillashtiring va qayta ishlang.
Slaydning mavjud layout turini saqlang yoki agar ko'rsatmada talab qilingan bo'lsa moslashtiring.
Agar foydalanuvchi matnni qisqartirish, fakt qo'shish, sarlavhani o'zgartirish yoki boshqa talab qo'ygan bo'lsa, uni to'liq bajaring.
Javobni FAQAT SlideContent JSON formatida qaytaring, ortiqcha matnsiz.
"""

    for model_name in models_to_try:
        try:
            logger.info(f"Slayd tahrirlanmoqda ({model_name}): {instruction[:40]}...")
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SlideContent,
                    temperature=0.5,
                ),
            )
            raw = response.text or ""
            cleaned = _clean_json_string(raw)
            updated_slide = SlideContent.model_validate_json(cleaned)
            return updated_slide
        except Exception as e:
            logger.warning(f"Slaydni tahrirlashda {model_name} da xatolik: {e}")
            continue

    return slide


class DefenseQuestions(BaseModel):
    questions: List[str] = Field(description="Komissiya a'zosi tomonidan beriladigan 3 ta jiddiy va dolzarb savol")


class DefenseEvaluation(BaseModel):
    score: int = Field(description="Javobga qo'yilgan baho: 1 dan 10 gacha butun son")
    feedback: str = Field(description="Javobning qisqa va aniq tahlili: kuchli tomonlari va kamchiliklari (2-3 jumla)")
    ideal_response: str = Field(description="Ushbu savolga berilishi mumkin bo'lgan professional va mukammal javob namunasi (2-3 jumla)")


async def generate_defense_questions(
    topic: str,
    slides_summary: str = "",
    language: str = "uz",
    api_key: Optional[str] = None,
) -> List[str]:
    """Taqdimot mavzusi va slaydlari asosida komissiya tomonidan beriladigan 3 ta jiddiy savol tuzadi."""
    key = api_key or config.GEMINI_API_KEY
    if not key:
        return [
            f"Ushbu «{topic}» mavzusida taklif qilayotgan asosiy yechimingizning mavjud muqobillardan eng katta farqi va ustunligi nimada?",
            f"Loyihani yoki ushbu g'oyani amaliyotga tatbiq etishda qanday asosiy xavflar (risklar) mavjud va ularni qanday bartaraf etasiz?",
            f"Ushbu tadqiqot yoki taqdimot natijalarining 1-2 yil ichidagi iqtisodiy/amaliy samaradorligini qanday baholaysiz?",
        ]

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

    prompt = f"""Siz talabchan va professional ilmiy/biznes komissiya raisisiz (Hay'at a'zosi / Examiner).
Ma'ruzachi «{topic}» mavzusida taqdimot himoya qilmoqda.
Taqdimot mazmuni va qisqacha slaydlari:
{slides_summary[:2500]}

VAZIFA:
Ma'ruzachining bilimini, tayyorgarligini va mavzuni qanchalik chuqur tushunganini sinash uchun eng dolzarb, kutilmagan va chuqur 3 ta savol tuzing:
1. Nazariy asoslar yoki muammoning dolzarbligi bo'yicha chuqur savol.
2. Amaliy qo'llanilishi, xavflar yoki yuzaga kelishi mumkin bo'lgan qiyinchiliklar bo'yicha savol.
3. Raqobatchilar, iqtisodiy/ijtimoiy samara yoki kelajak istiqbollari bo'yicha tahliliy savol.

TIL: {language} (o'zbek, rus yoki ingliz tili).
Savollar professional, aniq va ma'ruzachini fikrlashga undaydigan bo'lsin.
Javobni FAQAT DefenseQuestions JSON formatida qaytaring."""

    for model_name in models_to_try:
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=DefenseQuestions,
                    temperature=0.7,
                ),
            )
            raw = response.text or ""
            cleaned = _clean_json_string(raw)
            parsed = DefenseQuestions.model_validate_json(cleaned)
            if parsed.questions and len(parsed.questions) >= 3:
                return parsed.questions[:3]
        except Exception as e:
            logger.warning(f"generate_defense_questions {model_name} da xatolik: {e}")
            continue

    return [
        f"«{topic}» mavzusida taklif qilayotgan asosiy yondashuvingizning mavjud amaliyotdan asosiy farqi va ustunligi nimada?",
        f"Ushbu mavzuni yoki yechimni hayotga tatbiq etishda qanday jiddiy to'siqlar yuzaga kelishi mumkin va ularni qanday yengasiz?",
        f"Keltirilgan faktlar va xulosalarning ishonchliligi hamda kelajakdagi rivojlanish istiqbollarini qanday asoslaysiz?",
    ]


async def evaluate_defense_answer(
    question: str,
    user_answer: str,
    topic: str,
    language: str = "uz",
    api_key: Optional[str] = None,
) -> DefenseEvaluation:
    """Foydalanuvchining komissiya savoliga bergan javobini xolisona baholaydi va mukammal javob namunasini beradi."""
    key = api_key or config.GEMINI_API_KEY
    fallback = DefenseEvaluation(
        score=7,
        feedback="Javobingiz umumiy ma'noda to'g'ri, biroq fikringizni aniq faktlar va aniq misollar bilan kuchaytirishingiz lozim.",
        ideal_response="Mavzuning amaliy ahamiyatini ko'rsatib, raqamlar va aniq yechimlar asosida qisqa va ishonchli xulosa berish maqsadga muvofiq.",
    )
    if not key:
        return fallback

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

    prompt = f"""Siz taqdimot/diplom ishi himoyasini qabul qilayotgan talabchan, adolatli va professional komissiya raisisiz.
Mavzu: «{topic}»
Komissiya bergan savol:
«{question}»

Ma'ruzachining bergan javobi:
«{user_answer}»

VAZIFA:
Ma'ruzachining javobini xolisona va chuqur baholang:
1. score: 1 dan 10 gacha butun son qo'ying (1-juda sust/noto'g'ri, 5-o'rtacha, 8-yaxshi, 10-a'lo va mukammal).
2. feedback: Javobning qisqa va samimiy tahlili (2-3 jumla). Nima to'g'ri aytildi, nima yetishmadi yoki qaysi joyi zaif.
3. ideal_response: Komissiyani qoyil qoldiradigan, ishonchli, professional va ideal javob namunasi (2-3 jumla).

TIL: {language} (o'zbek, rus yoki ingliz tili).
Javobni FAQAT DefenseEvaluation JSON formatida qaytaring."""

    for model_name in models_to_try:
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=DefenseEvaluation,
                    temperature=0.4,
                ),
            )
            raw = response.text or ""
            cleaned = _clean_json_string(raw)
            return DefenseEvaluation.model_validate_json(cleaned)
        except Exception as e:
            logger.warning(f"evaluate_defense_answer {model_name} da xatolik: {e}")
            continue

    return fallback


# ------------------ MULTIMODAL (VISION & VOICE) & QUIZ DUEL ------------------
class VisionExtractionResult(BaseModel):
    title: str = Field(description="Rasmdan/konspektdan aniqlangan asosiy mavzu (3-7 so'z)")
    summary: str = Field(description="Rasmdagi matnning 2-3 jumlalik ixcham mazmuni")
    key_points: List[str] = Field(description="Rasmdagi asosiy 3-5 ta muhim nuqta yoki tushuncha")
    suggested_slides: int = Field(default=5, description="Tavsiya etiladigan slaydlar soni (3, 5, 7 yoki 10)")
    raw_text: str = Field(description="Rasmdagi aniqlangan to'liq matn (OCR)")


class VoiceCommandResult(BaseModel):
    transcript: str = Field(description="Ovozli xabardagi aytilgan gaplarning to'liq matni")
    topic: str = Field(description="Aniqlangan asosiy mavzu nomi")
    action: Literal["slide", "video", "essay", "article", "unknown"] = Field(default="slide", description="Foydalanuvchi nima yaratmoqchi: 'slide', 'video', 'essay', 'article'")
    slide_count: int = Field(default=5, description="Slaydlar soni (agar aytilgan bo'lsa, aks holda 5)")
    language: str = Field(default="uz", description="Til kodi: 'uz', 'ru', 'en'")


class QuizQuestion(BaseModel):
    question: str = Field(description="Qiziqarli va intellektual test savoli")
    options: List[str] = Field(description="Aynan 4 ta javob varianti (A, B, C, D)")
    correct_index: int = Field(description="To'g'ri javob indeksi (0, 1, 2, yoki 3)")
    explanation: str = Field(description="Nima uchun bu javob to'g'riligi haqida 1 jumlalik qiziqarli izoh")


class QuizDuelPack(BaseModel):
    category: str = Field(description="Kategoriya nomi")
    questions: List[QuizQuestion] = Field(description="Aynan 5 ta qiziqarli test savoli")


async def analyze_image_and_extract_topic(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    api_key: Optional[str] = None,
) -> VisionExtractionResult:
    """
    Rasm (daftar konspekti, kitob sahifasi, doska, hujjat) dagi matnni o'qib,
    asosiy mavzu va slaydlar uchun reja tuzadi (Gemini Vision OCR).
    """
    key = api_key or config.GEMINI_API_KEY
    fallback = VisionExtractionResult(
        title="Rasmdan o'qilgan mavzu",
        summary="Ushbu rasmda konspekt yoki o'quv materiallari tasvirlangan.",
        key_points=["Asosiy tushunchalar", "Mavzu tahlili", "Xulosa"],
        suggested_slides=5,
        raw_text="",
    )
    if not key:
        return fallback

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

    prompt = """Siz eng ilg'or AI Vision va OCR mutaxassisisiz. Sizga foydalanuvchi daftar konspekti, kitob sahifasi, doska yoki hujjat rasmini yubordi.

VAZIFA:
1. Rasmdagi barcha qo'lyozma yoki bosma matnlarni to'liq, aniq o'qing (OCR).
2. Ushbu matn qaysi ilmiy, amaliy yoki ta'limiy MAVZU haqida ekanligini aniqlang (title).
3. Matnning 2-3 jumlalik qisqa va mazmunli xulosasini tuzing (summary).
4. Slaydlar yoki mustaqil ish uchun eng muhim 3-5 ta asosiy fakt yoki punktlarni ajrating (key_points).
5. Mazmun hajmiga qarab tavsiya etiladigan slaydlar sonini (3, 5, 7 yoki 10) tanlang.

JAVOBNI FAQAT VisionExtractionResult JSON formatida qaytaring."""

    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    for model_name in models_to_try:
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=[prompt, image_part],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=VisionExtractionResult,
                    temperature=0.2,
                ),
            )
            raw = response.text or ""
            cleaned = _clean_json_string(raw)
            return VisionExtractionResult.model_validate_json(cleaned)
        except Exception as e:
            logger.warning(f"analyze_image_and_extract_topic {model_name} da xatolik: {e}")
            continue

    return fallback


async def analyze_voice_and_extract_command(
    audio_bytes: bytes,
    mime_type: str = "audio/ogg",
    api_key: Optional[str] = None,
) -> VoiceCommandResult:
    """
    Ovozli xabarni tahlil qilib, foydalanuvchi qaysi mavzuda, qanday formatda va
    necha slaydli material so'raganini aniqlaydi.
    """
    key = api_key or config.GEMINI_API_KEY
    fallback = VoiceCommandResult(
        transcript="Ovozli xabar qabul qilindi",
        topic="Taqdimot mavzusi",
        action="slide",
        slide_count=5,
        language="uz",
    )
    if not key:
        return fallback

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

    prompt = """Siz sun'iy intellekt audio assistentisiz. Foydalanuvchi Telegram orqali ovozli xabar (voice note) yubordi.

VAZIFA:
1. transcript: Ovozda aytilgan barcha so'zlarni to'liq, imlo qoidalariga mos holda matnga aylantiring (Speech-to-Text).
2. topic: Foydalanuvchi qaysi aniq mavzuda slayd, video yoki mustaqil ish so'rayotganini aniqlang (masalan: "Amir Temur saltanati", "Sun'iy intellekt tibbiyotda").
3. action: Foydalanuvchi nima yaratmoqchi?
   - 'slide' (slayd, taqdimot, prezentatsiya so'zlarini aytsa yoki shunchaki mavzu aytsa)
   - 'video' (video, rolik, film so'zlarini aytsa)
   - 'essay' (mustaqil ish, referat, konspekt so'zlarini aytsa)
   - 'article' (maqola, tezis so'zlarini aytsa)
4. slide_count: Agar ovozda necha slayd kerakligi aytilgan bo'lsa (masalan "7 ta slayd", "10 ta slayd"), shu raqamni yozing. Agar aytilmagan bo'lsa, standart 5 deb oling.
5. language: Ovoz qaysi tilda ekanligi ('uz', 'ru', 'en').

JAVOBNI FAQAT VoiceCommandResult JSON formatida qaytaring."""

    audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)

    for model_name in models_to_try:
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=[prompt, audio_part],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=VoiceCommandResult,
                    temperature=0.2,
                ),
            )
            raw = response.text or ""
            cleaned = _clean_json_string(raw)
            return VoiceCommandResult.model_validate_json(cleaned)
        except Exception as e:
            logger.warning(f"analyze_voice_and_extract_command {model_name} da xatolik: {e}")
            continue

    return fallback


async def generate_quiz_duel_questions(
    category: str = "aralash",
    question_count: int = 5,
    api_key: Optional[str] = None,
) -> QuizDuelPack:
    """
    Do'stlar bellashuvi yoki AI bilan duel uchun qiziqarli, qiyinligi o'rtacha bo'lgan
    5 ta intellektual test savollarini tuzadi.
    """
    key = api_key or config.GEMINI_API_KEY
    fallback = QuizDuelPack(
        category=category,
        questions=[
            QuizQuestion(
                question="O'zbekiston Respublikasi Konstitutsiyasi qachon qabul qilingan?",
                options=["1991-yil 1-sentyabr", "1992-yil 8-dekabr", "1993-yil 9-may", "1990-yil 20-iyun"],
                correct_index=1,
                explanation="O'zbekiston Konstitutsiyasi 1992-yil 8-dekabrda qabul qilingan."
            ),
            QuizQuestion(
                question="Dunyo bo'yicha eng mashhur AI tili bo'lgan Python qachon yaratilgan?",
                options=["1985-yil", "1991-yil", "1998-yil", "2005-yil"],
                correct_index=1,
                explanation="Gvido van Rossum Python tilini 1991-yilda ommaga taqdim etgan."
            ),
            QuizQuestion(
                question="Quyosh tizimidagi eng katta sayyora qaysi?",
                options=["Mars", "Saturn", "Yupiter", "Neptun"],
                correct_index=2,
                explanation="Yupiter Quyosh tizimidagi eng bahaybat gigant sayyoradir."
            ),
            QuizQuestion(
                question="Amir Temurning davlat shiori qanday bo'lgan?",
                options=["Kuch - adolatdadir", "Bilim - eng katta kuch", "G'alaba yoki o'lim", "Tinchlik - taraqqiyot poydevori"],
                correct_index=0,
                explanation="Sohibqiron Amir Temurning davlat shiori «Rosti-rasti» (Kuch - adolatdadir) bo'lgan."
            ),
            QuizQuestion(
                question="Kompyuter xotirasidagi 1 Gigabayt (GB) necha Megabayt (MB) ga teng?",
                options=["1000 MB", "1024 MB", "512 MB", "2048 MB"],
                correct_index=1,
                explanation="Ikkilik sanoq tizimida 1 GB aynan 1024 MB ni tashkil qiladi."
            ),
        ]
    )
    if not key:
        return fallback

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

    prompt = f"""Siz professional intellektual viktorina ("Zakovat", "Millioner") boshlovchisisiz.
KATEGORIYA: «{category}»
SAVOLLAR SONI: Aynan {question_count} ta savol.

QAT'IY TALABLAR:
1. Savollar zerikarli bo'lmasin! Haqiqiy intellekt, qiziqarli faktlar va mantiqqa asoslansin.
2. Har bir savolda aynan 4 ta variant (options) bo'lsin.
3. correct_index: 0, 1, 2 yoki 3 bo'lsin (to'g'ri variant indeksi).
4. explanation: Nega aynan shu javob to'g'riligi haqida 1 jumlalik qiziqarli izoh yozing.
5. Savollar va variantlar o'zbek tilida (lotin alifbosida) bo'lsin.

JAVOBNI FAQAT QuizDuelPack JSON formatida qaytaring."""

    for model_name in models_to_try:
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=QuizDuelPack,
                    temperature=0.7,
                ),
            )
            raw = response.text or ""
            cleaned = _clean_json_string(raw)
            pack = QuizDuelPack.model_validate_json(cleaned)
            if pack.questions and len(pack.questions) == question_count:
                return pack
        except Exception as e:
            logger.warning(f"generate_quiz_duel_questions {model_name} da xatolik: {e}")
            continue

    return fallback

