"""Builds the Turkish cover from the original cover art (assets/cover.jpg) and the footer badge.

Usage: python3 -I cover.py <book_dir>
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BOOK = Path(sys.argv[1])
A = BOOK / 'assets'
FONT = '/usr/share/fonts/truetype/open-sans/OpenSans-{}.ttf'
F = lambda w, s: ImageFont.truetype(FONT.format(w), s)
ORANGE_1, ORANGE_2 = (241, 160, 40), (222, 96, 38)
NAVY = (38, 56, 82)


def text_w(text, font):
    return ImageDraw.Draw(Image.new('L', (1, 1))).textbbox((0, 0), text, font=font)[2]


def gradient_text(im, text, font, x, y):
    bb = ImageDraw.Draw(Image.new('L', (1, 1))).textbbox((0, 0), text, font=font)
    w, h = bb[2], bb[3]
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).text((0, 0), text, font=font, fill=255)
    g = Image.new('RGB', (w, h))
    gd = ImageDraw.Draw(g)
    for i in range(w):
        t = i / max(1, w - 1)
        gd.line([(i, 0), (i, h)], fill=tuple(int(ORANGE_1[k] + (ORANGE_2[k] - ORANGE_1[k]) * t) for k in range(3)))
    im.paste(g, (x, y), mask)


def cover():
    im = Image.open(A / 'cover.jpg').convert('RGB')
    W, H = im.size
    bg = (214, 216, 214)
    # Fade out the Arabic title/author block at the bottom of the original art
    top, full = 2380, 2560
    px = im.load()
    for y in range(top, H):
        a = min(1, (y - top) / (full - top))
        for x in range(W):
            r, g, b = px[x, y]
            px[x, y] = (int(r * (1 - a) + bg[0] * a), int(g * (1 - a) + bg[1] * a), int(b * (1 - a) + bg[2] * a))
    R = W - 150
    f1 = F('ExtraBold', 300)
    for i, t in enumerate(['ON', 'ÖNCÜL']):
        gradient_text(im, t, f1, R - text_w(t, f1), 2440 + i * 340)
    d = ImageDraw.Draw(im)
    f3 = F('Semibold', 58)
    s = 'THE TEN PREMISES'
    d.text((R - text_w(s, f3) - 8, 3205), s, font=f3, fill=(110, 112, 115))
    d.text((150, 2925), 'Bunları —Allah’ın yardımıyla—', font=F('Semibold', 56), fill=NAVY)
    d.text((150, 2995), 'evvelkilerin ve sonrakilerin', font=F('Semibold', 56), fill=NAVY)
    d.text((150, 3065), 'ilminden süzüp derleyen:', font=F('Semibold', 56), fill=NAVY)
    d.text((150, 3145), 'İmrân b. Fadl Şâkir', font=F('ExtraBold', 86), fill=NAVY)
    im.save(A / 'cover_tr.jpg', quality=92)


def footer_badge(text_w_px=660, scale=4):
    """Orange double rule running into a rounded navy page-number box (mirrors the Arabic footer)."""
    box_w, box_h, gap = 30, 26, 8
    w, h = text_w_px * scale, box_h * scale
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    line_end = (text_w_px - box_w - gap) * scale
    y = h // 2 + 2 * scale
    d.rectangle([0, y - int(2.6 * scale), line_end, y], fill=(238, 138, 58, 255))
    d.rectangle([0, y + int(1.6 * scale), line_end, y + int(2.4 * scale)], fill=(238, 138, 58, 255))
    d.rounded_rectangle([(text_w_px - box_w) * scale + 2, 2, w - 3, h - 3], radius=7 * scale,
                        outline=NAVY + (255,), width=int(1.4 * scale))
    im.save(A / 'footer_badge.png')


cover()
footer_badge()
print('cover_tr.jpg + footer_badge.png written')
