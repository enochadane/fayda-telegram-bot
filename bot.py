"""
Fayda Digital ID → Physical ID Card Telegram Bot

Converts Fayda Digital Ethiopian National ID screenshots (front & back)
OR manually entered text & photo into horizontal physical ID card images.
"""

import io
import logging
import os

from dotenv import load_dotenv
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

from cropper import crop_photo, crop_qr, image_to_bytes, generate_qr_code
from extractor import extract_id_data
from compositor import compose_id, mirror_image, create_a4_printable

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Conversation states
(
    SELECTING_MODE,
    WAITING_FRONT,
    WAITING_BACK,
    WAITING_MANUAL_PHOTO,
    WAITING_MANUAL_QR,
    CONFIRMING_DATA,
    WAITING_EDIT_VALUE,
) = range(7)

# Template path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "national_id_blank.png")


DEFAULT_MANUAL_DATA = {
    "full_name_amharic": "ሙሉ ስም",
    "full_name_english": "Full Name",
    "date_of_birth": "03/08/1991 | 1999/Apr/11",
    "sex_amharic": "ወንድ",
    "sex_english": "Male",
    "date_of_expiry": "2026/08/26 | 2034/May/04",
    "date_of_issue": "2018/08/28 | 2026/May/06",
    "fan": "2941370269506215",
    "phone_number": "0911000000",
    "fin": "2980 2376 9475",
    "nationality_amharic": "ኢትዮጵያዊ",
    "nationality_english": "Ethiopian",
    "region_amharic": "አዲስ አበባ",
    "region_english": "Addis Ababa",
    "zone_amharic": "አዲስ አበባ",
    "zone_english": "Addis Ababa",
    "woreda_amharic": "ወረዳ 01",
    "woreda_english": "Woreda 01",
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send welcome message and ask user to select conversion mode."""
    context.user_data.clear()

    keyboard = [
        [
            InlineKeyboardButton("📸 Upload Digital ID Screenshots (OCR)", callback_data="mode_ocr"),
        ],
        [
            InlineKeyboardButton("✍️ Manual Entry (Text & Photo)", callback_data="mode_manual"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🇪🇹 <b>Fayda ID Card Converter</b>\n\n"
        "Welcome! How would you like to create your physical Fayda ID card?\n\n"
        "1️⃣ <b>Upload Screenshots:</b> Send front & back vertical ID screenshots (automated OCR via Gemini).\n"
        "2️⃣ <b>Manual Entry:</b> Upload a portrait photo and manually enter/edit the text fields.",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )
    return SELECTING_MODE


async def select_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle mode selection callback."""
    query = update.callback_query
    await query.answer()

    if query.data == "mode_ocr":
        context.user_data["mode"] = "ocr"
        await query.edit_message_text(
            "📸 <b>Step 1:</b> Please send me the <b>FRONT</b> of your Fayda Digital ID screenshot.",
            parse_mode="HTML",
        )
        return WAITING_FRONT

    elif query.data == "mode_manual":
        context.user_data["mode"] = "manual"
        await query.edit_message_text(
            "✍️ <b>Manual Entry Mode</b>\n\n"
            "📸 <b>Step 1:</b> Please send the <b>Person's Portrait Photo</b> (as a photo or file document).",
            parse_mode="HTML",
        )
        return WAITING_MANUAL_PHOTO

    return SELECTING_MODE


async def receive_front(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and store the front ID screenshot, ask for back."""
    if not update.message.photo and not update.message.document:
        await update.message.reply_text(
            "⚠️ Please send the front ID as a <b>photo</b> or <b>document</b>.",
            parse_mode="HTML",
        )
        return WAITING_FRONT

    if update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
    else:
        file = await update.message.document.get_file()

    buf = io.BytesIO()
    await file.download_to_memory(buf)
    context.user_data["front_image"] = buf.getvalue()

    await update.message.reply_text(
        "✅ Front ID received!\n\n"
        "📸 <b>Step 2:</b> Now send me the <b>BACK</b> of your Fayda Digital ID screenshot.",
        parse_mode="HTML",
    )
    return WAITING_BACK


async def receive_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive back ID screenshot, extract data, and present preview for verification."""
    if not update.message.photo and not update.message.document:
        await update.message.reply_text(
            "⚠️ Please send the back ID as a <b>photo</b> or <b>document</b>.",
            parse_mode="HTML",
        )
        return WAITING_BACK

    if update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
    else:
        file = await update.message.document.get_file()

    buf = io.BytesIO()
    await file.download_to_memory(buf)
    back_image_bytes = buf.getvalue()
    front_image_bytes = context.user_data.get("front_image")

    if not front_image_bytes:
        await update.message.reply_text(
            "❌ Something went wrong. Please start over with /start.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    await update.message.reply_text("⏳ Extracting details with Gemini Vision API... This may take a moment.")

    try:
        logger.info("Extracting ID data with Gemini Vision API...")
        data = extract_id_data(front_image_bytes, back_image_bytes)
        logger.info(f"Extracted data: {data}")

        context.user_data["extracted_data"] = data
        context.user_data["back_image"] = back_image_bytes

        await send_preview(update, context)
        return CONFIRMING_DATA

    except Exception as e:
        logger.error(f"Error extracting ID data: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ An error occurred while extracting ID data:\n<code>{str(e)[:200]}</code>\n\n"
            "Please try again with /start.",
            parse_mode="HTML",
        )
        context.user_data.clear()
        return ConversationHandler.END


async def receive_manual_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive person photo in manual mode and prompt for QR image or skip."""
    if not update.message.photo and not update.message.document:
        await update.message.reply_text(
            "⚠️ Please send the portrait image as a <b>photo</b> or <b>document</b>.",
            parse_mode="HTML",
        )
        return WAITING_MANUAL_PHOTO

    if update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
    else:
        file = await update.message.document.get_file()

    buf = io.BytesIO()
    await file.download_to_memory(buf)
    context.user_data["photo_bytes"] = buf.getvalue()

    keyboard = [
        [
            InlineKeyboardButton("⏩ Skip & Auto-Generate QR", callback_data="skip_qr"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "✅ Portrait photo received!\n\n"
        "📱 <b>Step 2 (Optional):</b> Send an image of the <b>QR Code</b>.\n"
        "If you don't have one, click <b>Skip & Auto-Generate QR</b> below.",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )
    return WAITING_MANUAL_QR


async def receive_manual_qr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive QR code image in manual mode and move to text entry/preview."""
    if update.message.photo or update.message.document:
        if update.message.photo:
            photo = update.message.photo[-1]
            file = await photo.get_file()
        else:
            file = await update.message.document.get_file()

        buf = io.BytesIO()
        await file.download_to_memory(buf)
        context.user_data["qr_bytes"] = buf.getvalue()
        await update.message.reply_text("✅ QR Code image received!")
    else:
        context.user_data["qr_bytes"] = None

    if "extracted_data" not in context.user_data:
        context.user_data["extracted_data"] = DEFAULT_MANUAL_DATA.copy()

    await send_preview(update, context)
    return CONFIRMING_DATA


async def handle_skip_qr_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle skipping QR upload in manual mode."""
    query = update.callback_query
    await query.answer()

    context.user_data["qr_bytes"] = None
    if "extracted_data" not in context.user_data:
        context.user_data["extracted_data"] = DEFAULT_MANUAL_DATA.copy()

    await query.edit_message_text("⚡ Auto-generating QR code for card composition...")
    await send_preview(query, context)
    return CONFIRMING_DATA


async def send_preview(update_or_query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display preview of fields and interactive edit buttons."""
    data = context.user_data["extracted_data"]

    preview_text = (
        "🔍 <b>Please verify / edit the card data:</b>\n\n"
        f"👤 <b>Name (Amh):</b> {data.get('full_name_amharic', '')}\n"
        f"👤 <b>Name (Eng):</b> {data.get('full_name_english', '')}\n"
        f"📅 <b>Date of Birth:</b> {data.get('date_of_birth', '')}\n"
        f"⚧ <b>Sex (Amh/Eng):</b> {data.get('sex_amharic', '')} | {data.get('sex_english', '')}\n"
        f"📅 <b>Date of Expiry:</b> {data.get('date_of_expiry', '')}\n"
        f"📅 <b>Date of Issue:</b> {data.get('date_of_issue', '')}\n"
        f"🔢 <b>FAN:</b> {data.get('fan', '')}\n"
        f"📞 <b>Phone Number:</b> {data.get('phone_number', '')}\n"
        f"🔢 <b>FIN:</b> {data.get('fin', '')}\n\n"
        f"📍 <b>Region (Amh/Eng):</b> {data.get('region_amharic', '')} | {data.get('region_english', '')}\n"
        f"📍 <b>Zone (Amh/Eng):</b> {data.get('zone_amharic', '')} | {data.get('zone_english', '')}\n"
        f"📍 <b>Woreda (Amh/Eng):</b> {data.get('woreda_amharic', '')} | {data.get('woreda_english', '')}\n\n"
        "Click any button below to edit a field. When ready, click <b>Confirm & Generate Card</b>."
    )

    keyboard = [
        [
            InlineKeyboardButton("📝 Name (Amh)", callback_data="edit_full_name_amharic"),
            InlineKeyboardButton("📝 Name (Eng)", callback_data="edit_full_name_english"),
        ],
        [
            InlineKeyboardButton("📅 Date of Birth", callback_data="edit_date_of_birth"),
            InlineKeyboardButton("⚧ Sex (Amh)", callback_data="edit_sex_amharic"),
        ],
        [
            InlineKeyboardButton("⚧ Sex (Eng)", callback_data="edit_sex_english"),
            InlineKeyboardButton("📅 Expiry Date", callback_data="edit_date_of_expiry"),
        ],
        [
            InlineKeyboardButton("📅 Issue Date", callback_data="edit_date_of_issue"),
            InlineKeyboardButton("🔢 FAN", callback_data="edit_fan"),
        ],
        [
            InlineKeyboardButton("📞 Phone", callback_data="edit_phone_number"),
            InlineKeyboardButton("🔢 FIN", callback_data="edit_fin"),
        ],
        [
            InlineKeyboardButton("📍 Region (Amh)", callback_data="edit_region_amharic"),
            InlineKeyboardButton("📍 Region (Eng)", callback_data="edit_region_english"),
        ],
        [
            InlineKeyboardButton("📍 Zone (Amh)", callback_data="edit_zone_amharic"),
            InlineKeyboardButton("📍 Zone (Eng)", callback_data="edit_zone_english"),
        ],
        [
            InlineKeyboardButton("📍 Woreda (Amh)", callback_data="edit_woreda_amharic"),
            InlineKeyboardButton("📍 Woreda (Eng)", callback_data="edit_woreda_english"),
        ],
        [
            InlineKeyboardButton("✅ Confirm & Generate Card", callback_data="confirm_generate"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if isinstance(update_or_query, CallbackQuery):
        await update_or_query.edit_message_text(preview_text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update_or_query.message.reply_text(preview_text, parse_mode="HTML", reply_markup=reply_markup)


async def handle_preview_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle button clicks on the verification screen."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "confirm_generate":
        await query.edit_message_text("⏳ Generating card components and composing template... Please wait.")
        await generate_card_and_send(query, context)
        return ConversationHandler.END

    elif data == "skip_qr":
        return await handle_skip_qr_callback(update, context)

    elif data.startswith("edit_"):
        field = data[5:]
        context.user_data["edit_target"] = field

        field_labels = {
            "full_name_amharic": "Full Name (Amharic)",
            "full_name_english": "Full Name (English)",
            "date_of_birth": "Date of Birth (e.g. 03/08/1991 | 1999/Apr/11)",
            "sex_amharic": "Sex (Amharic - e.g. ወንድ)",
            "sex_english": "Sex (English - e.g. Male)",
            "date_of_expiry": "Date of Expiry (e.g. 2026/08/26 | 2034/May/04)",
            "date_of_issue": "Date of Issue (e.g. 2018/08/28 | 2026/May/06)",
            "fan": "FAN (16 digits)",
            "phone_number": "Phone Number",
            "fin": "FIN (12 digits, e.g. 2980 2376 9475)",
            "region_amharic": "Region (Amharic)",
            "region_english": "Region (English)",
            "zone_amharic": "Zone (Amharic)",
            "zone_english": "Zone (English)",
            "woreda_amharic": "Woreda (Amharic)",
            "woreda_english": "Woreda (English)",
        }

        label = field_labels.get(field, field)
        await query.message.reply_text(
            f"✏️ Please send the new value for <b>{label}</b>:",
            parse_mode="HTML",
        )
        return WAITING_EDIT_VALUE

    return CONFIRMING_DATA


async def receive_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive updated text value for a field."""
    field = context.user_data.get("edit_target")
    if not field:
        await update.message.reply_text("❌ Session expired or invalid. Please start over with /start.")
        context.user_data.clear()
        return ConversationHandler.END

    new_value = update.message.text.strip()
    context.user_data["extracted_data"][field] = new_value

    await update.message.reply_text("✅ Field updated successfully!")
    await send_preview(update, context)
    return CONFIRMING_DATA


async def generate_card_and_send(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate physical card image and A4 printable document."""
    data = context.user_data.get("extracted_data")
    mode = context.user_data.get("mode", "ocr")

    if not data:
        await query.message.reply_text("❌ Missing ID data. Please start over with /start.")
        return

    try:
        photo = None
        qr = None

        if mode == "ocr":
            front_image_bytes = context.user_data.get("front_image")
            back_image_bytes = context.user_data.get("back_image")
            if not front_image_bytes or not back_image_bytes:
                await query.message.reply_text("❌ Missing screenshot images. Please restart with /start.")
                return

            front_img = Image.open(io.BytesIO(front_image_bytes))
            back_img = Image.open(io.BytesIO(back_image_bytes))
            photo = crop_photo(front_img)
            qr = crop_qr(back_img)

        else:
            photo_bytes = context.user_data.get("photo_bytes")
            if not photo_bytes:
                await query.message.reply_text("❌ Missing photo. Please restart with /start.")
                return

            photo = Image.open(io.BytesIO(photo_bytes))
            qr_bytes = context.user_data.get("qr_bytes")

            if qr_bytes:
                qr_raw = Image.open(io.BytesIO(qr_bytes))
                s = min(qr_raw.width, qr_raw.height)
                cx, cy = qr_raw.width // 2, qr_raw.height // 2
                qr = qr_raw.crop((cx - s // 2, cy - s // 2, cx + s // 2, cy + s // 2))
            else:
                qr = generate_qr_code(data, photo_img=photo)



        logger.info("Composing combined ID card...")
        result = compose_id(data, photo, qr, template_path=TEMPLATE_PATH)

        logger.info("Mirroring card and creating A4 printable canvas...")
        mirrored_card = mirror_image(result)
        a4_canvas, pdf_dpi = create_a4_printable(result)

        display_card = mirrored_card.copy()
        max_display_w = 1280
        if display_card.width > max_display_w:
            ratio = max_display_w / display_card.width
            display_card = display_card.resize(
                (max_display_w, int(display_card.height * ratio)), Image.LANCZOS
            )
        preview_buf = io.BytesIO()
        display_card.save(preview_buf, format="JPEG", quality=85)
        preview_buf.seek(0)

        a4_png_buf = io.BytesIO()
        a4_canvas.save(a4_png_buf, format="PNG", dpi=(pdf_dpi, pdf_dpi))
        a4_png_buf.seek(0)

        await query.message.reply_photo(
            photo=preview_buf,
            caption="🪪 Mirrored Physical ID Card Preview",
            write_timeout=60,
        )

        await query.message.reply_document(
            document=a4_png_buf,
            filename="fayda_printable_a4.png",
            caption="🖨️ Lossless A4 PNG — print this file at 100% scale for exact physical card sizing",
            write_timeout=180,
            disable_content_type_detection=True,
        )

        await query.message.reply_text(
            "✅ Done! Your physical ID card resources are ready.\n\n"
            "Send /start to convert another ID."
        )

    except Exception as e:
        logger.error(f"Error processing final ID: {e}", exc_info=True)
        await query.message.reply_text(
            f"❌ An error occurred during card generation:\n<code>{str(e)[:200]}</code>\n\n"
            "Please try again with /start.",
            parse_mode="HTML",
        )
    finally:
        context.user_data.clear()


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current conversation."""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Cancelled. Send /start to begin again.",
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help message."""
    await update.message.reply_text(
        "🇪🇹 <b>Fayda ID Card Converter</b>\n\n"
        "<b>How to use:</b>\n"
        "1. Send /start to begin\n"
        "2. Choose <b>Upload Screenshots</b> OR <b>Manual Entry</b>\n"
        "3. Follow the quick instructions to verify text & photo\n"
        "4. Receive your printable horizontal physical ID card!\n\n"
        "<b>Commands:</b>\n"
        "/start - Begin conversion\n"
        "/cancel - Cancel current conversion\n"
        "/help - Show this help message",
        parse_mode="HTML",
    )


def main():
    """Start the bot."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

    application = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_MODE: [
                CallbackQueryHandler(select_mode_callback, pattern="^mode_"),
            ],
            WAITING_FRONT: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_front),
            ],
            WAITING_BACK: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_back),
            ],
            WAITING_MANUAL_PHOTO: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_manual_photo),
            ],
            WAITING_MANUAL_QR: [
                CallbackQueryHandler(handle_skip_qr_callback, pattern="^skip_qr$"),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_manual_qr),
            ],
            CONFIRMING_DATA: [
                CallbackQueryHandler(handle_preview_callback),
            ],
            WAITING_EDIT_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit_value),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))

    logger.info("Bot started! Waiting for messages...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
