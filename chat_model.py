import streamlit as st
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
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
from openai import OpenAI
from dotenv import load_dotenv
import os

# 페이지 기본 설정
st.set_page_config(page_title="츄러스미 심리케어",layout='wide')

# 사용자 DB -------------------------------------------
User_DB = {
    "admin": {"password": "admin123", "role": "admin"},
    "user": {"password": "user123", "role": "user"},
    "unuser":{"password":"unuser123", "role":"unuser"}
} 

# 사용자 임의 데이터-------------------------------------
emotions = ['분노', '기쁨', '불안', '당황', '상처', '슬픔']
dates = [datetime.now().date() - timedelta(days=i) for i in range(9, -1, -1)]
np.random.seed(42)
psych_states = [np.random.randint(20, 80, size=6) for _ in dates]

df_psych = pd.DataFrame(psych_states, columns=emotions)
df_psych['날짜'] = dates
weights = {'불안': 0.4, '상처': 0.3, '슬픔': 0.3}
df_psych['우울점수'] = (
    df_psych['불안'] * weights['불안'] +
    df_psych['상처'] * weights['상처'] +
    df_psych['슬픔'] * weights['슬픔']
).round(1)
df_psych = df_psych.sort_values('날짜').reset_index(drop=True)

login_time = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
current_time = datetime.now()
usage_duration = current_time - login_time

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

# 세션 상태 초기화 -------------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""

# 로그인 함수 ------------------------------------------
def login():
    col1, col2, col3 = st.columns([3,2,3])
   
    with col2:
        img = Image.open("츄러스미_1.png")  # 츄러스미 이미지 삽입
        st.image(img, use_container_width=True)
    
        st.subheader("🔐로그인")
        username = st.text_input("아이디")
        password = st.text_input("비밀번호", type = 'password')
        
        col1, col2 = st.columns([4, 2])
        with col1:
            login_button = st.button("로그인")

        with col2:
            st.text('회원가입하기')
            
        if login_button:
            if username in User_DB and User_DB[username]["password"] == password:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.role = User_DB[username]["role"]
                st.rerun()  # 🔥 rerun으로 로그인 UI 지우고 새로 그림
            else:
                st.error("아이디 또는 비밀번호가 틀렸습니다😓")

# 사용자 대시보드----------------------------------------------
def my_dashboard():
    st.subheader(f"{st.session_state.username}님의 심리 대시보드 💉")
    
    # KPI 카드 4개(총 사용시간, 오늘 우울점수, 최고 우울점수, 최근 로그인 날짜)
    total_usage_hour = usage_duration.seconds // 3600
    total_usage_min = (usage_duration.seconds % 3600) // 60
    max_depression = df_psych['우울점수'].max()
    today_depression = df_psych[df_psych['날짜'] == datetime.now().date()]['우울점수'].values
    today_depression = today_depression[0] if len(today_depression) > 0 else np.nan
    
    #st.markdown('<div class="card">', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns([2,1,1,1])
    with col1:
        st.markdown('''**📅 로그인 날짜 선택**''')
        login_date = st.date_input(
            "로그인 날짜를 선택하세요",
            value=df_psych['날짜'].max(),
            min_value=df_psych['날짜'].min(),
            max_value=df_psych['날짜'].max())
    
    with col2:
        st.metric(
            label="오늘 사용 시간",
            value=f"{total_usage_hour}시간 {total_usage_min}분",
            delta="+30분"  
        )

    with col3:
         st.metric(
        label="오늘 우울 점수",
        value=f"😔 {today_depression:.1f}",
        delta="+0.5"  
    )

    with col4:
        st.metric(
        label="최근 최고 우울 점수",
        value=f"📈 {max_depression:.1f}",
        delta="+1.0"  # 전일 대비 변화 예시
    )

    # with kpi4:
    #     st.metric(
    #     label="최근 로그인 날짜",
    #     value=f"📅 {login_time.strftime('%Y-%m-%d')}",
    #     delta=""  # 날짜는 delta 없으면 빈 문자열
    # )

    st.divider()
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        tabs = st.tabs(["기본 정보", "상담 히스토리", "최근 상담 요약", "추천 행동"])

        with tabs[0]:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown("**📝 기본 정보**")
            st.markdown("""
            - 이름: 김다은  
            - 성별: 여자 👩
            """)
            st.markdown('</div>', unsafe_allow_html=True)

        with tabs[1]:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown("**📁 상담 히스토리**")
            st.markdown("""
            - 총 7회  
            - 최근 상담: 2025.08.19  
            - 주요 키워드: 불안, 자기비하, 가족문제
            """)
            st.markdown('</div>', unsafe_allow_html=True)

        with tabs[2]:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown("**🌧️ 최근 상담 요약**")
            st.markdown("""
            - 주된 감정: 슬픔, 불안  
            - 주요 키워드: 외로움, 관계 스트레스, 무기력  
            - 긍정 반응 키워드: 여행, 가족, 취미
            - 
            """)
            st.markdown('</div>', unsafe_allow_html=True)

        with tabs[3]:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown("**💡 추천 행동**")
            st.markdown("""
- 하루 5분 감정 기록하기  
  (긍정적이든 부정적이든, 글로 적으면 감정 정리에 도움)  
- 주 30분 가벼운 외출, 산책, 취미 활동  
  (몸을 움직이면 불안과 무기력 완화 효과)  
- 가족, 친구와 짧은 소통 시간 갖기  
  (감정을 나누는 것만으로도 외로움 완화)  
- 필요 시 상담사 또는 심리 전문가와 상담 연계  
  (전문가가 구체적인 대처 방법 안내)
""")
            st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown(''' **🔯감정상태분석**''')

        selected_data = df_psych[df_psych['날짜'] == login_date]
        if selected_data.empty:
            st.warning("해당 날짜의 데이터가 없습니다.")
        else:
            values = selected_data[emotions].values.flatten().tolist()
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
                height=200,
                paper_bgcolor='#f5faff'
            )
            st.plotly_chart(fig_radar, use_container_width=True)

            # ✅ 감정 중 가장 높은 값 추출
            emotion_scores = dict(zip(emotions, values))
            dominant_emotion = max(emotion_scores, key=emotion_scores.get)
            dominant_value = emotion_scores[dominant_emotion]

            # ✅ 감정별 코멘트 정의
            emotion_comments = {
                "기쁨": "행복한 하루를 보내셨군요! 이 기분 오래 간직하세요 😊",
                "슬픔": "마음이 무거운 날이었네요. 감정을 인정하는 건 용기예요 💙",
                "불안": "불안한 감정이 느껴지네요. 천천히 숨을 쉬며 마음을 돌보세요.",
                "분노": "화가 났던 일이 있었군요. 감정을 밖으로 표현하는 건 건강한 행동이에요.",
                "당황": "예상치 못한 일이 있었나요? 잠시 멈추고 차분히 생각해봐요.",
                "상처": "상처받은 마음, 혼자 아파하지 마세요. 당신은 소중한 사람이에요 💖"
            }

            comment = emotion_comments.get(dominant_emotion, "당신의 감정을 응원합니다 💗")

            st.markdown(f"**{dominant_emotion}** ({dominant_value}점)")
            st.info(comment)

        st.markdown('</div>', unsafe_allow_html=True)

        

    with col3:
        # ✅ 우울 점수 변화 추이 카드
        st.markdown(''' **📉우울점수변화추이**''')
        
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
            height=200,
            margin=dict(l=30, r=30, t=30, b=30),
            paper_bgcolor='#f5faff'
        )
        st.plotly_chart(fig_line, use_container_width=True)

        st.markdown("**📌 북마크 목록**")
        # 이미지와 유사한 북마크 목록 UI 생성 (st.write 사용)
        st.write("🎬 영화 - 아이언맨")
        st.write("📺 드라마 - 푹싹 속았수다")
        st.write("🎵 노래 - 아기상어")


@st.cache_resource
def load_emotion_model():
    model_name = "Jinuuuu/KoELECTRA_fine_tunning_emotion"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    return pipeline("text-classification", model=model, tokenizer=tokenizer, return_all_scores=True)

emotion_classifier = load_emotion_model()

# 레이블 매핑
label_map = {
    "angry": "분노",
    "happy": "행복",
    "anxious": "불안",
    "embarrassed": "당황",
    "sad": "슬픔",
    "hurt": "상처"
}

# 감정 예측 함수
def predict_emotion(text: str):
    result = emotion_classifier(text)[0]
    best = max(result, key=lambda x: x["score"])
    emotion = label_map.get(best["label"], best["label"])
    score = best["score"]
    return emotion, score

# -----------------------------
# 챗봇 함수
# -----------------------------


def chat_bot():
    load_dotenv()
    api_key = st.secrets["OPENAI_API_KEY"]

# ✅ OpenAI 클라이언트 초기화
    client = OpenAI(api_key=api_key)# 키 수정

    col1, col2 = st.columns([1,10])
    with col2:
        st.subheader("츄러스미~! 나와 대화해볼래? 👋")
        st.markdown("심린이에게 고민을 털어놔보세요.❤️")
    with col1:
        try:
            img = Image.open("츄러스미_2.png")
            st.image(img, width=100)
        except FileNotFoundError:
            st.warning("`츄러스미_2.png` 이미지를 찾을 수 없습니다.")
            st.write("📌 이미지 없음")

    # 💬 CSS 말풍선 스타일
    st.markdown("""
        <style>
            .message { max-width: 80%; padding: 10px 15px; border-radius: 20px; margin: 8px 0; display: inline-block; word-wrap: break-word; font-size: 16px; line-height: 1.4;}
            .bot { background-color: #f1f0f0; text-align: left; }
            .user { background-color: #dcf8c6; text-align: right; float: right; }
            .clearfix::after { content: ""; display: table; clear: both; }
        </style>
    """, unsafe_allow_html=True)

    # 세션 초기화
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "bot", "message": "안녕하세요! 필요한 도움이 있으신가요? 당신의 이야기를 들려주세요. 😊"}
        ]

    # --- 사용자 입력 받기 ---
    user_input = st.chat_input("💬 오늘 기분은 어땠나요? (예: 오늘 너무 속상했어...)")

    if user_input:
        # 1️⃣ 사용자 메시지 바로 추가
        st.session_state.chat_history.append({"role": "user", "message": user_input})

        with st.spinner("당신의 감정을 분석하고 상담사 연결 중... 🧘‍♀️"):
            try:
                # 2️⃣ 감정분류 (문자 레이블 처리)
                result = emotion_classifier(user_input)[0]
                best = max(result, key=lambda x: x["score"])
                label_map = {
                    "angry": "분노",
                    "happy": "행복",
                    "anxious": "불안",
                    "embarrassed": "당황",
                    "sad": "슬픔",
                    "hurt": "상처"
                }
                emotion = label_map.get(best["label"], best["label"])
                score = best["score"]

                # 3️⃣ GPT 프롬프트 구성
                prompt = f"""
                당신은 친절하고 경험 많은 심리상담사야.
                사용자가 입력한 문장: "{user_input}"
                감정 분석 결과: {emotion} (신뢰도: {score:.2f})

                - 먼저 사용자의 감정을 충분히 공감하고 이해를 표현해줘.
                - 상황을 개선할 수 있는 현실적 조언이나 방법 2-3가지 제안.
                - 감정 분석 신뢰도가 0.6 미만이면 자연스럽게 되묻기.
                - 말투는 친근하고 따뜻하게 작성.
                """

                # 4️⃣ GPT 응답 생성
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "너는 따뜻한 심리상담사이다. 사용자의 감정을 공감하고 현실적인 조언을 제공해줘."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7
                )
                answer = response.choices[0].message.content

                # 5️⃣ 챗봇 답변 추가
                st.session_state.chat_history.append({"role": "bot", "message": answer})

            except Exception as e:
                st.error(f"상담사 연결에 실패했습니다. 오류: {e}")

    # --- 대화 렌더링 ---
    for chat in st.session_state.chat_history:
        cls = "user" if chat["role"] == "user" else "bot"
        st.markdown(f'<div class="clearfix"><div class="message {cls}">{chat["message"]}</div></div>', unsafe_allow_html=True)

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

def content():
    st.subheader("🎬 심린이 추천 콘텐츠")
    st.markdown("감정을 선택하고, 음악 / 드라마 / 영화 콘텐츠를 추천받아보세요.")

    # 감정별 탭
    emotions = ["행복", "슬픔", "힘내요"]
    emotion_tabs = st.tabs(emotions)

    # 감정별 추천 데이터 예시
    data = {
        "행복": {
            "음악": [
                {"cover": "https://i.imgur.com/6nGTOq9.jpg", "artist": "아이유", "title": "좋은 날"},
                {"cover": "https://i.imgur.com/BiZcFqK.jpg", "artist": "방탄소년단", "title": "Dynamite"}
            ],
            "드라마": [
                {"cover": "https://i.imgur.com/hpQ47hL.jpg", "title": "이태원 클라쓰", "desc": "젊은이들의 열정과 우정을 그린 이야기"}
            ],
            "영화": [
                {"cover": "https://i.imgur.com/vGz4QOJ.jpg", "title": "라라랜드", "desc": "재즈 음악과 사랑을 그린 뮤지컬 영화"}
            ]
        },
        "슬픔": {
            "음악": [
                {"cover": "https://i.imgur.com/0K4nNGa.jpg", "artist": "이승철", "title": "소녀시대"}
            ],
            "드라마": [
                {"cover": "https://i.imgur.com/7grPQOZ.jpg", "title": "눈이 부시게", "desc": "시간을 되돌리는 슬픈 이야기"}
            ],
            "영화": [
                {"cover": "https://i.imgur.com/LDQ0tGp.jpg", "title": "건축학개론", "desc": "첫사랑의 기억을 그린 감성 영화"}
            ]
        },
        "힘내요": {
            "음악": [
                {"cover": "https://i.imgur.com/ZmFb8mR.jpg", "artist": "싸이", "title": "강남스타일"}
            ],
            "드라마": [
                {"cover": "https://i.imgur.com/tGJgqDn.jpg", "title": "굿닥터", "desc": "천재 의사의 성장 이야기"}
            ],
            "영화": [
                {"cover": "https://i.imgur.com/1rk5NHX.jpg", "title": "어벤져스: 엔드게임", "desc": "마블 히어로들의 대서사시 액션"}
            ]
        }
    }

    # 감정 탭 순회
    for i, emotion in enumerate(emotions):
        with emotion_tabs[i]:
            st.markdown(f"**{emotion} 감정에 맞는 추천 콘텐츠**")

            musics = data[emotion]["음악"]
            dramas = data[emotion]["드라마"]
            movies = data[emotion]["영화"]

            # 음악 섹션
            st.markdown("**🎵 음악**")

            # 한 줄에 2개씩 표시
            cols = st.columns(2)  # 2개의 컬럼 생성

            for idx, music in enumerate(musics):
                col = cols[idx % 2]  # 왼쪽/오른쪽 번갈아 배치
                with col:
                    st.image(music["cover"], width=150)
                    st.markdown(f"**{music['title']}**")
                    st.markdown(f"가수: {music['artist']}")
            st.markdown("---")

           # 드라마 섹션
            st.markdown("**📺 드라마**")

            n_cols = 2  # 한 줄에 2개씩 배치
            cols = st.columns(n_cols)

            for idx, drama in enumerate(dramas):
                col = cols[idx % n_cols]
                with col:
                    st.image(drama["cover"], width=150)
                    st.markdown(f"**{drama['title']}**")
                    st.markdown(drama["desc"])

            st.markdown("---")  # 섹션 구분

            # 영화 섹션
            st.markdown("**🎬 영화**")

            cols = st.columns(n_cols)
            for idx, movie in enumerate(movies):
                col = cols[idx % n_cols]
                with col:
                    st.image(movie["cover"], width=150)
                    st.markdown(f"**{movie['title']}**")
                    st.markdown(movie["desc"])

def logout():
    st.subheader("👋 로그아웃")

    if st.session_state.get("logged_in", False):
        st.warning("로그아웃하시겠습니까?")
        if st.button("✅ 로그아웃"):
            st.session_state.logged_in = False
            st.success("성공적으로 로그아웃되었습니다!")
            st.rerun()
            login()
    else:
        st.info("이미 로그아웃된 상태입니다.")
    
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
        my_dashboard()
    elif selected == '심린이랑 대화하기':
        chat_bot()
    elif selected == '심린이 추천병원':
        hospital()
    elif selected == '심린이 추천 콘텐츠':
        content()
    else:
        logout()
        
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
#--------------------------------------------------------------
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
            img = Image.open("설명하는츄러스미.png")
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
        chat_bot()
    elif selected == '심린이 추천병원':
        hospital()
    elif selected == '심린이 추천 콘텐츠':
        content()
    else:
        logout()


# 실행 흐름 -----------------------------
if st.session_state.logged_in:
    if st.session_state.role == "admin":
        admin_dashboard()
    elif st.session_state.role == "user":
        user_dashboard()
    else:
        unuser_dashboard()
else:
    login()
