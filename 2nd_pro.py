import streamlit as st
import mysql.connector
import openai
from datetime import datetime
from dotenv import load_dotenv
import os

# ========== GPT API 키 ==========
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# ========== DB 연결 ==========
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="1234",
        database="Churo2_db"
    )

# ========== GPT 호출 ==========
def ask_gpt(user_input, emotion=None):
    if emotion:
        prompt = f"사용자 입력: {user_input}\n분석된 감정: {emotion}\n감정을 고려해 공감형 답변을 해주세요."
    else:
        prompt = user_input
    
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",  # 또는 gpt-4
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message["content"]

# ========== DB 저장 ==========
def save_chat(user_id, question, answer):
    conn = get_db_connection()
    cursor = conn.cursor()

    chat_date = datetime.now().date()
    chat_time = datetime.now().time()

    cursor.execute("""
        INSERT INTO UserChat (user_id, chat_date, chat_time, question, answer)
        VALUES (%s, %s, %s, %s, %s)
    """, (user_id, chat_date, chat_time, question, answer))

    conn.commit()
    cursor.close()
    conn.close()

# ========== DB 불러오기 ==========
def load_chats(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT chat_id, question, answer, chat_date, chat_time
        FROM UserChat
        WHERE user_id = %s
        ORDER BY chat_id ASC
    """, (user_id,))
    chats = cursor.fetchall()

    cursor.close()
    conn.close()
    return chats

# ========== Streamlit UI ==========
st.title("💬 심리 상담 챗봇")

# 임시 user_id (로그인 구현 전)
user_id = 1

# 사용자 입력창
user_input = st.text_input("메시지를 입력하세요:")

if st.button("보내기") and user_input:
    # GPT 응답
    answer = ask_gpt(user_input)

    # DB 저장
    save_chat(user_id, user_input, answer)

    # 입력창 초기화
    st.session_state["last_input"] = user_input
    st.session_state["last_answer"] = answer

# 대화 내역 불러오기
chats = load_chats(user_id)

# 출력
for chat in chats:
    st.markdown(f"👤 **User:** {chat['question']}")
    st.markdown(f"🤖 **AI:** {chat['answer']}")
    st.markdown("---")
