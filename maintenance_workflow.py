import json
import os


WORKFLOW_STAGES = [
    ("isolation", "Απομόνωση"),
    ("preparation", "Προετοιμασία"),
    ("elements", "Στοιχεία"),
    ("attachments", "Αρχεία / Ολοκλήρωση"),
    ("completed", "Ολοκληρώθηκε"),
]

_WORKFLOW_STAGE_LABELS = dict(WORKFLOW_STAGES)
_VALID_STAGE_KEYS = {key for key, _label in WORKFLOW_STAGES}
_WORKFLOW_STAGE_INDEX = {
    key: index for index, (key, _label) in enumerate(WORKFLOW_STAGES)
}


def normalize_workflow_state(raw_state):
    state = raw_state if isinstance(raw_state, dict) else {}
    current_stage = str(state.get("current_stage") or "").strip().lower()
    if current_stage not in _VALID_STAGE_KEYS:
        current_stage = "isolation"
    return {
        "current_stage": current_stage,
        "daily_progress": str(state.get("daily_progress") or "").strip(),
    }


def load_workflow_from_data_json(raw_data_json):
    if not raw_data_json:
        return {}, normalize_workflow_state(None)
    try:
        payload = json.loads(raw_data_json)
    except Exception:
        return {}, normalize_workflow_state(None)
    if not isinstance(payload, dict):
        return {}, normalize_workflow_state(None)
    workflow_state = normalize_workflow_state(payload.get("workflow"))
    return payload, workflow_state


def dump_workflow_to_data_json(existing_payload, workflow_state):
    payload = dict(existing_payload or {})
    normalized_workflow = normalize_workflow_state(workflow_state)
    if normalized_workflow:
        payload["workflow"] = normalized_workflow
    if not payload:
        return None
    return json.dumps(payload, ensure_ascii=False)


def dedupe_attachment_paths(paths):
    ordered = []
    seen = set()
    for path in paths or []:
        text = str(path or "").strip()
        if not text:
            continue
        norm = os.path.normcase(os.path.normpath(text))
        if norm in seen:
            continue
        seen.add(norm)
        ordered.append(text)
    return ordered


def normalize_pending_tasks_text(tasks_text):
    text = str(tasks_text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines)


def build_pending_tasks_history_text(
    tasks_text,
    *,
    title="Εργασίες που απομένουν",
):
    normalized = normalize_pending_tasks_text(tasks_text)
    if not normalized:
        return ""
    return f"{title}:\n{normalized}"


def summarize_pending_tasks(tasks_text, *, max_length=160):
    normalized = normalize_pending_tasks_text(tasks_text)
    if not normalized:
        return ""
    compact = " • ".join(normalized.splitlines())
    if len(compact) <= max_length:
        return compact
    return f"{compact[: max_length - 3].rstrip()}..."


def get_stage_values():
    return [label for _key, label in WORKFLOW_STAGES]


def get_stage_label(stage_key):
    return _WORKFLOW_STAGE_LABELS.get(stage_key, _WORKFLOW_STAGE_LABELS["isolation"])


def get_stage_key_from_label(label):
    text = str(label or "").strip()
    for key, value in WORKFLOW_STAGES:
        if value == text:
            return key
    return "isolation"


def infer_workflow_stage(
    workflow_state,
    *,
    linked_isolation_request_id=None,
    checklist_has_content=False,
    selected_elements_count=0,
    completed=False,
    pending_tasks_text="",
    attachment_count=0,
    onedrive_link="",
):
    if completed:
        return "completed"

    if attachment_count or str(onedrive_link or "").strip():
        return "attachments"
    if selected_elements_count > 0:
        return "elements"
    if checklist_has_content:
        return "preparation"
    if linked_isolation_request_id:
        return "isolation"
    if str(pending_tasks_text or "").strip():
        return "elements"

    manual_stage = normalize_workflow_state(workflow_state).get("current_stage")
    if manual_stage in _VALID_STAGE_KEYS:
        return manual_stage

    return "isolation"


def summarize_workflow(
    workflow_state,
    *,
    linked_isolation_request_id=None,
    isolation_display_text="",
    checklist_has_content=False,
    checklist_summary_text="",
    selected_elements_count=0,
    completed=False,
    pending_tasks_text="",
    attachment_count=0,
    onedrive_link="",
):
    normalized = normalize_workflow_state(workflow_state)
    current_stage_key = normalized.get("current_stage") or "isolation"
    stage_key = infer_workflow_stage(
        normalized,
        linked_isolation_request_id=linked_isolation_request_id,
        checklist_has_content=checklist_has_content,
        selected_elements_count=selected_elements_count,
        completed=completed,
        pending_tasks_text=pending_tasks_text,
        attachment_count=attachment_count,
        onedrive_link=onedrive_link,
    )
    guidance_stage_key = current_stage_key
    if _WORKFLOW_STAGE_INDEX.get(stage_key, 0) > _WORKFLOW_STAGE_INDEX.get(
        current_stage_key, 0
    ):
        guidance_stage_key = stage_key

    pending_tasks_text = str(pending_tasks_text or "").strip()
    daily_progress = normalized.get("daily_progress") or ""
    overview_lines = [
        "1. Απομόνωση: "
        + (
            (
                f"#{linked_isolation_request_id} | {isolation_display_text.strip()}"
                if isolation_display_text and str(isolation_display_text).strip()
                else f"συνδεδεμένη (#{linked_isolation_request_id})"
            )
            if linked_isolation_request_id
            else "προαιρετική / δεν συνδέθηκε"
        ),
        "2. Προετοιμασία: "
        + (
            checklist_summary_text.strip()
            if checklist_has_content and checklist_summary_text
            else "δεν έχει συμπληρωθεί checklist"
        ),
        "3. Στοιχεία: "
        + (
            f"{selected_elements_count} επιλεγμένα"
            if selected_elements_count
            else "δεν έχουν επιλεγεί στοιχεία"
        ),
        "4. Αρχεία: "
        + (
            f"{attachment_count} αρχεία προς αντιγραφή"
            if attachment_count
            else (
                "υπάρχει σύνδεσμος φακέλου"
                if str(onedrive_link or "").strip()
                else "δεν έχουν οριστεί αρχεία ακόμη"
            )
        ),
    ]

    if completed:
        next_action = (
            "Ελέγξτε τα αρχεία και τις αναφορές πριν κλείσετε οριστικά τη συντήρηση."
        )
    elif guidance_stage_key == "isolation":
        next_action = "Συνδέστε την απομόνωση όταν υπάρχει, ώστε η διαδικασία να παραμένει ενιαία."
    elif guidance_stage_key == "preparation":
        next_action = "Επιλέξτε τα στοιχεία που θα συντηρηθούν, κατά προτίμηση ανά πύλη ή ομάδα εργασίας."
    elif guidance_stage_key == "elements":
        next_action = "Προσθέστε αρχεία ή ορίστε σύνδεσμο φακέλου ώστε οι μετρήσεις και οι φωτογραφίες να είναι άμεσα προσβάσιμες."
    elif guidance_stage_key == "attachments":
        next_action = "Καταγράψτε την ημερήσια πρόοδο και κλείστε τη συντήρηση όταν ολοκληρωθούν τα στοιχεία και τα συνημμένα."
    elif pending_tasks_text:
        next_action = "Η συντήρηση μένει ανοιχτή. Ενημερώνετε την πρόοδο κάθε ημέρας και κλείστε την όταν μηδενιστούν οι εκκρεμότητες."
    else:
        next_action = "Καταγράψτε την ημερήσια πρόοδο και κλείστε τη συντήρηση όταν ολοκληρωθούν τα στοιχεία και τα συνημμένα."

    return {
        "stage_key": stage_key,
        "stage_label": get_stage_label(stage_key),
        "overview_lines": overview_lines,
        "next_action": next_action,
        "daily_progress": daily_progress,
    }
