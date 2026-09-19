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
            "TAQDIMOT YO'NALISHI: BIZNES, STARTAP VA INVESTOR PITCH DECK.\n"
            "- Taqdimot strukturasi: Bozor muammosi (Pain Point) -> Innovatsion yechim (Solution) -> Bozor hajmi (TAM/SAM/SOM) -> Biznes va monetizatsiya modeli -> Raqobatchilar va ustunliklar -> Rivojlanish xaritasi (Roadmap) -> Jamoa va investitsiya talabi (The Ask).\n"
            "- Kuchli iqtisodiy, moliyaviy va strategik atamalar, o'sish ko'rsatkichlaridan foydalaning."
        ),
        "analytics": (
            "TAQDIMOT YO'NALISHI: TAHLILIY HISOBOT VA STATISTIKA.\n"
            "- Taqdimot strukturasi: Asosiy strategik KPIlar -> O'sish dinamikasi va tahliliy trendlar -> Qiyosiy ko'rsatkichlar -> Xavf-xatarlar (Risk Management) -> Tahliliy prognoz va operatsion qarorlar.\n"
            "- Aniq foizlar, nisbatlar, jadvallar va chuqur tahliliy faktlarga asoslaning."
        ),
        "general": (
            "TAQDIMOT YO'NALISHI: UMUMIY VA IJODIY EXECUTIVE TAQDIMOT.\n"
            "- Mavzuning eng qiziqarli, zamonaviy va ta'sirchan jihatlarini ochib bering."
        ),
    }.get(mode, "Executive taqdimot tayyorlang.")

    return f"""Siz jahon miqyosidagi yetakchi taqdimot dizayneri (Canva/McKinsey/Apple darajasidagi) va yuqori darajadagi strategik spikersiz.
Siz yaratgan taqdimotlar xuddi professional inson dizayneri tomonidan soatlab ijodiy o'ylab topilgandek, jonli, ta'sirchan, zamonaviy va chuqur mantiqqa ega bo'lishi shart.
Sun'iy intellekt qoliplari (quruq, shablon, robotga o'xshash jumlalar) mutlaqo TAQIQLANADI!

MAVZU: "{topic}"

{mode_guidelines}

TIL TALABI:
{lang_instruction}

MUHIM QAT'IY TALABLAR (INSON DARAJASIDAGI DIZAYN VA MAZMUN):
1. JAMI SLAYDLAR SONI: 'slides' ro'yxatida ANIQ VA ROPPA-ROSA {slide_count} TA SLAYD BO'LISHI SHART!
   - Kam ham, ko'p ham bo'lmasin. Aniq {slide_count} ta unikal slayd.

2. INSON DIZAYNERI USLUBI — KUCHLI SARLAVHALAR VA MAZMUN (QAT'IY QOIDALAR):
   - "Kirish", "Asosiy tushuncha", "Omil 1", "Strategiya 2", "Loyiha rejasi" kabi zerikarli va qolip so'zlar QAT'IYAN MAN ETILADI!
   - Sarlavhalar xuddi Forbes yoki Harvard Business Review maqolalaridek o'quvchi diqqatini darhol jalb qiluvchi, natijaga va ma'noga yo'naltirilgan bo'lsin (masalan: "2026-yilgi burilish nuqtasi: Bozor qayerga qarab ketmoqda?", "Nega 78% an'anaviy yondashuvlar samarasiz?", "Raqamli intizom: Biznesni 3 barobar tezlashtirish yo'li").
   - Kategoriya tegi ('category_badge') 1-2 so'zdan iborat professional belgi bo'lsin (masalan: 'STRATEGIK TAHLIL', 'ASOSIY METRIKA', 'BURILISH NUQTASI', 'YECHIM', 'YO'L XARITASI').
   - Har bir karta yoki punktning izohi 15-25 ta so'zdan iborat, aniq atamalar, ma'lumotlar va amaliy tavsiyalar bilan to'ldirilsin.

3. VIZUAL SAN'AT VA FOTOGRAFIA ('image_keyword'):
   - Har bir slayd uchun 'image_keyword' maydoniga slayd mavzusiga mos, go'zal va fotorealistik rasm generatsiya qilish uchun inglizcha 3-5 ta sifatli so'z kiriting.
   - Masalan: "futuristic clean laboratory scientist microscope 4k", "uzbekistan samarkand registan historical sunset cinematic", "cybersecurity digital shield protection high tech glowing".
   - Bu rasmlar slaydda zamonaviy 60/40 insoniy vizual kompozitsiya hosil qilish uchun ishlatiladi.

4. HAR BIR SLAYDNING VIZUAL STRUKTURASI ALMASHIB TURISHI SHART:
   - Ketma-ket bir xil layout ishlatilmasin! Tomoshabin har bir slaydda yangi vizual shaklni ko'rsin.
   - Foydalaniladigan layout turlari:
     * "title_slide" (1-slayd uchun ta'sirchan muqova)
     * "cards_grid" (3 ta asosiy yo'nalish yoki g'oya kartalari)
     * "chart_slide" (haqiqiy PowerPoint diagrammasi: dinamika yoki taqsimot ko'rsatkichlari)
     * "stats_metrics" (katta, hayratlanarli raqamlar: masalan '+140%', '$4.2M', '99.4%', '24/7')
     * "comparison" (an'anaviy vs innovatsion yechim solishtiruvi)
     * "timeline_steps" (bosqichma-bosqich yo'l xaritasi yoki qadamlar)
     * "matrix_2x2" (4 ta asosiy burchak yoki strategik ustun)
     * "quote_highlight" (kuchli falsafiy fikr yoki bozor eksperti xulosasi)
     * "checklist_points" (amaliy 4 ta oltin qoida yoki harakatlar tekshiruv ro'yxati)
     * "conclusion" (yakuniy kuchli xulosa va harakatga chorlov)

5. JONLI VA TA'SIRCHAN SPIKER NUTQI ('speaker_speech'):
   - {speech_instruction}
   - Nutq quruq matn o'qish emas, balki zalga qarab jonli murojaat qiladigan professional notiq ovozida bo'lsin.
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
    """Slaydlar soni kam chiqqan taqdirda qo'shimcha boyituvchi sifatli va turfa xil slaydlar bazasi."""
    short_t = topic if len(topic) < 40 else topic[:40] + "..."
    spk = lambda s: s if with_speech else None
    return [
        SlideContent(
            layout="cards_grid",
            category_badge="CHUQUR TAHLIL",
            title=f"{short_t}: Muvaffaqiyat Omillari",
            subtitle="Mavzuning samaradorligini ta'minlovchi asosiy yo'nalishlar va tamoyillar",
            cards=[
                CardItem(title="Aniq Maqsadlar", description="Har bir jarayonda o'lchanadigan natijalar va strategik vazifalarni belgilash.", badge="Omil 1"),
                CardItem(title="Resurslar Tahlili", description="Mavjud imkoniyatlar, vaqt va moddiy resurslardan oqilona foydalanish.", badge="Omil 2"),
                CardItem(title="Monitoring va Nazorat", description="Har bir bosqichni doimiy nazorat qilib borish va tezkor tuzatishlar kiritish.", badge="Omil 3"),
            ],
            speaker_speech=spk("Ushbu slaydda biz jarayonning muvaffaqiyatini ta'minlovchi uchta asosiy omilni ko'rib chiqamiz. Ularning har biri yakuniy natijaga bevosita ta'sir ko'rsatadi."),
        ),
        SlideContent(
            layout="stats_metrics",
            category_badge="NATIJALAR VA STATISTIKA",
            title="Kutilayotgan O'sish va Dinamika",
            subtitle="Amaliyotga tatbiq etish orqali erishiladigan asosiy ko'rsatkichlar",
            stats=[
                StatItem(number="92%", label="Samaradorlik", description="Tizimli yondashuv natijasida ish sifati ortishi"),
                StatItem(number="2.8X", label="Tezlik", description="Topshiriqlar bajarilish vaqtining qisqarishi"),
                StatItem(number="65%", label="Xarajat qisqarishi", description="Ortiqcha sarf-xarajatlar oldini olish"),
                StatItem(number="100%", label="Ishonchlilik", description="Standartlarga to'liq mos kelish darajasi"),
            ],
            speaker_speech=spk("Ko'rib turganingizdek, raqamlar o'z-o'zidan gapirmoqda. Tizimli yondashuv samaradorlikni 92 foizgacha oshirish imkonini beradi."),
        ),
        SlideContent(
            layout="quote_highlight",
            category_badge="MUHIM FALSAFA VA IQTIHOS",
            title="Mavzuning Asosiy G'oyasi",
            subtitle="Tizimning chuqur ma'nosi va strategik ahamiyati",
            quote_text="\"Katta muvaffaqiyatlar — har kuni kiritiladigan kichik, ammo qat'iy intizomli intilishlar mevasidir.\"",
            quote_author="Strategik Ekspert Xulosasi",
            highlight_takeaway="Har bir o'zgarish avvalambor to'g'ri tushuncha va qarashdan boshlanadi.",
            speaker_speech=spk("Ushbu iqtibos butun loyihaning ruhini ifodalaydi. Katta o'sishga erishish uchun intizomli qadamlar zarur."),
        ),
        SlideContent(
            layout="comparison",
            category_badge="IMKONIYATLAR VA XAVFLAR",
            title="Yechimning Afzalliklari",
            subtitle="Kutilayotgan ijobiy o'zgarishlar va yuzaga kelishi mumkin bo'lgan to'siqlar yechimi",
            comparison_col1=ComparisonColumn(
                header="Asosiy Yutuqlar",
                badge="Afzalliklar",
                points=[
                    "Barcha jarayonlarning shaffof va oson boshqarilishi",
                    "Xatoliklar ehtimolini minimal darajaga tushirish",
                    "Jamoa va tizim o'rtasidagi uyg'unlikning kuchayishi",
                ],
            ),
            comparison_col2=ComparisonColumn(
                header="Xavflarni Kamaytirish",
                badge="Yechimlar",
                points=[
                    "Oldindan xavflarni prognoz qilish va profilaktika",
                    "Favqulodda vaziyatlar uchun tayyor rejalar mavjudligi",
                    "Doimiy xavfsizlik va barqarorlikni ta'minlash",
                ],
            ),
            speaker_speech=spk("Ushbu taqqoslash orqali yangi yechimning asosiy afzalliklari hamda yuzaga kelishi mumkin bo'lgan xatarlarni qanday bartaraf etishimiz ko'rsatilgan."),
        ),
        SlideContent(
            layout="matrix_2x2",
            category_badge="4 TA USTUN (MATRITSA)",
            title="Barqaror Rivojlanish Matritsasi",
            subtitle="Tizimni 4 ta asosiy burchak va tamoyillar bo'yicha tahlili",
            matrix_items=[
                CardItem(title="Kadrlar Salohiyati", description="Iqtidorli mutaxassislarni jalb qilish va uzluksiz malakasini oshirib borish.", badge="01. Inson"),
                CardItem(title="Texnologik Quvvat", description="Zamonaviy algoritmlar, ma'lumotlar bazasi va bulutli servislar.", badge="02. Texnika"),
                CardItem(title="Moliyaviy Oqilonalik", description="Xarajatlarni maqbullashtirish va yuqori daromadlilikka erishish.", badge="03. Moliya"),
                CardItem(title="Bozor Talabi", description="Auditoriya ehtiyojlarini oldindan sezish va tezkor yechim berish.", badge="04. Bozor"),
            ],
            speaker_speech=spk("Ushbu matritsada 4 ta asosiy ustun jamlangan: inson kapitali, texnologiya, moliya va bozor talablari."),
        ),
        SlideContent(
            layout="timeline_steps",
            category_badge="YO'L XARITASI",
            title="Amaliy Harakatlar Rejasi",
            subtitle="Mavzuni bosqichma-bosqich hayotga tatbiq etish yo'nalishlari",
            steps=[
                CardItem(title="Dastlabki Tayyorgarlik", description="Zarur ma'lumotlar bazasini yig'ish va rejalashtirish.", badge="Qadam 1"),
                CardItem(title="Tizimni Integratsiya Qilish", description="Yangi uslub va vositalarni ish jarayoniga kiritish.", badge="Qadam 2"),
                CardItem(title="Sinov va Sifat Nazorati", description="Dastlabki natijalarni baholash va takomillashtirish.", badge="Qadam 3"),
                CardItem(title="Barqaror Qo'llash", description="Muntazam ishlash rejimiga o'tish va kengaytirish.", badge="Qadam 4"),
            ],
            speaker_speech=spk("Harakatlar rejasi to'rtta aniq qadamdan iborat. Har bir qadam o'z vaqtida va sifatli bajarilishi shart."),
        ),
        SlideContent(
            layout="checklist_points",
            category_badge="AMALIY CHECKLIST",
            title="Muvaffaqiyat Uchun Muhim Qoidalar",
            subtitle="Kutilgan natijaga erishishda rioya qilinishi shart bo'lgan talablar",
            checklist=[
                "Barcha ko'rsatkichlarni raqamlashtirish va har haftalik hisobotlarni yuritish",
                "Xatolar ustida tezkor ishlash va qayta aloqa mexanizmini yo'lga qo'yish",
                "Xavfsizlik protokollariga 100% qat'iy amal qilish",
                "Innovatsiyalarni sinashdan qo'rqmaslik va doimiy yangilanish",
            ],
            speaker_speech=spk("Ushbu checklist orqali siz kundalik faoliyatda amal qilishingiz kerak bo'lgan asosiy 4 ta oltin qoidani ko'rishingiz mumkin."),
        ),
        SlideContent(
            layout="cards_grid",
            category_badge="INNOVATSIYA VA TEXNOLOGIYA",
            title="Zamonaviy Vositalar va Usullar",
            subtitle="Ilg'or tajribalar va innovatsion imkoniyatlardan foydalanish",
            cards=[
                CardItem(title="Raqamli Platformalar", description="Zamonaviy bulutli va mobil texnologiyalardan keng foydalanish.", badge="Texnologiya"),
                CardItem(title="Intellektual Tahlil", description="Ma'lumotlar tahlili asosida to'g'ri qarorlar qabul qilish.", badge="AI & Data"),
                CardItem(title="Moslashuvchanlik", description="Har qanday o'zgaruvchan sharoitlarga tezkor moslashish qobiliyati.", badge="Agile"),
            ],
            speaker_speech=spk("Zamonaviy dunyoda innovatsion vositalarsiz natijaga erishib bo'lmaydi. Biz eng ilg'or raqamli yechimlarga tayanamiz."),
        ),
        SlideContent(
            layout="stats_metrics",
            category_badge="ISTIQBOLLAR",
            title="Kelajakdagi Ko'rsatkichlar",
            subtitle="Uzoq muddatli istiqbol va rivojlanish darajasi",
            stats=[
                StatItem(number="3-5 Yil", label="Strategik qamrov", description="Uzoq muddatli barqaror o'sish rejasi"),
                StatItem(number="+150%", label="Qamrov kengayishi", description="Foydalanuvchilar va hamkorlar o'sishi"),
                StatItem(number="Top 5", label="Yetakchilik o'rni", description="Soha bo'yicha yuqori pog'onalarga chiqish"),
                StatItem(number="A+", label="Sifat darajasi", description="Xalqaro talablar va standartlarga javob berish"),
            ],
            speaker_speech=spk("Kelajak istiqbollarimiz uzoq muddatli strategiyaga asoslangan bo'lib, o'sish sur'ati 150 foizdan oshishi kutilmoqda."),
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
        "gemini-3.5-flash",
        "gemini-3.8-flash",
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
        "gemini-3.5-flash",
        "gemini-3.8-flash",
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
    """
    Offline sinov va API key yo'q holatlar uchun to'liq slide_count miqdoridagi turfa xil yuqori sifatli slaydlar.
    """
    short_t = topic if len(topic) < 40 else topic[:40] + "..."
    spk = lambda s: s if with_speech else None
    base_slides = [
        SlideContent(
            layout="title_slide",
            category_badge="STRATEGIYA VA RIVOJLANISH",
            title=short_t,
            subtitle="Zamonaviy yondashuvlar, amaliy yechimlar va kelajak istiqbollari tahlili",
            highlight_takeaway="Yangi davr texnologiyalari va strategik o'sish sari qadam",
            speaker_speech=spk(f"Assalomu alaykum hurmatli qatnashchilar! Bugungi taqdimotimiz {short_t} mavzusiga bag'ishlanadi."),
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
            speaker_speech=spk("Ushbu slaydda ko'rib turganingizdek, avtomatlashtirish, sun'iy intellekt va masshtablash eng muhim ustunlar hisoblanadi."),
        ),
        SlideContent(
            layout="quote_highlight",
            category_badge="MUHIM FALSAFA VA IQTIHOS",
            title="Mavzuning Bosh Fikri",
            subtitle="Tizimning chuqur ma'nosi va strategik ahamiyati",
            quote_text="\"Kelajakni bashorat qilishning eng yaxshi usuli — uni bugundan boshlab o'z qo'llaringiz bilan yaratishdir.\"",
            quote_author="Strategik Ekspert Fikri",
            highlight_takeaway="Rivojlanish va innovatsiyalar to'xtovsiz harakat talab qiladi.",
            speaker_speech=spk("Ushbu fikr bizning barcha sa'y-harakatlarimiz negizini tashkil etadi."),
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
            speaker_speech=spk("Statistika shuni ko'rsatmoqdaki, samaradorlik 85 foizga oshgan va jarayonlar 3.4 barobar tezlashgan."),
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
            speaker_speech=spk("An'anaviy usul bilan zamonaviy yechim o'rtasidagi farq yaqqol ko'rinib turibdi. Innovatsiyalar vaqt va mablag'ni tejaydi."),
        ),
        SlideContent(
            layout="matrix_2x2",
            category_badge="4 TA ASOSIY USTUN",
            title="Tizimning Muvozanatli Matritsasi",
            subtitle="To'rtta asosiy sohada muvaffaqiyatga erishish parametrlari",
            matrix_items=[
                CardItem(title="Kadrlar Sifati", description="Mutaxassislar malakasi va mahorati.", badge="01. Kadr"),
                CardItem(title="Texnologiya", description="Ilg'or uskunalar va dasturiy ta'minot.", badge="02. IT"),
                CardItem(title="Moliyaviy Nazorat", description="Hisob-kitoblar va investitsiya samaradorligi.", badge="03. Moliya"),
                CardItem(title="Mijozlar Qoniqishi", description="Foydalanuvchilar ishonchi va sodiqligi.", badge="04. Natija"),
            ],
            speaker_speech=spk("To'rtta asosiy ustunimiz har bir yo'nalishda muvozanatni ta'minlaydi."),
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
            speaker_speech=spk("Rejamiz to'rtta tizimli bosqichga bo'lingan bo'lib, har bir qadam puxta hisob-kitoblarga asoslangan."),
        ),
        SlideContent(
            layout="checklist_points",
            category_badge="AMALIY TAVSIYALAR",
            title="Amaliy Harakatlar Ro'yxati",
            subtitle="Rejani muvaffaqiyatli amalga oshirish qoidalari",
            checklist=[
                "Barcha jarayonlarni aniq metrikalar orqali o'lchab borish",
                "Jamoaviy mas'uliyat va muntazam sinovlar o'tkazish",
                "Xavfsizlik va barqarorlik talablariga rioya qilish",
                "Olingan natijalarni tahlil qilib doimiy takomillashish",
            ],
            speaker_speech=spk("Ushbu qoidalarga amal qilgan holda, har qanday to'siqni yengib o'tish mumkin."),
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
            speaker_speech=spk("Xulosa qilib aytganda, bugungi imkoniyatlardan unumli foydalanish ertangi muvaffaqiyatimiz garovidir. E'tiboringiz uchun rahmat!"),
        ),
    ]

    init_pres = PresentationContent(topic=topic, language=language, slides=base_slides)
    return _ensure_slide_count(init_pres, slide_count, topic, language, with_speech=with_speech)


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
        "gemini-3.5-flash",
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
        "gemini-3.5-flash",
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
