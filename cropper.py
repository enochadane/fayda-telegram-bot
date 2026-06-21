"""
Crop photo and QR code regions from vertical Fayda Digital ID screenshots.

Uses relative coordinates based on the known layout of the vertical digital ID format.
Sample input dimensions: 1110 x 1779 (front), 1109 x 1777 (back)
"""

from PIL import Image, ImageFilter
import io


def crop_photo(front_image: Image.Image) -> Image.Image:
    """
    Extract the portrait photo from the vertical front ID screenshot.

    Crops from just below any white status bar down to ~53% of card height.
    Determines status bar presence dynamically to handle pre-cropped images.

    Args:
        front_image: PIL Image of the front vertical ID screenshot.

    Returns:
        Cropped PIL Image of the photo.
    """
    w, h = front_image.size

    # Dynamically detect and skip phone status bar (usually pure white at top center)
    status_bar_height = 0
    cx = w // 2
    while status_bar_height < 60:
        r, g, b = front_image.getpixel((cx, status_bar_height))[:3]
        if r > 250 and g > 250 and b > 250:
            status_bar_height += 1
        else:
            break

    # Exact ratios derived from pixel scan of sample-input/front.PNG (1110x1779):
    # Grey photo box: left=429, top=380, right=709, bottom=946
    # These exclude white borders and the gold wave at the bottom.
    left   = int(w * 0.324)
    right  = int(w * 0.689)
    top    = status_bar_height + int((h - status_bar_height) * 0.144)
    bottom = status_bar_height + int((h - status_bar_height) * 0.525)

    photo = front_image.crop((left, top, right, bottom))
    return photo




def crop_qr(back_image: Image.Image) -> Image.Image:
    """
    Extract just the QR code from the vertical back ID screenshot.

    The QR square sits below the blue header banner.
    Calibrated for 1109x1777 reference dimensions.

    Args:
        back_image: PIL Image of the back vertical ID screenshot.

    Returns:
        Cropped PIL Image of the QR code only (square).
    """
    w, h = back_image.size

    # QR code square: skip the header (~14% from top), stop before text fields (~60%)
    # Horizontally the QR spans roughly x: 10.8% to 89.5% of width
    left   = int(w * 0.108)  # ~120px
    top    = int(h * 0.118)  # ~210px — just below the header banner
    right  = int(w * 0.884)  # ~980px
    bottom = int(h * 0.601)  # ~1068px — just above text fields

    qr = back_image.crop((left, top, right, bottom))

    # Ensure it's exactly square by taking the smaller dimension
    s = min(qr.width, qr.height)
    cx, cy = qr.width // 2, qr.height // 2
    qr = qr.crop((cx - s // 2, cy - s // 2, cx + s // 2, cy + s // 2))

    return qr


def image_to_bytes(image: Image.Image, format: str = "PNG") -> bytes:
    """Convert a PIL Image to bytes."""
    buf = io.BytesIO()
    image.save(buf, format=format)
    return buf.getvalue()


def bytes_to_image(data: bytes) -> Image.Image:
    """Convert bytes to a PIL Image."""
    return Image.open(io.BytesIO(data))
