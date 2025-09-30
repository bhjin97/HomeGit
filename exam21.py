from typing import Dict, Annotated
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from transformers import pipeline
from contextlib import asynccontextmanager

classifier = None  # 전역 변수

# lifespan 함수 먼저 정의
@asynccontextmanager
async def startup(app: FastAPI):
    global classifier
    classifier = pipeline("sentiment-analysis")
    print("모델 로드 완료")
    yield

# FastAPI 앱 생성
app = FastAPI(lifespan=startup)

# 라우트 작성
@app.get("/")
async def main():
    content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>FastAPI + HuggingFace</title>
    </head>
    <body>
        <h1>허깅페이스 모델을 활용한 sentiment-analysis 테스트</h1><hr>
        <form action="/predict" method="post">
            <input name="content" type="text" size="50" placeholder="분석을 원하는 글을 입력하세요"><br>
            <input type="submit" value="요청">
        </form>
    </body>
    </html>
    """
    return HTMLResponse(content=content)

@app.post("/predict", response_model=Dict)
def predict(content: Annotated[str, Form()]):
    """
    사용자가 입력한 문장을 허깅페이스 감정분석(sentiment-analysis) 모델로 분석.
    결과 예: {'label': 'POSITIVE', 'score': 0.99}
    """
    result = classifier(content)
    return result[0]
