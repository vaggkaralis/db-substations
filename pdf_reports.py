"""
PDF Report Generation for Circuit Breaker Maintenance
Generates maintenance reports matching the official templates
"""

import unicodedata
from datetime import datetime

from strings_proxy import STRINGS as S

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        HRFlowable,
        Image,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    _HAS_REPORTLAB = True
except Exception:
    # Allow importing this module in test environments without reportlab
    _HAS_REPORTLAB = False
import json
import logging
import os
import subprocess
import uuid
import threading
import queue
from config_manager import get_app_setting


def _normalize_pdf_file(path: str) -> bool:
    """If `pikepdf` is available, reopen and re-save the PDF to normalize filters.

    Returns True if normalization ran successfully, False otherwise.
    """
    try:
        import pikepdf
    except Exception:
        logging.debug("pikepdf not available; skipping PDF normalization for %s", path)
        return False
    try:
        # Open and re-save (linearize) to normalize filter chains
        # (removes ASCII85, etc.)
        # allow_overwriting_input lets pikepdf write back to the same filename
        with pikepdf.Pdf.open(path, allow_overwriting_input=True) as pdf:
            pdf.save(path, linearize=True)
        logging.info("PDF normalization succeeded: %s", path)
        return True
    except Exception:
        logging.exception("PDF normalization failed for %s", path)
        return False


def _reset_windows_acl(path: str) -> bool:
    if os.name != "nt":
        return True
    try:
        completed = subprocess.run(
            ["icacls", str(path), "/inheritance:e"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            logging.debug(
                "icacls inheritance restore failed for %s: %s",
                path,
                completed.stdout or completed.stderr,
            )
        completed = subprocess.run(
            ["icacls", str(path), "/reset"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            logging.debug(
                "icacls reset failed for %s: %s",
                path,
                completed.stdout or completed.stderr,
            )
            return False
        return True
    except Exception:
        logging.debug("ACL reset failed for %s", path, exc_info=True)
        return False


def _rewrite_pdf_in_place(path: str) -> bool:
    """Rewrite a PDF via a sibling temp file so the final file
    inherits clean metadata.
    """
    try:
        import pikepdf
    except Exception:
        return False

    fs_path = _fs_path(path)
    temp_path = _temp_pdf_path(fs_path)
    try:
        with pikepdf.Pdf.open(fs_path) as pdf:
            pdf.save(temp_path, linearize=True)
        os.replace(_fs_path(temp_path), fs_path)
        return True
    except Exception:
        logging.debug("Temp rewrite failed for %s", fs_path, exc_info=True)
        try:
            if os.path.exists(_fs_path(temp_path)):
                os.remove(_fs_path(temp_path))
        except Exception:
            pass
        return False


def is_pdf_readable(path: str, *, min_size: int = 32) -> bool:
    """Return True when a PDF exists, has a valid header, and can be parsed.

    If `pikepdf` is unavailable, fall back to a lightweight header/size check.
    """
    try:
        fs_path = _fs_path(path)
        if not os.path.exists(fs_path):
            return False
        if os.path.getsize(fs_path) < min_size:
            return False
        with open(fs_path, "rb") as handle:
            if handle.read(5) != b"%PDF-":
                return False
        try:
            import pikepdf
        except Exception:
            return True
        with pikepdf.Pdf.open(fs_path) as pdf:
            len(pdf.pages)
        return True
    except Exception:
        return False


def repair_pdf_access(path: str, *, normalize_existing: bool = True) -> bool:
    """Best-effort repair for existing PDFs so external readers can open them.

    This clears restrictive filesystem attributes and optionally re-saves the
    PDF through `pikepdf` to normalize older/generated files in place.
    """
    try:
        fs_path = _fs_path(path)
        if not os.path.exists(fs_path):
            return False

        # Fast path for sync/report scans: avoid rewriting PDFs that already
        # parse correctly and have a valid header.
        if is_pdf_readable(fs_path):
            return True

        try:
            os.chmod(fs_path, 0o666)
        except Exception:
            pass

        if os.name == "nt":
            try:
                import ctypes

                FILE_ATTRIBUTE_NORMAL = 0x80
                ctypes.windll.kernel32.SetFileAttributesW(
                    str(fs_path), FILE_ATTRIBUTE_NORMAL
                )
            except Exception:
                pass

        _reset_windows_acl(fs_path)

        if normalize_existing:
            try:
                if not _rewrite_pdf_in_place(fs_path):
                    _normalize_pdf_file(fs_path)
            except Exception:
                logging.debug(
                    "Existing PDF normalization failed for %s", fs_path, exc_info=True
                )

        _reset_windows_acl(fs_path)

        return is_pdf_readable(fs_path)
    except Exception:
        return False


def _fs_path(path: str) -> str:
    abs_path = os.path.abspath(path)
    if os.name != "nt" or abs_path.startswith("\\\\?\\"):
        return abs_path
    if abs_path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + abs_path[2:]
    return "\\\\?\\" + abs_path


def _temp_pdf_path(final_path: str) -> str:
    """Return a temp file path in the same directory as final_path."""
    d = os.path.dirname(final_path) or os.getcwd()
    # ensure dir exists
    os.makedirs(_fs_path(d), exist_ok=True)
    name = os.path.basename(final_path)
    # include uuid to avoid collisions
    tmp_name = f".{name}.tmp.{uuid.uuid4().hex}.pdf"
    return os.path.join(d, tmp_name)


def _finalize_pdf(temp_path: str, final_path: str) -> None:
    """Decide whether to normalize synchronously or asynchronously and
    move the temp PDF into its final location. Behavior is automatic:

    - If `pikepdf` is not available, simply move the file into place.
    - If available and file size < threshold -> normalize synchronously then move.
    - If available and file size >= threshold -> move into place quickly and
      enqueue the final path for background normalization.

    Threshold is read from `pdf_normalize_size_threshold_kb` in app settings.
    """
    try:
        fs_temp = _fs_path(temp_path)
        fs_final = _fs_path(final_path)

        # Ensure parent exists
        parent = os.path.dirname(fs_final)
        os.makedirs(parent, exist_ok=True)

        try:
            size_kb = os.path.getsize(fs_temp) // 1024
        except Exception:
            size_kb = 0

        threshold_kb = int(
            get_app_setting("pdf_normalize_size_threshold_kb", 1024) or 1024
        )

        # Check pikepdf availability
        try:
            has_pike = True
        except Exception:
            has_pike = False

        if not has_pike:
            # No normalization available; move into place atomically
            try:
                os.replace(fs_temp, fs_final)
            except Exception:
                try:
                    os.rename(fs_temp, fs_final)
                except Exception:
                    logging.exception("Failed to move PDF %s -> %s", fs_temp, fs_final)
            return

        # If file is large, move into place and enqueue for background normalization
        if size_kb >= threshold_kb:
            try:
                os.replace(fs_temp, fs_final)
            except Exception:
                try:
                    os.rename(fs_temp, fs_final)
                except Exception:
                    logging.exception(
                        "Failed to move PDF (large) %s -> %s", fs_temp, fs_final
                    )
            try:
                _pdf_norm_queue.put(fs_final)
            except Exception:
                logging.exception(
                    "Failed to enqueue PDF normalization for %s", fs_final
                )
            return

        # Small file: normalize synchronously then move into place
        try:
            _normalize_pdf_file(fs_temp)
        except Exception:
            logging.exception("Synchronous PDF normalization failed for %s", fs_temp)

        try:
            os.replace(fs_temp, fs_final)
        except Exception:
            try:
                os.rename(fs_temp, fs_final)
            except Exception:
                logging.exception(
                    "Failed to move PDF after normalization %s -> %s", fs_temp, fs_final
                )

    finally:
        try:
            # Set permissive mode on the filesystem-resolved path. Use the
            # Windows-long-path form when available to avoid "path too long"
            # errors. Also attempt to clear read-only/hidden attributes on
            # Windows so external readers (Acrobat) can open the file.
            try:
                os.chmod(fs_final, 0o666)
            except Exception:
                try:
                    os.chmod(final_path, 0o666)
                except Exception:
                    pass

            if os.name == "nt":
                try:
                    import ctypes

                    FILE_ATTRIBUTE_NORMAL = 0x80
                    # Use wide-char API to clear attributes
                    ctypes.windll.kernel32.SetFileAttributesW(
                        str(final_path), FILE_ATTRIBUTE_NORMAL
                    )
                except Exception:
                    try:
                        ctypes.windll.kernel32.SetFileAttributesW(
                            str(fs_final), FILE_ATTRIBUTE_NORMAL
                        )
                    except Exception:
                        pass
                try:
                    _reset_windows_acl(fs_final)
                except Exception:
                    pass
        except Exception:
            pass

    def set_pdf_title(path: str, title: str) -> bool:
        """Set the internal PDF Title metadata to `title` using pikepdf.

        Returns True on success, False otherwise. If pikepdf is not available,
        this is a no-op and returns False.
        """
        try:
            import pikepdf
        except Exception:
            return False
        try:
            fs = _fs_path(path)
            with pikepdf.Pdf.open(fs, allow_overwriting_input=True) as pdf:
                info = pdf.open_metadata()
                info["/Title"] = str(title)
                pdf.save(fs)
            return True
        except Exception:
            logging.debug("Failed to set PDF Title for %s", path, exc_info=True)
            return False

    def move_pdf_preserve_title(src: str, dest: str) -> bool:
        """Move a PDF from `src` to `dest`, preserving or copying the internal
        Title metadata from the original into the destination file.

        Safest-effort: will attempt to normalize via pikepdf, set metadata, move
        atomically, and finally reset ACLs. Returns True on success.
        """
        try:
            fs_src = _fs_path(src)
            fs_dest = _fs_path(dest)
            if not os.path.exists(fs_src):
                return False

            # Read original title where possible
            orig_title = None
            try:
                import pikepdf

                with pikepdf.Pdf.open(fs_src) as pdf:
                    try:
                        meta = pdf.open_metadata()
                        orig_title = meta.get("/Title")
                    except Exception:
                        orig_title = None
            except Exception:
                orig_title = None

            # Ensure dest dir exists
            os.makedirs(os.path.dirname(fs_dest), exist_ok=True)

            # Try a temp rewrite into destination directory to ensure clean metadata
            tmp = _temp_pdf_path(fs_dest)
            try:
                try:
                    import pikepdf

                    with pikepdf.Pdf.open(fs_src) as pdf:
                        if orig_title:
                            info = pdf.open_metadata()
                            info["/Title"] = str(orig_title)
                        pdf.save(tmp, linearize=True)
                except Exception:
                    # Fallback to simple copy when pikepdf is not available
                    import shutil

                    shutil.copyfile(fs_src, tmp)

                # Move temp into final place
                try:
                    os.replace(tmp, fs_dest)
                except Exception:
                    os.rename(tmp, fs_dest)

                # Clear restrictive attributes / ACLs
                try:
                    os.chmod(fs_dest, 0o666)
                except Exception:
                    pass
                try:
                    _reset_windows_acl(fs_dest)
                except Exception:
                    pass

                return True
            finally:
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except Exception:
                    pass

        except Exception:
            logging.exception("Failed to move PDF %s -> %s", src, dest)
            return False


# Background normalization queue and worker
_pdf_norm_queue = queue.Queue()


def _pdf_norm_worker():
    while True:
        path = _pdf_norm_queue.get()
        try:
            logging.debug("pdf-norm-worker: picked up job for %s", path)
            # Attempt normalization; _normalize_pdf_file handles missing pikepdf
            ok = _normalize_pdf_file(path)
            if ok:
                logging.info("pdf-norm-worker: normalized %s", path)
            else:
                logging.warning(
                    "pdf-norm-worker: normalization skipped/failed for %s", path
                )
        except Exception:
            logging.exception(
                "pdf-norm-worker: unexpected error while normalizing %s", path
            )
        finally:
            _pdf_norm_queue.task_done()


# Start worker thread as daemon
_pdf_norm_thread = threading.Thread(
    target=_pdf_norm_worker, daemon=True, name="pdf-norm-worker"
)
_pdf_norm_thread.start()


def _safe_filename_component(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).strip()
    text = "".join(ch for ch in text if ch.isalnum() or ch in {"-", "_", " "})
    text = "_".join(text.split())
    return text or "checklist"


def generate_preparation_checklist_pdf(
    checklist_state, categories, metadata=None, output_path=None
):
    if not _HAS_REPORTLAB:
        raise RuntimeError(
            "Το ReportLab δεν είναι διαθέσιμο για δημιουργία PDF checklist."
        )

    metadata = metadata or {}
    state = checklist_state if isinstance(checklist_state, dict) else {}
    selected_categories = state.get("selected_categories") or []
    item_values = state.get("items") if isinstance(state.get("items"), dict) else {}

    if output_path is None:
        reports_dir = os.path.join(os.path.dirname(__file__), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        title_part = _safe_filename_component(
            metadata.get("maintenance_name")
            or metadata.get("title")
            or "preparation_checklist"
        )
        date_part = _safe_filename_component(
            metadata.get("date_time") or datetime.now().strftime("%Y-%m-%d_%H-%M")
        )
        output_path = os.path.join(
            reports_dir, f"{title_part}_{date_part}_checklist.pdf"
        )

    generator = MaintenanceReportGenerator(None)
    font_name = getattr(generator, "greek_font", "Helvetica")
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ChecklistTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=16,
        leading=20,
        alignment=TA_CENTER,
        spaceAfter=10,
    )
    heading_style = ParagraphStyle(
        "ChecklistHeading",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#17324d"),
        spaceBefore=8,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "ChecklistBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10,
        leading=13,
        alignment=TA_LEFT,
    )

    story = [Paragraph("Checklist προετοιμασίας εργασίας", title_style)]

    metadata_lines = []
    if metadata.get("maintenance_name"):
        metadata_lines.append(f"Συντήρηση: {metadata['maintenance_name']}")
    if metadata.get("substation_name"):
        metadata_lines.append(f"Υποσταθμός: {metadata['substation_name']}")
    if metadata.get("maintenance_type"):
        metadata_lines.append(f"Τύπος: {metadata['maintenance_type']}")
    if metadata.get("date_time"):
        metadata_lines.append(f"Ημερομηνία: {metadata['date_time']}")

    for line in metadata_lines:
        story.append(Paragraph(line, body_style))

    if metadata_lines:
        story.append(Spacer(1, 6))

    visible_categories = [
        category
        for category in categories
        if category.get("key") in selected_categories
    ]

    if not visible_categories:
        story.append(Paragraph("Δεν έχουν επιλεγεί κατηγορίες checklist.", body_style))
    else:
        for category in visible_categories:
            category_key = category.get("key")
            story.append(
                Paragraph(
                    category.get("label") or category_key or "Κατηγορία", heading_style
                )
            )

            table_rows = [
                [
                    Paragraph("Κατάσταση", body_style),
                    Paragraph("Ενέργεια", body_style),
                ]
            ]
            for item in category.get("items", []):
                checked = bool(
                    item_values.get(category_key, {}).get(item.get("key"), False)
                )
                table_rows.append(
                    [
                        Paragraph("Ναι" if checked else "Οχι", body_style),
                        Paragraph(
                            str(item.get("label") or item.get("key") or "-"), body_style
                        ),
                    ]
                )

            table = Table(table_rows, colWidths=[28 * mm, 150 * mm], repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dde6ef")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                        ("FONTNAME", (0, 0), (-1, -1), font_name),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("LEADING", (0, 0), (-1, -1), 11),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            story.append(table)
            story.append(Spacer(1, 8))

    temp_path = _temp_pdf_path(output_path)
    doc = SimpleDocTemplate(_fs_path(temp_path), pagesize=A4)
    doc.build(story)
    _finalize_pdf(temp_path, output_path)
    return output_path


# Canonical breaker element names
ELEM_BREAKER_YT = S.get("MESSAGES", {}).get("ELEMENT_BREAKER_YT", "Διακόπτης ΥΤ")
ELEM_BREAKER_MT = S.get("MESSAGES", {}).get("ELEMENT_BREAKER_MT", "Διακόπτης ΜΤ")


class MaintenanceReportGenerator:
    """Generate maintenance reports for circuit breakers"""

    def __init__(self, conn):
        self.conn = conn
        logging.debug("%s", "\n" + "=" * 80)
        logging.debug("PDF REPORT GENERATOR INITIALIZATION")
        logging.debug("%s", "=" * 80)
        self.setup_fonts()
        logging.debug("%s", "=" * 80 + "\n")

    def setup_fonts(self):
        """Setup fonts for Greek text support"""
        # Register fonts with full Greek polytonic (accented) character support
        try:
            import platform

            system = platform.system()

            # First, try bundled DejaVu Sans (known to work correctly with ReportLab)
            bundled_font = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")

            if system == "Windows":
                # Windows fonts - prioritize bundled font, then system fonts
                font_paths = [
                    bundled_font,  # Bundled DejaVu Sans (best for ReportLab)
                    "C:\\Windows\\Fonts\\segoeui.ttf",  # Segoe UI
                    "C:\\Windows\\Fonts\\tahoma.ttf",  # Tahoma
                    "C:\\Windows\\Fonts\\verdana.ttf",  # Verdana
                ]
            elif system == "Darwin":  # macOS
                font_paths = [
                    bundled_font,
                    "/Library/Fonts/Arial Unicode.ttf",
                    "/System/Library/Fonts/Helvetica.ttc",
                ]
            else:  # Linux
                font_paths = [
                    bundled_font,
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                ]

            # Try to register the first available font
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        # Register base font (embeds the TTF when possible)
                        pdfmetrics.registerFont(TTFont("GreekFont", font_path))

                        # Attempt to find and register bold/italic variants
                        # adjacent to the base font
                        base_dir = os.path.dirname(font_path)
                        base_name = os.path.splitext(os.path.basename(font_path))[0]
                        registered_variants = {}

                        def _try_variant(suffix, label):
                            candidates = [
                                f"{base_name}{suffix}.ttf",
                                f"{base_name}-{suffix}.ttf",
                                f"{base_name}{suffix}.TTF",
                            ]
                            # Helpful explicit candidates for DejaVu
                            if base_name.lower().startswith("dejavusans"):
                                if "bold" in suffix.lower():
                                    candidates.insert(0, "DejaVuSans-Bold.ttf")
                                if (
                                    "italic" in suffix.lower()
                                    or "oblique" in suffix.lower()
                                ):
                                    candidates.insert(0, "DejaVuSans-Oblique.ttf")
                            for cand in candidates:
                                cand_path = os.path.join(base_dir, cand)
                                if os.path.exists(cand_path):
                                    try:
                                        name = f"GreekFont{label}"
                                        pdfmetrics.registerFont(TTFont(name, cand_path))
                                        registered_variants[label] = name
                                        logging.debug(
                                            "Registered font variant %s -> %s",
                                            label,
                                            cand_path,
                                        )
                                        return True
                                    except Exception:
                                        logging.exception(
                                            "Failed to register font variant %s at %s",
                                            label,
                                            cand_path,
                                        )
                            return False

                        _try_variant("-Bold", "Bold")
                        _try_variant("-Italic", "Italic")

                        # Register family with available variants
                        try:
                            fam_kwargs = {"normal": "GreekFont"}
                            if "Bold" in registered_variants:
                                fam_kwargs["bold"] = registered_variants["Bold"]
                            if "Italic" in registered_variants:
                                fam_kwargs["italic"] = registered_variants["Italic"]
                            registerFontFamily("GreekFont", **fam_kwargs)
                        except Exception:
                            logging.debug(
                                "Could not register font family variants; "
                                "continuing with base font"
                            )

                        self.greek_font = "GreekFont"
                        font_name = (
                            "DejaVu Sans (bundled)"
                            if font_path == bundled_font
                            else os.path.basename(font_path)
                        )
                        logging.debug("Using font for Greek text: %s", font_name)
                        logging.debug("   Path: %s", font_path)
                        return
                    except Exception:
                        logging.exception("Failed to register %s", font_path)
                        continue

            # If no font found, use Helvetica (limited Greek support)
            logging.warning(
                "No suitable Greek font found, using Helvetica (limited support)"
            )
            self.greek_font = "Helvetica"

        except Exception:
            # Fallback to Helvetica
            logging.exception("Error setting up fonts")
            self.greek_font = "Helvetica"

    def normalize_text(self, text):
        """
        Normalize Greek text to NFC (precomposed) form.
        This converts decomposed characters (letter + combining accent)
        to precomposed characters (single character with accent).
        Required for proper rendering of Greek accented characters in PDFs.
        """
        if text is None:
            return ""
        if isinstance(text, (int, float)):
            text = str(text)
        # Normalize to NFC (precomposed) form
        normalized = unicodedata.normalize("NFC", text)
        # Debug output for first few calls
        if hasattr(self, "_debug_count"):
            self._debug_count += 1
        else:
            self._debug_count = 1
        if self._debug_count <= 3 and len(normalized) > 5:
            logging.debug("normalize_text: '%s' -> '%s'", text[:30], normalized[:30])
        return normalized

    def normalize_table_data(self, data):
        """Normalize all text in a table data structure"""
        normalized = []
        for row in data:
            normalized_row = []
            for cell in row:
                if isinstance(cell, str):
                    normalized_row.append(self.normalize_text(cell))
                else:
                    normalized_row.append(cell)
            normalized.append(normalized_row)
        return normalized

    def get_breaker_category_display(self, breaker_category):
        """Get display name for breaker category"""
        category_map = {
            "SF6": "ΑΕΡΙΟΥ (SF6)",
            "Πτωχού Ελαίου": "ΛΑΔΙΟΥ",
            "Ελαίου": "ΛΑΔΙΟΥ",
            # Legacy English names (for backward compatibility)
            "Oil": "ΛΑΔΙΟΥ",
            # Vacuum (MV) representation
            "Κενού": "ΚΕΝΟΥ",
            "Vacuum": "ΚΕΝΟΥ",
        }
        return category_map.get(breaker_category, breaker_category)

    def generate_maintenance_report(self, maintenance_id, element_id, output_path=None):
        """
        Generate PDF maintenance report for a specific circuit breaker

        Args:
            maintenance_id: ID of the maintenance record
            element_id: ID of the element (circuit breaker)
            output_path: REQUIRED - full path where the PDF should be saved
                        This should be determined by report_sync module to ensure
                        proper OneDrive folder structure and prevent empty folders

        Returns:
            Path to the generated PDF file
        """
        if output_path is None:
            raise ValueError(
                "output_path is required. Use report_sync.get_or_prompt_report_path() "
                "to determine proper output path and check for existing reports."
            )

        c = self.conn.cursor()

        # Get maintenance record
        c.execute(
            """
            SELECT
                m.id,
                m.substation_id,
                m.date_time,
                m.overall_comments,
                m.maintenance_type,
                m.user_name,
                s.name as substation_name,
                s.location,
                s.division
            FROM maintenance m
            JOIN substations s ON m.substation_id = s.id
            WHERE m.id = ?
        """,
            (maintenance_id,),
        )
        maintenance = c.fetchone()

        if not maintenance:
            raise ValueError(f"Maintenance record {maintenance_id} not found")

        (
            maint_id,
            sub_id,
            date_time,
            overall_comments,
            maint_type,
            user_name,
            sub_name,
            sub_location,
            division,
        ) = maintenance

        # Get element details
        c.execute(
            """
            SELECT
                e.id,
                e.element_type,
                e.name,
                e.serial_number,
                e.manufacturer,
                e.model,
                e.breaker_category,
                e.voltage_level,
                e.gate,
                e.manufacture_year,
                em.manufacturer as model_manufacturer,
                em.model_name
            FROM elements e
            LEFT JOIN element_models em ON e.element_model_id = em.id
            WHERE e.id = ?
        """,
            (element_id,),
        )
        element = c.fetchone()

        if not element:
            raise ValueError(f"Element {element_id} not found")

        (
            elem_id,
            elem_type,
            elem_name,
            serial_num,
            manufacturer,
            model,
            breaker_category,
            voltage_level,
            gate,
            manufacture_year,
            model_manufacturer,
            model_name,
        ) = element

        # Legacy records can have a NULL breaker category; default to oil report
        # to keep retroactive report generation resilient.
        breaker_category = (breaker_category or "").strip()
        if not breaker_category:
            breaker_category = "Ελαίου"

        # Get maintenance measurements for this element
        c.execute(
            """
            SELECT
                element_comments,
                insulation_closed_fa_ground,
                insulation_closed_fa_unit,
                insulation_closed_fb_ground,
                insulation_closed_fb_unit,
                insulation_closed_fc_ground,
                insulation_closed_fc_unit,
                insulation_open_fa_fa,
                insulation_open_fa_unit,
                insulation_open_fb_fb,
                insulation_open_fb_unit,
                insulation_open_fc_fc,
                insulation_open_fc_unit,
                contact_resistance_fa_fa,
                contact_resistance_fb_fb,
                contact_resistance_fc_fc,
                operations_count,
                sf6_n2_fa,
                h2o_fa,
                so2_fa,
                sf6_n2_fb,
                h2o_fb,
                so2_fb,
                sf6_n2_fc,
                h2o_fc,
                so2_fc,
                vidar_fa,
                vidar_fb,
                vidar_fc
            FROM maintenance_elements
            WHERE maintenance_id = ? AND element_id = ?
        """,
            (maintenance_id, element_id),
        )
        measurements = c.fetchone()

        if not measurements:
            raise ValueError(
                f"No maintenance data found for element {element_id} "
                f"in maintenance {maintenance_id}"
            )

        # Ensure parent directory exists (folder should be created by caller)
        parent_dir = os.path.dirname(output_path)
        if not os.path.exists(_fs_path(parent_dir)):
            os.makedirs(_fs_path(parent_dir), exist_ok=True)

        output_write_path = _fs_path(output_path)

        # Generate the PDF based on breaker category
        category_lower = breaker_category.lower()
        if "sf6" in category_lower:
            self._generate_sf6_report(
                output_write_path, maintenance, element, measurements
            )
        elif category_lower in ["oil", "πτωχού ελαίου", "ελαίου"]:
            self._generate_oil_report(
                output_write_path, maintenance, element, measurements
            )
        elif category_lower in ["vacuum", "κενού"]:
            self._generate_vacuum_report(
                output_write_path, maintenance, element, measurements
            )
        else:
            raise ValueError(f"Unknown breaker category: {breaker_category}")

        return output_path

    def _create_header(self, story, breaker_type, substation_name):
        """Create report header"""
        styles = getSampleStyleSheet()

        # Title style
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=16,
            textColor=colors.HexColor("#000080"),
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName=self.greek_font,
        )

        subtitle_style = ParagraphStyle(
            "CustomSubtitle",
            parent=styles["Normal"],
            fontSize=14,
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName=self.greek_font,
        )

        meta_style = ParagraphStyle(
            "CustomMeta",
            parent=styles["Normal"],
            fontSize=8.5,
            textColor=colors.HexColor("#5f6b7a"),
            spaceAfter=16,
            alignment=TA_CENTER,
            fontName=self.greek_font,
        )

        title_text = S["MESSAGES"].get(
            "MAINTENANCE_REPORT_TITLE", "ΔΕΛΤΙΟ ΣΥΝΤΗΡΗΣΗΣ ΔΙΑΚΟΠΤΗ {breaker}"
        )
        subtitle_text = S["MESSAGES"].get(
            "MAINTENANCE_REPORT_SUBTITLE", "Υποσταθμός: {substation}"
        )
        title = Paragraph(
            self.normalize_text(title_text.format(breaker=breaker_type)),
            title_style,
        )
        subtitle = Paragraph(
            self.normalize_text(subtitle_text.format(substation=substation_name)),
            subtitle_style,
        )
        meta = Paragraph(
            self.normalize_text(
                "Εσωτερική χρήση ΔΕΔΔΗΕ | Παραγόμενο εταιρικό έγγραφο συντήρησης"
            ),
            meta_style,
        )

        # Prefer to let _get_logo_flowable decide unit sizes so module can be
        # imported even when reportlab (and `mm`) is not available.
        logo = self._get_logo_flowable()
        if logo:
            logo.hAlign = "RIGHT"
            header_table = Table(
                [[[title, subtitle, meta], logo]], colWidths=[140 * mm, 40 * mm]
            )
            header_table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.append(header_table)
        else:
            story.append(title)
            story.append(subtitle)
            story.append(meta)

        story.append(Spacer(1, 12))

    def _get_logo_flowable(self, max_width=None, max_height=None):
        """Return a scaled logo Image flowable if available.

        Use `mm` units if reportlab is present; otherwise fall back to pixels.
        """
        # Lazy-resolve mm to avoid NameError when reportlab is not installed
        try:
            from reportlab.lib.units import mm as _mm
        except Exception:
            _mm = None
        if max_width is None:
            max_width = 28 * _mm if _mm is not None else 28
        if max_height is None:
            max_height = 20 * _mm if _mm is not None else 20
        logo_path = os.path.join(os.path.dirname(__file__), "logo_deddie.png")
        fallback_path = os.path.join(os.path.dirname(__file__), "deddie_logo.png")
        if not os.path.exists(logo_path) and not os.path.exists(fallback_path):
            return None

        if not os.path.exists(logo_path):
            logo_path = fallback_path
        try:
            reader = ImageReader(logo_path)
            img_width, img_height = reader.getSize()
            scale = min(max_width / img_width, max_height / img_height)
            return Image(logo_path, width=img_width * scale, height=img_height * scale)
        except Exception:
            return None

    def _create_official_footer(self, *, document_kind: str) -> list:
        styles = getSampleStyleSheet()
        note_style = ParagraphStyle(
            "OfficialFooterNote",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#5f6b7a"),
            alignment=TA_CENTER,
            fontName=self.greek_font,
        )
        time_style = ParagraphStyle(
            "OfficialFooterTime",
            parent=note_style,
            fontSize=7.5,
            textColor=colors.HexColor("#7a8594"),
        )
        return [
            Spacer(1, 18),
            HRFlowable(
                width="100%",
                color=colors.HexColor("#c9d1db"),
                thickness=0.7,
                spaceBefore=0,
                spaceAfter=6,
            ),
            (
                Paragraph(
                    self.normalize_text(
                        (
                            f"{document_kind} - Το παρόν έγγραφο παράγεται από το "
                            "εταιρικό σύστημα DB Substations της ΔΕΔΔΗΕ και "
                            "αποτυπώνει τα καταχωρημένα δεδομένα της συγκεκριμένης "
                            "συντήρησης. Απαιτείται έλεγχος και υπογραφή από το "
                            "αρμόδιο προσωπικό όπου προβλέπεται."
                        )
                    ),
                    note_style,
                )
            ),
            Spacer(1, 4),
            Paragraph(
                self.normalize_text(
                    f"Δημιουργήθηκε: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                ),
                time_style,
            ),
        ]

    def _create_info_table(self, element_data, maintenance_data):
        """Create general information table"""
        (
            maint_id,
            sub_id,
            date_time,
            overall_comments,
            maint_type,
            user_name,
            sub_name,
            sub_location,
            division,
        ) = maintenance_data
        (
            elem_id,
            elem_type,
            elem_name,
            serial_num,
            manufacturer,
            model,
            breaker_category,
            voltage_level,
            gate,
            manufacture_year,
            model_manufacturer,
            model_name,
        ) = element_data

        # Use model data if available, otherwise element data
        display_manufacturer = (
            model_manufacturer if model_manufacturer else manufacturer
        )
        display_model = model_name if model_name else model

        data = [
            [S["MESSAGES"].get("REPORT_SECTION_BREAKER_INFO", "ΣΤΟΙΧΕΙΑ ΔΙΑΚΟΠΤΗ"), ""],
            [S["MESSAGES"].get("ELEMENT_NAME_LABEL", "Όνομα:"), elem_name or "-"],
            [
                S["MESSAGES"].get("SERIAL_NUMBER_LABEL", "Αριθμός Σειράς (S/N):"),
                serial_num or "-",
            ],
            [
                S["MESSAGES"].get("MANUFACTURER_LABEL", "Κατασκευαστής:"),
                display_manufacturer or "-",
            ],
            ["Μοντέλο:", display_model or "-"],
            ["Τάση (kV):", voltage_level or "-"],
            ["Πύλη:", gate or "-"],
            ["Έτος Κατασκευής:", manufacture_year or "-"],
            ["", ""],
            ["ΣΤΟΙΧΕΙΑ ΣΥΝΤΗΡΗΣΗΣ", ""],
            ["Ημερομηνία:", date_time or "-"],
            ["Τύπος Συντήρησης:", maint_type or "-"],
            ["Τομέας:", division or "-"],
        ]

        # Normalize all text for proper Greek character rendering
        data = self.normalize_table_data(data)

        table = Table(data, colWidths=[80 * mm, 100 * mm])
        table.setStyle(
            TableStyle(
                [
                    # Header rows
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
                    ("BACKGROUND", (0, 9), (-1, 9), colors.HexColor("#4472C4")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("TEXTCOLOR", (0, 9), (-1, 9), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), self.greek_font),
                    ("FONTNAME", (0, 9), (-1, 9), self.greek_font),
                    ("FONTSIZE", (0, 0), (-1, 0), 12),
                    ("FONTSIZE", (0, 9), (-1, 9), 12),
                    # All cells
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    (
                        "FONTNAME",
                        (0, 0),
                        (-1, -1),
                        self.greek_font,
                    ),  # Apply Greek font to ALL cells
                    ("FONTSIZE", (0, 1), (-1, -1), 10),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )

        return table

    def _create_measurements_table(self, measurements, breaker_category):
        """Create measurements table for insulation and contact resistance"""
        breaker_category = (breaker_category or "").strip()
        (
            elem_comments,
            ins_closed_fa,
            ins_closed_fa_unit,
            ins_closed_fb,
            ins_closed_fb_unit,
            ins_closed_fc,
            ins_closed_fc_unit,
            ins_open_fa,
            ins_open_fa_unit,
            ins_open_fb,
            ins_open_fb_unit,
            ins_open_fc,
            ins_open_fc_unit,
            cont_fa,
            cont_fb,
            cont_fc,
            ops_count,
            sf6_n2_fa,
            h2o_fa,
            so2_fa,
            sf6_n2_fb,
            h2o_fb,
            so2_fb,
            sf6_n2_fc,
            h2o_fc,
            so2_fc,
            vidar_fa,
            vidar_fb,
            vidar_fc,
        ) = measurements

        # Helper to format value with unit
        def format_value(value, unit=""):
            if value is None or value == "":
                return "-"
            return f"{value} {unit}" if unit else f"{value}"

        tables = []

        # Operations Counter
        if ops_count is not None:
            ops_data = [
                ["ΜΕΤΡΗΤΗΣ ΧΕΙΡΙΣΜΩΝ", ""],
                ["Αριθμός Χειρισμών:", str(ops_count)],
            ]
            ops_data = self.normalize_table_data(ops_data)
            ops_table = Table(ops_data, colWidths=[90 * mm, 90 * mm])
            ops_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("FONTNAME", (0, 0), (-1, 0), self.greek_font),
                        ("FONTSIZE", (0, 0), (-1, 0), 11),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                        (
                            "FONTNAME",
                            (0, 0),
                            (-1, -1),
                            self.greek_font,
                        ),  # Apply Greek font to ALL cells
                        ("FONTSIZE", (0, 1), (-1, -1), 10),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            tables.append(ops_table)

        # Insulation and Contact Resistance
        data = [
            ["ΜΕΤΡΗΣΕΙΣ ΜΟΝΩΣΕΩΝ", "", "", ""],
            ["Θέση", "Φάση Α", "Φάση Β", "Φάση Γ"],
            [
                "Κλειστή Θέση (προς γη)",
                format_value(ins_closed_fa, ins_closed_fa_unit),
                format_value(ins_closed_fb, ins_closed_fb_unit),
                format_value(ins_closed_fc, ins_closed_fc_unit),
            ],
            [
                "Ανοιχτή Θέση (μεταξύ επαφών)",
                format_value(ins_open_fa, ins_open_fa_unit),
                format_value(ins_open_fb, ins_open_fb_unit),
                format_value(ins_open_fc, ins_open_fc_unit),
            ],
            ["", "", "", ""],
            ["ΜΕΤΡΗΣΕΙΣ ΑΝΤΙΣΤΑΣΗΣ ΕΠΑΦΩΝ (μΩ)", "", "", ""],
            ["", "Φάση Α", "Φάση Β", "Φάση Γ"],
            [
                "Αντίσταση Επαφών",
                format_value(cont_fa, "μΩ") if cont_fa else "-",
                format_value(cont_fb, "μΩ") if cont_fb else "-",
                format_value(cont_fc, "μΩ") if cont_fc else "-",
            ],
        ]

        data = self.normalize_table_data(data)
        table = Table(data, colWidths=[60 * mm, 40 * mm, 40 * mm, 40 * mm])
        table.setStyle(
            TableStyle(
                [
                    # Headers
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#70AD47")),
                    ("BACKGROUND", (0, 5), (-1, 5), colors.HexColor("#FFC000")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("TEXTCOLOR", (0, 5), (-1, 5), colors.black),
                    ("FONTNAME", (0, 0), (-1, 0), self.greek_font),
                    ("FONTNAME", (0, 5), (-1, 5), self.greek_font),
                    ("FONTSIZE", (0, 0), (-1, 0), 11),
                    ("FONTSIZE", (0, 5), (-1, 5), 11),
                    ("SPAN", (0, 0), (-1, 0)),
                    ("SPAN", (0, 5), (-1, 5)),
                    # Subheaders
                    ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#A9D08E")),
                    ("BACKGROUND", (0, 6), (-1, 6), colors.HexColor("#FFE699")),
                    ("FONTNAME", (0, 1), (-1, 1), self.greek_font),
                    ("FONTNAME", (0, 6), (-1, 6), self.greek_font),
                    # All cells - MUST set font for all cells
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    (
                        "FONTNAME",
                        (0, 0),
                        (-1, -1),
                        self.greek_font,
                    ),  # Apply Greek font to ALL cells
                    ("FONTSIZE", (0, 1), (-1, -1), 10),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        tables.append(table)

        # SF6 Gas Quality (only for SF6 breakers)
        if "SF6" in breaker_category.upper() and (sf6_n2_fa or h2o_fa or so2_fa):
            sf6_data = [
                ["ΠΟΙΟΤΗΤΑ ΑΕΡΙΟΥ SF6", "", "", ""],
                ["", "SF6/N2 (%)", "H2O (°C atm)", "SO2 (ppm)"],
                [
                    "ΦΑ",
                    format_value(sf6_n2_fa),
                    format_value(h2o_fa),
                    format_value(so2_fa),
                ],
                [
                    "ΦΒ",
                    format_value(sf6_n2_fb),
                    format_value(h2o_fb),
                    format_value(so2_fb),
                ],
                [
                    "ΦΓ",
                    format_value(sf6_n2_fc),
                    format_value(h2o_fc),
                    format_value(so2_fc),
                ],
            ]

            sf6_data = self.normalize_table_data(sf6_data)
            sf6_table = Table(sf6_data, colWidths=[40 * mm, 45 * mm, 45 * mm, 45 * mm])
            sf6_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#9966FF")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("FONTNAME", (0, 0), (-1, 0), self.greek_font),
                        ("FONTSIZE", (0, 0), (-1, 0), 11),
                        ("SPAN", (0, 0), (-1, 0)),
                        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#CC99FF")),
                        ("FONTNAME", (0, 1), (-1, 1), self.greek_font),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                        (
                            "FONTNAME",
                            (0, 0),
                            (-1, -1),
                            self.greek_font,
                        ),  # Apply Greek font to ALL cells
                        ("FONTSIZE", (0, 1), (-1, -1), 10),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            tables.append(sf6_table)

        # Vacuum Check VIDAR (only for Vacuum breakers)
        if breaker_category.lower() in ["vacuum", "κενού"] and (
            vidar_fa or vidar_fb or vidar_fc
        ):
            vidar_data = [
                ["ΕΛΕΓΧΟΣ ΚΕΝΟΥ (VIDAR)", "", "", ""],
                ["", "ΦΑ-ΦΑ", "ΦΒ-ΦΒ", "ΦΓ-ΦΓ"],
                [
                    "Τιμή",
                    format_value(vidar_fa),
                    format_value(vidar_fb),
                    format_value(vidar_fc),
                ],
            ]

            vidar_data = self.normalize_table_data(vidar_data)
            vidar_table = Table(
                vidar_data, colWidths=[40 * mm, 45 * mm, 45 * mm, 45 * mm]
            )
            vidar_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FF6666")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("FONTNAME", (0, 0), (-1, 0), self.greek_font),
                        ("FONTSIZE", (0, 0), (-1, 0), 11),
                        ("SPAN", (0, 0), (-1, 0)),
                        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#FF9999")),
                        ("FONTNAME", (0, 1), (-1, 1), self.greek_font),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                        (
                            "FONTNAME",
                            (0, 0),
                            (-1, -1),
                            self.greek_font,
                        ),  # Apply Greek font to ALL cells
                        ("FONTSIZE", (0, 1), (-1, -1), 10),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            tables.append(vidar_table)

        return tables

    def _create_comments_section(self, overall_comments, element_comments):
        """Create comments section"""
        styles = getSampleStyleSheet()

        comment_style = ParagraphStyle(
            "CommentStyle",
            parent=styles["Normal"],
            fontSize=10,
            spaceAfter=10,
            alignment=TA_LEFT,
            fontName=self.greek_font,
        )

        story_items = []

        if element_comments:
            story_items.append(Spacer(1, 12))
            story_items.append(
                Paragraph(
                    self.normalize_text("<b>ΣΧΟΛΙΑ ΣΤΟΙΧΕΙΟΥ:</b>"), comment_style
                )
            )
            story_items.append(
                Paragraph(self.normalize_text(element_comments), comment_style)
            )

        if overall_comments:
            story_items.append(Spacer(1, 12))
            story_items.append(
                Paragraph(
                    self.normalize_text("<b>ΓΕΝΙΚΑ ΣΧΟΛΙΑ ΣΥΝΤΗΡΗΣΗΣ:</b>"),
                    comment_style,
                )
            )
            story_items.append(
                Paragraph(self.normalize_text(overall_comments), comment_style)
            )

        return story_items

    def _generate_sf6_report(
        self, output_path, maintenance_data, element_data, measurements
    ):
        """Generate SF6 (Gas) circuit breaker maintenance report"""
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
        )

        story = []

        # Header
        self._create_header(
            story, "ΑΕΡΙΟΥ (SF6)", maintenance_data[6]
        )  # substation_name

        # Information table
        info_table = self._create_info_table(element_data, maintenance_data)
        story.append(info_table)
        story.append(Spacer(1, 15))

        # Measurements tables (returns list of tables)
        measurements_tables = self._create_measurements_table(measurements, "SF6")
        for table in measurements_tables:
            story.append(table)
            story.append(Spacer(1, 10))

        # Comments
        comments = self._create_comments_section(maintenance_data[3], measurements[0])
        story.extend(comments)

        # Footer
        story.extend(
            self._create_official_footer(document_kind="Δελτίο συντήρησης διακόπτη SF6")
        )

        # Build PDF to temp and finalize (automatic normalization/move)
        temp_path = _temp_pdf_path(output_path)
        doc = SimpleDocTemplate(
            _fs_path(temp_path),
            pagesize=A4,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
        )
        doc.build(story)
        _finalize_pdf(temp_path, output_path)

    def _generate_oil_report(
        self, output_path, maintenance_data, element_data, measurements
    ):
        """Generate Oil circuit breaker maintenance report"""
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
        )

        story = []

        # Header
        self._create_header(story, "ΛΑΔΙΟΥ", maintenance_data[6])  # substation_name

        # Information table
        info_table = self._create_info_table(element_data, maintenance_data)
        story.append(info_table)
        story.append(Spacer(1, 15))

        # Measurements tables (returns list of tables)
        measurements_tables = self._create_measurements_table(measurements, "Oil")
        for table in measurements_tables:
            story.append(table)
            story.append(Spacer(1, 10))

        # Comments
        comments = self._create_comments_section(maintenance_data[3], measurements[0])
        story.extend(comments)

        # Attempt to include a brief DGA diagnostics block when a recent DGA
        # measurement exists for this maintenance/element.
        try:
            from dga_reports import analyze_dga_diagnostics

            cur = self.conn.cursor()
            # Look for latest DGA measurement for this element in the same maintenance
            cur.execute(
                """
                SELECT
                    h2,
                    c2h2,
                    c2h4,
                    c2h6,
                    co,
                    co2,
                    ch4,
                    o2,
                    c3h8,
                    n2,
                    h2o,
                    measurement_date
                FROM dga_measurements
                WHERE maintenance_id = ? AND element_id = ?
                ORDER BY measurement_date DESC, created_at DESC
                LIMIT 1
                """,
                (maintenance_data[0], element_data[0]),
            )
            row = cur.fetchone()
            if row:
                vals = {
                    "h2": row[0],
                    "c2h2": row[1],
                    "c2h4": row[2],
                    "c2h6": row[3],
                    "co": row[4],
                    "co2": row[5],
                    "ch4": row[6],
                    "o2": row[7],
                    "c3h8": row[8],
                    "n2": row[9],
                    "h2o": row[10],
                }
                diag = analyze_dga_diagnostics(vals)
                if diag:
                    styles = getSampleStyleSheet()
                    body_style = ParagraphStyle(
                        "DgaDiag",
                        parent=styles["BodyText"],
                        fontName=self.greek_font,
                        fontSize=9,
                        leading=11,
                    )
                    story.append(Spacer(1, 8))
                    story.append(
                        Paragraph(
                            self.normalize_text(
                                "DGA Diagnostics (latest measurement):"
                            ),
                            body_style,
                        )
                    )
                    primary = diag.get("primary") or {}
                    consensus = diag.get("consensus") or {}
                    findings = diag.get("findings") or []
                    if primary.get("display_summary"):
                        story.append(
                            Paragraph(
                                self.normalize_text(primary.get("display_summary")),
                                body_style,
                            )
                        )
                    if consensus and consensus.get("summary"):
                        story.append(
                            Paragraph(
                                self.normalize_text(consensus.get("summary")),
                                body_style,
                            )
                        )
                    # Add up to two findings
                    for f in findings[:2]:
                        label_txt = f.get("label") or f.get("code")
                        summary_txt = f.get("summary") or ""
                        line = f"{label_txt}: {summary_txt}"
                        story.append(Paragraph(self.normalize_text(line), body_style))
                    story.append(Spacer(1, 6))
        except Exception:
            # Non-fatal: do not break PDF generation if diagnostics fail
            pass

        # Footer
        story.extend(
            self._create_official_footer(
                document_kind="Δελτίο συντήρησης διακόπτη ελαίου"
            )
        )

        # Build PDF to temp and finalize (automatic normalization/move)
        temp_path = _temp_pdf_path(output_path)
        doc = SimpleDocTemplate(
            _fs_path(temp_path),
            pagesize=A4,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
        )
        doc.build(story)
        _finalize_pdf(temp_path, output_path)

    def _generate_vacuum_report(
        self, output_path, maintenance_data, element_data, measurements
    ):
        """Generate Vacuum circuit breaker maintenance report"""
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
        )

        story = []

        # Header
        self._create_header(story, "ΚΕΝΟΥ", maintenance_data[6])  # substation_name

        # Information table
        info_table = self._create_info_table(element_data, maintenance_data)
        story.append(info_table)
        story.append(Spacer(1, 15))

        # Measurements tables (returns list of tables)
        measurements_tables = self._create_measurements_table(measurements, "Vacuum")
        for table in measurements_tables:
            story.append(table)
            story.append(Spacer(1, 10))

        # Comments
        comments = self._create_comments_section(maintenance_data[3], measurements[0])
        story.extend(comments)

        # Footer
        story.extend(
            self._create_official_footer(
                document_kind="Δελτίο συντήρησης διακόπτη κενού"
            )
        )

        # Build PDF to temp and finalize (automatic normalization/move)
        temp_path = _temp_pdf_path(output_path)
        doc = SimpleDocTemplate(
            _fs_path(temp_path),
            pagesize=A4,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
        )
        doc.build(story)
        _finalize_pdf(temp_path, output_path)


def generate_maintenance_report(conn, maintenance_id, element_id, output_path=None):
    """
    Convenience function to generate a maintenance report

    Args:
        conn: Database connection
        maintenance_id: ID of the maintenance record
        element_id: ID of the circuit breaker element
        output_path: REQUIRED - full path where the PDF should be saved

    Returns:
        Path to the generated PDF file

    Note:
        output_path must be provided. Use report_sync module to determine proper path:

        from report_sync import safe_generate_and_store_report
        result = safe_generate_and_store_report(
            conn,
            maintenance_id=mid,
            element_id=eid,
        )
    """
    if output_path is None:
        raise ValueError(
            "output_path is required. Use report_sync.safe_generate_and_store_report() "
            "instead."
        )

    generator = MaintenanceReportGenerator(conn)
    return generator.generate_maintenance_report(
        maintenance_id, element_id, output_path
    )


def generate_maintenance_overview_report(conn, maintenance_id, output_path=None):
    """Generate a maintenance-level summary PDF covering all linked elements."""
    if not _HAS_REPORTLAB:
        raise RuntimeError(
            "Το ReportLab δεν είναι διαθέσιμο για δημιουργία συνολικού PDF συντήρησης."
        )

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            m.id,
            m.date_time,
            m.name,
            m.maintenance_type,
            m.overall_comments,
            m.user_name,
            s.name,
            s.location,
            s.division,
            p.name
        FROM maintenance m
        JOIN substations s ON s.id = m.substation_id
        LEFT JOIN people p ON p.id = m.responsible_id
        WHERE m.id = ?
        """,
        (maintenance_id,),
    )
    maintenance = cursor.fetchone()
    if not maintenance:
        raise ValueError(f"Maintenance record {maintenance_id} not found")

    (
        maint_id,
        date_time,
        maintenance_name,
        maintenance_type,
        overall_comments,
        user_name,
        substation_name,
        location,
        division,
        responsible_name,
    ) = maintenance

    cursor.execute(
        """
        SELECT e.name, e.element_type, e.gate, e.breaker_category, me.element_comments
        FROM maintenance_elements me
        JOIN elements e ON e.id = me.element_id
        WHERE me.maintenance_id = ?
        ORDER BY e.gate, e.element_type, e.name
        """,
        (maintenance_id,),
    )
    elements = cursor.fetchall() or []

    if output_path is None:
        reports_dir = os.path.join(os.path.dirname(__file__), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        output_path = os.path.join(
            reports_dir, f"maintenance_{maintenance_id}_overview.pdf"
        )

    generator = MaintenanceReportGenerator(conn)
    font_name = getattr(generator, "greek_font", "Helvetica")
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "MaintenanceOverviewTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=16,
        leading=20,
        alignment=TA_CENTER,
        spaceAfter=10,
    )
    section_style = ParagraphStyle(
        "MaintenanceOverviewSection",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#17324d"),
        spaceBefore=8,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "MaintenanceOverviewBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9,
        leading=12,
        alignment=TA_LEFT,
    )
    small_style = ParagraphStyle(
        "MaintenanceOverviewSmall",
        parent=body_style,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#5f6b7a"),
    )

    logo = generator._get_logo_flowable(max_width=30 * mm, max_height=22 * mm)
    header_left = [
        Paragraph(generator.normalize_text("ΔΕΔΔΗΕ"), title_style),
        Paragraph(
            generator.normalize_text("Συνοπτική Αναφορά Συντήρησης"), section_style
        ),
        Paragraph(
            generator.normalize_text(f"Κωδικός εγγράφου: M{maintenance_id}"),
            small_style,
        ),
    ]
    header_table = Table(
        [[header_left, logo or Spacer(1, 1)]],
        colWidths=[145 * mm, 35 * mm],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    summary_rows = [
        ["Υποσταθμός", substation_name or "-", "Ημερομηνία", date_time or "-"],
        ["Συντήρηση", maintenance_name or "-", "Τύπος", maintenance_type or "-"],
        ["Υπεύθυνος", responsible_name or user_name or "-", "Τομέας", division or "-"],
        ["Τοποθεσία", location or "-", "Στοιχεία", str(len(elements))],
    ]
    summary_table = Table(summary_rows, colWidths=[28 * mm, 62 * mm, 28 * mm, 62 * mm])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#17324d")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#17324d")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
                ("TEXTCOLOR", (2, 0), (2, -1), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c9d1db")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    story = [
        header_table,
        Spacer(1, 10),
        summary_table,
        Spacer(1, 10),
    ]

    story.append(Paragraph(generator.normalize_text("Συνολικά Σχόλια"), section_style))
    story.append(
        Paragraph(generator.normalize_text(overall_comments or "-"), body_style)
    )
    story.append(Spacer(1, 8))

    story.append(
        Paragraph(
            generator.normalize_text("Στοιχεία Συνδεδεμένων Στοιχείων"), section_style
        )
    )

    # Render each element as a small block (name/type/gate/category) followed
    # by its comments. This avoids extremely tall single table cells which
    # ReportLab cannot split across pages when a single cell's content exceeds
    # the page frame.
    for (
        element_name,
        element_type,
        gate,
        breaker_category,
        element_comments,
    ) in elements:
        element_table = Table(
            [
                [
                    Paragraph(
                        generator.normalize_text(f"<b>{element_name or '-'}</b>"),
                        body_style,
                    ),
                    Paragraph(
                        generator.normalize_text(element_type or "-"), body_style
                    ),
                    Paragraph(generator.normalize_text(gate or "-"), body_style),
                    Paragraph(
                        generator.normalize_text(breaker_category or "-"), body_style
                    ),
                ]
            ],
            colWidths=[58 * mm, 54 * mm, 28 * mm, 40 * mm],
        )
        element_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d7dee7")),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f6f8fb")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(element_table)
        if element_comments:
            max_chars = 4000
            comment_text = element_comments
            if isinstance(comment_text, str) and len(comment_text) > max_chars:
                comment_text = comment_text[:max_chars] + "\n... (truncated)"
            story.append(Spacer(1, 4))
            story.append(
                Paragraph(
                    generator.normalize_text(f"<b>Σχόλια:</b> {comment_text}"),
                    body_style,
                )
            )
        story.append(Spacer(1, 6))

    story.extend(
        generator._create_official_footer(document_kind="Συνοπτική αναφορά συντήρησης")
    )

    temp_path = _temp_pdf_path(output_path)
    doc = SimpleDocTemplate(
        _fs_path(temp_path),
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
    )
    doc.build(story)
    _finalize_pdf(temp_path, output_path)
    return output_path


class InspectionReportGenerator:
    """Generate inspection reports from stored inspection data"""

    def __init__(self, conn):
        self.conn = conn
        self.setup_fonts()

    def setup_fonts(self):
        """Setup fonts for Greek text support"""
        try:
            import platform

            system = platform.system()

            bundled_font = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")

            if system == "Windows":
                font_paths = [
                    bundled_font,
                    "C:\\Windows\\Fonts\\segoeui.ttf",
                    "C:\\Windows\\Fonts\\tahoma.ttf",
                    "C:\\Windows\\Fonts\\verdana.ttf",
                ]
            elif system == "Darwin":
                font_paths = [
                    bundled_font,
                    "/Library/Fonts/Arial Unicode.ttf",
                    "/System/Library/Fonts/Helvetica.ttc",
                ]
            else:
                font_paths = [
                    bundled_font,
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                ]

            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(
                            TTFont("GreekFontInspection", font_path)
                        )

                        base_dir = os.path.dirname(font_path)
                        base_name = os.path.splitext(os.path.basename(font_path))[0]
                        registered_variants = {}

                        def _try_variant(suffix, label):
                            candidates = [
                                f"{base_name}{suffix}.ttf",
                                f"{base_name}-{suffix}.ttf",
                                f"{base_name}{suffix}.TTF",
                            ]
                            if base_name.lower().startswith("dejavusans"):
                                if "bold" in suffix.lower():
                                    candidates.insert(0, "DejaVuSans-Bold.ttf")
                                if (
                                    "italic" in suffix.lower()
                                    or "oblique" in suffix.lower()
                                ):
                                    candidates.insert(0, "DejaVuSans-Oblique.ttf")
                            for cand in candidates:
                                cand_path = os.path.join(base_dir, cand)
                                if os.path.exists(cand_path):
                                    try:
                                        name = f"GreekFontInspection{label}"
                                        pdfmetrics.registerFont(TTFont(name, cand_path))
                                        registered_variants[label] = name
                                        logging.debug(
                                            "Registered inspection font variant %s "
                                            "-> %s",
                                            label,
                                            cand_path,
                                        )
                                        return True
                                    except Exception:
                                        logging.exception(
                                            (
                                                "Failed to register inspection font "
                                                "variant %s at %s"
                                            ),
                                            label,
                                            cand_path,
                                        )
                            return False

                        _try_variant("-Bold", "Bold")
                        _try_variant("-Italic", "Italic")

                        try:
                            fam_kwargs = {"normal": "GreekFontInspection"}
                            if "Bold" in registered_variants:
                                fam_kwargs["bold"] = registered_variants["Bold"]
                            if "Italic" in registered_variants:
                                fam_kwargs["italic"] = registered_variants["Italic"]
                            registerFontFamily("GreekFontInspection", **fam_kwargs)
                        except Exception:
                            logging.debug(
                                "Could not register inspection font family variants; "
                                "proceeding with base font"
                            )

                        self.greek_font = "GreekFontInspection"
                        return
                    except Exception:
                        continue

            self.greek_font = "Helvetica"
        except Exception:
            self.greek_font = "Helvetica"

    def normalize_text(self, text):
        if text is None:
            return ""
        if isinstance(text, (int, float)):
            text = str(text)
        return unicodedata.normalize("NFC", text)

    def normalize_table_data(self, data):
        normalized = []
        for row in data:
            normalized_row = []
            for cell in row:
                if isinstance(cell, str):
                    normalized_row.append(self.normalize_text(cell))
                else:
                    normalized_row.append(cell)
            normalized.append(normalized_row)
        return normalized

    def _get_logo_flowable(self, max_width=None, max_height=None):
        """Return a scaled logo Image flowable if available.

        Use `mm` units if reportlab is present; otherwise fall back to pixels.
        """
        # Lazy-resolve mm to avoid NameError when reportlab is not installed
        try:
            from reportlab.lib.units import mm as _mm
        except Exception:
            _mm = None
        if max_width is None:
            max_width = 28 * _mm if _mm is not None else 28
        if max_height is None:
            max_height = 20 * _mm if _mm is not None else 20
        logo_path = os.path.join(os.path.dirname(__file__), "logo_deddie.png")
        fallback_path = os.path.join(os.path.dirname(__file__), "deddie_logo.png")
        if not os.path.exists(logo_path) and not os.path.exists(fallback_path):
            return None

        if not os.path.exists(logo_path):
            logo_path = fallback_path
        try:
            reader = ImageReader(logo_path)
            img_width, img_height = reader.getSize()
            scale = min(max_width / img_width, max_height / img_height)
            return Image(logo_path, width=img_width * scale, height=img_height * scale)
        except Exception:
            return None

    def generate_inspection_report(self, inspection_id, output_path=None):
        c = self.conn.cursor()
        c.execute(
            """
            SELECT substation_name, inspection_date, data_json
            FROM inspections
            WHERE id = ?
        """,
            (inspection_id,),
        )
        row = c.fetchone()

        if not row:
            raise ValueError(f"Inspection record {inspection_id} not found")

        substation_name, inspection_date, data_json = row

        try:
            data = json.loads(data_json or "{}")
        except Exception:
            data = {}

        fields = data.get("fields", [])

        if output_path is None:
            reports_dir = os.path.join(os.path.dirname(__file__), "reports")
            os.makedirs(reports_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = (
                (substation_name or "Inspection").replace("/", "-").replace("\\", "-")
            )
            output_path = os.path.join(
                reports_dir, f"Inspection_{safe_name}_{timestamp}.pdf"
            )

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
        )

        styles = getSampleStyleSheet()
        story = []

        title_style = ParagraphStyle(
            "InspectionTitle",
            parent=styles["Heading1"],
            fontSize=16,
            textColor=colors.HexColor("#000080"),
            spaceAfter=10,
            alignment=TA_CENTER,
            fontName=self.greek_font,
        )

        subtitle_style = ParagraphStyle(
            "InspectionSubtitle",
            parent=styles["Normal"],
            fontSize=12,
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName=self.greek_font,
        )

        title = Paragraph(
            self.normalize_text("ΑΝΑΦΟΡΑ ΕΠΙΘΕΩΡΗΣΗΣ ΥΠΟΣΤΑΘΜΟΥ"), title_style
        )

        subtitle_text = (
            f"Υποσταθμός: {substation_name or '-'} | Ημερομηνία: {inspection_date}"
        )
        subtitle = Paragraph(self.normalize_text(subtitle_text), subtitle_style)

        logo = self._get_logo_flowable(max_width=28 * mm, max_height=20 * mm)
        if logo:
            logo.hAlign = "RIGHT"
            header_table = Table(
                [[[title, subtitle], logo]], colWidths=[140 * mm, 40 * mm]
            )
            header_table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.append(header_table)
        else:
            story.append(title)
            story.append(subtitle)

        story.append(Spacer(1, 10))

        if not fields:
            story.append(
                Paragraph(
                    self.normalize_text("Δεν υπάρχουν διαθέσιμα δεδομένα επιθεώρησης."),
                    styles["Normal"],
                )
            )
        else:
            cell_style = ParagraphStyle(
                "InspectionCell",
                parent=styles["Normal"],
                fontSize=9,
                leading=11,
                fontName=self.greek_font,
            )
            header_style = ParagraphStyle(
                "InspectionHeader",
                parent=styles["Normal"],
                fontSize=9,
                leading=11,
                fontName=self.greek_font,
                textColor=colors.black,
            )
            section_title_style = ParagraphStyle(
                "InspectionSectionTitle",
                parent=styles["Heading3"],
                fontSize=11,
                leading=13,
                fontName=self.greek_font,
                textColor=colors.HexColor("#000080"),
                spaceBefore=8,
                spaceAfter=4,
            )

            def get_fallback_sections():
                # Build fallback using centralized inspection rows to avoid duplication
                rows = S.get("MESSAGES", {}).get("INSPECTION_ROWS", [])
                sections = [
                    "Υποσταθμός",
                    "Αρ. Δελτίου",
                    "Μήνας",
                    "Ονομ. Επιθεωρητή",
                    "Περιοχή",
                    "Ημέρα",
                    "Έτος",
                    "Ημερομηνία",
                ]

                # Section 1
                sections.extend(
                    [
                        {"type": "section", "title": "1. Έλεγχος Χώρων ΥΣ"},
                        "Παρατηρήσεις (1. Έλεγχος Χώρων ΥΣ)",
                    ]
                )
                sections.extend(rows[0:4])

                # Section 2
                sections.extend(
                    [
                        {
                            "type": "section",
                            "title": "2. Μ/Σ 150/20kV & Διακόπτες 150kV & 20kV",
                        },
                        "Παρατηρήσεις (2. Μ/Σ 150/20kV & Διακόπτες 150kV & 20kV)",
                    ]
                )
                sections.extend(rows[4:12])

                # Section 3a
                sections.extend(
                    [
                        {"type": "section", "title": "3α. Υπαίθριες πύλες 20 kV"},
                        "Παρατηρήσεις (3α. Υπαίθριες πύλες 20 kV)",
                    ]
                )
                if len(rows) > 12:
                    sections.append(rows[12])

                # Section 3b
                sections.extend(
                    [
                        {"type": "section", "title": "3β. Πίνακες 20 kV"},
                        "Παρατηρήσεις (3β. Πίνακες 20 kV)",
                    ]
                )
                sections.extend(rows[13:15])

                # Section 4
                sections.extend(
                    [
                        {"type": "section", "title": "4. Κτίριο χειρισμών & Τ.Α.Σ."},
                        "Παρατηρήσεις (4. Κτίριο χειρισμών & Τ.Α.Σ.)",
                    ]
                )
                sections.extend(rows[15:18])

                # Section 5
                sections.extend(
                    [
                        {"type": "section", "title": "5. Αποζεύκτες Γραμμών"},
                        "Παρατηρήσεις (5. Αποζεύκτες Γραμμών)",
                    ]
                )
                if len(rows) > 18:
                    sections.append(rows[18])

                # Section 6
                sections.extend(
                    [
                        {"type": "section", "title": "6. PC ΧΕΙΡΙΣΜΩΝ"},
                        "Παρατηρήσεις (6. PC ΧΕΙΡΙΣΜΩΝ)",
                    ]
                )
                sections.extend(rows[19:21])

                # Section 7
                sections.extend(
                    [
                        {"type": "section", "title": "7. Απόψεις"},
                        "Απόψεις - Προτάσεις",
                    ]
                )

                return sections

            def build_sections():
                fallback = get_fallback_sections()
                sections = []
                current_title = "Στοιχεία Επιθεώρησης"
                current_labels = []
                for item in fallback:
                    if isinstance(item, dict) and item.get("type") == "section":
                        if current_labels:
                            sections.append((current_title, list(current_labels)))
                        current_title = item.get("title", "")
                        current_labels = []
                    elif isinstance(item, str):
                        current_labels.append(item)
                if current_labels:
                    sections.append((current_title, list(current_labels)))
                label_to_section = {}
                for title, labels in sections:
                    for label in labels:
                        label_to_section[label] = title
                return sections, label_to_section

            sections, label_to_section = build_sections()
            section_items = {title: [] for title, _labels in sections}
            other_items = []

            for field in fields:
                if not isinstance(field, dict):
                    continue
                label = field.get("label", "")
                if label in label_to_section:
                    section_items[label_to_section[label]].append(field)
                else:
                    other_items.append(field)

            def add_section_table(title, items):
                story.append(Paragraph(self.normalize_text(title), section_title_style))
                table_data = [
                    [
                        Paragraph(self.normalize_text("Πεδίο"), header_style),
                        Paragraph(self.normalize_text("Τιμή"), header_style),
                    ]
                ]
                for field in items:
                    label = field.get("label", "") if isinstance(field, dict) else ""
                    value = field.get("value", "") if isinstance(field, dict) else ""
                    label_text = self.normalize_text(str(label))
                    value_text = self.normalize_text(str(value)).replace("\n", "<br/>")
                    table_data.append(
                        [
                            Paragraph(label_text, cell_style),
                            Paragraph(value_text, cell_style),
                        ]
                    )
                table = Table(table_data, colWidths=[55 * mm, 125 * mm])
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9e2f3")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                            ("TOPPADDING", (0, 0), (-1, -1), 3),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ]
                    )
                )
                story.append(table)

            for title, _labels in sections:
                items = section_items.get(title) or []
                if items:
                    add_section_table(title, items)

            if other_items:
                add_section_table("Λοιπά", other_items)

        story.append(Spacer(1, 12))
        footer_style = ParagraphStyle(
            "InspectionFooter",
            parent=styles["Normal"],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER,
            fontName=self.greek_font,
        )
        footer = Paragraph(
            self.normalize_text(
                f"Δημιουργήθηκε: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            ),
            footer_style,
        )
        story.append(footer)

        temp_path = _temp_pdf_path(output_path)
        doc = SimpleDocTemplate(
            _fs_path(temp_path),
            pagesize=A4,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
        )
        doc.build(story)
        async_flag = bool(get_app_setting("pdf_normalize_async", False))
        try:
            file_size_kb = os.path.getsize(_fs_path(temp_path)) // 1024
        except Exception:
            file_size_kb = 0
        threshold_kb = int(
            get_app_setting("pdf_normalize_size_threshold_kb", 1024) or 1024
        )
        if async_flag and file_size_kb >= threshold_kb:
            try:
                os.replace(_fs_path(temp_path), _fs_path(output_path))
            except Exception:
                try:
                    os.rename(_fs_path(temp_path), _fs_path(output_path))
                except Exception:
                    pass
            try:
                _pdf_norm_queue.put(_fs_path(output_path))
            except Exception:
                pass
        else:
            try:
                _normalize_pdf_file(temp_path)
            except Exception:
                pass
            try:
                os.replace(_fs_path(temp_path), _fs_path(output_path))
            except Exception:
                try:
                    os.rename(_fs_path(temp_path), _fs_path(output_path))
                except Exception:
                    pass
        return output_path


def generate_inspection_report(conn, inspection_id, output_path=None):
    """Convenience function to generate an inspection report PDF."""
    generator = InspectionReportGenerator(conn)
    return generator.generate_inspection_report(inspection_id, output_path)


class SF6LeakReportGenerator:
    """Generate annual SF6 leakage reports."""

    def __init__(self, conn):
        self.conn = conn
        self.greek_font = "Helvetica"
        self.setup_fonts()

    def setup_fonts(self):
        """Setup fonts for Greek text support."""
        try:
            import platform

            system = platform.system()
            font_paths = []
            if system == "Windows":
                font_paths = [
                    os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf"),
                    "C:\\Windows\\Fonts\\DejaVuSans.ttf",
                    "C:\\Windows\\Fonts\\arial.ttf",
                ]
            elif system == "Darwin":
                font_paths = [
                    "/Library/Fonts/Arial Unicode.ttf",
                    "/Library/Fonts/Arial.ttf",
                ]
            else:
                font_paths = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                ]

            for font_path in font_paths:
                if os.path.exists(font_path):
                    pdfmetrics.registerFont(TTFont("GreekFont", font_path))
                    registerFontFamily(
                        "GreekFont", normal="GreekFont", bold="GreekFont"
                    )
                    self.greek_font = "GreekFont"
                    return
        except Exception:
            self.greek_font = "Helvetica"

    def _normalize_text(self, text):
        if text is None:
            return ""
        if isinstance(text, (int, float)):
            text = str(text)
        return unicodedata.normalize("NFC", str(text))

    def generate_report(self, year, output_path=None):
        c = self.conn.cursor()
        year_prefix = f"{year}%"

        c.execute(
            """
            SELECT m.date_time, s.name, e.name, me.sf6_leakage_kg
            FROM maintenance_elements me
            JOIN maintenance m ON me.maintenance_id = m.id
            JOIN elements e ON me.element_id = e.id
            JOIN substations s ON m.substation_id = s.id
            WHERE e.breaker_category = 'SF6'
              AND m.date_time LIKE ?
                            AND me.sf6_leakage_kg IS NOT NULL
                            AND me.sf6_leakage_kg > 0
            ORDER BY m.date_time ASC
            """,
            (year_prefix,),
        )
        rows = c.fetchall()

        total_leakage = sum([r[3] or 0 for r in rows])

        c.execute(f"""
            SELECT SUM(COALESCE(em.sf6_capacity_kg, 0))
            FROM elements e
            LEFT JOIN element_models em ON e.element_model_id = em.id
            WHERE e.operating_status = 'Ενεργή'
              AND e.breaker_category = 'SF6'
              AND e.element_type IN ('{ELEM_BREAKER_YT}', '{ELEM_BREAKER_MT}')
            """)
        installed_sf6 = c.fetchone()[0] or 0.0
        percentage = (total_leakage / installed_sf6 * 100) if installed_sf6 else 0.0

        if output_path is None:
            reports_dir = os.path.join(os.path.dirname(__file__), "reports")
            os.makedirs(reports_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(
                reports_dir, f"SF6_Leakages_{year}_{timestamp}.pdf"
            )

        doc = SimpleDocTemplate(output_path, pagesize=A4)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "SF6Title",
            parent=styles["Heading1"],
            fontName=self.greek_font,
            alignment=TA_CENTER,
            fontSize=16,
            spaceAfter=12,
        )
        normal_style = ParagraphStyle(
            "SF6Normal",
            parent=styles["Normal"],
            fontName=self.greek_font,
            fontSize=11,
            spaceAfter=6,
        )

        story = [
            Paragraph(
                self._normalize_text(f"Αναφορά Διαρροών SF6 - {year}"), title_style
            ),
            Paragraph(
                self._normalize_text(f"Σύνολο διαρροών: {total_leakage:.2f} kg"),
                normal_style,
            ),
            Paragraph(
                self._normalize_text(
                    f"Εγκατεστημένο SF6 (ενεργά): {installed_sf6:.2f} kg"
                ),
                normal_style,
            ),
            Paragraph(
                self._normalize_text(f"Ποσοστό διαρροών: {percentage:.2f}%"),
                normal_style,
            ),
            Spacer(1, 12),
        ]

        table_data = [
            [
                self._normalize_text("Ημερομηνία"),
                self._normalize_text("Υποσταθμός"),
                self._normalize_text("Στοιχείο"),
                self._normalize_text("Διαρροή (kg)"),
            ]
        ]

        for date_time, sub_name, elem_name, leakage in rows:
            table_data.append(
                [
                    self._normalize_text(date_time or "-"),
                    self._normalize_text(sub_name or "-"),
                    self._normalize_text(elem_name or "-"),
                    self._normalize_text(
                        f"{leakage:.2f}" if leakage is not None else "-"
                    ),
                ]
            )

        table = Table(table_data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, -1), self.greek_font),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )

        story.append(table)
        temp_path = _temp_pdf_path(output_path)
        doc = SimpleDocTemplate(_fs_path(temp_path), pagesize=A4)
        doc.build(story)
        async_flag = bool(get_app_setting("pdf_normalize_async", False))
        try:
            file_size_kb = os.path.getsize(_fs_path(temp_path)) // 1024
        except Exception:
            file_size_kb = 0
        threshold_kb = int(
            get_app_setting("pdf_normalize_size_threshold_kb", 1024) or 1024
        )
        if async_flag and file_size_kb >= threshold_kb:
            try:
                os.replace(_fs_path(temp_path), _fs_path(output_path))
            except Exception:
                try:
                    os.rename(_fs_path(temp_path), _fs_path(output_path))
                except Exception:
                    pass
            try:
                _pdf_norm_queue.put(_fs_path(output_path))
            except Exception:
                pass
        else:
            try:
                _normalize_pdf_file(temp_path)
            except Exception:
                pass
            try:
                os.replace(_fs_path(temp_path), _fs_path(output_path))
            except Exception:
                try:
                    os.rename(_fs_path(temp_path), _fs_path(output_path))
                except Exception:
                    pass
        return output_path


def generate_sf6_leak_report(conn, year, output_path=None):
    """Convenience function to generate SF6 leak report PDF."""
    generator = SF6LeakReportGenerator(conn)
    return generator.generate_report(year, output_path)
