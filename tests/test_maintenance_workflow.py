from maintenance_workflow import (
    build_pending_tasks_history_text,
    dedupe_attachment_paths,
    get_stage_key_from_label,
    normalize_workflow_state,
    normalize_pending_tasks_text,
    summarize_pending_tasks,
    summarize_workflow,
)


def test_normalize_workflow_state_defaults_to_planning():
    state = normalize_workflow_state(None)

    assert state == {"current_stage": "isolation", "daily_progress": ""}


def test_summarize_workflow_prefers_checklist_then_elements():
    summary = summarize_workflow(
        {"current_stage": "isolation", "daily_progress": ""},
        linked_isolation_request_id=12,
        isolation_display_text="2026-04-15 08:00 - 2026-04-15 15:00 | Accepted",
        checklist_has_content=True,
        checklist_summary_text="2 κατηγορίες | 5/7 βήματα ολοκληρωμένα",
        selected_elements_count=0,
        completed=False,
        pending_tasks_text="",
        attachment_count=0,
        onedrive_link="",
    )

    assert summary["stage_key"] == "preparation"
    assert "#12" in summary["overview_lines"][0]
    assert "08:00 - 2026-04-15 15:00" in summary["overview_lines"][0]
    assert "5/7" in summary["overview_lines"][1]
    assert "Επιλέξτε τα στοιχεία" in summary["next_action"]


def test_summarize_workflow_marks_completed_stage():
    summary = summarize_workflow(
        {
            "current_stage": get_stage_key_from_label("Στοιχεία"),
            "daily_progress": "Ολοκληρώθηκαν οι μετρήσεις.",
        },
        linked_isolation_request_id=5,
        checklist_has_content=True,
        checklist_summary_text="1 κατηγορία | 3/3 βήματα ολοκληρωμένα",
        selected_elements_count=4,
        completed=True,
        pending_tasks_text="",
        attachment_count=3,
        onedrive_link="https://example.invalid/folder",
    )

    assert summary["stage_key"] == "completed"
    assert summary["stage_label"] == "Ολοκληρώθηκε"
    assert "3 αρχεία" in summary["overview_lines"][3]


def test_dedupe_attachment_paths_preserves_order():
    paths = [
        r"C:\temp\alpha.pdf",
        r"C:\temp\beta.pdf",
        r"C:\temp\alpha.pdf",
    ]

    assert dedupe_attachment_paths(paths) == [
        r"C:\temp\alpha.pdf",
        r"C:\temp\beta.pdf",
    ]


def test_pending_tasks_helpers_normalize_and_format_multiline_text():
    raw_text = "  Task A\r\n\r\n  Task B  \n\n- Task C  "

    assert normalize_pending_tasks_text(raw_text) == "Task A\nTask B\n- Task C"
    assert build_pending_tasks_history_text(raw_text) == (
        "Εργασίες που απομένουν:\nTask A\nTask B\n- Task C"
    )


def test_summarize_pending_tasks_compacts_and_truncates():
    summary = summarize_pending_tasks(
        "Task A\nTask B\nTask C",
        max_length=18,
    )

    assert summary.endswith("...")
    assert "Task A" in summary
