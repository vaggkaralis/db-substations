import os

from onedrive_hybrid_storage import (
    _canonical_overview_report_filename,
    _canonical_report_filename,
    _maintenance_instance_folder_name,
    _normalize_reports_root_path,
)
from pdf_reports import repair_pdf_access


def test_canonical_report_filename_respects_deep_parent_budget():
    parent_dir = (
        r"C:\Users\example\OneDrive - Company\Shared\Very Long Root\Substations"
        r"\Deep\Maintenance\Tree\With\Several\Nested\Folders\And\Reports\Breakers MV"
        r"\Another\Level\20250515_0000_SUBSTATION_WITH_LONG_NAME"
    )

    filename = _canonical_report_filename(
        "SUBSTATION WITH LONG NAME",
        "BREAKER WITH LONG NAME",
        2405,
        parent_dir=parent_dir,
    )

    assert len(os.path.join(parent_dir, filename)) <= 259
    assert filename.endswith(".pdf")
    assert filename.startswith("Αναφ_")


def test_canonical_overview_filename_uses_report_prefix():
    filename = _canonical_overview_report_filename(
        "TEST SUB",
        539,
        parent_dir=r"C:\tmp\instance",
    )

    assert filename.startswith("Αναφ_")
    assert filename.endswith(".pdf")


def test_normalize_reports_root_path_collapses_legacy_reports_folder(tmp_path):
    instance_root = tmp_path / "inst"
    legacy_reports = instance_root / "Αναφορές"

    assert _normalize_reports_root_path(str(legacy_reports)) == os.path.abspath(instance_root)


def test_maintenance_instance_folder_name_uses_short_fallback_for_deep_gate_root():
    gate_root = (
        r"C:\Users\example\OneDrive - Company\Shared\Very Long Root\Substations"
        r"\Deep\Gate Root\With\Long\Segments\ΠΥΛΗ 2"
    )

    folder_name = _maintenance_instance_folder_name(
        "2025-05-15 00:00:00",
        substation_name="ΔΟΞΑ (ΘΕΣΣΑΛΟΝΙΚΗ I)",
        elements=[("Διακόπτης ΜΤ", "Ρ-280"), ("Διακόπτης ΜΤ", "Ρ-290")],
        maintenance_id=2405,
        gate_root=gate_root,
    )

    assert folder_name.startswith("Συντ_")
    projected = os.path.join(gate_root, folder_name, "Αναφ_Διακόπτες ΜΤ", "Αναφ_M2405_1234567890.pdf")
    assert len(projected) <= 258


def test_repair_pdf_access_skips_rewrite_when_pdf_is_already_readable(tmp_path, monkeypatch):
    path = tmp_path / "readable.pdf"
    path.write_bytes(b"%PDF-1.4\n%fake\n")

    monkeypatch.setattr("pdf_reports.is_pdf_readable", lambda _: True)

    def fail(*args, **kwargs):
        raise AssertionError("rewrite path should not run for readable PDFs")

    monkeypatch.setattr("pdf_reports._rewrite_pdf_in_place", fail)
    monkeypatch.setattr("pdf_reports._normalize_pdf_file", fail)

    assert repair_pdf_access(str(path)) is True