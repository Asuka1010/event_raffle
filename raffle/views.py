import csv
import io
from datetime import date, datetime

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm

from .forms import ConfigForm, UploadForm, RegistrationForm, UserSettingsForm
from .models import HistoricalData, RaffleRun
from .services import (
    consolidate_students,
    generate_ranking_csv,
    generate_updated_history_csv,
    parse_csv_upload,
    parse_datetime,
    run_priority_raffle,
    parse_historical_csv,
    parse_event_signup_csv,
)


SESSION_KEYS = {
    "signups": "raffle_signups",
    "historical": "raffle_historical",
    "master": "raffle_master",
    "event_name": "raffle_event_name",
    "event_capacity": "raffle_event_capacity",
    "event_date": "raffle_event_date",
    "eligible_ranked": "raffle_eligible_ranked",
    "selected": "raffle_selected",
    "updated_history_csv": "raffle_updated_history_csv",
}


@login_required
def upload_view(request: HttpRequest) -> HttpResponse:
    """Handle initial historical CSV upload and display historical data"""
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            # Parse the uploaded historical CSV using the new format
            historical_csv = request.FILES.get("historical_csv")
            if historical_csv:
                print(f"DEBUG: File uploaded: {historical_csv.name}, size: {historical_csv.size}")
                # Read the file content first
                csv_content = historical_csv.read().decode("utf-8")
                print(f"DEBUG: CSV content length: {len(csv_content)}")
                # Parse the content
                historical_rows = parse_historical_csv(io.StringIO(csv_content))
                print(f"DEBUG: Parsed {len(historical_rows)} rows from uploaded file")
                # Save to session for now
                request.session[SESSION_KEYS["historical"]] = _serialize_for_session(historical_rows)
                print(f"DEBUG: Saved {len(historical_rows)} rows to session")
                # Save to database
                HistoricalData.objects.update_or_create(
                    user=request.user,
                    defaults={"csv_text": csv_content}
                )
                print(f"DEBUG: Saved to database for user {request.user}")
                # messages.success(request, "Historical database uploaded successfully!") # Removed as per new_code
                return redirect("raffle:upload")
            else:
                print(f"DEBUG: No historical_csv file found in request.FILES")
        else:
            print(f"DEBUG: Form validation failed: {form.errors}")
    else:
        form = UploadForm()

    # Get historical data from database or session
    historical_rows = []
    hd = HistoricalData.objects.filter(user=request.user).first()
    if hd and hd.csv_text:
        # Parse from database
        print(f"DEBUG: Found historical data in database, length: {len(hd.csv_text)}")
        historical_rows = parse_historical_csv(io.StringIO(hd.csv_text))
        print(f"DEBUG: Parsed {len(historical_rows)} rows from database")
        print(f"DEBUG: First row sample: {historical_rows[0] if historical_rows else 'None'}")
    elif SESSION_KEYS["historical"] in request.session:
        # Parse from session
        print(f"DEBUG: Found historical data in session")
        session_data = request.session[SESSION_KEYS["historical"]]
        print(f"DEBUG: Session data type: {type(session_data)}, length: {len(session_data) if session_data else 0}")
        historical_rows = _deserialize_from_session(session_data)
        print(f"DEBUG: Deserialized {len(historical_rows)} rows from session")
        print(f"DEBUG: First row sample: {historical_rows[0] if historical_rows else 'None'}")
    else:
        print(f"DEBUG: No historical data found in database or session")
        print(f"DEBUG: User: {request.user}")
        print(f"DEBUG: HistoricalData objects: {HistoricalData.objects.filter(user=request.user).count()}")
        print(f"DEBUG: Session keys: {list(request.session.keys())}")
        print(f"DEBUG: Looking for key: {SESSION_KEYS['historical']}")

    print(f"DEBUG: Final historical_rows length: {len(historical_rows)}")
    print(f"DEBUG: Template will receive: historical_rows = {bool(historical_rows)}")

    # Get past raffle runs for event filtering
    runs = RaffleRun.objects.filter(user=request.user).order_by("-date")

    # Handle filtering and sorting
    focus_run_id = request.GET.get("event", "")
    sort_by = request.GET.get("sort", "")
    direction = request.GET.get("direction", "asc")

    if focus_run_id:
        # Filter by specific event
        try:
            focus_run = RaffleRun.objects.get(id=focus_run_id, user=request.user)
            # This would need more complex logic to filter historical data by event
            pass
        except RaffleRun.DoesNotExist:
            pass

    if sort_by:
        reverse_sort = direction == "desc"
        if sort_by == "attended":
            historical_rows.sort(key=lambda x: _to_int(x.get(sort_by, 0)), reverse=reverse_sort)
        elif sort_by in ["absent", "late"]:
            historical_rows.sort(key=lambda x: _to_int(x.get(sort_by, 0)), reverse=reverse_sort)

    return render(request, "raffle/upload.html", {
        "form": form,
        "historical_rows": historical_rows,
        "runs": runs,
        "focus_run_id": focus_run_id,
        "sort": sort_by,
        "direction": direction,
    })


@login_required
def config_view(request: HttpRequest) -> HttpResponse:
    """Handle event configuration and signup CSV upload"""
    if request.method == "POST":
        form = ConfigForm(request.POST, request.FILES)
        if form.is_valid():
            request.session[SESSION_KEYS["event_name"]] = form.cleaned_data["event_name"]
            request.session[SESSION_KEYS["event_capacity"]] = int(form.cleaned_data["event_capacity"])
            request.session[SESSION_KEYS["event_date"]] = str(form.cleaned_data["event_date"])  # ISO
            # Build master from uploaded signups and saved historical
            signups = parse_event_signup_csv(form.cleaned_data["signup_csv"])
            cutoff_dt = form.cleaned_data.get("event_cutoff")
            persisted_historical = request.session.get(SESSION_KEYS["historical"]) or []
            if not persisted_historical:
                hd = HistoricalData.objects.filter(user=request.user).first()
                if hd and hd.csv_text:
                    persisted_historical = parse_historical_csv(io.StringIO(hd.csv_text))
            # If signup CSV has signup date/time column, filter/sort around cutoff
            # Accept flexible headers like 'signup time', 'timestamp', 'submitted at'
            if cutoff_dt:
                for row in signups:
                    dt_str = row.get("signup date")
                    row["_signup_dt"] = parse_datetime(dt_str)
                # People signing up before cutoff are ensured registration: mark response yes
                for row in signups:
                    if row.get("_signup_dt") and row["_signup_dt"] <= cutoff_dt:
                        row["participation status"] = "planned"
                # Sort: before cutoff first, then by datetime ascending
                signups.sort(key=lambda r: (not (r.get("_signup_dt") and r["_signup_dt"] <= cutoff_dt), r.get("_signup_dt") or datetime.max))
            master = consolidate_students(signups, persisted_historical)
            request.session[SESSION_KEYS["signups"]] = signups
            request.session[SESSION_KEYS["master"]] = _serialize_for_session(master)
            return redirect("raffle:selection")
    else:
        form = ConfigForm()

    return render(request, "raffle/config.html", {"form": form})


@login_required
def database_view(request: HttpRequest) -> HttpResponse:
    master = request.session.get(SESSION_KEYS["master"]) or []
    event_name = request.session.get(SESSION_KEYS["event_name"]) or ""
    event_capacity = request.session.get(SESSION_KEYS["event_capacity"]) or 0
    # Optional simple search via GET param
    q = (request.GET.get("q") or "").strip().lower()
    students = master
    if q:
        students = [
            s
            for s in master
            if q in (s.get("name") or "").lower()
            or q in (s.get("email") or "").lower()
            or q in (s.get("class") or "").lower()
        ]
    ctx = {
        "students": students,
        "total": len(master),
        "event_name": event_name,
        "event_capacity": event_capacity,
        "q": q,
    }
    return render(request, "raffle/database.html", ctx)


@login_required
def selection_view(request: HttpRequest) -> HttpResponse:
    master = request.session.get(SESSION_KEYS["master"]) or []
    if not master:
        return redirect("raffle:upload")
    capacity = int(request.session.get(SESSION_KEYS["event_capacity"]) or 0)
    eligible_ranked, selected = run_priority_raffle(master, capacity)
    request.session[SESSION_KEYS["eligible_ranked"]] = _serialize_for_session(eligible_ranked)
    request.session[SESSION_KEYS["selected"]] = _serialize_for_session(selected)
    ctx = {
        "eligible": eligible_ranked,
        "selected": selected,
        "capacity": capacity,
    }
    return render(request, "raffle/selection.html", ctx)


@login_required
def results_view(request: HttpRequest) -> HttpResponse:
    eligible = request.session.get(SESSION_KEYS["eligible_ranked"]) or []
    selected = request.session.get(SESSION_KEYS["selected"]) or []
    event_name = request.session.get(SESSION_KEYS["event_name"]) or ""
    event_capacity = int(request.session.get(SESSION_KEYS["event_capacity"]) or 0)
    event_date = request.session.get(SESSION_KEYS["event_date"]) or ""
    # Compute updated historical database preview (do not persist until confirmed)
    # Use the actual historical database as the base for updates
    base_historical = request.session.get(SESSION_KEYS["historical"]) or []
    if not base_historical:
        hd = HistoricalData.objects.filter(user=request.user).first()
        if hd and hd.csv_text:
            base_historical = parse_csv_upload(io.StringIO(hd.csv_text))
    adjustments = request.session.get("raffle_adjustments") or {}

    updated_csv = generate_updated_history_csv(base_historical, selected, event_name, adjustments, event_date)
    updated_rows = parse_csv_upload(io.StringIO(updated_csv))

    # Identify selected participants not present in historical (by email)
    base_emails = { (r.get("email") or "").lower() for r in base_historical }
    missing_selected = [s for s in selected if (s.get("email") or "").lower() not in base_emails]

    if request.method == "POST":
        action = request.POST.get("action") or ""
        if action == "save":
            # Persist per user and record raffle run
            HistoricalData.objects.update_or_create(user=request.user, defaults={"csv_text": updated_csv})
            request.session[SESSION_KEYS["historical"]] = updated_rows
            try:
                selected_csv = _to_csv(selected)
                eligible_csv = generate_ranking_csv(eligible)
                RaffleRun.objects.create(
                    user=request.user,
                    name=event_name,
                    date=datetime.fromisoformat(event_date).date() if event_date else None,
                    capacity=event_capacity,
                    signup_csv_text=_to_csv(request.session.get(SESSION_KEYS["signups"]) or []),
                    selected_csv_text=selected_csv,
                    eligible_csv_text=eligible_csv,
                )
            except Exception:
                pass
            return redirect("raffle:upload")
        else:
            # Cancel -> do not persist
            return redirect("raffle:upload")
    ctx = {
        "eligible_count": len(eligible),
        "selected_count": len(selected),
        "event_name": event_name,
        "event_capacity": event_capacity,
        "event_date": event_date,
        "selected": selected,
        "updated_history_rows": updated_rows,
        "missing_selected": missing_selected,
    }
    return render(request, "raffle/results.html", ctx)


@login_required
def events_list_view(request: HttpRequest) -> HttpResponse:
    runs = RaffleRun.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "raffle/events_list.html", {"runs": runs})


@login_required
def event_detail_view(request: HttpRequest, run_id: int) -> HttpResponse:
    run = RaffleRun.objects.get(user=request.user, id=run_id)
    selected_rows = parse_csv_upload(io.StringIO(run.selected_csv_text)) if run.selected_csv_text else []
    eligible_rows = parse_csv_upload(io.StringIO(run.eligible_csv_text)) if run.eligible_csv_text else []
    if request.method == "POST":
        # Build adjustments and apply to historical DB
        adjustments = {}
        for s in selected_rows:
            email = (s.get("email") or "").lower()
            if not email:
                continue
            adjustments[email] = {
                "absent": bool(request.POST.get(f"absent_{email}")),
                "late": bool(request.POST.get(f"late_{email}")),
            }
        # Load historical
        hd = HistoricalData.objects.filter(user=request.user).first()
        master = parse_csv_upload(io.StringIO(hd.csv_text)) if (hd and hd.csv_text) else []
        # Apply updated historical with just selected rows; event name from run
        updated_csv = generate_updated_history_csv(master, selected_rows, run.name, adjustments)
        HistoricalData.objects.update_or_create(user=request.user, defaults={"csv_text": updated_csv})
        request.session[SESSION_KEYS["historical"]] = parse_csv_upload(io.StringIO(updated_csv))
        return redirect("raffle:event_detail", run_id=run.id)
    return render(
        request,
        "raffle/event_detail.html",
        {"run": run, "selected_rows": selected_rows, "eligible_rows": eligible_rows},
    )


@login_required
def edit_historical_view(request: HttpRequest) -> HttpResponse:
    hd = HistoricalData.objects.filter(user=request.user).first()
    if request.method == "POST":
        try:
            row_count = int(request.POST.get("row_count") or 0)
        except Exception:
            row_count = 0
        preserved_events = request.session.get("raffle_edit_rows_events") or []
        max_event_cols = int(request.session.get("raffle_edit_max_event_cols") or 0)

        # Rebuild rows from POST + preserved event columns
        rebuilt = []
        for idx in range(row_count):
            email = (request.POST.get(f"email_{idx}") or "").strip()
            first_name = (request.POST.get(f"first_name_{idx}") or "").strip()
            last_name = (request.POST.get(f"last_name_{idx}") or "").strip()
            student_class = (request.POST.get(f"class_{idx}") or "").strip()
            attended = request.POST.get(f"attended_{idx}") or "0"
            absent = request.POST.get(f"absent_{idx}") or "0"
            late = request.POST.get(f"late_{idx}") or "0"
            latest_attended = (request.POST.get(f"latest_attended_{idx}") or "").strip()
            events_attended_str = (request.POST.get(f"events_attended_{idx}") or "").strip()
            events_cols = preserved_events[idx] if idx < len(preserved_events) else {}
            rebuilt.append(
                {
                    "email": email,
                    "first name": first_name,
                    "last name": last_name,
                    "class": student_class,
                    "attended": attended,
                    "absent": absent,
                    "late": late,
                    "latest attended": latest_attended,
                    "attended events": events_attended_str,
                    "_events_columns": events_cols,
                }
            )

        # Write CSV in historical format, preserving event columns
        headers = ["email", "First Name", "Last Name", "Class"]
        for i in range(1, max_event_cols + 1):
            headers.append(f"Event{i}")
        headers.extend(["Absent", "Late", "Attended", "Attended Events", "Latest Attended"])

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        for r in rebuilt:
            row = [
                r.get("email") or "",
                r.get("first name") or "",
                r.get("last name") or "",
                r.get("class") or "",
            ]
            events_cols = r.get("_events_columns") or {}
            for i in range(1, max_event_cols + 1):
                row.append(events_cols.get(f"event{i}") or "")
            row.extend([
                r.get("absent") or 0,
                r.get("late") or 0,
                r.get("attended") or 0,
                r.get("attended events") or "",
                r.get("latest attended") or "",
            ])
            writer.writerow(row)
        csv_text = output.getvalue()

        HistoricalData.objects.update_or_create(user=request.user, defaults={"csv_text": csv_text})
        request.session[SESSION_KEYS["historical"]] = parse_csv_upload(io.StringIO(csv_text)) if csv_text else []
        return redirect("raffle:upload")

    # GET: build editable rows from current historical
    rows = []
    if hd and hd.csv_text:
        rows = parse_csv_upload(io.StringIO(hd.csv_text))
    # Prepare rows with preserved event columns
    editable_rows = []
    preserved_events = []
    max_event_cols = 0
    for r in rows:
        events_cols = {k: r.get(k) for k in r.keys() if str(k).startswith("event")}
        count_events = len(events_cols)
        max_event_cols = max(max_event_cols, count_events)
        editable_rows.append(
            {
                "email": r.get("email") or "",
                "first_name": r.get("first name") or "",
                "last_name": r.get("last name") or "",
                "class": r.get("class") or "",
                "attended": r.get("attended") or 0,
                "absent": r.get("absent") or 0,
                "late": r.get("late") or 0,
                "latest_attended": r.get("latest attended") or "",
                "events_attended": r.get("attended events") or "",
            }
        )
        preserved_events.append(events_cols)

    request.session["raffle_edit_rows_events"] = preserved_events
    request.session["raffle_edit_max_event_cols"] = max_event_cols

    return render(
        request,
        "raffle/edit_historical.html",
        {"rows": editable_rows, "row_count": len(editable_rows)},
    )


@login_required
def download_selected_csv(request: HttpRequest) -> HttpResponse:
    selected = request.session.get(SESSION_KEYS["selected"]) or []
    if not selected:
        return redirect("raffle:results")
    content = _to_csv(selected)
    filename = f"{_safe_name(request.session.get(SESSION_KEYS['event_name']) or 'event')}_selected_attendees.csv"
    return _csv_response(content, filename)


@login_required
def download_ranking_csv(request: HttpRequest) -> HttpResponse:
    eligible = request.session.get(SESSION_KEYS["eligible_ranked"]) or []
    if not eligible:
        return redirect("raffle:results")
    content = generate_ranking_csv(eligible)
    filename = f"{_safe_name(request.session.get(SESSION_KEYS['event_name']) or 'event')}_all_eligible.csv"
    return _csv_response(content, filename)


@login_required
def download_updated_database_csv(request: HttpRequest) -> HttpResponse:
    master = request.session.get(SESSION_KEYS["master"]) or []
    selected = request.session.get(SESSION_KEYS["selected"]) or []
    event_name = request.session.get(SESSION_KEYS["event_name"]) or "Event"
    content = generate_updated_history_csv(master, selected, event_name)
    # Persist latest historical database for next runs (session + per-user DB)
    parsed = parse_csv_upload(io.StringIO(content))
    request.session[SESSION_KEYS["historical"]] = parsed
    request.session[SESSION_KEYS["updated_history_csv"]] = content
    HistoricalData.objects.update_or_create(
        user=request.user,
        defaults={"csv_text": content},
    )
    return _csv_response(content, "updated_student_database.csv")


def register_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("raffle:upload")
    else:
        form = RegistrationForm()
    return render(request, "raffle/register.html", {"form": form})


def login_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect("raffle:upload")
    else:
        form = AuthenticationForm(request)
    return render(request, "raffle/login.html", {"form": form})


def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("raffle:login")


@login_required
def settings_view(request: HttpRequest) -> HttpResponse:
    # Prepare historical rows for editing
    hd = HistoricalData.objects.filter(user=request.user).first()
    rows = []
    if hd and hd.csv_text:
        rows = parse_csv_upload(io.StringIO(hd.csv_text))
    editable_rows = []
    preserved_events = []
    max_event_cols = 0
    for r in rows:
        events_cols = {k: r.get(k) for k in r.keys() if str(k).startswith("event")}
        count_events = len(events_cols)
        max_event_cols = max(max_event_cols, count_events)
        editable_rows.append(
            {
                "email": r.get("email") or "",
                "first_name": r.get("first name") or "",
                "last_name": r.get("last name") or "",
                "class": r.get("class") or "",
                "attended": r.get("attended") or 0,
                "absent": r.get("absent") or 0,
                "late": r.get("late") or 0,
                "latest_attended": r.get("latest attended") or "",
                "events_attended": r.get("attended events") or "",
            }
        )
        preserved_events.append(events_cols)

    request.session["raffle_edit_rows_events"] = preserved_events
    request.session["raffle_edit_max_event_cols"] = max_event_cols

    if request.method == "POST":
        form_type = request.POST.get("form_type") or "profile"
        if form_type == "profile":
            form = UserSettingsForm(request.POST, instance=request.user)
            if form.is_valid():
                form.save()
                return redirect("raffle:settings")
        elif form_type == "upload_historical":
            # Handle CSV upload to replace historical DB
            uploaded = request.FILES.get("historical_csv")
            if uploaded:
                rows = parse_csv_upload(uploaded)
                csv_text = _to_csv(rows)
                HistoricalData.objects.update_or_create(user=request.user, defaults={"csv_text": csv_text})
                request.session[SESSION_KEYS["historical"]] = rows
            return redirect("raffle:settings")
        else:  # historical CRUD
            try:
                row_count = int(request.POST.get("row_count") or 0)
            except Exception:
                row_count = 0
            preserved_events = request.session.get("raffle_edit_rows_events") or []
            max_event_cols = int(request.session.get("raffle_edit_max_event_cols") or 0)

            # Rebuild from POST
            rebuilt = []
            for idx in range(row_count):
                if request.POST.get(f"delete_{idx}"):
                    continue
                email = (request.POST.get(f"email_{idx}") or "").strip()
                first_name = (request.POST.get(f"first_name_{idx}") or "").strip()
                last_name = (request.POST.get(f"last_name_{idx}") or "").strip()
                student_class = (request.POST.get(f"class_{idx}") or "").strip()
                attended = request.POST.get(f"attended_{idx}") or "0"
                absent = request.POST.get(f"absent_{idx}") or "0"
                late = request.POST.get(f"late_{idx}") or "0"
                latest_attended = (request.POST.get(f"latest_attended_{idx}") or "").strip()
                events_attended_str = (request.POST.get(f"events_attended_{idx}") or "").strip()
                events_cols = preserved_events[idx] if idx < len(preserved_events) else {}
                rebuilt.append(
                    {
                        "email": email,
                        "first name": first_name,
                        "last name": last_name,
                        "class": student_class,
                        "attended": attended,
                        "absent": absent,
                        "late": late,
                        "latest attended": latest_attended,
                        "attended events": events_attended_str,
                        "_events_columns": events_cols,
                    }
                )

            # Optional add new row
            add_email = (request.POST.get("add_email") or "").strip()
            if add_email:
                rebuilt.append(
                    {
                        "email": add_email,
                        "first name": (request.POST.get("add_first_name") or "").strip(),
                        "last name": (request.POST.get("add_last_name") or "").strip(),
                        "class": (request.POST.get("add_class") or "").strip(),
                        "attended": (request.POST.get("add_attended") or "0").strip(),
                        "absent": (request.POST.get("add_absent") or "0").strip(),
                        "late": (request.POST.get("add_late") or "0").strip(),
                        "latest attended": (request.POST.get("add_latest_attended") or "").strip(),
                        "attended events": (request.POST.get("add_events_attended") or "").strip(),
                        "_events_columns": {},
                    }
                )

            # Write CSV preserving EventN columns
            headers = ["email", "First Name", "Last Name", "Class"]
            for i in range(1, max_event_cols + 1):
                headers.append(f"Event{i}")
            headers.extend(["Absent", "Late", "Attended", "Attended Events", "Latest Attended"])

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(headers)
            for r in rebuilt:
                row = [
                    r.get("email") or "",
                    r.get("first name") or "",
                    r.get("last name") or "",
                    r.get("class") or "",
                ]
                events_cols = r.get("_events_columns") or {}
                for i in range(1, max_event_cols + 1):
                    row.append(events_cols.get(f"event{i}") or "")
                row.extend([
                    r.get("absent") or 0,
                    r.get("late") or 0,
                    r.get("attended") or 0,
                    r.get("attended events") or "",
                    r.get("latest attended") or "",
                ])
                writer.writerow(row)
            csv_text = output.getvalue()

            HistoricalData.objects.update_or_create(user=request.user, defaults={"csv_text": csv_text})
            request.session[SESSION_KEYS["historical"]] = parse_csv_upload(io.StringIO(csv_text)) if csv_text else []
            return redirect("raffle:settings")

    form = UserSettingsForm(instance=request.user)
    return render(
        request,
        "raffle/settings.html",
        {"form": form, "rows": editable_rows, "row_count": len(editable_rows)},
    )


# Helpers
def _serialize_for_session(rows):
    def convert(v):
        if isinstance(v, (datetime,)):
            return v.isoformat()
        if isinstance(v, (date,)):
            return v.isoformat()
        return v

    out = []
    for r in rows:
        out.append({k: convert(v) for k, v in r.items()})
    return out


def _deserialize_from_session(serialized_rows):
    """Deserialize rows from session back to a list of dictionaries."""
    # The data is already in the correct format, just return it directly
    return serialized_rows


def _to_csv(rows) -> str:
    if not rows:
        return ""
    # ensure consistent headers
    headers = list(rows[0].keys())
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return output.getvalue()


def _csv_response(content: str, filename: str) -> HttpResponse:
    resp = HttpResponse(content, content_type="text/csv")
    resp["Content-Disposition"] = f"attachment; filename=\"{filename}\""
    return resp


def _safe_name(name: str) -> str:
    return "_".join(name.split())


def _to_int(value):
    """Convert a value to an integer, handling potential errors."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0

