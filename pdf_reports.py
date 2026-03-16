"""
PDF Report Generation for Circuit Breaker Maintenance
Generates maintenance reports matching the official templates
"""

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
    from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate,
                                    Spacer, Table, TableStyle)

    _HAS_REPORTLAB = True
except Exception:
    # Allow importing this module in test environments without reportlab
    _HAS_REPORTLAB = False
import json
import logging
import os
import unicodedata
from datetime import datetime

from strings_proxy import STRINGS as S


def _fs_path(path: str) -> str:
    abs_path = os.path.abspath(path)
    if os.name != "nt" or abs_path.startswith("\\\\?\\"):
        return abs_path
    if abs_path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + abs_path[2:]
    return "\\\\?\\" + abs_path

# Canonical breaker element names
ELEM_BREAKER_YT = S.get("MESSAGES", {}).get("ELEMENT_BREAKER_YT", "Διακόπτης ΥΤ")
ELEM_BREAKER_MT = S.get("MESSAGES", {}).get("ELEMENT_BREAKER_MT", "Διακόπτης ΜΤ")


class MaintenanceReportGenerator:
    """Generate maintenance reports for circuit breakers"""

    def __init__(self, conn):
        self.conn = conn
        logging.info("%s", "\n" + "=" * 80)
        logging.info("PDF REPORT GENERATOR INITIALIZATION")
        logging.info("%s", "=" * 80)
        self.setup_fonts()
        logging.info("%s", "=" * 80 + "\n")

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
                        # Register font WITHOUT asciiReadable to preserve Unicode characters
                        pdfmetrics.registerFont(TTFont("GreekFont", font_path))

                        # Also register font family for bold/italic support
                        try:
                            registerFontFamily("GreekFont", normal="GreekFont")
                        except Exception:
                            pass

                        self.greek_font = "GreekFont"
                        font_name = (
                            "DejaVu Sans (bundled)"
                            if font_path == bundled_font
                            else os.path.basename(font_path)
                        )
                        logging.info("Using font for Greek text: %s", font_name)
                        logging.info("   Path: %s", font_path)
                        return
                    except Exception:
                        logging.exception('Failed to register %s', font_path)
                        continue

            # If no font found, use Helvetica (limited Greek support)
            logging.warning(
                "No suitable Greek font found, using Helvetica (limited support)"
            )
            self.greek_font = "Helvetica"

        except Exception:
            # Fallback to Helvetica
            logging.exception('Error setting up fonts')
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
            SELECT m.id, m.substation_id, m.date_time, m.overall_comments, m.maintenance_type, m.user_name,
                   s.name as substation_name, s.location, s.division
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
                 SELECT e.id, e.element_type, e.name, e.serial_number, e.manufacturer, e.model,
                     e.breaker_category, e.voltage_level, e.gate, e.manufacture_year,
                   em.manufacturer as model_manufacturer, em.model_name
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
            SELECT element_comments,
                   insulation_closed_fa_ground, insulation_closed_fa_unit,
                   insulation_closed_fb_ground, insulation_closed_fb_unit,
                   insulation_closed_fc_ground, insulation_closed_fc_unit,
                   insulation_open_fa_fa, insulation_open_fa_unit,
                   insulation_open_fb_fb, insulation_open_fb_unit,
                   insulation_open_fc_fc, insulation_open_fc_unit,
                   contact_resistance_fa_fa, contact_resistance_fb_fb, contact_resistance_fc_fc,
                   operations_count,
                   sf6_n2_fa, h2o_fa, so2_fa, sf6_n2_fb, h2o_fb, so2_fb, sf6_n2_fc, h2o_fc, so2_fc,
                   vidar_fa, vidar_fb, vidar_fc
            FROM maintenance_elements
            WHERE maintenance_id = ? AND element_id = ?
        """,
            (maintenance_id, element_id),
        )
        measurements = c.fetchone()

        if not measurements:
            raise ValueError(
                f"No maintenance data found for element {element_id} in maintenance {maintenance_id}"
            )

        # Ensure parent directory exists (folder should be created by caller)
        parent_dir = os.path.dirname(output_path)
        if not os.path.exists(_fs_path(parent_dir)):
            os.makedirs(_fs_path(parent_dir), exist_ok=True)

        output_write_path = _fs_path(output_path)

        # Generate the PDF based on breaker category
        category_lower = breaker_category.lower()
        if "sf6" in category_lower:
            self._generate_sf6_report(output_write_path, maintenance, element, measurements)
        elif category_lower in ["oil", "πτωχού ελαίου", "ελαίου"]:
            self._generate_oil_report(output_write_path, maintenance, element, measurements)
        elif category_lower in ["vacuum", "κενού"]:
            self._generate_vacuum_report(output_write_path, maintenance, element, measurements)
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
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName=self.greek_font,
        )

        title_text = S["MESSAGES"].get("MAINTENANCE_REPORT_TITLE", "ΔΕΛΤΙΟ ΣΥΝΤΗΡΗΣΗΣ ΔΙΑΚΟΠΤΗ {breaker}")
        subtitle_text = S["MESSAGES"].get("MAINTENANCE_REPORT_SUBTITLE", "Υποσταθμός: {substation}")
        title = Paragraph(
            self.normalize_text(title_text.format(breaker=breaker_type)),
            title_style,
        )
        subtitle = Paragraph(
            self.normalize_text(subtitle_text.format(substation=substation_name)), subtitle_style
        )

        # Prefer to let _get_logo_flowable decide unit sizes so module can be
        # imported even when reportlab (and `mm`) is not available.
        logo = self._get_logo_flowable()
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
            [S["MESSAGES"].get("SERIAL_NUMBER_LABEL", "Αριθμός Σειράς (S/N):"), serial_num or "-"],
            [S["MESSAGES"].get("MANUFACTURER_LABEL", "Κατασκευαστής:"), display_manufacturer or "-"],
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
        if breaker_category.lower() in ["vacuum", "κενού"] and (vidar_fa or vidar_fb or vidar_fc):
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
        story.append(Spacer(1, 20))
        styles = getSampleStyleSheet()
        footer_style = ParagraphStyle(
            "Footer",
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

        # Build PDF
        doc.build(story)
        # Ensure file is readable by all users (fix Acrobat Reader access denied)
        try:
            os.chmod(output_path, 0o666)
        except Exception:
            pass

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

        # Footer
        story.append(Spacer(1, 20))
        styles = getSampleStyleSheet()
        footer_style = ParagraphStyle(
            "Footer",
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

        # Build PDF
        doc.build(story)
        # Ensure file is readable by all users (fix Acrobat Reader access denied)
        try:
            os.chmod(output_path, 0o666)
        except Exception:
            pass

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
        story.append(Spacer(1, 20))
        styles = getSampleStyleSheet()
        footer_style = ParagraphStyle(
            "Footer",
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

        # Build PDF
        doc.build(story)
        # Ensure file is readable by all users (fix Acrobat Reader access denied)
        try:
            os.chmod(output_path, 0o666)
        except Exception:
            pass


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
            "output_path is required. Use report_sync.safe_generate_and_store_report() instead."
        )
    
    generator = MaintenanceReportGenerator(conn)
    return generator.generate_maintenance_report(
        maintenance_id, element_id, output_path
    )


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
                        try:
                            registerFontFamily(
                                "GreekFontInspection", normal="GreekFontInspection"
                            )
                        except Exception:
                            pass
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
                sections.extend([
                    {"type": "section", "title": "1. Έλεγχος Χώρων ΥΣ"},
                    "Παρατηρήσεις (1. Έλεγχος Χώρων ΥΣ)",
                ])
                sections.extend(rows[0:4])

                # Section 2
                sections.extend([
                    {"type": "section", "title": "2. Μ/Σ 150/20kV & Διακόπτες 150kV & 20kV"},
                    "Παρατηρήσεις (2. Μ/Σ 150/20kV & Διακόπτες 150kV & 20kV)",
                ])
                sections.extend(rows[4:12])

                # Section 3a
                sections.extend([
                    {"type": "section", "title": "3α. Υπαίθριες πύλες 20 kV"},
                    "Παρατηρήσεις (3α. Υπαίθριες πύλες 20 kV)",
                ])
                if len(rows) > 12:
                    sections.append(rows[12])

                # Section 3b
                sections.extend([
                    {"type": "section", "title": "3β. Πίνακες 20 kV"},
                    "Παρατηρήσεις (3β. Πίνακες 20 kV)",
                ])
                sections.extend(rows[13:15])

                # Section 4
                sections.extend([
                    {"type": "section", "title": "4. Κτίριο χειρισμών & Τ.Α.Σ."},
                    "Παρατηρήσεις (4. Κτίριο χειρισμών & Τ.Α.Σ.)",
                ])
                sections.extend(rows[15:18])

                # Section 5
                sections.extend([
                    {"type": "section", "title": "5. Αποζεύκτες Γραμμών"},
                    "Παρατηρήσεις (5. Αποζεύκτες Γραμμών)",
                ])
                if len(rows) > 18:
                    sections.append(rows[18])

                # Section 6
                sections.extend([
                    {"type": "section", "title": "6. PC ΧΕΙΡΙΣΜΩΝ"},
                    "Παρατηρήσεις (6. PC ΧΕΙΡΙΣΜΩΝ)",
                ])
                sections.extend(rows[19:21])

                # Section 7
                sections.extend([
                    {"type": "section", "title": "7. Απόψεις"},
                    "Απόψεις - Προτάσεις",
                ])

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

        doc.build(story)
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
        doc.build(story)
        return output_path


def generate_sf6_leak_report(conn, year, output_path=None):
    """Convenience function to generate SF6 leak report PDF."""
    generator = SF6LeakReportGenerator(conn)
    return generator.generate_report(year, output_path)
