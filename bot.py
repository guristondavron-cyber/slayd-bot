import asyncio
import logging
import os
import sys
from typing import Dict, Any, Optional, Tuple

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiohttp import web

import config
import database
from document_service import (
    extract_text_from_pdf,
    extract_text_from_docx,
    extract_text_from_txt,
    transcribe_voice_with_gemini,
)
from gemini_service import (
    generate_presentation_with_gemini,
    generate_presentation_from_document,
    generate_mock_presentation,
    PresentationContent,
)
from slide_designer import create_presentation_file

# Logging sozlamalari
log_file = os.path.join(os.path.dirname(__file__), "bot.log")
handlers = [logging.FileHandler(log_file, encoding="utf-8")]
if sys.stdout is not None:
    handlers.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=handlers,
)
logger = logging.getLogger("SlideBot")

router = Router()


# FSM Holatlari
class SlideCreationState(StatesGroup):
    waiting_for_topic = State()
    waiting_for_language = State()
    waiting_for_slide_count = State()
    waiting_for_theme = State()


class AdminState(StatesGroup):
    waiting_for_channel = State()
    waiting_for_initial_limit = State()
    waiting_for_referral_reward = State()
    waiting_for_broadcast_message = State()
    waiting_for_give_limit = State()


def is_admin(user_id: int) -> bool:
    """Foydalanuvchi admin ekanligini tekshiradi."""
    uid_str = str(user_id)
    if config.ADMIN_ID and uid_str == config.ADMIN_ID:
        return True
    admin_setting = database.get_setting("admin_ids", "")
    return uid_str in [x.strip() for x in admin_setting.split(",") if x.strip()]


async def safe_callback_answer(callback: CallbackQuery, text: str = None, show_alert: bool = False):
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except Exception:
        pass


async def check_channel_subscription(bot: Bot, user_id: int) -> Tuple[bool, str]:
    """Majburiy a'zolik kanalini tekshiradi."""
    if is_admin(user_id):
        return True, ""

    channel = database.get_setting("required_channel", "").strip()
    if not channel:
        return True, ""

    if not channel.startswith("@") and not channel.startswith("-100"):
        channel = "@" + channel

    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        if member.status in ("member", "administrator", "creator"):
            return True, channel
        return False, channel
    except Exception as e:
        logger.warning(f"Kanal obunasini tekshirishda ogohlantirish: {e}")
        return True, channel  # Agar bot kanalda admin bo'lmasa, foydalanuvchini to'xtatmaymiz


def channel_sub_keyboard(channel: str) -> InlineKeyboardMarkup:
    clean_channel = channel.lstrip("@")
    url = f"https://t.me/{clean_channel}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga a'zo bo'lish", url=url)],
            [InlineKeyboardButton(text="✅ A'zo bo'ldim (Tekshirish)", callback_data="btn_check_sub")],
        ]
    )


def main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🚀 Yangi Slayd Yaratish", callback_data="btn_create_slide")],
        [
            InlineKeyboardButton(text="👤 Profil & Referal", callback_data="btn_profile"),
            InlineKeyboardButton(text="🎨 Mavzular", callback_data="btn_themes"),
        ],
        [InlineKeyboardButton(text="ℹ️ Bot Haqida & Qo'llanma", callback_data="btn_help")],
    ]
    if is_admin(user_id):
        buttons.append([InlineKeyboardButton(text="👑 Admin Paneli", callback_data="btn_admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def language_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
            ],
            [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="btn_cancel")],
        ]
    )


def slide_count_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="3 ta (Ekspress)", callback_data="count_3"),
                InlineKeyboardButton(text="5 ta (Tavsiya)", callback_data="count_5"),
            ],
            [
                InlineKeyboardButton(text="7 ta (Kengaytirilgan)", callback_data="count_7"),
                InlineKeyboardButton(text="10 ta (Katta taqdimot)", callback_data="count_10"),
            ],
            [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="btn_cancel")],
        ]
    )


def theme_selection_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for key, th in config.THEMES.items():
        btn = InlineKeyboardButton(text=f"{th.emoji} {th.name}", callback_data=f"theme_{key}")
        row.append(btn)
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="btn_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Jonli Statistika", callback_data="adm_stats")],
            [InlineKeyboardButton(text="📢 Majburiy Kanal Sozlamasi", callback_data="adm_channel")],
            [InlineKeyboardButton(text="🎁 Limit va Referal Bonusi", callback_data="adm_limits")],
            [InlineKeyboardButton(text="✉️ Foydalanuvchilarga Xabar (Rassilka)", callback_data="adm_broadcast")],
            [InlineKeyboardButton(text="🔙 Bosh Menyu", callback_data="btn_cancel")],
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject, bot: Bot):
    await state.clear()
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Foydalanuvchi"
    username = message.from_user.username or ""

    # Referal ID tekshirish (?start=ref_12345)
    referrer_id = None
    if command.args and command.args.startswith("ref_"):
        try:
            ref_candidate = int(command.args.replace("ref_", ""))
            if ref_candidate != user_id:
                referrer_id = ref_candidate
        except ValueError:
            pass

    user_dict, rewarded_ref, reward_amount = database.get_or_create_user(
        user_id=user_id,
        first_name=first_name,
        username=username,
        referrer_id=referrer_id,
    )

    # Agar do'sti taklif qilgan bo'lsa, taklif qiluvchiga xabar yuborish
    if rewarded_ref:
        try:
            await bot.send_message(
                chat_id=rewarded_ref,
                text=(
                    f"🎉 <b>Ajoyib yangilik!</b>\n\n"
                    f"Sizning referal havolangiz orqali yangi do'stingiz (<b>{first_name}</b>) botga qo'shildi!\n"
                    f"🎁 Hisobingizga <b>+{reward_amount} ta bepul slayd</b> qo'shildi."
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass

    # Majburiy kanal tekshiruvi
    is_subbed, channel = await check_channel_subscription(bot, user_id)
    if not is_subbed:
        await message.answer(
            f"Assalomu alaykum, <b>{first_name}</b>!\n\n"
            f"Botimizdan to'liq foydalanish uchun rasmiy kanalimizga a'zo bo'ling:\n"
            f"👉 <b>{channel}</b>",
            parse_mode="HTML",
            reply_markup=channel_sub_keyboard(channel),
        )
        return

    text = (
        f"Assalomu alaykum, <b>{first_name}</b>!\n\n"
        f"Men <b>Gemini AI Slayd Yaratuvchi</b> botman.\n"
        f"Siz menga ixtiyoriy <b>mavzu</b>, <b>PDF/Word hujjati</b> yoki hatto <b>ovozli xabar</b> yuboring — "
        f"men esa professional 16:9 formatdagi PowerPoint (.pptx) taqdimot tayyorlab beraman.\n\n"
        f"📊 <b>Sizning balansingiz:</b> {user_dict['slides_left']} ta bepul taqdimot\n\n"
        f"Boshlash uchun quyidagi tugmani bosing:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu_keyboard(user_id))


@router.callback_query(F.data == "btn_check_sub")
async def cb_check_subscription(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    is_subbed, channel = await check_channel_subscription(bot, user_id)
    if is_subbed:
        await safe_callback_answer(callback, "A'zolik tasdiqlandi! Rahmat.")
        user = database.get_user(user_id)
        slides = user["slides_left"] if user else 3
        text = (
            f"✅ <b>Obuna muvaffaqiyatli tasdiqlandi!</b>\n\n"
            f"📊 <b>Sizning balansingiz:</b> {slides} ta bepul taqdimot.\n\n"
            f"Slayd yaratish uchun quyidagi tugmani bosing:"
        )
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=main_menu_keyboard(user_id))
    else:
        await safe_callback_answer(callback, "Siz hali kanalga a'zo bo'lmadingiz!", show_alert=True)


@router.callback_query(F.data == "btn_cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_callback_answer(callback)
    await callback.message.edit_text("Amal bekor qilindi.", reply_markup=main_menu_keyboard(callback.from_user.id))


# ------------------ PROFIL VA REFERAL ------------------
@router.callback_query(F.data == "btn_profile")
async def cb_profile(callback: CallbackQuery, bot: Bot):
    await safe_callback_answer(callback)
    user_id = callback.from_user.id
    user = database.get_user(user_id)
    if not user:
        user = {"slides_left": 3, "referrals_count": 0}

    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    reward = database.get_setting("referral_reward", "2")

    text = (
        f"👤 <b>Sizning Profilingiz</b>\n\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"📊 <b>Qolgan slaydlar:</b> <b>{user['slides_left']} ta</b>\n"
        f"👥 <b>Taklif qilingan do'stlar:</b> <b>{user['referrals_count']} ta</b>\n\n"
        f"🎁 <b>Referal Dasturi:</b>\n"
        f"Do'stlaringizni taklif qiling va har bir do'stingiz uchun <b>+{reward} ta bepul slayd</b> oling!\n\n"
        f"🔗 <b>Sizning shaxsiy havolangiz:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"<i>Havolani do'stlaringizga yoki guruhlarga ulashing!</i>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↗️ Do'stlarga ulashish",
                    url=f"https://t.me/share/url?url={ref_link}&text=Ajoyib%20Gemini%20AI%20Slayd%20Generator%20boti!%20Sinab%20ko'ring:",
                )
            ],
            [InlineKeyboardButton(text="🚀 Slayd Yaratish", callback_data="btn_create_slide")],
            [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="btn_cancel")],
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


# ------------------ SLAYD YARATISH OQIMI ------------------
@router.callback_query(F.data == "btn_create_slide")
async def cb_start_create(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await safe_callback_answer(callback)
    user_id = callback.from_user.id

    # Obunani tekshirish
    is_subbed, channel = await check_channel_subscription(bot, user_id)
    if not is_subbed:
        await callback.message.edit_text(
            f"⚠️ Slayd yaratish uchun avval rasmiy kanalimizga a'zo bo'ling:\n👉 <b>{channel}</b>",
            parse_mode="HTML",
            reply_markup=channel_sub_keyboard(channel),
        )
        return

    # Limitni tekshirish
    if not database.has_slides_left(user_id, is_admin(user_id)):
        reward = database.get_setting("referral_reward", "2")
        bot_info = await bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
        text = (
            f"⚠️ <b>Sizning bepul slaydlar limitingiz tugadi!</b>\n\n"
            f"Yana yangi taqdimotlar yaratish uchun do'stlaringizni taklif qiling.\n"
            f"Har bir taklif qilingan do'st uchun sizga <b>+{reward} ta bepul slayd</b> beriladi!\n\n"
            f"🔗 <b>Sizning taklif havolangiz:</b>\n"
            f"<code>{ref_link}</code>"
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="↗️ Do'stlarga ulashish",
                        url=f"https://t.me/share/url?url={ref_link}&text=Sun'iy%20intellektda%20bepul%20slaydlar%20yasang:",
                    )
                ],
                [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="btn_cancel")],
            ]
        )
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
        return

    await state.set_state(SlideCreationState.waiting_for_topic)
    text = (
        "✍️ <b>Taqdimot mavzusini kiriting:</b>\n\n"
        "<i>Siz 3 xil usulda mavzu berishingiz mumkin:</i>\n"
        "1. Matn ko'rinishida yozing (masalan: <i>'Sun'iy intellekt kelajagi'</i>)\n"
        "2. 🎙 <b>Ovozli xabar</b> yuboring (mavzuni aytib bering)\n"
        "3. 📄 <b>PDF yoki Word (.docx)</b> hujjat yuboring (bot hujjatdan slayd yasaydi)\n\n"
        "Mavzuni yozing yoki fayl yuboring:"
    )
    await callback.message.edit_text(text, parse_mode="HTML")


# Ovozli xabarni qabul qilish
@router.message(F.voice, SlideCreationState.waiting_for_topic)
async def process_voice_topic(message: Message, state: FSMContext, bot: Bot):
    status_msg = await message.answer("🎙 <i>Ovozli xabar tahlil qilinmoqda...</i>", parse_mode="HTML")
    try:
        file_info = await bot.get_file(message.voice.file_id)
        voice_io = await bot.download_file(file_info.file_path)
        voice_bytes = voice_io.read()

        topic = await transcribe_voice_with_gemini(voice_bytes, mime_type="audio/ogg")
        if not topic or len(topic) < 3:
            topic = "Ovozli xabar asosida taqdimot"

        await status_msg.delete()
        await state.update_data(topic=topic, is_doc=False)
        await state.set_state(SlideCreationState.waiting_for_language)

        text = (
            f"🎙 <b>Ovozingizdan aniqlangan mavzu:</b>\n"
            f"👉 <i>{topic}</i>\n\n"
            f"Endi taqdimot <b>qaysi tilda</b> tuzilishini tanlang:"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=language_selection_keyboard())
    except Exception as e:
        logger.error(f"Ovoz yuklashda xatolik: {e}")
        await status_msg.edit_text("Ovozni o'qishda xatolik yuz berdi. Iltimos, matn ko'rinishida yozib yuboring.")


# Hujjat (PDF/Word/TXT) qabul qilish
@router.message(F.document, SlideCreationState.waiting_for_topic)
async def process_document_topic(message: Message, state: FSMContext, bot: Bot):
    doc = message.document
    filename = doc.file_name.lower()

    if not (filename.endswith(".pdf") or filename.endswith(".docx") or filename.endswith(".txt")):
        await message.answer("Iltimos, faqat PDF, Word (.docx) yoki TXT formatdagi fayl yuboring:")
        return

    status_msg = await message.answer("📄 <i>Hujjat o'qilmoqda va tahlil qilinmoqda...</i>", parse_mode="HTML")
    try:
        file_info = await bot.get_file(doc.file_id)
        file_io = await bot.download_file(file_info.file_path)
        file_bytes = file_io.read()

        extracted_text = ""
        if filename.endswith(".pdf"):
            extracted_text = extract_text_from_pdf(file_bytes)
        elif filename.endswith(".docx"):
            extracted_text = extract_text_from_docx(file_bytes)
        elif filename.endswith(".txt"):
            extracted_text = extract_text_from_txt(file_bytes)

        if not extracted_text or len(extracted_text) < 50:
            await status_msg.edit_text("Hujjat ichida yetarli matn topilmadi. Boshqa fayl yuboring.")
            return

        topic = doc.file_name.rsplit(".", 1)[0].replace("_", " ").title()
        await status_msg.delete()
        await state.update_data(topic=topic, doc_text=extracted_text, is_doc=True)
        await state.set_state(SlideCreationState.waiting_for_language)

        text = (
            f"📄 <b>Hujjat muvaffaqiyatli qabul qilindi:</b> <i>{doc.file_name}</i>\n"
            f"Matn hajmi: {len(extracted_text)} ta belgi.\n\n"
            f"Taqdimot <b>qaysi tilda</b> tuzilsin?"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=language_selection_keyboard())
    except Exception as e:
        logger.error(f"Hujjat yuklashda xatolik: {e}")
        await status_msg.edit_text("Faylni yuklashda xatolik yuz berdi. Qaytadan urinib ko'ring.")


# Matnli mavzuni qabul qilish
@router.message(SlideCreationState.waiting_for_topic)
async def process_text_topic(message: Message, state: FSMContext):
    topic = (message.text or "").strip()
    if len(topic) < 3:
        await message.answer("Iltimos, mavzuni to'liqroq yozing (kamida 3 ta harf):")
        return

    await state.update_data(topic=topic, is_doc=False)
    await state.set_state(SlideCreationState.waiting_for_language)

    text = f"📌 <b>Mavzu:</b> <i>{topic}</i>\n\nTaqdimot <b>qaysi tilda</b> tayyorlansin?"
    await message.answer(text, parse_mode="HTML", reply_markup=language_selection_keyboard())


@router.callback_query(F.data.startswith("lang_"), SlideCreationState.waiting_for_language)
async def process_language(callback: CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    lang = callback.data.split("_")[1]
    await state.update_data(language=lang)
    await state.set_state(SlideCreationState.waiting_for_slide_count)

    data = await state.get_data()
    topic = data.get("topic", "")

    text = (
        f"📌 <b>Mavzu:</b> <i>{topic}</i>\n\n"
        f"Taqdimotda <b>nechta slayd</b> bo'lishini tanlang:"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=slide_count_keyboard())


@router.callback_query(F.data.startswith("count_"), SlideCreationState.waiting_for_slide_count)
async def process_slide_count(callback: CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    count = int(callback.data.split("_")[1])
    await state.update_data(slide_count=count)
    await state.set_state(SlideCreationState.waiting_for_theme)

    data = await state.get_data()
    topic = data.get("topic", "")

    text = (
        f"📌 <b>Mavzu:</b> <i>{topic}</i>\n"
        f"📊 <b>Slaydlar:</b> {count} ta\n\n"
        f"🎨 <b>Dizayn va ranglar mavzusini tanlang:</b>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=theme_selection_keyboard())


@router.callback_query(F.data.startswith("theme_"), SlideCreationState.waiting_for_theme)
async def process_theme_and_generate(callback: CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback, "Generatsiya boshlandi...")
    theme_key = callback.data.split("theme_")[1]
    data = await state.get_data()
    topic = data.get("topic", "Taqdimot")
    slide_count = data.get("slide_count", 5)
    language = data.get("language", "uz")
    is_doc = data.get("is_doc", False)
    doc_text = data.get("doc_text", "")
    theme_info = config.THEMES.get(theme_key, config.THEMES[config.DEFAULT_THEME])

    await state.clear()

    loading_text = (
        f"⏳ <b>Taqdimot tayyorlanmoqda...</b>\n\n"
        f"📌 <b>Mavzu:</b> {topic}\n"
        f"🎨 <b>Dizayn:</b> {theme_info.emoji} {theme_info.name}\n\n"
        f"1️⃣ <i>Sun'iy intellekt orqali reja va professional matnlar tuzilmoqda...</i>"
    )
    try:
        status_msg = await callback.message.edit_text(loading_text, parse_mode="HTML")
    except Exception:
        status_msg = await callback.message.answer(loading_text, parse_mode="HTML")

    presentation_content: PresentationContent
    try:
        if is_doc and doc_text:
            presentation_content = await generate_presentation_from_document(
                doc_text=doc_text,
                slide_count=slide_count,
                language=language,
            )
        else:
            presentation_content = await generate_presentation_with_gemini(
                topic=topic,
                slide_count=slide_count,
                language=language,
            )
    except Exception as e:
        logger.error(f"Gemini generatsiyasida xatolik: {e}")
        presentation_content = generate_mock_presentation(topic, slide_count=slide_count)

    try:
        try:
            await status_msg.edit_text(
                f"⏳ <b>Taqdimot tayyorlanmoqda...</b>\n\n"
                f"📌 <b>Mavzu:</b> {topic}\n"
                f"🎨 <b>Dizayn:</b> {theme_info.emoji} {theme_info.name}\n\n"
                f"✅ <i>Kontent tayyorlandi!</i>\n"
                f"2️⃣ <i>16:9 formatda zamonaviy grafikalar va kartochkalar chizilmoqda...</i>",
                parse_mode="HTML",
            )
        except Exception:
            pass

        pptx_file_path = create_presentation_file(
            content=presentation_content,
            theme_key=theme_key,
        )

        # Foydalanuvchi limitini kamaytirish va statistikaga yozish
        user_id = callback.from_user.id
        database.use_slide(user_id, is_admin(user_id))
        database.record_presentation(user_id, topic, theme_key, len(presentation_content.slides))

        user = database.get_user(user_id)
        left = user["slides_left"] if user else 0

        caption = (
            f"🎉 <b>Taqdimotingiz muvaffaqiyatli tayyorlandi!</b>\n\n"
            f"📌 <b>Mavzu:</b> {topic}\n"
            f"📊 <b>Slaydlar:</b> {len(presentation_content.slides)} ta\n"
            f"🎨 <b>Dizayn:</b> {theme_info.emoji} {theme_info.name}\n"
            f"📁 <b>Format:</b> PowerPoint (.pptx)\n"
            f"💎 <b>Qolgan balansingiz:</b> {left} ta slayd\n\n"
            f"💡 <i>Faylni PowerPoint, Google Slides yoki WPS Office orqali to'liq ochishingiz va tahrirlashingiz mumkin.</i>"
        )

        action_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🚀 Yangi Slayd Yaratish", callback_data="btn_create_slide")],
                [InlineKeyboardButton(text="👤 Profil & Ko'proq Limit Olish", callback_data="btn_profile")],
            ]
        )

        document = FSInputFile(pptx_file_path, filename=os.path.basename(pptx_file_path))
        await callback.message.answer_document(
            document=document,
            caption=caption,
            parse_mode="HTML",
            reply_markup=action_kb,
        )
        try:
            await status_msg.delete()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Slayd chizishda xatolik: {e}")
        await callback.message.answer(
            "❌ Slayd faylini yaratishda texnik xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.",
            reply_markup=main_menu_keyboard(callback.from_user.id),
        )


# ------------------ TELEGRAMDAN BOSHQARILADIGAN ADMIN PANEL ------------------
@router.message(Command("admin"))
@router.callback_query(F.data == "btn_admin_panel")
async def cmd_admin_panel(event: Any, state: FSMContext):
    user_id = event.from_user.id
    if not is_admin(user_id):
        if isinstance(event, Message):
            await event.answer("Kechirasiz, ushbu buyruq faqat bot egasi uchun.")
        return

    await state.clear()
    if isinstance(event, CallbackQuery):
        await safe_callback_answer(event)

    stats = database.get_global_stats()
    req_chan = database.get_setting("required_channel", "O'rnatilmagan")
    init_lim = database.get_setting("initial_slides_limit", "3")
    ref_rew = database.get_setting("referral_reward", "2")

    text = (
        "👑 <b>Boshqaruv Paneli (Admin)</b>\n\n"
        f"📊 <b>Statistika:</b>\n"
        f"• Jami foydalanuvchilar: <b>{stats['total_users']}</b> ta\n"
        f"• Bugun qo'shilganlar: <b>{stats['today_users']}</b> ta\n"
        f"• Jami yaratilgan slaydlar: <b>{stats['total_presentations']}</b> ta\n"
        f"• Do'stlar orqali qo'shilganlar: <b>{stats['total_referrals']}</b> ta\n\n"
        f"⚙️ <b>Joriy Sozlamalar:</b>\n"
        f"• Majburiy kanal: <code>{req_chan or 'O''rnatilmagan'}</code>\n"
        f"• Boshlang'ich limit: <b>{init_lim} ta</b>\n"
        f"• Referal bonusi: <b>+{ref_rew} ta</b>\n\n"
        "Quyidagi tugmalar orqali sozlamalarni bevosita Telegramdan o'zgartirishingiz mumkin:"
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=admin_menu_keyboard())
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=admin_menu_keyboard())


@router.callback_query(F.data == "adm_stats")
async def cb_admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await safe_callback_answer(callback)
    stats = database.get_global_stats()
    text = (
        "📊 <b>Kengaytirilgan Statistika</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{stats['total_users']} ta</b>\n"
        f"📈 Bugun qo'shilganlar: <b>{stats['today_users']} ta</b>\n"
        f"📁 Yaratilgan jami taqdimotlar: <b>{stats['total_presentations']} ta</b>\n"
        f"📅 Bugun yaratilgan taqdimotlar: <b>{stats['today_presentations']} ta</b>\n"
        f"🔗 Referal takliflar soni: <b>{stats['total_referrals']} ta</b>\n\n"
        f"<i>Baza holati: Faol (SQLite)</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Admin menyu", callback_data="btn_admin_panel")]])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "adm_channel")
async def cb_admin_channel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await safe_callback_answer(callback)
    await state.set_state(AdminState.waiting_for_channel)
    current = database.get_setting("required_channel", "")

    text = (
        "📢 <b>Majburiy Obuna Kanalini Sozlash</b>\n\n"
        f"Joriy kanal: <code>{current or 'O''rnatilmagan (O''chiq)'}</code>\n\n"
        "Yangi kanal username'ini yuboring (masalan: <code>@mening_kanalim</code>).\n"
        "Majburiy obunani <b>o'chirib qo'yish</b> uchun <code>ochirish</code> deb yozing.\n\n"
        "<i>Eslatma: Bot ushbu kanalda admin bo'lishi kerak!</i>\n"
        "Bekor qilish uchun /cancel yozing."
    )
    await callback.message.edit_text(text, parse_mode="HTML")


@router.message(AdminState.waiting_for_channel)
async def process_set_channel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    text = (message.text or "").strip()
    if text.startswith("/cancel"):
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=admin_menu_keyboard())
        return

    if text.lower() in ("ochirish", "none", "o'chirish", "off"):
        database.set_setting("required_channel", "")
        await state.clear()
        await message.answer("✅ Majburiy obuna o'chirildi!", reply_markup=admin_menu_keyboard())
        return

    if not text.startswith("@") and not text.startswith("-100"):
        text = "@" + text

    database.set_setting("required_channel", text)
    await state.clear()
    await message.answer(f"✅ Majburiy obuna kanali <b>{text}</b> ga o'rnatildi!", parse_mode="HTML", reply_markup=admin_menu_keyboard())


@router.callback_query(F.data == "adm_limits")
async def cb_admin_limits(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await safe_callback_answer(callback)
    init_lim = database.get_setting("initial_slides_limit", "3")
    ref_rew = database.get_setting("referral_reward", "2")

    text = (
        "🎁 <b>Limit va Bonuslarni O'zgartirish</b>\n\n"
        f"1. Yangi foydalanuvchiga beriladigan slaydlar: <b>{init_lim} ta</b>\n"
        f"2. Taklif qilingan har bir do'st uchun bonus: <b>+{ref_rew} ta</b>\n\n"
        "Qaysi birini o'zgartirmoqchisiz?"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1. Boshlang'ich limitni o'zgartirish", callback_data="set_init_limit")],
            [InlineKeyboardButton(text="2. Referal bonusini o'zgartirish", callback_data="set_ref_reward")],
            [InlineKeyboardButton(text="🔙 Admin menyu", callback_data="btn_admin_panel")],
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "set_init_limit")
async def cb_set_init_limit(callback: CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    await state.set_state(AdminState.waiting_for_initial_limit)
    await callback.message.edit_text("Yangi foydalanuvchilar uchun slaydlar sonini raqamda yuboring (masalan: 5):")


@router.message(AdminState.waiting_for_initial_limit)
async def process_initial_limit(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        val = int(message.text.strip())
        database.set_setting("initial_slides_limit", str(val))
        await state.clear()
        await message.answer(f"✅ Boshlang'ich limit <b>{val} ta</b> qilib belgilandi.", parse_mode="HTML", reply_markup=admin_menu_keyboard())
    except ValueError:
        await message.answer("Iltimos, butun raqam yozing:")


@router.callback_query(F.data == "set_ref_reward")
async def cb_set_ref_reward(callback: CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    await state.set_state(AdminState.waiting_for_referral_reward)
    await callback.message.edit_text("Do'stini taklif qilgani uchun beriladigan bonus sonini yuboring (masalan: 3):")


@router.message(AdminState.waiting_for_referral_reward)
async def process_ref_reward(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        val = int(message.text.strip())
        database.set_setting("referral_reward", str(val))
        await state.clear()
        await message.answer(f"✅ Referal bonusi <b>+{val} ta</b> qilib belgilandi.", parse_mode="HTML", reply_markup=admin_menu_keyboard())
    except ValueError:
        await message.answer("Iltimos, butun raqam yozing:")


# ------------------ RASSILKA (XABAR TARQATISH) ------------------
@router.callback_query(F.data == "adm_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await safe_callback_answer(callback)
    await state.set_state(AdminState.waiting_for_broadcast_message)
    text = (
        "✉️ <b>Barcha foydalanuvchilarga xabar tarqatish (Rassilka)</b>\n\n"
        "Foydalanuvchilarga yuborilishi kerak bo'lgan xabarni yozing (matn, rasm yoki video bo'lishi mumkin).\n\n"
        "Bekor qilish uchun /cancel yozing."
    )
    await callback.message.edit_text(text, parse_mode="HTML")


@router.message(AdminState.waiting_for_broadcast_message)
async def process_broadcast(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("Rassilka bekor qilindi.", reply_markup=admin_menu_keyboard())
        return

    await state.clear()
    status_msg = await message.answer("⏳ <i>Xabarlar tarqatilmoqda, kuting...</i>", parse_mode="HTML")

    user_ids = database.get_all_user_ids()
    sent = 0
    failed = 0

    for uid in user_ids:
        try:
            await message.copy_to(chat_id=uid)
            sent += 1
            await asyncio.sleep(0.05)  # Telegram flood limitiga tushmaslik uchun
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ <b>Rassilka yakunlandi!</b>\n\n"
        f"• Yetkazildi: <b>{sent} ta</b>\n"
        f"• Yetkazilmadi (bloklangan): <b>{failed} ta</b>",
        parse_mode="HTML",
        reply_markup=admin_menu_keyboard(),
    )


@router.message(Command("addlimit"))
async def cmd_add_limit(message: Message):
    """Admin buyrug'i: /addlimit 12345678 10"""
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("Format: <code>/addlimit USER_ID SONI</code>\nMasalan: <code>/addlimit 12345678 5</code>", parse_mode="HTML")
        return
    try:
        target_uid = int(parts[1])
        add_count = int(parts[2])
        database.add_slides_to_user(target_uid, add_count)
        await message.answer(f"✅ Foydalanuvchi <code>{target_uid}</code> ga <b>+{add_count} ta slayd</b> qo'shildi!", parse_mode="HTML")
    except ValueError:
        await message.answer("ID va Soni butun son bo'lishi kerak!")


@router.message(Command("myid"))
async def cmd_myid(message: Message):
    await message.answer(f"Sizning Telegram ID raqamingiz: <code>{message.from_user.id}</code>", parse_mode="HTML")


@router.callback_query(F.data == "btn_themes")
async def cb_themes_gallery(callback: CallbackQuery):
    await safe_callback_answer(callback)
    text = (
        "🎨 <b>Mavjud Professional Dizayn Mavzulari:</b>\n\n"
        "🌙 <b>Dark Tech:</b> To'q kulrang/qora fon, neon moviy va indigo elementlar. IT, startaplar va zamonaviy texnologiyalar uchun ideal.\n\n"
        "💼 <b>Corporate Blue:</b> Klassik oppoq fon, qirollik ko'k va moviy ranglar. Biznes, moliya va rasmiy taqdimotlar uchun.\n\n"
        "🌿 <b>Emerald Green:</b> To'q zumrad fon, yorqin yashil elementlar. Ekologiya, ta'lim, sog'liqni saqlash va o'sish mavzulari uchun.\n\n"
        "🌅 <b>Modern Sunset:</b> To'q zamonaviy fon, jozibali koral va to'q sariq aksentlar. Marketing va ijodiy taqdimotlar uchun.\n\n"
        "⚪ <b>Clean Minimal:</b> Qoramtir matnlar va binafsharang urg'ular bilan toza oppoq minimalist dizayn."
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Slayd Yaratish", callback_data="btn_create_slide")],
            [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="btn_cancel")],
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "btn_help")
async def cb_help(callback: CallbackQuery):
    await safe_callback_answer(callback)
    text = (
        "ℹ️ <b>Slayd Yaratuvchi Bot Haqida</b>\n\n"
        "Ushbu bot eng ilg'or sun'iy intellekt texnologiyalari asosida ishlaydi "
        "va professional darajadagi taqdimotlarni bir necha soniyada tayyorlab beradi.\n\n"
        "<b>Imkoniyatlar:</b>\n"
        "• 16:9 Widescreen zamonaviy taqdimotlar\n"
        "• Matn, 🎙 Ovozli xabar yoki 📄 PDF/Word fayllardan slayd yasash\n"
        "• Avtomatik vizual modullar: kartochkalar, infografika, raqamlar, solishtirish jadvallari, timeline bosqichlari\n"
        "• 3 ta tilda yaratish (O'zbekcha, Ruscha, Inglizcha)\n"
        "• Do'stlarni taklif qilib qo'shimcha bepul limitlar olish\n\n"
        "Boshlash uchun pastdagi tugmani bosing:"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Slayd Yaratish", callback_data="btn_create_slide")],
            [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="btn_cancel")],
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


async def handle_ping(request):
    return web.Response(text="Gemini Slide Bot is running 24/7!")


async def start_web_server():
    """Render.com bepul Web Service rejimida portni tinglash uchun yengil server."""
    try:
        port = int(os.getenv("PORT", 8080))
        app = web.Application()
        app.router.add_get("/", handle_ping)
        app.router.add_get("/health", handle_ping)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Web server {port}-portda muvaffaqiyatli ishga tushdi.")
    except Exception as e:
        logger.warning(f"Web server ogohlantirish (lokal muhitda bu normal): {e}")


async def main():
    token = config.BOT_TOKEN
    if not token or "QOYING" in token:
        logger.warning("⚠️ DIQQAT: BOT_TOKEN .env faylida to'g'ri o'rnatilmagan!")
        return

    # Render buluti uchun web serverni yoqish
    await start_web_server()

    bot = Bot(token=token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logger.info("Bot 24/7 rejimida muvaffaqiyatli ishga tushdi...")

    while True:
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        except (KeyboardInterrupt, SystemExit):
            break
        except Exception as e:
            logger.error(f"Ulanishda xatolik: {e}. 5 soniyadan so'ng qayta ulanadi...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
