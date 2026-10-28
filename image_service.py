import os
import hashlib
import json
import urllib.parse
import urllib.request
import asyncio
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(__file__), "image_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _get_cache_path(prompt: str) -> str:
    h = hashlib.md5(prompt.strip().lower().encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{h}.jpg")


def _search_wikimedia_image(query: str, timeout: int = 4) -> Optional[bytes]:
    """Vikipediya va Wikimedia Commons orqali mavzuga 100% mos rasmni topadi."""
    try:
        clean_q = " ".join([w for w in query.split() if len(w) > 2][:4])
        if not clean_q:
            return None
        url = (
            "https://en.wikipedia.org/w/api.php?action=query&format=json&prop=pageimages"
            f"&generator=search&gsrsearch={urllib.parse.quote(clean_q)}&gsrlimit=3&pithumbsize=800"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SlideGeneratorBot/2.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            pages = data.get("query", {}).get("pages", {})
            for pid, p in pages.items():
                if "thumbnail" in p and "source" in p["thumbnail"]:
                    thumb_url = p["thumbnail"]["source"]
                    img_req = urllib.request.Request(
                        thumb_url,
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SlideGeneratorBot/2.0"}
                    )
                    with urllib.request.urlopen(img_req, timeout=timeout) as img_resp:
                        if img_resp.status == 200:
                            content = img_resp.read()
                            if len(content) > 3000:
                                return content
    except Exception as e:
        logger.debug(f"Wikimedia search ogohlantirish ({query[:25]}): {e}")
    return None


def fetch_ai_image_sync(prompt: str, width: int = 800, height: int = 600, timeout: int = 9) -> Optional[str]:
    """
    Slayd mavzusi yoki kalit so'zi bo'yicha mavzuga 100% mos rasm yuklab oladi va keshlaydi.
    1. Pollinations AI (Flux/SDXL) - zamonaviy AI foto generatsiyasi.
    2. Wikimedia Commons - haqiqiy tarixiy, ilmiy, geografik va akademik fotosuratlar.
    Hech qachon tasodifiy (random/picsum) rasmlar qaytarmaydi!
    """
    if not prompt or len(prompt.strip()) < 2:
        return None

    clean_prompt = prompt.strip()
    cache_path = _get_cache_path(clean_prompt)
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 2048:
        return cache_path

    # 1. Pollinations AI orqali fotorealistik rasm generatsiya qilish
    try:
        safe_kw = re.sub(r"[^a-zA-Z0-9\s\-_]", " ", clean_prompt)
        safe_kw = " ".join(safe_kw.split())[:120]
        if safe_kw:
            encoded_prompt = urllib.parse.quote(
                f"{safe_kw}, professional presentation slide visual, high quality documentary photo, 4k"
            )
            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true&seed=42"

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    data = response.read()
                    if len(data) > 3000:
                        with open(cache_path, "wb") as f:
                            f.write(data)
                        logger.info(f"AI rasm muvaffaqiyatli yuklandi: {safe_kw[:30]}...")
                        return cache_path
    except Exception as e:
        logger.warning(f"Pollinations AI rasm yuklashda ogohlantirish ({clean_prompt[:25]}...): {e}")

    # 2. Wikimedia Commons zaxira manbasi (Haqiqiy mavzuli fotosuratlar)
    wiki_data = _search_wikimedia_image(clean_prompt, timeout=5)
    if wiki_data:
        try:
            with open(cache_path, "wb") as f:
                f.write(wiki_data)
            logger.info(f"Wikimedia mavzuli rasm yuklandi: {clean_prompt[:30]}...")
            return cache_path
        except Exception as e:
            logger.warning(f"Wikimedia rasmni saqlashda xatolik: {e}")

    return None


async def fetch_ai_image(prompt: str, width: int = 800, height: int = 600, timeout: int = 9) -> Optional[str]:
    """Asinxron AI rasm yuklab olish wrapperi."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_ai_image_sync, prompt, width, height, timeout)
