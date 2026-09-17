import asyncio
import logging
import os
import sys
from typing import Dict, Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
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
from aiogram.exceptions import TelegramBadRequest

import config
from gemini_service import (
    generate_presentation_with_gemini,
    generate_mock_presentation,
    PresentationContent,
)
from slide_designer import create_presentation_file

# Logging sozlamalari - faylga va konsolga xavfsiz yozish
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

# Foydalanuvchi FSM holatlari
class SlideCreationState(StatesGroup):
    waiting_for_topic = State()
    waiting_for_slide_count = State()
    waiting_for_theme = State()


async def safe_callback_answer(callback: CallbackQuery, text: str = None, show_alert: bool = False):
    """Eskirgan yoki bekor qilingan querylar xatolik bermasligi uchun xavfsiz javob berish."""
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except Exception:
        pass


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚀 Yangi Slayd Yaratish", callback_data="btn_create_slide"),
            ],
            [
                InlineKeyboardButton(text="🎨 Dizayn Mavzulari", callback_data="btn_themes"),
                InlineKeyboardButton(text="ℹ️ Bot Haqida", callback_data="btn_help"),
            ],
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
                InlineKeyboardButton(text="10 ta (To'liq taqdimot)", callback_data="count_10"),
            ],
            [
                InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="btn_cancel"),
            ],
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


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_name = message.from_user.first_name if message.from_user else "Foydalanuvchi"

    text = (
        f"Assalomu alaykum, <b>{user_name}</b>!\n\n"
        f"Men <b>Professional Slayd Yaratuvchi</b> botman. Siz istagan mavzuni yozasiz, "
        f"men esa sun'iy intellekt yordamida zamonaviy 16:9 formatdagi, infografika va kartochkali "
        f"chiroyli <b>PowerPoint (.pptx)</b> taqdimot tayyorlab beraman.\n\n"
        f"Boshlash uchun quyidagi tugmani bosing:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "btn_cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_callback_answer(callback)
    try:
        await callback.message.edit_text(
            "Amal bekor qilindi. Bosh menyu:",
            reply_markup=main_menu_keyboard(),
        )
    except Exception:
        await callback.message.answer("Bosh menyu:", reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "btn_create_slide")
async def cb_start_create(callback: CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    await state.set_state(SlideCreationState.waiting_for_topic)
    text = (
        "✍️ <b>Taqdimot mavzusini kiriting:</b>\n\n"
        "<i>Masalan:</i>\n"
        "• Sun'iy intellektning tibbiyotdagi o'rni\n"
        "• Startap uchun Pitch Deck loyihasi\n"
        "• O'zbekistonda ekoturizmni rivojlantirish\n"
        "• Kiberxavfsizlik asoslari va himoya choralari\n\n"
        "Ixtiyoriy mavzuni yozib yuboring:"
    )
    try:
        await callback.message.edit_text(text, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, parse_mode="HTML")


@router.message(SlideCreationState.waiting_for_topic)
async def process_topic(message: Message, state: FSMContext):
    topic = (message.text or "").strip()
    if len(topic) < 3:
        await message.answer("Iltimos, mavzuni to'liqroq yozing (kamida 3 ta harf):")
        return

    await state.update_data(topic=topic)
    await state.set_state(SlideCreationState.waiting_for_slide_count)

    text = (
        f"📌 <b>Mavzu:</b> <i>{topic}</i>\n\n"
        f"Endi taqdimotda <b>nechta slayd</b> bo'lishini tanlang:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=slide_count_keyboard())


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
        f"📊 <b>Slaydlar soni:</b> {count} ta\n\n"
        f"🎨 <b>Dizayn va ranglar mavzusini tanlang:</b>"
    )
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=theme_selection_keyboard())
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=theme_selection_keyboard())


@router.callback_query(F.data.startswith("theme_"), SlideCreationState.waiting_for_theme)
async def process_theme_and_generate(callback: CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback, "Generatsiya boshlandi...")
    theme_key = callback.data.split("theme_")[1]
    data = await state.get_data()
    topic = data.get("topic", "Taqdimot")
    slide_count = data.get("slide_count", 5)
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

    # 1-qadam: Gemini orqali slaydlar rejasini yaratish (Admin kaliti asosida)
    presentation_content: PresentationContent
    try:
        if config.GEMINI_API_KEY:
            presentation_content = await generate_presentation_with_gemini(
                topic=topic,
                slide_count=slide_count,
                language="uz",
                api_key=config.GEMINI_API_KEY,
            )
        else:
            logger.warning("GEMINI_API_KEY sozlanmagan, mock ishlatilmoqda.")
            presentation_content = generate_mock_presentation(topic, slide_count=slide_count)
    except Exception as e:
        logger.error(f"AI generatsiyasida xatolik: {e}")
        presentation_content = generate_mock_presentation(topic, slide_count=slide_count)

    # 2-qadam: Slaydlarni chizish
    try:
        try:
            await status_msg.edit_text(
                f"⏳ <b>Taqdimot tayyorlanmoqda...</b>\n\n"
                f"📌 <b>Mavzu:</b> {topic}\n"
                f"🎨 <b>Dizayn:</b> {theme_info.emoji} {theme_info.name}\n\n"
                f"✅ <i>Kontent tayyorlandi!</i>\n"
                f"2️⃣ <i>16:9 formatda grafikalar, kartochkalar va infografikalar chizilmoqda...</i>",
                parse_mode="HTML",
            )
        except Exception:
            pass

        pptx_file_path = create_presentation_file(
            content=presentation_content,
            theme_key=theme_key,
        )

        caption = (
            f"🎉 <b>Taqdimotingiz tayyor!</b>\n\n"
            f"📌 <b>Mavzu:</b> {topic}\n"
            f"📊 <b>Slaydlar:</b> {len(presentation_content.slides)} ta\n"
            f"🎨 <b>Dizayn:</b> {theme_info.emoji} {theme_info.name}\n"
            f"📁 <b>Format:</b> Microsoft PowerPoint (.pptx)\n\n"
            f"💡 <i>Faylni PowerPoint, Google Slides yoki telefoningizdagi WPS Office orqali "
            f"to'liq ochishingiz va tahrirlashingiz mumkin.</i>"
        )

        action_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🚀 Yangi Slayd Yaratish", callback_data="btn_create_slide"),
                ],
                [
                    InlineKeyboardButton(text="🎨 Dizayn Mavzulari", callback_data="btn_themes"),
                ],
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
        logger.error(f"Slayd yaratishda xatolik: {e}")
        try:
            await status_msg.edit_text(
                "❌ <b>Slayd faylini tayyorlashda xatolik yuz berdi.</b>\n"
                "Iltimos, qaytadan urinib ko'ring yoki /start bosing.",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
        except Exception:
            await callback.message.answer(
                "❌ Slayd faylini tayyorlashda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.",
                reply_markup=main_menu_keyboard(),
            )


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
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "btn_help")
async def cb_help(callback: CallbackQuery):
    await safe_callback_answer(callback)
    text = (
        "ℹ️ <b>Slayd Yaratuvchi Bot Haqida</b>\n\n"
        "Ushbu bot eng ilg'or sun'iy intellekt texnologiyalari asosida ishlaydi "
        "va professional darajadagi taqdimotlarni bir necha soniyada tayyorlab beradi.\n\n"
        "<b>Imkoniyatlar:</b>\n"
        "• 16:9 Widescreen zamonaviy taqdimotlar\n"
        "• Avtomatik vizual modullar: kartochkalar, infografika, raqamlar, solishtirish jadvallari, timeline bosqichlari\n"
        "• 5 ta zamonaviy rang mavzulari\n"
        "• Microsoft PowerPoint, Google Slides va WPS Office formatida yuklab olish\n\n"
        "Boshlash uchun pastdagi tugmani bosing:"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Slayd Yaratish", callback_data="btn_create_slide")],
            [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="btn_cancel")],
        ]
    )
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Faqat bot egasi uchun maxfiy admin paneli."""
    user_id = str(message.from_user.id)
    if config.ADMIN_ID and user_id != config.ADMIN_ID:
        return

    api_configured = "✅ Sozlangan" if config.GEMINI_API_KEY else "❌ Sozlanmagan"
    slides_count = len(os.listdir("generated_slides")) if os.path.exists("generated_slides") else 0

    text = (
        "👑 <b>Admin Paneli (Faqat Bot Egasi Uchun)</b>\n\n"
        f"🤖 <b>Bot holati:</b> Ishlamoqda (24/7)\n"
        f"🔑 <b>Gemini API:</b> {api_configured}\n"
        f"📊 <b>Generatsiya qilingan jami slaydlar:</b> {slides_count} ta\n"
        f"⚙️ <b>Model:</b> <code>{config.GEMINI_MODEL}</code>\n"
    )
    await message.answer(text, parse_mode="HTML")


async def main():
    token = config.BOT_TOKEN
    if not token or "QOYING" in token:
        logger.warning("⚠️ DIQQAT: BOT_TOKEN .env faylida to'g'ri o'rnatilmagan!")
        return

    bot = Bot(token=token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logger.info("Bot fonda muvaffaqiyatli ishga tushdi...")
    
    while True:
        try:
            # Eski to'planib qolgan eskirgan so'rovlarni o'chirish (bad request bo'lmasligi uchun)
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
