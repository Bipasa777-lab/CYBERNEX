import io
import time

import fitz
from PIL import Image, ImageDraw, ImageFont

from paddleocr import PaddleOCR

OCR_LINES = [
    "CYBERNEX OCR TEST",
    "Pump inspection status: NORMAL",
    "Bearing temperature: 42 C",
    "Calibration due: 2026-12-01",
]


def text_image_png(lines):
    width, height = 1400, 140 + 130 * max(1, len(lines))
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=64)
    y = 50
    for line in lines:
        draw.text((70, y), line, fill="black", font=font)
        y += 130
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def build_page():
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(30, 30, 565, 812), stream=text_image_png(OCR_LINES), keep_proportion=True)
    return doc, page


out = io.StringIO()

for dpi in (150, 200):
    doc, page = build_page()
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    png = pix.tobytes("png")
    out.write(f"dpi={dpi} rendered size={pix.width}x{pix.height}\n")
    doc.close()

    # medium (default) engine
    ocr_med = PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        lang="en",
        enable_mkldnn=False,
    )
    t0 = time.perf_counter()
    res = ocr_med.predict(png)
    dt = time.perf_counter() - t0
    out.write(f"  medium predict: {dt:.1f}s texts={res[0].get('rec_texts') if res and res[0] else None}\n")

# mobile models
doc, page = build_page()
zoom = 200 / 72.0
pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
png = pix.tobytes("png")
doc.close()
try:
    ocr_mob = PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        text_detection_model_name="PP-OCRv6_mobile_det",
        text_recognition_model_name="PP-OCRv6_mobile_rec",
        lang="en",
        enable_mkldnn=False,
    )
    t0 = time.perf_counter()
    res = ocr_mob.predict(png)
    dt = time.perf_counter() - t0
    out.write(f"mobile predict (200dpi): {dt:.1f}s texts={(res[0].get('rec_texts') if res and res[0] else None)}\n")
except Exception as exc:
    out.write(f"mobile models failed: {type(exc).__name__}: {exc}\n")

with open("_bench_out.txt", "w", encoding="utf-8") as f:
    f.write(out.getvalue())
print("done")