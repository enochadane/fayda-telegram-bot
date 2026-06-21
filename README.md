# Fayda Digital ID → Physical ID Card Telegram Bot

This Telegram bot converts vertical Fayda Digital Ethiopian National ID screenshots (front & back) into a horizontal physical ID card format (both standard mirrored PNG and a print-ready A4 PDF format).

It extracts all ID fields using the Google Gemini Vision API, allows you to verify and edit the extracted data inline within Telegram, and then automatically generates:
1. **Mirrored Front & Back Images** (perfect for thermal/card printers).
2. **Printable A4 PDF** (with the exact dimensions aligned to the top of the page).

---

## 🛠️ Installation & Setup

### 1. Prerequisites
- **Python 3.10 or higher**
- A **Telegram Bot Token** (from [@BotFather](https://t.me/BotFather))
- A **Google Gemini API Key** (from [Google AI Studio](https://aistudio.google.com/))

### 2. Install Dependencies
Clone the repository, navigate into the directory, and run:
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Create a `.env` file in the root directory (if not already present) and populate it with your keys:
```env
TELEGRAM_BOT_TOKEN="your-telegram-bot-token-here"
GEMINI_API_KEY="your-gemini-api-key-here"
```

---

## 🚀 How to Run the Bot

To start the Telegram bot, run the following command in your terminal:
```bash
python bot.py
```

You should see a log message:
`Bot started! Waiting for messages...`

---

## 🧪 Step-by-Step Testing Flow

Follow these steps in Telegram to verify the entire pipeline:

1. **Start the Bot**:
   - Search for your bot on Telegram and click **Start** or send `/start`.
   - The bot will greet you and ask you to upload the **FRONT** screenshot of the Fayda Digital ID.

2. **Upload Front ID**:
   - Send the front ID screenshot (e.g., the reference image in `sample-input/front.PNG`).
   - You can send it either as a **Photo** or as a **Document (uncompressed)**.
   - The bot will confirm and ask for the **BACK** screenshot.

3. **Upload Back ID**:
   - Send the back ID screenshot (e.g., the reference image in `sample-input/back.PNG`).
   - The bot will display a loading message: `"⏳ Extracting details with Gemini Vision API... This may take a moment."`

4. **Verify Extracted Data**:
   - Once extraction is complete, the bot will display all 16 extracted fields in a clean HTML-formatted list.
   - Below the list, there will be an inline keyboard of buttons representing each field, plus a **"✅ Confirm & Generate Card"** button.

5. **Edit Data (Optional)**:
   - To correct any field, click its button (e.g., **"📝 Name (Eng)"** or **"🔢 FIN"**).
   - The bot will prompt you: `"✏️ Please send the corrected value for..."`
   - Type and send the new text.
   - The bot will update the data in memory, refresh the preview list, and show the updated fields.

6. **Confirm & Generate Card**:
   - Click the **"✅ Confirm & Generate Card"** button.
   - The bot will process the images:
     - Crop the portrait photo (zoomed out to show the head, hair, and both shoulders).
     - Crop the QR code from the back screenshot.
     - Generate a new horizontal national ID composite, mirroring the front/back components.
     - Generate a standard-aligned printable A4 PDF.
   - The bot will send you:
     - `fayda_mirrored_id.png` (PNG Image Document)
     - `fayda_printable_a4.pdf` (Printable A4 PDF)

7. **Cancel at Any Time**:
   - Send `/cancel` during the flow to reset the session.

---

## 📂 Project Structure

```
├── bot.py             # Bot conversation flow & Telegram logic
├── extractor.py       # Gemini Vision API integration for data extraction
├── cropper.py         # Precise PIL cropping parameters for photo/QR codes
├── compositor.py      # Layout composition, barcode generation, PDF assembly
├── requirements.txt   # List of dependencies
├── templates/
│   └── national_id_blank.png  # Base template used for physical layout rendering
├── fonts/
│   ├── NotoSans.ttf
│   └── NotoSansEthiopic.ttf   # Supporting fonts for English & Amharic script
├── sample-input/      # Sample inputs for testing
└── expected-output/   # Reference outputs for alignment checks
```
