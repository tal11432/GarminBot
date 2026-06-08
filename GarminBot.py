import json
import os
import random
import threading
import time

from datetime import datetime, date
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from garminconnect import Garmin

from telegram import (
    BotCommand,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Update
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

# =====================================================
# CONFIG
# =====================================================

load_dotenv()

EMAIL     = os.getenv("GARMIN_EMAIL")
PASSWORD  = os.getenv("GARMIN_PASSWORD")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID   = os.getenv("CHAT_ID")

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")

if not EMAIL or not PASSWORD:
    raise ValueError("Missing Garmin credentials")

if not BOT_TOKEN or not CHAT_ID:
    raise ValueError("Missing Telegram credentials")

with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

GOAL = CONFIG["plan"]

# =====================================================
# GARMIN LOGIN
# =====================================================

client = Garmin(EMAIL, PASSWORD)
print("Connecting to Garmin")
client.login()
print("Garmin connected")

# =====================================================
# WORKOUT GOALS
# =====================================================

WORKOUT_GOALS = {
    "conservative": {
        "high":     ["LSD", "Zone 2", "Base"],
        "moderate": ["Zone 2", "Base"],
        "recovery": ["Zone 2", "Base"],
    },
    "maintain": {
        "high":     ["Sweet Spot", "Tempo"],
        "moderate": ["Tempo", "Zone 2"],
        "recovery": ["Zone 2", "Base"],
    },
    "general_fitness": {
        "high":     ["Sweet Spot", "Tempo", "Threshold"],
        "moderate": ["Tempo", "Zone 2"],
        "recovery": ["Zone 2", "Base"],
    },
    "ftp": {
        "high":     ["Threshold", "Sweet Spot"],
        "moderate": ["Sweet Spot", "Tempo"],
        "recovery": ["Zone 2", "LSD", "Base"],
    },
    "vo2max": {
        "high":     ["VO2"],
        "moderate": ["Threshold", "Sweet Spot"],
        "recovery": ["Zone 2", "LSD", "Base"],
    },
    "endurance": {
        "high":     ["LSD", "Zone 2"],
        "moderate": ["Zone 2", "Base"],
        "recovery": ["Zone 2", "Base"],
    },
}

PLAN_LABELS = {
    "conservative":  "Conservative — Zone 2 & Base",
    "maintain":      "Maintain — Sweet Spot & Tempo",
    "general_fitness": "General Fitness — Sweet Spot & Threshold",
    "ftp":           "FTP — Threshold Training",
    "vo2max":        "VO2Max — Intervals",
    "endurance":     "Endurance — LSD",
}

REST_DAY_THRESHOLD = 25

# =====================================================
# METRICS
# =====================================================

def get_metrics():

    today = date.today().strftime("%Y-%m-%d")
    score = 50
    hrv         = None
    sleep_score = None
    load        = None

    try:
        hrv_data     = client.get_hrv_data(today)
        hrv          = hrv_data["hrvSummary"]["lastNightAvg"]
        baseline_low = hrv_data["hrvSummary"]["baseline"]["balancedLow"]
        status       = hrv_data["hrvSummary"]["status"]

        if status == "BALANCED":
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
        print("Getting training status...")
        ts = client.get_training_status(today)
        print("Got status")

        device = list(
            ts["mostRecentTrainingStatus"]
              ["latestTrainingStatusData"]
              .values()
        )[0]
        load = device["acuteTrainingLoadDTO"]["dailyTrainingLoadAcute"]

        if load > 150:
            score -= 20
        elif load < 80:
            score += 10
    except Exception:
        pass

    score = max(0, min(100, score))

    return {
        "score": score,
        "hrv":   hrv,
        "sleep": sleep_score,
        "load":  load,
    }

# =====================================================
# CHOOSE WORKOUT
# =====================================================

def get_tier(score):
    if score >= 65:
        return "high"
    elif score >= 40:
        return "moderate"
    else:
        return "recovery"


def find_candidates(cycling, keywords):
    return [
        w for w in cycling
        if any(kw.lower() in w["workoutName"].lower() for kw in keywords)
    ]


def choose_workout():
    global GOAL

    metrics = get_metrics()
    score   = metrics["score"]

    if score < REST_DAY_THRESHOLD:
        return None, metrics, "rest"

    workouts = client.get_workouts()

    cycling = [
        w for w in workouts
        if w["sportType"]["sportTypeKey"] == "cycling"
        and "test" not in w["workoutName"].lower()
    ]

    plan = WORKOUT_GOALS[GOAL]
    tier = get_tier(score)

    candidates = find_candidates(cycling, plan[tier])

    if not candidates and tier == "high":
        candidates = find_candidates(cycling, plan["moderate"])
    if not candidates:
        candidates = find_candidates(cycling, plan["recovery"])
    if not candidates:
        candidates = cycling

    chosen = random.choice(candidates)
    return chosen, metrics, tier

# =====================================================
# HELPERS
# =====================================================

TIER_EMOJI = {
    "high":     "🔵",
    "moderate": "🟡",
    "recovery": "🟢",
    "rest":     "😴",
}

TIER_LABEL = {
    "high":     "אימון מטרה",
    "moderate": "עצימות בינונית",
    "recovery": "התאוששות פעילה",
    "rest":     "יום מנוחה",
}

# =====================================================
# SEND DAILY MESSAGE
# =====================================================

async def send_daily_recommendation(app):
    workout, metrics, tier = choose_workout()

    score_bar = "█" * (metrics["score"] // 10) + "░" * (10 - metrics["score"] // 10)

    if workout is None:
        text = (
            f"😴 Garmin AI Coach\n\n"
            f"יום מנוחה מומלץ היום\n\n"
            f"ציון: {metrics['score']}/100\n"
            f"{score_bar}\n\n"
            f"HRV: {metrics['hrv']}\n"
            f"שינה: {metrics['sleep']}\n"
            f"עומס: {metrics['load']}\n\n"
            f"הגוף שלך צריך לנוח."
        )
        await app.bot.send_message(chat_id=CHAT_ID, text=text)
        return

    duration = round(workout["estimatedDurationInSecs"] / 60)

    text = (
        f"🚴 Garmin AI Coach\n\n"
        f"תוכנית: {PLAN_LABELS[GOAL]}\n"
        f"{TIER_EMOJI[tier]} {TIER_LABEL[tier]}\n\n"
        f"ציון: {metrics['score']}/100\n"
        f"{score_bar}\n\n"
        f"HRV: {metrics['hrv']}\n"
        f"שינה: {metrics['sleep']}\n"
        f"עומס: {metrics['load']}\n\n"
        f"אימון:\n"
        f"{workout['workoutName']}\n\n"
        f"משך: {duration} דקות\n\n"
        f"להוסיף ללוח Garmin?"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Schedule", callback_data=f"schedule_{workout['workoutId']}"),
            InlineKeyboardButton("❌ Skip",     callback_data="skip")
        ]
    ])

    await app.bot.send_message(chat_id=CHAT_ID, text=text, reply_markup=keyboard)

# =====================================================
# COMMAND: /coach
# =====================================================

async def coach_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    workout, metrics, tier = choose_workout()

    if workout is None:
        await update.message.reply_text(
            f"😴 יום מנוחה מומלץ (ציון: {metrics['score']}/100)"
        )
        return

    duration = round(workout["estimatedDurationInSecs"] / 60)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Schedule", callback_data=f"schedule_{workout['workoutId']}")]
    ])

    await update.message.reply_text(
        f"🚴 Garmin AI Coach\n\n"
        f"תוכנית: {PLAN_LABELS[GOAL]}\n"
        f"{TIER_EMOJI[tier]} {TIER_LABEL[tier]}\n\n"
        f"ציון: {metrics['score']}/100\n\n"
        f"אימון: {workout['workoutName']}\n"
        f"משך: {duration} דקות",
        reply_markup=keyboard
    )

# =====================================================
# COMMAND: /status
# =====================================================

async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    global GOAL

    metrics   = get_metrics()
    score_bar = "█" * (metrics["score"] // 10) + "░" * (10 - metrics["score"] // 10)
    tier      = get_tier(metrics["score"]) if metrics["score"] >= REST_DAY_THRESHOLD else "rest"

    await update.message.reply_text(
        f"📊 סטטוס נוכחי\n\n"
        f"תוכנית: {PLAN_LABELS[GOAL]}\n\n"
        f"ציון: {metrics['score']}/100\n"
        f"{score_bar}\n\n"
        f"HRV: {metrics['hrv']}\n"
        f"שינה: {metrics['sleep']}\n"
        f"עומס: {metrics['load']}\n\n"
        f"{TIER_EMOJI[tier]} אימון צפוי: {TIER_LABEL[tier]}"
    )

# =====================================================
# COMMAND: /setplan
# =====================================================

async def setplan_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
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
        reply_markup=keyboard
    )

# =====================================================
# BUTTONS
# =====================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    global GOAL

    query = update.callback_query
    await query.answer()
    data  = query.data

    # --- Plan change ---
    if data.startswith("plan_"):
        new_plan = data.replace("plan_", "")

        if new_plan not in WORKOUT_GOALS:
            await query.edit_message_text("❌ תוכנית לא מוכרת.")
            return

        GOAL = new_plan

        # שמירה ל-config.json
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump({"plan": GOAL}, f)

        await query.edit_message_text(
            f"✅ תוכנית עודכנה!\n\n{PLAN_LABELS[GOAL]}"
        )
        return

    # --- Skip workout ---
    if data == "skip":
        await query.edit_message_text("Workout skipped.")
        return

    # --- Schedule workout ---
    if data.startswith("schedule_"):
        workout_id = data.replace("schedule_", "")
        today      = date.today().strftime("%Y-%m-%d")

        try:
            client.schedule_workout(workout_id, today)
            await query.edit_message_text("✅ Workout added to Garmin calendar.")
        except Exception as e:
            await query.edit_message_text(f"❌ Failed: {e}")

# =====================================================
# REGISTER COMMANDS (מציג את התפריט כשמקלידים /)
# =====================================================

async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("coach",   "🚴 קבל המלצת אימון עכשיו"),
        BotCommand("status",  "📊 הצג מצב ומדדים נוכחיים"),
        BotCommand("setplan", "📋 שנה תוכנית אימון"),
    ])

# =====================================================
# DAILY SCHEDULER
# =====================================================

def scheduler_loop(app):
    while True:
        now = datetime.now(ISRAEL_TZ)

        if (
            now.hour == 8
            and now.minute == 0
            and now.weekday() != 5
        ):
            app.create_task(send_daily_recommendation(app))
            time.sleep(70)

        time.sleep(20)

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
    app.add_handler(CallbackQueryHandler(button_handler))

    threading.Thread(
        target=scheduler_loop,
        args=(app,),
        daemon=True
    ).start()

    print("Telegram bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
