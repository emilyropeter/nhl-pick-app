import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import json

# -----------------------------
# PAGE CONFIG
# -----------------------------
st.set_page_config(page_title="🏒 NHL Pick Tracker", layout="wide")

# -----------------------------
# GOOGLE SHEETS SETUP (via Streamlit Secrets)
# -----------------------------
scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]

# Load service account from Streamlit secrets
service_account_info = st.secrets["service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scope)
client = gspread.authorize(creds)

PICKS_SHEET_NAME = "NHL_Pick_Data"
SCHEDULE_SHEET_NAME = "NHL_Schedule"

picks_sheet = client.open(PICKS_SHEET_NAME).sheet1
schedule_sheet = client.open(SCHEDULE_SHEET_NAME).sheet1

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
def load_picks():
    raw_data = picks_sheet.get_all_values()
    if not raw_data:
        return pd.DataFrame(columns=["User","Week","Date","Game","Pick","Winner"])
    headers = [str(h).strip() for h in raw_data[0]]
    df = pd.DataFrame(raw_data[1:], columns=headers)
    return df

def load_schedule():
    raw_data = schedule_sheet.get_all_values()
    if not raw_data:
        return pd.DataFrame(columns=["Week","WeekStartDate","Date","Game","Home","Away"])
    headers = [str(h).strip() for h in raw_data[0]]
    df = pd.DataFrame(raw_data[1:], columns=headers)
    return df

def save_pick(user, week, date, game, pick):
    df = load_picks()
    exists = (df["User"]==user) & (df["Week"]==week) & (df["Game"]==game)
    if exists.any():
        df.loc[exists,"Pick"] = pick
    else:
        new_row = pd.DataFrame([{"User":user,"Week":week,"Date":date,"Game":game,"Pick":pick,"Winner":""}])
        df = pd.concat([df,new_row], ignore_index=True)
    picks_sheet.update([df.columns.tolist()] + df.values.tolist())

def save_winner(game, winner):
    df = load_picks()
    df.loc[df["Game"]==game,"Winner"] = winner
    picks_sheet.update([df.columns.tolist()] + df.values.tolist())

def get_week_status(week_start_str):
    today = datetime.today().date()
    week_start = datetime.strptime(week_start_str, "%Y-%m-%d").date()
    # Open only on Sunday
    if today < week_start + timedelta(days=1):
        return "Open"
    else:
        return "Closed"

# -----------------------------
# LOGIN
# -----------------------------
users = ["Em","Ma"]
username = st.sidebar.selectbox("Select your name:", users)
st.sidebar.success(f"Welcome, {username}!")
st.title("🏒 NHL Weekly Pick Tracker")

# -----------------------------
# LOAD DATA
# -----------------------------
schedule_df = load_schedule()
df_all = load_picks()

# -----------------------------
# DETERMINE CURRENT WEEK (based only on WeekStartDate)
# -----------------------------
today = datetime.today().date()

# Make sure WeekStartDate is a date object
schedule_df["WeekStartDate"] = pd.to_datetime(schedule_df["WeekStartDate"], errors="coerce").dt.date

# Find the most recent week start date that’s before or equal to today
past_weeks = schedule_df[schedule_df["WeekStartDate"] <= today]

if not past_weeks.empty:
    # Pick the latest available week start
    current_week_start = past_weeks["WeekStartDate"].max()
    current_week_row = schedule_df[schedule_df["WeekStartDate"] == current_week_start]
    current_week = current_week_row["Week"].iloc[0]
else:
    st.info("No active week found. Add a new week in the schedule.")
    current_week = "TBD"

# Prepare the week’s schedule
week_schedule = schedule_df[schedule_df["Week"] == current_week].copy()

# Mark the week as open (if it’s this week) or closed (if it’s old)
if not week_schedule.empty:
    week_start = pd.to_datetime(week_schedule["WeekStartDate"].iloc[0]).date()
    if today < week_start + timedelta(days=7):
        week_status = "Open"
    else:
        week_status = "Closed"
else:
    week_status = "Open"

st.subheader(f"Week {current_week} - Status: {week_status}")

# -----------------------------
# STEP 1: MAKE PICKS
# -----------------------------
st.subheader("Step 1: Make Your Picks")
if week_status == "Open":
    for _, row in week_schedule.iterrows():
        game = row["Game"]
        options = [row["Home"], row["Away"]]

        existing = df_all[(df_all["User"]==username) & (df_all["Week"]==current_week) & (df_all["Game"]==game)]
        current_pick = existing.iloc[0]["Pick"] if not existing.empty else ""

        pick = st.radio(f"{game}", ["", *options],
                        index=options.index(current_pick)+1 if current_pick in options else 0,
                        key=f"{username}_{game}")

        if st.button(f"Save Pick: {game}", key=f"save_{username}_{game}"):
            if pick != "":
                save_pick(username,current_week,row["Date"],game,pick)
                st.success(f"✅ Pick saved: {pick}")
else:
    st.info("Picks are closed for this week.")

# -----------------------------
# STEP 2: RECORD WINNERS (ADMIN)
# -----------------------------
st.subheader("Step 2: Record Winners (Admin)")
for _, row in week_schedule.iterrows():
    game = row["Game"]
    options = [row["Home"], row["Away"]]
    existing_winner = df_all[df_all["Game"]==game]["Winner"].dropna().unique()
    current_winner = existing_winner[0] if len(existing_winner)>0 else ""

    winner = st.selectbox(f"Winner of {game}", [""] + options,
                          index=options.index(current_winner)+1 if current_winner in options else 0,
                          key=f"winner_{game}")
    if winner != current_winner and winner != "":
        save_winner(game, winner)

# -----------------------------
# STEP 3: USER STATS
# -----------------------------
st.subheader("Your Picks and Accuracy")
df_all = load_picks()
df_all["Correct"] = df_all["Pick"] == df_all["Winner"]
user_picks = df_all[(df_all["User"]==username) & (df_all["Week"]==current_week)].copy()
if not user_picks.empty:
    weekly_accuracy = round(user_picks["Correct"].mean()*100,1)
    st.metric("Weekly Accuracy", f"{weekly_accuracy}%")
    st.dataframe(user_picks)
else:
    st.info("You haven't made any picks yet for this week.")

# -----------------------------
# STEP 4: LEADERBOARDS
# -----------------------------
st.subheader("🏆 Weekly Leaderboard")
week_picks = df_all[df_all["Week"]==current_week].copy()
if not week_picks.empty:
    weekly_leaderboard = week_picks.groupby("User")["Correct"].mean().reset_index()
    weekly_leaderboard["Accuracy %"] = (weekly_leaderboard["Correct"]*100).round(1)
    st.dataframe(weekly_leaderboard[["User","Accuracy %"]])
else:
    st.info("No picks recorded yet for this week.")

st.subheader("🌟 Cumulative Leaderboard (All Weeks)")
if not df_all.empty:
    cumulative_leaderboard = df_all.groupby("User")["Correct"].mean().reset_index()
    cumulative_leaderboard["Accuracy %"] = (cumulative_leaderboard["Correct"]*100).round(1)
    st.dataframe(cumulative_leaderboard[["User","Accuracy %"]])
else:
    st.info("No picks recorded yet.")

