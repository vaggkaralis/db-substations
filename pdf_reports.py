"""
PDF Report Generation for Circuit Breaker Maintenance
Generates maintenance reports matching the official templates
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import os
from datetime import datetime


class MaintenanceReportGenerator:
    """Generate maintenance reports for circuit breakers"""
    
    def __init__(self, conn):
        self.conn = conn
        self.setup_fonts()
    
    def setup_fonts(self):
        """Setup fonts for Greek text support"""
        # Try to use system fonts that support Greek
        # ReportLab will fall back to default if not found
        pass
    
    def get_breaker_category_display(self, breaker_category):
        """Get display name for breaker category"""
        category_map = {
            'SF6': 'ΑΕΡΙΟΥ (SF6)',
            'Oil': 'ΛΑΔΙΟΥ',
            'Vacuum': 'ΚΕΝΟΥ'
        }
        return category_map.get(breaker_category, breaker_category)
    
    def generate_maintenance_report(self, maintenance_id, element_id, output_path=None):
        """
        Generate PDF maintenance report for a specific circuit breaker
        
        Args:
            maintenance_id: ID of the maintenance record
            element_id: ID of the element (circuit breaker)
            output_path: Optional output path for the PDF. If None, generates in 'reports' folder
        
        Returns:
            Path to the generated PDF file
        """
        c = self.conn.cursor()
        
        # Get maintenance record
        c.execute("""
            SELECT m.id, m.substation_id, m.date_time, m.overall_comments, m.maintenance_type,
                   s.name as substation_name, s.location, s.division
            FROM maintenance m
            JOIN substations s ON m.substation_id = s.id
            WHERE m.id = ?
        """, (maintenance_id,))
        maintenance = c.fetchone()
        
        if not maintenance:
            raise ValueError(f"Maintenance record {maintenance_id} not found")
        
        maint_id, sub_id, date_time, overall_comments, maint_type, sub_name, sub_location, division = maintenance
        
        # Get element details
        c.execute("""
            SELECT e.id, e.element_type, e.name, e.serial_number, e.manufacturer, e.model,
                   e.breaker_category, e.voltage_level, e.bar, e.manufacture_year,
                   em.manufacturer as model_manufacturer, em.model_name
            FROM elements e
            LEFT JOIN element_models em ON e.element_model_id = em.id
            WHERE e.id = ?
        """, (element_id,))
        element = c.fetchone()
        
        if not element:
            raise ValueError(f"Element {element_id} not found")
        
        elem_id, elem_type, elem_name, serial_num, manufacturer, model, breaker_category, \
        voltage_level, bar, manufacture_year, model_manufacturer, model_name = element
        
        # Get maintenance measurements for this element
        c.execute("""
            SELECT element_comments,
                   insulation_closed_fa_ground, insulation_closed_fa_unit,
                   insulation_closed_fb_ground, insulation_closed_fb_unit,
                   insulation_closed_fc_ground, insulation_closed_fc_unit,
                   insulation_open_fa_fa, insulation_open_fa_unit,
                   insulation_open_fb_fb, insulation_open_fb_unit,
                   insulation_open_fc_fc, insulation_open_fc_unit,
                   contact_resistance_fa_fa, contact_resistance_fb_fb, contact_resistance_fc_fc
            FROM maintenance_elements
            WHERE maintenance_id = ? AND element_id = ?
        """, (maintenance_id, element_id))
        measurements = c.fetchone()
        
        if not measurements:
            raise ValueError(f"No maintenance data found for element {element_id} in maintenance {maintenance_id}")
        
        # Create output directory if needed
        if output_path is None:
            reports_dir = os.path.join(os.path.dirname(__file__), 'reports')
            os.makedirs(reports_dir, exist_ok=True)
            
            # Generate filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_name = elem_name.replace('/', '-').replace('\\', '-')
            output_path = os.path.join(reports_dir, f'Maintenance_{safe_name}_{timestamp}.pdf')
        
        # Generate the PDF based on breaker category
        if breaker_category == 'SF6':
            self._generate_sf6_report(output_path, maintenance, element, measurements)
        elif breaker_category == 'Oil':
            self._generate_oil_report(output_path, maintenance, element, measurements)
        elif breaker_category == 'Vacuum':
            self._generate_vacuum_report(output_path, maintenance, element, measurements)
        else:
            raise ValueError(f"Unknown breaker category: {breaker_category}")
        
        return output_path
    
    def _create_header(self, story, breaker_type, substation_name):
        """Create report header"""
        styles = getSampleStyleSheet()
        
        # Title style
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#000080'),
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        # Add header
        title = Paragraph(f'ΔΕΛΤΙΟ ΣΥΝΤΗΡΗΣΗΣ ΔΙΑΚΟΠΤΗ {breaker_type}', title_style)
        story.append(title)
        
        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Normal'],
            fontSize=14,
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        subtitle = Paragraph(f'Υποσταθμός: {substation_name}', subtitle_style)
        story.append(subtitle)
        story.append(Spacer(1, 12))
    
    def _create_info_table(self, element_data, maintenance_data):
        """Create general information table"""
        maint_id, sub_id, date_time, overall_comments, maint_type, sub_name, sub_location, division = maintenance_data
        elem_id, elem_type, elem_name, serial_num, manufacturer, model, breaker_category, \
        voltage_level, bar, manufacture_year, model_manufacturer, model_name = element_data
        
        # Use model data if available, otherwise element data
        display_manufacturer = model_manufacturer if model_manufacturer else manufacturer
        display_model = model_name if model_name else model
        
        data = [
            ['ΣΤΟΙΧΕΙΑ ΔΙΑΚΟΠΤΗ', ''],
            ['Όνομα:', elem_name or '-'],
            ['Αριθμός Σειράς (S/N):', serial_num or '-'],
            ['Κατασκευαστής:', display_manufacturer or '-'],
            ['Μοντέλο:', display_model or '-'],
            ['Τάση (kV):', voltage_level or '-'],
            ['Ζυγός:', bar or '-'],
            ['Έτος Κατασκευής:', manufacture_year or '-'],
            ['', ''],
            ['ΣΤΟΙΧΕΙΑ ΣΥΝΤΗΡΗΣΗΣ', ''],
            ['Ημερομηνία:', date_time or '-'],
            ['Τύπος Συντήρησης:', maint_type or '-'],
            ['Τομέας:', division or '-'],
        ]
        
        table = Table(data, colWidths=[80*mm, 100*mm])
        table.setStyle(TableStyle([
            # Header rows
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
            ('BACKGROUND', (0, 9), (-1, 9), colors.HexColor('#4472C4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('TEXTCOLOR', (0, 9), (-1, 9), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 9), (-1, 9), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('FONTSIZE', (0, 9), (-1, 9), 12),
            
            # All cells
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        
        return table
    
    def _create_measurements_table(self, measurements):
        """Create measurements table for insulation and contact resistance"""
        elem_comments, ins_closed_fa, ins_closed_fa_unit, ins_closed_fb, ins_closed_fb_unit, \
        ins_closed_fc, ins_closed_fc_unit, ins_open_fa, ins_open_fa_unit, ins_open_fb, \
        ins_open_fb_unit, ins_open_fc, ins_open_fc_unit, cont_fa, cont_fb, cont_fc = measurements
        
        # Helper to format value with unit
        def format_value(value, unit):
            if value is None or value == '':
                return '-'
            return f"{value} {unit}"
        
        data = [
            ['ΜΕΤΡΗΣΕΙΣ ΜΟΝΩΣΕΩΝ', '', '', ''],
            ['Θέση', 'Φάση Α', 'Φάση Β', 'Φάση Γ'],
            ['Κλειστή Θέση (προς γη)', 
             format_value(ins_closed_fa, ins_closed_fa_unit),
             format_value(ins_closed_fb, ins_closed_fb_unit),
             format_value(ins_closed_fc, ins_closed_fc_unit)],
            ['Ανοιχτή Θέση (μεταξύ επαφών)',
             format_value(ins_open_fa, ins_open_fa_unit),
             format_value(ins_open_fb, ins_open_fb_unit),
             format_value(ins_open_fc, ins_open_fc_unit)],
            ['', '', '', ''],
            ['ΜΕΤΡΗΣΕΙΣ ΑΝΤΙΣΤΑΣΗΣ ΕΠΑΦΩΝ (μΩ)', '', '', ''],
            ['', 'Φάση Α', 'Φάση Β', 'Φάση Γ'],
            ['Αντίσταση Επαφών',
             format_value(cont_fa, 'μΩ') if cont_fa else '-',
             format_value(cont_fb, 'μΩ') if cont_fb else '-',
             format_value(cont_fc, 'μΩ') if cont_fc else '-'],
        ]
        
        table = Table(data, colWidths=[60*mm, 40*mm, 40*mm, 40*mm])
        table.setStyle(TableStyle([
            # Headers
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#70AD47')),
            ('BACKGROUND', (0, 5), (-1, 5), colors.HexColor('#FFC000')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('TEXTCOLOR', (0, 5), (-1, 5), colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 5), (-1, 5), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('FONTSIZE', (0, 5), (-1, 5), 11),
            ('SPAN', (0, 0), (-1, 0)),
            ('SPAN', (0, 5), (-1, 5)),
            
            # Subheaders
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#A9D08E')),
            ('BACKGROUND', (0, 6), (-1, 6), colors.HexColor('#FFE699')),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
            ('FONTNAME', (0, 6), (-1, 6), 'Helvetica-Bold'),
            
            # All cells
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        
        return table
    
    def _create_comments_section(self, overall_comments, element_comments):
        """Create comments section"""
        styles = getSampleStyleSheet()
        
        comment_style = ParagraphStyle(
            'CommentStyle',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=10,
            alignment=TA_LEFT
        )
        
        story_items = []
        
        if element_comments:
            story_items.append(Spacer(1, 12))
            story_items.append(Paragraph('<b>ΣΧΟΛΙΑ ΣΤΟΙΧΕΙΟΥ:</b>', comment_style))
            story_items.append(Paragraph(element_comments, comment_style))
        
        if overall_comments:
            story_items.append(Spacer(1, 12))
            story_items.append(Paragraph('<b>ΓΕΝΙΚΑ ΣΧΟΛΙΑ ΣΥΝΤΗΡΗΣΗΣ:</b>', comment_style))
            story_items.append(Paragraph(overall_comments, comment_style))
        
        return story_items
    
    def _generate_sf6_report(self, output_path, maintenance_data, element_data, measurements):
        """Generate SF6 (Gas) circuit breaker maintenance report"""
        doc = SimpleDocTemplate(output_path, pagesize=A4,
                                topMargin=20*mm, bottomMargin=20*mm,
                                leftMargin=15*mm, rightMargin=15*mm)
        
        story = []
        
        # Header
        self._create_header(story, 'ΑΕΡΙΟΥ (SF6)', maintenance_data[5])  # substation_name
        
        # Information table
        info_table = self._create_info_table(element_data, maintenance_data)
        story.append(info_table)
        story.append(Spacer(1, 15))
        
        # Measurements table
        measurements_table = self._create_measurements_table(measurements)
        story.append(measurements_table)
        
        # Comments
        comments = self._create_comments_section(maintenance_data[3], measurements[0])
        story.extend(comments)
        
        # Footer
        story.append(Spacer(1, 20))
        styles = getSampleStyleSheet()
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER
        )
        footer = Paragraph(f'Δημιουργήθηκε: {datetime.now().strftime("%d/%m/%Y %H:%M")}', footer_style)
        story.append(footer)
        
        # Build PDF
        doc.build(story)
    
    def _generate_oil_report(self, output_path, maintenance_data, element_data, measurements):
        """Generate Oil circuit breaker maintenance report"""
        doc = SimpleDocTemplate(output_path, pagesize=A4,
                                topMargin=20*mm, bottomMargin=20*mm,
                                leftMargin=15*mm, rightMargin=15*mm)
        
        story = []
        
        # Header
        self._create_header(story, 'ΛΑΔΙΟΥ', maintenance_data[5])  # substation_name
        
        # Information table
        info_table = self._create_info_table(element_data, maintenance_data)
        story.append(info_table)
        story.append(Spacer(1, 15))
        
        # Measurements table
        measurements_table = self._create_measurements_table(measurements)
        story.append(measurements_table)
        
        # Comments
        comments = self._create_comments_section(maintenance_data[3], measurements[0])
        story.extend(comments)
        
        # Footer
        story.append(Spacer(1, 20))
        styles = getSampleStyleSheet()
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER
        )
        footer = Paragraph(f'Δημιουργήθηκε: {datetime.now().strftime("%d/%m/%Y %H:%M")}', footer_style)
        story.append(footer)
        
        # Build PDF
        doc.build(story)
    
    def _generate_vacuum_report(self, output_path, maintenance_data, element_data, measurements):
        """Generate Vacuum circuit breaker maintenance report"""
        doc = SimpleDocTemplate(output_path, pagesize=A4,
                                topMargin=20*mm, bottomMargin=20*mm,
                                leftMargin=15*mm, rightMargin=15*mm)
        
        story = []
        
        # Header
        self._create_header(story, 'ΚΕΝΟΥ', maintenance_data[5])  # substation_name
        
        # Information table
        info_table = self._create_info_table(element_data, maintenance_data)
        story.append(info_table)
        story.append(Spacer(1, 15))
        
        # Measurements table
        measurements_table = self._create_measurements_table(measurements)
        story.append(measurements_table)
        
        # Comments
        comments = self._create_comments_section(maintenance_data[3], measurements[0])
        story.extend(comments)
        
        # Footer
        story.append(Spacer(1, 20))
        styles = getSampleStyleSheet()
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER
        )
        footer = Paragraph(f'Δημιουργήθηκε: {datetime.now().strftime("%d/%m/%Y %H:%M")}', footer_style)
        story.append(footer)
        
        # Build PDF
        doc.build(story)


def generate_maintenance_report(conn, maintenance_id, element_id, output_path=None):
    """
    Convenience function to generate a maintenance report
    
    Args:
        conn: Database connection
        maintenance_id: ID of the maintenance record
        element_id: ID of the circuit breaker element
        output_path: Optional output path for the PDF
    
    Returns:
        Path to the generated PDF file
    """
    generator = MaintenanceReportGenerator(conn)
    return generator.generate_maintenance_report(maintenance_id, element_id, output_path)
