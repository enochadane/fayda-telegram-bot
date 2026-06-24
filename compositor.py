"""
Compose extracted ID data onto the combined horizontal ID card template using Pillow.

Template: national_id_blank.png  —  5460 × 1710 px  (RGB)
  ┌────────────────────────┬──────┬────────────────────────┐
  │     FRONT  (0–2727)    │ gap  │    BACK  (2739–5459)   │
  └────────────────────────┴──────┴────────────────────────┘

Front half coordinate reference (absolute x, y):
  Silhouette cut-out:           x=202–930,   y=330–1434
  Text fields start at:         x=1060
  "ሙሉ ስም | Full Name" label:    y=390–430   → value top: y=455
  "Date of Birth" label:        y=730–785   → value top: y=810
  "Sex" label:                  y=895–945   → value top: y=970
  "Date Of Expiry" label:       y=1055–1110 → value top: y=1140
  FAN white box:                x=1199–1963, y=1268–1558
  Date of Issue (rotated):      x=5, vertical strip on left edge
    Ethiopian calendar date:    y=150  (above pre-printed "Date of Issue" label)
    Gregorian date:             y=950  (below pre-printed "Date of Issue" label)

Back half coordinate reference (relative x offset from BACK_OFFSET=2739):
  "Phone Number" label:         y=90–130    → value top: y=145
  Nationality already printed   (skip)
  "Address" label:              y=425–560   → values start: y=570
  FIN white box:                rel-x=95–749, y=1362–1623
  QR zone:                      rel-x=1170–2701, y=30–1310
"""

import io
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import barcode
from barcode.writer import ImageWriter


# ─── Constants ────────────────────────────────────────────────────────────────
TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "templates", "national_id_blank.png",
)

BACK_OFFSET = 2739   # x-pixel where the back half begins in the combined image

# ─── Font paths ───────────────────────────────────────────────────────────────
FONT_DIR      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
ETHIOPIC_FONT = os.path.join(FONT_DIR, "NotoSansEthiopic.ttf")
SANS_FONT     = os.path.join(FONT_DIR, "NotoSans.ttf")


def _load_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a TrueType font at the given size."""
    return ImageFont.truetype(font_path, size)


def _draw_bold(draw: ImageDraw.ImageDraw, pos: tuple, text: str,
               fill: tuple, font: ImageFont.FreeTypeFont, stroke: int = 2) -> None:
    """
    Draw text with a stroke_width that mimics a bold/heavy weight.
    PIL's stroke_width parameter draws an outline using the same fill colour,
    thickening each glyph stroke without requiring a separate bold font file.
    """
    draw.text(pos, text, fill=fill, font=font,
              stroke_width=stroke, stroke_fill=fill)


def _generate_barcode_image(fan_number: str,
                             target_width: int, target_height: int) -> Image.Image:
    """
    Generate a Code128 barcode image for the FAN number.

    Args:
        fan_number:    The FAN digits string (no spaces).
        target_width:  Desired pixel width.
        target_height: Desired pixel height.

    Returns:
        PIL Image of the barcode (no text label below the bars), RGB mode.
    """
    code128 = barcode.get_barcode_class("code128")
    writer  = ImageWriter()
    options = {
        "module_width":  0.6,
        "module_height": 18.0,
        "quiet_zone":    1.5,
        "font_size":     0,
        "text_distance": 0,
        "write_text":    False,
        "dpi":           600,
    }

    barcode_obj = code128(fan_number, writer=writer)
    buf = io.BytesIO()
    barcode_obj.write(buf, options=options)
    buf.seek(0)

    barcode_img = Image.open(buf).convert("RGB")

    # Trim extra white padding the writer adds
    bbox = barcode_img.getbbox()
    if bbox:
        barcode_img = barcode_img.crop(bbox)

    barcode_img = barcode_img.resize((target_width, target_height), Image.LANCZOS)
    return barcode_img


def _make_photo_silhouette_mask(template: Image.Image) -> Image.Image:
    """
    Build a grayscale mask from the humanoid white silhouette on the front half.

    Uses a bidirectional walking search starting from the center of the silhouette
    to locate the exact shape boundaries. Geometric bounds prevent picking up
    background security waves or vertical label elements.

    Returns an 'L'-mode image the same size as template.
    """
    w, h = template.size
    mask  = Image.new("L", (w, h), 0)
    px    = template.load()
    mx    = mask.load()

    # Known vertical range of silhouette
    # Start at y=150 to capture the top of the head (was 300, which cut hair)
    sil_y_min, sil_y_max = 150, 1435
    center_x = 566

    for y in range(sil_y_min, sil_y_max):
        # 3-tier geometric limits:
        #   y < 300  → narrow bounds to stay inside the rounded head/hair region
        #              and avoid the Ethiopian flag stripe elements at the sides
        #   300–999  → normal torso bounds
        #   1000+    → wider hip/leg bounds
        if y < 300:
            left_limit  = 400
            right_limit = 730
        elif y < 1000:
            left_limit  = 250
            right_limit = 890
        else:
            left_limit  = 200
            right_limit = 930

        # Walk left
        left_edge = center_x
        while left_edge > left_limit:
            r, g, b = px[left_edge, y][:3]
            if (r + g + b) / 3 < 245:
                break
            left_edge -= 1

        # Walk right
        right_edge = center_x
        while right_edge < right_limit:
            r, g, b = px[right_edge, y][:3]
            if (r + g + b) / 3 < 245:
                break
            right_edge += 1

        if left_edge < center_x and right_edge > center_x:
            for x in range(left_edge, right_edge + 1):
                mx[x, y] = 255

    # A blur softens the silhouette edge
    mask = mask.filter(ImageFilter.GaussianBlur(radius=1))
    return mask


def remove_white_background_smooth(img: Image.Image, tolerance: int = 30, use_min_filter: bool = True, min_filter_size: int = 3) -> Image.Image:
    """
    Remove the white background of the photo by performing a flood fill
    from the top/left/right edges, making near-white pixels transparent.
    Smoothes/feathers the edges using a small Gaussian blur on the mask.
    """
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    
    mask = Image.new("L", (w, h), 255)
    mask_px = mask.load()
    
    visited = set()
    queue = []
    
    # Start BFS from top, left, and right edges (avoid bottom edge where shirts are)
    for x in range(w):
        queue.append((x, 0))
        visited.add((x, 0))
    for y in range(1, h):
        queue.append((0, y))
        visited.add((0, y))
        queue.append((w - 1, y))
        visited.add((w - 1, y))
        
    head = 0
    while head < len(queue):
        cx, cy = queue[head]
        head += 1
        
        mask_px[cx, cy] = 0
        
        for nx, ny in [(cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)]:
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                r, g, b, a = px[nx, ny]
                if r > 255 - tolerance and g > 255 - tolerance and b > 255 - tolerance:
                    visited.add((nx, ny))
                    queue.append((nx, ny))
                    
    # Optionally apply MinFilter to erode mask edges and eat the white halo
    if use_min_filter:
        mask = mask.filter(ImageFilter.MinFilter(min_filter_size))

    # Smooth the mask using a small blur
    mask_blurred = mask.filter(ImageFilter.GaussianBlur(radius=1.2))
    
    r, g, b, _ = img.split()
    img_result = Image.merge("RGBA", (r, g, b, mask_blurred))
    return img_result



def _paste_rotated_text(canvas: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                        fill: tuple, x_center: int, y: int, align_bottom: bool = False, stroke: int = 1) -> None:
    """
    Render `text` onto a temporary image, rotate it 90° counter-clockwise
    (so it reads from bottom to top along the card's left edge), then paste
    it onto `canvas` centered horizontally at `x_center`.

    If `align_bottom` is True, `y` is treated as the bottom limit of the text (y_end).
    Otherwise, `y` is treated as the top starting position (y_start).
    """
    # Measure the text so we can size the temporary image exactly
    tmp_img  = Image.new("RGBA", (1, 1))
    tmp_draw = ImageDraw.Draw(tmp_img)
    tbbox    = tmp_draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    txt_w    = tbbox[2] - tbbox[0] + 20
    txt_h    = tbbox[3] - tbbox[1] + 16

    # Draw text onto temporary image
    txt_img  = Image.new("RGBA", (txt_w, txt_h), (0, 0, 0, 0))
    txt_draw = ImageDraw.Draw(txt_img)
    txt_draw.text((10 - tbbox[0], 8 - tbbox[1]), text,
                  fill=fill, font=font,
                  stroke_width=stroke, stroke_fill=fill)

    # Rotate 90° CCW → text runs from bottom of card upward
    rotated = txt_img.rotate(90, expand=True)

    # Center text horizontally at x_center
    paste_x = x_center - rotated.width // 2

    # Calculate y-coordinate
    if align_bottom:
        paste_y = y - rotated.height
    else:
        paste_y = y

    canvas.paste(rotated, (paste_x, paste_y), rotated)


def compose_id(data: dict, photo_image: Image.Image, qr_image: Image.Image,
               template_path: str = TEMPLATE_PATH) -> Image.Image:
    """
    Compose both the front and back ID card onto the combined template in one pass.

    Args:
        data:          Dictionary of extracted ID fields (see extractor.py for keys).
        photo_image:   Cropped portrait photo (PIL Image).
        qr_image:      Cropped QR code image (PIL Image).
        template_path: Path to the combined template PNG.

    Returns:
        Composed PIL Image of the filled combined card (5460 × 1710, RGB).
    """
    template = Image.open(template_path).convert("RGBA")
    tw, th   = template.size  # 5460 × 1710

    # ══════════════════════════════════════════════════════════════════════════
    # FRONT HALF
    # ══════════════════════════════════════════════════════════════════════════

    # ── Step F1: Paste photo into the humanoid silhouette ─────────────────────
    photo_box_x1, photo_box_y1 = 202,  330
    photo_box_x2, photo_box_y2 = 930, 1434
    photo_box_w = photo_box_x2 - photo_box_x1   # 728
    photo_box_h = photo_box_y2 - photo_box_y1   # 1104

    src_w, src_h = photo_image.size

    # ── Position photo so the full portrait (head→shoulders) is visible ─────────
    #
    # Scale to fill the full silhouette width (matches physical card style).
    # === ZOOM CONTROL FOR MAIN PHOTO ===
    # Decrease this value to zoom out (e.g. 0.95), increase to zoom in (e.g. 1.05)
    main_photo_zoom = 0.93
    
    # Remove white background to prevent boxy edges and eat the white halo
    photo_clean = remove_white_background_smooth(photo_image, tolerance=30, use_min_filter=True)
    
    scale = (photo_box_w / src_w) * main_photo_zoom
    new_w = int(photo_box_w * main_photo_zoom)
    new_h = int(src_h * scale)
    photo_resized = photo_clean.resize((new_w, new_h), Image.LANCZOS)

    # ── Photo processing: convert to grayscale + enhance ──────────────────
    # Physical Ethiopian ID cards print the portrait in black & white.
    # Convert RGB channels to grayscale but preserve the alpha channel!
    r_ch, g_ch, b_ch, a_ch = photo_resized.split()
    photo_gray_l = Image.merge("RGB", (r_ch, g_ch, b_ch)).convert("L")
    photo_gray_l = ImageEnhance.Contrast(photo_gray_l).enhance(1.15)  # subtle contrast boost
    photo_gray_l = ImageEnhance.Sharpness(photo_gray_l).enhance(1.3)  # sharpen after resize
    photo_resized = Image.merge("RGBA", (photo_gray_l, photo_gray_l, photo_gray_l, a_ch))

    # Place the BOTTOM of the photo at 99.9 % of the silhouette box height.
    # This way the shoulders sit near the bottom-centre of the silhouette and
    # the face / head naturally appear in the upper portion.
    bottom_anchor = int(photo_box_h * 1.05)  # canvas y where photo bottom lands
    y_offset = bottom_anchor - new_h          # where the photo TOP starts (can be negative)
    x_offset = (photo_box_w - new_w) // 2     # center horizontally

    # === PHOTO BACKGROUND: WAVE PATTERN FROM TEMPLATE ===
    # Reconstruct the card's guilloché wave pattern behind the person.
    # We reconstruct the entire photo box background (728 × 1104 px) by walking
    # horizontally in steps of the wave period (13px) to find clean wave pixels
    # at the left (< 215) and right (> 915) edges of the front template.
    # Linear blending weights transition smoothly between the left and right sources,
    # preserving the background's colors, phase, and vertical consistency without seams.
    _WAVE_PERIOD = 13
    _fb_path = os.path.join(os.path.dirname(os.path.abspath(template_path)), "front_blank.png")
    _front_blank = Image.open(_fb_path).convert("RGB")

    # Crop the photo box area from front_blank
    _fb_crop = _front_blank.crop((photo_box_x1, photo_box_y1, photo_box_x2, photo_box_y2))
    _bg_px = _fb_crop.load()
    _orig_px = _front_blank.load()

    # Precompute clean x positions and blending weights for each column
    _x_map = []
    for _x_rel in range(photo_box_w):
        _x_abs = photo_box_x1 + _x_rel
        
        # Walk left to find clean pixel (< 215)
        _x_left = _x_abs
        while _x_left >= 215:
            _x_left -= _WAVE_PERIOD
            
        # Walk right to find clean pixel (> 915)
        _x_right = _x_abs
        while _x_right <= 915:
            _x_right += _WAVE_PERIOD
            
        _weight_left = (photo_box_w - 1 - _x_rel) / (photo_box_w - 1)
        _weight_right = 1.0 - _weight_left
        _x_map.append((_x_left, _x_right, _weight_left, _weight_right))

    for _y_rel in range(photo_box_h):
        _y_abs = photo_box_y1 + _y_rel
        for _x_rel in range(photo_box_w):
            _x_left, _x_right, _weight_left, _weight_right = _x_map[_x_rel]
            
            _r_l, _g_l, _b_l = _orig_px[_x_left, _y_abs]
            _r_r, _g_r, _b_r = _orig_px[_x_right, _y_abs]
            
            _r = int(_r_l * _weight_left + _r_r * _weight_right)
            _g = int(_g_l * _weight_left + _g_r * _weight_right)
            _b = int(_b_l * _weight_left + _b_r * _weight_right)
            
            _bg_px[_x_rel, _y_rel] = (_r, _g, _b)

    photo_canvas = _fb_crop.convert("RGBA")
    photo_canvas.paste(photo_resized, (x_offset, y_offset), photo_resized)

    # Paste final composed photo box back into template
    template.paste(photo_canvas.convert("RGB"), (photo_box_x1, photo_box_y1))


    # ── Step F1b: Ghost / watermark photo — semi-transparent portrait overlay ──
    # In the expected output the ghost portrait sits over the lower-right
    # decorative green-wave area of the front card.
    ghost_x1, ghost_y1 = 2130, 1195
    ghost_x2, ghost_y2 = 2470, 1558
    ghost_w = ghost_x2 - ghost_x1   # 340
    ghost_h = ghost_y2 - ghost_y1   # 363

    # Ghost photo: same bottom-anchor approach.
    # Anchor the photo bottom at 92 % of the ghost box so face + shoulders show.
    # === ZOOM CONTROL FOR GHOST PHOTO ===
    # Decrease this value to zoom out (e.g. 0.95), increase to zoom in (e.g. 1.05)
    ghost_photo_zoom = 0.75
    
    # For the ghost photo, also remove the white background to prevent a semi-transparent white box and eat the white halo
    ghost_clean = remove_white_background_smooth(photo_image, tolerance=30, use_min_filter=True)
    
    ghost_scale   = (ghost_w / src_w) * ghost_photo_zoom
    ghost_new_w   = int(ghost_w * ghost_photo_zoom)
    ghost_new_h   = int(src_h * ghost_scale)
    ghost_resized = ghost_clean.resize((ghost_new_w, ghost_new_h), Image.LANCZOS)
    
    # Ghost also in grayscale for consistency with the main photo
    g_r, g_g, g_b, g_a = ghost_resized.split()
    ghost_gray_l = Image.merge("RGB", (g_r, g_g, g_b)).convert("L")
    ghost_resized = Image.merge("RGBA", (ghost_gray_l, ghost_gray_l, ghost_gray_l, g_a))

    ghost_bottom_anchor = int(ghost_h * 1.05)
    ghost_y_offset      = ghost_bottom_anchor - ghost_new_h   # can be negative
    ghost_x_offset      = (ghost_w - ghost_new_w) // 2     # center horizontally

    # Create a transparent canvas to paste the resized ghost photo onto
    ghost_canvas = Image.new("RGBA", (ghost_w, ghost_h), (0, 0, 0, 0))
    ghost_canvas.paste(ghost_resized, (ghost_x_offset, ghost_y_offset), ghost_resized)

    # Apply ~25% opacity so the card background security pattern shows through
    r_ch, g_ch, b_ch, a_ch = ghost_canvas.split()
    a_ch = a_ch.point(lambda p: int(p * 0.25))
    ghost_rgba = Image.merge("RGBA", (r_ch, g_ch, b_ch, a_ch))
    template.paste(ghost_rgba, (ghost_x1, ghost_y1), ghost_rgba)

    # ── Step F2: Prepare overlay for text ─────────────────────────────────────
    overlay = Image.new("RGBA", template.size, (0, 0, 0, 0))
    draw    = ImageDraw.Draw(overlay)

    # Fonts – larger sizes for readability; stroke_width simulates bold weight
    font_name_am  = _load_font(ETHIOPIC_FONT, 88)   # Full name — Amharic
    font_name_en  = _load_font(SANS_FONT,     80)   # Full name — English
    font_field_am = _load_font(ETHIOPIC_FONT, 70)   # Other Amharic field values
    font_field_en = _load_font(SANS_FONT,     68)   # Other English field values
    font_fan_num  = _load_font(SANS_FONT,     60)   # FAN digits
    font_doi      = _load_font(SANS_FONT,     42)  # Date-of-issue (rotated) — compact to fit left-edge strip

    text_color = (25, 25, 25, 255)   # Near-black for all fields
    text_x     = 1060                # Left edge of all front-half text columns

    # ── Full Name ─────────────────────────────────────────────────────────────
    _draw_bold(draw, (text_x, 465), data["full_name_amharic"],
               text_color, font_name_am, stroke=2)
    _draw_bold(draw, (text_x, 560), data["full_name_english"],
               text_color, font_name_en, stroke=2)

    # ── Date of Birth ─────────────────────────────────────────────────────────
    _draw_bold(draw, (text_x, 800), data["date_of_birth"],
               text_color, font_field_en, stroke=1)

    # ── Sex ───────────────────────────────────────────────────────────────────
    sex_text = f'{data["sex_amharic"]}  |  {data["sex_english"]}'
    _draw_bold(draw, (text_x, 960), sex_text,
               text_color, font_field_am, stroke=1)

    # ── Date of Expiry ────────────────────────────────────────────────────────
    _draw_bold(draw, (text_x, 1125), data["date_of_expiry"],
               text_color, font_field_en, stroke=1)

    # ── Step F3: FAN number + barcode ─────────────────────────────────────────
    #
    # The template has pre-printed "ካርድ / ቁጥር / FAN" labels at x ≈ 600–1190.
    # The white box where the number/barcode go begins at x ≈ 1199.
    # Pixel-scan confirmed: box is x=1199–1963, y=1268–1558 (w=764, h=290).
    #
    fan_box_x1, fan_box_y1 = 1199, 1268
    fan_box_x2, fan_box_y2 = 1963, 1558
    fan_box_w = fan_box_x2 - fan_box_x1   # 764
    fan_box_h = fan_box_y2 - fan_box_y1   # 290

    fan_number  = data["fan"]
    fan_display = " ".join(fan_number[i:i+4] for i in range(0, len(fan_number), 4))

    # Number centred horizontally near the top of the white box
    nbbox      = draw.textbbox((0, 0), fan_display, font=font_fan_num)
    fan_text_w = nbbox[2] - nbbox[0]
    fan_text_x = fan_box_x1 + (fan_box_w - fan_text_w) // 2
    _draw_bold(draw, (fan_text_x, fan_box_y1 + 6), fan_display,
               text_color, font_fan_num, stroke=1)

    # Barcode fills the remainder of the white box below the number
    barcode_top = fan_box_y1 + 76         # leave room for the number line
    barcode_h   = fan_box_y2 - barcode_top - 8   # ~214 px (taller than before)
    try:
        bc_img  = _generate_barcode_image(fan_number, fan_box_w - 20, barcode_h)
        bc_rgba = bc_img.convert("RGBA")
        template.paste(bc_rgba,
                       (fan_box_x1 + 10, barcode_top),
                       bc_rgba)
    except Exception:
        pass   # graceful fallback — the number text is still visible

    # ── Step F4: Date of Issue — rotated text on the left-edge strip ──────────
    #
    # The template pre-prints "Date of Issue" vertically at x ≈ 35–65.
    # We add the actual dates to the LEFT of that label (x = 5).
    #
    #  Layout (card reads top→bottom):
    #    y=150  → Ethiopian-calendar date  (above the pre-printed label)
    #    y≈720  → pre-printed "Date of Issue" label (already on template)
    #    y=950  → Gregorian date            (below the pre-printed label)
    #
    doi_raw = data.get("date_of_issue", "")
    if doi_raw:
        doi_color = (110, 75, 35, 255)   # Brownish — matches template label tone
        parts         = doi_raw.split("|")
        # date_of_issue format: "Ethiopian_date | Gregorian_date"
        # e.g. "2018/08/28 | 2026/May/06"  → parts[0]=Ethiopian, parts[1]=Gregorian
        ethiopian_doi = parts[0].strip() if parts         else doi_raw
        gregorian_doi = parts[1].strip() if len(parts) > 1 else ""

        # Layout on the left vertical strip:
        # Gregorian date at the top, ending at y=680 (spaced above the pre-printed "Date of Issue" label at y=701)
        # Ethiopian date in the middle, starting at y=1010 (spaced below the pre-printed "Date of Issue" label ending at y=967)
        # Both aligned horizontally to center at x_center=63 in line with pre-printed labels
        if gregorian_doi:
            _paste_rotated_text(template, gregorian_doi, font_doi,
                                doi_color, x_center=63, y=680, align_bottom=True, stroke=2)
        if ethiopian_doi:
            _paste_rotated_text(template, ethiopian_doi, font_doi,
                                doi_color, x_center=63, y=1010, align_bottom=False, stroke=2)

    # ══════════════════════════════════════════════════════════════════════════
    # BACK HALF  (all absolute x = BACK_OFFSET + relative_x)
    # ══════════════════════════════════════════════════════════════════════════
    B = BACK_OFFSET   # shorthand

    # Erase the pre-printed sample "Gerese City Administration" address text
    bg_patch = template.crop((B + 61, 1100, B + 1161, 1190))
    template.paste(bg_patch, (B + 61, 1225))

    # Back-half fonts — slightly larger than before
    font_phone   = _load_font(SANS_FONT,     68)
    font_addr_am = _load_font(ETHIOPIC_FONT, 72)
    font_addr_en = _load_font(SANS_FONT,     66)
    font_fin     = _load_font(SANS_FONT,     64)

    back_text_x = B + 138   # left margin for all back text, aligned with labels

    # ── Phone Number  (label y=90–130 → value below) ──────────────────────────
    _draw_bold(draw, (back_text_x, 145), data["phone_number"],
               text_color, font_phone, stroke=1)

    # ── Nationality: already pre-printed on template — do NOT write again ─────

    # ── Address  (label ends ~y:560 → values expand to the bottom above FIN) ──
    address_coords = [
        (data["region_amharic"],  data["region_english"],  580,  675),
        (data["zone_amharic"],    data["zone_english"],    800,  895),
        (data["woreda_amharic"],  data["woreda_english"],  1020, 1115),
    ]

    for am_text, en_text, y_am, y_en in address_coords:
        _draw_bold(draw, (back_text_x, y_am), am_text,
                   text_color, font_addr_am, stroke=1)
        _draw_bold(draw, (back_text_x, y_en), en_text,
                   text_color, font_addr_en, stroke=1)

    # ── FIN number  (white box: rel x=95–749, y=1362–1623) ────────────────────
    fin_x = B + 430   # after the "ፋይዳ ልዩ ቁጥር / FIN" pre-printed labels
    fin_y = 1390
    _draw_bold(draw, (fin_x, fin_y), data["fin"],
               text_color, font_fin, stroke=1)

    # ── SN (Serial Number)  (white box: rel x=2061–2688, y=1530–1628) ──────────
    import hashlib
    fan_clean = "".join(data["fan"].split())
    hasher = hashlib.sha256(fan_clean.encode('utf-8'))
    hash_int = int(hasher.hexdigest()[:8], 16)
    sn_number = str(10000000 + (hash_int % 90000000))
    
    font_sn = _load_font(SANS_FONT, 56)
    # Draw to the right of "SN:" text inside the pre-printed white box
    _draw_bold(draw, (B + 2280, 1542), sn_number,
               text_color, font_sn, stroke=1)

    # ── QR Code  (rel x=1260–2580, y=130–1450) ─────────────────────────────────
    qr_target_size = 1320
    qr_copy = qr_image.copy().resize((qr_target_size, qr_target_size), Image.LANCZOS)
    if qr_copy.mode != "RGBA":
        qr_copy = qr_copy.convert("RGBA")

    # Paste QR within the zone — raise qy to 90 so the top of the QR aligns
    # with the Phone Number section label at y≈90
    qx = B + 1260
    qy = 90
    template.paste(qr_copy, (qx, qy), qr_copy)

    # ── Final composite ────────────────────────────────────────────────────────
    result = Image.alpha_composite(template, overlay)
    return result.convert("RGB")


def mirror_image(image: Image.Image) -> Image.Image:
    """Mirror the image horizontally (flip left-to-right)."""
    return image.transpose(Image.FLIP_LEFT_RIGHT)


def create_a4_printable(composed_id: Image.Image) -> tuple:
    """
    Place the mirrored front and back ID cards side-by-side at the very top of an A4 portrait page.

    - Card dimensions are mathematically aligned to native resolution to prevent resizing blur.
    - A thin vertical fold guide line is drawn in the center of the gap for PVC film folding.
    - The entire card block is horizontally centered on the A4 page.
    """
    # ── CARD SIZE CONTROL ──────────────────────────────────────────────────────
    # Standard CR80 physical card: 85.6 mm × 53.98 mm
    # Most home/office printers scale PDFs down by 2-5%.
    # We increase the target dimensions to compensate for typical printer scaling.
    # Adjust card_width_mm until your printer prints it at exactly 85.6 mm.
    card_width_mm = 88.5   # ← increase if printed card is too small, decrease if too large
    
    # We crop both front and back halves at exactly 2727 x 1710 pixels.
    # To avoid resizing blur, we do NOT scale the cards. Instead, we dynamically
    # calculate the PDF's DPI so that 2727 pixels renders at card_width_mm.
    dpi = (2727.0 * 25.4) / card_width_mm  # e.g., 782.66 DPI for 88.5 mm

    # A4 page dimensions in pixels at dynamic DPI
    a4_w = int(210.0 / 25.4 * dpi)   # ~6470 px = 210.0 mm
    a4_h = int(297.0 / 25.4 * dpi)   # ~9152 px = 297.0 mm

    canvas = Image.new("RGB", (a4_w, a4_h), (255, 255, 255))

    # Extract front and back halves from the combined template image.
    # We crop them both to exactly 2727 px wide to keep them identical in size.
    front_card = composed_id.crop((0,    0, 2727, 1710))
    back_card  = composed_id.crop((2733, 0, 5460, 1710))

    # Mirror each half (required for PVC film / dragon sheet printing)
    front_mirrored = mirror_image(front_card)
    back_mirrored  = mirror_image(back_card)

    # ── GAP & TOP MARGIN ──────────────────────────────────────────────────────
    gap_mm        = 5.0    # gap between cards — space for the fold line
    top_margin_mm = 2.0    # set to 0.0 for borderless printing

    # Force gap to be an even number of pixels to ensure mathematically perfect centering
    gap      = int(gap_mm        / 25.4 * dpi) // 2 * 2
    y_offset = int(top_margin_mm / 25.4 * dpi)

    # ── HORIZONTAL CENTERING ──────────────────────────────────────────────────
    # Center the entire combined block (front + gap + back) on the A4 page.
    target_w    = 2727
    target_h    = 1710
    total_width = target_w * 2 + gap
    block_x     = (a4_w - total_width) // 2    # left edge of the combined block
    front_x     = block_x
    back_x      = block_x + target_w + gap

    canvas.paste(front_mirrored, (front_x, y_offset))
    canvas.paste(back_mirrored,  (back_x,  y_offset))

    # ── FOLD GUIDE LINE ───────────────────────────────────────────────────────
    # Draw a thin vertical line at the exact center of the gap.
    # Fold the PVC film along this line to align front and back.
    fold_x         = block_x + target_w + gap // 2   # center of the gap (and center of A4 page!)
    fold_thickness = max(3, int(0.4 / 25.4 * dpi))   # 0.4 mm ≈ 12 px
    fold_color     = (20, 20, 20)                     # near-black
    draw = ImageDraw.Draw(canvas)
    draw.line(
        [(fold_x, y_offset), (fold_x, y_offset + target_h)],
        fill=fold_color,
        width=fold_thickness,
    )

    return canvas, dpi


# ─── Legacy helpers kept for backwards compatibility ──────────────────────────

def compose_front(template_path: str, data: dict, photo_image: Image.Image) -> Image.Image:
    """Deprecated: use compose_id() instead."""
    blank_qr = Image.new("RGB", (100, 100), (255, 255, 255))
    return compose_id(data, photo_image, blank_qr, template_path=TEMPLATE_PATH)


def compose_back(template_path: str, data: dict, qr_image: Image.Image) -> Image.Image:
    """Deprecated: use compose_id() instead."""
    blank_photo = Image.new("RGB", (300, 700), (200, 200, 200))
    return compose_id(data, blank_photo, qr_image, template_path=TEMPLATE_PATH)
