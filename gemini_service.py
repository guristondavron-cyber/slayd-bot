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
        "comparison",
        "timeline_steps",
        "conclusion",
    ] = Field(description="Slaydning vizual joylashuv turi")
    category_badge: str = Field(description="Slayd tepasidagi kichik kategoriya tegi (masalan: 'KIRISH', 'MUAMMO', 'YECHIM', 'STATISTIKA', 'BOSQICHLAR', 'XULOSA')")
    title: str = Field(description="Slaydning asosiy sarlavhasi (kuchli, jozibali, 4-8 so'z)")
    subtitle: Optional[str] = Field(default=None, description="Sarlavhani to'ldiruvchi qisqa izoh yoki savol (10-15 so'z)")
    
    # cards_grid uchun (3 yoki 4 ta karta)
    cards: Optional[List[CardItem]] = Field(default=None, description="cards_grid yoki umumiy punktlar uchun kartalar")
    
    # stats_metrics uchun (3 yoki 4 ta statistika)
    stats: Optional[List[StatItem]] = Field(default=None, description="stats_metrics slaydi uchun 3-4 ta muhim raqamlar")
    
    # comparison uchun
    comparison_col1: Optional[ComparisonColumn] = Field(default=None, description="Solishtirishning 1-ustuni")
    comparison_col2: Optional[ComparisonColumn] = Field(default=None, description="Solishtirishning 2-ustuni")
    
    # timeline_steps uchun
    steps: Optional[List[CardItem]] = Field(default=None, description="Ketma-ket 3-4 ta bosqich yoki harakatlar rejasi")
    
    # conclusion / call to action
    highlight_takeaway: Optional[str] = Field(default=None, description="Asosiy chaqiriq, yakuniy xulosa yoki iqtibos")
    speaker_notes: Optional[str] = Field(default=None, description="Spiker uchun qisqa maslahat")


class PresentationContent(BaseModel):
    topic: str = Field(description="Taqdimotning umumiy mavzusi")
    language: str = Field(default="uz", description="Taqdimot tili")
    slides: List[SlideContent] = Field(description="Belgilangan miqdordagi slaydlar ketma-ketligi")


def build_system_prompt(topic: str, slide_count: int, language: str = "uz") -> str:
    lang_instruction = {
        "uz": "Barcha matnlar, sarlavhalar va tushuntirishlar o'zbek adabiy tilida (lotin alifbosida), juda chiroyli va professional uslubda bo'lsin.",
        "ru": "Все тексты, заголовки и описания должны быть на грамотном русском языке.",
        "en": "All texts, headings, and explanations must be in clear, professional English.",
    }.get(language, "O'zbek tilida yozing.")

    return f"""Siz dunyo darajasidagi professional taqdimotlar (Executive Pitch Decks & Keynotes) dizayneri va biznes konsultantisiz.
Sizning vazifangiz quyidagi mavzu bo'yicha {slide_count} ta slayddan iborat to'liq va mukammal taqdimot kontentini tayyorlash:
MAVZU: "{topic}"

TIL TALABI:
{lang_instruction}

MUHIM QOIDALAR:
1. Slaydlar shunchaki quruq matn bo'lmasin. Har bir slayd ma'lum bir vizual strukturaga mos bo'lsin.
2. Har bir slaydga mos layout tanlang:
   - 1-slayd DOIMO: "title_slide" (Mavzuning kuchli sarlavhasi, kategoriya tegi va qisqa sub-sarlavha)
   - 2-slayd: Ko'pincha "cards_grid" (Muammo yoki asosiy yo'nalishlar - 3 ta karta)
   - O'rta slaydlar: "stats_metrics" (muhim raqamlar, prognozlar), "comparison" (eski vs yangi, xavflar vs yechimlar), yoki "timeline_steps" (amalga oshirish bosqichlari)
   - Oxirgi slayd DOIMO: "conclusion" (Yakuniy natija, asosiy xulosa va harakatga chaqiriq)
3. Matnlar ixcham, lo'nda va vizual idrok qilishga oson bo'lsin. Uzun paragraflar yozmang!
4. StatItem raqamlari qisqa va ta'sirchan bo'lsin (masalan: "85%", "+140%", "$2.4M", "24/7", "10x").
5. Jami roppa-rosa {slide_count} ta slayd yarating.
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


async def generate_presentation_with_gemini(
    topic: str,
    slide_count: int = 5,
    language: str = "uz",
    api_key: Optional[str] = None,
) -> PresentationContent:
    """Gemini API orqali taqdimot mazmunini generatsiya qiladi."""
    key = api_key or config.GEMINI_API_KEY
    if not key:
        raise ValueError(
            "GEMINI_API_KEY topilmadi! Iltimos, .env fayliga GEMINI_API_KEY kalitini kiriting yoki botga yuboring."
        )

    client = genai.Client(api_key=key)
    prompt = build_system_prompt(topic, slide_count, language)

    # Calling Gemini with structured output
    try:
        response = await client.aio.models.generate_content(
            model=config.GEMINI_MODEL,
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
        return presentation

    except Exception as e:
        logger.warning(f"models.generate_content failed: {e}. Trying fallback call...")
        response = await client.aio.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt + "\n\nQAT'IY TALAB: Javobni faqat va faqat to'g'ri JSON formatida qaytaring, hech qanday qo'shimcha matn yozmang.",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.7,
            ),
        )
        cleaned_json = _clean_json_string(response.text or "{}")
        return PresentationContent.model_validate_json(cleaned_json)


def build_document_prompt(doc_text: str, slide_count: int, language: str = "uz") -> str:
    lang_instruction = {
        "uz": "Barcha matnlar va sarlavhalar o'zbek adabiy tilida (lotin alifbosida) bo'lsin.",
        "ru": "Все тексты и заголовки должны быть на качественном русском языке.",
        "en": "All texts and headings must be in clear, professional English.",
    }.get(language, "O'zbek tilida yozing.")

    return f"""Siz professional taqdimotlar tahlilchisisiz.
Quyida berilgan hujjat/maqola matnidan eng muhim asosiy g'oyalar, xulosalar, faktlar va statistikani ajratib olib, 
aynan shu manba asosida {slide_count} ta slayddan iborat mukammal taqdimot kontentini tayyorlang.

MANBA HUJJAT MATNI:
\"\"\"
{doc_text[:12000]}
\"\"\"

TIL TALABI:
{lang_instruction}

MUHIM QOIDALAR:
1. 1-slayd: Hujjatning asosiy mavzusiga bag'ishlangan "title_slide".
2. O'rta slaydlar: Hujjatdagi muammolar, tahlillar, raqamlar ("stats_metrics"), solishtirishlar ("comparison") va bosqichlar ("timeline_steps").
3. Oxirgi slayd: Hujjat bo'yicha yakuniy xulosalar ("conclusion").
4. Jami roppa-rosa {slide_count} ta slayd tuzing.
"""


async def generate_presentation_from_document(
    doc_text: str,
    slide_count: int = 5,
    language: str = "uz",
    api_key: Optional[str] = None,
) -> PresentationContent:
    """Foydalanuvchi yuklagan PDF yoki Word matni asosida slaydlar yaratadi."""
    key = api_key or config.GEMINI_API_KEY
    if not key:
        return generate_mock_presentation("Hujjat Tahlili", slide_count=slide_count)

    client = genai.Client(api_key=key)
    prompt = build_document_prompt(doc_text, slide_count, language)

    try:
        response = await client.aio.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PresentationContent,
                temperature=0.7,
            ),
        )
        cleaned_json = _clean_json_string(response.text or "")
        return PresentationContent.model_validate_json(cleaned_json)
    except Exception as e:
        logger.warning(f"generate_presentation_from_document fallback: {e}")
        first_line = doc_text.splitlines()[0][:30] if doc_text else "Hujjat Tahlili"
        return generate_mock_presentation(first_line, slide_count=slide_count)



def generate_mock_presentation(topic: str, slide_count: int = 5) -> PresentationContent:
    """
    Offline sinov va API key yo'q holatlar uchun yuqori sifatli namunaviy slaydlar.
    """
    slides = [
        SlideContent(
            layout="title_slide",
            category_badge="STRATEGIYA VA RIVOJLANISH",
            title=topic if len(topic) < 40 else topic[:40] + "...",
            subtitle="Zamonaviy yondashuvlar, amaliy yechimlar va kelajak istiqbollari tahlili",
            highlight_takeaway="Yangi davr texnologiyalari va strategik o'sish sari qadam",
            speaker_notes="Kirish so'zi bilan tinglovchilarni mavzuga jalb qilish.",
        ),
        SlideContent(
            layout="cards_grid",
            category_badge="ASOSIY YO'NALISHLAR",
            title="Mavzuning Eng Muhim Asoslari",
            subtitle="Muvaffaqiyatga erishish uchun e'tibor qaratilishi zarur bo'lgan ustuvor sohalar",
            cards=[
                CardItem(
                    title="Avtomatlashtirish",
                    description="Kundalik takroriy jarayonlarni avtomatlashtirib, samaradorlikni 3 barobarga oshirish.",
                    badge="01",
                ),
                CardItem(
                    title="Sun'iy Intellekt",
                    description="Ma'lumotlarni tahlil qilish va qaror qabul qilishda eng yangi neyrotarmoqlardan foydalanish.",
                    badge="02",
                ),
                CardItem(
                    title="Masshtablash",
                    description="Yechimni xalqaro standartlarga moslashtirib, auditoriya qamrovini kengaytirish.",
                    badge="03",
                ),
            ],
            speaker_notes="Har bir ustuvor yo'nalish bo'yicha qisqacha misollar keltiring.",
        ),
        SlideContent(
            layout="stats_metrics",
            category_badge="STATISTIKA VA RAQAMLAR",
            title="Bozor Ko'rsatkichlari va Dinamika",
            subtitle="Haqiqiy raqamlar orqali o'sish va imkoniyatlar ko'lamini baholash",
            stats=[
                StatItem(
                    number="85%",
                    label="Samaradorlik o'sishi",
                    description="Yangi uslub joriy etilgandan keyingi ko'rsatkich",
                ),
                StatItem(
                    number="3.4X",
                    label="Tezlik ko'rsatkichi",
                    description="Topshiriqlarni bajarish vaqti qisqarishi",
                ),
                StatItem(
                    number="24/7",
                    label="Uzluksiz faoliyat",
                    description="Tizimning to'xtovsiz xizmat ko'rsatish darajasi",
                ),
                StatItem(
                    number="99.9%",
                    label="Aniqlik va ishonchlilik",
                    description="Xatoliklar ehtimolini minimal darajaga tushirish",
                ),
            ],
            speaker_notes="Raqamlarning manbasi va amaliy ahamiyatiga urg'u bering.",
        ),
        SlideContent(
            layout="comparison",
            category_badge="SOLISHTIRUV",
            title="An'anaviy vs Yangi Yondashuv",
            subtitle="Eski usullarning cheklovlari va innovatsion yechimning ustunliklari",
            comparison_col1=ComparisonColumn(
                header="An'anaviy Usul",
                badge="Eski / Cheklangan",
                points=[
                    "Qo'lda bajariladigan ko'p vaqt talab qiluvchi ishlar",
                    "Inson omili sababli tez-tez uchraydigan xatolar",
                    "Masshtablashning cheklanganligi va yuqori xarajat",
                    "Sekin moslashuvchanlik va qotib qolgan tizim",
                ],
            ),
            comparison_col2=ComparisonColumn(
                header="Zamonaviy Yechim",
                badge="Innovatsion / Tezkor",
                points=[
                    "Tezkor avtomatlashgan jarayonlar va AI ko'magi",
                    "Yuqori aniqlik va xatoliklarning kamayishi",
                    "Tez va oson masshtablash imkoniyati",
                    "Har qanday o'zgarishlarga tezkor moslashuv",
                ],
            ),
            speaker_notes="Tinglovchilarga nima sababdan yangi yondashuv zarurligini tushuntiring.",
        ),
        SlideContent(
            layout="timeline_steps",
            category_badge="HARKATLAR REJASI",
            title="Muvaffaqiyatga Yetaklovchi Bosqichlar",
            subtitle="Rejadan natijagacha bo'lgan aniq va tizimli qadamlar",
            steps=[
                CardItem(
                    title="Audit va Tahlil",
                    description="Mavjud holatni o'rganish va asosiy muammolarni aniqlash.",
                    badge="1-Bosqich",
                ),
                CardItem(
                    title="Strategiya Ishlab Chiqish",
                    description="Maqsadli yo'l xaritasini va texnik talablarni belgilash.",
                    badge="2-Bosqich",
                ),
                CardItem(
                    title="Sinov va Joriy Qilish",
                    description="Pilot loyihani ishga tushirish va dastlabki natijalarni olish.",
                    badge="3-Bosqich",
                ),
                CardItem(
                    title="To'liq Masshtablash",
                    description="Barcha bo'g'inlarda yangi tizimni to'liq ishga tushirish.",
                    badge="4-Bosqich",
                ),
            ],
            speaker_notes="Har bir bosqichning muddatlari haqida ma'lumot bering.",
        ),
        SlideContent(
            layout="conclusion",
            category_badge="XULOSA VA KELAJAK",
            title="Yangi Cho'qqilar Sari Dadil Qadam",
            subtitle="Innovatsiyalarni bugundan boshlab joriy qilish — ertangi kun yetakchiligi garovi",
            highlight_takeaway="\"Eng yaxshi bashorat — bu kelajakni o'z qo'llaringiz bilan yaratishdir.\"",
            cards=[
                CardItem(
                    title="Katta imkoniyatlar",
                    description="Bugun boshlangan harakat ertaga yetakchilikni ta'minlaydi.",
                    badge="Natija",
                ),
                CardItem(
                    title="Hamkorlikka tayyormiz",
                    description="Savollar va takliflar uchun biz bilan bog'laning.",
                    badge="Aloqa",
                ),
            ],
            speaker_notes="Yakuniy taassurot qoldirish va savol-javobga o'tish.",
        ),
    ]

    return PresentationContent(
        topic=topic,
        language="uz",
        slides=slides[:slide_count],
    )
