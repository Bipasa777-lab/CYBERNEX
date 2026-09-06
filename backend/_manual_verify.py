"""Manual Phase 8 verification: exercise the live FastAPI server.

Generates synthetic PDFs (normal / scanned / multi-scanned / mixed / invalid /
non-PDF) entirely on this machine and POSTs them to /api/v1/pdf/extract.
"""

import io
import json
import sys
import urllib.error
import urllib.request

import fitz
from PIL import Image, ImageDraw, ImageFont

BASE_URL = "http://127.0.0.1:8765/api/v1/pdf/extract"

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


def normal_pdf_bytes():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Digital boiler inspection report page one", fontsize=14)
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Digital boiler inspection report page two", fontsize=14)
    data = doc.tobytes()
    doc.close()
    return data


def scanned_pdf_bytes(lines_list):
    doc = fitz.open()
    for lines in lines_list:
        page = doc.new_page(width=595, height=842)
        page.insert_image(fitz.Rect(30, 30, 565, 812), stream=text_image_png(lines or []), keep_proportion=True)
    data = doc.tobytes()
    doc.close()
    return data


def mixed_pdf_bytes():
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Digital text page one", fontsize=14)
    p2 = doc.new_page()
    p2.insert_image(fitz.Rect(30, 30, 565, 812), stream=text_image_png(["Scanned middle page"]), keep_proportion=True)
    p3 = doc.new_page()
    p3.insert_text((72, 72), "Digital text page three", fontsize=14)
    data = doc.tobytes()
    doc.close()
    return data


def post_pdf(name, data, mime="application/pdf"):
    boundary = "----cybernexboundary42"
    body = (
        b"--" + boundary.encode() + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="' + name.encode() + b'"\r\n'
        b"Content-Type: " + mime.encode() + b"\r\n\r\n"
        + data
        + b"\r\n--" + boundary.encode() + b"--\r\n"
    )
    request = urllib.request.Request(
        BASE_URL,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def summarize(name, status, body):
    print(f"\n### {name} -> HTTP {status}")
    if status != 200:
        print(f"    detail: {body.get('detail', body)}")
        return
    print(f"    filename: {body['filename']}  page_count: {body['page_count']}")
    for page in body["pages"]:
        preview = page["text"][:80].replace("\n", " | ")
        print(
            f"    page {page['page_number']} has_text={page['has_text']} "
            f"chars={page['character_count']} source?={page.get('source', 'n/a')} :: {preview}"
        )


def main():
    default_timeout = urllib.request.socket.getdefaulttimeout()
    print(f"Connecting to {BASE_URL} ...")
    summarize(
        "NORMAL PDF (2 digital text pages)",
        *post_pdf("manual_normal.pdf", normal_pdf_bytes()),
    )
    summarize(
        "SCANNED PDF (1 image-only page)",
        *post_pdf("manual_scanned.pdf", scanned_pdf_bytes([OCR_LINES])),
    )
    summarize(
        "SCANNED MULTI-PAGE PDF (2 image-only pages)",
        *post_pdf("manual_scanned_multi.pdf", scanned_pdf_bytes([OCR_LINES[:2], OCR_LINES[2:4]])),
    )
    summarize(
        "MIXED PDF (text + scanned + text)",
        *post_pdf("manual_mixed.pdf", mixed_pdf_bytes()),
    )
    summarize(
        "INVALID PDF (garbage bytes)",
        *post_pdf("manual_invalid.pdf", b"this is not a real pdf at all"),
    )
    summarize(
        "NON-PDF UPLOAD (notes.txt)",
        *post_pdf("notes.txt", b"plain text file", mime="text/plain"),
    )
    summarize("MISSING FILE (no multipart field)", *post_pdf("missing.pdf", b""))
    urllib.request.socket.setdefaulttimeout(default_timeout)
    print("\nManual verification complete.")


if __name__ == "__main__":
    sys.exit(main())