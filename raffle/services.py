import csv
import io
import random
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


StudentRow = Dict[str, Any]


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, (int,)):
            return int(value)
        if isinstance(value, float):
            return int(value)
        s = str(value).strip()
        if s == "":
            return default
        return int(float(s))  # handle "20" or "20.0"
    except Exception:
        return default


def _strip_bom(text: Optional[str]) -> str:
    if text is None:
        return ""
    return str(text).replace("\ufeff", "")


def _parse_date(value: Optional[str]) -> Optional[date]:
    if value in (None, "", "null", "NULL", "N/A", "n/a"):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except Exception:
            continue
    return None


def parse_csv_upload(uploaded_file) -> List[StudentRow]:
    """Parse an uploaded CSV into a list of dicts with normalized keys.

    The function is tolerant to column name casing and minor variations.
    """
    raw = uploaded_file.read()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="replace")
    else:
        text = str(raw)
    reader = csv.DictReader(io.StringIO(text))
    rows: List[StudentRow] = []
    for row in reader:
        normalized = {
            _strip_bom(k).strip().lower(): (v.strip() if isinstance(v, str) else v)
            for k, v in row.items()
        }
        rows.append(normalized)
    return rows


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%m/%d/%Y %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except Exception:
            continue
    return None


def consolidate_students(signups: List[StudentRow], historical: List[StudentRow]) -> List[StudentRow]:
    """Combine current sign-ups with historical database into a master list.

    New students (not found in historical) get zeroed counters.
    Matching is attempted by email primarily, then by user_id if present.
    """
    history_index: Dict[str, StudentRow] = {}

    def identity_key(email: Optional[str], first_name: Optional[str], last_name: Optional[str], fallback_id: Optional[str] = None) -> Optional[str]:
        e = (email or "").strip().lower()
        fn = (first_name or "").strip().lower()
        ln = (last_name or "").strip().lower()
        if e or (fn or ln):
            return f"email:{e}|name:{fn} {ln}"
        if fallback_id:
            return f"user_id:{fallback_id}"
        return None

    def normalize_historical(h: StudentRow) -> Optional[Tuple[str, StudentRow]]:
        email = (h.get("email") or h.get("Email") or "").strip().lower()
        first_name = h.get("first name") or h.get("firstname") or ""
        last_name = h.get("last name") or h.get("lastname") or ""
        key = identity_key(email, first_name, last_name)
        if not key:
            return None
        normalized: StudentRow = {
            "user_id": h.get("user_id") or "",
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "name": (first_name + " " + last_name).strip(),
            "class": h.get("class") or h.get("student_class") or "",
            # Counters
            "num_absences": _to_int(h.get("absent")),
            "num_late_arrivals": _to_int(h.get("late")),
            "num_events_attended": _to_int(h.get("attended")),
            # Event list and latest label (string)
            "events_attended": _split_events(h.get("attended events")),
            "latest_attended": h.get("latest attended") or "",
            # Raw event columns preserved if present
            "_events_columns": {k: h.get(k) for k in h.keys() if k.startswith("event")},
        }
        return key, normalized

    for h in historical:
        norm = normalize_historical(h)
        if not norm:
            continue
        key, payload = norm
        history_index[key] = payload

    # Start master with all historical rows; default response is "no"
    master: Dict[str, StudentRow] = {}
    for key, payload in history_index.items():
        base = dict(payload)
        base.setdefault("response", "no")
        master[key] = base

    def normalize_signup(s: StudentRow) -> Optional[Tuple[str, StudentRow]]:
        email = (s.get("email") or s.get("email address") or "").strip().lower()
        attendee_id = (s.get("attendee id") or s.get("id") or "").strip()
        first_name = s.get("firstname") or s.get("first name") or s.get("first") or s.get("firstname(s)") or ""
        last_name = s.get("lastname") or s.get("last name") or s.get("last") or ""
        status = (s.get("participation status") or s.get("status") or "").strip().lower()
        if not email and not attendee_id:
            return None
        response = "yes" if status in {"planned", "yes"} else "no"
        normalized: StudentRow = {
            "user_id": attendee_id,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "name": (first_name + " " + last_name).strip() or s.get("name") or "",
            "class": s.get("class") or s.get("student_class") or "",
            "response": response,
        }
        key = identity_key(email, first_name, last_name, attendee_id)
        return key, normalized

    for s in signups:
        norm = normalize_signup(s)
        if not norm:
            continue
        key, signup_payload = norm
        # Use existing master row if present (from history), otherwise defaults
        base = dict(master.get(key) or {})
        hist = history_index.get(key)
        row: StudentRow = {
            **base,
            **signup_payload,
            # Preserve counters from history/base or zero for brand new
            "num_absences": (base.get("num_absences") if base else (hist.get("num_absences") if hist else 0)) or 0,
            "num_late_arrivals": (base.get("num_late_arrivals") if base else (hist.get("num_late_arrivals") if hist else 0)) or 0,
            "num_events_attended": (base.get("num_events_attended") if base else (hist.get("num_events_attended") if hist else 0)) or 0,
            "events_attended": (base.get("events_attended") if base else (hist.get("events_attended") if hist else [])) or [],
            "latest_attended": (base.get("latest_attended") if base else (hist.get("latest_attended") if hist else "")) or "",
            "_events_columns": (base.get("_events_columns") if base else (hist.get("_events_columns") if hist else {})) or {},
        }
        # Prefer historical/base identity fields over signup where available
        for field in ("first_name", "last_name", "name", "class", "email"):
            if base.get(field):
                row[field] = base[field]
        master[key] = row

    return list(master.values())


def _split_events(value: Optional[str]) -> List[str]:
    if not value:
        return []
    # Handle comma-separated events
    return [v.strip() for v in str(value).split(",") if v.strip()]


def _priority_key(student: StudentRow) -> Tuple[int, int, int, date]:
    # We may not have a date in this format; treat as None which becomes earliest
    last_date = student.get("last_attended_date")
    if isinstance(last_date, str):
        parsed = _parse_date(last_date)
    else:
        parsed = last_date
    priority_date = parsed or date.min
    return (
        int(student.get("num_events_attended") or 0),
        int(student.get("num_absences") or 0),
        int(student.get("num_late_arrivals") or 0),
        priority_date,
    )


def run_priority_raffle(students: List[StudentRow], capacity: int) -> Tuple[List[StudentRow], List[StudentRow]]:
    """Return (eligible_sorted_with_rank, selected_top_n).

    Implements multi-level sorting with a random tie-breaker by shuffling before a stable sort.
    Only considers students with response == "yes" (case-insensitive).
    """
    eligible = [s for s in students if (s.get("response") or "").strip().lower() == "yes"]
    rng = random.Random()
    rng.shuffle(eligible)
    eligible.sort(key=_priority_key)

    selected = eligible[: max(capacity, 0)]

    # Annotate rank
    for idx, s in enumerate(eligible, start=1):
        s["rank"] = idx
        s["selected"] = s in selected
    return eligible, selected


def generate_ranking_csv(eligible_ranked: List[StudentRow]) -> str:
    headers = [
        "rank",
        "selected",
        "user_id",
        "name",
        "email",
        "class",
        "num_events_attended",
        "num_absences",
        "num_late_arrivals",
        "last_attended_date",
    ]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for s in eligible_ranked:
        writer.writerow([
            s.get("rank"),
            "yes" if s.get("selected") else "no",
            s.get("user_id") or "",
            s.get("name") or "",
            s.get("email") or "",
            s.get("class") or "",
            int(s.get("num_events_attended") or 0),
            int(s.get("num_absences") or 0),
            int(s.get("num_late_arrivals") or 0),
            _format_date(s.get("last_attended_date")),
        ])
    return output.getvalue()


def generate_updated_history_csv(
    base_historical_students: List[StudentRow],
    selected: List[StudentRow],
    event_name: str,
    adjustments: Optional[Dict[str, Dict[str, bool]]] = None,
    event_date_str: Optional[str] = None,
) -> str:
    """Generate historical database CSV in the same format as the provided sample.

    Columns:
    email, First Name, Last Name, Class, Event1..Event20, Absent, Late, Attended, Attended Events, Latest Attended
    We preserve any incoming EventN columns if present on a row, otherwise keep them blank.
    """
    selected_emails = {str(s.get("email") or "").lower() for s in selected}
    selected_name_pairs = {
        (
            (s.get("first_name") or ((s.get("name") or "").split(" ")[0] if s.get("name") else "")).strip().lower(),
            (s.get("last_name") or (" ".join((s.get("name") or "").split(" ")[1:]) if s.get("name") else "")).strip().lower(),
        )
        for s in selected
    }
    adjustments = adjustments or {}
    output = io.StringIO()

    # Determine widest set of event columns seen in historical data
    max_event_cols = 0
    for s in base_historical_students:
        events_cols: Dict[str, Any] = s.get("_events_columns") or {}
        count = sum(1 for k in events_cols.keys() if k.startswith("event"))
        if count > max_event_cols:
            max_event_cols = count
    # Default to 0; allow writing Event1..EventN if present previously
    headers = [
        "email",
        "First Name",
        "Last Name",
        "Class",
    ]
    for i in range(1, max_event_cols + 1):
        headers.append(f"Event{i}")
    headers.extend(["Absent", "Late", "Attended", "Attended Events", "Latest Attended"])

    writer = csv.writer(output)
    writer.writerow(headers)

    for s in base_historical_students:
        email = (s.get("email") or "").lower()
        # Prefer names from normalized fields; fall back to CSV columns; last resort split name
        first_name = (
            s.get("first_name")
            or s.get("first name")
            or ((s.get("name") or "").split(" ")[0] if s.get("name") else "")
        )
        last_name = (
            s.get("last_name")
            or s.get("last name")
            or (" ".join((s.get("name") or "").split(" ")[1:]) if s.get("name") else "")
        )
        student_class = s.get("class") or ""

        is_selected = email in selected_emails
        num_attended = _to_int(s.get("num_events_attended") or s.get("attended") or 0) + (1 if is_selected else 0)
        num_absences = _to_int(s.get("num_absences") or s.get("absent") or 0)
        num_late = _to_int(s.get("num_late_arrivals") or s.get("late") or 0)
        adj = adjustments.get(email) or {}
        if adj.get("absent"):
            num_absences += 1
        if adj.get("late"):
            num_late += 1
        # events_attended may be list or CSV string
        events_attended = list(s.get("events_attended") or [])
        if not events_attended and s.get("attended events"):
            events_attended = _split_events(s.get("attended events"))
        if is_selected:
            events_attended.append(event_name)

        latest_attended_label = s.get("latest_attended") or s.get("latest attended") or ""
        if is_selected:
            # Historical column stores latest attended label; use event name for compatibility
            latest_attended_label = event_name

        row = [email, first_name, last_name, student_class]
        # EventN columns
        # Preserve EventN columns if present on the row (either packed or inline)
        events_cols: Dict[str, Any] = s.get("_events_columns") or {k: s.get(k) for k in s.keys() if str(k).startswith("event")}
        for i in range(1, max_event_cols + 1):
            row.append(events_cols.get(f"event{i}") or "")
        # Counters and aggregates
        row.extend([
            num_absences,
            num_late,
            num_attended,
            ", ".join(events_attended),
            latest_attended_label,
        ])
        writer.writerow(row)

    return output.getvalue()


def _format_date(value: Optional[date]) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        # assume already formatted
        return value
    return value.isoformat()


