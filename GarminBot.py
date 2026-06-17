import datetime as dt
import json
import os
import random
import threading

from http.server import BaseHTTPRequestHandler, HTTPServer
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
HISTORY_LENGTH         = 7
CONSECUTIVE_REST_THRESHOLD = 3
FTP_REMINDER_WEEKS     = 8
REST_DAY_THRESHOLD     = 25
SCHEDULED_TODAY_FILE   = "scheduled_today.json"

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
    d["targetType"]     = pz(zone_num)
    d["targetValueOne"] = zone_num
    d["targetValueTwo"] = zone_num
    return ExecutableStep(**d)

def seg(steps) -> WorkoutSegment:
    return WorkoutSegment(segmentOrder=1, sportType=CYCLING_SPORT, workoutSteps=steps)

def ride(name: str, total_secs: int, steps) -> CyclingWorkout:
    return CyclingWorkout(workoutName=name, estimatedDurationInSecs=total_secs,
                          workoutSegments=[seg(steps)])

# ---- THRESHOLD ----
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

# ---- MTB ----
def make_mtb_race_sim():
    """סימולציית מרוץ MTB — 3 'עליות' עם עצימות משתנה."""
    return ride("MTB Race Simulation", 4200, [
        pz_step(create_warmup_step(600, 1), 2),
        create_repeat_group(3, [
            pz_step(create_interval_step(120, 1), 6),
            pz_step(create_recovery_step(90,  2), 2),
            pz_step(create_interval_step(180, 3), 5),
            pz_step(create_recovery_step(120, 4), 1),
        ], step_order=2),
        pz_step(create_cooldown_step(600, 3), 2),
    ])

def make_mtb_explosive():
    """אינטרוולים קצרים ונפיצים לXCO — Zone 6 sprints."""
    return ride("MTB Explosive 8×45s", 3000, [
        pz_step(create_warmup_step(900, 1), 2),
        create_repeat_group(8, [
            pz_step(create_interval_step(45,  1), 6),
            pz_step(create_recovery_step(75,  2), 1),
        ], step_order=2),
        pz_step(create_cooldown_step(600, 3), 2),
    ])

def make_mtb_threshold_climb():
    """אינטרוולי עלייה לMTB — Threshold עם sprints."""
    return ride("MTB Climb Intervals 4×6", 4200, [
        pz_step(create_warmup_step(900, 1), 2),
        create_repeat_group(4, [
            pz_step(create_interval_step(300, 1), 4),
            pz_step(create_interval_step(60,  2), 6),
            pz_step(create_recovery_step(300, 3), 1),
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
                     W("z2_60",  "Zone 2 60min",     "60 דק'", make_zone2_60)],
        "moderate": [W("z2_60",  "Zone 2 60min",     "60 דק'", make_zone2_60),
                     W("z2_45",  "Zone 2 45min",     "45 דק'", make_zone2_45)],
        "recovery": [W("z2_45",  "Zone 2 45min",     "45 דק'", make_zone2_45),
                     W("arec",   "Active Recovery",  "30 דק'", make_active_recovery)],
    },
    "maintain": {
        "high":     [W("ss2x20", "Sweet Spot 2×20",  "65 דק'", make_sweet_spot_2x20),
                     W("tmp2x20","Tempo 2×20",        "65 דק'", make_tempo_2x20),
                     W("ss3x12", "Sweet Spot 3×12",  "58 דק'", make_sweet_spot_3x12)],
        "moderate": [W("tmp40",  "Tempo 40min",       "60 דק'", make_tempo_40),
                     W("z2_60",  "Zone 2 60min",     "60 דק'", make_zone2_60)],
        "recovery": [W("z2_45",  "Zone 2 45min",     "45 דק'", make_zone2_45),
                     W("arec",   "Active Recovery",  "30 דק'", make_active_recovery)],
    },
    "general_fitness": {
        "high":     [W("ss2x20", "Sweet Spot 2×20",  "65 דק'", make_sweet_spot_2x20),
                     W("ss3x12", "Sweet Spot 3×12",  "58 דק'", make_sweet_spot_3x12),
                     W("tmp2x20","Tempo 2×20",        "65 דק'", make_tempo_2x20),
                     W("th3x12", "Threshold 3×12",   "62 דק'", make_threshold_3x12)],
        "moderate": [W("tmp40",  "Tempo 40min",       "60 דק'", make_tempo_40),
                     W("ss3x12", "Sweet Spot 3×12",  "58 דק'", make_sweet_spot_3x12)],
        "recovery": [W("z2_45",  "Zone 2 45min",     "45 דק'", make_zone2_45),
                     W("z2_60",  "Zone 2 60min",     "60 דק'", make_zone2_60)],
    },
    "ftp": {
        "high":     [W("th2x20", "Threshold 2×20",   "65 דק'", make_threshold_2x20),
                     W("th3x12", "Threshold 3×12",   "62 דק'", make_threshold_3x12),
                     W("th4x8",  "Threshold 4×8",    "54 דק'", make_threshold_4x8),
                     W("ou4",    "Over-Under 4×8",   "66 דק'", make_over_under),
                     W("pyra",   "Pyramid Threshold","78 דק'", make_pyramid_threshold)],
        "moderate": [W("ss2x20", "Sweet Spot 2×20",  "65 דק'", make_sweet_spot_2x20),
                     W("ss3x12", "Sweet Spot 3×12",  "58 דק'", make_sweet_spot_3x12),
                     W("tmp40",  "Tempo 40min",       "60 דק'", make_tempo_40)],
        "recovery": [W("z2_45",  "Zone 2 45min",     "45 דק'", make_zone2_45),
                     W("z2_60",  "Zone 2 60min",     "60 דק'", make_zone2_60),
                     W("lsd90",  "LSD 90min",        "90 דק'", make_lsd_90)],
    },
    "vo2max": {
        "high":     [W("v5x5",   "VO2Max 5×5",       "75 דק'", make_vo2_5x5),
                     W("v4x6",   "VO2Max 4×6",       "71 דק'", make_vo2_4x6),
                     W("v3030",  "VO2Max 30/30 ×15", "45 דק'", make_vo2_30_30),
                     W("vmicro", "VO2Max Micro-Burst","55 דק'", make_vo2_micro)],
        "moderate": [W("th3x12", "Threshold 3×12",   "62 דק'", make_threshold_3x12),
                     W("ss2x20", "Sweet Spot 2×20",  "65 דק'", make_sweet_spot_2x20),
                     W("ou4",    "Over-Under 4×8",   "66 דק'", make_over_under)],
        "recovery": [W("z2_45",  "Zone 2 45min",     "45 דק'", make_zone2_45),
                     W("z2_60",  "Zone 2 60min",     "60 דק'", make_zone2_60)],
    },
    "endurance": {
        "high":     [W("lsd90",  "LSD 90min",        "90 דק'", make_lsd_90),
                     W("z2_60",  "Zone 2 60min",     "60 דק'", make_zone2_60)],
        "moderate": [W("z2_60",  "Zone 2 60min",     "60 דק'", make_zone2_60),
                     W("z2_45",  "Zone 2 45min",     "45 דק'", make_zone2_45)],
        "recovery": [W("z2_45",  "Zone 2 45min",     "45 דק'", make_zone2_45),
                     W("arec",   "Active Recovery",  "30 דק'", make_active_recovery)],
    },
    "mtb": {
        "high":     [W("mtbrace","MTB Race Sim",      "70 דק'", make_mtb_race_sim),
                     W("v3030",  "VO2Max 30/30 ×15", "45 דק'", make_vo2_30_30),
                     W("vmicro", "VO2Max Micro-Burst","55 דק'", make_vo2_micro),
                     W("mtbexp", "MTB Explosive 8×45","50 דק'", make_mtb_explosive),
                     W("mtbclmb","MTB Climb 4×6",    "70 דק'", make_mtb_threshold_climb)],
        "moderate": [W("ou4",    "Over-Under 4×8",   "66 דק'", make_over_under),
                     W("th3x12", "Threshold 3×12",   "62 דק'", make_threshold_3x12),
                     W("ss2x20", "Sweet Spot 2×20",  "65 דק'", make_sweet_spot_2x20)],
        "recovery": [W("z2_45",  "Zone 2 45min",     "45 דק'", make_zone2_45),
                     W("z2_60",  "Zone 2 60min",     "60 דק'", make_zone2_60)],
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
    "mtb":             "MTB — XCO Race Prep",
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
# SCHEDULED TODAY
# =====================================================

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
# AUTHORIZATION
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
        return False
    return (dt.date.today() - last).days >= FTP_REMINDER_WEEKS * 7

# =====================================================
# DELOAD WEEK
# =====================================================

def is_deload_week() -> bool:
    """כל 4 שבועות — שבוע deload אוטומטי."""
    start_str = load_config().get("plan_start_date")
    if not start_str:
        return False
    start   = dt.date.fromisoformat(start_str)
    weeks   = (dt.date.today() - start).days // 7
    return weeks > 0 and weeks % 4 == 3  # שבועות 3, 7, 11... (0-indexed)

# =====================================================
# ACTIVITY TRACKING
# =====================================================

def get_recent_cycling_dates(days: int = 10) -> set:
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
    cycling_dates = get_recent_cycling_dates()
    count = 0
    check = dt.date.today() - dt.timedelta(days=1)
    while check in cycling_dates:
        count += 1
        check -= dt.timedelta(days=1)
    return count

def had_hard_ride_yesterday() -> bool:
    """בדיקה גסה — אם יש אקטיביות רכיבה אתמול."""
    yesterday = dt.date.today() - dt.timedelta(days=1)
    return yesterday in get_recent_cycling_dates(3)

# =====================================================
# METRICS + TRAINING READINESS ALGORITHM
# =====================================================

def get_metrics() -> dict:
    today = dt.date.today().strftime("%Y-%m-%d")
    raw   = {}

    # --- HRV ---
    try:
        hrv_data            = client.get_hrv_data(today)
        raw["hrv"]          = hrv_data["hrvSummary"]["lastNightAvg"]
        raw["hrv_baseline"] = hrv_data["hrvSummary"]["baseline"]["balancedLow"]
        raw["hrv_status"]   = hrv_data["hrvSummary"]["status"]
    except Exception:
        pass

    # --- Sleep ---
    try:
        sleep_data         = client.get_sleep_data(today)
        dto                = sleep_data["dailySleepDTO"]
        raw["sleep_score"] = dto["sleepScores"]["overall"]["value"]
        raw["sleep_hours"] = round(dto.get("sleepTimeSeconds", 0) / 3600, 1)
    except Exception:
        pass

    # --- Body Battery ---
    try:
        bb_list = client.get_body_battery(today)
        if bb_list:
            vals = [e.get("charged", 0) for e in bb_list if e.get("charged")]
            if vals:
                raw["body_battery"] = max(vals)
    except Exception:
        pass

    # --- Training Status + Load + Recovery Time ---
    try:
        ts     = client.get_training_status(today)
        device = list(ts["mostRecentTrainingStatus"]["latestTrainingStatusData"].values())[0]

        raw["load"] = device["acuteTrainingLoadDTO"]["dailyTrainingLoadAcute"]

        status_dto = device.get("trainingStatusDTO", {})
        raw["training_status"] = status_dto.get("trainingStatusPhrase", "")

        recovery_dto = device.get("recoveryTimeDTO", {})
        raw["recovery_hours"] = recovery_dto.get("timeToOptimalRecovery", 0)
    except Exception:
        pass

    # --- Resting HR ---
    try:
        rhr_data   = client.get_rhr_data(today)
        metrics_map = rhr_data.get("allMetrics", {}).get("metricsMap", {})
        rhr_vals   = metrics_map.get("WELLNESS_RESTING_HEART_RATE", [])
        if rhr_vals:
            current_rhr     = rhr_vals[-1]["value"]
            avg_rhr         = sum(v["value"] for v in rhr_vals) / len(rhr_vals)
            raw["rhr"]      = current_rhr
            raw["rhr_delta"] = round(current_rhr - avg_rhr, 1)
    except Exception:
        pass

    # --- Yesterday's ride ---
    raw["rode_yesterday"] = had_hard_ride_yesterday()

    # --- Calculate readiness score ---
    raw["score"] = calculate_readiness_score(raw)
    return raw


def calculate_readiness_score(m: dict) -> int:
    """
    אלגוריתם Training Readiness מותאם אישית.
    מבוסס על 9 מדדים, ציון 0-100.
    """
    score = 50

    # Body Battery (0–100)
    bb = m.get("body_battery")
    if bb is not None:
        if   bb >= 75: score += 15
        elif bb >= 50: score += 7
        elif bb >= 30: score -= 7
        else:          score -= 15

    # HRV Status
    hrv_status = m.get("hrv_status", "").upper()
    hrv        = m.get("hrv")
    baseline   = m.get("hrv_baseline")
    if   hrv_status == "BALANCED":               score += 15
    elif hrv_status == "UNBALANCED":             score -= 10
    elif hrv_status in ("POOR", "LOW", "ALERT"): score -= 15
    # בונוס/עונש נוסף לפי ערך מול בייסליין
    if hrv and baseline:
        if   hrv > baseline * 1.05: score += 5
        elif hrv < baseline * 0.95: score -= 5

    # Recovery Time (שעות שנותרו)
    rec = m.get("recovery_hours", 0)
    if   rec == 0:   score += 10
    elif rec <= 18:  score += 5
    elif rec <= 36:  score += 0
    elif rec <= 54:  score -= 10
    else:            score -= 15

    # Sleep Score
    sl = m.get("sleep_score")
    if sl is not None:
        if   sl >= 85: score += 15
        elif sl >= 70: score += 8
        elif sl >= 55: score += 0
        elif sl >= 40: score -= 8
        else:          score -= 15

    # Sleep Duration (שעות)
    sh = m.get("sleep_hours")
    if sh is not None:
        if   sh >= 8: score += 10
        elif sh >= 7: score += 5
        elif sh >= 6: score += 0
        elif sh >= 5: score -= 5
        else:         score -= 10

    # Training Status
    ts_map = {
        "PRODUCTIVE": 10, "PEAKING": 8, "MAINTAINING": 5,
        "RECOVERY": 0, "UNPRODUCTIVE": -5, "DETRAINING": -5,
        "OVERREACHING": -15
    }
    ts = m.get("training_status", "").upper()
    score += ts_map.get(ts, 0)

    # Acute Training Load
    load = m.get("load")
    if load is not None:
        if   load < 60:  score += 10
        elif load < 100: score += 5
        elif load < 150: score += 0
        elif load < 200: score -= 10
        else:            score -= 15

    # Yesterday's ride
    if m.get("rode_yesterday"):
        score -= 10
    else:
        score += 10

    # Resting HR delta vs 7-day avg
    rhr_d = m.get("rhr_delta")
    if rhr_d is not None:
        if   rhr_d <= -3: score += 5
        elif rhr_d <= 3:  score += 0
        elif rhr_d <= 7:  score -= 5
        else:             score -= 10

    return max(0, min(100, score))

# =====================================================
# PICK WORKOUTS
# =====================================================

def get_tier(score: int) -> str:
    if   score >= 65: return "high"
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
    if score < REST_DAY_THRESHOLD:
        return None, None, "rest", "score"

    consecutive = get_consecutive_training_days()
    if consecutive >= CONSECUTIVE_REST_THRESHOLD:
        return None, None, "rest", f"consecutive_{consecutive}"

    # שבוע deload — מוריד לתקרה של recovery
    deload = is_deload_week()
    tier   = get_tier(score)
    if deload:
        tier = "recovery"

    tier_cons    = TIER_DOWN[tier]
    intensive    = pick_from_tier(plan_key, tier, [])
    conservative = pick_from_tier(plan_key, tier_cons, [intensive["key"]])
    return intensive, conservative, tier, "deload" if deload else None

# =====================================================
# GARMIN UPLOAD + SCHEDULE
# =====================================================

def upload_and_schedule(workout_key: str) -> str:
    w       = WORKOUT_BY_KEY[workout_key]
    workout = w["fn"]()

    result = client.upload_cycling_workout(workout)
    print(f"Upload result: {result}")  # לדיבוג — נראה ב-Railway logs

    wid = result.get("workoutId") or result.get("workout", {}).get("workoutId")
    print(f"Extracted workoutId: {wid}")

    today          = dt.date.today().strftime("%Y-%m-%d")
    schedule_result = client.schedule_workout(wid, today)
    print(f"Schedule result: {schedule_result}")

    # לא מוחקים את האימון! מחיקה כאן עלולה למחוק בקסקייד גם את
    # השיבוץ ביומן (ה"schedule" כנראה רק מצביע על ה-workoutId).

    save_history(workout_key)
    save_scheduled_today(workout_key, w["name"])
    return w["name"]

# =====================================================
# BUILD MESSAGE TEXT
# =====================================================

def build_metrics_text(m: dict) -> str:
    lines = []

    bb  = m.get("body_battery")
    hrv = m.get("hrv")
    hrv_status = m.get("hrv_status", "")
    sl  = m.get("sleep_score")
    sh  = m.get("sleep_hours")
    rec = m.get("recovery_hours")
    ts  = m.get("training_status", "")
    ld  = m.get("load")
    rhr = m.get("rhr")
    rhr_d = m.get("rhr_delta")

    if bb  is not None: lines.append(f"🔋 Body Battery:   {bb}/100")
    if hrv is not None: lines.append(f"💓 HRV:            {hrv}ms ({hrv_status})")
    if sl  is not None: lines.append(f"😴 שינה:           {sl}/100 ({sh}h)")
    if rec is not None: lines.append(f"⏱ Recovery Time:  {int(rec)}h")
    if ts:              lines.append(f"📈 Training Status:{ts}")
    if ld  is not None: lines.append(f"⚡ Load:            {int(ld)}")
    if rhr is not None:
        delta_str = f" ({'+' if rhr_d >= 0 else ''}{rhr_d} vs avg)" if rhr_d is not None else ""
        lines.append(f"❤️ RHR:            {rhr}bpm{delta_str}")

    return "\n".join(lines) if lines else "לא נמצאו נתונים"

# =====================================================
# SEND DAILY MESSAGE
# =====================================================

async def send_daily_recommendation(app):
    global GOAL
    if get_scheduled_today():
        return

    metrics = get_metrics()
    score   = metrics["score"]
    intensive, conservative, tier, rest_reason = choose_two_workouts(GOAL, score)
    score_bar = "█" * (score // 10) + "░" * (10 - score // 10)

    if intensive is None:
        if rest_reason and rest_reason.startswith("consecutive_"):
            days = rest_reason.split("_")[1]
            rest_text = f"רכבת {days} ימים ברצף — הגוף שלך צריך לנוח."
        else:
            rest_text = "הגוף שלך צריך לנוח."

        ftp_note = "\n\n💡 FTP Test מומלץ מחר!\n/ftpdone לאחר הטסט." if is_ftp_due() else ""

        await app.bot.send_message(chat_id=CHAT_ID, text=(
            f"😴 Garmin AI Coach\n\n"
            f"יום מנוחה מומלץ היום\n\n"
            f"ציון: {score}/100\n{score_bar}\n\n"
            f"{build_metrics_text(metrics)}\n\n"
            f"{rest_text}{ftp_note}"
        ))
        return

    deload_note = "\n🔄 שבוע Deload — אימונים קלים יותר השבוע." if rest_reason == "deload" else ""
    ftp_note    = "\n\n💡 FTP Test מומלץ מחר — /ftpdone לאחר הטסט." if is_ftp_due() and tier == "recovery" else ""

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"💪 {intensive['name']}",    callback_data=f"upload_{intensive['key']}"),
            InlineKeyboardButton(f"🌿 {conservative['name']}", callback_data=f"upload_{conservative['key']}"),
        ],
        [InlineKeyboardButton("❌ דלג", callback_data="skip")],
    ])

    await app.bot.send_message(chat_id=CHAT_ID, text=(
        f"🚴 Garmin AI Coach\n\n"
        f"תוכנית: {PLAN_LABELS[GOAL]}\n"
        f"{TIER_EMOJI[tier]} {TIER_LABEL[tier]}{deload_note}\n\n"
        f"ציון: {score}/100\n{score_bar}\n\n"
        f"{build_metrics_text(metrics)}\n\n"
        f"💪 אינטנסיבי:  {intensive['name']} ({intensive['dur']})\n"
        f"🌿 שמרני:      {conservative['name']} ({conservative['dur']})\n\n"
        f"באיזה אימון להתחיל?{ftp_note}"
    ), reply_markup=keyboard)

# =====================================================
# WEEKLY SUMMARY JOB
# =====================================================

async def weekly_summary_job(context: ContextTypes.DEFAULT_TYPE):
    global GOAL
    cycling_dates = get_recent_cycling_dates(7)
    count         = len(cycling_dates)
    day_names     = {0:"שני",1:"שלישי",2:"רביעי",3:"חמישי",4:"שישי",5:"שבת",6:"ראשון"}
    days_str      = ", ".join(day_names[d.weekday()] for d in sorted(cycling_dates)) or "לא נמצאו"
    bars          = "🟢" * count + "⬜" * (6 - count)
    emoji         = "🔥" if count >= 5 else "💪" if count >= 3 else "😴"
    deload_note   = "\n🔄 השבוע הבא — שבוע Deload מתוכנן." if is_deload_week() else ""

    await context.application.bot.send_message(chat_id=CHAT_ID, text=(
        f"📅 סיכום שבועי\n\n"
        f"אימונים השבוע: {count}/6\n{bars}\n\n"
        f"ימי רכיבה: {days_str}\n\n"
        f"תוכנית: {PLAN_LABELS[GOAL]}{deload_note}\n\n"
        f"{emoji} שבוע חדש מתחיל!"
    ))

# =====================================================
# DAILY JOB
# =====================================================

async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    await send_daily_recommendation(context.application)

# =====================================================
# COMMANDS
# =====================================================

async def coach_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
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
            msg += f"\n{rest_reason.split('_')[1]} ימי אימון רצופים."
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
    deload_note = " 🔄 Deload" if rest_reason == "deload" else ""
    await update.message.reply_text(
        f"🚴 {PLAN_LABELS[GOAL]}\n"
        f"{TIER_EMOJI[tier]} {TIER_LABEL[tier]}{deload_note} | ציון: {score}/100\n\n"
        f"💪 {intensive['name']} ({intensive['dur']})\n"
        f"🌿 {conservative['name']} ({conservative['dur']})",
        reply_markup=keyboard,
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    global GOAL
    metrics     = get_metrics()
    score       = metrics["score"]
    score_bar   = "█" * (score // 10) + "░" * (10 - score // 10)
    consecutive = get_consecutive_training_days()
    tier        = get_tier(score) if score >= REST_DAY_THRESHOLD else "rest"
    deload_note = "\n🔄 שבוע Deload פעיל!" if is_deload_week() else ""

    ftp_note = ""
    if is_ftp_due():
        last      = get_last_ftp_date()
        weeks_ago = (dt.date.today() - last).days // 7 if last else 0
        ftp_note  = f"\n\n💡 FTP Test לא עודכן {weeks_ago} שבועות — כדאי לתזמן."

    await update.message.reply_text(
        f"📊 סטטוס נוכחי\n\n"
        f"תוכנית: {PLAN_LABELS[GOAL]}{deload_note}\n\n"
        f"ציון: {score}/100\n{score_bar}\n\n"
        f"{build_metrics_text(metrics)}\n\n"
        f"ימי אימון רצופים: {consecutive}\n"
        f"{TIER_EMOJI[tier]} אימון צפוי: {TIER_LABEL[tier]}{ftp_note}"
    )


async def setplan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🟦 Conservative",    callback_data="plan_conservative")],
        [InlineKeyboardButton("🟩 Maintain",        callback_data="plan_maintain")],
        [InlineKeyboardButton("🟪 General Fitness", callback_data="plan_general_fitness")],
        [InlineKeyboardButton("🟨 FTP",             callback_data="plan_ftp")],
        [InlineKeyboardButton("🟥 VO2Max",          callback_data="plan_vo2max")],
        [InlineKeyboardButton("🌿 Endurance",       callback_data="plan_endurance")],
        [InlineKeyboardButton("🚵 MTB",             callback_data="plan_mtb")],
    ])
    await update.message.reply_text(
        f"📋 בחר תוכנית אימון\n\nתוכנית נוכחית: {PLAN_LABELS[GOAL]}",
        reply_markup=keyboard,
    )


async def ftpdone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    record_ftp_done()
    next_date = dt.date.today() + dt.timedelta(weeks=FTP_REMINDER_WEEKS)
    await update.message.reply_text(
        f"✅ FTP Test נרשם!\n\nתזכורת הבאה: {next_date.strftime('%d/%m/%Y')}"
    )

# =====================================================
# BUTTON HANDLER
# =====================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
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
        c    = load_config()
        c["plan"]            = GOAL
        c["plan_start_date"] = dt.date.today().isoformat()
        save_config(c)
        await query.edit_message_text(f"✅ תוכנית עודכנה!\n\n{PLAN_LABELS[GOAL]}\n\nDeload שבוע 4, 8, 12...")
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
    app.job_queue.run_daily(daily_job,
        time=dt.time(hour=8, minute=0, tzinfo=ISRAEL_TZ), days=(0,1,2,3,4,6))
    app.job_queue.run_daily(weekly_summary_job,
        time=dt.time(hour=9, minute=0, tzinfo=ISRAEL_TZ), days=(6,))
    print("Scheduled: daily 08:00, weekly summary Sunday 09:00")

# =====================================================
# ERROR HANDLER — לוג מסודר של חריגות לא מטופלות
# =====================================================

async def error_handler(update, context: ContextTypes.DEFAULT_TYPE):
    print(f"⚠️ Unhandled error: {context.error}")
    import traceback
    traceback.print_exception(type(context.error), context.error, context.error.__traceback__)

# =====================================================
# HEALTH CHECK SERVER (Render free tier requires a port)
# =====================================================

class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args):
        pass  # שתיקה — לא להציף לוגים בכל פינג


def start_health_server():
    port   = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    print(f"Health check server listening on port {port}")
    server.serve_forever()

# =====================================================
# MAIN
# =====================================================

def main():
    threading.Thread(target=start_health_server, daemon=True).start()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .get_updates_read_timeout(30)
        .get_updates_connect_timeout(30)
        .read_timeout(30)
        .connect_timeout(30)
        .build()
    )
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("coach",   coach_command))
    app.add_handler(CommandHandler("status",  status_command))
    app.add_handler(CommandHandler("setplan", setplan_command))
    app.add_handler(CommandHandler("ftpdone", ftpdone_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Telegram bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
