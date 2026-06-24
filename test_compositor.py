import os
from PIL import Image

from cropper import crop_photo, crop_qr
from compositor import compose_id, create_a4_printable

def main():
    proj_dir = os.path.dirname(os.path.abspath(__file__))
    front_path = os.path.join(proj_dir, "sample-input", "front.PNG")
    back_path = os.path.join(proj_dir, "sample-input", "back.PNG")

    if not os.path.exists(front_path) or not os.path.exists(back_path):
        print(f"Error: Could not find sample input files in 'sample-input/'. Please make sure front.PNG and back.PNG exist.")
        return

    print(f"Loading {front_path}...")
    front_img = Image.open(front_path)
    print(f"Loading {back_path}...")
    back_img = Image.open(back_path)

    print("Cropping photo...")
    photo_img = crop_photo(front_img)
    photo_img.save("cropped_photo.png")
    
    print("Cropping QR...")
    qr_img = crop_qr(back_img)
    qr_img.save("cropped_qr.png")

    # Offline mock data for composing the card
    mock_data = {
        "full_name_amharic": "ሄኖክ አዳነ ጥምደዶ",
        "full_name_english": "Henok Adane Tumdedo",
        "date_of_birth": "03/08/1991 | 1999/Apr/11",
        "sex_amharic": "ወንድ",
        "sex_english": "Male",
        "date_of_expiry": "2026/08/26 | 2034/May/04",
        "date_of_issue": "2018/08/28 | 2026/May/06",
        "fan": "2941370269506215",
        "phone_number": "0961418686",
        "fin": "2980 2376 9475",
        "nationality_amharic": "ኢትዮጵያዊ",
        "nationality_english": "Ethiopian",
        "region_amharic": "የደቡብ ብሔሮች ብሔረሰቦችና ሕዝቦች ክልል",
        "region_english": "Southern Nations, Nationalities, and Peoples' Region",
        "zone_amharic": "ሀዲያ ዞን",
        "zone_english": "Hadiya Zone",
        "woreda_amharic": "ሆሳዕና ከተማ አስተዳደር",
        "woreda_english": "Hosanna Town Administration"
    }

    print("Composing combined ID card...")
    result = compose_id(mock_data, photo_img, qr_img)
    result.save("test_composed_id.png")

    print("Generating printable A4 canvas...")
    a4_canvas, pdf_dpi = create_a4_printable(result)
    
    print("Saving test A4 PNG...")
    a4_canvas.save("test_printable_a4.png", format="PNG", dpi=(pdf_dpi, pdf_dpi))
    
    print("SUCCESS: Saved composed card to 'test_composed_id.png' and printable A4 PNG to 'test_printable_a4.png'.")

if __name__ == "__main__":
    main()
