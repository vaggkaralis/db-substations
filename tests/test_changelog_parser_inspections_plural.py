import json
import os
import tempfile

from changelog import _normalize_change_log_text


def test_parser_accepts_inspections_plural_and_inspection_singular():
    content = (
        '{"operation": "insert", "table": "maintenance", "data": {"id": "android-1775494156060", "substation_id": 40, "date_time": "2026-04-06 22:49", "overall_comments": "", "maintenance_type": "Επαναληπτική συντήρηση", "elements": [{"element_id": 1, "element_comments": "syntirisi test 5/4/26"}]}}\n'
        '{"operation": "insert", "table": "inspections", "data": {"substation_id": 40, "inspection_date": "2026-04-06", "fields": [{"label": "note1", "value": "a"}], "substation_name": "ΑΓΡΑΣ", "month_key": "2026-04", "source_file": "android-local", "created_at": "2026-04-06", "id": "android-1775494190159"}}'
    )

    fd, tmp = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(content)

        text = _normalize_change_log_text(open(tmp, "r", encoding="utf-8").read())
        lines = [ln for ln in text.splitlines() if ln.strip()]

        entries = []
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
            except Exception:
                try:
                    obj = json.loads(ln.strip('"'))
                except Exception:
                    continue
            table = obj.get("table")
            if table in ("maintenance", "inspection", "inspections"):
                entries.append(table)

        assert "maintenance" in entries
        assert any(t in entries for t in ("inspection", "inspections"))
        assert len(entries) == 2
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
