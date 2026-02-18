import streamlit as st
import uuid
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json

# -----------------------------
# Firebase Setup
# -----------------------------
# For Streamlit Cloud, store your service account JSON in Secrets
# Example: st.secrets["firebase_key_json"]
firebase_cred_dict = json.loads(st.secrets["firebase_key_json"])
cred = credentials.Certificate(firebase_cred_dict)
try:
    app = firebase_admin.get_app()
except ValueError:
    app = firebase_admin.initialize_app(cred)

db = firestore.client(app)

# -----------------------------
# Streamlit Config
# -----------------------------
st.set_page_config(page_title="Office Darts Tracker", layout="wide")

# -----------------------------
# Session State Setup
# -----------------------------
if "game_started" not in st.session_state:
    st.session_state.game_started = False
if "players" not in st.session_state:
    st.session_state.players = []
if "scores" not in st.session_state:
    st.session_state.scores = {}
if "current_player_index" not in st.session_state:
    st.session_state.current_player_index = 0
if "game_id" not in st.session_state:
    st.session_state.game_id = None
if "turn_number" not in st.session_state:
    st.session_state.turn_number = 1
if "winner" not in st.session_state:
    st.session_state.winner = None
if "double_in_active" not in st.session_state:
    st.session_state.double_in_active = {}
if "turn_start_score" not in st.session_state:
    st.session_state.turn_start_score = {}
if "busts" not in st.session_state:
    st.session_state.busts = {}

# Initialize dart inputs safely
for key in ["dart1", "dart2", "dart3", "double_check", "reset_darts"]:
    if key not in st.session_state:
        st.session_state[key] = 0 if "dart" in key else False

# -----------------------------
# Firebase Save Function
# -----------------------------
def save_throw_to_firestore(row):
    doc_id = f"{row['game_id']}_{row['turn_number']}_{row['player_name']}"
    db.collection("darts_throws").document(doc_id).set(row)

# -----------------------------
# Setup Screen
# -----------------------------
if not st.session_state.game_started:
    st.title("🎯 Office Darts Tracker")
    game_type = st.selectbox("Select Game Type", ["301", "501"])
    player_input = st.text_input(
        "Enter player names (comma separated)", placeholder="Eoin, John, Sarah"
    )

    if st.button("Start Game"):
        players = [p.strip() for p in player_input.split(",") if p.strip()]
        if len(players) < 2:
            st.error("Enter at least 2 players")
        else:
            st.session_state.players = players
            st.session_state.scores = {p: int(game_type) for p in players}
            st.session_state.double_in_active = {p: False for p in players}
            st.session_state.turn_start_score = {p: int(game_type) for p in players}
            st.session_state.busts = {p: 0 for p in players}
            st.session_state.game_started = True
            st.session_state.current_player_index = 0
            st.session_state.game_id = str(uuid.uuid4())
            st.session_state.turn_number = 1
            st.session_state.winner = None
            st.session_state.game_type = game_type
            st.session_state.reset_darts = True
            st.rerun()

# -----------------------------
# Game Screen
# -----------------------------
else:
    st.title("🎯 Live Game")
    players = st.session_state.players
    scores = st.session_state.scores
    current_index = st.session_state.current_player_index
    current_player = players[current_index]
    game_type = st.session_state.game_type
    busts = st.session_state.busts

    col1, col2 = st.columns([2, 1])

    # Display scores and busts
    with col1:
        st.subheader("Scores & Busts/No Scores")
        for p in players:
            if p == current_player:
                st.markdown(f"### 👉 {p}: {scores[p]} (Busts/No Scores: {busts[p]})")
            else:
                st.markdown(f"{p}: {scores[p]} (Busts/No Scores: {busts[p]})")

    # Reset darts if flagged
    if st.session_state.reset_darts:
        st.session_state.dart1 = 0
        st.session_state.dart2 = 0
        st.session_state.dart3 = 0
        st.session_state.double_check = False
        st.session_state.reset_darts = False

    # Input for current turn
    with col2:
        st.subheader(f"{current_player}'s Turn (3 Darts)")

        dart1 = st.number_input("Dart 1", min_value=0, max_value=180, step=1, key="dart1")
        dart2 = st.number_input("Dart 2", min_value=0, max_value=180, step=1, key="dart2")
        dart3 = st.number_input("Dart 3", min_value=0, max_value=180, step=1, key="dart3")
        is_double = st.checkbox("This turn included a double", key="double_check")

        total_throw = dart1 + dart2 + dart3

        # Live preview
        remaining_preview = scores[current_player] - total_throw
        st.metric(label="Remaining Score (Preview)", value=max(0, remaining_preview))

        if game_type == "301" and not st.session_state.double_in_active[current_player]:
            st.info("Double-In required! Score will not count until a double is hit.")
        elif remaining_preview < 0 or remaining_preview == 1:
            st.warning("⚠️ This turn would be a bust!")

        if st.button("Submit Turn"):
            start_score = scores[current_player]
            st.session_state.turn_start_score[current_player] = start_score
            remaining = start_score - total_throw
            bust_occurred = False

            # Double-In logic (301 only)
            if game_type == "301" and not st.session_state.double_in_active[current_player]:
                if is_double:
                    st.session_state.double_in_active[current_player] = True
                    scores[current_player] = remaining
                else:
                    st.warning("Double in required! Score not counted.")
                    remaining = start_score
                    bust_occurred = True
            else:
                # Double-Out logic (all games)
                if remaining < 0 or remaining == 1:
                    st.warning("Bust! Score reset.")
                    remaining = start_score
                    bust_occurred = True
                elif remaining == 0:
                    if is_double:
                        scores[current_player] = 0
                        st.session_state.winner = current_player
                    else:
                        st.warning("Must finish on a double! Bust.")
                        remaining = start_score
                        bust_occurred = True
                else:
                    scores[current_player] = remaining

            # Track busts
            if bust_occurred:
                busts[current_player] += 1

            # Save turn to Firestore
            row = {
                "game_id": st.session_state.game_id,
                "game_date": datetime.now(),
                "game_type": game_type,
                "player_name": current_player,
                "turn_number": st.session_state.turn_number,
                "dart1": dart1,
                "dart2": dart2,
                "dart3": dart3,
                "turn_total": total_throw,
                "remaining_score": scores[current_player],
                "double_flag": is_double,
                "bust": bust_occurred,
                "winner": st.session_state.winner,
                "timestamp": datetime.now()
            }
            save_throw_to_firestore(row)

            # Flag dart reset for next turn
            st.session_state.reset_darts = True
            st.session_state.turn_number += 1

            # Rotate player if no winner
            if not st.session_state.winner:
                st.session_state.current_player_index = (current_index + 1) % len(players)

            st.rerun()

    # Winner display
    if st.session_state.winner:
        st.success(f"🏆 Winner: {st.session_state.winner}")
        if st.button("Start New Game"):
            st.session_state.clear()
            st.rerun()
