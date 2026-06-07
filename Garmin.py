"""
PLANS

conservative  = הכי שמרני
maintenance   = שימור כושר
fitness       = שיפור כושר כללי
ftp           = שיפור FTP
vo2max        = שיפור VO2Max

שינוי תוכנית:
config.json

{
    "plan": "ftp"
}
"""

from datetime import date
from garminconnect import Garmin
from dotenv import load_dotenv

import os
import json


# ==================================================
# LOAD CONFIG
# ==================================================

with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

PLAN = CONFIG["plan"]


# ==================================================
# LOGIN
# ==================================================

load_dotenv()

EMAIL = os.getenv("GARMIN_EMAIL")
PASSWORD = os.getenv("GARMIN_PASSWORD")

if not EMAIL or not PASSWORD:
    raise ValueError("Missing GARMIN_EMAIL / GARMIN_PASSWORD")

client = Garmin(EMAIL, PASSWORD)
client.login()

print("Connected to Garmin")


# ==================================================
# DATE
# ==================================================

today = date.today().strftime("%Y-%m-%d")


# ==================================================
# HELPERS
# ==================================================

def safe_get(data, keys, default=None):
    try:
        for k in keys:
            data = data[k]
        return data
    except:
        return default


# ==================================================
# FETCH DATA
# ==================================================

status_data = None
sleep_data = None
stress_data = None
body_battery_data = None
hrv_data = None

try:
    status_data = client.get_training_status(today)
except:
    pass

try:
    sleep_data = client.get_sleep_data(today)
except:
    pass

try:
    stress_data = client.get_stress_data(today)
except:
    pass

try:
    body_battery_data = client.get_body_battery(today)
except:
    pass

try:
    hrv_data = client.get_hrv_data(today)
except:
    pass


# ==================================================
# TRAINING STATUS
# ==================================================

device = None

try:
    device = list(
        status_data["mostRecentTrainingStatus"]["latestTrainingStatusData"].values()
    )[0]
except:
    pass

status = None
acute_load = None
chronic_load = None
vo2max = None

if device:

    status = device.get("trainingStatus")

    load_block = device.get("acuteTrainingLoadDTO", {})

    acute_load = load_block.get("dailyTrainingLoadAcute")
    chronic_load = load_block.get("dailyTrainingLoadChronic")

try:
    vo2max = safe_get(
        status_data,
        [
            "mostRecentVO2Max",
            "cycling",
            "vo2MaxValue"
        ]
    )
except:
    pass


# ==================================================
# HRV
# ==================================================

hrv = None
hrv_status = None

if hrv_data:

    hrv = safe_get(
        hrv_data,
        ["hrvSummary", "lastNightAvg"]
    )

    hrv_status = safe_get(
        hrv_data,
        ["hrvSummary", "status"]
    )


# ==================================================
# SLEEP
# ==================================================

sleep_score = None

try:
    sleep_score = safe_get(
        sleep_data,
        [
            "dailySleepDTO",
            "sleepScores",
            "overall",
            "value"
        ]
    )
except:
    pass


# ==================================================
# BODY BATTERY
# ==================================================

body_battery = None

try:
    values = body_battery_data["bodyBatteryValuesArray"]

    if values:
        body_battery = values[-1]["bodyBatteryValue"]

except:
    pass


# ==================================================
# STRESS
# ==================================================

stress_avg = None

try:

    stress_values = stress_data["stressValuesArray"]

    vals = [
        x["stressLevel"]
        for x in stress_values
        if x.get("stressLevel") is not None
    ]

    if vals:
        stress_avg = round(sum(vals) / len(vals))

except:
    pass


# ==================================================
# RECOVERY SCORE
# ==================================================

score = 50


# ---------- HRV ----------

if hrv is not None:

    baseline_low = safe_get(
        hrv_data,
        ["hrvSummary", "baseline", "balancedLow"]
    )

    baseline_high = safe_get(
        hrv_data,
        ["hrvSummary", "baseline", "balancedUpper"]
    )

    if baseline_low and hrv < baseline_low:
        score -= 20

    elif baseline_high and hrv > baseline_high:
        score += 10


# ---------- Sleep ----------

if sleep_score is not None:

    if sleep_score >= 85:
        score += 15

    elif sleep_score >= 75:
        score += 5

    elif sleep_score < 60:
        score -= 20


# ---------- Body Battery ----------

if body_battery is not None:

    if body_battery >= 80:
        score += 15

    elif body_battery >= 60:
        score += 5

    elif body_battery < 40:
        score -= 20


# ---------- Stress ----------

if stress_avg is not None:

    if stress_avg > 50:
        score -= 15

    elif stress_avg < 25:
        score += 5


# ---------- Load ----------

if acute_load is not None:

    if acute_load > 150:
        score -= 20

    elif acute_load > 120:
        score -= 10


score = max(0, min(100, score))


# ==================================================
# WORKOUTS
# ==================================================

all_workouts = client.get_workouts()

cycling_workouts = []

for w in all_workouts:

    sport = (
        w.get("sportType", {})
         .get("sportTypeKey", "")
         .lower()
    )

    if sport == "cycling":
        cycling_workouts.append(w)


# ==================================================
# PLAN MAPPING
# ==================================================

plan_keywords = {

    "conservative": [
        "base",
        "zone 2",
        "lsd"
    ],

    "maintenance": [
        "base",
        "tempo"
    ],

    "fitness": [
        "tempo",
        "sweet spot",
        "threshold"
    ],

    "ftp": [
        "sweet spot",
        "threshold",
        "ftp"
    ],

    "vo2max": [
        "vo2",
        "interval"
    ]
}


# ==================================================
# WORKOUT PICKER
# ==================================================

recommended = None

if score < 35:

    candidates = [
        w for w in cycling_workouts
        if "base" in w["workoutName"].lower()
        or "zone 2" in w["workoutName"].lower()
    ]

else:

    keywords = plan_keywords.get(PLAN, [])

    candidates = []

    for w in cycling_workouts:

        name = w["workoutName"].lower()

        if any(k in name for k in keywords):
            candidates.append(w)

if candidates:
    recommended = candidates[0]


# ==================================================
# OUTPUT
# ==================================================

print("\n==============================")
print("GARMIN AI COACH")
print("==============================")

print("Plan:", PLAN)
print("Recovery Score:", score)

print()

print("HRV:", hrv)
print("HRV Status:", hrv_status)

print("Sleep:", sleep_score)

print("Body Battery:", body_battery)

print("Stress:", stress_avg)

print("VO2Max:", vo2max)

print("Acute Load:", acute_load)
print("Chronic Load:", chronic_load)

print()

if recommended:

    print("Recommended Workout:")
    print(recommended["workoutName"])

    mins = round(
        recommended["estimatedDurationInSecs"] / 60
    )

    print("Duration:", mins, "min")

else:

    print("No matching workout found")


# ==================================================
# OPTIONAL: SCHEDULE TO GARMIN CALENDAR
# ==================================================

if recommended:

    print("\nPush workout to Garmin Calendar?")
    answer = input("Type Y to schedule, anything else to skip: ").strip().upper()

    if answer == "Y":

        try:

            result = client.schedule_workout(
                recommended["workoutId"],
                today
            )

            print("\nWorkout successfully scheduled!")

            print("Workout:", recommended["workoutName"])
            print("Date:", today)

            print("\nGarmin response:")
            print(result)

        except Exception as e:

            print("\nFailed to schedule workout")
            print(e)

    else:

        print("\nWorkout was not scheduled.")
