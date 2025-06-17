from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import time
import os
import json
from pymongo import MongoClient
from config import FILLER_WORDS, IDEAL_WPM, SLOW_THRESHOLD, FAST_THRESHOLD
from dotenv import load_dotenv
import os

load_dotenv()  # .env 파일 로드

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")


app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB 클라이언트 연결
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
collection = db[COLLECTION_NAME]

# 요청 모델
class TextAnalysisRequest(BaseModel):
    session_id: str = "default"
    text: str

# 분석기 클래스
class SpeechAnalyzer:
    def __init__(self):
        self.start_time = time.time()
        self.word_count = 0
        self.filler_counts = {word: 0 for word in FILLER_WORDS}
        self.all_words = []
        self.full_text = ""

    def add_text(self, text: str) -> None:
        words = text.strip().split()
        self.word_count += len(words)
        self.all_words.extend(words)
        self.full_text += " " + text.strip()
        self._count_fillers(words)

    def _count_fillers(self, words: list) -> None:
        for word in words:
            word_lower = word.lower().strip('.,!?;:')
            if word_lower in self.filler_counts:
                self.filler_counts[word_lower] += 1

    def get_analysis(self) -> dict:
        minutes = (time.time() - self.start_time) / 60
        wpm = self.word_count / minutes if minutes > 0 else 0

        used_fillers = {k: v for k, v in self.filler_counts.items() if v > 0}

        if wpm < SLOW_THRESHOLD:
            wpm_feedback = "조금 더 빠르게 말씀해보시는 건 어떨까요?"
        elif wpm > FAST_THRESHOLD:
            wpm_feedback = "조금 더 천천히, 또박또박 말씀해보세요."
        else:
            wpm_feedback = "적절한 속도로 말하고 계십니다."

        return {
            "session_id": self.session_id,
            "full_text": self.full_text.strip(),
            "word_count": self.word_count,
            "wpm": round(wpm, 2),
            "wpm_feedback": wpm_feedback,
            "filler_words": used_fillers,
            "total_fillers": sum(used_fillers.values()),
            "speech_duration": round(time.time() - self.start_time, 2),
            "last_updated": datetime.now().isoformat()
        }

    @property
    def session_id(self):
        return getattr(self, '_session_id', 'default')

    @session_id.setter
    def session_id(self, value):
        self._session_id = value

# 인메모리 세션 저장소
sessions = {}

# MongoDB에 분석 결과 저장
def save_result_to_db(result: dict) -> None:
    try:
        collection.insert_one(result)
    except Exception as e:
        print(f"MongoDB 저장 실패: {e}")

# API: 텍스트 분석
@app.post("/api/analyze")
async def analyze_text(request: TextAnalysisRequest):
    if not request.text:
        raise HTTPException(status_code=400, detail="텍스트를 입력해주세요.")

    # 세션 가져오기
    if request.session_id not in sessions:
        analyzer = SpeechAnalyzer()
        analyzer.session_id = request.session_id
        sessions[request.session_id] = analyzer

    analyzer = sessions[request.session_id]
    analyzer.add_text(request.text)
    result = analyzer.get_analysis()

    # MongoDB에 저장
    save_result_to_db(result)

    return {
        "success": True,
        "analysis": result
    }

# API: 세션 초기화
@app.post("/api/reset-session")
async def reset_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]
    return {"success": True}

# API: 필러 단어 목록
@app.get("/api/filler-words")
async def get_filler_words():
    return {
        "success": True,
        "words": FILLER_WORDS
    }

# API: 세션별 전체 분석 기록 불러오기 (MongoDB 기반)
@app.get("/api/session-history/{session_id}")
async def get_session_history(session_id: str):
    try:
        results = list(collection.find({"session_id": session_id}, {"_id": 0}))
        if not results:
            raise HTTPException(status_code=404, detail="해당 세션의 분석 기록이 없습니다.")
        return {
            "success": True,
            "session_id": session_id,
            "history": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 조회 오류: {e}")
