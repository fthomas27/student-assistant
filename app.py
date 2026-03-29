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
)
""")
    cur.execute("""
CREATE TABLE IF NOT EXISTS completions (
id SERIAL PRIMARY KEY,
completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
assignment_title TEXT NOT NULL,
class_name TEXT NOT NULL DEFAULT '',
duration_minutes REAL NOT NULL DEFAULT 0,
estimate_minutes REAL NOT NULL DEFAULT 0,
timed BOOLEAN NOT NULL DEFAULT TRUE
)
""")
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
)
""")
    cur.execute("""
CREATE TABLE IF NOT EXISTS briefing_cache (
id INT PRIMARY KEY DEFAULT 1,
generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
content TEXT NOT NULL DEFAULT ''
)
""")
    defaults = {
        "name": "Finn",
        "morning_briefing_time": "07:00",
        "timer_cutoff_multiplier": "2.0",
        "canvas_ical_url": "",
        "apple_ical_url": "",
        "anthropic_api_key": ""
    }
    for k, v in defaults.items():
        cur.execute("""
INSERT INTO config (key, value) VALUES (%s, %s)
ON CONFLICT (key) DO NOTHING
""", (k, v))
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
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
""", (k, str(v)))
    conn.commit()
    cur.close()
    conn.close()


def fetch_ical(url):
    if not url:
        return None
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
            "description": description[:500],
            "due_iso": due_val.astimezone(TZ).isoformat(),
            "due_display": due_val.astimezone(TZ).strftime("%a %b %-d at %-I:%M %p"),
            "urgency": urgency
        })
    assignments.sort(key=lambda x: x["due_iso"])
    return assignments


def parse_calendar_events(cal):
    events = []
    now_local = datetime.now(TZ)
    today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        summary = str(component.get("SUMMARY", "Untitled"))
        start_dt = component.get("DTSTART")
        end_dt = component.get("DTEND")
        if start_dt is None:
            continue
        start_val = start_dt.dt
        if isinstance(start_val, date) and not isinstance(start_val, datetime):
            start_val = datetime(start_val.year, start_val.month, start_val.day, 0, 0, 0, tzinfo=TZ)
        if start_val.tzinfo is None:
            start_val = start_val.replace(tzinfo=TZ)
        start_local = start_val.astimezone(TZ)
        if not (today_start <= start_local < today_end):
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
            "start_display": start_local.strftime("%-I:%M %p"),
            "end_display": end_local.strftime("%-I:%M %p") if end_local else "",
            "start_iso": start_local.isoformat()
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
SELECT AVG(duration_minutes) as avg
FROM completions
WHERE class_name = %s AND timed = TRUE AND duration_minutes > 0
ORDER BY completed_at DESC
LIMIT 20
""", (class_name,))
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
        canvas_url = cfg.get("canvas_ical_url", "")
        apple_url = cfg.get("apple_ical_url", "")
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
        if canvas_url:
            cal = fetch_ical(canvas_url)
            if cal:
                assignments = parse_canvas_assignments(cal)
        events = []
        if apple_url:
            cal = fetch_ical(apple_url)
            if cal:
                events = parse_calendar_events(cal)
        now_str = datetime.now(TZ).strftime("%A, %B %-d, %Y at %-I:%M %p")
        if assignments:
            lines = []
            for a in assignments[:10]:
                lines.append("- %s (%s) due %s [%s]" % (a["title"], a["class_name"], a["due_display"], a["urgency"]))
            asgn_text = "\n".join(lines)
        else:
            asgn_text = "No upcoming assignments."
        if events:
            lines = []
            for e in events:
                lines.append("- %s at %s" % (e["title"], e["start_display"]))
            events_text = "\n".join(lines)
        else:
            events_text = "No events today."
        prompt = (
            "You are a smart, friendly daily assistant for a high school student named %s. "
            "Write a concise morning briefing (3-5 sentences max). "
            "Mention the most urgent assignments, any calendar events, and give one short motivating tip. "
            "Be warm but brief. Do not use bullet points in your response. "
            "Current time: %s\n\nAssignments:\n%s\n\nToday's schedule:\n%s"
        ) % (name, now_str, asgn_text, events_text)
        try:
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            content = message.content[0].text if message.content else "Have a great day!"
        except Exception as e:
            log.error("Anthropic API error: %s", e)
            content = "Could not generate briefing. Check your API key in Settings."
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
INSERT INTO briefing_cache (id, generated_at, content)
VALUES (1, NOW(), %s)
ON CONFLICT (id) DO UPDATE SET generated_at = NOW(), content = EXCLUDED.content
""", (content,))
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


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/assignments")
def api_assignments():
    cfg = get_config()
    url = cfg.get("canvas_ical_url", "")
    if not url:
        return jsonify({"assignments": [], "error": "Canvas iCal URL not configured."})
    cal = fetch_ical(url)
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


@app.route("/api/calendar")
def api_calendar():
    cfg = get_config()
    url = cfg.get("apple_ical_url", "")
    if not url:
        return jsonify({"events": [], "error": "Apple Calendar iCal URL not configured."})
    cal = fetch_ical(url)
    if cal is None:
        return jsonify({"events": [], "error": "Failed to fetch Apple Calendar."})
    return jsonify({"events": parse_calendar_events(cal)})


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
    row = get_timer_state_row()
    return jsonify(timer_response(row))


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
UPDATE timer_state SET
assignment_uid = %s, assignment_title = %s, class_name = %s,
estimate_minutes = %s, started_at = NOW(), paused_at = NULL,
accumulated_seconds = 0, active = TRUE
WHERE id = 1
""", (uid, title, class_name, estimate))
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
        cur.execute("UPDATE timer_state SET paused_at = NOW(), accumulated_seconds = %s WHERE id = 1", (elapsed,))
        conn.commit()
        cur.close()
        conn.close()
    return jsonify(timer_response(get_timer_state_row()))


@app.route("/api/timer/resume", methods=["POST"])
def api_timer_resume():
    with _timer_lock:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE timer_state SET started_at = NOW(), paused_at = NULL WHERE id = 1")
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
VALUES (%s, %s, %s, %s, TRUE)
""", (row["assignment_title"], row.get("class_name", ""), round(elapsed_min, 2), float(row.get("estimate_minutes") or 30)))
            conn.commit()
            cur.close()
            conn.close()
        conn2 = get_db()
        cur2 = conn2.cursor()
        cur2.execute("""
UPDATE timer_state SET active = FALSE, paused_at = NULL, started_at = NULL,
accumulated_seconds = 0, assignment_uid = '', assignment_title = '', class_name = ''
WHERE id = 1
""")
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
VALUES (%s, %s, 0, %s, FALSE)
""", (title, class_name, estimate))
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
FROM completions WHERE completed_at >= %s ORDER BY completed_at DESC
""", (today_start,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    for r in rows:
        r["completed_at"] = r["completed_at"].isoformat()
    return jsonify({"completions": rows})


@app.route("/api/completions/week")
def api_completions_week():
    week_start = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    week_start -= timedelta(days=week_start.weekday())
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
SELECT assignment_title, class_name, duration_minutes, estimate_minutes, timed, completed_at
FROM completions WHERE completed_at >= %s ORDER BY completed_at DESC
""", (week_start,))
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
    cur.execute("SELECT SUM(duration_minutes) as total FROM completions WHERE completed_at >= %s AND timed = TRUE", (week_start,))
    week_row = cur.fetchone()
    weekly_minutes = float(week_row["total"] or 0)
    cur.execute("""
SELECT class_name, AVG(duration_minutes) as avg, COUNT(*) as cnt
FROM completions
WHERE timed = TRUE AND duration_minutes > 0 AND class_name != ''
GROUP BY class_name ORDER BY avg DESC LIMIT 10
""")
    by_class = [{"class_name": r["class_name"], "avg_minutes": round(float(r["avg"]), 1), "count": r["cnt"]} for r in cur.fetchall()]
    cur.execute("""
SELECT AVG(ABS(duration_minutes - estimate_minutes) / NULLIF(estimate_minutes, 0)) as err
FROM completions WHERE timed = TRUE AND estimate_minutes > 0 AND duration_minutes > 0
""")
    acc_row = cur.fetchone()
    accuracy_pct = None
    if acc_row and acc_row["err"] is not None:
        accuracy_pct = round((1.0 - min(float(acc_row["err"]), 1.0)) * 100, 1)
    cur.execute("""
SELECT DISTINCT DATE(completed_at AT TIME ZONE 'America/Denver') as day
FROM completions ORDER BY day DESC LIMIT 30
""")
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
    return jsonify({"weekly_minutes": round(weekly_minutes, 1), "by_class": by_class, "estimate_accuracy_pct": accuracy_pct, "streak_days": streak})


@app.route("/api/config", methods=["GET"])
def api_config_get():
    cfg = get_config()
    safe = {k: v for k, v in cfg.items() if k != "anthropic_api_key"}
    safe["has_api_key"] = bool(cfg.get("anthropic_api_key", ""))
    return jsonify(safe)


@app.route("/api/config", methods=["POST"])
def api_config_post():
    data = request.get_json(force=True) or {}
    allowed = {"name", "morning_briefing_time", "timer_cutoff_multiplier", "canvas_ical_url", "apple_ical_url", "anthropic_api_key"}
    updates = {k: str(v)[:2000] for k, v in data.items() if k in allowed}
    if updates:
        set_config(updates)
        if "morning_briefing_time" in updates:
            schedule_briefing()
    return jsonify({"status": "ok"})


init_db()
schedule_briefing()
scheduler.start()
threading.Thread(target=generate_briefing, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
