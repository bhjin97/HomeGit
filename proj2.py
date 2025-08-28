import streamlit as st
import mysql.connector
from openai import OpenAI
from datetime import datetime
from dotenv import load_dotenv
import os

# ========== 환경 변수 로드 ==========
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# OpenAI 클라이언트 생성
client = OpenAI(api_key=OPENAI_API_KEY)

# ========== DB 연결 ==========
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="1234",
        database="Churo2_db"
    )

# ========== GPT 호출 ==========
def ask_gpt(user_id, user_input, emotion=None):
    chats = load_chats(user_id)
    messages = []
    for chat in chats:
        messages.append({"role": "user", "content": chat["question"]})
        messages.append({"role": "assistant", "content": chat["answer"]})

    if emotion:
        prompt = f"사용자 입력: {user_input}\n분석된 감정: {emotion}\n감정을 고려해 공감형 답변을 해주세요."
    else:
        prompt = user_input
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )
    return response.choices[0].message.content

# ========== 감정 분석 ==========
def analyze_emotion(user_input):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "다음 문장의 감정을 기쁨 슬픔 당황 분노 상처 중 하나의 단어로만 출력해."},
            {"role": "user", "content": user_input}
        ]
    )
    return response.choices[0].message.content.strip()

# ========== DB 저장 ==========
def save_chat_and_emotion(user_id, question, answer):
    conn = get_db_connection()
    cursor = conn.cursor()
    chat_date = datetime.now().date()
    chat_time = datetime.now().time()

    # UserChat 저장
    cursor.execute("""
        INSERT INTO UserChat (user_id, chat_date, chat_time, question, answer)
        VALUES (%s, %s, %s, %s, %s)
    """, (user_id, chat_date, chat_time, question, answer))
    chat_id = cursor.lastrowid   # 방금 저장된 chat_id 가져오기

    # 감정 분석
    dominant_emotion = analyze_emotion(question)

    # EmotionLog 저장
    cursor.execute("""
        INSERT INTO EmotionLog (chat_id, user_id, dominant_emotion)
        VALUES (%s, %s, %s)
    """, (chat_id, user_id, dominant_emotion))

    conn.commit()
    cursor.close()
    conn.close()
    return dominant_emotion

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

# ========== 로그인 검증 ==========
def get_user_id(login_id, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM Member WHERE login_id=%s AND password=%s", (login_id, password))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result[0] if result else None

# ========== 회원가입 ==========
def register_user(login_id, name, gender, age, address, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM Member WHERE login_id=%s", (login_id,))
    if cursor.fetchone()[0] > 0:
        cursor.close()
        conn.close()
        return False, "이미 존재하는 아이디입니다."

    cursor.execute("""
        INSERT INTO Member (login_id, name, gender, age, address, password, role)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (login_id, name, gender, age, address, password, "user"))

    conn.commit()
    cursor.close()
    conn.close()
    return True, "회원가입 성공! 로그인 해주세요."

# ========== dominant emotion 집계 ==========
def get_dominant_emotion(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT dominant_emotion, COUNT(*) as cnt
        FROM EmotionLog
        WHERE user_id = %s
        GROUP BY dominant_emotion
        ORDER BY cnt DESC
        LIMIT 1
    """, (user_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result[0] if result else None

# ========== 드라마 추천 ==========
def recommend_drama_by_emotion(emotion):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT title, description, poster_url, rating
        FROM Drama
        WHERE emotion_genre = %s
        ORDER BY rating DESC
        LIMIT 3
    """, (emotion,))
    dramas = cursor.fetchall()
    cursor.close()
    conn.close()
    return dramas

# ========== 영화 추천 ==========
def recommend_movie_by_emotion(emotion):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT title, description, poster_url, rating
        FROM Movie
        WHERE emotion_genre = %s
        ORDER BY rating DESC
        LIMIT 3
    """, (emotion,))
    movies = cursor.fetchall()
    cursor.close()
    conn.close()
    return movies

# ========== 음악 추천 ==========
def recommend_music_by_emotion(emotion):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT title, artist, album_cover
        FROM Music
        WHERE emotion_genre = %s
        LIMIT 3
    """, (emotion,))
    musics = cursor.fetchall()
    cursor.close()
    conn.close()
    return musics

# ========== 추천 출력 (3종) ==========
def show_recommendations_all(emotion):
    st.subheader("🎭 감정 기반 추천 결과")

    # 드라마
    st.markdown("### 📺 드라마")
    dramas = recommend_drama_by_emotion(emotion)
    if dramas:
        for d in dramas:
            if d.get("poster_url"):
                st.image(d["poster_url"], width=120)
            st.markdown(f"**{d['title']}** ⭐ {d.get('rating', '')}")
            st.caption(d.get("description", ""))
            st.markdown("---")
    else:
        st.warning("해당 감정에 맞는 드라마가 없습니다 😢")

    # 영화
    st.markdown("### 🎬 영화")
    movies = recommend_movie_by_emotion(emotion)
    if movies:
        for m in movies:
            if m.get("poster_url"):
                st.image(m["poster_url"], width=120)
            st.markdown(f"**{m['title']}** ⭐ {m.get('rating', '')}")
            st.caption(m.get("description", ""))
            st.markdown("---")
    else:
        st.warning("해당 감정에 맞는 영화가 없습니다 😢")

    # 음악
    st.markdown("### 🎵 음악")
    musics = recommend_music_by_emotion(emotion)
    if musics:
        for mu in musics:
            if mu.get("album_cover"):
                st.image(mu["album_cover"], width=120)
            st.markdown(f"**{mu['title']} - {mu['artist']}**")
            st.markdown("---")
    else:
        st.warning("해당 감정에 맞는 음악이 없습니다 😢")


# ========== Streamlit UI ==========
st.title("💬 심리 상담 챗봇")

# 페이지 상태
if "page" not in st.session_state:
    st.session_state["page"] = "login"

# 🟢 로그인 페이지
if st.session_state["page"] == "login" and "user_id" not in st.session_state:
    st.subheader("🔑 로그인")
    login_id = st.text_input("아이디")
    password = st.text_input("비밀번호", type="password")

    if st.button("로그인"):
        user_id = get_user_id(login_id, password)
        if user_id:
            st.session_state["user_id"] = user_id
            st.success(f"로그인 성공! user_id={user_id}")
            st.rerun()
        else:
            st.error("아이디/비밀번호가 잘못되었습니다.")

    if st.button("👉 회원가입"):
        st.session_state["page"] = "register"
        st.rerun()

# 🟢 회원가입 페이지
elif st.session_state["page"] == "register":
    st.subheader("📝 회원가입")

    new_id = st.text_input("아이디")
    new_name = st.text_input("이름")
    new_gender = st.selectbox("성별", ["M", "F", "Other"])
    new_age = st.number_input("나이", min_value=0, max_value=120, step=1)
    new_address = st.text_input("주소")
    new_pw = st.text_input("비밀번호", type="password")

    if st.button("가입하기"):
        success, msg = register_user(new_id, new_name, new_gender, new_age, new_address, new_pw)
        if success:
            st.success(msg)
            st.session_state["page"] = "login"
        else:
            st.error(msg)

    if st.button("⬅ 돌아가기"):
        st.session_state["page"] = "login"
        st.rerun()

# 🟢 채팅 페이지
elif "user_id" in st.session_state:
    user_id = st.session_state["user_id"]
    st.success(f"환영합니다! user_id={user_id}")
    chats = load_chats(user_id)
    for chat in chats:
        with st.chat_message("user"):
            st.markdown(chat["question"])
        with st.chat_message("assistant"):
            st.markdown(chat["answer"])

    user_input = st.chat_input("메시지를 입력하세요")
    if user_input:
        answer = ask_gpt(user_id, user_input)
        detected_emotion = save_chat_and_emotion(user_id, user_input, answer)
        with st.chat_message("user"):
            st.markdown(user_input)
        with st.chat_message("assistant"):
            st.markdown(answer)

    if st.button("추천 받기"):
        if chats:
            last_message = chats[-1]["question"]
            detected_emotion = analyze_emotion(last_message)
            st.info(f"최근 감정 분석 결과: **{detected_emotion}**")
            show_recommendations_all(detected_emotion)

    if st.button("세션 종료"):
        dominant_emotion = get_dominant_emotion(user_id)
        if dominant_emotion:
            st.success(f"세션 전체 감정 요약 → **{dominant_emotion}**")
        else:
            st.warning("대화 기록이 없어 세션 요약을 할 수 없습니다.")
