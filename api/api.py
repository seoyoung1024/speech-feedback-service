from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import time
import os
import json
import google.generativeai as genai
from typing import Optional, Dict, Any
from pydantic import BaseModel
from pymongo import MongoClient
from bson import ObjectId
from config import FILLER_WORDS, IDEAL_WPM, SLOW_THRESHOLD, FAST_THRESHOLD
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")

# Gemini API 키 설정
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

# FastAPI 앱 초기화
app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 배포 시 특정 도메인으로 제한 필요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB 연결
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
collection = db[COLLECTION_NAME]

# 요청 모델 정의
class TextAnalysisRequest(BaseModel):
    session_id: str = "default"
    text: str
    generate_ai_feedback: bool = False

# 응답 모델 정의
class AnalysisResponse(BaseModel):
    success: bool
    analysis: Dict[str, Any]

# MongoDB ObjectId를 문자열로 변환하는 헬퍼 함수
def mongo_to_dict(obj):
    if isinstance(obj, dict):
        return {k: mongo_to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [mongo_to_dict(item) for item in obj]
    elif isinstance(obj, ObjectId):
        return str(obj)
    return obj

# ====================
# 📌 분석 클래스 정의
# ====================
class SpeechAnalyzer:
    def __init__(self):
        self.start_time = time.time()
        self.word_count = 0
        self.filler_counts = {word: 0 for word in FILLER_WORDS}
        self.all_words = []
        self.full_text = ""
        self._session_id = "default"

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
        return self._session_id

    @session_id.setter
    def session_id(self, value):
        self._session_id = value

# ====================
# 📌 AI 피드백 생성
# ====================
async def generate_ai_feedback(analysis_result: dict) -> str:
    """Gemini를 사용하여 분석 결과에 대한 피드백 생성"""
    try:
        wpm = analysis_result.get('wpm', 0)
        wpm_feedback = analysis_result.get('wpm_feedback', '')
        total_fillers = analysis_result.get('total_fillers', 0)
        filler_words = analysis_result.get('filler_words', {})
        speech_duration = analysis_result.get('speech_duration', 0)
        full_text = analysis_result.get('full_text', '')
        
        prompt = f"""
        다음은 사용자의 발화 분석 결과입니다. 이에 대한 전문가 같은 피드백을 제공해주세요.
        
        [발화 내용]
        {full_text}
        
        [분석 결과]
        - 평균 속도: {wpm} WPM
        - 속도 피드백: {wpm_feedback}
        - 사용된 필러 단어: {total_fillers}회
        - 필터 단어 상세: {json.dumps(filler_words, ensure_ascii=False)}
        - 발화 시간: {speech_duration:.2f}초
        
        다음 사항을 고려하여 한국어로 피드백을 작성해주세요:
        1. 발화 속도가 적절한지 평가
        2. 필러 단어 사용 패턴 분석
        3. 전체적인 발화 흐름과 명확성 평가
        4. 개선을 위한 구체적인 조언
        5. 격려의 메시지 포함
        """
        
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"AI 피드백 생성 오류: {e}")
        return "AI 피드백을 생성하는 중 오류가 발생했습니다."

# ====================
# 📌 세션 & DB 관리
# ====================

# 인메모리 세션 저장소
sessions = {}

# MongoDB 저장 함수
def save_result_to_db(result: dict) -> dict:
    try:
        # _id 필드가 있으면 제거 (MongoDB가 자동 생성하도록)
        result_copy = result.copy()
        if '_id' in result_copy:
            del result_copy['_id']
            
        # MongoDB에 저장
        result_id = collection.insert_one(result_copy).inserted_id
        
        # 저장된 문서 조회
        saved_doc = collection.find_one({"_id": result_id})
        return mongo_to_dict(saved_doc)
    except Exception as e:
        print(f"MongoDB 저장 실패: {e}")
        return result

# ====================
# 📌 API 라우팅
# ====================

@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_text(request: TextAnalysisRequest):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="텍스트를 입력해주세요.")

    if request.session_id not in sessions:
        analyzer = SpeechAnalyzer()
        analyzer.session_id = request.session_id
        sessions[request.session_id] = analyzer

    analyzer = sessions[request.session_id]
    analyzer.add_text(request.text)
    result = analyzer.get_analysis()

    # AI 피드백 생성 (요청된 경우에만)
    if request.generate_ai_feedback:
        result["ai_feedback"] = await generate_ai_feedback(result)

    # 결과 저장
    saved_result = save_result_to_db(result)
    
    return {
        "success": True,
        "analysis": saved_result
    }

@app.post("/api/reset-session")
async def reset_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]
    return {"success": True, "message": f"세션 {session_id} 초기화 완료"}

@app.get("/api/filler-words")
async def get_filler_words():
    return {
        "success": True,
        "words": FILLER_WORDS
    }

@app.get("/api/session-history/{session_id}")
async def get_session_history(session_id: str):
    try:
        results = list(collection.find({"session_id": session_id}))
        if not results:
            raise HTTPException(status_code=404, detail="해당 세션의 분석 기록이 없습니다.")
        
        # ObjectId를 문자열로 변환
        results = [mongo_to_dict(result) for result in results]
        
        return {
            "success": True,
            "session_id": session_id,
            "history": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 조회 오류: {e}")

# 서버 실행
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)