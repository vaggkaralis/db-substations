import sqlite3
from pathlib import Path

from pdf_reports import MaintenanceReportGenerator


def _create_pdf_schema(conn):
    cur = conn.cursor()
    # Minimal tables and columns referenced by generator
    cur.executescript(
        """
        CREATE TABLE substations (id INTEGER PRIMARY KEY, name TEXT, location TEXT, division TEXT);
        CREATE TABLE element_models (id INTEGER PRIMARY KEY, manufacturer TEXT, model_name TEXT);
        CREATE TABLE elements (id INTEGER PRIMARY KEY, element_type TEXT, name TEXT, serial_number TEXT, manufacturer TEXT, model TEXT, breaker_category TEXT, voltage_level TEXT, gate TEXT, manufacture_year TEXT, element_model_id INTEGER);
        CREATE TABLE maintenance (id INTEGER PRIMARY KEY, substation_id INTEGER, date_time TEXT, overall_comments TEXT, maintenance_type TEXT, user_name TEXT);
        CREATE TABLE maintenance_elements (
            maintenance_id INTEGER,
            element_id INTEGER,
            element_comments TEXT,
            insulation_closed_fa_ground TEXT,
            insulation_closed_fa_unit TEXT,
            insulation_closed_fb_ground TEXT,
            insulation_closed_fb_unit TEXT,
            insulation_closed_fc_ground TEXT,
            insulation_closed_fc_unit TEXT,
            insulation_open_fa_fa TEXT,
            insulation_open_fa_unit TEXT,
            insulation_open_fb_fb TEXT,
            insulation_open_fb_unit TEXT,
            insulation_open_fc_fc TEXT,
            insulation_open_fc_unit TEXT,
            contact_resistance_fa_fa TEXT,
            contact_resistance_fb_fb TEXT,
            contact_resistance_fc_fc TEXT,
            operations_count INTEGER,
            sf6_n2_fa TEXT,
            h2o_fa TEXT,
            so2_fa TEXT,
            sf6_n2_fb TEXT,
            h2o_fb TEXT,
            so2_fb TEXT,
            sf6_n2_fc TEXT,
            h2o_fc TEXT,
            so2_fc TEXT,
            vidar_fa TEXT,
            vidar_fb TEXT,
            vidar_fc TEXT
        );
        """
    )
    conn.commit()


def test_generate_maintenance_report_smoke(tmp_path):
    db_path = tmp_path / "report.db"
    conn = sqlite3.connect(str(db_path))
    _create_pdf_schema(conn)
    cur = conn.cursor()
    # Insert minimal rows
    cur.execute("INSERT INTO substations (id, name, location, division) VALUES (1, 'S1', '', '')")
    cur.execute("INSERT INTO elements (id, element_type, name, breaker_category) VALUES (1, 'type', 'E1', 'SF6')")
    cur.execute("INSERT INTO maintenance (id, substation_id, date_time, overall_comments, maintenance_type, user_name) VALUES (1, 1, '2020-01-01', 'ok', 'type', 'user')")
    cur.execute("INSERT INTO maintenance_elements (maintenance_id, element_id, element_comments) VALUES (1, 1, 'ok')")
    conn.commit()

    gen = MaintenanceReportGenerator(conn)
    # Monkeypatch heavy PDF generation to a lightweight writer so the smoke
    # test only validates end-to-end plumbing without requiring full ReportLab.
    def _fake_sf6(output_path, maintenance, element, measurements):
        p = Path(output_path)
        p.write_bytes(b"%PDF-1.4\n%fake pdf\n")
        return str(p)

    gen._generate_sf6_report = _fake_sf6
    out = gen.generate_maintenance_report(1, 1, output_path=str(tmp_path / "out.pdf"))
    assert Path(out).exists()
    assert Path(out).stat().st_size > 0
    conn.close()
