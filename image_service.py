import os
import hashlib
import urllib.parse
import urllib.request
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(__file__), "image_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _get_cache_path(prompt: str) -> str:
    h = hashlib.md5(prompt.strip().lower().encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{h}.jpg")


def fetch_ai_image_sync(prompt: str, width: int = 800, height: int = 600, timeout: int = 8) -> Optional[str]:
    """
    Slayd mavzusi yoki kalit so'zi bo'yicha AI rasmni yuklab oladi va keshlaydi.
    Pollinations AI (Flux/SDXL) xizmatidan foydalanadi (bepul, API key talab qilmaydi).
    Agar yuklab bo'lmasa, None qaytaradi.
    """
    if not prompt or len(prompt.strip()) < 2:
        return None

    clean_prompt = prompt.strip()
    cache_path = _get_cache_path(clean_prompt)
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 1024:
        return cache_path

    # Inglizcha visual promptni boyitish
    encoded_prompt = urllib.parse.quote(f"{clean_prompt}, professional modern presentation visual, cinematic lighting, 8k resolution, minimalist clean aesthetic")
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true&seed=42"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                data = response.read()
                if len(data) > 1024:
                    with open(cache_path, "wb") as f:
                        f.write(data)
                    logger.info(f"AI rasm muvaffaqiyatli yuklandi: {clean_prompt[:30]}...")
                    return cache_path
    except Exception as e:
        logger.warning(f"AI rasm yuklashda ogohlantirish ({clean_prompt[:25]}...): {e}")

    return None


async def fetch_ai_image(prompt: str, width: int = 800, height: int = 600, timeout: int = 8) -> Optional[str]:
    """Asinxron AI rasm yuklab olish wrapperi."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_ai_image_sync, prompt, width, height, timeout)
