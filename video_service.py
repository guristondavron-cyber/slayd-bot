import os
import re
import json
import asyncio
import logging
import random
import subprocess
import tempfile
import urllib.parse
from typing import List, Dict, Any, Optional, Callable, Awaitable
from pydantic import BaseModel, Field
import requests
import shutil
import imageio_ffmpeg
import static_ffmpeg
import edge_tts
from google import genai
from google.genai import types

import config

logger = logging.getLogger(__name__)

# static-ffmpeg yo'llarini tizim muhitiga avtomatik qo'shish
try:
    static_ffmpeg.add_paths()
except Exception as _e:
    logger.warning(f"static_ffmpeg add_paths warning: {_e}")

# Output directory for rendered videos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEOS_DIR = os.path.join(BASE_DIR, "generated_videos")
os.makedirs(VIDEOS_DIR, exist_ok=True)

# Limit concurrent heavy video rendering jobs to prevent server overload
VIDEO_SEMAPHORE = asyncio.Semaphore(2)


class VideoScene(BaseModel):
    scene_number: int = Field(description="Sahna tartib raqami (1, 2, 3...)")
    title: str = Field(description="Sahnaning qisqa mazmuni (2-4 so'z)")
    narration: str = Field(description="Diktant yoki tushuntirish nutqi matni (o'zbek tilida, 15-25 so'z, 8-10 soniya nutq)")
    visual_prompt: str = Field(description="Ushbu sahnani generatsiya qilish uchun batafsil inglizcha kinematik promt")
    camera_motion: str = Field(default="zoom_in", description="Kamera harakati: 'zoom_in', 'zoom_out', 'pan_right', 'pan_left', 'tilt_up'")


class VideoScenario(BaseModel):
    title: str = Field(description="Videofilmning jozibali sarlavhasi")
    summary: str = Field(description="Qisqacha ssenariy mazmuni")
    visual_style: str = Field(default="Cinematic documentary 4k, photorealistic", description="Umumiy vizual uslub")
    scenes: List[VideoScene] = Field(description="Mantiqiy ketma-ket bir-birini davom ettiruvchi sahnalar")


def get_ffmpeg_binary() -> str:
    """Tizimdagi yoki static-ffmpeg/imageio orqali ffmpeg binary yo'lini qaytaradi."""
    # 1. Tizim PATH
    p = shutil.which("ffmpeg")
    if p:
        return p
    # 2. imageio-ffmpeg
    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    # 3. static_ffmpeg qayta chaqirish
    try:
        static_ffmpeg.add_paths()
        p = shutil.which("ffmpeg")
        if p:
            return p
    except Exception:
        pass
    return "ffmpeg"


def get_font_file() -> Optional[str]:
    """Tizimdagi mos shrift faylini aniqlaydi (subtitrlar uchun)."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def get_audio_duration(audio_path: str, ffmpeg_exe: str) -> float:
    """Audio fayl davomiyligini (soniyalarda) aniqlaydi."""
    try:
        cmd = [ffmpeg_exe, "-i", audio_path]
        res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
        if m:
            h, mn, s = m.groups()
            return int(h) * 3600 + int(mn) * 60 + float(s)
    except Exception as e:
        logger.warning(f"Audio duration error: {e}")
    return 7.5


async def generate_video_scenario(
    topic: str,
    duration_preset: str = "60s",
    language: str = "uz",
    api_key: Optional[str] = None,
) -> VideoScenario:
    """
    Google Gemini orqali mavzu bo'yicha ssenariy va sahnama-sahna promtlarni tuzadi.
    duration_preset: '30s' (3 sahna), '60s' (6 sahna), '180s' (15 sahna).
    """
    key = api_key or config.GEMINI_API_KEY
    if not key:
        raise ValueError("GEMINI_API_KEY topilmadi!")

    client = genai.Client(api_key=key)

    preset_scene_counts = {
        "30s": 3,
        "60s": 6,
        "180s": 9,
    }
    target_scenes = preset_scene_counts.get(duration_preset, 6)

    system_prompt = f"""
Siz professional kinorejissyor va ssenaristsiz. Sizga mavzu beriladi va siz qisqa videoroliklar zanjiridan iborat yaxlit, qiziqarli videofilm ssenariysini tuzishingiz kerak.

MAVZU: {topic}
SAHNALAR SONI: Aynan {target_scenes} ta sahna.
HAR BIR SAHNA DAVOMIYLIGI: ~8-10 soniya.
JAMI VIDEO VAQTI: {target_scenes * 10} soniya atrofida.

QAT'IY QOIDALAR:
1. UZLUKSIZLIK (CONTINUITY):
   - Har bir 10 sekundlik sahna oldingi sahnaning bevosita mantiqiy va vizual DAVOMI bo'lishi shart!
   - Qahramonlar, muhit, yorug'lik va umumiy uslub bir-biriga mos kelishi lozim.
   - 1-sahna: Kirish / umumiy plan (establishing shot).
   - O'rta sahnalar: Voqealar rivoji, harakatlar, tafsilotlar.
   - So'nggi sahna: Kulminatsiya va kuchli xulosa.

2. DIKTOR NUTQI (narration):
   - O'zbek tilida, ifodali, jonli va professional diktorlik uslubida bo'lsin.
   - Har bir sahna uchun 1-2 jumlalik (~15-22 so'z) matn yozing. 10 soniyada erkin o'qiladigan bo'lsin.
   - Qoliplardan qoching, tomoshabinni ekranga mixlab qo'yadigan qiziqarli faktlar va tasvirlarni ishlating.

3. VIZUAL PROMT (visual_prompt):
   - Mutlaqo INGLIZ tilida, neyrotarmoq uchun juda batafsil yozilsin.
   - Masalan: "Cinematic 8k, photorealistic, dramatic golden hour lighting, 35mm film lens, atmospheric dust particles, epic historical ambiance, award-winning cinematography, no text, no watermark".
   - Kamera harakatiga mos vizual tasvir bering.

4. KAMERA HARAKATI (camera_motion):
   - Har bir sahna uchun har xil kamera harakatini tanlang: 'zoom_in', 'zoom_out', 'pan_right', 'pan_left', 'tilt_up'.
"""

    candidate_models = [
        config.GEMINI_MODEL,
        "gemini-2.5-flash",
        "gemini-3.8-flash",
        "gemini-flash-latest",
        "gemini-3.5-flash",
    ]

    for model_name in candidate_models:
        try:
            logger.info(f"Gemini {model_name} orqali video ssenariysi tuzilmoqda...")
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=system_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=VideoScenario,
                    temperature=0.7,
                ),
            )
            raw_text = response.text
            data = json.loads(raw_text)
            scenario = VideoScenario.model_validate(data)
            if scenario.scenes and len(scenario.scenes) > 0:
                return scenario
        except Exception as e:
            logger.warning(f"Model {model_name} xatosi: {e}")
            continue

    # Fallback agar neyrotarmoq javobi olinmasa
    return VideoScenario(
        title=topic[:50],
        summary=f"{topic} bo'yicha qiziqarli video lavha",
        visual_style="Cinematic photorealistic 4k",
        scenes=[
            VideoScene(
                scene_number=i,
                title=f"{topic} - {i}-qism",
                narration=f"{topic} mavzusi bo'yicha muhim va qiziqarli faktlar bilan tanishamiz.",
                visual_prompt=f"Cinematic photorealistic shot about {topic}, ultra-detailed, 8k, dramatic lighting",
                camera_motion="zoom_in" if i % 2 == 1 else "zoom_out",
            )
            for i in range(1, target_scenes + 1)
        ],
    )


async def generate_scene_voice(
    narration: str,
    output_path: str,
    voice: str = "uz-UZ-MadinaNeural",
) -> float:
    """Edge-TTS orqali sahna audio nutqini yaratadi va davomiyligini qaytaradi."""
    ffmpeg_exe = get_ffmpeg_binary()
    try:
        communicate = edge_tts.Communicate(narration, voice)
        await asyncio.wait_for(communicate.save(output_path), timeout=12.0)
    except Exception as e:
        logger.warning(f"TTS error or timeout: {e}")
        # Bo'sh audio fallback yaratish
        try:
            subprocess.run([
                ffmpeg_exe, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-t", "6", "-c:a", "mp3", output_path
            ], capture_output=True, timeout=5, stdin=subprocess.DEVNULL)
        except Exception:
            pass

    return get_audio_duration(output_path, ffmpeg_exe)


def download_scene_image(visual_prompt: str, output_path: str, seed: int) -> bool:
    """
    Pollinations AI (Turbo) va Picsum orqali yuqori sifatli 1280x720 fotorealistik kadrni tezkor yuklab oladi.
    """
    clean_prompt = visual_prompt.strip()
    full_prompt = f"{clean_prompt}, cinematic, 8k, highly detailed, photorealistic, atmospheric lighting, 16:9 widescreen, no text, no watermark"
    encoded = urllib.parse.quote(full_prompt)

    # Birinchi navbatda Turbo (1-2 soniyada tayyor bo'ladi)
    urls = [
        f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&model=turbo&nologo=true&seed={seed}",
        f"https://picsum.photos/seed/{seed}/1280/720",
        f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&model=flux&nologo=true&seed={seed}",
    ]

    for url in urls:
        try:
            resp = requests.get(url, timeout=7)
            if resp.status_code == 200 and len(resp.content) > 5000:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                return True
        except Exception:
            pass

    # Fallback to deterministic clean placeholder image with Pillow
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (1280, 720), color=(random.randint(20, 45), random.randint(25, 55), random.randint(40, 80)))
        draw = ImageDraw.Draw(img)
        draw.rectangle([(40, 40), (1240, 680)], outline=(100, 150, 220), width=3)
        img.save(output_path, "JPEG")
        return True
    except Exception as e:
        logger.error(f"Fallback image error: {e}")
        return False


def build_motion_filter(motion: str, duration: float, fps: int = 25) -> str:
    """FFmpeg zoompan filtri orqali turli kinematik kamera harakatlarini hosil qiladi."""
    total_frames = max(25, int(duration * fps))

    if motion == "zoom_out":
        return f"scale=1280:720,zoompan=z='if(lte(zoom,1.0),1.20,max(1.001,zoom-0.0012))':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1280x720:fps={fps}"
    elif motion == "pan_right":
        return f"scale=1280:720,zoompan=z=1.12:d={total_frames}:x='(in/{total_frames})*(iw-iw/zoom)':y='ih/2-(ih/zoom/2)':s=1280x720:fps={fps}"
    elif motion == "pan_left":
        return f"scale=1280:720,zoompan=z=1.12:d={total_frames}:x='(1-(in/{total_frames}))*(iw-iw/zoom)':y='ih/2-(ih/zoom/2)':s=1280x720:fps={fps}"
    elif motion == "tilt_up":
        return f"scale=1280:720,zoompan=z=1.12:d={total_frames}:x='iw/2-(iw/zoom/2)':y='(1-(in/{total_frames}))*(ih-ih/zoom)':s=1280x720:fps={fps}"
    else:
        # Default: zoom_in
        return f"scale=1280:720,zoompan=z='min(zoom+0.0014,1.20)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1280x720:fps={fps}"


def render_single_scene_clip(
    image_path: str,
    audio_path: str,
    subtitle_text: str,
    output_clip_path: str,
    motion: str,
    duration: float,
    ffmpeg_exe: str,
) -> bool:
    """
    Bitta sahna uchun: rasm + kamera harakati + ovoz + subtitrlar + fade effektlarini
    bitta MP4 kadrga aylantiradi.
    Ultrafast tezlik va 4 bosqichli xavfsiz fallback tizimiga ega.
    """
    font_file = get_font_file()
    motion_filter = build_motion_filter(motion, duration, fps=25)
    fade_duration = 0.35
    fade_out_start = max(0.1, duration - fade_duration)

    # 1-URINISH: To'liq kinematika (harakat + subtitrlar + fade)
    if font_file and subtitle_text:
        sub_txt_path = output_clip_path + ".sub.txt"
        try:
            words = subtitle_text.split()
            lines = []
            cur_line = []
            cur_len = 0
            for w in words:
                if cur_len + len(w) > 40 and cur_line:
                    lines.append(" ".join(cur_line))
                    cur_line = [w]
                    cur_len = len(w)
                else:
                    cur_line.append(w)
                    cur_len += len(w) + 1
            if cur_line:
                lines.append(" ".join(cur_line))
            wrapped_sub = "\n".join(lines[:2])

            with open(sub_txt_path, "w", encoding="utf-8") as f:
                f.write(wrapped_sub)

            clean_font = font_file.replace("\\", "/").replace(":", "\\:")
            clean_sub_txt = sub_txt_path.replace("\\", "/").replace(":", "\\:")
            drawtext_filter = (
                f"drawtext=fontfile='{clean_font}':textfile='{clean_sub_txt}':"
                f"fontsize=24:fontcolor=white:box=1:boxcolor=black@0.65:boxborderw=8:"
                f"line_spacing=6:x=(w-text_w)/2:y=h-text_h-45"
            )
            vfilters1 = f"{motion_filter},fade=t=in:st=0:d={fade_duration},fade=t=out:st={fade_out_start:.2f}:d={fade_duration},{drawtext_filter}"
            cmd1 = [
                ffmpeg_exe, "-y",
                "-loop", "1", "-i", image_path,
                "-i", audio_path,
                "-vf", vfilters1,
                "-t", f"{duration:.2f}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
                "-c:a", "aac", "-b:a", "192k", "-shortest",
                output_clip_path,
            ]
            res1 = subprocess.run(cmd1, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, stdin=subprocess.DEVNULL)
            if res1.returncode == 0 and os.path.exists(output_clip_path) and os.path.getsize(output_clip_path) > 1000:
                return True
        except Exception as e:
            logger.warning(f"Tier 1 render with subtitles failed: {e}")
        finally:
            if os.path.exists(sub_txt_path):
                try:
                    os.remove(sub_txt_path)
                except Exception:
                    pass

    # 2-URINISH: Kamera harakati + audio (subtitrsiz)
    try:
        vfilters2 = f"{motion_filter},fade=t=in:st=0:d={fade_duration},fade=t=out:st={fade_out_start:.2f}:d={fade_duration}"
        cmd2 = [
            ffmpeg_exe, "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_path,
            "-vf", vfilters2,
            "-t", f"{duration:.2f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
            "-c:a", "aac", "-b:a", "192k", "-shortest",
            output_clip_path,
        ]
        res2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=18, stdin=subprocess.DEVNULL)
        if res2.returncode == 0 and os.path.exists(output_clip_path) and os.path.getsize(output_clip_path) > 1000:
            return True
    except Exception as e:
        logger.warning(f"Tier 2 render failed: {e}")

    # 3-URINISH: Oddiy scale + fade + audio (zoompan yuklamasisiz)
    try:
        vfilters3 = f"scale=1280:720,setsar=1,fade=t=in:st=0:d={fade_duration},fade=t=out:st={fade_out_start:.2f}:d={fade_duration}"
        cmd3 = [
            ffmpeg_exe, "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_path,
            "-vf", vfilters3,
            "-t", f"{duration:.2f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
            "-c:a", "aac", "-b:a", "192k", "-shortest",
            output_clip_path,
        ]
        res3 = subprocess.run(cmd3, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, stdin=subprocess.DEVNULL)
        if res3.returncode == 0 and os.path.exists(output_clip_path) and os.path.getsize(output_clip_path) > 1000:
            return True
    except Exception as e:
        logger.warning(f"Tier 3 render failed: {e}")

    # 4-URINISH: Minimal statik kadr (100% kafolatli oxirgi chora)
    try:
        cmd4 = [
            ffmpeg_exe, "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_path,
            "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
            "-c:a", "aac", "-b:a", "128k", "-shortest",
            "-t", f"{duration:.2f}",
            output_clip_path,
        ]
        subprocess.run(cmd4, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=12, stdin=subprocess.DEVNULL)
        return os.path.exists(output_clip_path) and os.path.getsize(output_clip_path) > 500
    except Exception as e:
        logger.error(f"Tier 4 render fatal: {e}")
        return False


def assemble_all_clips(
    clip_paths: List[str],
    final_output_path: str,
    ffmpeg_exe: str,
) -> bool:
    """Barcha sahna kadrlarini ulab, fon musiqasi qo'shib, tayyor MP4 video hosil qiladi."""
    if not clip_paths:
        return False

    concat_txt_path = final_output_path + ".list.txt"
    try:
        with open(concat_txt_path, "w", encoding="utf-8") as f:
            for p in clip_paths:
                clean_p = os.path.abspath(p).replace("\\", "/")
                f.write(f"file '{clean_p}'\n")

        # 1-qadam: Barcha kadrlarni bitta videoga tezkor birlashtirish
        temp_merged = final_output_path + ".temp.mp4"
        cmd_concat = [
            ffmpeg_exe, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_txt_path,
            "-c", "copy",
            temp_merged,
        ]
        res = subprocess.run(cmd_concat, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25, stdin=subprocess.DEVNULL)
        if res.returncode != 0 or not os.path.exists(temp_merged):
            # Fallback re-encode
            cmd_reencode = [
                ffmpeg_exe, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_txt_path,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-c:a", "aac",
                temp_merged,
            ]
            subprocess.run(cmd_reencode, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=40, stdin=subprocess.DEVNULL)

        if not os.path.exists(temp_merged):
            return False

        # 2-qadam: Kinematik ambient fon musiqasi mikslari (atmosfera ovozi)
        total_duration = get_audio_duration(temp_merged, ffmpeg_exe)
        cmd_final = [
            ffmpeg_exe, "-y",
            "-i", temp_merged,
            "-f", "lavfi",
            "-i", f"aevalsrc=sin(110*2*PI*t)*0.015+sin(164.81*2*PI*t)*0.01+sin(220*2*PI*t)*0.008:d={total_duration}",
            "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=2[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            final_output_path,
        ]
        res_final = subprocess.run(cmd_final, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=35, stdin=subprocess.DEVNULL)
        if res_final.returncode == 0 and os.path.exists(final_output_path):
            return True

        # Agar amix da xatolik bo'lsa, birlashtirilgan videoning o'zini saqlaymiz
        if os.path.exists(temp_merged):
            if os.path.exists(final_output_path):
                os.remove(final_output_path)
            os.rename(temp_merged, final_output_path)
            return True

        return False
    finally:
        for tmp_f in [concat_txt_path, final_output_path + ".temp.mp4"]:
            if os.path.exists(tmp_f):
                try:
                    os.remove(tmp_f)
                except Exception:
                    pass


async def create_ai_video_pipeline(
    topic: str,
    duration_preset: str = "60s",
    voice: str = "uz-UZ-MadinaNeural",
    progress_callback: Optional[Callable[[int, str], Awaitable[None]]] = None,
) -> Optional[str]:
    """
    To'liq AI video yaratish konveyeri:
    1. Ssenariy tuzish (Gemini)
    2. Har bir sahnaning ovozi va rasmini olish (parallel)
    3. Kinematik kadrlarga aylantirish (ultrafast, fonda)
    4. Yaxlit MP4 film qilib montaj qilish
    """
    async with VIDEO_SEMAPHORE:
        ffmpeg_exe = get_ffmpeg_binary()
        temp_dir = tempfile.mkdtemp(prefix="ai_video_")
        clip_paths = []

        try:
            # 1-QADAM: Ssenariy
            if progress_callback:
                await progress_callback(10, "🎬 <b>1/4: Kinematik ssenariy va sahnalar tuzilmoqda...</b>")

            scenario = await generate_video_scenario(topic=topic, duration_preset=duration_preset)
            total_scenes = len(scenario.scenes)
            if total_scenes == 0:
                raise ValueError("Ssenariy tuzishda sahnalar yaratilmadi.")

            # 2 & 3-QADAM: Har bir sahnani generatsiya qilish va montajlash
            for idx, scene in enumerate(scenario.scenes, start=1):
                scene_pct = 15 + int((idx / total_scenes) * 65)
                if progress_callback:
                    await progress_callback(
                        scene_pct,
                        f"🎞 <b>2/4: Sahna {idx}/{total_scenes} tayyorlanmoqda:</b>\n"
                        f"<i>«{scene.title}»</i> (Ovoz va AI kadrlar olinmoqda...)"
                    )

                img_path = os.path.join(temp_dir, f"scene_{idx}.jpg")
                audio_path = os.path.join(temp_dir, f"scene_{idx}.mp3")
                clip_path = os.path.join(temp_dir, f"scene_{idx}.mp4")

                # Audio nutq va vizual kadrni PARALLEL (bir vaqtda) yuklab olish
                seed = random.randint(1000, 999999)
                audio_task = generate_scene_voice(scene.narration, audio_path, voice=voice)
                image_task = asyncio.to_thread(download_scene_image, scene.visual_prompt, img_path, seed)

                dur, _ = await asyncio.gather(audio_task, image_task)
                scene_duration = max(5.0, round(dur + 0.6, 2))

                # Kinematik kadrni fonda tezkor render qilish (event loop bloklanmaydi)
                success = await asyncio.to_thread(
                    render_single_scene_clip,
                    image_path=img_path,
                    audio_path=audio_path,
                    subtitle_text=scene.narration,
                    output_clip_path=clip_path,
                    motion=scene.camera_motion,
                    duration=scene_duration,
                    ffmpeg_exe=ffmpeg_exe,
                )

                if success and os.path.exists(clip_path):
                    clip_paths.append(clip_path)

                if progress_callback:
                    await progress_callback(
                        min(82, scene_pct + 4),
                        f"⚡️ <b>2/4: Sahna {idx}/{total_scenes} tayyor!</b>\n"
                        f"<i>«{scene.title}»</i> (Keyingi kadrga o'tilmoqda...)"
                    )

            if not clip_paths:
                raise ValueError("Birorta ham sahna kadrlari generatsiya qilinmadi.")

            # 4-QADAM: Yaxlit montaj va musiqa
            if progress_callback:
                await progress_callback(85, "✂️ <b>3/4: Barcha sahnalar ulanmoqda va fon musiqasi montaj qilinmoqda...</b>")

            safe_title = re.sub(r'[^a-zA-Z0-9_]', '_', topic[:25]).strip('_') or "ai_video"
            final_filename = f"{safe_title}_{random.randint(1000, 9999)}.mp4"
            final_path = os.path.join(VIDEOS_DIR, final_filename)

            assembled = await asyncio.to_thread(assemble_all_clips, clip_paths, final_path, ffmpeg_exe)

            if assembled and os.path.exists(final_path):
                if progress_callback:
                    await progress_callback(100, "✅ <b>4/4: Video to'liq tayyor! Telegramga yuklanmoqda...</b>")
                return final_path
            else:
                return None

        except Exception as e:
            logger.error(f"Video pipeline failed: {e}", exc_info=True)
            return None
        finally:
            # Vaqtinchalik fayllarni tozalash
            try:
                for root, dirs, files in os.walk(temp_dir, topdown=False):
                    for name in files:
                        os.remove(os.path.join(root, name))
                    for name in dirs:
                        os.rmdir(os.path.join(root, name))
                os.rmdir(temp_dir)
            except Exception:
                pass
