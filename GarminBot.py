import json
import os
import threading
import time

from datetime import datetime, date

from dotenv import load_dotenv
from garminconnect import Garmin

from telegram import (
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

EMAIL = os.getenv("GARMIN_EMAIL")
PASSWORD = os.getenv("GARMIN_PASSWORD")

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

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

    "conservative": [
        "Base",
        "Zone 2",
        "LSD"
    ],

    "maintain": [
        "Base",
        "Tempo"
    ],

    "general_fitness": [
        "Sweet Spot",
        "Tempo",
        "Base"
    ],

    "ftp": [
        "FTP",
        "Threshold",
        "Sweet Spot"
    ],

    "vo2max": [
        "VO2",
        "Intervals"
    ],

    "endurance": [
        "LSD",
        "Base"
    ]
}

# =====================================================
# METRICS
# =====================================================

def get_metrics():

    today = date.today().strftime("%Y-%m-%d")

    score = 50

    hrv = None
    sleep_score = None
    load = None

    try:

        hrv_data = client.get_hrv_data(today)

        hrv = (
            hrv_data["hrvSummary"]["lastNightAvg"]
        )

        baseline_low = (
            hrv_data["hrvSummary"]["baseline"]["balancedLow"]
        )

        status = (
            hrv_data["hrvSummary"]["status"]
        )

        if status == "BALANCED":
            score += 10

        if hrv < baseline_low:
            score -= 20

    except Exception:
        pass

    try:

        sleep = client.get_sleep_data(today)

        sleep_score = (
            sleep["dailySleepDTO"]
            ["sleepScores"]
            ["overall"]
            ["value"]
        )

        if sleep_score >= 85:
            score += 15

        elif sleep_score < 60:
            score -= 15

    except Exception:
        pass

    try:

        print("Getting Status...")
        ts = client.get_training_status(today)
        print("Got status")
        device = list(
            ts["mostRecentTrainingStatus"]
              ["latestTrainingStatusData"]
              .values()
        )[0]

        load = (
            device["acuteTrainingLoadDTO"]
            ["dailyTrainingLoadAcute"]
        )

        if load > 150:
            score -= 20

        elif load < 80:
            score += 10

    except Exception:
        pass

    score = max(0, min(100, score))

    return {
        "score": score,
        "hrv": hrv,
        "sleep": sleep_score,
        "load": load
    }

# =====================================================
# CHOOSE WORKOUT
# =====================================================

def choose_workout():

    metrics = get_metrics()

    score = metrics["score"]

    workouts = client.get_workouts()

    cycling = [
        w for w in workouts
        if w["sportType"]["sportTypeKey"] == "cycling"
    ]

    keywords = WORKOUT_GOALS[GOAL]

    candidates = []

    for workout in cycling:

        name = workout["workoutName"]

        if any(
            keyword.lower() in name.lower()
            for keyword in keywords
        ):
            candidates.append(workout)

    if score < 40:

        recovery = []

        for workout in cycling:

            n = workout["workoutName"].lower()

            if (
                "base" in n
                or "zone 2" in n
                or "lsd" in n
            ):
                recovery.append(workout)

        if recovery:
            chosen = recovery[0]
        else:
            chosen = cycling[0]

    else:

        if candidates:
            chosen = candidates[0]
        else:
            chosen = cycling[0]

    return chosen, metrics

# =====================================================
# SEND DAILY MESSAGE
# =====================================================

async def send_daily_recommendation(app):

    workout, metrics = choose_workout()

    duration = round(
        workout["estimatedDurationInSecs"] / 60
    )

    text = f"""
🚴 Garmin AI Coach

Goal: {GOAL}

Score: {metrics['score']}
HRV: {metrics['hrv']}
Sleep: {metrics['sleep']}
Load: {metrics['load']}

Workout:
{workout['workoutName']}

Duration:
{duration} minutes

Add workout to Garmin calendar?
"""

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Schedule",
                callback_data=f"schedule_{workout['workoutId']}"
            ),
            InlineKeyboardButton(
                "❌ Skip",
                callback_data="skip"
            )
        ]
    ])

    await app.bot.send_message(
        chat_id=CHAT_ID,
        text=text,
        reply_markup=keyboard
    )

# =====================================================
# BUTTONS
# =====================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    data = query.data

    if data == "skip":

        await query.edit_message_text(
            "Workout skipped."
        )

        return

    if data.startswith("schedule_"):

        workout_id = data.replace(
            "schedule_",
            ""
        )

        today = date.today().strftime(
            "%Y-%m-%d"
        )

        try:

            client.schedule_workout(
                workout_id,
                today
            )

            await query.edit_message_text(
                "Workout added to Garmin calendar."
            )

        except Exception as e:

            await query.edit_message_text(
                f"Failed: {e}"
            )

# =====================================================
# MANUAL COMMAND
# =====================================================

async def coach_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    workout, metrics = choose_workout()

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "Schedule",
                callback_data=f"schedule_{workout['workoutId']}"
            )
        ]
    ])

    await update.message.reply_text(
        f"""
🚴 Garmin AI Coach

Goal: {GOAL}

Score: {metrics['score']}

Workout:
{workout['workoutName']}
""",
        reply_markup=keyboard
    )

# =====================================================
# DAILY SCHEDULER
# =====================================================

def scheduler_loop(app):

    while True:

        now = datetime.now()

        if (
            now.hour == 8
            and now.minute == 0
            and now.weekday() != 5
        ):

            app.create_task(
                send_daily_recommendation(app)
            )

            time.sleep(70)

        time.sleep(20)

# =====================================================
# MAIN
# =====================================================

def main():

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "coach",
            coach_command
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    threading.Thread(
        target=scheduler_loop,
        args=(app,),
        daemon=True
    ).start()

    print("Telegram bot started")

    app.run_polling()

if __name__ == "__main__":
    main()
