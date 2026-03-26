import pytest
from pathlib import Path


def test_generated_pdf_is_readable(tmp_path):
    # Ensure pikepdf is available for validation
    pikepdf = pytest.importorskip("pikepdf")

    # Import project module (project root already on sys.path when pytest runs)
    import importlib
    pdf_reports = importlib.import_module("pdf_reports")
    # Skip if pdf_reports could not initialize ReportLab support (shims may not
    # provide full API required for generation).
    if not getattr(pdf_reports, "_HAS_REPORTLAB", False):
        pytest.skip("ReportLab not fully available for PDF generation")
    generate_preparation_checklist_pdf = pdf_reports.generate_preparation_checklist_pdf
    out = tmp_path / "test_checklist.pdf"

    # Generate a minimal checklist PDF
    generate_preparation_checklist_pdf(
        {"selected_categories": []},
        [],
        metadata={"title": "test", "date_time": "now"},
        output_path=str(out),
    )

    assert out.exists(), "PDF was not created"
    assert out.stat().st_size > 1000, "Generated PDF is unexpectedly small"

    # Verify pikepdf can open the file (ensures filters/permissions are correct)
    with pikepdf.Pdf.open(str(out)) as pdf:
        assert len(pdf.pages) >= 1
