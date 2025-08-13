import csv
import io
from datetime import date, datetime

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm

from .forms import ConfigForm, UploadForm, RegistrationForm
from .models import HistoricalData, RaffleRun
from .services import (
    consolidate_students,
    generate_ranking_csv,
    generate_updated_history_csv,
    parse_csv_upload,
    run_priority_raffle,
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
    # Build historical preview for GET and POST rendering
    historical_rows = []
    try:
        persisted_historical = request.session.get(SESSION_KEYS["historical"]) or []
        if not persisted_historical:
            hd = HistoricalData.objects.filter(user=request.user).first()
            if hd and hd.csv_text:
                persisted_historical = parse_csv_upload(io.BytesIO(hd.csv_text.encode("utf-8")))
        historical_rows = persisted_historical
    except Exception:
        historical_rows = []

    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            signups = parse_csv_upload(form.cleaned_data["signup_csv"])
            # Load persisted historical for this user; fallback to session; otherwise from upload
            persisted_historical = request.session.get(SESSION_KEYS["historical"]) or []
            if not persisted_historical:
                try:
                    hd = HistoricalData.objects.filter(user=request.user).first()
                    if hd and hd.csv_text:
                        persisted_historical = parse_csv_upload(io.BytesIO(hd.csv_text.encode("utf-8")))
                except Exception:
                    persisted_historical = []
            historical = persisted_historical
            if not persisted_historical and form.cleaned_data.get("historical_csv"):
                historical = parse_csv_upload(form.cleaned_data["historical_csv"])
                request.session[SESSION_KEYS["historical"]] = historical
            master = consolidate_students(signups, historical)
            request.session[SESSION_KEYS["signups"]] = signups
            request.session[SESSION_KEYS["master"]] = _serialize_for_session(master)
            return redirect("raffle:config")
    else:
        form = UploadForm()
    return render(request, "raffle/upload.html", {"form": form, "historical_rows": historical_rows})


@login_required
def config_view(request: HttpRequest) -> HttpResponse:
    if SESSION_KEYS["master"] not in request.session:
        return redirect("raffle:upload")
    if request.method == "POST":
        form = ConfigForm(request.POST)
        if form.is_valid():
            request.session[SESSION_KEYS["event_name"]] = form.cleaned_data["event_name"]
            request.session[SESSION_KEYS["event_capacity"]] = int(form.cleaned_data["event_capacity"])
            request.session[SESSION_KEYS["event_date"]] = str(form.cleaned_data["event_date"])  # ISO
            return redirect("raffle:database")
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
    # Ensure updated historical database is computed, stored, and previewed
    master = request.session.get(SESSION_KEYS["master"]) or []
    # Build adjustments from POST (checkboxes like absent_email and late_email)
    adjustments = {}
    if request.method == "POST":
        for s in selected:
            email = (s.get("email") or "").lower()
            if not email:
                continue
            adjustments[email] = {
                "absent": bool(request.POST.get(f"absent_{email}")),
                "late": bool(request.POST.get(f"late_{email}")),
            }
        request.session["raffle_adjustments"] = adjustments
    else:
        adjustments = request.session.get("raffle_adjustments") or {}

    updated_csv = generate_updated_history_csv(master, selected, event_name, adjustments)
    request.session[SESSION_KEYS["updated_history_csv"]] = updated_csv
    # Persist per user
    HistoricalData.objects.update_or_create(user=request.user, defaults={"csv_text": updated_csv})
    updated_rows = parse_csv_upload(io.BytesIO(updated_csv.encode("utf-8")))
    # Persist raffle run for history listing
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
    ctx = {
        "eligible_count": len(eligible),
        "selected_count": len(selected),
        "event_name": event_name,
        "event_capacity": event_capacity,
        "event_date": event_date,
        "selected": selected,
        "updated_history_rows": updated_rows,
    }
    return render(request, "raffle/results.html", ctx)


@login_required
def events_list_view(request: HttpRequest) -> HttpResponse:
    runs = RaffleRun.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "raffle/events_list.html", {"runs": runs})


@login_required
def event_detail_view(request: HttpRequest, run_id: int) -> HttpResponse:
    run = RaffleRun.objects.get(user=request.user, id=run_id)
    selected_rows = parse_csv_upload(io.BytesIO(run.selected_csv_text.encode("utf-8"))) if run.selected_csv_text else []
    eligible_rows = parse_csv_upload(io.BytesIO(run.eligible_csv_text.encode("utf-8"))) if run.eligible_csv_text else []
    return render(
        request,
        "raffle/event_detail.html",
        {"run": run, "selected_rows": selected_rows, "eligible_rows": eligible_rows},
    )


@login_required
def edit_historical_view(request: HttpRequest) -> HttpResponse:
    hd = HistoricalData.objects.filter(user=request.user).first()
    if request.method == "POST":
        csv_text = request.POST.get("csv_text") or ""
        HistoricalData.objects.update_or_create(user=request.user, defaults={"csv_text": csv_text})
        request.session[SESSION_KEYS["historical"]] = parse_csv_upload(io.BytesIO(csv_text.encode("utf-8"))) if csv_text else []
        return redirect("raffle:upload")
    csv_text = hd.csv_text if hd else ""
    return render(request, "raffle/edit_historical.html", {"csv_text": csv_text})


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
    parsed = parse_csv_upload(io.BytesIO(content.encode("utf-8")))
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

