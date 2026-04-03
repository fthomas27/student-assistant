import os
import json
import logging
import threading
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

import psycopg2
import psycopg2.extras
import requests
from flask import Flask, request, jsonify, render_template
from icalendar import Calendar
from apscheduler.schedulers.background import BackgroundScheduler
import anthropic

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

TZ = ZoneInfo("America/Denver")

_briefing_lock = threading.Lock()
_timer_lock = threading.Lock()

# ── Hardcoded calendar URLs ──────────────────────────────────────────────────
PERSONAL_ICAL_URL = "https://p107-caldav.icloud.com/published/2/OTg1NzQ4NTY5ODU3NDg1NhsR_oH4Uc5HZPs6egZwYCgNaNoVdbGZnhTJRBFIsovYYGFTxg1u1ClSf4dPKWfDbUirJMtTPpJPtm_Zct60PgM"
CANVAS_ICAL_URL = "https://pcsd.instructure.com/feeds/calendars/user_wC7Sn9BAtT2VtytLikpkf7f2hC8Pz90mqGLPXR9F.ics"


def get_db():
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
)""")

    cur.execute("""
CREATE TABLE IF NOT EXISTS completions (
    id SERIAL PRIMARY KEY,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assignment_title TEXT NOT NULL,
    class_name TEXT NOT NULL DEFAULT '',
    duration_minutes REAL NOT NULL DEFAULT 0,
    estimate_minutes REAL NOT NULL DEFAULT 0,
    timed BOOLEAN NOT NULL DEFAULT TRUE
)""")

    cur.execute("""
CREATE TABLE IF NOT EXISTS timer_state (
    id INT PRIMARY KEY DEFAULT 1,
    assignment_uid TEXT NOT NULL DEFAULT '',
    assignment_title TEXT NOT NULL DEFAULT '',
    class_name TEXT NOT NULL DEFAULT '',
    estimate_minutes REAL NOT NULL DEFAULT 30,
    started_at TIMESTAMPTZ,
    paused_at TIMESTAMPTZ,
    accumulated_seconds REAL NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT FALSE
)""")

    cur.execute("""
CREATE TABLE IF NOT EXISTS briefing_cache (
    id INT PRIMARY KEY DEFAULT 1,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    content TEXT NOT NULL DEFAULT ''
)""")

    cur.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    title TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    urgency TEXT NOT NULL DEFAULT 'low',
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    completed_at TIMESTAMPTZ,
    due_date DATE
)""")

    cur.execute("""
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    lead TEXT NOT NULL DEFAULT '',
    members TEXT NOT NULL DEFAULT '',
    last_checkin TIMESTAMPTZ,
    checkin_interval_days INT NOT NULL DEFAULT 7,
    completion_pct INT NOT NULL DEFAULT 0
)""")

    cur.execute("""
CREATE TABLE IF NOT EXISTS project_notes (
    id SERIAL PRIMARY KEY,
    project_id INT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    content TEXT NOT NULL
)""")

    defaults = {
        "name": "Finn",
        "morning_briefing_time": "07:00",
        "timer_cutoff_multiplier": "2.0",
        "anthropic_api_key": ""
    }
    for k, v in defaults.items():
        cur.execute("""
INSERT INTO config (key, value) VALUES (%s, %s)
ON CONFLICT (key) DO NOTHING""", (k, v))

    cur.execute("INSERT INTO timer_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING")
    cur.execute("INSERT INTO briefing_cache (id, content) VALUES (1, '') ON CONFLICT (id) DO NOTHING")
    conn.commit()
    cur.close()
    conn.close()
    log.info("Database initialized.")


def get_config():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM config")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def set_config(updates):
    conn = get_db()
    cur = conn.cursor()
    for k, v in updates.items():
        cur.execute("""
INSERT INTO config (key, value) VALUES (%s, %s)
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""", (k, str(v)))
    conn.commit()
    cur.close()
    conn.close()


def fetch_ical(url):
    if not url:
        return None
    # Convert webcal to https
    if url.startswith("webcal://"):
        url = "https://" + url[9:]
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return Calendar.from_ical(resp.content)
    except Exception as e:
        log.warning("iCal fetch failed for %s: %s", url, e)
        return None


def parse_canvas_assignments(cal):
    assignments = []
    now_utc = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
    cutoff = now_utc + timedelta(days=14)
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        uid = str(component.get("UID", ""))
        summary = str(component.get("SUMMARY", "Untitled"))
        description = str(component.get("DESCRIPTION", ""))
        teacher = str(component.get("ORGANIZER", ""))
        due_dt = component.get("DTSTART") or component.get("DUE")
        if due_dt is None:
            continue
        due_val = due_dt.dt
        if isinstance(due_val, date) and not isinstance(due_val, datetime):
            due_val = datetime(due_val.year, due_val.month, due_val.day, 23, 59, 0, tzinfo=ZoneInfo("UTC"))
        if due_val.tzinfo is None:
            due_val = due_val.replace(tzinfo=ZoneInfo("UTC"))
        if due_val < now_utc or due_val > cutoff:
            continue
        class_name = ""
        title = summary
        if " - " in summary:
            parts = summary.rsplit(" - ", 1)
            title = parts[0].strip()
            class_name = parts[1].strip()
        delta = due_val - now_utc
        if delta.total_seconds() < 86400:
            urgency = "high"
        elif delta.total_seconds() < 259200:
            urgency = "medium"
        else:
            urgency = "low"
        assignments.append({
            "uid": uid,
            "title": title,
            "class_name": class_name,
            "description": description[:1000],
            "teacher": teacher,
            "due_iso": due_val.astimezone(TZ).isoformat(),
            "due_display": due_val.astimezone(TZ).strftime("%a %b %-d at %-I:%M %p"),
            "urgency": urgency
        })
    assignments.sort(key=lambda x: x["due_iso"])
    return assignments


def parse_calendar_events(cal, days_ahead=30):
    events = []
    now_local = datetime.now(TZ)
    today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    range_end = today_start + timedelta(days=days_ahead)
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        summary = str(component.get("SUMMARY", "Untitled"))
        start_dt = component.get("DTSTART")
        end_dt = component.get("DTEND")
        if start_dt is None:
            continue
        start_val = start_dt.dt
        all_day = isinstance(start_val, date) and not isinstance(start_val, datetime)
        if all_day:
            start_val = datetime(start_val.year, start_val.month, start_val.day, 0, 0, 0, tzinfo=TZ)
        if start_val.tzinfo is None:
            start_val = start_val.replace(tzinfo=TZ)
        start_local = start_val.astimezone(TZ)
        if not (today_start <= start_local < range_end):
            continue
        end_local = None
        if end_dt:
            end_val = end_dt.dt
            if isinstance(end_val, date) and not isinstance(end_val, datetime):
                end_val = datetime(end_val.year, end_val.month, end_val.day, 23, 59, 0, tzinfo=TZ)
            if end_val.tzinfo is None:
                end_val = end_val.replace(tzinfo=TZ)
            end_local = end_val.astimezone(TZ)
        events.append({
            "title": summary,
            "start_display": "All Day" if all_day else start_local.strftime("%-I:%M %p"),
            "end_display": end_local.strftime("%-I:%M %p") if end_local and not all_day else "",
            "start_iso": start_local.isoformat(),
            "date": start_local.strftime("%Y-%m-%d"),
            "all_day": all_day
        })
    events.sort(key=lambda x: x["start_iso"])
    return events


KEYWORD_ESTIMATES = {
    "essay": 45, "paper": 45, "write": 45, "writing": 45,
    "worksheet": 30, "problems": 30, "exercises": 30,
    "reading": 25, "read": 25, "chapter": 25,
    "vocab": 15, "vocabulary": 15, "flashcard": 15,
    "quiz": 20, "test": 20
}


def get_class_average(class_name):
    if not class_name:
        return None
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
SELECT AVG(duration_minutes) as avg FROM (
    SELECT duration_minutes FROM completions
    WHERE class_name = %s AND timed = TRUE AND duration_minutes > 0
    ORDER BY completed_at DESC LIMIT 20
) sub""", (class_name,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row and row["avg"] is not None:
        return round(float(row["avg"]), 1)
    return None


def estimate_assignment(title, class_name):
    avg = get_class_average(class_name)
    if avg:
        return avg
    title_lower = title.lower()
    for kw, mins in KEYWORD_ESTIMATES.items():
        if kw in title_lower:
            return float(mins)
    return 30.0


def generate_briefing(force=False):
    with _briefing_lock:
        cfg = get_config()
        api_key = cfg.get("anthropic_api_key", "")
        if not api_key:
            return
        name = cfg.get("name", "Finn")
        if not force:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT generated_at FROM briefing_cache WHERE id = 1")
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row and row["generated_at"]:
                age = datetime.now(TZ) - row["generated_at"].astimezone(TZ)
                if age.total_seconds() < 3600:
                    return

        assignments = []
        cal = fetch_ical(CANVAS_ICAL_URL)
        if cal:
            assignments = parse_canvas_assignments(cal)

        events = []
        cal2 = fetch_ical(PERSONAL_ICAL_URL)
        if cal2:
            events = [e for e in parse_calendar_events(cal2, days_ahead=1)]

        # Get tasks
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT title, urgency FROM tasks WHERE completed = FALSE ORDER BY urgency DESC, created_at ASC LIMIT 5")
        tasks = [dict(r) for r in cur.fetchall()]

        # Get stale projects
        cur.execute("""
SELECT title, last_checkin, checkin_interval_days FROM projects
WHERE status = 'active' AND (last_checkin IS NULL OR
    NOW() - last_checkin > make_interval(days => checkin_interval_days))
LIMIT 3""")
        stale_projects = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()

        now_str = datetime.now(TZ).strftime("%A, %B %-d, %Y at %-I:%M %p")

        today_asgn = [a for a in assignments if a["urgency"] == "high"][:5]
        asgn_text = "\n".join(["- %s (%s) due %s, est. %d min" % (
            a["title"], a["class_name"], a["due_display"],
            estimate_assignment(a["title"], a["class_name"])
        ) for a in today_asgn]) or "No urgent assignments."

        events_text = "\n".join(["- %s at %s" % (e["title"], e["start_display"]) for e in events]) or "No events today."
        tasks_text = "\n".join(["- [%s] %s" % (t["urgency"], t["title"]) for t in tasks]) or "No pending tasks."
        stale_text = "\n".join(["- %s (overdue check-in)" % p["title"] for p in stale_projects]) or ""

        prompt = (
            "You are a sharp, efficient personal assistant for a high school student named %s who is also a "
            "student leader managing projects and working toward a future in politics. "
            "Write a concise, action-oriented daily briefing (4-6 sentences). "
            "Cover: most urgent assignments with estimated time, today's schedule, any urgent tasks, "
            "and if there are stale projects mention them briefly. "
            "Be warm but direct. No bullet points. Sound like a capable chief of staff briefing a busy person. "
            "Current time: %s\n\nUrgent Assignments:\n%s\n\nToday's schedule:\n%s\n\nPending Tasks:\n%s\n\nProjects needing check-in:\n%s"
        ) % (name, now_str, asgn_text, events_text, tasks_text, stale_text)

        try:
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}]
            )
            content = message.content[0].text if message.content else "Have a great day!"
        except Exception as e:
            log.error("Anthropic API error: %s", e)
            content = "Could not generate briefing. Check your API key in Settings."

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
INSERT INTO briefing_cache (id, generated_at, content) VALUES (1, NOW(), %s)
ON CONFLICT (id) DO UPDATE SET generated_at = NOW(), content = EXCLUDED.content""", (content,))
        conn.commit()
        cur.close()
        conn.close()


scheduler = BackgroundScheduler(timezone=TZ)


def schedule_briefing():
    cfg = get_config()
    t = cfg.get("morning_briefing_time", "07:00")
    try:
        hour, minute = int(t.split(":")[0]), int(t.split(":")[1])
    except Exception:
        hour, minute = 7, 0
    scheduler.remove_all_jobs()
    scheduler.add_job(generate_briefing, "cron", hour=hour, minute=minute,
                      id="morning_briefing", replace_existing=True)
    log.info("Briefing scheduled for %02d:%02d Mountain", hour, minute)


def get_timer_state_row():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM timer_state WHERE id = 1")
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else {}


def get_timer_elapsed(row):
    accumulated = float(row.get("accumulated_seconds") or 0)
    if row.get("active") and row.get("started_at") and not row.get("paused_at"):
        started = row["started_at"]
        if started.tzinfo is None:
            started = started.replace(tzinfo=ZoneInfo("UTC"))
        delta = datetime.now(ZoneInfo("UTC")) - started
        accumulated += delta.total_seconds()
    return accumulated


def timer_response(row):
    elapsed = get_timer_elapsed(row)
    elapsed_min = elapsed / 60.0
    estimate = float(row.get("estimate_minutes") or 30)
    cfg = get_config()
    try:
        multiplier = float(cfg.get("timer_cutoff_multiplier", "2.0"))
    except Exception:
        multiplier = 2.0
    cutoff_min = estimate * multiplier
    return {
        "active": bool(row.get("active")),
        "paused": bool(row.get("paused_at")),
        "assignment_uid": row.get("assignment_uid", ""),
        "assignment_title": row.get("assignment_title", ""),
        "class_name": row.get("class_name", ""),
        "estimate_minutes": estimate,
        "elapsed_minutes": round(elapsed_min, 2),
        "cutoff_minutes": round(cutoff_min, 2),
        "over_estimate": elapsed_min > estimate,
        "over_cutoff": elapsed_min > cutoff_min
    }


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/assignments")
def api_assignments():
    try:
        cal = fetch_ical(CANVAS_ICAL_URL)
        if cal is None:
            return jsonify({"assignments": [], "error": "Failed to fetch Canvas calendar."})
        conn = get_db()
        cur = conn.cursor()
        today_start = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        cur.execute("SELECT assignment_title FROM completions WHERE completed_at >= %s", (today_start,))
        completed_titles = set(r["assignment_title"] for r in cur.fetchall())
        cur.close()
        conn.close()
        assignments = parse_canvas_assignments(cal)
        result = []
        for a in assignments:
            if a["title"] in completed_titles:
                continue
            a["estimate_minutes"] = estimate_assignment(a["title"], a["class_name"])
            result.append(a)
        return jsonify({"assignments": result})
    except Exception:
        log.exception("/api/assignments failed")
        return jsonify({"assignments": [], "error": "Internal server error fetching assignments."}), 500


@app.route("/api/calendar")
def api_calendar():
    days = int(request.args.get("days", 30))
    events = []
    # Personal calendar
    cal = fetch_ical(PERSONAL_ICAL_URL)
    if cal:
        for e in parse_calendar_events(cal, days_ahead=days):
            e["source"] = "personal"
            events.append(e)
    # Canvas assignments as calendar events
    cal2 = fetch_ical(CANVAS_ICAL_URL)
    if cal2:
        for a in parse_canvas_assignments(cal2):
            events.append({
                "title": a["title"] + " (due)",
                "start_display": a["due_display"],
                "end_display": "",
                "start_iso": a["due_iso"],
                "date": a["due_iso"][:10],
                "all_day": False,
                "source": "canvas",
                "urgency": a["urgency"],
                "class_name": a["class_name"]
            })
    events.sort(key=lambda x: x["start_iso"])
    return jsonify({"events": events})


@app.route("/api/briefing")
def api_briefing():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT content, generated_at FROM briefing_cache WHERE id = 1")
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row and row["content"]:
        return jsonify({
            "briefing": row["content"],
            "generated_at": row["generated_at"].isoformat() if row["generated_at"] else None
        })
    return jsonify({"briefing": "Generating your briefing...", "generated_at": None})


@app.route("/api/briefing/refresh", methods=["POST"])
def api_briefing_refresh():
    threading.Thread(target=generate_briefing, kwargs={"force": True}, daemon=True).start()
    return jsonify({"status": "refreshing"})


@app.route("/api/timer", methods=["GET"])
def api_timer_get():
    return jsonify(timer_response(get_timer_state_row()))


@app.route("/api/timer/start", methods=["POST"])
def api_timer_start():
    data = request.get_json(force=True) or {}
    uid = str(data.get("uid", ""))
    title = str(data.get("title", ""))
    class_name = str(data.get("class_name", ""))
    estimate = float(data.get("estimate_minutes", 30))
    with _timer_lock:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
UPDATE timer_state SET assignment_uid=%s, assignment_title=%s, class_name=%s,
estimate_minutes=%s, started_at=NOW(), paused_at=NULL, accumulated_seconds=0, active=TRUE WHERE id=1""",
                    (uid, title, class_name, estimate))
        conn.commit()
        cur.close()
        conn.close()
    return jsonify(timer_response(get_timer_state_row()))


@app.route("/api/timer/pause", methods=["POST"])
def api_timer_pause():
    with _timer_lock:
        row = get_timer_state_row()
        if not row.get("active") or row.get("paused_at"):
            return jsonify(timer_response(row))
        elapsed = get_timer_elapsed(row)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE timer_state SET paused_at=NOW(), accumulated_seconds=%s WHERE id=1", (elapsed,))
        conn.commit()
        cur.close()
        conn.close()
    return jsonify(timer_response(get_timer_state_row()))


@app.route("/api/timer/resume", methods=["POST"])
def api_timer_resume():
    with _timer_lock:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE timer_state SET started_at=NOW(), paused_at=NULL WHERE id=1")
        conn.commit()
        cur.close()
        conn.close()
    return jsonify(timer_response(get_timer_state_row()))


@app.route("/api/timer/stop", methods=["POST"])
def api_timer_stop():
    data = request.get_json(force=True) or {}
    save = bool(data.get("save", True))
    with _timer_lock:
        row = get_timer_state_row()
        elapsed = get_timer_elapsed(row)
        elapsed_min = elapsed / 60.0
        if save and row.get("assignment_title") and elapsed_min > 0.5:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
INSERT INTO completions (assignment_title, class_name, duration_minutes, estimate_minutes, timed)
VALUES (%s, %s, %s, %s, TRUE)""",
                        (row["assignment_title"], row.get("class_name", ""),
                         round(elapsed_min, 2), float(row.get("estimate_minutes") or 30)))
            conn.commit()
            cur.close()
            conn.close()
        conn2 = get_db()
        cur2 = conn2.cursor()
        cur2.execute("""
UPDATE timer_state SET active=FALSE, paused_at=NULL, started_at=NULL,
accumulated_seconds=0, assignment_uid='', assignment_title='', class_name='' WHERE id=1""")
        conn2.commit()
        cur2.close()
        conn2.close()
    return jsonify({"saved": save, "elapsed_minutes": round(elapsed_min, 2)})


@app.route("/api/complete", methods=["POST"])
def api_complete():
    data = request.get_json(force=True) or {}
    title = str(data.get("title", ""))[:300]
    class_name = str(data.get("class_name", ""))[:100]
    estimate = float(data.get("estimate_minutes", 30))
    if not title:
        return jsonify({"error": "title required"}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
INSERT INTO completions (assignment_title, class_name, duration_minutes, estimate_minutes, timed)
VALUES (%s, %s, 0, %s, FALSE)""", (title, class_name, estimate))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/completions/today")
def api_completions_today():
    today_start = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
SELECT assignment_title, class_name, duration_minutes, estimate_minutes, timed, completed_at
FROM completions WHERE completed_at >= %s ORDER BY completed_at DESC""", (today_start,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    for r in rows:
        r["completed_at"] = r["completed_at"].isoformat()
    return jsonify({"completions": rows})


@app.route("/api/stats")
def api_stats():
    conn = get_db()
    cur = conn.cursor()
    week_start = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    week_start -= timedelta(days=week_start.weekday())
    cur.execute("SELECT SUM(duration_minutes) as total FROM completions WHERE completed_at >= %s AND timed=TRUE", (week_start,))
    week_row = cur.fetchone()
    weekly_minutes = float(week_row["total"] or 0)
    cur.execute("""
SELECT class_name, AVG(duration_minutes) as avg, COUNT(*) as cnt
FROM completions WHERE timed=TRUE AND duration_minutes>0 AND class_name!=''
GROUP BY class_name ORDER BY avg DESC LIMIT 10""")
    by_class = [{"class_name": r["class_name"], "avg_minutes": round(float(r["avg"]), 1), "count": r["cnt"]} for r in cur.fetchall()]
    cur.execute("""
SELECT AVG(ABS(duration_minutes - estimate_minutes) / NULLIF(estimate_minutes, 0)) as err
FROM completions WHERE timed=TRUE AND estimate_minutes>0 AND duration_minutes>0""")
    acc_row = cur.fetchone()
    accuracy_pct = None
    if acc_row and acc_row["err"] is not None:
        accuracy_pct = round((1.0 - min(float(acc_row["err"]), 1.0)) * 100, 1)
    cur.execute("""
SELECT DISTINCT DATE(completed_at AT TIME ZONE 'America/Denver') as day
FROM completions ORDER BY day DESC LIMIT 30""")
    streak_days = [r["day"] for r in cur.fetchall()]
    streak = 0
    check = date.today()
    for d in streak_days:
        if d == check:
            streak += 1
            check -= timedelta(days=1)
        elif d == check - timedelta(days=1):
            check -= timedelta(days=1)
        else:
            break
    cur.close()
    conn.close()
    return jsonify({"weekly_minutes": round(weekly_minutes, 1), "by_class": by_class,
                    "estimate_accuracy_pct": accuracy_pct, "streak_days": streak})


# ── Tasks ────────────────────────────────────────────────────────────────────

@app.route("/api/tasks", methods=["GET"])
def api_tasks_get():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
SELECT id, title, notes, urgency, completed, completed_at, due_date, created_at
FROM tasks ORDER BY completed ASC, 
    CASE urgency WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END ASC,
    created_at ASC""")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    for r in rows:
        if r["completed_at"]:
            r["completed_at"] = r["completed_at"].isoformat()
        if r["due_date"]:
            r["due_date"] = str(r["due_date"])
        r["created_at"] = r["created_at"].isoformat()
    return jsonify({"tasks": rows})


@app.route("/api/tasks", methods=["POST"])
def api_tasks_create():
    data = request.get_json(force=True) or {}
    title = str(data.get("title", "")).strip()[:300]
    if not title:
        return jsonify({"error": "title required"}), 400
    notes = str(data.get("notes", ""))[:2000]
    urgency = str(data.get("urgency", "low"))
    due_date = data.get("due_date") or None
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
INSERT INTO tasks (title, notes, urgency, due_date) VALUES (%s, %s, %s, %s) RETURNING id""",
                (title, notes, urgency, due_date))
    new_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"id": new_id, "status": "ok"})


@app.route("/api/tasks/<int:task_id>", methods=["PATCH"])
def api_tasks_update(task_id):
    data = request.get_json(force=True) or {}
    conn = get_db()
    cur = conn.cursor()
    if "completed" in data:
        completed = bool(data["completed"])
        cur.execute("""
UPDATE tasks SET completed=%s, completed_at=%s WHERE id=%s""",
                    (completed, datetime.now(TZ) if completed else None, task_id))
    if "title" in data:
        cur.execute("UPDATE tasks SET title=%s WHERE id=%s", (str(data["title"])[:300], task_id))
    if "urgency" in data:
        cur.execute("UPDATE tasks SET urgency=%s WHERE id=%s", (str(data["urgency"]), task_id))
    if "notes" in data:
        cur.execute("UPDATE tasks SET notes=%s WHERE id=%s", (str(data["notes"])[:2000], task_id))
    if "due_date" in data:
        cur.execute("UPDATE tasks SET due_date=%s WHERE id=%s", (data["due_date"] or None, task_id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def api_tasks_delete(task_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id=%s", (task_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})


# ── Projects ─────────────────────────────────────────────────────────────────

@app.route("/api/projects", methods=["GET"])
def api_projects_get():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
SELECT id, title, description, status, lead, members, last_checkin,
       checkin_interval_days, completion_pct, created_at,
       CASE WHEN last_checkin IS NULL OR
           NOW() - last_checkin > make_interval(days => checkin_interval_days)
       THEN TRUE ELSE FALSE END as needs_checkin
FROM projects ORDER BY status ASC, created_at DESC""")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    for r in rows:
        if r["last_checkin"]:
            r["last_checkin"] = r["last_checkin"].isoformat()
        r["created_at"] = r["created_at"].isoformat()
    return jsonify({"projects": rows})


@app.route("/api/projects", methods=["POST"])
def api_projects_create():
    data = request.get_json(force=True) or {}
    title = str(data.get("title", "")).strip()[:300]
    if not title:
        return jsonify({"error": "title required"}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
INSERT INTO projects (title, description, status, lead, members, checkin_interval_days, completion_pct)
VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (title, str(data.get("description", ""))[:2000],
                 str(data.get("status", "active")),
                 str(data.get("lead", ""))[:200],
                 str(data.get("members", ""))[:500],
                 int(data.get("checkin_interval_days", 7)),
                 int(data.get("completion_pct", 0))))
    new_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"id": new_id, "status": "ok"})


@app.route("/api/projects/<int:project_id>", methods=["PATCH"])
def api_projects_update(project_id):
    data = request.get_json(force=True) or {}
    conn = get_db()
    cur = conn.cursor()
    fields = ["title", "description", "status", "lead", "members",
              "checkin_interval_days", "completion_pct"]
    for f in fields:
        if f in data:
            cur.execute("UPDATE projects SET %s=%%s WHERE id=%%s" % f, (data[f], project_id))
    if data.get("checkin_now"):
        cur.execute("UPDATE projects SET last_checkin=NOW() WHERE id=%s", (project_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/projects/<int:project_id>", methods=["DELETE"])
def api_projects_delete(project_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM projects WHERE id=%s", (project_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/projects/<int:project_id>/notes", methods=["GET"])
def api_project_notes_get(project_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, content, created_at FROM project_notes WHERE project_id=%s ORDER BY created_at DESC", (project_id,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    for r in rows:
        r["created_at"] = r["created_at"].isoformat()
    return jsonify({"notes": rows})


@app.route("/api/projects/<int:project_id>/notes", methods=["POST"])
def api_project_notes_create(project_id):
    data = request.get_json(force=True) or {}
    content = str(data.get("content", "")).strip()
    if not content:
        return jsonify({"error": "content required"}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO project_notes (project_id, content) VALUES (%s, %s) RETURNING id",
                (project_id, content))
    new_id = cur.fetchone()["id"]
    # Also update last_checkin
    cur.execute("UPDATE projects SET last_checkin=NOW() WHERE id=%s", (project_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"id": new_id, "status": "ok"})


@app.route("/api/projects/<int:project_id>/notes/<int:note_id>", methods=["DELETE"])
def api_project_notes_delete(project_id, note_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM project_notes WHERE id=%s AND project_id=%s", (note_id, project_id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/config", methods=["GET"])
def api_config_get():
    cfg = get_config()
    return jsonify({
        "name": cfg.get("name", "Finn"),
        "morning_briefing_time": cfg.get("morning_briefing_time", "07:00"),
        "timer_cutoff_multiplier": cfg.get("timer_cutoff_multiplier", "2.0"),
        "has_api_key": bool(cfg.get("anthropic_api_key", ""))
    })


@app.route("/api/config", methods=["POST"])
def api_config_post():
    data = request.get_json(force=True) or {}
    allowed = {"name", "morning_briefing_time", "timer_cutoff_multiplier", "anthropic_api_key"}
    updates = {k: str(v)[:2000] for k, v in data.items() if k in allowed}
    if updates:
        set_config(updates)
        if "morning_briefing_time" in updates:
            schedule_briefing()
    return jsonify({"status": "ok"})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True) or {}
    system_prompt = data.get("system", "")
    messages = data.get("messages", [])
    api_key = os.environ.get("ANTHROPIC_API_KEY", "") or get_config().get("anthropic_api_key", "")
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not configured. Add it in Settings."}), 500
    try:
        # Inject live assignments into the system prompt
        try:
            cal = fetch_ical(CANVAS_ICAL_URL)
            if cal:
                asgn_list = parse_canvas_assignments(cal)
                if asgn_list:
                    asgn_text = "; ".join(
                        "%s (%s, due %s)" % (a["title"], a["class_name"], a["due_display"])
                        for a in asgn_list
                    )
                    system_prompt += " Upcoming assignments: " + asgn_text + "."
        except Exception:
            log.warning("/api/chat could not fetch assignments for context")

        # Inject pending tasks into the system prompt
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "SELECT title, urgency FROM tasks WHERE completed = FALSE "
                "ORDER BY urgency DESC, created_at ASC LIMIT 10"
            )
            tasks = [dict(r) for r in cur.fetchall()]
            cur.close()
            conn.close()
            if tasks:
                tasks_text = "; ".join(
                    "[%s] %s" % (t["urgency"], t["title"]) for t in tasks
                )
                system_prompt += " Pending tasks: " + tasks_text + "."
        except Exception:
            log.warning("/api/chat could not fetch tasks for context")

        client = anthropic.Anthropic(api_key=api_key)
        kwargs = {"model": "claude-sonnet-4-6", "max_tokens": 1024, "messages": messages}
        if system_prompt:
            kwargs["system"] = system_prompt
        message = client.messages.create(**kwargs)
        content = message.content[0].text if message.content else ""
        return jsonify({"content": content})
    except Exception:
        log.exception("/api/chat failed")
        return jsonify({"error": "Failed to reach AI. Check server logs."}), 500


init_db()
schedule_briefing()
scheduler.start()
threading.Thread(target=generate_briefing, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
