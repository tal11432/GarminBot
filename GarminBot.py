import datetime as dt
import json
import os
import random

from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from garminconnect import Garmin
from garminconnect.workout import (
    CyclingWorkout,
    WorkoutSegment,
    ExecutableStep,
    create_warmup_step,
    create_cooldown_step,
    create_interval_step,
    create_recovery_step,
    create_repeat_group,
    TargetType,
)

from telegram import (
    BotCommand,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Update,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# =====================================================
# CONFIG
# =====================================================

load_dotenv()

EMAIL         = os.getenv("GARMIN_EMAIL")
PASSWORD      = os.getenv("GARMIN_PASSWORD")
BOT_TOKEN     = os.getenv("BOT_TOKEN")
CHAT_ID       = os.getenv("CHAT_ID")
ISRAEL_TZ     = ZoneInfo("Asia/Jerusalem")
GARMIN_TOKENS = "garmin_tokens.json"
HISTORY_FILE  = "history.json"
HISTORY_LENGTH = 7

CONSECUTIVE_REST_THRESHOLD = 3   # ימי אימון רצופים לפני מנוחה כפויה
FTP_REMINDER_WEEKS         = 8   # כל כמה שבועות להזכיר FTP test
REST_DAY_THRESHOLD         = 25

if not EMAIL or not PASSWORD:
    raise ValueError("Missing Garmin credentials")
if not BOT_TOKEN or not CHAT_ID:
    raise ValueError("Missing Telegram credentials")


def load_config() -> dict:
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(data: dict):
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(data, f)


CONFIG = load_config()
GOAL   = CONFIG.get("plan", "ftp")

# =====================================================
# GARMIN LOGIN
# =====================================================

def garmin_connect():
    garmin = Garmin(EMAIL, PASSWORD)
    try:
        garmin.login(GARMIN_TOKENS)
        print("Garmin connected (from token)")
    except Exception:
        print("Token missing or expired, logging in fresh...")
        garmin.login()
        garmin.garth.dump(GARMIN_TOKENS)
        print("Garmin connected (fresh login, token saved)")
    return garmin

client = garmin_connect()

# =====================================================
# WORKOUT BUILDERS
# =====================================================

CYCLING_SPORT = {"sportTypeId": 2, "sportTypeKey": "cycling"}


def pz(zone_num: int) -> dict:
    return {
        "workoutTargetTypeId": TargetType.POWER,
        "workoutTargetTypeKey": "power.zone",
        "displayOrder": 1,
        "targetValueOne": zone_num,
        "targetValueTwo": zone_num,
    }


def pz_step(base_step: ExecutableStep, zone_num: int) -> ExecutableStep:
    d = base_step.model_dump()
    d["targetType"]    = pz(zone_num)
    d["targetValueOne"] = zone_num
    d["targetValueTwo"] = zone_num
    return ExecutableStep(**d)


def seg(steps) -> WorkoutSegment:
    return WorkoutSegment(segmentOrder=1, sportType=CYCLING_SPORT, workoutSteps=steps)


def ride(name: str, total_secs: int, steps) -> CyclingWorkout:
    return CyclingWorkout(workoutName=name, estimatedDurationInSecs=total_secs,
                          workoutSegments=[seg(steps)])


# ---- FTP / THRESHOLD ----
def make_threshold_2x20():
    return ride("Threshold 2×20", 3900, [
        pz_step(create_warmup_step(600, 1),    2),
        pz_step(create_interval_step(1200, 2), 4),
        pz_step(create_recovery_step(300, 3),  1),
        pz_step(create_interval_step(1200, 4), 4),
        pz_step(create_cooldown_step(600, 5),  2),
    ])

def make_threshold_3x12():
    return ride("Threshold 3×12", 3720, [
        pz_step(create_warmup_step(600, 1), 2),
        create_repeat_group(3, [
            pz_step(create_interval_step(720, 1), 4),
            pz_step(create_recovery_step(300, 2), 1),
        ], step_order=2),
        pz_step(create_cooldown_step(600, 3), 2),
    ])

def make_threshold_4x8():
    return ride("Threshold 4×8", 3240, [
        pz_step(create_warmup_step(600, 1), 2),
        create_repeat_group(4, [
            pz_step(create_interval_step(480, 1), 4),
            pz_step(create_recovery_step(240, 2), 1),
        ], step_order=2),
        pz_step(create_cooldown_step(600, 3), 2),
    ])

def make_over_under():
    return ride("Over-Under 4×(5+3)", 3960, [
        pz_step(create_warmup_step(600, 1), 2),
        create_repeat_group(4, [
            pz_step(create_interval_step(300, 1), 4),
            pz_step(create_interval_step(180, 2), 5),
            pz_step(create_recovery_step(300, 3), 1),
        ], step_order=2),
        pz_step(create_cooldown_step(600, 3), 2),
    ])

def make_pyramid_threshold():
    return ride("Pyramid Threshold", 4710, [
        pz_step(create_warmup_step(600, 1),    2),
        pz_step(create_interval_step(300, 2),  4),
        pz_step(create_recovery_step(180, 3),  1),
        pz_step(create_interval_step(600, 4),  4),
        pz_step(create_recovery_step(240, 5),  1),
        pz_step(create_interval_step(900, 6),  4),
        pz_step(create_recovery_step(240, 7),  1),
        pz_step(create_interval_step(600, 8),  4),
        pz_step(create_recovery_step(180, 9),  1),
        pz_step(create_interval_step(300, 10), 4),
        pz_step(create_cooldown_step(600, 11), 2),
    ])

# ---- SWEET SPOT ----
def make_sweet_spot_2x20():
    return ride("Sweet Spot 2×20", 3900, [
        pz_step(create_warmup_step(600, 1),    2),
        pz_step(create_interval_step(1200, 2), 3),
        pz_step(create_recovery_step(300, 3),  1),
        pz_step(create_interval_step(1200, 4), 3),
        pz_step(create_cooldown_step(600, 5),  2),
    ])

def make_sweet_spot_3x12():
    return ride("Sweet Spot 3×12", 3480, [
        pz_step(create_warmup_step(600, 1), 2),
        create_repeat_group(3, [
            pz_step(create_interval_step(720, 1), 3),
            pz_step(create_recovery_step(240, 2), 1),
        ], step_order=2),
        pz_step(create_cooldown_step(600, 3), 2),
    ])

# ---- TEMPO ----
def make_tempo_40():
    return ride("Tempo 40min", 3600, [
        pz_step(create_warmup_step(600, 1),    2),
        pz_step(create_interval_step(2400, 2), 3),
        pz_step(create_cooldown_step(600, 3),  2),
    ])

def make_tempo_2x20():
    return ride("Tempo 2×20", 3900, [
        pz_step(create_warmup_step(600, 1),    2),
        pz_step(create_interval_step(1200, 2), 3),
        pz_step(create_recovery_step(300, 3),  1),
        pz_step(create_interval_step(1200, 4), 3),
        pz_step(create_cooldown_step(600, 5),  2),
    ])

# ---- VO2MAX ----
def make_vo2_5x5():
    return ride("VO2Max 5×5", 4500, [
        pz_step(create_warmup_step(900, 1), 2),
        create_repeat_group(5, [
            pz_step(create_interval_step(300, 1), 5),
            pz_step(create_recovery_step(300, 2), 1),
        ], step_order=2),
        pz_step(create_cooldown_step(600, 3), 2),
    ])

def make_vo2_4x6():
    return ride("VO2Max 4×6", 4260, [
        pz_step(create_warmup_step(900, 1), 2),
        create_repeat_group(4, [
            pz_step(create_interval_step(360, 1), 5),
            pz_step(create_recovery_step(360, 2), 1),
        ], step_order=2),
        pz_step(create_cooldown_step(600, 3), 2),
    ])

def make_vo2_30_30():
    return ride("VO2Max 30/30 ×15", 2700, [
        pz_step(create_warmup_step(900, 1), 2),
        create_repeat_group(15, [
            pz_step(create_interval_step(30, 1), 5),
            pz_step(create_recovery_step(30, 2), 1),
        ], step_order=2),
        pz_step(create_cooldown_step(600, 3), 2),
    ])

def make_vo2_micro():
    return ride("VO2Max Micro-Burst 40/20", 3300, [
        pz_step(create_warmup_step(900, 1), 2),
        create_repeat_group(20, [
            pz_step(create_interval_step(40, 1), 6),
            pz_step(create_recovery_step(20, 2), 1),
        ], step_order=2),
        pz_step(create_cooldown_step(600, 3), 2),
    ])

# ---- BASE / RECOVERY ----
def make_zone2_45():
    return ride("Zone 2 — 45min", 3000, [
        pz_step(create_warmup_step(300, 1),    2),
        pz_step(create_interval_step(2400, 2), 2),
        pz_step(create_cooldown_step(300, 3),  2),
    ])

def make_zone2_60():
    return ride("Zone 2 — 60min", 3600, [
        pz_step(create_warmup_step(300, 1),    2),
        pz_step(create_interval_step(3000, 2), 2),
        pz_step(create_cooldown_step(300, 3),  2),
    ])

def make_lsd_90():
    return ride("LSD — 90min", 5400, [
        pz_step(create_warmup_step(300, 1),    2),
        pz_step(create_interval_step(4800, 2), 2),
        pz_step(create_cooldown_step(300, 3),  2),
    ])

def make_active_recovery():
    return ride("Active Recovery 30min", 1800, [
        pz_step(create_interval_step(1800, 1), 1),
    ])

# =====================================================
# WORKOUT LIBRARY
# =====================================================

def W(key, name, dur, fn):
    return {"key": key, "name": name, "dur": dur, "fn": fn}

WORKOUT_LIBRARY = {
    "conservative": {
        "high":     [W("lsd90",  "LSD 90min",        "90 דק'", make_lsd_90),
                     W("z2_60",  "Zone 2 60min",      "60 דק'", make_zone2_60)],
        "moderate": [W("z2_60",  "Zone 2 60min",      "60 דק'", make_zone2_60),
                     W("z2_45",  "Zone 2 45min",      "45 דק'", make_zone2_45)],
        "recovery": [W("z2_45",  "Zone 2 45min",      "45 דק'", make_zone2_45),
                     W("arec",   "Active Recovery",   "30 דק'", make_active_recovery)],
    },
    "maintain": {
        "high":     [W("ss2x20", "Sweet Spot 2×20",   "65 דק'", make_sweet_spot_2x20),
                     W("tmp2x20","Tempo 2×20",         "65 דק'", make_tempo_2x20),
                     W("ss3x12", "Sweet Spot 3×12",   "58 דק'", make_sweet_spot_3x12)],
        "moderate": [W("tmp40",  "Tempo 40min",        "60 דק'", make_tempo_40),
                     W("z2_60",  "Zone 2 60min",       "60 דק'", make_zone2_60)],
        "recovery": [W("z2_45",  "Zone 2 45min",       "45 דק'", make_zone2_45),
                     W("arec",   "Active Recovery",    "30 דק'", make_active_recovery)],
    },
    "general_fitness": {
        "high":     [W("ss2x20", "Sweet Spot 2×20",   "65 דק'", make_sweet_spot_2x20),
                     W("ss3x12", "Sweet Spot 3×12",   "58 דק'", make_sweet_spot_3x12),
                     W("tmp2x20","Tempo 2×20",         "65 דק'", make_tempo_2x20),
                     W("th3x12", "Threshold 3×12",    "62 דק'", make_threshold_3x12)],
        "moderate": [W("tmp40",  "Tempo 40min",        "60 דק'", make_tempo_40),
                     W("ss3x12", "Sweet Spot 3×12",   "58 דק'", make_sweet_spot_3x12)],
        "recovery": [W("z2_45",  "Zone 2 45min",       "45 דק'", make_zone2_45),
                     W("z2_60",  "Zone 2 60min",       "60 דק'", make_zone2_60)],
    },
    "ftp": {
        "high":     [W("th2x20", "Threshold 2×20",    "65 דק'", make_threshold_2x20),
                     W("th3x12", "Threshold 3×12",    "62 דק'", make_threshold_3x12),
                     W("th4x8",  "Threshold 4×8",     "54 דק'", make_threshold_4x8),
                     W("ou4",    "Over-Under 4×8",    "66 דק'", make_over_under),
                     W("pyra",   "Pyramid Threshold", "78 דק'", make_pyramid_threshold)],
        "moderate": [W("ss2x20", "Sweet Spot 2×20",   "65 דק'", make_sweet_spot_2x20),
                     W("ss3x12", "Sweet Spot 3×12",   "58 דק'", make_sweet_spot_3x12),
                     W("tmp40",  "Tempo 40min",        "60 דק'", make_tempo_40)],
        "recovery": [W("z2_45",  "Zone 2 45min",      "45 דק'", make_zone2_45),
                     W("z2_60",  "Zone 2 60min",      "60 דק'", make_zone2_60),
                     W("lsd90",  "LSD 90min",         "90 דק'", make_lsd_90)],
    },
    "vo2max": {
        "high":     [W("v5x5",   "VO2Max 5×5",        "75 דק'", make_vo2_5x5),
                     W("v4x6",   "VO2Max 4×6",        "71 דק'", make_vo2_4x6),
                     W("v3030",  "VO2Max 30/30 ×15",  "45 דק'", make_vo2_30_30),
                     W("vmicro", "VO2Max Micro-Burst", "55 דק'", make_vo2_micro)],
        "moderate": [W("th3x12", "Threshold 3×12",    "62 דק'", make_threshold_3x12),
                     W("ss2x20", "Sweet Spot 2×20",   "65 דק'", make_sweet_spot_2x20),
                     W("ou4",    "Over-Under 4×8",    "66 דק'", make_over_under)],
        "recovery": [W("z2_45",  "Zone 2 45min",      "45 דק'", make_zone2_45),
                     W("z2_60",  "Zone 2 60min",      "60 דק'", make_zone2_60)],
    },
    "endurance": {
        "high":     [W("lsd90",  "LSD 90min",         "90 דק'", make_lsd_90),
                     W("z2_60",  "Zone 2 60min",      "60 דק'", make_zone2_60)],
        "moderate": [W("z2_60",  "Zone 2 60min",      "60 דק'", make_zone2_60),
                     W("z2_45",  "Zone 2 45min",      "45 דק'", make_zone2_45)],
        "recovery": [W("z2_45",  "Zone 2 45min",      "45 דק'", make_zone2_45),
                     W("arec",   "Active Recovery",   "30 דק'", make_active_recovery)],
    },
}

WORKOUT_BY_KEY = {
    w["key"]: w
    for plan in WORKOUT_LIBRARY.values()
    for tier in plan.values()
    for w in tier
}

PLAN_LABELS = {
    "conservative":    "Conservative — Zone 2 & Base",
    "maintain":        "Maintain — Sweet Spot & Tempo",
    "general_fitness": "General Fitness — Sweet Spot & Threshold",
    "ftp":             "FTP — Threshold Training",
    "vo2max":          "VO2Max — Intervals",
    "endurance":       "Endurance — LSD",
}

TIER_EMOJI = {"high": "🔵", "moderate": "🟡", "recovery": "🟢", "rest": "😴"}
TIER_LABEL = {"high": "אימון מטרה", "moderate": "עצימות בינונית",
              "recovery": "התאוששות פעילה", "rest": "יום מנוחה"}
TIER_DOWN  = {"high": "moderate", "moderate": "recovery", "recovery": "recovery"}

# =====================================================
# HISTORY
# =====================================================

def load_history() -> list:
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(key: str):
    history = load_history()
    if key not in history:
        history.append(key)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history[-HISTORY_LENGTH:], f)


# =====================================================
# SCHEDULED TODAY — מניעת Double Booking
# =====================================================

SCHEDULED_TODAY_FILE = "scheduled_today.json"


def get_scheduled_today() -> dict | None:
    try:
        with open(SCHEDULED_TODAY_FILE, "r") as f:
            data = json.load(f)
        if data.get("date") == dt.date.today().isoformat():
            return data
        return None
    except Exception:
        return None


def save_scheduled_today(key: str, name: str):
    with open(SCHEDULED_TODAY_FILE, "w") as f:
        json.dump({"date": dt.date.today().isoformat(), "key": key, "name": name}, f)


# =====================================================
# AUTHORIZATION — רק הבעלים יכול לשלוט בבוט
# =====================================================

def is_authorized(update: Update) -> bool:
    return str(update.effective_chat.id) == CHAT_ID


# =====================================================
# FTP TEST TRACKING
# =====================================================

def get_last_ftp_date() -> dt.date | None:
    try:
        d = load_config().get("last_ftp_test")
        return dt.date.fromisoformat(d) if d else None
    except Exception:
        return None


def record_ftp_done():
    c = load_config()
    c["last_ftp_test"] = dt.date.today().isoformat()
    save_config(c)


def is_ftp_due() -> bool:
    last = get_last_ftp_date()
    if last is None:
        return False  # לא נוודא בפעם הראשונה
    return (dt.date.today() - last).days >= FTP_REMINDER_WEEKS * 7

# =====================================================
# CONSECUTIVE TRAINING DAYS
# =====================================================

def get_recent_cycling_dates(days: int = 10) -> set:
    """Returns set of dates with completed cycling activities."""
    try:
        activities = client.get_activities(0, 30)
        cutoff     = dt.date.today() - dt.timedelta(days=days)
        dates      = set()
        for act in activities:
            type_key = act.get("activityType", {}).get("typeKey", "")
            if "cycling" in type_key or "mountain_biking" in type_key:
                start = act.get("startTimeLocal", "")[:10]
                d = dt.date.fromisoformat(start)
                if d >= cutoff:
                    dates.add(d)
        return dates
    except Exception:
        return set()


def get_consecutive_training_days() -> int:
    """Count consecutive cycling days ending yesterday."""
    cycling_dates = get_recent_cycling_dates()
    count         = 0
    check         = dt.date.today() - dt.timedelta(days=1)
    while check in cycling_dates:
        count += 1
        check -= dt.timedelta(days=1)
    return count

# =====================================================
# METRICS
# =====================================================

def get_metrics() -> dict:
    today = dt.date.today().strftime("%Y-%m-%d")
    score = 50
    hrv = sleep_score = load = None

    try:
        hrv_data     = client.get_hrv_data(today)
        hrv          = hrv_data["hrvSummary"]["lastNightAvg"]
        baseline_low = hrv_data["hrvSummary"]["baseline"]["balancedLow"]
        if hrv_data["hrvSummary"]["status"] == "BALANCED":
            score += 10
        if hrv < baseline_low:
            score -= 20
    except Exception:
        pass

    try:
        sleep       = client.get_sleep_data(today)
        sleep_score = sleep["dailySleepDTO"]["sleepScores"]["overall"]["value"]
        if sleep_score >= 85:
            score += 15
        elif sleep_score < 60:
            score -= 15
    except Exception:
        pass

    try:
        ts     = client.get_training_status(today)
        device = list(ts["mostRecentTrainingStatus"]["latestTrainingStatusData"].values())[0]
        load   = device["acuteTrainingLoadDTO"]["dailyTrainingLoadAcute"]
        if load > 150:
            score -= 20
        elif load < 80:
            score += 10
    except Exception:
        pass

    return {"score": max(0, min(100, score)), "hrv": hrv, "sleep": sleep_score, "load": load}

# =====================================================
# PICK WORKOUTS
# =====================================================

def get_tier(score: int) -> str:
    if score >= 65:   return "high"
    elif score >= 40: return "moderate"
    else:             return "recovery"


def pick_from_tier(plan_key: str, tier: str, exclude_keys: list) -> dict:
    options = WORKOUT_LIBRARY[plan_key][tier]
    history = load_history()
    fresh   = [w for w in options if w["key"] not in history and w["key"] not in exclude_keys]
    pool    = fresh if fresh else [w for w in options if w["key"] not in exclude_keys]
    return random.choice(pool if pool else options)


def choose_two_workouts(plan_key: str, score: int):
    """Returns (intensive, conservative, tier, rest_reason)."""
    # יום מנוחה — ציון נמוך
    if score < REST_DAY_THRESHOLD:
        return None, None, "rest", "score"

    # יום מנוחה — שלושה ימי אימון רצופים
    consecutive = get_consecutive_training_days()
    if consecutive >= CONSECUTIVE_REST_THRESHOLD:
        return None, None, "rest", f"consecutive_{consecutive}"

    tier      = get_tier(score)
    tier_cons = TIER_DOWN[tier]
    intensive    = pick_from_tier(plan_key, tier, [])
    conservative = pick_from_tier(plan_key, tier_cons, [intensive["key"]])
    return intensive, conservative, tier, None

# =====================================================
# GARMIN UPLOAD + SCHEDULE
# =====================================================

def upload_and_schedule(workout_key: str) -> str:
    """Upload, schedule, then delete from library. Returns workout name."""
    w       = WORKOUT_BY_KEY[workout_key]
    workout = w["fn"]()
    result  = client.upload_cycling_workout(workout)
    wid     = result.get("workoutId") or result.get("workout", {}).get("workoutId")
    today   = dt.date.today().strftime("%Y-%m-%d")
    client.schedule_workout(wid, today)
    try:
        client.delete_workout(wid)  # מנקה את הספרייה
    except Exception:
        pass  # לא קריטי אם המחיקה נכשלת
    save_history(workout_key)
    save_scheduled_today(workout_key, w["name"])
    return w["name"]

# =====================================================
# SEND DAILY MESSAGE
# =====================================================

async def send_daily_recommendation(app):
    scheduled = get_scheduled_today()
    if scheduled:
        return
    global GOAL
    metrics = get_metrics()
    score   = metrics["score"]
    intensive, conservative, tier, rest_reason = choose_two_workouts(GOAL, score)
    score_bar = "█" * (score // 10) + "░" * (10 - score // 10)

    # --- יום מנוחה ---
    if intensive is None:
        if rest_reason and rest_reason.startswith("consecutive_"):
            days = rest_reason.split("_")[1]
            rest_text = f"רכבת {days} ימים ברצף — הגוף שלך צריך לנוח."
        else:
            rest_text = "הגוף שלך צריך לנוח."

        # בדיקת FTP
        ftp_note = ""
        if is_ftp_due():
            ftp_note = "\n\n💡 FTP Test מומלץ מחר!\nאחרי יום מנוחה תגיע בכוחות מלאים.\nהשתמש ב /ftpdone לאחר הטסט."

        await app.bot.send_message(
            chat_id=CHAT_ID,
            text=(
                f"😴 Garmin AI Coach\n\n"
                f"יום מנוחה מומלץ היום\n\n"
                f"ציון: {score}/100\n{score_bar}\n\n"
                f"HRV: {metrics['hrv']}\nשינה: {metrics['sleep']}\nעומס: {metrics['load']}\n\n"
                f"{rest_text}{ftp_note}"
            )
        )
        return

    # בדיקת FTP ביום רגיל (tier recovery = יום קל = מחר אפשר טסט)
    ftp_note = ""
    if is_ftp_due() and tier == "recovery":
        ftp_note = "\n\n💡 FTP Test מומלץ מחר — אחרי יום התאוששות תגיע בכוחות מלאים.\n/ftpdone לאחר הטסט."

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"💪 {intensive['name']}",    callback_data=f"upload_{intensive['key']}"),
            InlineKeyboardButton(f"🌿 {conservative['name']}", callback_data=f"upload_{conservative['key']}"),
        ],
        [InlineKeyboardButton("❌ דלג", callback_data="skip")],
    ])

    await app.bot.send_message(
        chat_id=CHAT_ID,
        text=(
            f"🚴 Garmin AI Coach\n\n"
            f"תוכנית: {PLAN_LABELS[GOAL]}\n"
            f"{TIER_EMOJI[tier]} {TIER_LABEL[tier]}\n\n"
            f"ציון: {score}/100\n{score_bar}\n\n"
            f"HRV: {metrics['hrv']}\nשינה: {metrics['sleep']}\nעומס: {metrics['load']}\n\n"
            f"💪 אינטנסיבי:  {intensive['name']} ({intensive['dur']})\n"
            f"🌿 שמרני:      {conservative['name']} ({conservative['dur']})\n\n"
            f"באיזה אימון להתחיל?{ftp_note}"
        ),
        reply_markup=keyboard,
    )

# =====================================================
# WEEKLY SUMMARY JOB (ראשון בבוקר)
# =====================================================

async def weekly_summary_job(context: ContextTypes.DEFAULT_TYPE):
    global GOAL
    cycling_dates = get_recent_cycling_dates(7)
    count         = len(cycling_dates)

    day_names = {0: "שני", 1: "שלישי", 2: "רביעי", 3: "חמישי",
                 4: "שישי", 5: "שבת", 6: "ראשון"}
    days_str  = ", ".join(day_names[d.weekday()] for d in sorted(cycling_dates)) or "לא נמצאו"

    bars  = "🟢" * count + "⬜" * (6 - count)
    emoji = "🔥" if count >= 5 else "💪" if count >= 3 else "😴"

    await context.application.bot.send_message(
        chat_id=CHAT_ID,
        text=(
            f"📅 סיכום שבועי\n\n"
            f"אימונים השבוע: {count}/6\n"
            f"{bars}\n\n"
            f"ימי רכיבה: {days_str}\n\n"
            f"תוכנית: {PLAN_LABELS[GOAL]}\n\n"
            f"{emoji} שבוע חדש מתחיל!"
        )
    )

# =====================================================
# DAILY JOB
# =====================================================

async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    await send_daily_recommendation(context.application)

# =====================================================
# COMMANDS
# =====================================================

async def coach_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    scheduled = get_scheduled_today()
    if scheduled:
        await update.message.reply_text(f"✅ כבר תזמנת אימון היום:\n{scheduled['name']}")
        return
    global GOAL
    metrics = get_metrics()
    score   = metrics["score"]
    intensive, conservative, tier, rest_reason = choose_two_workouts(GOAL, score)

    if intensive is None:
        msg = "😴 יום מנוחה מומלץ"
        if rest_reason and rest_reason.startswith("consecutive_"):
            days = rest_reason.split("_")[1]
            msg += f"\n{days} ימי אימון רצופים — תן לגוף לנוח."
        else:
            msg += f" (ציון: {score}/100)"
        await update.message.reply_text(msg)
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"💪 {intensive['name']}",    callback_data=f"upload_{intensive['key']}"),
            InlineKeyboardButton(f"🌿 {conservative['name']}", callback_data=f"upload_{conservative['key']}"),
        ],
        [InlineKeyboardButton("❌ דלג", callback_data="skip")],
    ])
    await update.message.reply_text(
        f"🚴 {PLAN_LABELS[GOAL]}\n"
        f"{TIER_EMOJI[tier]} {TIER_LABEL[tier]} | ציון: {score}/100\n\n"
        f"💪 {intensive['name']} ({intensive['dur']})\n"
        f"🌿 {conservative['name']} ({conservative['dur']})",
        reply_markup=keyboard,
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    global GOAL
    metrics     = get_metrics()
    score       = metrics["score"]
    score_bar   = "█" * (score // 10) + "░" * (10 - score // 10)
    consecutive = get_consecutive_training_days()
    tier        = get_tier(score) if score >= REST_DAY_THRESHOLD else "rest"

    ftp_note = ""
    if is_ftp_due():
        last = get_last_ftp_date()
        weeks_ago = (dt.date.today() - last).days // 7 if last else 0
        ftp_note = f"\n\n💡 FTP Test לא עודכן זה {weeks_ago} שבועות — כדאי לתזמן."

    await update.message.reply_text(
        f"📊 סטטוס נוכחי\n\n"
        f"תוכנית: {PLAN_LABELS[GOAL]}\n\n"
        f"ציון: {score}/100\n{score_bar}\n\n"
        f"HRV: {metrics['hrv']}\nשינה: {metrics['sleep']}\nעומס: {metrics['load']}\n\n"
        f"ימי אימון רצופים: {consecutive}\n"
        f"{TIER_EMOJI[tier]} אימון צפוי: {TIER_LABEL[tier]}{ftp_note}"
    )


async def setplan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🟦 Conservative",    callback_data="plan_conservative")],
        [InlineKeyboardButton("🟩 Maintain",        callback_data="plan_maintain")],
        [InlineKeyboardButton("🟪 General Fitness", callback_data="plan_general_fitness")],
        [InlineKeyboardButton("🟨 FTP",             callback_data="plan_ftp")],
        [InlineKeyboardButton("🟥 VO2Max",          callback_data="plan_vo2max")],
        [InlineKeyboardButton("🌿 Endurance",       callback_data="plan_endurance")],
    ])
    await update.message.reply_text(
        f"📋 בחר תוכנית אימון\n\nתוכנית נוכחית: {PLAN_LABELS[GOAL]}",
        reply_markup=keyboard,
    )


async def ftpdone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    record_ftp_done()
    next_date = dt.date.today() + dt.timedelta(weeks=FTP_REMINDER_WEEKS)
    await update.message.reply_text(
        f"✅ FTP Test נרשם!\n\nתזכורת הבאה: {next_date.strftime('%d/%m/%Y')} (בעוד {FTP_REMINDER_WEEKS} שבועות)"
    )

# =====================================================
# BUTTON HANDLER
# =====================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    global GOAL
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("plan_"):
        new_plan = data.replace("plan_", "")
        if new_plan not in WORKOUT_LIBRARY:
            await query.edit_message_text("❌ תוכנית לא מוכרת.")
            return
        GOAL = new_plan
        c = load_config()
        c["plan"] = GOAL
        save_config(c)
        await query.edit_message_text(f"✅ תוכנית עודכנה!\n\n{PLAN_LABELS[GOAL]}")
        return

    if data.startswith("upload_"):
        key = data.replace("upload_", "")
        if key not in WORKOUT_BY_KEY:
            await query.edit_message_text("❌ אימון לא נמצא.")
            return
        await query.edit_message_text("⏳ מעלה אימון לגרמין...")
        try:
            name = upload_and_schedule(key)
            await query.edit_message_text(f"✅ {name}\n\nנוסף ללוח Garmin!")
        except Exception as e:
            await query.edit_message_text(f"❌ שגיאה: {e}")
        return

    if data == "skip":
        await query.edit_message_text("Workout skipped.")

# =====================================================
# POST INIT
# =====================================================

async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("coach",   "🚴 קבל המלצת אימון עכשיו"),
        BotCommand("status",  "📊 הצג מצב ומדדים נוכחיים"),
        BotCommand("setplan", "📋 שנה תוכנית אימון"),
        BotCommand("ftpdone", "✅ עדכן שעשית FTP Test"),
    ])

    # הודעה יומית ב-8:00 ימים א'-ו' (לא שבת)
    app.job_queue.run_daily(
        daily_job,
        time=dt.time(hour=8, minute=0, tzinfo=ISRAEL_TZ),
        days=(0, 1, 2, 3, 4, 6),
    )

    # סיכום שבועי ב-9:00 ביום ראשון
    app.job_queue.run_daily(
        weekly_summary_job,
        time=dt.time(hour=9, minute=0, tzinfo=ISRAEL_TZ),
        days=(6,),  # ראשון בלבד
    )

    print("Scheduled: daily job 08:00, weekly summary Sunday 09:00")

# =====================================================
# MAIN
# =====================================================

def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("coach",   coach_command))
    app.add_handler(CommandHandler("status",  status_command))
    app.add_handler(CommandHandler("setplan", setplan_command))
    app.add_handler(CommandHandler("ftpdone", ftpdone_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Telegram bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
