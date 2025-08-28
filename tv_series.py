import requests
import mysql.connector

# ========== TMDB API 키 ==========
API_KEY = "YOUR_TMDB_API_KEY"
BASE_URL = "https://api.themoviedb.org/3"
IMG_BASE = "https://image.tmdb.org/t/p/w500"

# ========== DB 연결 ==========
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="비밀번호",
        database="Churo2_db"
    )

# ========== TMDB 인기 TV 시리즈 가져오기 ==========
def fetch_popular_tv():
    url = f"{BASE_URL}/tv/popular?api_key={API_KEY}&language=ko-KR&page=1"
    response = requests.get(url)
    return response.json()["results"]

# ========== DB 저장 ==========
def save_drama_to_db(drama_list):
    conn = get_db_connection()
    cursor = conn.cursor()

    for drama in drama_list:
        title = drama.get("name")
        description = drama.get("overview")
        poster_path = drama.get("poster_path")
        poster_url = f"{IMG_BASE}{poster_path}" if poster_path else None
        rating = drama.get("vote_average")

        cursor.execute("""
            INSERT INTO Drama (title, description, poster_url, emotion_genre, rating)
            VALUES (%s, %s, %s, %s, %s)
        """, (title, description, poster_url, None, rating))

    conn.commit()
    cursor.close()
    conn.close()

# 실행
if __name__ == "__main__":
    dramas = fetch_popular_tv()
    save_drama_to_db(dramas)
    print("✅ 인기 드라마 데이터 DB 저장 완료")
