import streamlit as st
import mysql.connector
from openai import OpenAI
from datetime import datetime
from dotenv import load_dotenv
import os
from streamlit_option_menu import option_menu
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
import plotly.express as px
from PIL import Image
import io
import base64, html
import json

def load_avatar(path):
    img = Image.open(path)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

GPT_AVATAR_PATH = load_avatar("D:/whynot/githome/data/churros.png")
USER_AVATAR_PATH = load_avatar("D:/whynot/githome/data/profile.jpg")

from pathlib import Path
CHAR_IMG_PATH = Path("D:/whynot/githome/data/image.png")  # 캐릭터 이미지


st.markdown("""
<style>
.chat-row{display:flex; gap:8px; margin:8px 0; align-items:flex-end;}
.chat-row.user{justify-content:flex-end;}
.chat-row.bot{justify-content:flex-start;}
.chat-bubble{
  max-width:70%;
  padding:12px 16px;
  border-radius:18px;
  line-height:1.55;
  font-size:16px;
  box-shadow:0 4px 14px rgba(0,0,0,.06);
  word-break:break-word;
  white-space:pre-wrap;
}
.chat-bubble.user{background:#e8f5e9; border-top-right-radius:6px;}
.chat-bubble.bot{background:#f5f7fb; border-top-left-radius:6px;}
.chat-avatar{
  width:36px; height:36px; border-radius:50%;
  object-fit:cover;
  box-shadow:0 2px 6px rgba(0,0,0,.12);
}
</style>
""", unsafe_allow_html=True)

def _bytes_to_data_uri(img_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(img_bytes).decode()

def render_bubble(role: str, text: str, avatar_bytes: bytes = None):
    """role: 'user' or 'bot'."""
    bubble_cls = "user" if role == "user" else "bot"
    # 안전하게 특수문자 이스케이프
    safe_text = html.escape(text)
    # 간단한 이모지/줄바꿈 허용하고 싶으면 아래 라인 사용
    # safe_text = safe_text.replace("\\n", "<br>")
    av_html = ""
    if avatar_bytes:
        av_html = f'<img class="chat-avatar" src="{_bytes_to_data_uri(avatar_bytes)}" />'

    if role == "user":
        # [말풍선] [아바타]
        html_block = f'''
        <div class="chat-row user">
          <div class="chat-bubble user">{safe_text}</div>
          {av_html}
        </div>
        '''
    else:
        # [아바타] [말풍선]
        html_block = f'''
        <div class="chat-row bot">
          {av_html}
          <div class="chat-bubble bot">{safe_text}</div>
        </div>
        '''
    st.markdown(html_block, unsafe_allow_html=True)

# 페이지 기본 설정
st.set_page_config(page_title="츄러스미 심리케어",layout='wide')

# ✅ 세션 상태 초기화 (맨 위에서 딱 한 번만 실행)
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "role" not in st.session_state:
    st.session_state.role = ""
if "user_id" not in st.session_state:
    st.session_state.user_id = None

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
# 분포까지 계산
def analyze_emotion_distribution(user_input: str):
    """
    반환 예:
    {
      "joy": 0.12, "sadness": 0.55, "anger": 0.06, "hurt": 0.10, "embarrassed": 0.07, "anxiety": 0.10,
      "dominant_emotion": "슬픔"
    }
    """
    system = (
        "다음 한국어 문장의 감정 분포를 JSON으로만 출력해.\n"
        "labels = [기쁨(joy), 슬픔(sadness), 분노(anger), 상처(hurt), 당황(embarrassed), 불안(anxiety)].\n"
        "요구 형식: {\"joy\":0~1, \"sadness\":0~1, \"anger\":0~1, \"hurt\":0~1, \"embarrassed\":0~1, \"anxiety\":0~1, \"dominant_emotion\":\"라벨\"}\n"
        "합계는 1.0에 가깝게. dominant_emotion은 가장 높은 감정의 한국어 라벨(기쁨/슬픔/분노/상처/당황/불안)만."
    )
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_input}
        ],
        temperature=0.3
    )
    txt = resp.choices[0].message.content.strip()

    # JSON 파싱 & 방어로직
    try:
        data = json.loads(txt)
    except Exception:
        # 파싱 실패 시 간단 분류로 폴백
        data = {}

    # 키 보정 & 기본값
    keys = ["joy","sadness","anger","hurt","embarrassed","anxiety"]
    for k in keys:
        data[k] = float(data.get(k, 0))

    # 정규화(합 0이면 그대로 0, 아니면 1.0로 맞춤)
    s = sum(data[k] for k in keys)
    if s > 0:
        for k in keys:
            data[k] = round(data[k] / s, 3)

    # dominant_emotion 보정
    ko_map = {
        "joy":"기쁨", "sadness":"슬픔", "anger":"분노",
        "hurt":"상처", "embarrassed":"당황", "anxiety":"불안"
    }
    if not data.get("dominant_emotion"):
        # 스코어 최대값으로 결정
        top = max(keys, key=lambda k: data[k])
        data["dominant_emotion"] = ko_map[top]
    else:
        # 혹시 영문 키면 한국어로 치환
        de = data["dominant_emotion"]
        inv = {v:k for k,v in ko_map.items()}
        if de in inv:
            top = inv[de]
        else:
            top = max(keys, key=lambda k: data[k])
            data["dominant_emotion"] = ko_map[top]

    return data

# 이전 코드와 호환: 지배감정만 필요할 때
def analyze_emotion(user_input: str) -> str:
    return analyze_emotion_distribution(user_input)["dominant_emotion"]

# ========== DB 저장 ==========
def save_chat_and_emotion(user_id, question, answer):
    conn = get_db_connection()
    cursor = conn.cursor()
    chat_date = datetime.now().date()
    chat_time = datetime.now().time()

    # 1) UserChat 저장
    cursor.execute("""
        INSERT INTO UserChat (user_id, chat_date, chat_time, question, answer)
        VALUES (%s, %s, %s, %s, %s)
    """, (user_id, chat_date, chat_time, question, answer))
    chat_id = cursor.lastrowid

    # 2) 감정 분포 분석
    dist = analyze_emotion_distribution(question)

    # 3) EmotionLog 저장 (점수 + 지배감정)
    #    - 점수 컬럼이 실제로 있는 경우에만 값을 넣도록 구성
    cursor.execute("""
        INSERT INTO EmotionLog
            (chat_id, user_id, joy_score, sadness_score, anger_score, hurt_score, embarrassed_score, anxiety_score, dominant_emotion)
        VALUES
            (%s, %s, %s,  %s, %s, %s, %s, %s, %s)
    """, (
        chat_id, user_id,
        dist["joy"], dist["sadness"], dist["anger"], dist["hurt"], dist["embarrassed"], dist["anxiety"],
        dist["dominant_emotion"]
    ))

    conn.commit()
    cursor.close()
    conn.close()

    return dist["dominant_emotion"]  # 기존 사용처와 호환


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
def get_user_info(login_id, password):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT user_id, login_id, role FROM Member WHERE login_id=%s AND password=%s",
        (login_id, password)
    )
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result   # {'user_id': 1, 'login_id':'abc', 'role':'user'}

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

# 드라마 추천
def recommend_drama_by_emotion(emotion):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT drama_id, title, description, poster_url, rating
        FROM Drama
        WHERE emotion_genre = %s
        ORDER BY RAND()
        LIMIT 3
    """, (emotion,))
    dramas = cursor.fetchall()
    cursor.close()
    conn.close()
    return dramas

# 영화 추천
def recommend_movie_by_emotion(emotion):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT movie_id, title, description, poster_url, rating
        FROM Movie
        WHERE emotion_genre = %s
        ORDER BY RAND()
        LIMIT 3
    """, (emotion,))
    movies = cursor.fetchall()
    cursor.close()
    conn.close()
    return movies

# 음악 추천
def recommend_music_by_emotion(emotion):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT music_id, title, artist, album_cover
        FROM Music
        WHERE emotion_genre = %s
        LIMIT 3
    """, (emotion,))
    musics = cursor.fetchall()
    cursor.close()
    conn.close()
    return musics


# ========== 추천 저장 ==========
def save_recommendation(user_id, emotion, content_type, content_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO UserRecommendation (user_id, emotion, content_type, content_id)
        VALUES (%s, %s, %s, %s)
    """, (user_id, emotion, content_type, content_id))
    conn.commit()
    cursor.close()
    conn.close()

# ========== 추천 출력 (3종) ==========
def show_recommendations_all(emotion):
    st.subheader(f"🎭 {emotion} 감정 기반 추천 콘텐츠")

    tabs = st.tabs(["🎬 영화", "📺 드라마", "🎵 음악" ])

    # 🎵 음악 탭
    with tabs[2]:
        musics = recommend_music_by_emotion(emotion)
        if musics:
            cols = st.columns(3)
            for idx, mu in enumerate(musics):
                with cols[idx % 3]:
                    if mu.get("album_cover"):
                        st.image(mu["album_cover"], width=120)
                    st.markdown(f"**{mu['title']}**")
                    st.caption(f"가수: {mu['artist']}")
                    save_recommendation(st.session_state["user_id"], emotion, "music", mu["music_id"])
        else:
            st.warning("해당 감정에 맞는 음악이 없습니다 😢")

    # 📺 드라마 탭
    with tabs[1]:
        dramas = recommend_drama_by_emotion(emotion)
        if dramas:
            cols = st.columns(3)
            for idx, d in enumerate(dramas):
                with cols[idx % 3]:
                    if d.get("poster_url"):
                        st.image(d["poster_url"], width=120)
                    st.markdown(f"**{d['title']}** ⭐ {d.get('rating','')}")

                    # ✅ 줄거리 자르기
                    desc = d.get("description", "")
                    if desc and len(desc) > 100:
                        desc = desc[:100] + "..."
                    st.caption(desc)

                    save_recommendation(st.session_state["user_id"], emotion, "drama", d["drama_id"])
        else:
            st.warning("해당 감정에 맞는 드라마가 없습니다 😢")

    # 🎬 영화 탭
    with tabs[0]:
        movies = recommend_movie_by_emotion(emotion)
        if movies:
            cols = st.columns(3)
            for idx, m in enumerate(movies):
                with cols[idx % 3]:
                    if m.get("poster_url"):
                        st.image(m["poster_url"], width=120)
                    st.markdown(f"**{m['title']}** ⭐ {m.get('rating','')}")

                    # ✅ 줄거리 자르기
                    desc = m.get("description", "")
                    if desc and len(desc) > 100:
                        desc = desc[:100] + "..."
                    st.caption(desc)

                    save_recommendation(st.session_state["user_id"], emotion, "movie", m["movie_id"])
        else:
            st.warning("해당 감정에 맞는 영화가 없습니다 😢")

# ======================================= Dash Board ==========================================
# 세션 상태 초기화 -------------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""
    st.session_state.user_id = None  
    
def my_dashboard():
    # 안전하게 기본값
    username = st.session_state.get("username", "")
    user_id = st.session_state.get("user_id")
    st.subheader(f"{username}님의 심리 대시보드 💉")

    if not user_id:
        st.warning("로그인이 필요합니다.")
        return

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 0) 날짜/점수용 기반 데이터: 날짜별 우울점수(가중합) 계산
    #    우울점수 = anxiety*0.4 + hurt*0.3 + sadness*0.3  (0~1 범위라면 100배해서 보이게)
    cursor.execute("""
        SELECT uc.chat_date,
               AVG(COALESCE(el.anxiety_score,0)*0.4 + 
                   COALESCE(el.hurt_score,0)*0.3 + 
                   COALESCE(el.sadness_score,0)*0.3) AS depression_raw
        FROM EmotionLog el
        JOIN UserChat uc ON el.chat_id = uc.chat_id
        WHERE el.user_id = %s
        GROUP BY uc.chat_date
        ORDER BY uc.chat_date
    """, (user_id,))
    rows = cursor.fetchall()

    # -------------------------------------------
    # ① 우울점수 집계용 DataFrame 구성
    # -------------------------------------------
    df_psych = pd.DataFrame(rows, columns=["chat_date", "depression_raw"]) if rows else \
            pd.DataFrame(columns=["chat_date", "depression_raw"])

    if not df_psych.empty:
        # 날짜/점수 보정
        df_psych["chat_date"] = pd.to_datetime(df_psych["chat_date"], errors="coerce")
        df_psych["depression_raw"] = pd.to_numeric(df_psych["depression_raw"], errors="coerce").fillna(0.0)
        df_psych["우울점수"] = (df_psych["depression_raw"] * 100).round(1)

        # 최종적으로 '날짜' 컬럼으로 사용
        df_psych = df_psych.rename(columns={"chat_date": "날짜"})

        # 오늘 값 / 최고값
        today_mask = df_psych["날짜"].dt.date == datetime.now().date()
        today_depression = float(df_psych.loc[today_mask, "우울점수"].iloc[-1]) if today_mask.any() else None
        max_depression = float(df_psych["우울점수"].max())
    else:
        today_depression = None
        max_depression = None

    # -------------------------------------------
    # ② "오늘 사용시간" 추정 (UserChat의 first/last time 기준)
    # -------------------------------------------
    cursor.execute("""
        SELECT MIN(chat_time) AS first_time, MAX(chat_time) AS last_time
        FROM UserChat
        WHERE user_id = %s AND chat_date = CURRENT_DATE()
    """, (user_id,))
    today_session = cursor.fetchone()

    def _to_time(v):
        # v가 timedelta면 00:00 기준으로 변환, datetime이면 time() 추출, time이면 그대로 반환
        if v is None:
            return None
        from datetime import timedelta
        if isinstance(v, timedelta):
            return (datetime.min + v).time()
        if hasattr(v, "time"):
            # datetime.datetime인 경우
            try:
                return v.time()
            except Exception:
                pass
        return v  # 이미 time이거나 파서 불필요한 타입은 그대로

    ft = _to_time(today_session["first_time"]) if today_session else None
    lt = _to_time(today_session["last_time"]) if today_session else None

    if ft and lt:
        t1 = datetime.combine(datetime.today().date(), ft)
        t2 = datetime.combine(datetime.today().date(), lt)
        usage_minutes = max(0, int((t2 - t1).total_seconds() // 60))
    else:
        usage_minutes = 0

    total_usage_hour = usage_minutes // 60
    total_usage_min = usage_minutes % 60


    # 2) 상단 KPI + 날짜 선택
    col1, col2, col3, col4 = st.columns([2,1,1,1])

    # 날짜 범위 계산 (df_psych가 비었을 때 대비)
    if not df_psych.empty:
        date_series = pd.to_datetime(df_psych["날짜"], errors="coerce").dropna()
        login_date_min = date_series.min().date()
        login_date_default = date_series.max().date()
    else:
        login_date_min = login_date_default = datetime.now().date()

    with col1:
        st.markdown("**📅 로그인 날짜 선택**")
        # ✅ 항상 생성되도록 위치 이동 + 컬럼 안에서 렌더
        login_date = st.date_input(
            "📅 로그인 날짜",
            value=login_date_default,
            min_value=login_date_min,
            max_value=login_date_default
        )

    with col2:
        st.metric(label="오늘 사용 시간", value=f"{total_usage_hour}시간 {total_usage_min}분", delta="+0분")
    with col3:
        st.metric(label="오늘 우울 점수", value=(f"😔 {today_depression:.1f}" if today_depression is not None else "—"))
    with col4:
        st.metric(label="최근 최고 우울 점수", value=(f"📈 {max_depression:.1f}" if max_depression is not None else "—"))

    st.divider()

    # 3) 좌측 탭들: 기본정보/히스토리/요약/행동
    colL, colM, colR = st.columns([1,1,1])

    with colL:
        tabs = st.tabs(["기본 정보", "상담 히스토리", "최근 상담 요약", "추천 행동"])

        # 기본 정보
        with tabs[0]:
            cursor.execute("SELECT name, gender, age, address FROM Member WHERE user_id=%s", (user_id,))
            member = cursor.fetchone() or {"name":"-", "gender":"-", "age":"-", "address":"-"}
            st.markdown("**📝 기본 정보**")
            st.markdown(f"- 이름: {member.get('name','-')}")
            st.markdown(f"- 성별: {member.get('gender','-')}")
            st.markdown(f"- 나이: {member.get('age','-')}")
            st.markdown(f"- 주소: {member.get('address','-')}")

        # 상담 히스토리 (최근 5개)
        with tabs[1]:
            st.markdown("**📁 상담 히스토리**")
            cursor.execute("""
                SELECT chat_date, question 
                FROM userchat 
                WHERE user_id=%s 
                ORDER BY chat_id DESC 
                LIMIT 5
            """, (user_id,))
            history = cursor.fetchall()
            if history:
                for h in history:
                    st.write(f"- {h['chat_date']} 👉 {h['question'][:60]}{'...' if len(h['question'])>60 else ''}")
            else:
                st.info("히스토리가 없습니다.")

        # 최근 상담 요약 (가장 최신 1개)
        with tabs[2]:
            st.markdown("**🌧️ 최근 상담 요약**")
            cursor.execute("""
                SELECT cs.summary_text
                FROM CounselingSummary AS cs
                JOIN UserChat          AS uc ON cs.chat_id = uc.chat_id
                WHERE uc.user_id = %s
                ORDER BY cs.summary_id DESC
                LIMIT 1
            """, (user_id,))
            summary = cursor.fetchone()
            if summary and summary.get("summary_text"):
                st.info(summary["summary_text"])
            else:
                st.write("요약 데이터가 없습니다.")

        # 추천 행동 (정적 문구)
        with tabs[3]:
            st.markdown("**💡 추천 행동**")
            st.markdown("""
            - 하루 5분 감정 기록하기 (글로 적으면 감정 정리에 도움)
            - 주 30분 산책/취미 활동 (불안·무기력 완화)
            - 가족·친구와 짧은 소통 시간 갖기 (외로움 완화)
            - 필요 시 전문가 상담 연계
            """)

    # 4) 가운데: 선택 날짜 감정 레이더
    with colM:
        st.markdown("**🔯 감정상태분석**")
        cursor.execute("""
            SELECT 
            AVG(COALESCE(joy_score,0))         AS joy,
            AVG(COALESCE(sadness_score,0))     AS sadness,
            AVG(COALESCE(anger_score,0))       AS anger,
            AVG(COALESCE(hurt_score,0))        AS hurt,
            AVG(COALESCE(embarrassed_score,0)) AS embarrassed,
            AVG(COALESCE(anxiety_score,0))     AS anxiety
            FROM EmotionLog el
            JOIN UserChat uc ON el.chat_id = uc.chat_id
            WHERE el.user_id=%s AND uc.chat_date=%s
        """, (user_id, login_date))
        emo = cursor.fetchone()

        if emo and any(v for v in emo.values() if v is not None):
            emotions_labels = ["기쁨","슬픔","분노","상처","당황","불안"]
            values = [
                emo["joy"] or 0, emo["sadness"] or 0, emo["anger"] or 0,
                emo["hurt"] or 0, emo["embarrassed"] or 0, emo["anxiety"] or 0
            ]
            fig_radar = go.Figure()
            fig_radar.add_trace(go.Scatterpolar(
                r=values + [values[0]],
                theta=emotions_labels + [emotions_labels[0]],
                fill="toself",
                name="감정 점수"
            ))

            # 값 스케일 (동적 범위)
            max_val = max([float(v or 0) for v in values]) if values else 1
            if max_val <= 1:   # 값이 0~1 사이일 때
                y_max = min(1.0, max_val * 1.5)  # 최대값보다 살짝 크게
            else:              # 값이 0~100 사이일 때
                y_max = min(100.0, max_val * 1.2)
                
            fig_radar.update_layout(
                polar=dict(
                    radialaxis=dict(
                        visible=True,
                        range=[0, y_max],   # ✅ 유동적으로 조정된 최대치
                        gridcolor="rgba(0,0,0,0.12)",
                        tickfont=dict(size=12)
                    ),
                    angularaxis=dict(tickfont=dict(size=13))
                ),
                height=350,
                margin=dict(l=30, r=30, t=20, b=20),
                showlegend=False
            )
            st.plotly_chart(fig_radar, use_container_width=True)
            
            # 대표 감정 코멘트
            idx_max = int(np.argmax(values)) if values else 0
            dominant_emotion = emotions_labels[idx_max]
            emotion_comments = {
                "기쁨": "행복한 하루를 보내셨군요! 이 기분 오래 간직하세요 😊",
                "슬픔": "마음이 무거운 날이었네요. 감정을 인정하는 건 용기예요 💙",
                "불안": "불안이 느껴지네요. 천천히 숨을 쉬며 마음을 돌보세요.",
                "분노": "화가 났던 일이 있었군요. 감정을 표현하는 건 건강한 행동이에요.",
                "당황": "예상치 못한 일이 있었나요? 잠시 멈추고 차분히 생각해봐요.",
                "상처": "상처받은 마음, 혼자 아파하지 마세요. 당신은 소중한 사람이에요 💖"
            }
            st.info(emotion_comments.get(dominant_emotion, "당신의 감정을 응원합니다 💗"))
        else:
            st.warning("선택한 날짜의 감정 데이터가 없습니다.")

    # 5) 우측: 우울점수 변화 추이 + 북마크
    with colR:
        st.markdown("**📉 우울점수변화추이**")
        if not df_psych.empty:
            fig_line = go.Figure()
            fig_line.add_trace(go.Scatter(
                # ✅ 'chat_date' → '날짜' 로 통일
                x=df_psych["날짜"],
                y=df_psych["우울점수"],
                mode="lines+markers",
                line=dict(shape="spline")
            ))
            fig_line.update_layout(yaxis_range=[0, 100], height=220, margin=dict(l=30,r=30,t=20,b=20))
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("아직 우울점수 데이터가 없습니다.")

        st.markdown("**📌 북마크 목록**")
        cursor.execute("""
            SELECT b.bookmark_id, m.title AS movie, d.title AS drama, mu.title AS music
            FROM UserBookmark b
            LEFT JOIN Movie m ON b.movie_id = m.movie_id
            LEFT JOIN Drama d ON b.drama_id = d.drama_id
            LEFT JOIN Music mu ON b.music_id = mu.music_id
            WHERE b.user_id = %s
            ORDER BY b.created_at DESC
            LIMIT 5
        """, (user_id,))
        bookmarks = cursor.fetchall()
        if bookmarks:
            for bm in bookmarks:
                if bm.get("movie"): st.write(f"🎬 영화 - {bm['movie']}")
                if bm.get("drama"): st.write(f"📺 드라마 - {bm['drama']}")
                if bm.get("music"): st.write(f"🎵 노래 - {bm['music']}")
        else:
            st.caption("북마크가 아직 없습니다.")

    cursor.close()
    conn.close()

def logout():
    # 세션 상태 초기화
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""
    st.session_state.user_id = None
    
    st.success("👋 성공적으로 로그아웃되었습니다.")
    st.rerun()  # 🔥 rerun 해서 로그인 화면으로 돌아가기

def truncate_text(text, max_len=60):
    if not text:
        return ""
    return text if len(text) <= max_len else text[:max_len] + "..."

def render_card(rec, content_type):
    if rec.get("cover"):
        st.image(rec["cover"], width=120)

    if content_type == "music":
        st.markdown(f"🎵 **{rec['title']} - {rec['artist']}**")
    else:
        st.markdown(f"**{rec['title']}**")

    # ✅ 줄거리 고정 길이 + 카드 스타일
    st.markdown(
        f"<div style='min-height:60px; max-height:60px; overflow:hidden; font-size:13px; color:gray;'>"
        f"{truncate_text(rec.get('description',''), 60)}  "
        f"(감정: {rec['emotion']})</div>",
        unsafe_allow_html=True
    )
    st.markdown("---")

def content():
    st.subheader("🎬 내가 추천받은 콘텐츠 기록")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT r.emotion, r.content_type, r.created_at,
               COALESCE(m.title, d.title, mu.title) as title,
               COALESCE(m.poster_url, d.poster_url, mu.album_cover) as cover,
               COALESCE(m.description, d.description, '') as description,
               mu.artist
        FROM UserRecommendation r
        LEFT JOIN Movie m ON r.content_type='movie' AND r.content_id=m.movie_id
        LEFT JOIN Drama d ON r.content_type='drama' AND r.content_id=d.drama_id
        LEFT JOIN Music mu ON r.content_type='music' AND r.content_id=mu.music_id
        WHERE r.user_id=%s
        ORDER BY r.created_at DESC
        LIMIT 30
    """, (st.session_state["user_id"],))
    recs = cursor.fetchall()
    cursor.close()
    conn.close()

    if not recs:
        st.info("아직 추천받은 콘텐츠 기록이 없습니다.")
        return

    # 👉 탭 나누기
    tab_movie, tab_drama, tab_music = st.tabs(["🎬 영화", "📺 드라마", "🎵 음악" ])

    # 🎵 음악 탭
    with tab_music:
        musics = [r for r in recs if r["content_type"] == "music"]
        if musics:
            cols = st.columns(3)
            for idx, rec in enumerate(musics):
                with cols[idx % 3]:
                    if rec["cover"]:
                        st.image(rec["cover"], width=120)
                    st.markdown(f"**{rec['title']} - {rec['artist']}**")
                    st.caption(f"감정: {rec['emotion']}")
        else:
            st.warning("추천받은 음악 기록이 없습니다.")

    # 📺 드라마 탭
    with tab_drama:
        dramas = [r for r in recs if r["content_type"] == "drama"]
        if dramas:
            cols = st.columns(3)
            for idx, rec in enumerate(dramas):
                with cols[idx % 3]:
                    render_card(rec, "drama")   # 카드 함수 사용
        else:
            st.warning("추천받은 드라마 기록이 없습니다.")


    # 🎬 영화 탭
    with tab_movie:
        movies = [r for r in recs if r["content_type"] == "movie"]
        if movies:
            cols = st.columns(3)
            for idx, rec in enumerate(movies):
                with cols[idx % 3]:
                    render_card(rec, "movie")   # 카드 함수 사용
        else:
            st.warning("추천받은 영화 기록이 없습니다.")

def hospital():
    st.title("🏥심린이 병원추천")

    # 기본 위치: 서울 시청
    default_lat, default_lon = 37.5665, 126.9780

    # 사용자 위치 입력
    user_location = st.text_input("📍 현재 위치를 입력하세요 (예: 서울시 강남구 역삼동)")

    # 지도 초기화
    m = folium.Map(location=[default_lat, default_lon], zoom_start=13)

    # 사용자 위치 입력 시 처리
    if user_location:
        geolocator = Nominatim(user_agent="myGeocoder")
        location = geolocator.geocode(user_location)

        if location:
            lat, lon = location.latitude, location.longitude

            # 내 위치 마커
            folium.Marker(
                [lat, lon], tooltip="내 위치", icon=folium.Icon(color="blue")
            ).add_to(m)

            # 병원 예시 마커 (임의 좌표, 실제 데이터로 바꿀 수 있음)
            folium.Marker(
                [lat + 0.001, lon + 0.001],
                tooltip="힐링 정신건강의학과의원",
                icon=folium.Icon(color="green")
            ).add_to(m)

            folium.Marker(
                [lat - 0.001, lon - 0.001],
                tooltip="마음숲 클리닉",
                icon=folium.Icon(color="green")
            ).add_to(m)

            # 중심을 사용자 위치로 이동
            m.location = [lat, lon]
            m.zoom_start = 15

        else:
            st.error("❌ 위치를 찾을 수 없습니다. 다시 입력해 주세요.")
    else:
        st.info("📌 위치를 입력하면 주변 병원이 지도에 표시됩니다.")

        # 지도 표시
    col1, col2, col3 = st.columns([2,1,1])
    with col1:
        st_folium(m, width=700, height=450)
    with col2:
        st.text("거리기반")
    with col3:
        st.text("평점기반")
        
def chat_header():
    col1, col2 = st.columns([1, 8])  # 왼쪽: 이미지 / 오른쪽: 타이틀+설명

    with col1:
        st.image("D:/whynot/githome/data/churros.png", width=120)  # 심린이 캐릭터

    with col2:
        st.markdown("""
        ### 츄러스미~! 나와 대화해볼래? 👋  
        심린이한테 고민을 털어놔보세요. 🧡
        """)
        st.caption("안녕하세요! 필요한 도움이 있으신가요? 당신의 이야기를 들려주세요. 😊")

def user_dashboard():
    # 사이드바 메뉴
    with st.sidebar:
        selected = option_menu(
            "츄러스미 메뉴",
            ["나의 대시보드", "심린이랑 대화하기", "심린이 추천병원", "심린이 추천 콘텐츠", "로그아웃"],
            icons=['bar-chart', 'chat-dots', 'hospital', 'camera-video', 'box-arrow-right'],
            default_index=0,
            styles={
                "container": {"padding": "5px"},
                "nav-link": {"font-size": "16px", "text-align": "left", "margin":"0px", "--hover-color": "#eee"},
                "nav-link-selected": {"background-color": "#b3d9ff"},
            }
        )

    if selected == '나의 대시보드':
        st.title(f"🙋 환영합니다, {st.session_state['username']}님") 
        my_dashboard()

     # === 대화 불러오기 ===
    elif selected == '심린이랑 대화하기':   
        chat_header()    
        chats = load_chats(st.session_state["user_id"])
        for chat in chats:
            render_bubble("user", chat["question"], USER_AVATAR_PATH)
            render_bubble("bot",  chat["answer"],   GPT_AVATAR_PATH)

        # 입력창
        user_input = st.chat_input("메시지를 입력하세요…")
        if user_input:
            # 1) DB 저장 + GPT 호출
            answer = ask_gpt(st.session_state["user_id"], user_input)
            detected_emotion = save_chat_and_emotion(st.session_state["user_id"], user_input, answer)

            # 2) 화면에 바로 말풍선으로 렌더
            render_bubble("user", user_input, USER_AVATAR_PATH)
            render_bubble("bot", answer, GPT_AVATAR_PATH)

            st.rerun()

        if user_input:
            # 1) DB 저장 + GPT 호출
            answer = ask_gpt(st.session_state["user_id"], user_input)
            detected_emotion = save_chat_and_emotion(st.session_state["user_id"], user_input, answer)

            # 2) 세션에 추가
            with st.chat_message("user", avatar=USER_AVATAR_PATH):
                st.markdown(user_input)
            with st.chat_message("assistant", avatar=GPT_AVATAR_PATH):
                st.markdown(answer)

            st.rerun()

        # === 추천/세션 종료 버튼 ===
        col1, col2 = st.columns(2)
        with col1:
            if st.button("추천 받기"):
                if chats:
                    last_message = chats[-1]["question"]
                    detected_emotion = analyze_emotion(last_message)
                    st.info(f"최근 감정 분석 결과: **{detected_emotion}**")
                    show_recommendations_all(detected_emotion)

        with col2:
            if st.button("세션 종료"):
                dominant_emotion = get_dominant_emotion(st.session_state["user_id"])
                if dominant_emotion:
                    st.success(f"세션 전체 감정 요약 → **{dominant_emotion}**")
                    show_recommendations_all(dominant_emotion)
                else:
                    st.warning("대화 기록이 없어 세션 요약을 할 수 없습니다.")


    elif selected == '심린이 추천병원':
        hospital()

    elif selected == '심린이 추천 콘텐츠':
        st.title("🎭 감정 기반 추천 콘텐츠")
        content()

    else:
        logout()

# 페이지 상태 초기화
if "page" not in st.session_state:
    st.session_state["page"] = "login"

# =========================
# 🟢 로그인 페이지 (이미지 + 폼 나란히)
# =========================
if st.session_state["page"] == "login" and not st.session_state.get("user_id"):
    st.title("💬 심리 상담 챗봇")
    col_img, col_form = st.columns([1, 2], vertical_alignment="center")

    with col_img:
        try:
            st.image(str(CHAR_IMG_PATH), width=260)  # 캐릭터 크기
        except Exception:
            st.markdown("<div style='font-size:100px'>🐰</div>", unsafe_allow_html=True)

    with col_form:
        st.markdown("### 🔑 로그인")
        login_id = st.text_input("아이디", placeholder="아이디 입력", label_visibility="collapsed")
        password = st.text_input("비밀번호", type="password", placeholder="비밀번호 입력", label_visibility="collapsed")

        c1, c2, c3 = st.columns([1,1,1])
        with c1:
            if st.button("로그인", use_container_width=True):
                user_info = get_user_info(login_id, password)
                if user_info:
                    st.session_state["user_id"]   = user_info["user_id"]
                    st.session_state["username"]  = user_info["login_id"]
                    st.session_state["role"]      = user_info["role"]
                    st.success(f"로그인 성공! {st.session_state['username']}님 ({user_info['role']})")
                    st.rerun()
                else:
                    st.error("아이디/비밀번호가 잘못되었습니다.")
        with c2:
            if st.button("👉 회원가입", use_container_width=True):
                st.session_state["page"] = "register"
                st.rerun()
        with c3:
            if st.button("👤 비회원 체험", use_container_width=True):
                st.session_state["role"] = "guest"
                st.session_state["user_id"] = 2   # DB에 있는 guest 계정
                st.session_state["username"] = "비회원"
                st.session_state["logged_in"] = True
                st.rerun()

# =========================
# 🟢 회원가입 페이지 (이미지 + 폼 나란히)
# =========================
elif st.session_state["page"] == "register":
    col_img, col_form = st.columns([1, 2], vertical_alignment="center")

    with col_img:
        try:
            st.image(str(CHAR_IMG_PATH), width=220)
        except Exception:
            st.markdown("<div style='font-size:90px'>🐰</div>", unsafe_allow_html=True)

    with col_form:
        st.markdown("### 📝 회원가입")
        new_id     = st.text_input("아이디", placeholder="아이디", label_visibility="collapsed")
        new_name   = st.text_input("이름", placeholder="이름", label_visibility="collapsed")
        new_gender = st.selectbox("성별", ["M", "F", "Other"])
        new_age    = st.number_input("나이", min_value=0, max_value=120, step=1)
        new_address= st.text_input("주소", placeholder="주소", label_visibility="collapsed")
        new_pw     = st.text_input("비밀번호", type="password", placeholder="비밀번호", label_visibility="collapsed")

        c1, c2 = st.columns([1,1])
        with c1:
            if st.button("가입하기", use_container_width=True):
                success, msg = register_user(new_id, new_name, new_gender, new_age, new_address, new_pw)
                if success:
                    st.success(msg)
                    st.session_state["page"] = "login"
                else:
                    st.error(msg)
        with c2:
            if st.button("⬅ 돌아가기", use_container_width=True):
                st.session_state["page"] = "login"
                st.rerun()

# ======== 비회원 파트 =========
def u_my_dashboard():
    st.subheader(f"{st.session_state.username}님의 심리 대시보드 💉")
    st.error("🔒 회원가입 후 로그인하면, 아래 화면과 유사한 전용 대시보드 화면이 나타납니다", icon="⚠️")
    
    col1, col2, col3 = st.columns([2,2,2])
    with col2:
        st.markdown("### 가입하면 이런 기능을 쓸 수 있어요!")
        col7, col4,col5 = st.columns([1,2,1])
        st.markdown("**⭐개인 맞춤형 감정 분석 차트**")
        st.markdown(" **⭐시간별 우울 점수 변화 추이**")
        st.markdown(" **⭐심리 챗봇과 연계된 맞춤 행동 추천**")
        st.markdown(" **⭐심리 맟춤 미디어 추천까지!!!**")
        with col4:
            img = Image.open("D:/whynot/githome/data/churro2.png")
            st.image(img, width=450) # 츄러스미 이미지 삽입

    with col1:
        col5, col6 = st.columns([1,2])
        with col6:
            st.divider()
            st.metric(
                label="오늘 사용 시간",
                value="1시간 30분",
                delta="+30분"  
            )
            st.divider()
            st.metric(
            label="오늘 우울 점수",
            value="😔 25 점",
            delta="+0.5"  
        )
            st.divider()
            st.metric(
            label="최근 최고 우울 점수",
            value="📈 75 점",
            delta="+1.0"  # 전일 대비 변화 예시
        )
            st.divider()

    with col3:
        st.markdown(''' **🔯감정상태분석**''')
        # 가상 감정 데이터
        emotions = ["행복", "슬픔", "분노", "불안", "놀람", "평온"]
        values = [80, 40, 30, 60, 70, 90]  # 가상 수치

        # 레이더 차트 생성
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(
            r=values + [values[0]],
            theta=emotions + [emotions[0]],
            fill='toself',
            name='감정 점수',
            text=[f"{emo}: {val}" for emo, val in zip(emotions, values)] + [f"{emotions[0]}: {values[0]}"],
            hoverinfo='text'
        ))

        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            showlegend=False,
            margin=dict(l=30, r=30, t=30, b=30),
            height=250,
            paper_bgcolor='#f5faff'
        )

        # Streamlit 출력
        st.plotly_chart(fig_radar, use_container_width=True)
        st.divider()    
        # ✅ 가상 데이터 생성
        dates = pd.date_range(start="2025-08-20", periods=7, freq="D")
        scores = [25, 30, 28, 40, 35, 45, 50]  # 가상의 우울 점수

        df_psych = pd.DataFrame({
            "날짜": dates,
            "우울점수": scores
        })

        # ✅ 우울 점수 변화 추이 카드
        st.markdown(''' **📉 우울점수변화추이**''')

        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(
            x=df_psych['날짜'],
            y=df_psych['우울점수'],
            mode='lines+markers',
            line=dict(shape='spline', color='#EF553B'),
            marker=dict(size=8, color='#EF553B'),
            name='우울점수'
        ))
        fig_line.update_layout(
            xaxis_title='날짜',
            yaxis_title='우울점수',
            yaxis_range=[0, 100],
            height=250,
            margin=dict(l=30, r=30, t=30, b=30),
            paper_bgcolor='#f5faff'
        )

        st.plotly_chart(fig_line, use_container_width=True)
        
# 비회원대시보드
def unuser_dashboard():
    st.session_state["user_id"] = 2
    # 사이드바 메뉴
    with st.sidebar:
        selected = option_menu(
            "츄러스미 메뉴",
            ["나의 대시보드", "심린이랑 대화하기", "심린이 추천병원", "심린이 추천 콘텐츠", "로그아웃"],
            icons=['bar-chart', 'chat-dots', 'hospital', 'camera-video', 'box-arrow-right'],
            default_index=0,
            styles={
                "container": {"padding": "5px"},
                "nav-link": {"font-size": "16px", "text-align": "left", "margin":"0px", "--hover-color": "#eee"},
                "nav-link-selected": {"background-color": "#b3d9ff"},
            }
        )
      
    if selected == '나의 대시보드':
        u_my_dashboard()
    elif selected == '심린이랑 대화하기':
        chats = load_chats(st.session_state["user_id"])
        for chat in chats:
            render_bubble("user", chat["question"], USER_AVATAR_PATH)
            render_bubble("bot",  chat["answer"],   GPT_AVATAR_PATH)

        # 입력창
        user_input = st.chat_input("메시지를 입력하세요…")
        if user_input:
            # 1) DB 저장 + GPT 호출
            answer = ask_gpt(st.session_state["user_id"], user_input)
            detected_emotion = save_chat_and_emotion(st.session_state["user_id"], user_input, answer)

            # 2) 화면에 바로 말풍선으로 렌더
            render_bubble("user", user_input, USER_AVATAR_PATH)
            render_bubble("bot", answer, GPT_AVATAR_PATH)

            st.rerun()

        if user_input:
            # 1) DB 저장 + GPT 호출
            answer = ask_gpt(st.session_state["user_id"], user_input)
            detected_emotion = save_chat_and_emotion(st.session_state["user_id"], user_input, answer)

            # 2) 세션에 추가
            with st.chat_message("user", avatar=USER_AVATAR_PATH):
                st.markdown(user_input)
            with st.chat_message("assistant", avatar=GPT_AVATAR_PATH):
                st.markdown(answer)

            st.rerun()

        # === 추천/세션 종료 버튼 ===
        col1, col2 = st.columns(2)
        with col1:
            if st.button("추천 받기"):
                if chats:
                    last_message = chats[-1]["question"]
                    detected_emotion = analyze_emotion(last_message)
                    st.info(f"최근 감정 분석 결과: **{detected_emotion}**")
                    show_recommendations_all(detected_emotion)

        with col2:
            if st.button("세션 종료"):
                dominant_emotion = get_dominant_emotion(st.session_state["user_id"])
                if dominant_emotion:
                    st.success(f"세션 전체 감정 요약 → **{dominant_emotion}**")
                    show_recommendations_all(dominant_emotion)
                else:
                    st.warning("대화 기록이 없어 세션 요약을 할 수 없습니다.")

    elif selected == '심린이 추천병원':
        hospital()
    elif selected == '심린이 추천 콘텐츠':
        content()
    else:
        logout()

# 관리자 임의 데이터--------------------------------------------
def create_sample_user_data():
    dates = pd.date_range(end=pd.Timestamp.today(), periods=30)
    data = pd.DataFrame({
        '날짜': dates,
        '가입 수': np.random.randint(5, 50, size=30),
        '성별': np.random.choice(['남성', '여성'], size=30),
        '나이': np.random.choice(range(10, 70, 10), size=30),
        '사용 시간': np.random.uniform(5, 120, size=30),
        '이용 빈도': np.random.randint(1, 10, size=30),
        '감정': np.random.choice(['기쁨', '슬픔', '분노', '불안', '평온'], size=30)
    })
    return data
def evaluation():
    st.subheader("⭐ 고객 평가")

    st.markdown("### ✅ 사용자 리뷰")
    reviews = [
        {"사용자": "user01", "리뷰": "정말 유용했어요!", "별점": 5},
        {"사용자": "user02", "리뷰": "조금 아쉬워요.", "별점": 3},
        {"사용자": "user03", "리뷰": "많은 도움이 되었어요.", "별점": 4},
    ]
    st.dataframe(pd.DataFrame(reviews))

    st.markdown("### 🚨 신고 접수 목록")
    st.warning("※ 신고 데이터는 현재 샘플 상태입니다.")
    st.write("- user02 → 챗봇 응답 부적절")
    st.write("- user05 → 욕설 포함된 리뷰")

def service_management():
    st.subheader("⚙️ 서비스 설정")

    st.markdown("### 📢 공지사항")
    st.text_area("공지사항 입력", "예: 9월 1일 서버 점검 예정입니다.")

    st.markdown("### 🛠️ 점검 모드")
    st.checkbox("서비스 점검 모드 활성화")

    st.markdown("### 🤖 챗봇 모델 선택")
    selected_model = st.selectbox("사용할 챗봇 모델을 선택하세요", ["v1.0", "v1.5", "v2.0", "GPT-4"])

def money_management():
    st.subheader("💰 수익 관리")

    st.markdown("### 🏥 병원 제휴 및 광고")
    st.write("- 행복정신과 (광고 계약 월 30만원)")
    st.write("- 마음편한의원 (심리상담 연계)")

    st.markdown("### 👩‍⚕️ 심리상담사 연결")
    st.write("현재 등록된 상담사 수: 8명")

    st.markdown("### ⭐ 프리미엄 유료 구독")
    st.metric("구독 사용자 수", 142)

    st.markdown("### 🏢 기업용 직원 감정 케어")
    st.write("기업 등록 수: 5곳")
    st.write("이용 기업: LG전자, 스타트업A 등")
# 관리자 대시보드 ---------------------------------------------
def user_management():
    user_data = create_sample_user_data()
    
    # ---------- 상단 지표 카드 ----------
    col1, col2 = st.columns([1.5,1])
    
    with col1:
        st.error("여기는 관리자가 접근할 수 있는 영역입니다.")
        st.subheader("📊 사용자 통계")
        
    with col2:
        col6, col7, col8 = st.columns(3)

        # 평균 사용 시간 delta 계산
        delta_time = user_data["사용 시간"].iloc[-1] - user_data["사용 시간"].iloc[-2]
        delta_freq = user_data["이용 빈도"].iloc[-1] - user_data["이용 빈도"].iloc[-2]
        delta_age = user_data["나이"].iloc[-1] - user_data["나이"].iloc[-2]
        # Metric 카드
        col6.metric("⏱ 평균 사용 시간", f"{user_data['사용 시간'].mean():.0f}분", f"{delta_time:+.2f}")
        col7.metric("📈 평균 이용 빈도", f"{user_data['이용 빈도'].mean():.0f}회", f"{delta_freq:+.2f}")
        col8.metric("🎂 평균 나이", f"{user_data['나이'].mean():.0f}세", f"{delta_age:+.2f}")
    st.markdown("---")  # 구분선

    # ---------- 하단 차트 영역 ----------
    col1, col2, col3, col4 = st.columns(4, gap="medium")
    
    # 1) 가입 추이
    with col1:
        st.markdown("🆕 **가입 추이**")
        fig_line = px.line(
            user_data, x='날짜', y='가입 수',
            markers=True,
            color_discrete_sequence=["#636EFA"]
        )
        fig_line.update_layout(height=300, width=300, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_line, use_container_width=False)
    
    # 2) 성별 비율
    with col2:
        st.markdown("👫 **성별 비율**")
        fig_pie = px.pie(user_data, names='성별', hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
        fig_pie.update_layout(height=300, width=300, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_pie, use_container_width=False)
    
    # 3) 나이대 분포
    with col3:
        st.markdown("🎂 **나이대 분포**")
        fig_hist = px.histogram(user_data, x='나이', nbins=10, color_discrete_sequence=["#EDB7AD"])
        fig_hist.update_layout(height=300, width=300, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_hist, use_container_width=False)
    
    # 4) 감정 트렌드
    with col4:
        st.markdown("😊 **감정 트렌드**")
        fig_emotion = px.histogram(user_data, x='감정', color='감정', 
                                   color_discrete_sequence=px.colors.qualitative.Pastel)
        fig_emotion.update_layout(height=300, width=300, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_emotion, use_container_width=False)
def admin_dashboard():
    st.title("👮‍♂️ 츄러스미 관리자 Dash Board")

    # 사이드바 메뉴
    with st.sidebar:
        admin_menu = option_menu(
            "관리자 메뉴",
            ["사용자 통계", "고객 평가", "서비스 설정", "수익 관리", "로그아웃"],
            icons=["bar-chart-line", "chat-dots", "gear", "currency-dollar", "box-arrow-right"],
            menu_icon="gear",
            default_index=0
        )

    if admin_menu == "사용자 통계":
        user_management()
    elif admin_menu == "고객 평가":
        evaluation()
    elif admin_menu == "서비스 설정":
        service_management()
    elif admin_menu == "수익 관리":
        money_management()
    else:
        logout()

# 🟢 유저 대시보드
if st.session_state.get("role") == "user": 
    user_dashboard()
elif st.session_state.get("role") == "admin":
    admin_dashboard()
elif st.session_state.get("role") == "guest":
    st.title("👤 비회원 체험 모드")
    unuser_dashboard()
elif st.session_state["page"] == "register":
    # 위쪽에서 회원가입 폼 렌더
    pass
else:
    # 기본은 로그인 페이지
    pass