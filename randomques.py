import streamlit as st
import pandas as pd
import requests
import io
import os
import time
import streamlit.components.v1 as components
import random
import base64
import json

# ✅ Page Setup
st.set_page_config(page_title="Online Quiz", layout="wide")

# ✅ Prevent Right-Click & Copying (Anti-Cheating)
DISABLE_JS = """
<script>
document.addEventListener("contextmenu", event => event.preventDefault());
document.addEventListener("keydown", function(event) { 
    if (event.ctrlKey && (event.key === 'c' || event.key === 'x' || event.key === 'u')) {
        event.preventDefault();
    }
});
document.addEventListener('copy', (event) => event.preventDefault());
document.addEventListener('selectstart', (event) => event.preventDefault());
</script>
"""
components.html(DISABLE_JS, height=0)

# ✅ GitHub Quiz Data Source
GITHUB_REPO = st.secrets["github"]["username"]+"/sai"
GITHUB_FILE_PATH = "quiz_data.xlsx"
GITHUB_TOKEN = st.secrets["api"]["key"]
#for results
FILE_PATH="results.xlsx"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"

# ✅ Excel File for Storing Scores
LOCAL_EXCEL_PATH = "sample.xlsx"

# ✅ Quiz Timer Duration (Seconds)
QUIZ_DURATION = 60  

# ✅ Fetch Quiz Data from GitHub
def fetch_quiz_data():
    # ✅ If already fetched, return stored data (prevents reloading & reshuffling)
    if "shuffled_questions" in st.session_state:
        return pd.DataFrame(st.session_state.shuffled_questions)

    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{GITHUB_FILE_PATH}"
    url += f"?timestamp={pd.Timestamp.now().timestamp()}"  # Prevent caching issues
    headers = {"Cache-Control": "no-cache"}

    #st.write("✅ Fetching quiz data...")
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            df = pd.read_excel(io.BytesIO(response.content), dtype=str, engine='openpyxl')

            # ✅ Ensure DataFrame is NOT empty
            if df.empty:
                st.error("❌ Quiz data is empty. Please check the source file.")
                return None

            # ✅ Shuffle ONLY ONCE & Store in Session
            shuffled_df = df.sample(frac=1).reset_index(drop=True)  # Remove fixed seed for variation
            st.session_state.shuffled_questions = shuffled_df.to_dict(orient='records')

            #st.write("✅ Quiz data loaded & shuffled!")
            return shuffled_df
        else:
            st.error(f"❌ Failed to fetch quiz data. Status Code: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"❌ Error fetching quiz data: {e}")
        return None



# ✅ Function to Append Data & Upload Back to GitHub
def append_score_to_github(participant1, participant2, phone, email, score):
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    # 1️⃣ Fetch Existing File
    response = requests.get(GITHUB_API_URL, headers=headers)
    
    if response.status_code == 200:
        file_data = response.json()
        content = base64.b64decode(file_data["content"])  # Decode file
        existing_df = pd.read_excel(io.BytesIO(content))
        sha = file_data["sha"]  # Required for updating file
    else:
        existing_df = pd.DataFrame(columns=["Participant 1", "Participant 2", "Phone", "Email", "Score"])
        sha = None  # New file creation

    # 2️⃣ Append New Data
    new_data = pd.DataFrame([[participant1, participant2, phone, email, score]],
                            columns=["Participant 1", "Participant 2", "Phone", "Email", "Score"])
    updated_df = pd.concat([existing_df, new_data], ignore_index=True)

    # 3️⃣ Convert Data to Byte Stream
    output = io.BytesIO()
    updated_df.to_excel(output, index=False, engine='openpyxl')
    output.seek(0)

    # 4️⃣ Encode Data in Base64
    encoded_content = base64.b64encode(output.read()).decode()

    # 5️⃣ Push Updated File to GitHub
    data = {
        "message": "Append new quiz score",
        "content": encoded_content,
        "sha": sha  # Required if updating an existing file
    }
    
    response = requests.put(GITHUB_API_URL, headers=headers, data=json.dumps(data))

    if response.status_code in [200, 201]:
        print("✅ Score successfully updated in GitHub!")
        return True
    else:
        print(f"❌ Failed to update GitHub file: {response.json()}")
        return False

# ✅ Save Participant Data & Score to Excel
def save_score_to_excel(participant1, participant2, phone, email, score):
    try:
        if os.path.exists(LOCAL_EXCEL_PATH):
            existing_data = pd.read_excel(LOCAL_EXCEL_PATH)
        else:
            existing_data = pd.DataFrame(columns=["Participant 1", "Participant 2", "Phone", "Email", "Score"])
        
        new_data = pd.DataFrame([[participant1, participant2, phone, email, score]], 
                                columns=["Participant 1", "Participant 2", "Phone", "Email", "Score"])
        updated_data = pd.concat([existing_data, new_data], ignore_index=True)
        
        updated_data.to_excel(LOCAL_EXCEL_PATH, index=False)
        return True
    except Exception as e:
        st.error(f"❌ Error saving the score: {e}")
        return False

# ✅ Calculate Score
def evaluate_quiz(user_answers, correct_answers):
    return sum(1 for q in user_answers if user_answers[q] == correct_answers[q])

# ✅ Main App
def main():
    st.title("📝 Online Quiz")
    st.markdown("""
        <style>
        body {
            -webkit-user-select: none;
            -moz-user-select: none;
            -ms-user-select: none;
            user-select: none;
        }
        </style>
    """, unsafe_allow_html=True)

    # Initialize session state variables
    if "submitted" not in st.session_state:
        st.session_state.submitted = False
    if "quiz_closed" not in st.session_state:
        st.session_state.quiz_closed = False
    if "start_time" not in st.session_state:
        st.session_state.start_time = None
    if "user_answers" not in st.session_state:
        st.session_state.user_answers = {}

    # ✅ Collect Participant Details (Before Quiz Starts)
    if "participant1" not in st.session_state:
        with st.form("participant_form"):
            participant1 = st.text_input("👤 Participant 1 Name")
            participant2 = st.text_input("👤 Participant 2 Name")
            phone = st.text_input("📞 Phone Number")
            email = st.text_input("✉️ Email ID")
            start_button = st.form_submit_button("Start Quiz")

        if start_button:
            if not all([participant1, participant2, phone, email]):
                st.warning("⚠️ Please fill in all fields to start the quiz.")
                return

            # Store participant details
            st.session_state.participant1 = participant1
            st.session_state.participant2 = participant2
            st.session_state.phone = phone
            st.session_state.email = email
            st.session_state.start_time = time.time()
            st.session_state.quiz_started = True
            st.rerun()

    # If quiz hasn't started, stop execution
    if "quiz_started" not in st.session_state or not st.session_state.quiz_started:
        return

    # ✅ Display Participant Details (Read-Only)
    st.write("### Participant Details")
    st.text_input("👤 Participant 1", value=st.session_state.participant1, disabled=True)
    st.text_input("👤 Participant 2", value=st.session_state.participant2, disabled=True)
    st.text_input("📞 Phone Number", value=st.session_state.phone, disabled=True)
    st.text_input("✉️ Email ID", value=st.session_state.email, disabled=True)

    # ✅ Timer Implementation
    elapsed_time = time.time() - st.session_state.start_time
    remaining_time = max(QUIZ_DURATION - int(elapsed_time), 0)

    timer_placeholder = st.sidebar.empty()
    timer_placeholder.markdown(f"⏳ **Time Left: {remaining_time} seconds**")

    # ✅ Auto-Submit if Time Runs Out
    if remaining_time == 0 and not st.session_state.submitted:
        st.session_state.submitted = True
        st.session_state.quiz_closed = True
        if "correct_answers" in st.session_state:
            st.session_state.score = evaluate_quiz(st.session_state.user_answers, st.session_state.correct_answers)
            append_score_to_github(st.session_state.participant1,st.session_state.participant2, st.session_state.phone, st.session_state.email, st.session_state.score)
        st.rerun()

    # ✅ Fetch Quiz Data
    quiz_data = fetch_quiz_data()

    if quiz_data is not None:
        required_columns = {"Question", "Option 1", "Option 2", "Option 3", "Option 4", "Correct Answer"}
        if not required_columns.issubset(quiz_data.columns):
            st.error("❌ The quiz data file is missing required columns!")
            return

        questions = {}
        correct_answers = {}
        for _, row in quiz_data.iterrows():
            question = str(row["Question"]).replace("\n", "<br>")  # Preserve line breaks
            options = [
                str(row["Option 1"]).replace("\n", "<br>"),
                str(row["Option 2"]).replace("\n", "<br>"),
                str(row["Option 3"]).replace("\n", "<br>"),
                str(row["Option 4"]).replace("\n", "<br>")
            ]
            questions[question] = options
            correct_answers[question] = str(row["Correct Answer"])

        st.session_state.correct_answers = correct_answers

        # ✅ Display Questions
        st.write("### Quiz Questions")
        if not st.session_state.submitted:
            for question, options in questions.items():
                    st.markdown(f'<hr><p style="margin-bottom: 5px; font-weight: bold;">{question}</p>', unsafe_allow_html=True)
                    st.session_state.user_answers[question] = st.radio("", options, key=question)

            
            if st.button("Submit"):
                st.session_state.submitted = True
                st.session_state.quiz_closed = True
                st.session_state.score = evaluate_quiz(st.session_state.user_answers, st.session_state.correct_answers)
                append_score_to_github(st.session_state.participant1,st.session_state.participant2, st.session_state.phone, st.session_state.email, st.session_state.score)
                st.rerun()
        else:
            st.write("✅ **Thank you for participating!** Your responses have been recorded.")

    if st.session_state.quiz_closed:
        st.write("✅ **Thank you for participating!** Your responses have been recorded.")
        st.stop()

    time.sleep(1)
    st.rerun()

if __name__ == "__main__":
    main() 
