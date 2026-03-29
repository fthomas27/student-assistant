import os
import time
import uuid
import datetime
import threading
import requests
import psycopg2
import psycopg2.extras
from flask import Flask, jsonify, request, render_template
from icalendar import Calendar
from anthropic import Anthropic
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

app = Flask(**name**)

DATABASE_URL = os.environ.get(“DATABASE_URL”, “”)

def get_db():
conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
return conn

def init_db():
conn = get_db()
cur  = conn.cursor()
cur.execute(”””
CREATE TABLE IF NOT EXISTS config (
key   TEXT PRIMARY KEY,
value TEXT
)
“””)
cur.execute(”””
CREATE TABLE IF NOT EXISTS completions (
id               TEXT PRIMARY KEY,
assignment_id    TEXT,
assignment_name  TEXT,
class_name       TEXT,
duration_minutes INTEGER,
estimate_minutes INTEGER,
completed_at     TIMESTAMPTZ DEFAULT NOW(),
timed            BOOLEAN DEFAULT FALSE
)
“””)
cur.execute(”””
CREATE TABLE IF NOT EXISTS timer_state (
id               TEXT PRIMARY KEY DEFAULT ‘current’,
assignment_id    TEXT,
assignment_name  TEXT,
class_name       TEXT,
estimate_minutes INTEGER,
elapsed_seconds  REAL DEFAULT 0,
paused           BOOLEAN DEFAULT FALSE,
resumed_at       REAL,
started_at       TIMESTAMPTZ DEFAULT NOW()
)
“””)
cur.execute(”””
CREATE TABLE IF NOT EXISTS briefing_cache (
id           TEXT PRIMARY KEY DEFAULT ‘current’,
briefing     TEXT DEFAULT ‘’,
generated_at TIMESTAMPTZ DEFAULT NOW()
)
“””)
defaults = {
“name”:                    “Finn”,
“morning_briefing_time”:   “07:00”,
“timer_cutoff_multiplier”: “2.0”,
“canvas_ical_url”:         “”,
“apple_ical_url”:          “”,
“anthropic_api_key”:       “”,
}
for k, v in defaults.items():
cur.execute(”””
INSERT INTO config (key, value) VALUES (%s, %s)
ON CONFLICT (key) DO NOTHING
“””, (k, v))
conn.commit()
cur.close()
conn.close()

def get_config():
conn = get_db()
cur  = conn.cursor()
cur.execute(“SELECT key, value FROM config”)
rows = cur.fetchall()
cur.close(); conn.close()
return {r[“key”]: r[“value”] for r in rows}

def set_config(updates):
conn = get_db()
cur  = conn.cursor()
for k, v in updates.items():
cur.execute(”””
INSERT INTO config (key, value) VALUES (%s, %s)
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
“””, (k, str(v)))
conn.commit()
cur.close(); conn.close()

def fetch_ical(url):
try:
r = requests.get(url, timeout=10)
r.raise_for_status()
return Calendar.from_ical(r.content)
except Exception as e:
print(f”iCal error: {e}”)
return None

def to_aware_dt(dt_val):
if isinstance(dt_val, datetime.datetime):
if dt_val.tzinfo is None:
return pytz.UTC.localize(dt_val)
return dt_val
if isinstance(dt_val, datetime.date):
return datetime.datetime.combine(dt_val, datetime.time(23, 59), tzinfo=pytz.UTC)
return None

def format_due(due_dt, now):
days = (due_dt - now).days
if days < 0:  return “Overdue”
if days == 0: return “Due today”
if days == 1: return “Due tomorrow”
return f”Due in {days} days”

def urgency_level(due_dt, now):
hours = (due_dt - now).total_seconds() / 3600
if hours < 24:  return “high”
if hours < 72:  return “medium”
return “low”

def get_estimate(class_name, assignment_name, description):
conn = get_db()
cur  = conn.cursor()
cur.execute(”””
SELECT AVG(duration_minutes) as avg FROM completions
WHERE class_name = %s AND timed = TRUE AND duration_minutes IS NOT NULL
“””, (class_name,))
row = cur.fetchone()
cur.close(); conn.close()
if row and row[“avg”]:
return round(row[“avg”])
text = (description + “ “ + assignment_name).lower()
if any(w in text for w in [“essay”,“paper”,“write”,“paragraph”,“response”]): return 45
if any(w in text for w in [“worksheet”,“problems”,“questions”,“quiz”,“test”]):  return 30
if any(w in text for w in [“read”,“reading”,“chapter”,“pages”]):               return 25
if any(w in text for w in [“vocab”,“vocabulary”,“flashcard”,“define”]):        return 15
return 30

def get_done_ids():
conn = get_db()
cur  = conn.cursor()
cur.execute(“SELECT assignment_id FROM completions WHERE assignment_id IS NOT NULL”)
rows = cur.fetchall()
cur.close(); conn.close()
return set(r[“assignment_id”] for r in rows)

def get_assignments():
cfg = get_config()
url = cfg.get(“canvas_ical_url”, “”)
if not url: return []
cal = fetch_ical(url)
if not cal: return []
now      = datetime.datetime.now(pytz.UTC)
done_ids = get_done_ids()
results  = []
for comp in cal.walk():
if comp.name != “VEVENT”: continue
raw_due = comp.get(“DTEND”) or comp.get(“DTSTART”)
if not raw_due: continue
due_dt = to_aware_dt(raw_due.dt)
if not due_dt: continue
if due_dt < now - datetime.timedelta(days=1): continue
if due_dt > now + datetime.timedelta(weeks=2): continue
uid         = str(comp.get(“UID”, “”))
summary     = str(comp.get(“SUMMARY”, “Assignment”))
description = str(comp.get(“DESCRIPTION”, “”))
if uid in done_ids: continue
class_name      = “General”
assignment_name = summary
if “ - “ in summary:
parts           = summary.split(” - “, 1)
assignment_name = parts[0].strip()
class_name      = parts[1].strip()
estimate = get_estimate(class_name, assignment_name, description)
results.append({
“id”:               uid or summary,
“name”:             assignment_name,
“class_name”:       class_name,
“due”:              due_dt.isoformat(),
“due_friendly”:     format_due(due_dt, now),
“description”:      description[:600],
“estimate_minutes”: estimate,
“urgency”:          urgency_level(due_dt, now),
})
results.sort(key=lambda x: x[“due”])
return results

LOCAL_TZ = pytz.timezone(“America/Denver”)

def get_calendar_events():
cfg = get_config()
url = cfg.get(“apple_ical_url”, “”)
if not url: return []
cal = fetch_ical(url)
if not cal: return []
now         = datetime.datetime.now(pytz.UTC)
today_start = now.replace(hour=0,  minute=0,  second=0,  microsecond=0)
today_end   = now.replace(hour=23, minute=59, second=59, microsecond=0)
events      = []
for comp in cal.walk():
if comp.name != “VEVENT”: continue
raw_start = comp.get(“DTSTART”)
if not raw_start: continue
start_dt = to_aware_dt(raw_start.dt)
if not start_dt or start_dt < today_start or start_dt > today_end: continue
raw_end = comp.get(“DTEND”)
end_dt  = to_aware_dt(raw_end.dt) if raw_end else None
start_l = start_dt.astimezone(LOCAL_TZ)
event   = {
“name”:           str(comp.get(“SUMMARY”, “Event”)),
“start”:          start_dt.isoformat(),
“start_friendly”: start_l.strftime(”%-I:%M %p”),
}
if end_dt:
end_l = end_dt.astimezone(LOCAL_TZ)
event[“end_friendly”]     = end_l.strftime(”%-I:%M %p”)
event[“duration_minutes”] = int((end_dt - start_dt).total_seconds() / 60)
events.append(event)
events.sort(key=lambda x: x[“start”])
return events

def get_completions_since(since_dt):
conn = get_db()
cur  = conn.cursor()
cur.execute(”””
SELECT * FROM completions WHERE completed_at >= %s ORDER BY completed_at DESC
“””, (since_dt,))
rows = [dict(r) for r in cur.fetchall()]
cur.close(); conn.close()
for r in rows:
if isinstance(r.get(“completed_at”), datetime.datetime):
r[“completed_at”] = r[“completed_at”].isoformat()
return rows

def get_completions_today():
now = datetime.datetime.now(pytz.UTC)
return get_completions_since(now.replace(hour=0, minute=0, second=0, microsecond=0))

def get_completions_week():
return get_completions_since(datetime.datetime.now(pytz.UTC) - datetime.timedelta(days=7))

def calculate_streak():
conn = get_db()
cur  = conn.cursor()
cur.execute(“SELECT DISTINCT DATE(completed_at) as d FROM completions ORDER BY d DESC”)
dates  = set(r[“d”] for r in cur.fetchall())
cur.close(); conn.close()
today  = datetime.date.today()
streak = 0
check  = today
while check in dates:
streak += 1
check  -= datetime.timedelta(days=1)
return streak

def get_stats():
conn = get_db()
cur  = conn.cursor()
cur.execute(”””
SELECT class_name, AVG(duration_minutes) as avg FROM completions
WHERE timed = TRUE AND duration_minutes IS NOT NULL GROUP BY class_name
“””)
class_avgs = {r[“class_name”]: round(r[“avg”]) for r in cur.fetchall()}
week_ago   = datetime.datetime.now(pytz.UTC) - datetime.timedelta(days=7)
cur.execute(”””
SELECT COALESCE(SUM(duration_minutes), 0) as total FROM completions
WHERE timed = TRUE AND completed_at >= %s
“””, (week_ago,))
total_mins = cur.fetchone()[“total”]
cur.execute(”””
SELECT AVG(ABS(duration_minutes - estimate_minutes)) as avg_diff FROM completions
WHERE timed = TRUE AND duration_minutes IS NOT NULL AND estimate_minutes IS NOT NULL
“””)
acc_row  = cur.fetchone()
accuracy = round(acc_row[“avg_diff”]) if acc_row and acc_row[“avg_diff”] else None
cur.execute(“SELECT COUNT(*) as total FROM completions”)
total = cur.fetchone()[“total”]
cur.close(); conn.close()
return {
“class_averages”:          class_avgs,
“total_minutes_this_week”: int(total_mins),
“avg_accuracy_minutes”:    accuracy,
“streak_days”:             calculate_streak(),
“total_completed”:         total,
}

_timer_lock = threading.Lock()

def get_timer():
conn = get_db()
cur  = conn.cursor()
cur.execute(“SELECT * FROM timer_state WHERE id = ‘current’”)
row = cur.fetchone()
cur.close(); conn.close()
if not row: return {}
t    = dict(row)
secs = t.get(“elapsed_seconds”, 0) or 0
if not t.get(“paused”) and t.get(“resumed_at”):
secs += time.time() - t[“resumed_at”]
t[“elapsed_minutes”] = round(secs / 60, 1)
return t

def elapsed_from(t):
secs = t.get(“elapsed_seconds”, 0) or 0
if not t.get(“paused”) and t.get(“resumed_at”):
secs += time.time() - t[“resumed_at”]
return secs / 60

def clear_timer():
conn = get_db()
cur  = conn.cursor()
cur.execute(“DELETE FROM timer_state WHERE id = ‘current’”)
conn.commit(); cur.close(); conn.close()

def generate_briefing():
cfg     = get_config()
api_key = cfg.get(“anthropic_api_key”, “”)
if not api_key:
return “Add your Anthropic API key in Settings to enable daily briefings.”
try:
assignments     = get_assignments()
events          = get_calendar_events()
completed_today = get_completions_today()
name            = cfg.get(“name”, “there”)
now             = datetime.datetime.now(LOCAL_TZ)
def fmt_a():
if not assignments: return “None”
return “\n”.join(f”- {a[‘name’]} ({a[‘class_name’]}) — {a[‘due_friendly’]}, est. {a[‘estimate_minutes’]} min. Details: {a[‘description’][:200]}” for a in assignments)
def fmt_e():
if not events: return “Nothing scheduled”
return “\n”.join(f”- {e[‘name’]} at {e[‘start_friendly’]}” + (f” until {e[‘end_friendly’]}” if e.get(“end_friendly”) else “”) for e in events)
def fmt_d():
if not completed_today: return “Nothing yet”
return “\n”.join(f”- {c[‘assignment_name’]}” + (f” ({c[‘duration_minutes’]} min)” if c.get(“duration_minutes”) else “”) for c in completed_today)
prompt = (
f”You are a smart, direct student assistant for {name}, a high school student.\n\n”
f”Today is {now.strftime(’%A, %B %d at %-I:%M %p’)}.\n\n”
f”PENDING ASSIGNMENTS:\n{fmt_a()}\n\n”
f”TODAY’S SCHEDULE:\n{fmt_e()}\n\n”
f”COMPLETED TODAY:\n{fmt_d()}\n\n”
f”Write a short daily plan for {name}. Be specific — use actual assignment names, “
f”fit work around the schedule, say what to do first and why. “
f”3 to 5 sentences max. No bullet points. Talk like a smart friend, not a teacher.”
)
client   = Anthropic(api_key=api_key)
response = client.messages.create(
model=“claude-sonnet-4-20250514”,
max_tokens=300,
messages=[{“role”: “user”, “content”: prompt}],
)
text = response.content[0].text
conn = get_db()
cur  = conn.cursor()
cur.execute(”””
INSERT INTO briefing_cache (id, briefing, generated_at) VALUES (‘current’, %s, NOW())
ON CONFLICT (id) DO UPDATE SET briefing = EXCLUDED.briefing, generated_at = NOW()
“””, (text,))
conn.commit(); cur.close(); conn.close()
return text
except Exception as e:
print(f”Briefing error: {e}”)
return “Could not generate briefing right now.”

@app.route(”/”)
def index():
return render_template(“index.html”)

@app.route(”/api/assignments”)
def route_assignments():
return jsonify(get_assignments())

@app.route(”/api/calendar”)
def route_calendar():
return jsonify(get_calendar_events())

@app.route(”/api/briefing”)
def route_briefing_get():
conn = get_db()
cur  = conn.cursor()
cur.execute(“SELECT briefing FROM briefing_cache WHERE id = ‘current’”)
row = cur.fetchone()
cur.close(); conn.close()
if row and row[“briefing”]:
return jsonify({“briefing”: row[“briefing”]})
return jsonify({“briefing”: generate_briefing()})

@app.route(”/api/briefing/refresh”, methods=[“POST”])
def route_briefing_refresh():
return jsonify({“briefing”: generate_briefing()})

@app.route(”/api/timer”)
def route_timer_get():
return jsonify(get_timer())

@app.route(”/api/timer/start”, methods=[“POST”])
def route_timer_start():
with _timer_lock:
d    = request.json or {}
conn = get_db()
cur  = conn.cursor()
cur.execute(”””
INSERT INTO timer_state (id, assignment_id, assignment_name, class_name,
estimate_minutes, elapsed_seconds, paused, resumed_at, started_at)
VALUES (‘current’, %s, %s, %s, %s, 0, FALSE, %s, NOW())
ON CONFLICT (id) DO UPDATE SET
assignment_id = EXCLUDED.assignment_id, assignment_name = EXCLUDED.assignment_name,
class_name = EXCLUDED.class_name, estimate_minutes = EXCLUDED.estimate_minutes,
elapsed_seconds = 0, paused = FALSE, resumed_at = EXCLUDED.resumed_at, started_at = NOW()
“””, (d.get(“assignment_id”), d.get(“assignment_name”), d.get(“class_name”), d.get(“estimate_minutes”, 30), time.time()))
conn.commit(); cur.close(); conn.close()
return jsonify({“ok”: True})

@app.route(”/api/timer/pause”, methods=[“POST”])
def route_timer_pause():
with _timer_lock:
t = get_timer()
if not t or t.get(“paused”): return jsonify({“ok”: False})
secs = (t.get(“elapsed_seconds”) or 0)
if t.get(“resumed_at”): secs += time.time() - t[“resumed_at”]
conn = get_db()
cur  = conn.cursor()
cur.execute(“UPDATE timer_state SET elapsed_seconds = %s, paused = TRUE, resumed_at = NULL WHERE id = ‘current’”, (secs,))
conn.commit(); cur.close(); conn.close()
return jsonify({“ok”: True, “elapsed_minutes”: round(secs / 60, 1)})

@app.route(”/api/timer/resume”, methods=[“POST”])
def route_timer_resume():
with _timer_lock:
conn = get_db()
cur  = conn.cursor()
cur.execute(“UPDATE timer_state SET paused = FALSE, resumed_at = %s WHERE id = ‘current’”, (time.time(),))
conn.commit(); cur.close(); conn.close()
return jsonify({“ok”: True})

@app.route(”/api/timer/stop”, methods=[“POST”])
def route_timer_stop():
with _timer_lock:
t = get_timer()
if not t: return jsonify({“ok”: False})
d       = request.json or {}
discard = d.get(“discard”, False)
mins    = elapsed_from(t)
if not discard:
cfg    = get_config()
cutoff = float(cfg.get(“timer_cutoff_multiplier”, 2.0))
est    = t.get(“estimate_minutes”) or 30
if mins <= est * cutoff:
conn = get_db()
cur  = conn.cursor()
cur.execute(”””
INSERT INTO completions (id, assignment_id, assignment_name, class_name,
duration_minutes, estimate_minutes, completed_at, timed)
VALUES (%s, %s, %s, %s, %s, %s, NOW(), TRUE)
“””, (str(uuid.uuid4()), t.get(“assignment_id”), t.get(“assignment_name”), t.get(“class_name”), round(mins), est))
conn.commit(); cur.close(); conn.close()
clear_timer()
return jsonify({“ok”: True, “elapsed_minutes”: round(mins)})

@app.route(”/api/complete”, methods=[“POST”])
def route_complete():
d    = request.json or {}
conn = get_db()
cur  = conn.cursor()
cur.execute(”””
INSERT INTO completions (id, assignment_id, assignment_name, class_name, duration_minutes, completed_at, timed)
VALUES (%s, %s, %s, %s, NULL, NOW(), FALSE)
“””, (str(uuid.uuid4()), d.get(“assignment_id”), d.get(“assignment_name”), d.get(“class_name”)))
conn.commit(); cur.close(); conn.close()
return jsonify({“ok”: True})

@app.route(”/api/completions/today”)
def route_completions_today():
return jsonify(get_completions_today())

@app.route(”/api/completions/week”)
def route_completions_week():
return jsonify(get_completions_week())

@app.route(”/api/stats”)
def route_stats():
return jsonify(get_stats())

@app.route(”/api/config”, methods=[“GET”])
def route_config_get():
cfg = get_config()
return jsonify({k: v for k, v in cfg.items() if k != “anthropic_api_key”})

@app.route(”/api/config”, methods=[“POST”])
def route_config_save():
d       = request.json or {}
updates = {k: d[k] for k in (“name”,“morning_briefing_time”,“timer_cutoff_multiplier”,“canvas_ical_url”,“apple_ical_url”,“anthropic_api_key”) if k in d}
set_config(updates)
return jsonify({“ok”: True})

def start_scheduler():
try:
cfg   = get_config()
parts = cfg.get(“morning_briefing_time”, “07:00”).split(”:”)
sched = BackgroundScheduler()
sched.add_job(generate_briefing, “cron”, hour=int(parts[0]), minute=int(parts[1]) if len(parts) > 1 else 0)
sched.start()
except Exception as e:
print(f”Scheduler error: {e}”)

if **name** == “**main**”:
init_db()
start_scheduler()
app.run(host=“0.0.0.0”, port=int(os.environ.get(“PORT”, 5000)), debug=False)
