import asyncio
import json
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
    InputMediaPhoto,
    LabeledPrice,
    PreCheckoutQuery,
    WebAppInfo,
)
from aiohttp import web

import config
import database
from document_service import (
    extract_text_from_pdf,
    extract_text_from_docx,
    extract_text_from_txt,
    transcribe_voice_with_gemini,
    extract_text_and_topic_from_image,
)
from gemini_service import (
    generate_presentation_with_gemini,
    generate_presentation_from_document,
    generate_mock_presentation,
    translate_presentation_content,
    tweak_single_slide,
    PresentationContent,
    SlideContent,
)
from slide_designer import (
    create_presentation_file,
    generate_speaker_speech_file,
    generate_slide_preview_image,
    generate_all_slides_preview_images,
    render_slide_to_image,
    generate_themes_showcase_image,
    convert_pptx_to_pdf,
)

# Logging
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


def get_themes_showcase_path() -> str:
    """Showcase rasmini topadi (assets yoki root papkada) yoki dinamik generatsiya qiladi."""
    assets_p = os.path.join(config.ASSETS_DIR, "themes_showcase.png")
    if os.path.exists(assets_p) and os.path.getsize(assets_p) > 10000:
        return assets_p
    root_p = os.path.join(os.path.dirname(__file__), "themes_showcase.png")
    if os.path.exists(root_p) and os.path.getsize(root_p) > 10000:
        return root_p
    return generate_themes_showcase_image()


# FSM Holatlari
class SlideCreationState(StatesGroup):
    waiting_for_mode = State()
    waiting_for_topic = State()
    waiting_for_author = State()
    waiting_for_logo = State()
    waiting_for_language = State()
    waiting_for_slide_count = State()
    waiting_for_custom_slide_count = State()
    waiting_for_theme = State()
    waiting_for_speech_choice = State()


class SlideEditState(StatesGroup):
    waiting_for_slide_choice = State()
    waiting_for_instruction = State()


class UserPromoState(StatesGroup):
    waiting_for_promo = State()


class AdminState(StatesGroup):
    waiting_for_channel = State()
    waiting_for_initial_limit = State()
    waiting_for_referral_reward = State()
    waiting_for_broadcast_message = State()
    waiting_for_give_limit = State()
    waiting_for_new_admin = State()
    waiting_for_create_promo = State()
    waiting_for_payment_info = State()


def is_admin(user_id: int) -> bool:
    """Foydalanuvchi asosiy yoki 2-admin ekanligini tekshiradi."""
    return database.is_user_admin(user_id, config.ADMIN_ID)


async def safe_callback_answer(callback: CallbackQuery, text: str = None, show_alert: bool = False):
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except Exception:
        pass


async def safe_edit_or_answer(
    message: Message,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True,
) -> Message:
    """Xabar matn bo'lsa uni tahrirlaydi, hujjat/media yoki eskirgan bo'lsa yangi xabar yuboradi."""
    try:
        if message.text is not None:
            return await message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
            )
    except Exception:
        pass
    return await message.answer(
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
        disable_web_page_preview=disable_web_page_preview,
    )


async def check_channel_subscription(bot: Bot, user_id: int) -> Tuple[bool, str]:
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
        return True, channel


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
        [InlineKeyboardButton(text="📱 Web App orqali yaratish (Interaktiv)", web_app=WebAppInfo(url=config.WEBAPP_URL))],
        [
            InlineKeyboardButton(text="📁 Mening Taqdimotlarim", callback_data="btn_my_presentations"),
            InlineKeyboardButton(text="💎 Tariflar & To'lov", callback_data="btn_tariffs"),
        ],
        [
            InlineKeyboardButton(text="👤 Profil & Referal", callback_data="btn_profile"),
            InlineKeyboardButton(text="🎁 Kunlik Bonus (+1)", callback_data="btn_daily_bonus"),
        ],
        [
            InlineKeyboardButton(text="🎟 Promokod", callback_data="btn_enter_promo"),
            InlineKeyboardButton(text="🎨 Mavzular Ko'rgazmasi", callback_data="btn_themes"),
        ],
        [
            InlineKeyboardButton(text="ℹ️ Bot Haqida", callback_data="btn_help"),
        ],
    ]
    if is_admin(user_id):
        buttons.append([InlineKeyboardButton(text="👑 Admin Paneli", callback_data="btn_admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def mode_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎓 Darslik / Referat", callback_data="mode_education"),
                InlineKeyboardButton(text="💼 Biznes / Pitch Deck", callback_data="mode_business"),
            ],
            [
                InlineKeyboardButton(text="📊 Tahliliy hisobot", callback_data="mode_analytics"),
                InlineKeyboardButton(text="🚀 Erkin & Kreativ", callback_data="mode_general"),
            ],
            [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="btn_cancel")],
        ]
    )


def author_skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏩ O'tkazib yuborish (Muallifsiz)", callback_data="author_skip")],
            [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="btn_cancel")],
        ]
    )


def logo_skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏩ O'tkazib yuborish (Logotipsiz)", callback_data="logo_skip")],
            [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="btn_cancel")],
        ]
    )


def translate_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇿 O'zbek tiliga", callback_data="trans_to_uz"),
                InlineKeyboardButton(text="🇷🇺 Rus tiliga", callback_data="trans_to_ru"),
                InlineKeyboardButton(text="🇬🇧 Ingliz tiliga", callback_data="trans_to_en"),
            ],
            [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="btn_cancel")],
        ]
    )


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
                InlineKeyboardButton(text="5 ta (Ekspress)", callback_data="count_5"),
                InlineKeyboardButton(text="8 ta (Standart)", callback_data="count_8"),
            ],
            [
                InlineKeyboardButton(text="12 ta (Kengaytirilgan)", callback_data="count_12"),
                InlineKeyboardButton(text="15 ta (Katta)", callback_data="count_15"),
            ],
            [
                InlineKeyboardButton(text="20 ta (Diplom / Loyiha)", callback_data="count_20"),
                InlineKeyboardButton(text="✍️ Boshqa son kiritish", callback_data="count_custom"),
            ],
            [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="btn_cancel")],
        ]
    )


def theme_selection_keyboard(prefix: str = "theme_") -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for key, th in config.THEMES.items():
        btn = InlineKeyboardButton(text=f"{th.emoji} {th.name}", callback_data=f"{prefix}{key}")
        row.append(btn)
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="btn_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def speech_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎤 Ha, nutq matni kerak", callback_data="speech_yes"),
            ],
            [
                InlineKeyboardButton(text="⚡️ Yo'q, faqat slaydlar yetarli", callback_data="speech_no"),
            ],
            [
                InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="btn_cancel"),
            ],
        ]
    )


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Jonli Statistika", callback_data="adm_stats"),
                InlineKeyboardButton(text="📢 Majburiy Kanal", callback_data="adm_channel"),
            ],
            [
                InlineKeyboardButton(text="👥 Adminlar Boshqaruvi", callback_data="adm_admins"),
                InlineKeyboardButton(text="🎁 Foydalanuvchiga Limit Berish", callback_data="adm_give_limit"),
            ],
            [
                InlineKeyboardButton(text="🎟 Promokod Yaratish", callback_data="adm_create_promo"),
                InlineKeyboardButton(text="⚙️ Standart Limit & Bonus", callback_data="adm_limits"),
            ],
            [
                InlineKeyboardButton(text="💳 Karta & To'lov Matni", callback_data="adm_payment_info"),
                InlineKeyboardButton(text="✉️ Rassilka (Xabar tarqatish)", callback_data="adm_broadcast"),
            ],
            [
                InlineKeyboardButton(text="📢 Qayta Jalb Qilish (Retargeting)", callback_data="adm_retargeting"),
            ],
            [InlineKeyboardButton(text="🔙 Bosh Menyu", callback_data="btn_cancel")],
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject, bot: Bot):
    await state.clear()
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Foydalanuvchi"
    username = message.from_user.username or ""

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

    if rewarded_ref:
        try:
            await bot.send_message(
                chat_id=rewarded_ref,
                text=(
                    f"🎉 <b>Ajoyib yangilik!</b>\n\n"
                    f"Sizning referal havolangiz orqali yangi do'stingiz (<b>{first_name}</b>) botga qo'shildi!\n"
                    f"🎁 Hisobingizga <b>+{reward_amount} ta bepul slayd</b> taqdim etildi."
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass

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

    vip_badge = " [VIP CHEKSIZ]" if user_dict.get("is_vip") else ""
    balance_text = "Cheksiz (VIP)" if user_dict.get("is_vip") else f"{user_dict['slides_left']} ta"

    text = (
        f"Assalomu alaykum, <b>{first_name}</b>{vip_badge}!\n\n"
        f"Men <b>Professional Slayd Yaratuvchi (@SlaydchiAkabot)</b> botman.\n"
        f"Siz menga ixtiyoriy <b>mavzu</b>, <b>PDF/Word hujjati</b>, <b>rasm/konspekt</b> yoki <b>ovozli xabar</b> yuboring — "
        f"men 16:9 formatdagi PowerPoint taqdimot va uning <b>spiker nutqi matnini</b> tayyorlab beraman.\n\n"
        f"📊 <b>Sizning balansingiz:</b> <b>{balance_text}</b>\n\n"
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
        bal = "Cheksiz (VIP)" if (user and user.get("is_vip")) else f"{user['slides_left']} ta"
        text = (
            f"✅ <b>Obuna muvaffaqiyatli tasdiqlandi!</b>\n\n"
            f"📊 <b>Sizning balansingiz:</b> {bal}\n\n"
            f"Slayd yaratish uchun quyidagi tugmani bosing:"
        )
        await safe_edit_or_answer(callback.message, text, reply_markup=main_menu_keyboard(user_id))
    else:
        await safe_callback_answer(callback, "Siz hali kanalga a'zo bo'lmadingiz!", show_alert=True)


@router.callback_query(F.data == "btn_cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_callback_answer(callback)
    await safe_edit_or_answer(callback.message, "Amal bekor qilindi.", reply_markup=main_menu_keyboard(callback.from_user.id))


# ------------------ PROFIL VA REFERAL ------------------
@router.callback_query(F.data == "btn_profile")
async def cb_profile(callback: CallbackQuery, bot: Bot):
    await safe_callback_answer(callback)
    user_id = callback.from_user.id
    user = database.get_user(user_id)
    if not user:
        user = {"slides_left": 3, "referrals_count": 0, "is_vip": 0}

    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    reward = database.get_setting("referral_reward", "2")
    status_text = "💎 VIP Cheksiz" if user.get("is_vip") else f"<b>{user['slides_left']} ta</b>"

    text = (
        f"👤 <b>Sizning Profilingiz</b>\n\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"💎 <b>Status:</b> {status_text}\n"
        f"👥 <b>Taklif qilingan do'stlar:</b> <b>{user['referrals_count']} ta</b>\n\n"
        f"🎁 <b>Referal Dasturi:</b>\n"
        f"Do'stlaringizni taklif qiling va har bir do'stingiz uchun <b>+{reward} ta bepul slayd</b> oling!\n\n"
        f"🔗 <b>Sizning taklif havolangiz:</b>\n"
        f"<code>{ref_link}</code>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↗️ Do'stlarga ulashish",
                    url=f"https://t.me/share/url?url={ref_link}&text=Sun'iy%20intellektda%20bepul%20slaydlar%20yasang!",
                )
            ],
            [
                InlineKeyboardButton(text="🎟 Promokod kiritish", callback_data="btn_enter_promo"),
                InlineKeyboardButton(text="💎 Tariflar", callback_data="btn_tariffs"),
            ],
            [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="btn_cancel")],
        ]
    )
    await safe_edit_or_answer(callback.message, text, reply_markup=kb, disable_web_page_preview=True)


# ------------------ PROMOKOD ISHLATISH ------------------
@router.callback_query(F.data == "btn_enter_promo")
async def cb_prompt_promo(callback: CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    await state.set_state(UserPromoState.waiting_for_promo)
    text = (
        "🎟 <b>Promokodni kiriting:</b>\n\n"
        "Kanallarda e'lon qilingan maxsus kodni yozib yuboring:\n\n"
        "Bekor qilish uchun /cancel yozing."
    )
    await callback.message.edit_text(text, parse_mode="HTML")


@router.message(UserPromoState.waiting_for_promo)
async def process_user_promo(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text.startswith("/cancel"):
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=main_menu_keyboard(message.from_user.id))
        return

    success, msg, bonus = database.use_promocode(message.from_user.id, text)
    await state.clear()
    await message.answer(msg, reply_markup=main_menu_keyboard(message.from_user.id))


# ------------------ TARIFLAR VA TO'LOV (STARS VA KARTA) ------------------
@router.callback_query(F.data == "btn_tariffs")
async def cb_tariffs(callback: CallbackQuery):
    await safe_callback_answer(callback)
    payment_info = database.get_formatted_payment_info()

    text = (
        "💎 <b>Qo'shimcha Slaydlar Uchun Tariflar</b>\n\n"
        "⭐️ <b>Telegram Stars orqali tezkor to'lov (1 soniyada avtomatik faollashadi):</b>\n"
        "• <b>10 ta slayd paketi</b> — ⭐ 50 Stars\n"
        "• <b>30 ta slayd paketi</b> — ⭐ 120 Stars\n"
        "• <b>Cheksiz VIP (1 oy)</b> — ⭐ 250 Stars\n\n"
        "━━━━━━━━━━━━━━\n"
        "💳 <b>Karta orqali to'lov (Click & Payme):</b>\n"
        "• 10 ta slayd — <b>9 000 so'm</b>\n"
        "• 30 ta slayd — <b>19 000 so'm</b>\n"
        "• Cheksiz VIP — <b>39 000 so'm</b>\n\n"
        f"{payment_info}\n\n"
        "<i>To'lov qilgach, chek yoki skrinshotni adminga yuboring, hisobingiz 1 daqiqa ichida to'ldiriladi!</i>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐ 10 Slayd (50 Stars)", callback_data="buy_stars_10"),
                InlineKeyboardButton(text="⭐ 30 Slayd (120 Stars)", callback_data="buy_stars_30"),
            ],
            [
                InlineKeyboardButton(text="👑 Cheksiz VIP (250 Stars)", callback_data="buy_stars_vip"),
            ],
            [
                InlineKeyboardButton(text="🎟 Promokod kiritish", callback_data="btn_enter_promo"),
                InlineKeyboardButton(text="🚀 Slayd Yaratish", callback_data="btn_create_slide"),
            ],
            [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="btn_cancel")],
        ]
    )
    await safe_edit_or_answer(callback.message, text, reply_markup=kb)


@router.callback_query(F.data == "buy_stars_10")
async def cb_buy_stars_10(callback: CallbackQuery):
    await safe_callback_answer(callback)
    prices = [LabeledPrice(label="10 ta Slayd", amount=50)]
    await callback.message.answer_invoice(
        title="⭐ 10 ta Slayd Paketi",
        description="Sun'iy intellektda 10 ta professional taqdimot yaratish uchun slaydlar paketi",
        payload="stars_pack_10",
        currency="XTR",
        prices=prices,
        provider_token="",
    )


@router.callback_query(F.data == "buy_stars_30")
async def cb_buy_stars_30(callback: CallbackQuery):
    await safe_callback_answer(callback)
    prices = [LabeledPrice(label="30 ta Slayd", amount=120)]
    await callback.message.answer_invoice(
        title="⭐ 30 ta Slayd Paketi (Mashhur)",
        description="Sun'iy intellektda 30 ta professional taqdimot yaratish uchun slaydlar paketi",
        payload="stars_pack_30",
        currency="XTR",
        prices=prices,
        provider_token="",
    )


@router.callback_query(F.data == "buy_stars_vip")
async def cb_buy_stars_vip(callback: CallbackQuery):
    await safe_callback_answer(callback)
    prices = [LabeledPrice(label="VIP Cheksiz (1 oy)", amount=250)]
    await callback.message.answer_invoice(
        title="👑 Cheksiz VIP Status (1 oy)",
        description="1 oy davomida xohlagancha cheksiz taqdimotlar va spiker nutqlarini yaratish",
        payload="stars_pack_vip",
        currency="XTR",
        prices=prices,
        provider_token="",
    )


@router.pre_checkout_query()
async def process_pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    sp = message.successful_payment
    payload = sp.invoice_payload
    user_id = message.from_user.id

    if payload == "stars_pack_10":
        database.add_slides_to_user(user_id, 10)
        await message.answer(
            "🎉 <b>To'lov muvaffaqiyatli qabul qilindi!</b>\n\n"
            "Hisobingizga <b>+10 ta bepul slayd</b> qo'shildi. Rahmat!\n\n"
            "Endi yangi taqdimot yaratishingiz mumkin:",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(user_id),
        )
    elif payload == "stars_pack_30":
        database.add_slides_to_user(user_id, 30)
        await message.answer(
            "🎉 <b>To'lov muvaffaqiyatli qabul qilindi!</b>\n\n"
            "Hisobingizga <b>+30 ta bepul slayd</b> qo'shildi. Rahmat!\n\n"
            "Endi yangi taqdimot yaratishingiz mumkin:",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(user_id),
        )
    elif payload == "stars_pack_vip":
        database.set_user_vip(user_id, True)
        await message.answer(
            "👑 <b>Tabriklaymiz! Sizga Cheksiz VIP status berildi!</b>\n\n"
            "Endi hech qanday limitsiz, xohlagancha professional slaydlar yarata olasiz!",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(user_id),
        )


# ------------------ SLAYD YARATISH OQIMI ------------------
@router.callback_query(F.data == "btn_create_slide")
async def cb_start_create(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await safe_callback_answer(callback)
    user_id = callback.from_user.id

    is_subbed, channel = await check_channel_subscription(bot, user_id)
    if not is_subbed:
        await safe_edit_or_answer(
            callback.message,
            f"⚠️ Slayd yaratish uchun avval rasmiy kanalimizga a'zo bo'ling:\n👉 <b>{channel}</b>",
            reply_markup=channel_sub_keyboard(channel),
        )
        return

    if not database.has_slides_left(user_id, is_admin(user_id)):
        reward = database.get_setting("referral_reward", "2")
        bot_info = await bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
        text = (
            f"⚠️ <b>Sizning bepul slaydlar limitingiz tugadi!</b>\n\n"
            f"🎁 <b>Har kuni bepul bonus:</b> Bosh menyudagi «🎁 Kunlik Bonus» tugmasini bosing!\n"
            f"👥 Yoki do'stlaringizni taklif qilib, har biri uchun <b>+{reward} ta bepul slayd</b> oling:\n"
            f"<code>{ref_link}</code>\n\n"
            f"Yoki 💎 <b>Tariflar</b> bo'limidan qulay paket sotib oling."
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🎁 Kunlik Bonus (+1)", callback_data="btn_daily_bonus")],
                [InlineKeyboardButton(text="💎 Tariflar & To'lov", callback_data="btn_tariffs")],
                [InlineKeyboardButton(text="🎟 Promokod kiritish", callback_data="btn_enter_promo")],
                [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="btn_cancel")],
            ]
        )
        await safe_edit_or_answer(callback.message, text, reply_markup=kb, disable_web_page_preview=True)
        return

    await state.set_state(SlideCreationState.waiting_for_mode)
    text = (
        "🎯 <b>Taqdimot yo'nalishini (formatini) tanlang:</b>\n\n"
        "Sun'iy intellekt taqdimot rejasini va mazmunini qaysi uslubda tuzsin?"
    )
    await safe_edit_or_answer(callback.message, text, reply_markup=mode_selection_keyboard())


@router.callback_query(F.data.startswith("mode_"), SlideCreationState.waiting_for_mode)
async def process_mode_selected(callback: CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    mode = callback.data.split("mode_")[1]
    await state.update_data(mode=mode)
    await state.set_state(SlideCreationState.waiting_for_topic)

    mode_names = {
        "education": "🎓 Darslik / Referat / Ilmiy ish",
        "business": "💼 Biznes / Pitch Deck / Startap",
        "analytics": "📊 Tahliliy hisobot / SWOT / Tadqiqot",
        "general": "🚀 Erkin & Kreativ taqdimot",
    }
    mode_title = mode_names.get(mode, "Erkin taqdimot")

    text = (
        f"🎯 <b>Tanlangan yo'nalish:</b> {mode_title}\n\n"
        "✍️ <b>Endi taqdimot mavzusini kiriting:</b>\n\n"
        "<i>3 xil usulda berishingiz mumkin:</i>\n"
        "1. Mavzuni yozing (masalan: <i>'Sun'iy intellekt kelajagi'</i>)\n"
        "2. 🎙 <b>Ovozli xabar</b> yuboring\n"
        "3. 📄 <b>PDF yoki Word (.docx)</b> hujjat yuboring\n\n"
        "Mavzuni yozing yoki fayl tashlang:"
    )
    await safe_edit_or_answer(callback.message, text)


@router.message(F.voice, SlideCreationState.waiting_for_topic)
async def process_voice_topic(message: Message, state: FSMContext, bot: Bot):
    status_msg = await message.answer("🎙 <i>Ovoz tahlil qilinmoqda...</i>", parse_mode="HTML")
    try:
        file_info = await bot.get_file(message.voice.file_id)
        voice_io = await bot.download_file(file_info.file_path)
        voice_bytes = voice_io.read()

        topic = await transcribe_voice_with_gemini(voice_bytes, mime_type="audio/ogg")
        if not topic or len(topic) < 3:
            topic = "Ovozli xabar asosida taqdimot"

        await status_msg.delete()
        await state.update_data(topic=topic, is_doc=False)
        await state.set_state(SlideCreationState.waiting_for_author)

        text = (
            f"🎙 <b>Aniqlangan mavzu:</b> <i>{topic}</i>\n\n"
            "✍️ <b>Slaydlar tagida muallif (tayyorlovchi) nomi chiqsinmi?</b>\n"
            "<i>Masalan:</i> <code>Alisher Navoiy</code> yoki <code>Toshkent Davlat Universiteti</code>\n\n"
            "Ismingizni yozing yoki o'tkazib yuboring:"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=author_skip_keyboard())
    except Exception as e:
        logger.error(f"Ovozda xatolik: {e}")
        await status_msg.edit_text("Ovozni o'qishda xatolik yuz berdi. Matn ko'rinishida yozib yuboring.")


@router.message(F.document, SlideCreationState.waiting_for_topic)
async def process_document_topic(message: Message, state: FSMContext, bot: Bot):
    doc = message.document
    filename = doc.file_name.lower()

    if not (filename.endswith(".pdf") or filename.endswith(".docx") or filename.endswith(".txt")):
        await message.answer("Iltimos, faqat PDF, Word (.docx) yoki TXT formatdagi fayl yuboring:")
        return

    status_msg = await message.answer("📄 <i>Hujjat tahlil qilinmoqda...</i>", parse_mode="HTML")
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
        await state.set_state(SlideCreationState.waiting_for_author)

        text = (
            f"📄 <b>Hujjat qabul qilindi:</b> <i>{doc.file_name}</i>\n\n"
            "✍️ <b>Slaydlar tagida muallif (tayyorlovchi) nomi chiqsinmi?</b>\n"
            "<i>Masalan:</i> <code>Alisher Navoiy</code> yoki <code>Toshkent Davlat Universiteti</code>\n\n"
            "Ismingizni yozing yoki o'tkazib yuboring:"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=author_skip_keyboard())
    except Exception as e:
        logger.error(f"Faylda xatolik: {e}")
        await status_msg.edit_text("Faylni yuklashda xatolik yuz berdi. Qaytadan urinib ko'ring.")


@router.message(F.photo, SlideCreationState.waiting_for_topic)
async def process_photo_topic(message: Message, state: FSMContext, bot: Bot):
    photo = message.photo[-1]
    status_msg = await message.answer("📸 <i>Kitob/konspekt rasmi tahlil qilinmoqda (matnlar o'qilmoqda)...</i>", parse_mode="HTML")
    try:
        file_info = await bot.get_file(photo.file_id)
        photo_io = await bot.download_file(file_info.file_path)
        photo_bytes = photo_io.read()

        topic, doc_text = await extract_text_and_topic_from_image(photo_bytes, mime_type="image/jpeg")
        if not doc_text or len(doc_text) < 25:
            await status_msg.edit_text("Rasmdagi matnlar aniq ko'rinmadi. Iltimos, sifatliroq rasm yuboring yoki mavzuni yozib yuboring.")
            return

        await status_msg.delete()
        await state.update_data(topic=topic, doc_text=doc_text, is_doc=True)
        await state.set_state(SlideCreationState.waiting_for_author)

        text = (
            f"📸 <b>Rasmdan aniqlangan mavzu:</b> <i>{topic}</i>\n"
            f"📝 <b>O'qilgan konspekt:</b> <i>{doc_text[:140]}...</i>\n\n"
            "✍️ <b>Slaydlar tagida muallif (tayyorlovchi) nomi chiqsinmi?</b>\n"
            "<i>Masalan:</i> <code>Alisher Navoiy</code> yoki <code>Toshkent Davlat Universiteti</code>\n\n"
            "Ismingizni yozing yoki o'tkazib yuboring:"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=author_skip_keyboard())
    except Exception as e:
        logger.error(f"Rasmni o'qishda xatolik: {e}")
        await status_msg.edit_text("Rasmni tahlil qilishda xatolik yuz berdi. Qaytadan urinib ko'ring.")


@router.message(SlideCreationState.waiting_for_topic)
async def process_text_topic(message: Message, state: FSMContext):
    topic = (message.text or "").strip()
    if len(topic) < 3:
        await message.answer("Iltimos, mavzuni to'liqroq yozing (kamida 3 ta harf):")
        return

    await state.update_data(topic=topic, is_doc=False)
    await state.set_state(SlideCreationState.waiting_for_author)

    text = (
        f"📌 <b>Mavzu:</b> <i>{topic}</i>\n\n"
        "✍️ <b>Slaydlar tagida muallif (tayyorlovchi) nomi chiqsinmi?</b>\n"
        "<i>Masalan:</i> <code>Alisher Navoiy</code> yoki <code>Toshkent Davlat Universiteti</code>\n\n"
        "Ismingizni yozing yoki o'tkazib yuboring:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=author_skip_keyboard())


@router.message(SlideCreationState.waiting_for_author)
async def process_author_text(message: Message, state: FSMContext):
    author = (message.text or "").strip()[:60]
    await state.update_data(author_name=author)
    await state.set_state(SlideCreationState.waiting_for_logo)

    data = await state.get_data()
    topic = data.get("topic", "")
    text = (
        f"📌 <b>Mavzu:</b> <i>{topic}</i>\n"
        f"✍️ <b>Muallif:</b> <i>{author}</i>\n\n"
        "🏢 <b>Tashkilot, universitet yoki brend logotipi bormi?</b>\n\n"
        "Slaydlarning yuqori o'ng burchagiga logotipingizni joylashtirishimiz mumkin.\n\n"
        "Logotip rasmini (PNG / JPG) yuboring yoki o'tkazib yuboring:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=logo_skip_keyboard())


@router.callback_query(F.data == "author_skip", SlideCreationState.waiting_for_author)
async def process_author_skip(callback: CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    await state.update_data(author_name="")
    await state.set_state(SlideCreationState.waiting_for_logo)

    data = await state.get_data()
    topic = data.get("topic", "")
    text = (
        f"📌 <b>Mavzu:</b> <i>{topic}</i>\n\n"
        "🏢 <b>Tashkilot, universitet yoki brend logotipi bormi?</b>\n\n"
        "Slaydlarning yuqori o'ng burchagiga logotipingizni joylashtirishimiz mumkin.\n\n"
        "Logotip rasmini (PNG / JPG) yuboring yoki o'tkazib yuboring:"
    )
    await safe_edit_or_answer(callback.message, text, reply_markup=logo_skip_keyboard())


@router.message(F.photo, SlideCreationState.waiting_for_logo)
async def process_logo_photo(message: Message, state: FSMContext, bot: Bot):
    photo = message.photo[-1]
    os.makedirs(config.GENERATED_DIR, exist_ok=True)
    logo_path = os.path.join(config.GENERATED_DIR, f"logo_{message.from_user.id}.png")
    try:
        file_info = await bot.get_file(photo.file_id)
        await bot.download_file(file_info.file_path, destination=logo_path)
        await state.update_data(logo_path=logo_path)
    except Exception as e:
        logger.warning(f"Logotip yuklashda xatolik: {e}")
        await state.update_data(logo_path=None)

    await state.set_state(SlideCreationState.waiting_for_language)
    data = await state.get_data()
    topic = data.get("topic", "")
    text = f"✅ <b>Logotip muvaffaqiyatli saqlandi!</b>\n\n📌 <b>Mavzu:</b> <i>{topic}</i>\n\nTaqdimot <b>qaysi tilda</b> tayyorlansin?"
    await message.answer(text, parse_mode="HTML", reply_markup=language_selection_keyboard())


@router.callback_query(F.data == "logo_skip", SlideCreationState.waiting_for_logo)
async def process_logo_skip(callback: CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    await state.update_data(logo_path=None)
    await state.set_state(SlideCreationState.waiting_for_language)

    data = await state.get_data()
    topic = data.get("topic", "")
    text = f"📌 <b>Mavzu:</b> <i>{topic}</i>\n\nTaqdimot <b>qaysi tilda</b> tayyorlansin?"
    await safe_edit_or_answer(callback.message, text, reply_markup=language_selection_keyboard())


@router.message(SlideCreationState.waiting_for_logo)
async def process_logo_text_fallback(message: Message, state: FSMContext):
    await state.update_data(logo_path=None)
    await state.set_state(SlideCreationState.waiting_for_language)
    data = await state.get_data()
    topic = data.get("topic", "")
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

    text = f"📌 <b>Mavzu:</b> <i>{topic}</i>\n\nTaqdimotda <b>nechta slayd</b> bo'lishini tanlang:"
    await safe_edit_or_answer(callback.message, text, reply_markup=slide_count_keyboard())


@router.callback_query(F.data == "count_custom", SlideCreationState.waiting_for_slide_count)
async def process_custom_count_prompt(callback: CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    await state.set_state(SlideCreationState.waiting_for_custom_slide_count)
    await safe_edit_or_answer(callback.message, "Nechta slayd kerakligini raqamda yozing (1 dan 25 gacha):")


@router.message(SlideCreationState.waiting_for_custom_slide_count)
async def process_custom_count_input(message: Message, state: FSMContext):
    try:
        count = int(message.text.strip())
        if not (1 <= count <= 25):
            await message.answer("Iltimos, 1 dan 25 gacha bo'lgan son yozing:")
            return
    except ValueError:
        await message.answer("Faqat butun son kiriting:")
        return

    await state.update_data(slide_count=count)
    await state.set_state(SlideCreationState.waiting_for_theme)

    data = await state.get_data()
    topic = data.get("topic", "")

    showcase_path = get_themes_showcase_path()

    photo = FSInputFile(showcase_path)
    caption = (
        f"🎨 <b>Mavjud 10 xil Professional Shablonlar</b> (Yuqoridagi namunalar)\n\n"
        f"📌 <b>Mavzu:</b> <i>{topic}</i>\n"
        f"📊 <b>Slaydlar soni:</b> {count} ta\n\n"
        f"O'zingizga ma'qul dizayn tugmasini bosing:"
    )
    await message.answer_photo(
        photo=photo,
        caption=caption,
        parse_mode="HTML",
        reply_markup=theme_selection_keyboard(),
    )


@router.callback_query(F.data.startswith("count_"), SlideCreationState.waiting_for_slide_count)
async def process_slide_count(callback: CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    count = int(callback.data.split("_")[1])
    await state.update_data(slide_count=count)
    await state.set_state(SlideCreationState.waiting_for_theme)

    data = await state.get_data()
    topic = data.get("topic", "")

    showcase_path = get_themes_showcase_path()

    try:
        await callback.message.delete()
    except Exception:
        pass

    photo = FSInputFile(showcase_path)
    caption = (
        f"🎨 <b>Mavjud 10 xil Professional Shablonlar</b> (Yuqoridagi namunalar)\n\n"
        f"📌 <b>Mavzu:</b> <i>{topic}</i>\n"
        f"📊 <b>Slaydlar soni:</b> {count} ta\n\n"
        f"O'zingizga ma'qul dizayn tugmasini bosing:"
    )
    await callback.message.answer_photo(
        photo=photo,
        caption=caption,
        parse_mode="HTML",
        reply_markup=theme_selection_keyboard(),
    )


@router.callback_query(F.data.startswith("theme_"), SlideCreationState.waiting_for_theme)
async def process_theme_selected(callback: CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    theme_key = callback.data.split("theme_")[1]
    await state.update_data(theme_key=theme_key)
    await state.set_state(SlideCreationState.waiting_for_speech_choice)

    data = await state.get_data()
    topic = data.get("topic", "")
    slide_count = data.get("slide_count", 5)
    theme_info = config.THEMES.get(theme_key, config.THEMES[config.DEFAULT_THEME])

    try:
        await callback.message.delete()
    except Exception:
        pass

    text = (
        f"📌 <b>Mavzu:</b> <i>{topic}</i>\n"
        f"📊 <b>Slaydlar soni:</b> {slide_count} ta\n"
        f"🎨 <b>Tanlangan dizayn:</b> {theme_info.emoji} {theme_info.name}\n\n"
        f"🎤 <b>Spiker nutqi (ma'ruza matni) kerakmi?</b>\n\n"
        f"Taqdimotda so'zlash uchun har bir slaydga alohida tayyor nutq matni tuzilsinmi?\n"
        f"<i>(Agar «Ha» tanlansa, har bir slayd tagida va alohida 📄 Nutq_matni.txt faylida nutq taqdim etiladi)</i>"
    )
    await callback.message.answer(text, parse_mode="HTML", reply_markup=speech_selection_keyboard())


async def execute_presentation_generation(
    target_msg: Message,
    user_id: int,
    topic: str,
    slide_count: int,
    theme_key: str,
    language: str = "uz",
    mode: str = "general",
    author_name: Optional[str] = None,
    logo_path: Optional[str] = None,
    with_speech: bool = True,
    is_doc: bool = False,
    doc_text: str = "",
    status_msg: Optional[Message] = None,
):
    theme_info = config.THEMES.get(theme_key, config.THEMES[config.DEFAULT_THEME])
    speech_desc = "va spiker nutqi" if with_speech else "(faqat slaydlar)"
    loading_text = (
        f"⏳ <b>Taqdimot tayyorlanmoqda...</b>\n\n"
        f"📌 <b>Mavzu:</b> {topic}\n"
        f"🎨 <b>Dizayn:</b> {theme_info.emoji} {theme_info.name}\n"
        f"📊 <b>Hajmi:</b> {slide_count} ta slayd\n\n"
        f"1️⃣ <i>AI mavzuga mos interaktiv reja {speech_desc} tuzmoqda...</i>"
    )
    if not status_msg:
        status_msg = await target_msg.answer(loading_text, parse_mode="HTML")
    else:
        try:
            await status_msg.edit_text(loading_text, parse_mode="HTML")
        except Exception:
            status_msg = await target_msg.answer(loading_text, parse_mode="HTML")

    presentation_content: PresentationContent
    try:
        if is_doc and doc_text:
            presentation_content = await generate_presentation_from_document(
                doc_text=doc_text,
                slide_count=slide_count,
                language=language,
                with_speech=with_speech,
                mode=mode,
            )
        else:
            presentation_content = await generate_presentation_with_gemini(
                topic=topic,
                slide_count=slide_count,
                language=language,
                with_speech=with_speech,
                mode=mode,
            )
    except Exception as e:
        logger.error(f"Generatsiyada xatolik: {e}")
        presentation_content = generate_mock_presentation(
            topic, slide_count=slide_count, with_speech=with_speech, mode=mode
        )

    try:
        try:
            await status_msg.edit_text(
                f"⏳ <b>Taqdimot tayyorlanmoqda...</b>\n\n"
                f"📌 <b>Mavzu:</b> {topic}\n"
                f"🎨 <b>Dizayn:</b> {theme_info.emoji} {theme_info.name}\n\n"
                f"✅ <i>Kontent tayyorlandi!</i>\n"
                f"2️⃣ <i>16:9 formatda tematik rasmlar va diagrammalar chizilmoqda...</i>",
                parse_mode="HTML",
            )
        except Exception:
            pass

        # 1. PowerPoint faylini yaratish (Slaydlar ostida eslatmasiz, toza format)
        pptx_file_path = create_presentation_file(
            content=presentation_content,
            theme_key=theme_key,
            author_name=author_name,
            logo_path=logo_path,
        )

        # 2. Slaydning vizual Telegram rasmini (Preview) yaratish
        preview_img_path = generate_slide_preview_image(
            content=presentation_content,
            theme_key=theme_key,
            author_name=author_name,
            logo_path=logo_path,
        )

        # 3. Spiker nutqi faylini yaratish (agar so'ralgan bo'lsa)
        speech_file_path = None
        if with_speech:
            speech_file_path = generate_speaker_speech_file(presentation_content)

        database.use_slide(user_id, is_admin(user_id))

        # Tarix va qayta ishlash uchun JSON
        content_json_str = json.dumps([s.model_dump() for s in presentation_content.slides], ensure_ascii=False)
        database.record_presentation(
            user_id=user_id,
            topic=topic,
            theme=theme_key,
            slide_count=len(presentation_content.slides),
            content_json=content_json_str,
            author_name=author_name,
        )

        database.save_last_presentation(
            user_id=user_id,
            topic=topic,
            theme=theme_key,
            content_json=content_json_str,
            author_name=author_name,
        )

        user = database.get_user(user_id)
        left = "Cheksiz (VIP)" if (user and user.get("is_vip")) else f"{user['slides_left']} ta"

        speech_status_line = (
            "🎤 <b>Spiker nutqi:</b> Alohida Nutq_matni.txt faylida taqdim etildi.\n\n"
            if with_speech
            else "⚡️ <b>Spiker nutqi:</b> O'chirilgan (toza slaydlar).\n\n"
        )
        author_line = f"✍️ <b>Muallif:</b> {author_name}\n" if author_name else ""
        logo_line = "🏢 <b>Logotip:</b> Slaydlarga biriktirildi\n" if logo_path else ""

        caption = (
            f"🎉 <b>Taqdimotingiz tayyor!</b>\n\n"
            f"📌 <b>Mavzu:</b> {topic}\n"
            f"📊 <b>Slaydlar:</b> {len(presentation_content.slides)} ta (Har biri individual dizaynda)\n"
            f"🎨 <b>Dizayn:</b> {theme_info.emoji} {theme_info.name}\n"
            f"{author_line}"
            f"{logo_line}"
            f"💎 <b>Qolgan balansingiz:</b> {left}\n\n"
            f"{speech_status_line}"
            f"💡 <i>Slaydlarni istalgan PowerPoint dasturida ochib, bemalol tahrirlashingiz mumkin.</i>"
        )

        # 1-qadam: Slaydning preview rasmini yuborish
        if preview_img_path and os.path.exists(preview_img_path):
            preview_photo = FSInputFile(preview_img_path)
            await target_msg.answer_photo(
                photo=preview_photo,
                caption=caption,
                parse_mode="HTML",
            )
        else:
            await target_msg.answer(caption, parse_mode="HTML")

        # 2-qadam: PowerPoint faylni yuborish
        pptx_doc = FSInputFile(pptx_file_path, filename=os.path.basename(pptx_file_path))
        await target_msg.answer_document(
            document=pptx_doc,
            caption=f"📁 <b>{topic}</b> — PowerPoint (.pptx) taqdimot fayli",
            parse_mode="HTML",
        )

        # 3-qadam: Spiker nutqi faylini yuborish (faqat agar tanlangan bo'lsa, alohida faylda)
        if with_speech and speech_file_path and os.path.exists(speech_file_path):
            speech_doc = FSInputFile(speech_file_path, filename=os.path.basename(speech_file_path))
            await target_msg.answer_document(
                document=speech_doc,
                caption="🎤 <b>Taqdimotda so'zlash uchun to'liq Spiker Nutqi (Nutq_matni.txt)</b>",
                parse_mode="HTML",
            )

        try:
            await status_msg.delete()
        except Exception:
            pass

        # Navigatsiya va qo'shimcha amallar tugmalari
        finish_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📄 PDF formatida", callback_data="btn_download_pdf"),
                    InlineKeyboardButton(text="📸 Slaydlar (Rasm)", callback_data="btn_all_slides_images"),
                ],
                [
                    InlineKeyboardButton(text="✏️ Slaydni tahrirlash", callback_data="btn_edit_slide"),
                    InlineKeyboardButton(text="🌐 Boshqa tilga tarjima", callback_data="btn_translate"),
                ],
                [
                    InlineKeyboardButton(text="🔄 Dizaynni o'zgartirish", callback_data="btn_reskin"),
                    InlineKeyboardButton(text="🚀 Yangi Slayd", callback_data="btn_create_slide"),
                ],
                [
                    InlineKeyboardButton(text="📁 Mening Taqdimotlarim", callback_data="btn_my_presentations"),
                    InlineKeyboardButton(text="👤 Profil & Balans", callback_data="btn_profile"),
                ],
                [InlineKeyboardButton(text="🔙 Bosh Menyu", callback_data="btn_cancel")],
            ]
        )
        await target_msg.answer(
            "✨ <b>Taqdimot to'liq yetkazildi!</b>\n\n"
            "💡 <b>Yangi imkoniyatlar:</b>\n"
            "• 📸 <b>Slaydlar (Rasm):</b> Barcha slaydlarni sifatli rasm (PNG) to'plami sifatida olish.\n"
            "• ✏️ <b>Slaydni tahrirlash:</b> Istalgan slaydni AI yordamida o'zgartirish yoki to'ldirish.\n"
            "• 🌐 <b>Boshqa tilga tarjima:</b> 1 bosishda o'zbek, rus yoki ingliz tiliga o'girish.\n"
            "• 🔄 <b>Dizaynni o'zgartirish (Re-skin):</b> 10 ta premium mavzudan biriga zudlik bilan o'tkazish.",
            parse_mode="HTML",
            reply_markup=finish_kb,
        )

    except Exception as e:
        logger.error(f"Slayd yaratishda xatolik: {e}")
        await target_msg.answer(
            "❌ Slayd tayyorlashda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.",
            reply_markup=main_menu_keyboard(user_id),
        )


@router.callback_query(F.data.in_(["speech_yes", "speech_no"]), SlideCreationState.waiting_for_speech_choice)
async def process_speech_choice_and_generate(callback: CallbackQuery, state: FSMContext):
    with_speech = (callback.data == "speech_yes")
    await safe_callback_answer(callback, "Generatsiya boshlandi...")
    data = await state.get_data()
    topic = data.get("topic", "Taqdimot")
    slide_count = data.get("slide_count", 5)
    language = data.get("language", "uz")
    theme_key = data.get("theme_key", config.DEFAULT_THEME)
    mode = data.get("mode", "general")
    author_name = data.get("author_name", "")
    logo_path = data.get("logo_path")
    is_doc = data.get("is_doc", False)
    doc_text = data.get("doc_text", "")

    await state.clear()
    await execute_presentation_generation(
        target_msg=callback.message,
        user_id=callback.from_user.id,
        topic=topic,
        slide_count=slide_count,
        theme_key=theme_key,
        language=language,
        mode=mode,
        author_name=author_name,
        logo_path=logo_path,
        with_speech=with_speech,
        is_doc=is_doc,
        doc_text=doc_text,
    )


@router.message(F.web_app_data)
async def handle_web_app_data(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Foydalanuvchi"
    username = message.from_user.username or ""
    user_dict = database.get_or_create_user(user_id, first_name, username)

    try:
        data = json.loads(message.web_app_data.data)
    except Exception as e:
        logger.error(f"WebApp ma'lumotlarida xatolik: {e}")
        await message.answer("⚠️ Ma'lumotlarni qabul qilishda xatolik yuz berdi.")
        return

    topic = data.get("topic", "").strip()
    slide_count = int(data.get("slide_count", 7))
    theme_key = data.get("theme_key", "dark_tech")
    mode = data.get("mode", "general")
    language = data.get("language", "uz")
    with_speech = bool(data.get("with_speech", True))
    author_name = data.get("author_name", "").strip() or None

    if not topic or len(topic) < 3:
        await message.answer("⚠️ Mavzu kiritilmadi. Iltimos, qaytadan Mini App orqali yuboring.")
        return

    if user_dict["slides_left"] <= 0 and not user_dict.get("is_vip"):
        await message.answer(
            "⚠️ Sizning balansingizda slaydlar qolmagan. Tariflar bo'limidan to'ldirishingiz mumkin.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="💎 Tariflar & To'lov", callback_data="btn_tariffs")]]
            ),
        )
        return

    await execute_presentation_generation(
        target_msg=message,
        user_id=user_id,
        topic=topic,
        slide_count=slide_count,
        theme_key=theme_key,
        language=language,
        mode=mode,
        author_name=author_name,
        logo_path=None,
        with_speech=with_speech,
        is_doc=False,
        doc_text="",
    )


# ------------------ PDF EXPORT VA RE-SKIN HANDLERS ------------------
@router.callback_query(F.data == "btn_download_pdf")
async def cb_download_pdf(callback: CallbackQuery):
    await safe_callback_answer(callback, "PDF tayyorlanmoqda...")
    user_id = callback.from_user.id
    last_pres = database.get_last_presentation(user_id)
    if not last_pres:
        await callback.message.answer("⚠️ Oxirgi taqdimot ma'lumotlari topilmadi. Iltimos, yangi slayd yarating.")
        return

    status_msg = await callback.message.answer("⏳ <i>PDF fayl shakllantirilmoqda...</i>", parse_mode="HTML")
    try:
        topic = last_pres["topic"]
        theme_key = last_pres["theme"]
        author_name = last_pres.get("author_name")
        slides_data = json.loads(last_pres["content_json"])
        content = PresentationContent(
            topic=topic,
            slides=[SlideContent(**s) for s in slides_data]
        )

        clean_topic = "".join(c for c in topic if c.isalnum() or c in (" ", "_", "-")).strip()[:35]
        pptx_path = os.path.join(config.GENERATED_DIR, f"{clean_topic}.pptx")
        if not os.path.exists(pptx_path):
            pptx_path = create_presentation_file(content, theme_key=theme_key, author_name=author_name)

        pdf_path = convert_pptx_to_pdf(
            pptx_path=pptx_path,
            content=content,
            theme_key=theme_key,
            author_name=author_name,
        )

        await status_msg.delete()
        if pdf_path and os.path.exists(pdf_path):
            pdf_filename = f"{clean_topic if clean_topic else 'Taqdimot'}.pdf"
            pdf_doc = FSInputFile(pdf_path, filename=pdf_filename)
            await callback.message.answer_document(
                document=pdf_doc,
                caption=f"📄 <b>{topic}</b> — PDF formatidagi taqdimot",
                parse_mode="HTML",
            )
        else:
            await callback.message.answer("❌ PDF fayl shakllantirishda xatolik yuz berdi.")
    except Exception as e:
        logger.error(f"PDF yuklashda xatolik: {e}")
        try:
            await status_msg.delete()
        except Exception:
            pass
        await callback.message.answer("❌ PDF yaratishda xatolik yuz berdi.")


@router.callback_query(F.data == "btn_reskin")
async def cb_reskin_prompt(callback: CallbackQuery):
    await safe_callback_answer(callback)
    user_id = callback.from_user.id
    last_pres = database.get_last_presentation(user_id)
    if not last_pres:
        await callback.message.answer("⚠️ Oxirgi taqdimot ma'lumotlari topilmadi. Iltimos, yangi slayd yarating.")
        return

    showcase_path = get_themes_showcase_path()

    photo = FSInputFile(showcase_path)
    current_th = config.THEMES.get(last_pres['theme'], config.THEMES[config.DEFAULT_THEME])
    text = (
        "🔄 <b>1-Click Dizaynni O'zgartirish (Re-skin)</b>\n\n"
        f"📌 <b>Mavzu:</b> {last_pres['topic']}\n"
        f"🎨 <b>Joriy dizayn:</b> {current_th.emoji} {current_th.name}\n\n"
        "Qaysi yangi dizaynga o'tkazmoqchisiz? Bitta bosishda bir zumda tayyor bo'ladi (AI qayta ishlatilmaydi va limit ketmaydi!):"
    )
    await callback.message.answer_photo(
        photo=photo,
        caption=text,
        parse_mode="HTML",
        reply_markup=theme_selection_keyboard(prefix="reskin_to_"),
    )


@router.callback_query(F.data.startswith("reskin_to_"))
async def cb_process_reskin(callback: CallbackQuery):
    await safe_callback_answer(callback, "Yangi dizaynga o'tkazilmoqda...")
    new_theme = callback.data.split("reskin_to_")[1]
    user_id = callback.from_user.id

    last_pres = database.get_last_presentation(user_id)
    if not last_pres:
        await callback.message.answer("⚠️ Taqdimot ma'lumotlari topilmadi.")
        return

    theme_info = config.THEMES.get(new_theme, config.THEMES[config.DEFAULT_THEME])
    status_msg = await callback.message.answer(
        f"⏳ <i>Yangi dizaynga o'tkazilmoqda ({theme_info.emoji} {theme_info.name})...</i>",
        parse_mode="HTML",
    )

    try:
        topic = last_pres["topic"]
        author_name = last_pres.get("author_name")
        slides_data = json.loads(last_pres["content_json"])
        content = PresentationContent(
            topic=topic,
            slides=[SlideContent(**s) for s in slides_data]
        )

        # Yangi dizaynda fayl va preview yaratish
        pptx_file_path = create_presentation_file(content=content, theme_key=new_theme, author_name=author_name)
        preview_img_path = generate_slide_preview_image(content=content, theme_key=new_theme, author_name=author_name)

        # Bazani yangilash
        database.save_last_presentation(
            user_id=user_id,
            topic=topic,
            theme=new_theme,
            content_json=last_pres["content_json"],
            author_name=author_name,
        )

        await status_msg.delete()

        # Preview rasm
        preview_photo = FSInputFile(preview_img_path)
        caption = (
            f"🎨 <b>Yangi Dizayndagi Taqdimot Tayyor!</b>\n\n"
            f"📌 <b>Mavzu:</b> {topic}\n"
            f"🎨 <b>Yangi Dizayn:</b> {theme_info.emoji} {theme_info.name}\n"
            f"📊 <b>Slaydlar:</b> {len(content.slides)} ta\n"
            f"✍️ <b>Muallif:</b> {author_name if author_name else 'Standart'}\n\n"
            f"📁 <i>PowerPoint (.pptx) fayli quyida yuklandi:</i>"
        )
        await callback.message.answer_photo(photo=preview_photo, caption=caption, parse_mode="HTML")

        pptx_doc = FSInputFile(pptx_file_path, filename=os.path.basename(pptx_file_path))
        await callback.message.answer_document(
            document=pptx_doc,
            caption=f"📁 <b>{topic}</b> — ({theme_info.name} dizaynida)",
            parse_mode="HTML",
        )

        finish_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📄 PDF formatida olish", callback_data="btn_download_pdf"),
                    InlineKeyboardButton(text="🔄 Boshqa dizayn", callback_data="btn_reskin"),
                ],
                [InlineKeyboardButton(text="🚀 Yangi Slayd Yaratish", callback_data="btn_create_slide")],
                [InlineKeyboardButton(text="🔙 Bosh Menyu", callback_data="btn_cancel")],
            ]
        )
        await callback.message.answer(
            "✨ <b>Dizayn muvaffaqiyatli yangilandi!</b>",
            reply_markup=finish_kb,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Re-skin da xatolik: {e}")
        try:
            await status_msg.delete()
        except Exception:
            pass
        await callback.message.answer("❌ Qayta dizayn qilishda xatolik yuz berdi.")


# ------------------ BARCHA SLAYDLARNI RASMDA OLISH (FEATURE 1) ------------------
@router.callback_query(F.data == "btn_all_slides_images")
async def cb_all_slides_images(callback: CallbackQuery, bot: Bot):
    await safe_callback_answer(callback, "Slaydlar rasmlari tayyorlanmoqda...")
    user_id = callback.from_user.id
    last_pres = database.get_last_presentation(user_id)
    if not last_pres or not last_pres.get("content_json"):
        await callback.message.answer("⚠️ Oxirgi taqdimot ma'lumotlari topilmadi.")
        return

    status_msg = await callback.message.answer("⏳ <i>Barcha slaydlar HD rasm (PNG) qilib chizilmoqda...</i>", parse_mode="HTML")
    try:
        topic = last_pres["topic"]
        theme_key = last_pres["theme"]
        author_name = last_pres.get("author_name")
        slides_data = json.loads(last_pres["content_json"])
        content = PresentationContent(topic=topic, slides=[SlideContent(**s) for s in slides_data])

        images = generate_all_slides_preview_images(content, theme_key=theme_key, author_name=author_name)
        await status_msg.delete()

        # Telegram albumda yuborish (maksimal 10 tadan guruhlab)
        chunk_size = 10
        for i in range(0, len(images), chunk_size):
            chunk = images[i:i + chunk_size]
            media_group = []
            for idx, img_p in enumerate(chunk):
                caption = f"📸 <b>{topic}</b> — {i + idx + 1}-slayd" if idx == 0 else ""
                media_group.append(InputMediaPhoto(media=FSInputFile(img_p), caption=caption, parse_mode="HTML"))
            await callback.message.answer_media_group(media=media_group)

        await callback.message.answer(
            f"🎉 <b>Barcha {len(images)} ta slayd fotosurat ko'rinishida yuborildi!</b>\n\n"
            "Ularni telefoningizga saqlab olishingiz yoki do'stlaringiz bilan ulashishingiz mumkin.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Rasmlar to'plamida xatolik: {e}")
        try:
            await status_msg.delete()
        except Exception:
            pass
        await callback.message.answer("❌ Slaydlarni rasmga aylantirishda xatolik yuz berdi.")


# ------------------ 1-CLICK TARJIMA QILISH (FEATURE 3) ------------------
@router.callback_query(F.data == "btn_translate")
async def cb_translate_prompt(callback: CallbackQuery):
    await safe_callback_answer(callback)
    user_id = callback.from_user.id
    last_pres = database.get_last_presentation(user_id)
    if not last_pres:
        await callback.message.answer("⚠️ Oxirgi taqdimot ma'lumotlari topilmadi.")
        return

    text = (
        "🌐 <b>1-Click Taqdimotni Tarjima Qilish</b>\n\n"
        f"📌 <b>Mavzu:</b> {last_pres['topic']}\n\n"
        "Taqdimotning barcha slaydlari, sarlavhalari, kartalari va nutqini qaysi tilga tarjima qilmoqchisiz?\n"
        "<i>Dizayn, tartib va rasmlar 100% to'liq saqlanadi.</i>"
    )
    await callback.message.answer(text, parse_mode="HTML", reply_markup=translate_language_keyboard())


@router.callback_query(F.data.startswith("trans_to_"))
async def cb_process_translate(callback: CallbackQuery):
    target_lang = callback.data.split("trans_to_")[1]
    await safe_callback_answer(callback, "Tarjima boshlanmoqda...")
    user_id = callback.from_user.id
    last_pres = database.get_last_presentation(user_id)
    if not last_pres:
        await callback.message.answer("⚠️ Oxirgi taqdimot ma'lumotlari topilmadi.")
        return

    lang_titles = {"uz": "O'zbek", "ru": "Rus", "en": "Ingliz"}
    status_msg = await callback.message.answer(
        f"⏳ <i>Taqdimot {lang_titles.get(target_lang, target_lang)} tiliga professional tarjima qilinmoqda...</i>",
        parse_mode="HTML",
    )

    try:
        topic = last_pres["topic"]
        theme_key = last_pres["theme"]
        author_name = last_pres.get("author_name")
        slides_data = json.loads(last_pres["content_json"])
        content = PresentationContent(topic=topic, slides=[SlideContent(**s) for s in slides_data])

        translated_content = await translate_presentation_content(content, target_lang=target_lang)

        # Yangi fayl va preview
        pptx_file_path = create_presentation_file(content=translated_content, theme_key=theme_key, author_name=author_name)
        preview_img_path = generate_slide_preview_image(content=translated_content, theme_key=theme_key, author_name=author_name)

        new_json_str = json.dumps([s.model_dump() for s in translated_content.slides], ensure_ascii=False)
        database.save_last_presentation(
            user_id=user_id,
            topic=translated_content.topic,
            theme=theme_key,
            content_json=new_json_str,
            author_name=author_name,
        )

        await status_msg.delete()

        preview_photo = FSInputFile(preview_img_path)
        caption = (
            f"🌐 <b>Taqdimot {lang_titles.get(target_lang, target_lang)} tiliga muvaffaqiyatli tarjima qilindi!</b>\n\n"
            f"📌 <b>Mavzu:</b> {translated_content.topic}\n"
            f"📊 <b>Slaydlar soni:</b> {len(translated_content.slides)} ta\n\n"
            "📁 <i>Yangi tarjima qilingan taqdimot fayli (.pptx) quyida yuklandi:</i>"
        )
        await callback.message.answer_photo(photo=preview_photo, caption=caption, parse_mode="HTML")

        pptx_doc = FSInputFile(pptx_file_path, filename=os.path.basename(pptx_file_path))
        await callback.message.answer_document(
            document=pptx_doc,
            caption=f"📁 <b>{translated_content.topic}</b> ({target_lang.upper()} tilida)",
            parse_mode="HTML",
        )

        finish_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📄 PDF formatida", callback_data="btn_download_pdf"),
                    InlineKeyboardButton(text="📸 Slaydlar (Rasm)", callback_data="btn_all_slides_images"),
                ],
                [
                    InlineKeyboardButton(text="✏️ Slaydni tahrirlash", callback_data="btn_edit_slide"),
                    InlineKeyboardButton(text="🌐 Boshqa tilga tarjima", callback_data="btn_translate"),
                ],
                [
                    InlineKeyboardButton(text="🚀 Yangi Slayd", callback_data="btn_create_slide"),
                    InlineKeyboardButton(text="🔙 Bosh Menyu", callback_data="btn_cancel"),
                ],
            ]
        )
        await callback.message.answer("✨ <b>Amal yakunlandi!</b>", reply_markup=finish_kb, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Tarjima jarayonida xatolik: {e}")
        try:
            await status_msg.delete()
        except Exception:
            pass
        await callback.message.answer("❌ Tarjima qilishda xatolik yuz berdi.")


# ------------------ SLAYDNI TAHRIRLASH (FEATURE 7) ------------------
@router.callback_query(F.data == "btn_edit_slide")
async def cb_edit_slide_prompt(callback: CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    user_id = callback.from_user.id
    last_pres = database.get_last_presentation(user_id)
    if not last_pres or not last_pres.get("content_json"):
        await callback.message.answer("⚠️ Oxirgi taqdimot ma'lumotlari topilmadi.")
        return

    slides_data = json.loads(last_pres["content_json"])
    total_slides = len(slides_data)

    buttons = []
    row = []
    for i in range(total_slides):
        row.append(InlineKeyboardButton(text=f"{i+1}-slayd", callback_data=f"pick_slide_{i+1}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="btn_cancel")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await state.set_state(SlideEditState.waiting_for_slide_choice)
    await callback.message.answer(
        "✏️ <b>AI Slayd Muharriri</b>\n\n"
        f"Taqdimotingizda jami <b>{total_slides} ta slayd</b> mavjud.\n"
        "Qaysi slaydni o'zgartirmoqchisiz yoki yaxshilamoqchisiz? Tanlang:",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("pick_slide_"), SlideEditState.waiting_for_slide_choice)
async def cb_picked_slide_for_edit(callback: CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    slide_num = int(callback.data.split("pick_slide_")[1])
    user_id = callback.from_user.id
    last_pres = database.get_last_presentation(user_id)
    if not last_pres:
        await callback.message.answer("⚠️ Taqdimot topilmadi.")
        return

    slides_data = json.loads(last_pres["content_json"])
    chosen_slide = slides_data[slide_num - 1]

    await state.update_data(chosen_slide_index=slide_num - 1)
    await state.set_state(SlideEditState.waiting_for_instruction)

    text = (
        f"✏️ <b>{slide_num}-slayd tanlandi:</b>\n"
        f"📌 <b>Sarlavha:</b> {chosen_slide.get('title')}\n\n"
        "Ushbu slaydni qanday o'zgartirmoqchisiz? Ko'rsatma (prompt) yozing:\n\n"
        "<i>Masalan:</i>\n"
        "• <i>Matnni qisqaroq qil va 3 ta aniq fakt qo'sh</i>\n"
        "• <i>Sarlavhani 'Sun'iy intellekt kelajagi' deb o'zgartir</i>\n"
        "• <i>3 ta karta shaklida yangi g'oyalar yoz</i>\n\n"
        "Yozib yuboring (bekor qilish uchun /cancel):"
    )
    await callback.message.answer(text, parse_mode="HTML")


@router.message(SlideEditState.waiting_for_instruction)
async def process_slide_edit_instruction(message: Message, state: FSMContext):
    instruction = (message.text or "").strip()
    if instruction.startswith("/cancel"):
        await state.clear()
        await message.answer("Tahrirlash bekor qilindi.", reply_markup=main_menu_keyboard(message.from_user.id))
        return

    data = await state.get_data()
    slide_index = data.get("chosen_slide_index", 0)
    user_id = message.from_user.id

    last_pres = database.get_last_presentation(user_id)
    if not last_pres:
        await message.answer("⚠️ Taqdimot topilmadi.")
        await state.clear()
        return

    status_msg = await message.answer(f"⏳ <i>{slide_index + 1}-slayd sizning ko'rsatmangiz asosida yangilanmoqda...</i>", parse_mode="HTML")
    try:
        topic = last_pres["topic"]
        theme_key = last_pres["theme"]
        author_name = last_pres.get("author_name")
        slides_data = json.loads(last_pres["content_json"])
        target_slide_dict = slides_data[slide_index]
        target_slide = SlideContent(**target_slide_dict)

        updated_slide = await tweak_single_slide(target_slide, instruction=instruction, language="uz")
        slides_data[slide_index] = updated_slide.model_dump()

        new_content = PresentationContent(topic=topic, slides=[SlideContent(**s) for s in slides_data])

        # Yangi PPTX va preview
        pptx_file_path = create_presentation_file(content=new_content, theme_key=theme_key, author_name=author_name)
        new_json_str = json.dumps([s.model_dump() for s in new_content.slides], ensure_ascii=False)
        database.save_last_presentation(
            user_id=user_id,
            topic=topic,
            theme=theme_key,
            content_json=new_json_str,
            author_name=author_name,
        )

        theme_info = config.THEMES.get(theme_key, config.THEMES[config.DEFAULT_THEME])
        updated_slide_img = render_slide_to_image(
            slide_data=updated_slide,
            theme=theme_info,
            current_num=slide_index + 1,
            total_slides=len(new_content.slides),
            author_name=author_name,
        )
        out_img_path = os.path.join(config.GENERATED_DIR, f"edited_slide_{user_id}_{slide_index+1}.png")
        updated_slide_img.save(out_img_path, "PNG", quality=95)

        await status_msg.delete()
        await state.clear()

        photo_input = FSInputFile(out_img_path)
        caption = (
            f"✅ <b>{slide_index + 1}-slayd muvaffaqiyatli tahrirlandi!</b>\n\n"
            f"📌 <b>Yangi Sarlavha:</b> {updated_slide.title}\n"
            f"✍️ <b>Ko'rsatkich:</b> {instruction}\n\n"
            "📁 <i>Yangilangan to'liq taqdimot fayli (.pptx) quyida yuklandi:</i>"
        )
        await message.answer_photo(photo=photo_input, caption=caption, parse_mode="HTML")

        pptx_doc = FSInputFile(pptx_file_path, filename=os.path.basename(pptx_file_path))
        await message.answer_document(
            document=pptx_doc,
            caption=f"📁 <b>{topic}</b> (Tahrirlangan versiya)",
            parse_mode="HTML",
        )

        finish_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📄 PDF formatida", callback_data="btn_download_pdf"),
                    InlineKeyboardButton(text="📸 Slaydlar (Rasm)", callback_data="btn_all_slides_images"),
                ],
                [
                    InlineKeyboardButton(text="✏️ Yana boshqa slaydni tahrirlash", callback_data="btn_edit_slide"),
                ],
                [
                    InlineKeyboardButton(text="🚀 Yangi Slayd", callback_data="btn_create_slide"),
                    InlineKeyboardButton(text="🔙 Bosh Menyu", callback_data="btn_cancel"),
                ],
            ]
        )
        await message.answer("✨ <b>Tahrirlash muvaffaqiyatli yakunlandi!</b>", reply_markup=finish_kb, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Slaydni tahrirlashda xatolik: {e}")
        try:
            await status_msg.delete()
        except Exception:
            pass
        await message.answer("❌ Slaydni tahrirlashda xatolik yuz berdi.", reply_markup=main_menu_keyboard(message.from_user.id))
        await state.clear()


# ------------------ MENING TAQDIMOTLARIM (FEATURE 6) ------------------
@router.message(Command("history"))
@router.callback_query(F.data == "btn_my_presentations")
async def cb_my_presentations(event: Any):
    is_cb = isinstance(event, CallbackQuery)
    user_id = event.from_user.id
    message = event.message if is_cb else event

    if is_cb:
        await safe_callback_answer(event)

    presentations = database.get_user_presentations(user_id, limit=5)
    if not presentations:
        text = (
            "📁 <b>Siz hali birorta taqdimot yaratmadingiz!</b>\n\n"
            "Birinchi professional taqdimotingizni yaratish uchun quyidagi tugmani bosing:"
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🚀 Yangi Slayd Yaratish", callback_data="btn_create_slide")],
                [InlineKeyboardButton(text="🔙 Bosh Menyu", callback_data="btn_cancel")],
            ]
        )
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
        return

    text = "📁 <b>Sizning Oxirgi Taqdimotlaringiz:</b>\n\n"
    buttons = []
    for idx, p in enumerate(presentations):
        date_str = str(p.get("created_at", ""))[:16]
        th = config.THEMES.get(p.get("theme", ""), config.THEMES[config.DEFAULT_THEME])
        text += f"<b>{idx+1}. {p['topic']}</b>\n"
        text += f"   📊 {p['slide_count']} ta slayd  •  {th.emoji} {th.name}  •  🗓 {date_str}\n\n"

        p_id = p["id"]
        buttons.append([
            InlineKeyboardButton(text=f"📥 {idx+1}. PPTX", callback_data=f"hist_dl_{p_id}"),
            InlineKeyboardButton(text=f"📸 {idx+1}. Rasmlar", callback_data=f"hist_img_{p_id}"),
        ])

    buttons.append([InlineKeyboardButton(text="🚀 Yangi Slayd Yaratish", callback_data="btn_create_slide")])
    buttons.append([InlineKeyboardButton(text="🔙 Bosh Menyu", callback_data="btn_cancel")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("hist_dl_"))
async def cb_history_download(callback: CallbackQuery):
    p_id = int(callback.data.split("hist_dl_")[1])
    await safe_callback_answer(callback, "Taqdimot tayyorlanmoqda...")
    p = database.get_presentation_by_id(p_id)
    if not p or not p.get("content_json"):
        await callback.message.answer("⚠️ Ushbu taqdimot fayli topilmadi.")
        return

    slides_data = json.loads(p["content_json"])
    content = PresentationContent(topic=p["topic"], slides=[SlideContent(**s) for s in slides_data])
    pptx_path = create_presentation_file(content=content, theme_key=p["theme"], author_name=p.get("author_name"))

    pptx_doc = FSInputFile(pptx_path, filename=os.path.basename(pptx_path))
    await callback.message.answer_document(
        document=pptx_doc,
        caption=f"📁 <b>{p['topic']}</b> (Tarixdan yuklandi)",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("hist_img_"))
async def cb_history_images(callback: CallbackQuery):
    p_id = int(callback.data.split("hist_img_")[1])
    await safe_callback_answer(callback, "Rasmlar tayyorlanmoqda...")
    p = database.get_presentation_by_id(p_id)
    if not p or not p.get("content_json"):
        await callback.message.answer("⚠️ Ushbu taqdimot topilmadi.")
        return

    slides_data = json.loads(p["content_json"])
    content = PresentationContent(topic=p["topic"], slides=[SlideContent(**s) for s in slides_data])
    images = generate_all_slides_preview_images(content, theme_key=p["theme"], author_name=p.get("author_name"))

    chunk_size = 10
    for i in range(0, len(images), chunk_size):
        chunk = images[i:i + chunk_size]
        media_group = []
        for idx, img_p in enumerate(chunk):
            cap = f"📸 <b>{p['topic']}</b> — {i + idx + 1}-slayd" if idx == 0 else ""
            media_group.append(InputMediaPhoto(media=FSInputFile(img_p), caption=cap, parse_mode="HTML"))
        await callback.message.answer_media_group(media=media_group)


# ------------------ KUNLIK BONUS HANDLER ------------------
@router.callback_query(F.data == "btn_daily_bonus")
async def cb_daily_bonus(callback: CallbackQuery):
    user_id = callback.from_user.id
    success, msg, bal, rem = database.claim_daily_bonus(user_id)
    await safe_callback_answer(callback, "Kunlik bonus!")

    status_extra = f"\n\n📊 <b>Joriy balansingiz:</b> <b>{bal} ta slayd</b>" if success else ""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Slayd Yaratish", callback_data="btn_create_slide")],
            [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="btn_cancel")],
        ]
    )
    await safe_edit_or_answer(callback.message, f"{msg}{status_extra}", reply_markup=kb)


# ------------------ TELEGRAMDAN TO'LIQ BOSHQARILADIGAN ADMIN PANEL ------------------
@router.message(Command("admin"))
@router.callback_query(F.data == "btn_admin_panel")
async def cmd_admin_panel(event: Any, state: FSMContext):
    user_id = event.from_user.id
    if not is_admin(user_id):
        if isinstance(event, Message):
            await event.answer("Kechirasiz, ushbu buyruq faqat bot adminlari uchun.")
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
        f"• Qo'shimcha adminlar: <b>{stats.get('total_subadmins', 0)}</b> ta\n\n"
        f"⚙️ <b>Joriy Sozlamalar:</b>\n"
        f"• Majburiy kanal: <code>{req_chan or 'O''rnatilmagan'}</code>\n"
        f"• Boshlang'ich limit: <b>{init_lim} ta</b>\n"
        f"• Referal bonusi: <b>+{ref_rew} ta</b>\n\n"
        "Quyidagi bo'limlardan birini tanlang:"
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=admin_menu_keyboard())
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=admin_menu_keyboard())


@router.message(Command("give"))
async def cmd_give(message: Message, command: CommandObject, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    args = (command.args or "").split()
    if len(args) != 2:
        await message.answer(
            "Format: <code>/give USER_ID MIQDOR</code>\n\n"
            "<i>Misollar:</i>\n"
            "• <code>/give 12345678 50</code> — 50 ta slayd berish\n"
            "• <code>/give 12345678 vip</code> — Cheksiz VIP status berish",
            parse_mode="HTML",
        )
        return
    try:
        target_uid = int(args[0])
    except ValueError:
        await message.answer("User ID faqat raqam bo'lishi kerak!")
        return

    val = args[1].lower()
    if val == "vip":
        database.set_user_vip(target_uid, True)
        await message.answer(f"✅ Foydalanuvchi <code>{target_uid}</code> ga <b>VIP CHEKSIZ</b> status berildi!", parse_mode="HTML")
        try:
            await bot.send_message(
                chat_id=target_uid,
                text="🎉 <b>Tabriklaymiz!</b> Admin tomonidan sizga <b>VIP CHEKSIZ</b> status taqdim etildi! Endi xohlagancha bepul taqdimot yaratishingiz mumkin.",
                parse_mode="HTML",
            )
        except Exception:
            pass
    else:
        try:
            count = int(val)
            database.add_slides_to_user(target_uid, count)
            await message.answer(f"✅ Foydalanuvchi <code>{target_uid}</code> ga <b>+{count} ta slayd</b> qo'shildi!", parse_mode="HTML")
            try:
                await bot.send_message(
                    chat_id=target_uid,
                    text=f"🎉 <b>Ajoyib yangilik!</b> Admin tomonidan hisobingizga <b>+{count} ta bepul slayd</b> taqdim etildi!",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        except ValueError:
            await message.answer("Slaydlar soni raqam yoki 'vip' bo'lishi kerak!")


@router.message(Command("addadmin"))
async def cmd_add_admin(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    args = (command.args or "").strip()
    if not args:
        await message.answer("Format: <code>/addadmin USER_ID</code>\n<i>Masalan:</i> <code>/addadmin 12345678</code>", parse_mode="HTML")
        return
    try:
        target_uid = int(args)
        database.add_admin(user_id=target_uid, added_by=message.from_user.id, note="Yordamchi Admin")
        await message.answer(f"✅ <code>{target_uid}</code> muvaffaqiyatli <b>Admin</b> etib tayinlandi!", parse_mode="HTML")
    except ValueError:
        await message.answer("User ID faqat raqam bo'lishi kerak!")


@router.message(Command("removeadmin"))
async def cmd_remove_admin(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    args = (command.args or "").strip()
    if not args:
        await message.answer("Format: <code>/removeadmin USER_ID</code>\n<i>Masalan:</i> <code>/removeadmin 12345678</code>", parse_mode="HTML")
        return
    try:
        target_uid = int(args)
        database.remove_admin(target_uid)
        await message.answer(f"✅ <code>{target_uid}</code> adminlikdan olindi.", parse_mode="HTML")
    except ValueError:
        await message.answer("User ID faqat raqam bo'lishi kerak!")


# 1. Adminlar boshqaruvi (2-admin qo'shish va o'chirish)
@router.callback_query(F.data == "adm_admins")
async def cb_admin_list(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await safe_callback_answer(callback)
    admins = database.get_all_admins()
    
    admin_list_text = ""
    for a in admins:
        admin_list_text += f"• ID: <code>{a['user_id']}</code> ({a.get('note') or 'Admin'})\n"
    if not admin_list_text:
        admin_list_text = "<i>Hozircha qo'shimcha adminlar yo'q.</i>\n"

    text = (
        "👥 <b>Adminlar Boshqaruvi</b>\n\n"
        f"Asosiy admin ID: <code>{config.ADMIN_ID}</code>\n\n"
        f"<b>Qo'shimcha adminlar ro'yxati:</b>\n{admin_list_text}\n"
        "Yangi 2-admin qo'shish uchun pastdagi tugmani bosing:"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Yangi Admin Qo'shish", callback_data="adm_add_admin_prompt")],
            [InlineKeyboardButton(text="🗑 Adminni O'chirish", callback_data="adm_remove_admin_prompt")],
            [InlineKeyboardButton(text="🔙 Admin menyu", callback_data="btn_admin_panel")],
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "adm_add_admin_prompt")
async def cb_prompt_add_admin(callback: CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    await state.set_state(AdminState.waiting_for_new_admin)
    await callback.message.edit_text(
        "➕ <b>Yangi Admin Qo'shish:</b>\n\n"
        "Yangi admin qilmoqchi bo'lgan foydalanuvchining <b>Telegram ID raqamini</b> yuboring:\n"
        "<i>(Masalan: 123456789)</i>\n\n"
        "Bekor qilish uchun /cancel yozing.",
        parse_mode="HTML",
    )


@router.message(AdminState.waiting_for_new_admin)
async def process_new_admin(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    text = (message.text or "").strip()
    if text.startswith("/cancel"):
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=admin_menu_keyboard())
        return
    try:
        target_uid = int(text)
        database.add_admin(user_id=target_uid, added_by=message.from_user.id, note="Yordamchi Admin")
        await state.clear()
        await message.answer(f"✅ <code>{target_uid}</code> muvaffaqiyatli <b>Admin</b> etib tayinlandi!", parse_mode="HTML", reply_markup=admin_menu_keyboard())
    except ValueError:
        await message.answer("Iltimos, faqat raqamdan iborat Telegram ID yuboring:")


@router.callback_query(F.data == "adm_remove_admin_prompt")
async def cb_prompt_remove_admin(callback: CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    admins = database.get_all_admins()
    if not admins:
        await callback.message.answer("O'chirish uchun qo'shimcha adminlar yo'q.", reply_markup=admin_menu_keyboard())
        return

    buttons = []
    for a in admins:
        buttons.append([InlineKeyboardButton(text=f"❌ O'chirish: {a['user_id']}", callback_data=f"del_adm_{a['user_id']}")])
    buttons.append([InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="btn_admin_panel")])
    await callback.message.edit_text("Qaysi adminni o'chirmoqchisiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("del_adm_"))
async def cb_delete_admin(callback: CallbackQuery):
    target_uid = int(callback.data.split("del_adm_")[1])
    database.remove_admin(target_uid)
    await safe_callback_answer(callback, "Admin o'chirildi!")
    await callback.message.edit_text(f"✅ <code>{target_uid}</code> adminlikdan olindi.", parse_mode="HTML", reply_markup=admin_menu_keyboard())


# 2. Foydalanuvchiga limit va VIP berish
@router.callback_query(F.data == "adm_give_limit")
async def cb_prompt_give_limit(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await safe_callback_answer(callback)
    await state.set_state(AdminState.waiting_for_give_limit)
    text = (
        "🎁 <b>Foydalanuvchiga Limit yoki VIP Berish:</b>\n\n"
        "Foydalanuvchi ID raqamini va beriladigan slaydlar sonini probel bilan yuboring:\n\n"
        "<i>Misollar:</i>\n"
        "• <code>123456789 50</code> — 50 ta slayd qo'shish\n"
        "• <code>123456789 vip</code> — Cheksiz VIP status berish\n\n"
        "Bekor qilish uchun /cancel yozing."
    )
    await callback.message.edit_text(text, parse_mode="HTML")


@router.message(AdminState.waiting_for_give_limit)
async def process_give_limit(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    text = (message.text or "").strip()
    if text.startswith("/cancel"):
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=admin_menu_keyboard())
        return

    parts = text.split()
    if len(parts) != 2:
        await message.answer("Format: <code>USER_ID SONI</code> (masalan: <code>12345678 50</code> yoki <code>12345678 vip</code>):", parse_mode="HTML")
        return

    try:
        target_uid = int(parts[0])
    except ValueError:
        await message.answer("ID raqami faqat son bo'lishi kerak!")
        return

    val = parts[1].lower()
    await state.clear()

    if val == "vip":
        database.set_user_vip(target_uid, True)
        await message.answer(f"✅ Foydalanuvchi <code>{target_uid}</code> ga <b>VIP CHEKSIZ</b> status berildi!", parse_mode="HTML", reply_markup=admin_menu_keyboard())
        try:
            await bot.send_message(
                chat_id=target_uid,
                text="🎉 <b>Tabriklaymiz!</b> Admin tomonidan sizga <b>VIP CHEKSIZ</b> status taqdim etildi! Endi xohlagancha bepul taqdimot yaratishingiz mumkin.",
                parse_mode="HTML",
            )
        except Exception:
            pass
    else:
        try:
            count = int(val)
            database.add_slides_to_user(target_uid, count)
            await message.answer(f"✅ Foydalanuvchi <code>{target_uid}</code> ga <b>+{count} ta slayd</b> qo'shildi!", parse_mode="HTML", reply_markup=admin_menu_keyboard())
            try:
                await bot.send_message(
                    chat_id=target_uid,
                    text=f"🎉 <b>Ajoyib yangilik!</b> Admin tomonidan hisobingizga <b>+{count} ta bepul slayd</b> taqdim etildi!",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        except ValueError:
            await message.answer("Slaydlar soni raqam bo'lishi kerak!")


# 3. Promokod yaratish
@router.callback_query(F.data == "adm_create_promo")
async def cb_prompt_create_promo(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await safe_callback_answer(callback)
    await state.set_state(AdminState.waiting_for_create_promo)
    promos = database.get_all_promocodes()
    promo_list = "\n".join([f"• <code>{p['code']}</code> (+{p['bonus_slides']} ta, qoldi: {p['activations_left']} ta)" for p in promos])

    text = (
        "🎟 <b>Yangi Promokod Yaratish</b>\n\n"
        f"<b>Mavjud promokodlar:</b>\n{promo_list or 'Promokodlar yo''q'}\n\n"
        "Yangi promokod yaratish uchun quyidagi formatda yuboring:\n"
        "<code>KOD_NOMI BONUS_SONI AKTIVATSIYALAR</code>\n\n"
        "<i>Masalan:</i> <code>YANGI2026 5 100</code>\n"
        "(YANGI2026 kodi orqali 100 kishiga +5 tadan slayd beriladi)\n\n"
        "Bekor qilish uchun /cancel yozing."
    )
    await callback.message.edit_text(text, parse_mode="HTML")


@router.message(AdminState.waiting_for_create_promo)
async def process_create_promo(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    text = (message.text or "").strip()
    if text.startswith("/cancel"):
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=admin_menu_keyboard())
        return

    parts = text.split()
    if len(parts) != 3:
        await message.answer("Format: <code>KOD BONUS SONI</code> (masalan: <code>START 5 50</code>):", parse_mode="HTML")
        return

    code = parts[0].upper()
    try:
        bonus = int(parts[1])
        acts = int(parts[2])
        database.create_promocode(code, bonus, acts)
        await state.clear()
        await message.answer(f"✅ <b>{code}</b> promokodi muvaffaqiyatli yaratildi!\nBonus: +{bonus} ta | Aktivatsiyalar: {acts} ta", parse_mode="HTML", reply_markup=admin_menu_keyboard())
    except ValueError:
        await message.answer("Bonus va aktivatsiyalar soni butun raqam bo'lishi kerak!")


# 4. Karta va to'lov matni
@router.callback_query(F.data == "adm_payment_info")
async def cb_prompt_payment_info(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await safe_callback_answer(callback)
    await state.set_state(AdminState.waiting_for_payment_info)
    current = database.get_formatted_payment_info()
    text = (
        "💳 <b>Karta Raqami va To'lov Ma'lumotlarini Sozlash:</b>\n\n"
        f"<b>Joriy ma'lumotlar:</b>\n{current}\n\n"
        "Yangi karta raqami va karta egasining ism-familiyasini yozib yuboring.\n\n"
        "<b>Namuna:</b>\n"
        "<code>💳 Karta: 8600 1234 5678 9012\n👤 Egasi: ALISHER NAVOIY</code>\n\n"
        "<i>(Yoki faqat 16 xonali karta raqamingizni yozsangiz ham bot o'zi chiroyli qilib oladi)</i>\n\n"
        "Bekor qilish uchun /cancel yozing."
    )
    await callback.message.edit_text(text, parse_mode="HTML")


@router.message(AdminState.waiting_for_payment_info)
async def process_payment_info(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    text = (message.text or "").strip()
    if text.startswith("/cancel"):
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=admin_menu_keyboard())
        return

    database.set_setting("payment_info", text)
    await state.clear()
    await message.answer(
        "✅ To'lov ma'lumotlari muvaffaqiyatli yangilandi!\n\n"
        f"<b>Botda ko'rinishi:</b>\n{database.get_formatted_payment_info()}",
        parse_mode="HTML",
        reply_markup=admin_menu_keyboard(),
    )


# 5. Kanal sozlamasi
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
        "O'chirib qo'yish uchun <code>ochirish</code> deb yozing.\n\n"
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


# 6. Standart limit va referal bonusi
@router.callback_query(F.data == "adm_limits")
async def cb_admin_limits(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await safe_callback_answer(callback)
    init_lim = database.get_setting("initial_slides_limit", "3")
    ref_rew = database.get_setting("referral_reward", "2")

    text = (
        "⚙️ <b>Standart Limit va Bonuslarni O'zgartirish</b>\n\n"
        f"1. Yangi foydalanuvchiga beriladigan slaydlar: <b>{init_lim} ta</b>\n"
        f"2. Har bir taklif qilingan do'st uchun bonus: <b>+{ref_rew} ta</b>\n\n"
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
    await callback.message.edit_text("Yangi foydalanuvchilar uchun standart slaydlar sonini yuboring (masalan: 5):")


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


# 7. Rassilka
@router.callback_query(F.data == "adm_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await safe_callback_answer(callback)
    await state.set_state(AdminState.waiting_for_broadcast_message)
    text = (
        "✉️ <b>Barcha foydalanuvchilarga xabar tarqatish (Rassilka)</b>\n\n"
        "Foydalanuvchilarga yuborilishi kerak bo'lgan xabarni yuboring (matn, rasm yoki video).\n\n"
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
    status_msg = await message.answer("⏳ <i>Xabarlar tarqatilmoqda...</i>", parse_mode="HTML")

    user_ids = database.get_all_user_ids()
    sent = 0
    failed = 0

    for uid in user_ids:
        try:
            await message.copy_to(chat_id=uid)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ <b>Rassilka yakunlandi!</b>\n\n• Yetkazildi: <b>{sent} ta</b>\n• Yetkazilmadi: <b>{failed} ta</b>",
        parse_mode="HTML",
        reply_markup=admin_menu_keyboard(),
    )


# 8. Tezkor buyruqlar
@router.message(Command("give"))
async def cmd_give_quick(message: Message, bot: Bot):
    """Format: /give 12345678 50 yoki /give 12345678 vip"""
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("Format: <code>/give USER_ID SONI_YOKI_VIP</code>\nMisollar:\n• <code>/give 12345678 50</code>\n• <code>/give 12345678 vip</code>", parse_mode="HTML")
        return
    try:
        target_uid = int(parts[1])
        val = parts[2].lower()
        if val == "vip":
            database.set_user_vip(target_uid, True)
            await message.answer(f"✅ <code>{target_uid}</code> ga <b>VIP CHEKSIZ</b> status berildi!", parse_mode="HTML")
        else:
            cnt = int(val)
            database.add_slides_to_user(target_uid, cnt)
            await message.answer(f"✅ <code>{target_uid}</code> ga <b>+{cnt} ta slayd</b> qo'shildi!", parse_mode="HTML")
    except ValueError:
        await message.answer("ID va Soni to'g'ri raqam bo'lishi kerak!")


@router.message(Command("myid"))
async def cmd_myid(message: Message):
    await message.answer(f"Sizning Telegram ID raqamingiz: <code>{message.from_user.id}</code>", parse_mode="HTML")


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
        f"🔗 Referal takliflar soni: <b>{stats['total_referrals']} ta</b>\n"
        f"👑 Qo'shimcha adminlar: <b>{stats.get('total_subadmins', 0)} ta</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Admin menyu", callback_data="btn_admin_panel")]])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


# Retargeting Handlers
@router.callback_query(F.data == "adm_retargeting")
async def cb_admin_retargeting(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await safe_callback_answer(callback)

    stats = database.get_retargeting_stats()
    text = (
        "📢 <b>Smart Marketing & Retargeting (Qayta jalb qilish)</b>\n\n"
        f"👥 Jami ro'yxatdan o'tgan foydalanuvchilar: <b>{stats['total']} ta</b>\n"
        f"😴 3+ kundan beri kirmagan nofaol foydalanuvchilar: <b>{stats['inactive']} ta</b>\n\n"
        "<i>Ushbu funksiya orqali nofaol foydalanuvchilarga bepul bonus va yangi imkoniyatlar haqida do'stona eslatma yuborib, ularni botga qaytarish mumkin.</i>"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Eslatmani Yuborish (Nofaollarga)", callback_data="adm_send_retargeting")],
            [InlineKeyboardButton(text="🔙 Admin menyu", callback_data="btn_admin_panel")],
        ]
    )
    await safe_edit_or_answer(callback.message, text, reply_markup=kb)


@router.callback_query(F.data == "adm_send_retargeting")
async def cb_admin_send_retargeting(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    await safe_callback_answer(callback, "Eslatma yuborilmoqda...")

    inactive_users = database.get_inactive_users(days_inactive=3, limit=100)
    if not inactive_users:
        await callback.message.answer("Hozirda eslatma yuboriladigan nofaol foydalanuvchilar yo'q.")
        return

    sent_count = 0
    fail_count = 0

    reminder_text = (
        "🎁 <b>Salom! Sizni @SlaydchiAkabot da ko'rmaganimizga ham bir necha kun bo'ldi!</b>\n\n"
        "✨ Botimizda yangi katta yangilanishlar bo'ldi:\n"
        "• 🎙 <b>Ovozli xabar</b> yoki 📸 <b>Kitob/Konspekt rasmini</b> yuborib slayd yasash\n"
        "• 📊 <b>Haqiqiy PowerPoint diagrammalari va grafiklari</b>\n"
        "• 📱 <b>Yangi interaktiv Telegram Mini App</b>\n\n"
        "🎁 <i>Siz uchun yangi kunlik bonus tayyor! /start bosing va yangi taqdimotingizni 1 daqiqada yarating</i> 🚀"
    )

    for u in inactive_users:
        uid = u["user_id"]
        try:
            await bot.send_message(
                chat_id=uid,
                text=reminder_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🚀 Slayd Yaratish", callback_data="btn_create_slide")],
                        [InlineKeyboardButton(text="📱 Mini Appni Ochish", web_app=WebAppInfo(url=config.WEBAPP_URL))],
                    ]
                )
            )
            database.record_reminder_sent(uid)
            sent_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail_count += 1

    await callback.message.answer(
        f"✅ <b>Retargeting xabarlari muvaffaqiyatli yakunlandi!</b>\n\n"
        f"📨 Yuborildi: {sent_count} ta foydalanuvchiga\n"
        f"❌ Yetib bormadi (bloklagan): {fail_count} ta",
        parse_mode="HTML",
        reply_markup=admin_menu_keyboard(),
    )


# To'g'ridan-to'g'ri yuborilgan audio, rasm va hujjatlarni qabul qilish
@router.message(F.voice)
async def handle_direct_voice(message: Message, state: FSMContext, bot: Bot):
    curr_state = await state.get_state()
    if curr_state:
        return
    user_id = message.from_user.id
    user_dict = database.get_or_create_user(user_id, message.from_user.first_name, message.from_user.username)
    if user_dict["slides_left"] <= 0 and not user_dict.get("is_vip"):
        await message.answer(
            "⚠️ Sizning balansingizda slaydlar qolmagan. Tariflar bo'limidan to'ldirishingiz mumkin.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💎 Tariflar & To'lov", callback_data="btn_tariffs")]])
        )
        return
    await state.set_state(SlideCreationState.waiting_for_topic)
    await process_voice_topic(message, state, bot)


@router.message(F.document)
async def handle_direct_document(message: Message, state: FSMContext, bot: Bot):
    curr_state = await state.get_state()
    if curr_state:
        return
    user_id = message.from_user.id
    user_dict = database.get_or_create_user(user_id, message.from_user.first_name, message.from_user.username)
    if user_dict["slides_left"] <= 0 and not user_dict.get("is_vip"):
        await message.answer(
            "⚠️ Sizning balansingizda slaydlar qolmagan. Tariflar bo'limidan to'ldirishingiz mumkin.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💎 Tariflar & To'lov", callback_data="btn_tariffs")]])
        )
        return
    await state.set_state(SlideCreationState.waiting_for_topic)
    await process_document_topic(message, state, bot)


@router.message(F.photo)
async def handle_direct_photo(message: Message, state: FSMContext, bot: Bot):
    curr_state = await state.get_state()
    if curr_state:
        return
    user_id = message.from_user.id
    user_dict = database.get_or_create_user(user_id, message.from_user.first_name, message.from_user.username)
    if user_dict["slides_left"] <= 0 and not user_dict.get("is_vip"):
        await message.answer(
            "⚠️ Sizning balansingizda slaydlar qolmagan. Tariflar bo'limidan to'ldirishingiz mumkin.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💎 Tariflar & To'lov", callback_data="btn_tariffs")]])
        )
        return
    await state.set_state(SlideCreationState.waiting_for_topic)
    await process_photo_topic(message, state, bot)


@router.callback_query(F.data == "btn_themes")
async def cb_themes_gallery(callback: CallbackQuery):
    await safe_callback_answer(callback)
    showcase_path = get_themes_showcase_path()

    photo = FSInputFile(showcase_path)
    text = (
        "🎨 <b>10 xil Professional Dizayn Shablonlari Ko'rgazmasi</b>\n\n"
        "Barcha dizayn shablonlarining haqiqiy 16:9 ko'rinishlari yuqoridagi rasmda aks etgan.\n\n"
        "🌙 <b>Dark Tech:</b> IT, dasturlash va texnologiya\n"
        "⚡️ <b>Cyberpunk:</b> Neon pushti va firuza (Futuristik)\n"
        "💼 <b>Corporate Blue:</b> Biznes, bank va rasmiy taqdimotlar\n"
        "🌿 <b>Emerald Green:</b> Ta'lim, ekologiya va tibbiyot\n"
        "🌅 <b>Modern Sunset:</b> Marketing, dizayn va startaplar\n"
        "☀️ <b>Silicon Valley:</b> Zamonaviy toza oq dizayn\n"
        "☕️ <b>Warm Editorial:</b> Gumanitar fanlar, adabiyot va tarix\n"
        "👑 <b>Midnight Gold:</b> VIP, premium va hashamatli loyihalar\n"
        "🌊 <b>Sapphire Ocean:</b> Ilmiy tadqiqotlar va dengiz moviyligi\n"
        "🍷 <b>Ruby Luxury:</b> San'at, moda va eksklyuziv taqdimotlar\n\n"
        "<i>Slayd yaratishda o'zingizga yoqqan shablonni tanlashingiz mumkin!</i>"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Slayd Yaratish", callback_data="btn_create_slide")],
            [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="btn_cancel")],
        ]
    )
    await callback.message.answer_photo(photo=photo, caption=text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "btn_help")
async def cb_help(callback: CallbackQuery):
    await safe_callback_answer(callback)
    text = (
        "ℹ️ <b>Slayd Yaratuvchi Bot (@SlaydchiAkabot) Haqida</b>\n\n"
        "Ushbu bot eng ilg'or sun'iy intellekt texnologiyalari asosida ishlaydi.\n\n"
        "<b>Imkoniyatlar:</b>\n"
        "• 16:9 Widescreen zamonaviy taqdimotlar (20 tagacha slayd)\n"
        "• Matn, 🎙 Ovozli xabar, 📸 Kitob/Konspekt rasmi yoki 📄 PDF/Word fayllardan slayd yasash\n"
        "• 📊 <b>Haqiqiy PowerPoint diagrammalari va grafiklari</b>\n"
        "• 🎤 <b>Har bir slayd uchun tayyor Spiker nutqi (so'zlash matni)</b>\n"
        "• 3 ta tilda yaratish (O'zbekcha, Ruscha, Inglizcha)\n"
        "• Do'stlarni taklif qilib qo'shimcha bepul limitlar olish\n"
        "• Maxsus promokodlardan foydalanish\n\n"
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
    return web.Response(text="@SlaydchiAkabot is running 24/7!")


async def handle_webapp(request):
    webapp_path = os.path.join(os.path.dirname(__file__), "templates", "webapp.html")
    if os.path.exists(webapp_path):
        with open(webapp_path, "r", encoding="utf-8") as f:
            return web.Response(text=f.read(), content_type="text/html")
    return web.Response(text="Web App template topilmadi.", status=404)


async def start_web_server():
    try:
        port = int(os.getenv("PORT", 8080))
        app = web.Application()
        app.router.add_get("/", handle_ping)
        app.router.add_get("/health", handle_ping)
        app.router.add_get("/webapp", handle_webapp)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Web server {port}-portda muvaffaqiyatli ishga tushdi (/webapp faol).")
    except Exception as e:
        logger.warning(f"Web server ogohlantirish: {e}")


async def main():
    token = config.BOT_TOKEN
    if not token or "QOYING" in token:
        logger.warning("⚠️ DIQQAT: BOT_TOKEN .env faylida to'g'ri o'rnatilmagan!")
        return

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
