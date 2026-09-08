import re
import os
import uuid
from typing import Dict, Any, List, Optional
from app.core.config import get_settings
from app.core.logging import logger

try:
    import docx
    from docx.shared import Pt, RGBColor
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    docx = None  # type: ignore
    Pt = None  # type: ignore
    RGBColor = None  # type: ignore

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False
    openpyxl = None  # type: ignore

try:
    import pptx
    PPTX_AVAILABLE = True
except ImportError:
    PPTX_AVAILABLE = False
    pptx = None  # type: ignore

settings = get_settings()

# Match characters disallowed in XML 1.0 documents:
# Valid chars: #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
_ILLEGAL_XML_CHARS_RE = re.compile(
    r"[^\u0009\u000A\u000D\u0020-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]"
)


def sanitize_xml_text(text: Any) -> str:
    """
    Sanitizes string for XML 1.0 / OpenXML compliance.
    Replaces form feeds (\\x0c) and vertical tabs (\\x0b) with newlines,
    and removes NULL bytes (\\x00) and any other control characters
    disallowed in XML 1.0 documents.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    # Convert form feed and vertical tab to newline so text layout is preserved
    text = text.replace("\x0c", "\n").replace("\x0b", "\n")
    # Strip any characters illegal in XML 1.0
    return _ILLEGAL_XML_CHARS_RE.sub("", text)


class DocumentGenerator:
    def generate_docx(
        self,
        title: str,
        sections: List[Dict[str, str]],
        output_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates a sovereign DOCX deliverable in storage/outputs/.
        Enforces a genuine OpenXML ZIP package created via python-docx.
        Never saves plain text under a .docx extension.
        """
        if not DOCX_AVAILABLE or docx is None or Pt is None or RGBColor is None:
            raise RuntimeError(
                "python-docx is not installed. Cannot generate valid DOCX package."
            )

        settings.init_storage_dirs()
        doc_id = f"docgen-{uuid.uuid4().hex[:8]}"

        raw_filename = os.path.basename(output_name) if output_name else f"Deliverable_{doc_id}.docx"
        filename = raw_filename if raw_filename.endswith(".docx") else f"{raw_filename}.docx"

        file_path = os.path.abspath(os.path.join(settings.OUTPUT_DIR, filename))

        clean_title = sanitize_xml_text(title)
        safe_sections = sections or []

        try:
            doc = docx.Document()

            # Header Title
            title_p = doc.add_heading(level=0)
            run = title_p.add_run(clean_title)
            run.font.color.rgb = RGBColor(12, 74, 110)  # Cybernex Sky Blue #0C4A6E
            run.font.size = Pt(22)
            run.bold = True

            doc.add_paragraph("CYBERNEX Sovereign AI Workbench Deliverable")
            doc.add_paragraph("=" * 60)

            for sec in safe_sections:
                if not isinstance(sec, dict):
                    sec = {"title": "Section", "content": str(sec)}
                sec_title = sanitize_xml_text(sec.get("title", "Section"))
                sec_content = sanitize_xml_text(sec.get("content", ""))

                h = doc.add_heading(sec_title, level=1)
                if h.runs:
                    h.runs[0].font.color.rgb = RGBColor(3, 105, 161)

                if sec_content:
                    paragraphs = sec_content.split("\n\n")
                    for p_text in paragraphs:
                        clean_p = p_text.strip()
                        if clean_p:
                            p = doc.add_paragraph(clean_p)
                            if p.style and getattr(p.style, "font", None) is not None:
                                p.style.font.size = Pt(11)
                else:
                    p = doc.add_paragraph("")
                    if p.style and getattr(p.style, "font", None) is not None:
                        p.style.font.size = Pt(11)

            doc.save(file_path)
            logger.info(f"Generated valid DOCX deliverable: {file_path}")

        except Exception as e:
            logger.error(f"Failed to generate valid DOCX file: {e}")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass
            raise RuntimeError(f"Failed to generate valid DOCX package: {e}") from e

        size_bytes = os.path.getsize(file_path) if os.path.exists(file_path) else 1024
        size_str = f"{round(size_bytes / 1024, 1)} KB"

        return {
            "id": doc_id,
            "name": filename,
            "type": "DOCX",
            "size": size_str,
            "status": "Verified",
            "summary": f"Generated formal document '{clean_title}'.",
            "file_path": file_path,
            "download_url": f"/api/v1/documents/{doc_id}/download"
        }

    def generate_xlsx(
        self,
        title: str,
        rows: List[List[Any]],
        output_name: Optional[str] = None
    ) -> Dict[str, Any]:
        settings.init_storage_dirs()
        doc_id = f"docgen-{uuid.uuid4().hex[:8]}"

        raw_filename = os.path.basename(output_name) if output_name else f"Analysis_{doc_id}.xlsx"
        filename = raw_filename if raw_filename.endswith(".xlsx") else f"{raw_filename}.xlsx"

        file_path = os.path.abspath(os.path.join(settings.OUTPUT_DIR, filename))

        if not OPENPYXL_AVAILABLE or openpyxl is None:
            raise RuntimeError("openpyxl is not installed. Cannot generate valid XLSX deliverable.")

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            if ws is None:
                ws = wb.create_sheet("Sheet1")
            clean_title = sanitize_xml_text(title)
            # Remove characters invalid in Excel sheet names: \ / ? * [ ] :
            ws_title = re.sub(r"[\[\]\*\?/\\]", "_", clean_title).strip()[:31]
            ws.title = ws_title if ws_title else "Sheet1"

            safe_rows = rows or []
            for r_idx, row in enumerate(safe_rows, 1):
                if not isinstance(row, (list, tuple)):
                    row = [row]
                for c_idx, val in enumerate(row, 1):
                    clean_val = sanitize_xml_text(val) if isinstance(val, str) else val
                    ws.cell(row=r_idx, column=c_idx, value=clean_val)
            wb.save(file_path)
        except Exception as e:
            logger.error(f"Failed to generate valid XLSX file: {e}")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass
            raise RuntimeError(f"Failed to generate valid XLSX package: {e}") from e

        size_bytes = os.path.getsize(file_path) if os.path.exists(file_path) else 1024
        return {
            "id": doc_id,
            "name": filename,
            "type": "XLSX",
            "size": f"{round(size_bytes / 1024, 1)} KB",
            "status": "Verified",
            "summary": f"Generated spreadsheet deliverable '{title}'.",
            "file_path": file_path,
            "download_url": f"/api/v1/documents/{doc_id}/download"
        }

    def generate_pptx(
        self,
        title: str,
        slides: List[Any],
        output_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates a sovereign PPTX presentation deliverable in storage/outputs/.
        Uses python-pptx to produce a valid OpenXML presentation.
        """
        if not PPTX_AVAILABLE or pptx is None:
            raise RuntimeError("python-pptx is not installed. Cannot generate valid PPTX deliverable.")

        settings.init_storage_dirs()
        doc_id = f"docgen-{uuid.uuid4().hex[:8]}"

        raw_filename = os.path.basename(output_name) if output_name else f"Presentation_{doc_id}.pptx"
        filename = raw_filename if raw_filename.endswith(".pptx") else f"{raw_filename}.pptx"

        file_path = os.path.abspath(os.path.join(settings.OUTPUT_DIR, filename))
        clean_title = sanitize_xml_text(title)
        safe_slides = slides or []

        try:
            prs = pptx.Presentation()
            
            # Title slide
            title_slide_layout = prs.slide_layouts[0]
            slide = prs.slides.add_slide(title_slide_layout)
            if slide.shapes.title and getattr(slide.shapes.title, "has_text_frame", False):
                title_tf = getattr(slide.shapes.title, "text_frame", None)
                if title_tf is not None:
                    title_tf.text = clean_title

            if len(slide.placeholders) > 1:
                sub_ph = slide.placeholders[1]
                if getattr(sub_ph, "has_text_frame", False):
                    sub_tf = getattr(sub_ph, "text_frame", None)
                    if sub_tf is not None:
                        sub_tf.text = "CYBERNEX Sovereign AI Workbench Deliverable"

            # Content slides
            bullet_slide_layout = prs.slide_layouts[1]
            for s_data in safe_slides:
                if not isinstance(s_data, dict):
                    s_data = {"title": "Slide", "content": str(s_data)}
                s_title = sanitize_xml_text(s_data.get("title", "Slide"))
                s_content = sanitize_xml_text(s_data.get("content", ""))

                slide = prs.slides.add_slide(bullet_slide_layout)
                if slide.shapes.title and getattr(slide.shapes.title, "has_text_frame", False):
                    slide_title_tf = getattr(slide.shapes.title, "text_frame", None)
                    if slide_title_tf is not None:
                        slide_title_tf.text = s_title
                
                if len(slide.placeholders) > 1:
                    content_ph = slide.placeholders[1]
                    if getattr(content_ph, "has_text_frame", False):
                        tf = getattr(content_ph, "text_frame", None)
                        if tf is not None:
                            tf.word_wrap = True
                            
                            points = [p.strip() for p in s_content.split("\n") if p.strip()]
                            if points:
                                tf.text = points[0]
                                for pt in points[1:]:
                                    p = tf.add_paragraph()
                                    p.text = pt

            prs.save(file_path)
            logger.info(f"Generated valid PPTX deliverable: {file_path}")

        except Exception as e:
            logger.error(f"Failed to generate valid PPTX file: {e}")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass
            raise RuntimeError(f"Failed to generate valid PPTX package: {e}") from e

        size_bytes = os.path.getsize(file_path) if os.path.exists(file_path) else 1024
        return {
            "id": doc_id,
            "name": filename,
            "type": "PPTX",
            "size": f"{round(size_bytes / 1024, 1)} KB",
            "status": "Verified",
            "summary": f"Generated PowerPoint deliverable '{clean_title}'.",
            "file_path": file_path,
            "download_url": f"/api/v1/documents/{doc_id}/download"
        }

    def _fallback_text(self, file_path: str, title: str, sections: List[Dict[str, str]]):
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"CYBERNEX SOVEREIGN EXECUTIVE REPORT: {title}\n\n")
            for sec in (sections or []):
                if isinstance(sec, dict):
                    f.write(f"=== {sec.get('title', '')} ===\n")
                    f.write(f"{sec.get('content', '')}\n\n")


doc_generator = DocumentGenerator()


