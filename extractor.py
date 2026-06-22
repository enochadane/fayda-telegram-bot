"""
Extract structured data from vertical Fayda Digital ID screenshots using Google Gemini Vision API.
"""

import json
import os
from google import genai
from google.genai import types


def get_client() -> genai.Client:
    """Create a Gemini client using the API key from environment."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set")
    return genai.Client(api_key=api_key)


def extract_id_data(front_image_bytes: bytes, back_image_bytes: bytes) -> dict:
    """
    Send front and back ID screenshots to Gemini Vision API and extract
    all structured fields.

    Args:
        front_image_bytes: Bytes of the front vertical ID screenshot.
        back_image_bytes: Bytes of the back vertical ID screenshot.

    Returns:
        Dictionary with all extracted fields:
        {
            "full_name_amharic": str,
            "full_name_english": str,
            "date_of_birth": str,       # e.g. "03/08/1991 | 1999/Apr/11"
            "sex_amharic": str,          # e.g. "ወንድ"
            "sex_english": str,          # e.g. "Male"
            "date_of_expiry": str,       # e.g. "2026/08/26 | 2034/May/04"
            "date_of_issue": str,        # e.g. "2018/08/28 | 2026/May/06"
            "fan": str,                  # e.g. "2941370269506215"
            "phone_number": str,         # e.g. "0961418686"
            "fin": str,                  # e.g. "2980 2376 9475"
            "nationality_amharic": str,  # e.g. "ኢትዮጵያ"
            "nationality_english": str,  # e.g. "Ethiopian"
            "region_amharic": str,
            "region_english": str,
            "zone_amharic": str,
            "zone_english": str,
            "woreda_amharic": str,
            "woreda_english": str,
        }
    """
    client = get_client()

    prompt = """You are an OCR specialist analyzing two screenshots of an Ethiopian Fayda Digital National ID card (vertical format).

The FIRST image is the FRONT of the card. It contains:
- A portrait photo
- Full Name in Amharic script (ሙሉ ስም) and in English (Full Name) — these are TWO SEPARATE lines of text
- Date of Birth (in both Gregorian and Ethiopian calendar, separated by " | ")
- Sex in Amharic (ፆታ) and in English (Sex)
- Date of Expiry (in both Gregorian and Ethiopian calendar, separated by " | ")
- Date of Issue (rotated text on the right side, in both Gregorian and Ethiopian calendar, separated by " | ")
- FAN number (Fayda Application Number, a long numeric string shown with a barcode)

The SECOND image is the BACK of the card. It contains:
- A large QR code
- Phone Number
- FIN (Fayda Identification Number, formatted with spaces like "2980 2376 9475")
- Nationality in Amharic and English
- Address with Region, Zone, and Woreda/Town (each in Amharic and English on separate lines)

CRITICAL INSTRUCTIONS FOR AMHARIC TEXT:
- You MUST perform OCR (optical character recognition) to read the ACTUAL Amharic/Ethiopic (ግዕዝ) characters printed on the card.
- DO NOT translate the English text into Amharic. The Amharic text is ALREADY PRINTED on the card as a separate line.
- The Amharic name and the English name may look different — they are independently written on the card.
- For example, a name like "ሄኖክ አዳነ ጥምደዶ" is ALREADY on the card — read it directly, do NOT attempt to transliterate "Henok Adane Tumdedo" into Amharic.
- Same applies to Region, Zone, Woreda, Sex, and Nationality — each has its own Amharic text printed on the card.

Extract ALL the text data from both images and return ONLY a JSON object with these exact keys:
{
    "full_name_amharic": "the EXACT Amharic text as printed on the card for the name",
    "full_name_english": "the EXACT English text as printed on the card for the name",
    "date_of_birth": "the complete DOB string including both calendar formats separated by ' | '",
    "sex_amharic": "the EXACT Amharic text for sex as printed on the card (e.g. ወንድ or ሴት)",
    "sex_english": "the EXACT English text for sex as printed on the card (e.g. Male or Female)",
    "date_of_expiry": "the complete expiry string including both calendar formats separated by ' | '",
    "date_of_issue": "the complete issue date string including both calendar formats separated by ' | '",
    "fan": "the FAN number (digits only, no spaces)",
    "phone_number": "the phone number",
    "fin": "the FIN number (with spaces as shown)",
    "nationality_amharic": "the EXACT Amharic nationality text as printed (e.g. ኢትዮጵያዊ)",
    "nationality_english": "the EXACT English nationality text as printed (e.g. Ethiopian)",
    "region_amharic": "the EXACT Amharic region text as printed on the card",
    "region_english": "the EXACT English region text as printed on the card",
    "zone_amharic": "the EXACT Amharic zone text as printed on the card",
    "zone_english": "the EXACT English zone text as printed on the card",
    "woreda_amharic": "the EXACT Amharic woreda/town text as printed on the card",
    "woreda_english": "the EXACT English woreda/town text as printed on the card"
}

IMPORTANT:
- Return ONLY the JSON object, no markdown formatting, no code blocks, no explanation.
- For ALL Amharic fields: READ the actual Ethiopic script characters from the image. Do NOT translate or transliterate from English.
- Preserve the exact text as shown on the card, including all special characters.
- For dates, include both Gregorian and Ethiopian calendar values separated by " | ".
- For FAN, include only digits, no spaces.
- For FIN, include the spaces as shown on the card.
"""

    front_part = types.Part.from_bytes(data=front_image_bytes, mime_type="image/png")
    back_part = types.Part.from_bytes(data=back_image_bytes, mime_type="image/png")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=prompt),
                    front_part,
                    back_part,
                ],
            )
        ],
        config=types.GenerateContentConfig(
            temperature=0.1,  # Low temperature for accurate extraction
        ),
    )

    # Parse JSON from response
    response_text = response.text.strip()

    # Remove markdown code block if present
    if response_text.startswith("```"):
        # Remove ```json and trailing ```
        lines = response_text.split("\n")
        # Find the start of JSON (after ```json or ```)
        start_idx = 1 if lines[0].startswith("```") else 0
        # Find the end (before trailing ```)
        end_idx = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        response_text = "\n".join(lines[start_idx:end_idx])

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse Gemini response as JSON: {e}\nResponse: {response_text}")

    # Validate all required fields are present
    required_fields = [
        "full_name_amharic", "full_name_english",
        "date_of_birth", "sex_amharic", "sex_english",
        "date_of_expiry", "date_of_issue", "fan",
        "phone_number", "fin",
        "nationality_amharic", "nationality_english",
        "region_amharic", "region_english",
        "zone_amharic", "zone_english",
        "woreda_amharic", "woreda_english",
    ]

    missing = [f for f in required_fields if f not in data]
    if missing:
        raise ValueError(f"Missing fields in Gemini response: {missing}")

    return data
"""
Extract structured data from vertical Fayda Digital ID screenshots using Google Gemini Vision API.
"""

import json
import os
from google import genai
from google.genai import types


def get_client() -> genai.Client:
    """Create a Gemini client using the API key from environment."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set")
    return genai.Client(api_key=api_key)


def extract_id_data(front_image_bytes: bytes, back_image_bytes: bytes) -> dict:
    """
    Send front and back ID screenshots to Gemini Vision API and extract
    all structured fields.

    Args:
        front_image_bytes: Bytes of the front vertical ID screenshot.
        back_image_bytes: Bytes of the back vertical ID screenshot.

    Returns:
        Dictionary with all extracted fields:
        {
            "full_name_amharic": str,
            "full_name_english": str,
            "date_of_birth": str,       # e.g. "03/08/1991 | 1999/Apr/11"
            "sex_amharic": str,          # e.g. "ወንድ"
            "sex_english": str,          # e.g. "Male"
            "date_of_expiry": str,       # e.g. "2026/08/26 | 2034/May/04"
            "date_of_issue": str,        # e.g. "2018/08/28 | 2026/May/06"
            "fan": str,                  # e.g. "2941370269506215"
            "phone_number": str,         # e.g. "0961418686"
            "fin": str,                  # e.g. "2980 2376 9475"
            "nationality_amharic": str,  # e.g. "ኢትዮጵያ"
            "nationality_english": str,  # e.g. "Ethiopian"
            "region_amharic": str,
            "region_english": str,
            "zone_amharic": str,
            "zone_english": str,
            "woreda_amharic": str,
            "woreda_english": str,
        }
    """
    client = get_client()

    prompt = """You are an OCR specialist analyzing two screenshots of an Ethiopian Fayda Digital National ID card (vertical format).

The FIRST image is the FRONT of the card. It contains:
- A portrait photo
- Full Name in Amharic script (ሙሉ ስም) and in English (Full Name) — these are TWO SEPARATE lines of text
- Date of Birth (in both Gregorian and Ethiopian calendar, separated by " | ")
- Sex in Amharic (ፆታ) and in English (Sex)
- Date of Expiry (in both Gregorian and Ethiopian calendar, separated by " | ")
- Date of Issue (rotated text on the right side, in both Gregorian and Ethiopian calendar, separated by " | ")
- FAN number (Fayda Application Number, a long numeric string shown with a barcode)

The SECOND image is the BACK of the card. It contains:
- A large QR code
- Phone Number
- FIN (Fayda Identification Number, formatted with spaces like "2980 2376 9475")
- Nationality in Amharic and English
- Address with Region, Zone, and Woreda/Town (each in Amharic and English on separate lines)

CRITICAL INSTRUCTIONS FOR AMHARIC TEXT:
- You MUST perform OCR (optical character recognition) to read the ACTUAL Amharic/Ethiopic (ግዕዝ) characters printed on the card.
- DO NOT translate the English text into Amharic. The Amharic text is ALREADY PRINTED on the card as a separate line.
- The Amharic name and the English name may look different — they are independently written on the card.
- For example, a name like "ሄኖክ አዳነ ጥምደዶ" is ALREADY on the card — read it directly, do NOT attempt to transliterate "Henok Adane Tumdedo" into Amharic.
- Same applies to Region, Zone, Woreda, Sex, and Nationality — each has its own Amharic text printed on the card.

Extract ALL the text data from both images and return ONLY a JSON object with these exact keys:
{
    "full_name_amharic": "the EXACT Amharic text as printed on the card for the name",
    "full_name_english": "the EXACT English text as printed on the card for the name",
    "date_of_birth": "the complete DOB string including both calendar formats separated by ' | '",
    "sex_amharic": "the EXACT Amharic text for sex as printed on the card (e.g. ወንድ or ሴት)",
    "sex_english": "the EXACT English text for sex as printed on the card (e.g. Male or Female)",
    "date_of_expiry": "the complete expiry string including both calendar formats separated by ' | '",
    "date_of_issue": "the complete issue date string including both calendar formats separated by ' | '",
    "fan": "the FAN number (digits only, no spaces)",
    "phone_number": "the phone number",
    "fin": "the FIN number (with spaces as shown)",
    "nationality_amharic": "the EXACT Amharic nationality text as printed (e.g. ኢትዮጵያዊ)",
    "nationality_english": "the EXACT English nationality text as printed (e.g. Ethiopian)",
    "region_amharic": "the EXACT Amharic region text as printed on the card",
    "region_english": "the EXACT English region text as printed on the card",
    "zone_amharic": "the EXACT Amharic zone text as printed on the card",
    "zone_english": "the EXACT English zone text as printed on the card",
    "woreda_amharic": "the EXACT Amharic woreda/town text as printed on the card",
    "woreda_english": "the EXACT English woreda/town text as printed on the card"
}

IMPORTANT:
- Return ONLY the JSON object, no markdown formatting, no code blocks, no explanation.
- For ALL Amharic fields: READ the actual Ethiopic script characters from the image. Do NOT translate or transliterate from English.
- Preserve the exact text as shown on the card, including all special characters.
- For dates, include both Gregorian and Ethiopian calendar values separated by " | ".
- For FAN, include only digits, no spaces.
- For FIN, include the spaces as shown on the card.
"""

    front_part = types.Part.from_bytes(data=front_image_bytes, mime_type="image/png")
    back_part = types.Part.from_bytes(data=back_image_bytes, mime_type="image/png")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=prompt),
                    front_part,
                    back_part,
                ],
            )
        ],
        config=types.GenerateContentConfig(
            temperature=0.1,  # Low temperature for accurate extraction
        ),
    )

    # Parse JSON from response
    response_text = response.text.strip()

    # Remove markdown code block if present
    if response_text.startswith("```"):
        # Remove ```json and trailing ```
        lines = response_text.split("\n")
        # Find the start of JSON (after ```json or ```)
        start_idx = 1 if lines[0].startswith("```") else 0
        # Find the end (before trailing ```)
        end_idx = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        response_text = "\n".join(lines[start_idx:end_idx])

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse Gemini response as JSON: {e}\nResponse: {response_text}")

    # Validate all required fields are present
    required_fields = [
        "full_name_amharic", "full_name_english",
        "date_of_birth", "sex_amharic", "sex_english",
        "date_of_expiry", "date_of_issue", "fan",
        "phone_number", "fin",
        "nationality_amharic", "nationality_english",
        "region_amharic", "region_english",
        "zone_amharic", "zone_english",
        "woreda_amharic", "woreda_english",
    ]

    missing = [f for f in required_fields if f not in data]
    if missing:
        raise ValueError(f"Missing fields in Gemini response: {missing}")

    return data
