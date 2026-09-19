import io
import logging
import os
from typing import Optional
import pypdf
import docx
from google import genai
from google.genai import types

import config

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """PDF fayldan barcha matnlarni ajratib oladi."""
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        texts = []
        for i, page in enumerate(reader.pages):
            if i > 50:  # Maksimal 50 bet (serverni yuklamaslik uchun)
                break
            t = page.extract_text()
            if t:
                texts.append(t)
        return "\n".join(texts).strip()
    except Exception as e:
        logger.error(f"PDF o'qishda xatolik: {e}")
        return ""


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Word (.docx) fayldan matnlarni ajratib oladi."""
    try:
        doc = docx.Document(io.BytesIO(file_bytes))
        paras = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paras).strip()
    except Exception as e:
        logger.error(f"DOCX o'qishda xatolik: {e}")
        return ""


def extract_text_from_txt(file_bytes: bytes) -> str:
    """Oddiy .txt fayldan matn o'qish."""
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            return file_bytes.decode(enc).strip()
        except UnicodeDecodeError:
            continue
    return ""


async def transcribe_voice_with_gemini(voice_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """
    Ovozli xabarni (Voice / Audio) Gemini 3.8 Flash orqali tahlil qilib, 
    undagi taqdimot mavzusi va talablarni aniqlab beradi.
    """
    if not config.GEMINI_API_KEY:
        return "Sun'iy intellekt va kelajak texnologiyalari"

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    
    prompt = (
        "Foydalanuvchi taqdimot (slayd) tayyorlash uchun ovozli xabar yubordi. "
        "Ushbu audio yozuvni tinglang va foydalanuvchi qaysi mavzuda taqdimot qilmoqchi ekanini, "
        "asosiy talablarini aniqlang. Javobingiz faqatgina aniqlangan MAVZU nomidan iborat bo'lsin "
        "(masalan: 'Sun'iy intellektning tibbiyotdagi o'rni' yoki 'Startap loyihasi rejasi'). "
        "Hech qanday ortiqcha so'z yozmang, faqat mavzuning o'zini qaytaring."
    )

    try:
        audio_part = types.Part.from_bytes(data=voice_bytes, mime_type=mime_type)
        response = await client.aio.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[prompt, audio_part],
        )
        return (response.text or "").strip().strip('"').strip("'")
    except Exception as e:
        logger.error(f"Ovozni tahlil qilishda xatolik: {e}")
        return ""


async def extract_text_and_topic_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> tuple:
    """
    Kitob varag'i, konspekt yoki doska rasmini tahlil qilib, 
    undagi matnni (OCR) va eng asosiy mavzu nomini qaytaradi.
    Qaytaradi: (mavzu, to'liq_matn)
    """
    if not config.GEMINI_API_KEY:
        return "Rasm Asosida Taqdimot", "Ushbu rasm asosida tayyorlangan taqdimot kontenti."

    client = genai.Client(api_key=config.GEMINI_API_KEY)

    prompt = (
        "Siz professional taqdimot yaratuvchi yordamchisiz. "
        "Foydalanuvchi kitob, konspekt daftari yoki ilmiy hujjat rasmini yubordi.\n"
        "1. Rasmdagi barcha asosiy matnlarni, tushunchalarni va faktlarni to'liq o'qing (OCR).\n"
        "2. Ushbu material uchun mos, qisqa va aniq MAVZU nomini belgilang.\n\n"
        "Javobingizni quyidagi formatda qaytaring:\n"
        "MAVZU: [Qisqa aniq mavzu nomi]\n"
        "MATN:\n[Rasmdan o'qilgan batafsil konspekt va ma'lumotlar]"
    )

    try:
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        response = await client.aio.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[prompt, image_part],
        )
        res_text = (response.text or "").strip()
        topic = "Rasm Asosidagi Taqdimot"
        doc_text = res_text

        if "MAVZU:" in res_text and "MATN:" in res_text:
            parts = res_text.split("MATN:", 1)
            topic_part = parts[0].replace("MAVZU:", "").strip()
            topic = topic_part.splitlines()[0].strip().strip('"').strip("'")
            doc_text = parts[1].strip()

        return topic, doc_text
    except Exception as e:
        logger.error(f"Rasmni OCR tahlil qilishda xatolik: {e}")
        return "Rasm Asosida Taqdimot", ""

