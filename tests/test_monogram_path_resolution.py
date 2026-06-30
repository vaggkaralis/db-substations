import pathlib

import DBrun


def test_resolve_monogram_pdf_path_accepts_absolute(tmp_path):
    app = DBrun.SubstationApp()
    pdf_path = tmp_path / "single-line.pdf"
    pdf_path.write_text("dummy", encoding="utf-8")

    resolved = app._resolve_monogram_pdf_path(str(pdf_path))

    assert resolved == str(pdf_path.resolve())


def test_resolve_monogram_pdf_path_accepts_file_uri(tmp_path):
    app = DBrun.SubstationApp()
    pdf_path = tmp_path / "diagram.pdf"
    pdf_path.write_text("dummy", encoding="utf-8")

    uri = pathlib.Path(pdf_path).as_uri()
    resolved = app._resolve_monogram_pdf_path(uri)

    assert resolved == str(pdf_path.resolve())


def test_resolve_monogram_pdf_path_resolves_relative_to_db_dir(tmp_path):
    app = DBrun.SubstationApp()

    db_dir = tmp_path / "portable"
    db_dir.mkdir(parents=True)
    app.db_path = str(db_dir / "substations.db")

    pdf_dir = db_dir / "monograms"
    pdf_dir.mkdir(parents=True)
    pdf_path = pdf_dir / "sub-a.pdf"
    pdf_path.write_text("dummy", encoding="utf-8")

    resolved = app._resolve_monogram_pdf_path("monograms/sub-a.pdf")

    assert resolved == str(pdf_path.resolve())
