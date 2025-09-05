# routes/calendar.py
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from utils.get_current_user_cognito import get_current_user
from .integrations.google.calendar import with_service, ensure_creds
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

router = APIRouter(prefix="/calendar", tags=["Calendar"])
# routes/calendar.py (añade imports)


def _parse_anchor_date(date_str: Optional[str], tz: str) -> datetime:
    """
    Convierte YYYY-MM-DD (local) a datetime aware al inicio del día en tz.
    Si no viene, usa 'hoy' en esa tz.
    """
    z = ZoneInfo(tz)
    if date_str:
        y, m, d = map(int, date_str.split("-"))
        return datetime(y, m, d, 0, 0, 0, tzinfo=z)
    now = datetime.now(z)
    return datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=z)


def _parse_local_dt_to_rfc3339(local_iso: str, tz: str) -> str:
    """
    local_iso: 'YYYY-MM-DDTHH:mm' o 'YYYY-MM-DDTHH:mm:ss'
    Devuelve RFC3339 con offset, ej '2025-08-26T09:00:00-05:00'
    """
    # Permite que venga sin segundos
    if len(local_iso) == 16:  # YYYY-MM-DDTHH:mm
        local_iso = local_iso + ":00"
    try:
        dt_naive = datetime.fromisoformat(local_iso)  # naive
    except ValueError:
        raise HTTPException(400, detail=f"start/end con formato inválido: {local_iso}")
    try:
        z = ZoneInfo(tz)
    except Exception:
        raise HTTPException(400, detail=f"timezone inválido: {tz}")
    dt_aware = dt_naive.replace(tzinfo=z)
    # ISO 8601 con offset; Google acepta este formato directamente
    return dt_aware.isoformat()


def _compute_range(
    view: Literal["month", "week", "day"],
    anchor: datetime,
) -> tuple[datetime, datetime]:
    """
    Devuelve (timeMin_inclusive, timeMax_exclusive) en la tz del anchor.
    - month: desde el 1er día del mes 00:00 hasta el 1ro del mes siguiente 00:00 (exclusive)
    - week:  lunes 00:00 hasta lunes siguiente 00:00 (exclusive)
    - day:   día 00:00 hasta día siguiente 00:00 (exclusive)
    """
    # normaliza al inicio de día
    start = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
    if view == "day":
        end = start + timedelta(days=1)
    elif view == "week":
        # lunes = 0 … domingo = 6
        weekday = start.weekday()
        monday = start - timedelta(days=weekday)
        end = monday + timedelta(days=7)
        start = monday
    else:  # "month"
        first = start.replace(day=1)
        # siguiente mes:
        if first.month == 12:
            next_month = first.replace(year=first.year + 1, month=1)
        else:
            next_month = first.replace(month=first.month + 1)
        end = next_month
        start = first
    return start, end


def _to_rfc3339_z(dt: datetime) -> str:
    """
    Google Calendar API acepta RFC3339.
    Si el datetime es aware con tz, lo convertimos a UTC y emitimos con 'Z'.
    """
    if dt.tzinfo is None:
        # asume UTC si llega naive (no debería)
        return dt.isoformat(timespec="seconds") + "Z"
    utc = dt.astimezone(ZoneInfo("UTC"))
    return utc.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def normalize_event_resp(ev: dict):
    s = ev.get("start", {})
    e = ev.get("end", {})
    return {
        "id": ev.get("id"),
        "summary": ev.get("summary"),
        "description": ev.get("description"),
        "location": ev.get("location"),
        "start": s.get("dateTime") or s.get("date"),
        "end": e.get("dateTime") or e.get("date"),
        "all_day": bool(s.get("date")),
        "hangoutLink": ev.get("hangoutLink"),
        "htmlLink": ev.get("htmlLink"),
    }


# routes/calendar.py (reemplaza tu list_events por esta versión)


@router.get("/events")
async def list_events(
    # 1) filtros crudos (si vienen, tienen prioridad)
    timeMin: Optional[str] = Query(None, description="RFC3339, ej 2025-08-01T00:00:00Z"),
    timeMax: Optional[str] = Query(None, description="RFC3339, ej 2025-09-01T00:00:00Z"),
    # 2) filtros “amigables” por rango
    view: Optional[Literal["month", "week", "day"]] = Query(
        None, description="Si no envías timeMin/timeMax: {month|week|day}"
    ),
    date_str: Optional[str] = Query(None, alias="date", description="Anchor YYYY-MM-DD en tz local"),
    tz: str = Query("UTC", description="IANA TZ, ej America/Bogota"),
    # paginación y demás
    pageToken: Optional[str] = Query(None),
    maxResults: int = Query(200, ge=1, le=2500),
    calendarId: str = "primary",
    current_user=Depends(get_current_user),
):
    """
    Reglas:
    - Si mandas timeMin & timeMax → se usan tal cual.
    - Si no, se calculan a partir de view/date/tz.
    - timeMax es EXCLUSIVO (Google).
    """
    creds = await ensure_creds(current_user.sub)
    if not creds:
        raise HTTPException(409, "Conecta tu Google Calendar primero.")

    # calcula rango si no te lo mandaron
    if not timeMin or not timeMax:
        # Defaults: mes actual en tz si no especificas view
        v = view or "month"
        try:
            anchor = _parse_anchor_date(date_str, tz)
        except Exception:
            raise HTTPException(400, detail="date debe ser YYYY-MM-DD válido")
        tmin_dt, tmax_dt = _compute_range(v, anchor)
        timeMin = _to_rfc3339_z(tmin_dt)
        timeMax = _to_rfc3339_z(tmax_dt)

    def _list(svc):
        return (
            svc.events()
            .list(
                calendarId=calendarId,
                timeMin=timeMin,
                timeMax=timeMax,
                singleEvents=True,
                orderBy="startTime",
                pageToken=pageToken,
                maxResults=maxResults,
            )
            .execute()
        )

    data = await with_service(creds, _list)
    return {
        "items": [normalize_event_resp(e) for e in data.get("items", [])],
        "nextPageToken": data.get("nextPageToken"),
        "timeMin": timeMin,
        "timeMax": timeMax,
    }


@router.post("/events")
async def create_event(
    payload: dict,
    calendarId: str = "primary",
    current_user=Depends(get_current_user),
):
    creds = await ensure_creds(current_user.sub)
    if not creds:
        raise HTTPException(409, "Conecta tu Google Calendar primero.")

    tz = payload.get("timezone") or "UTC"
    all_day = bool(payload.get("all_day"))

    if all_day:
        # Validación de all-day: start/end como YYYY-MM-DD
        start_date = payload.get("start")
        end_date = payload.get("end")
        if not (start_date and end_date) or len(start_date) != 10 or len(end_date) != 10:
            raise HTTPException(400, detail="Para all_day usa start/end como 'YYYY-MM-DD'")
        start = {"date": start_date, "timeZone": tz}
        end = {"date": end_date, "timeZone": tz}
    else:
        if not payload.get("start") or not payload.get("end"):
            raise HTTPException(400, detail="start y end son requeridos")

        dt_start = _parse_local_dt_to_rfc3339(payload["start"], tz)
        dt_end = _parse_local_dt_to_rfc3339(payload["end"], tz)

        # Validar start < end
        if datetime.fromisoformat(dt_end) <= datetime.fromisoformat(dt_start):
            raise HTTPException(400, detail="end debe ser posterior a start")

        # Puedes omitir timeZone si ya llevas offset. Dejarlo no hace daño.
        start = {"dateTime": dt_start, "timeZone": tz}
        end = {"dateTime": dt_end, "timeZone": tz}

    # Normaliza estructuras opcionales
    attendees_raw = payload.get("attendees") or []
    attendees = []
    for a in attendees_raw:
        if isinstance(a, str):
            attendees.append({"email": a})
        elif isinstance(a, dict) and "email" in a:
            attendees.append({"email": a["email"]})
    reminders = payload.get("reminders") or {"useDefault": True}

    body = {
        "summary": (payload.get("summary") or "(sin título)")[:250],
        "description": payload.get("description"),
        "location": payload.get("location"),
        "start": start,
        "end": end,
        "attendees": attendees,
        "reminders": reminders,
    }

    if payload.get("create_meet"):
        import uuid

        body["conferenceData"] = {
            "createRequest": {
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
                "requestId": str(uuid.uuid4()),
            }
        }

    def _insert(svc):
        return (
            svc.events()
            .insert(
                calendarId=calendarId,
                body=body,
                conferenceDataVersion=1 if payload.get("create_meet") else 0,
            )
            .execute()
        )

    try:
        ev = await with_service(creds, _insert)
    except Exception:
        raise
    return normalize_event_resp(ev)


@router.patch("/events/{event_id}")
async def update_event(
    event_id: str,
    payload: dict,
    calendarId: str = "primary",
    current_user=Depends(get_current_user),
):
    creds = await ensure_creds(current_user.sub)
    if not creds:
        raise HTTPException(409, "Conecta tu Google Calendar primero.")

    def _patch(svc):
        return svc.events().patch(calendarId=calendarId, eventId=event_id, body=payload).execute()

    ev = await with_service(creds, _patch)
    return normalize_event_resp(ev)


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: str,
    calendarId: str = "primary",
    current_user=Depends(get_current_user),
):
    creds = await ensure_creds(current_user.sub)
    if not creds:
        raise HTTPException(409, "Conecta tu Google Calendar primero.")

    def _del(svc):
        return svc.events().delete(calendarId=calendarId, eventId=event_id).execute()

    await with_service(creds, _del)
    return {"ok": True}
