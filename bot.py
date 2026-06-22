"""
Fayda Digital ID → Physical ID Card Telegram Bot

Converts vertical Fayda Digital Ethiopian National ID screenshots (front & back)
into horizontal physical ID card images.

Usage:
    1. Send /start to the bot
    2. Send the front ID screenshot
    3. Send the back ID screenshot
    4. Receive the filled horizontal ID card (front & back)
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

from cropper import crop_photo, crop_qr, image_to_bytes
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
WAITING_FRONT, WAITING_BACK, CONFIRMING_DATA, WAITING_EDIT_VALUE = range(4)

# Template path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "national_id_blank.png")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send welcome message and ask for front ID screenshot."""
    await update.message.reply_text(
        "🇪🇹 *Fayda ID Card Converter*\n\n"
        "I'll convert your vertical Fayda Digital ID screenshots "
        "into horizontal physical ID card format\\.\n\n"
        "📸 *Step 1:* Send me the *FRONT* of your Fayda Digital ID screenshot\\.",
        parse_mode="MarkdownV2",
    )
    return WAITING_FRONT


async def receive_front(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and store the front ID screenshot, ask for back."""
    if not update.message.photo and not update.message.document:
        await update.message.reply_text(
            "⚠️ Please send the front ID as a *photo* or *document*\\.",
            parse_mode="MarkdownV2",
        )
        return WAITING_FRONT

    # Get the highest resolution photo
    if update.message.photo:
        photo = update.message.photo[-1]  # Highest resolution
        file = await photo.get_file()
    else:
        file = await update.message.document.get_file()

    # Download the image
    buf = io.BytesIO()
    await file.download_to_memory(buf)
    context.user_data["front_image"] = buf.getvalue()

    await update.message.reply_text(
        "✅ Front ID received\\!\n\n"
        "📸 *Step 2:* Now send me the *BACK* of your Fayda Digital ID screenshot\\.",
        parse_mode="MarkdownV2",
    )
    return WAITING_BACK


async def receive_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive back ID screenshot, extract data, and present preview for verification."""
    if not update.message.photo and not update.message.document:
        await update.message.reply_text(
            "⚠️ Please send the back ID as a *photo* or *document*\\.",
            parse_mode="MarkdownV2",
        )
        return WAITING_BACK

    # Get the highest resolution photo
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
            "❌ Something went wrong\\. Please start over with /start\\.",
            parse_mode="MarkdownV2",
        )
        return ConversationHandler.END

    await update.message.reply_text("⏳ Extracting details with Gemini Vision API... This may take a moment.")

    try:
        # Step 1: Extract data using Gemini Vision API
        logger.info("Extracting ID data with Gemini Vision API...")
        data = extract_id_data(front_image_bytes, back_image_bytes)
        logger.info(f"Extracted data: {data}")

        # Store data and image bytes in session for editing
        context.user_data["extracted_data"] = data
        context.user_data["back_image"] = back_image_bytes

        # Show verification screen
        await send_preview(update, context)
        return CONFIRMING_DATA

    except Exception as e:
        logger.error(f"Error extracting ID data: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ An error occurred while extracting ID data:\n`{str(e)[:200]}`\n\n"
            "Please try again with /start\\.",
            parse_mode="MarkdownV2",
        )
        context.user_data.clear()
        return ConversationHandler.END


async def send_preview(update_or_query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send or edit the message to display a preview of extracted fields and the verification keyboard."""
    data = context.user_data["extracted_data"]

    preview_text = (
        "🔍 <b>Please verify the extracted data:</b>\n\n"
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
        "If everything is correct, click <b>Confirm & Generate Card</b>. Otherwise, click any button below to edit a field."
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
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if isinstance(update_or_query, CallbackQuery):
        await update_or_query.edit_message_text(preview_text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update_or_query.message.reply_text(preview_text, parse_mode="HTML", reply_markup=reply_markup)


async def handle_preview_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle callback button clicks on the verification screen."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "confirm_generate":
        await query.edit_message_text("⏳ Generating card components and composing template... Please wait.")
        await generate_card_and_send(query, context)
        return ConversationHandler.END
    elif data.startswith("edit_"):
        field = data[5:]
        context.user_data["edit_target"] = field

        field_labels = {
            "full_name_amharic": "Full Name (Amharic)",
            "full_name_english": "Full Name (English)",
            "date_of_birth": "Date of Birth (e.g. 03/08/1991 | 1999/Apr/11)",
            "sex_amharic": "Sex (Amharic)",
            "sex_english": "Sex (English)",
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
            f"✏️ Please send the corrected value for <b>{label}</b>:",
            parse_mode="HTML"
        )
        return WAITING_EDIT_VALUE


async def receive_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the text correction for a field and show the updated preview."""
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
    """Generate the card image/PDF and send them to the Telegram user."""
    front_image_bytes = context.user_data.get("front_image")
    back_image_bytes = context.user_data.get("back_image")
    data = context.user_data.get("extracted_data")

    if not front_image_bytes or not back_image_bytes or not data:
        await query.message.reply_text("❌ Missing ID data. Please start over with /start.")
        return

    try:
        # Step 2: Crop photo and QR from the input images
        logger.info("Cropping photo and QR code...")
        front_img = Image.open(io.BytesIO(front_image_bytes))
        back_img = Image.open(io.BytesIO(back_image_bytes))

        photo = crop_photo(front_img)
        qr = crop_qr(back_img)

        # Step 3: Compose the combined horizontal card
        logger.info("Composing combined ID card...")
        result = compose_id(data, photo, qr, template_path=TEMPLATE_PATH)

        # Step 3b: Mirror the card and create the A4 printable version
        logger.info("Mirroring card and creating A4 PDF...")
        mirrored_card = mirror_image(result)
        a4_canvas = create_a4_printable(result)

        # Step 4: Send results back
        # PNG: Send as a visible inline photo (not a downloadable file)
        # Downsize for Telegram display — users print from the PDF, not the PNG
        display_card = mirrored_card.copy()
        max_display_w = 1280
        if display_card.width > max_display_w:
            ratio = max_display_w / display_card.width
            display_card = display_card.resize(
                (max_display_w, int(display_card.height * ratio)), Image.LANCZOS
            )
        png_buf = io.BytesIO()
        display_card.save(png_buf, format="JPEG", quality=85)
        png_buf.seek(0)

        pdf_buf = io.BytesIO()
        a4_canvas.save(pdf_buf, format="PDF", resolution=800.0, quality=100)
        pdf_buf.seek(0)

        # Send the card as a visible photo in the chat
        await query.message.reply_photo(
            photo=png_buf,
            caption="🪪 Mirrored Physical ID Card Preview",
            write_timeout=60,
        )

        # Send the high-quality printable A4 PDF as a downloadable document
        await query.message.reply_document(
            document=pdf_buf,
            filename="fayda_printable_a4.pdf",
            caption="🖨️ Printable A4 PDF — print this file for the physical card",
            write_timeout=180,
            disable_content_type_detection=True,
        )

        await query.message.reply_text(
            "✅ Done! Your physical ID card resources are ready.\n\n"
            "Send /start to convert another digital ID."
        )

    except Exception as e:
        logger.error(f"Error processing final ID: {e}", exc_info=True)
        await query.message.reply_text(
            f"❌ An error occurred during card generation:\n`{str(e)[:200]}`\n\n"
            "Please try again with /start.",
            parse_mode="Markdown",
        )
    finally:
        context.user_data.clear()


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current conversation."""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Cancelled\\. Send /start to begin again\\.",
        parse_mode="MarkdownV2",
    )
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help message."""
    await update.message.reply_text(
        "🇪🇹 *Fayda ID Card Converter*\n\n"
        "*How to use:*\n"
        "1\\. Send /start to begin\n"
        "2\\. Send the FRONT screenshot of your vertical Fayda Digital ID\n"
        "3\\. Send the BACK screenshot of your vertical Fayda Digital ID\n"
        "4\\. Receive your horizontal physical ID card \\(front \\& back\\)\n\n"
        "*Commands:*\n"
        "/start \\- Begin conversion\n"
        "/cancel \\- Cancel current conversion\n"
        "/help \\- Show this help message",
        parse_mode="MarkdownV2",
    )


def main():
    """Start the bot."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

    # Verify Gemini API key is set
    if not os.getenv("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY environment variable is not set")

    # Build the application
    application = Application.builder().token(token).build()

    # Conversation handler for the ID conversion flow
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FRONT: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_front),
            ],
            WAITING_BACK: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_back),
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

    # Start polling
    logger.info("Bot started! Waiting for messages...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
