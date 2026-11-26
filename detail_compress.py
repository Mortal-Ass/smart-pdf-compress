"""Page budgets and local detail protection for size-first scan compression."""
from io import BytesIO
import math

import pymupdf as fitz


def parse_regions(text, count):
    regions = {}
    for item in text.split(";"):
        if not item.strip():
            continue
        try:
            page, coords = item.split(":")
            page = int(page)
            x, y, right, bottom = map(float, coords.split(","))
            if not (1 <= page <= count and 0 <= x < right <= 100 and 0 <= y < bottom <= 100):
                raise ValueError
        except ValueError:
            raise ValueError("局部区域格式为 页码:左,上,右,下，坐标按页面百分比填写") from None
        regions.setdefault(page, []).append((x, y, right, bottom))
    return regions


def bitmap(page, dpi, clip=None):
    from PIL import Image
    dpi = min(dpi, max(1, int(72 * math.sqrt(6000000 / page.rect.get_area()))))
    pix = page.get_pixmap(dpi=dpi, clip=clip, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples), dpi


def encoded(image, fmt, **kwargs):
    buf = BytesIO()
    image.save(buf, fmt, **kwargs)
    return buf.getvalue()


def qr_codes(image):
    import zxingcpp
    return zxingcpp.read_barcodes(image, formats=zxingcpp.BarcodeFormat.QRCode)


def detail_candidate(original, target, limit, focus, regions, log):
    patches, expected, weights = [], [], []
    for n, page in enumerate(original, 1):
        log(f"分析第 {n}/{len(original)} 页的小字和二维码", flush=True)
        image, dpi = bitmap(page, 200)
        codes = qr_codes(image)
        expected.append({c.bytes for c in codes})
        items = []
        for coords in regions.get(n, []):
            rect = fitz.Rect(*(v * (page.rect.width if j % 2 == 0 else page.rect.height) / 100
                               for j, v in enumerate(coords)))
            crop, _ = bitmap(page, 180, rect)
            items.append((rect, encoded(crop, "JPEG", quality=85, optimize=True)))
        for code in codes:
            pos = code.position
            points = [pos.top_left, pos.top_right, pos.bottom_left, pos.bottom_right]
            box = (max(0, min(p.x for p in points)-12), max(0, min(p.y for p in points)-12),
                   min(image.width, max(p.x for p in points)+13), min(image.height, max(p.y for p in points)+13))
            crop = image.crop(box).convert("L")
            binary = crop.point(lambda v: 255 if v > 160 else 0, mode="1")
            if code.bytes in {c.bytes for c in qr_codes(binary)}:
                crop = binary
            items.append((fitz.Rect(*(v*72/dpi for v in box)) & page.rect, encoded(crop, "PNG")))
        patches.append(items)
        image.thumbnail((600, 600))
        weights.append(len(encoded(image, "JPEG", quality=65)) ** .75 * (2.8 if n in focus else 1))
    available = limit - sum(len(data) + 450 for items in patches for _, data in items) - 700*len(original) - 2000
    for factor in (1, .94, .84):
        with fitz.open() as doc:
            for n, page in enumerate(original, 1):
                budget = max(3500, available * factor * weights[n-1] / sum(weights))
                image, _ = bitmap(page, 200 if n in focus else 136)
                rate = max(1, image.width * image.height * 3 / budget)
                data = encoded(image, "JPEG2000", irreversible=True, mct=1, quality_layers=[rate])
                dest = doc.new_page(width=page.mediabox.width, height=page.mediabox.height)
                dest.set_mediabox(page.mediabox)
                dest.set_cropbox(page.cropbox)
                # Images and selected regions use displayed-page coordinates.
                def place(rect, stream):
                    dest.insert_image(rect * page.derotation_matrix, stream=stream,
                                      rotate=page.rotation, keep_proportion=False)
                place(page.rect, data)
                for rect, patch in patches[n-1]:
                    place(rect, patch)
                dest.set_rotation(page.rotation)
            result = doc.tobytes(garbage=3, deflate=True, use_objstms=1)
        if len(result) <= limit or factor == .84:
            target.write_bytes(result)
            break
    with fitz.open(target) as final:
        for n, payloads in enumerate(expected):
            if payloads and not payloads <= {c.bytes for c in qr_codes(bitmap(final[n], 200)[0])}:
                raise ValueError(f"第 {n+1} 页二维码复核失败，请调整重点页或局部区域后重试")
    return sum(map(len, expected))
