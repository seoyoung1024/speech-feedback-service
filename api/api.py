from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
import time
import os
import json
import google.generativeai as genai
from typing import Optional, Dict, Any
from pydantic import BaseModel
from pymongo import MongoClient
from bson import ObjectId
from config import FILLER_WORDS, IDEAL_WPM, SLOW_THRESHOLD, FAST_THRESHOLD
import boto3
import re
import traceback

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
    allow_origins=["https://alb.seoyoung.store"],  # 배포 시 특정 도메인으로 제한 필요
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
    start_time: Optional[float] = None
    end_time: Optional[float] = None

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
        self.reset()

    def reset(self):
        self.start_time = None
        self.end_time = None  # ✅ 마지막 텍스트 수신 시각
        self.word_count = 0
        self.filler_counts = {word: 0 for word in FILLER_WORDS}
        self.all_words = []
        self.full_text = ""
        self._session_id = "default"
        self._first_text_added = False

    def add_text(self, text: str, start_time: float = None, end_time: float = None) -> None:
        words = re.findall(r'\b\w+\b', text)
        if not words:
            return
        now = time.time()

        # 디버깅 로그 추가 (받은 값 그대로 출력)
        print(f"[DEBUG] add_text()에 전달된 start_time: {start_time}, end_time: {end_time}")
        if start_time is not None:
            self.start_time = start_time
        elif not self._first_text_added:
            self.start_time = now
        if end_time is not None:
            self.end_time = end_time
        else:
            self.end_time = now

        # 디버깅 로그 (내부 적용된 값 확인)
        print(f"[DEBUG] SpeechAnalyzer에 설정된 start_time: {self.start_time}, end_time: {self.end_time}")

        self._first_text_added = True
        self.word_count = len(words)         # 누적이 아니라 새로 계산
        self.all_words = words               # 누적이 아니라 새로 할당
        self.full_text = text.strip()        # 누적이 아니라 새로 할당
        self._count_fillers(words)
        

    def _count_fillers(self, words: list) -> None:
        for word in words:
            word_lower = word.lower().strip('.,!?;:')
            if word_lower in self.filler_counts:
                self.filler_counts[word_lower] += 1

    def get_analysis(self) -> dict:
        # 1. 발화 시간 계산
        if self.start_time is None or self.end_time is None:
            print("[WARN] start_time 또는 end_time이 None입니다. 기본값 1초로 설정합니다.")
            elapsed_time = 1.0
        else:
            elapsed_time = self.end_time - self.start_time
            if elapsed_time < 1.0:
                print(f"[WARN] 발화 시간이 너무 짧습니다: {elapsed_time:.3f}초 → 1초로 보정합니다.")
                elapsed_time = 1.0
            elif elapsed_time > 600:
                print(f"[INFO] 발화 시간이 600초를 초과했습니다: {elapsed_time:.1f}초 → 600초로 제한합니다.")
                elapsed_time = 600

        # 2. 발화 속도 계산 (WPM)
        minutes = elapsed_time / 60.0
        wpm = (self.word_count / minutes) if minutes > 0 else 0
        wpm = round(wpm, 2)

        # 2-1. 음절(Syllable) 기준 속도 계산 (SPM)
        syllable_count = sum(1 for c in self.full_text if '\uAC00' <= c <= '\uD7A3')
        spm = (syllable_count / minutes) if minutes > 0 else 0
        spm = round(spm, 2)

        # 3. 필러 단어 정리
        used_fillers = {k: v for k, v in self.filler_counts.items() if v > 0}
        total_fillers = sum(used_fillers.values())

        # 4. WPM 피드백 결정
        if wpm < SLOW_THRESHOLD:
            wpm_feedback = "조금 더 빠르게 말씀해보시는 건 어떨까요?"
        elif wpm > FAST_THRESHOLD:
            wpm_feedback = "조금 더 천천히, 또박또박 말씀해보세요."
        else:
            wpm_feedback = "적절한 속도로 말하고 계십니다."

        s3_url = None
        if s3_client:
            result_data = {
                "session_id": self.session_id,
                "analysis": {
                    "word_count": self.word_count,
                    "spm": round(spm, 2),
                    "filler_words": used_fillers,
                    "total_fillers": total_fillers,
                    "speech_duration": round(elapsed_time, 2),
                    "analyzed_at": datetime.utcnow().isoformat(),
                    "full_text": self.full_text
                }
            }
            s3_url = upload_to_s3(result_data, f"{self.session_id}.json")

        return {
            "session_id": self.session_id,
            "word_count": self.word_count,
            "spm": spm,
            "syllable_count": syllable_count,
            "spm_feedback": spm_feedback,
            "filler_words": used_fillers,
            "total_fillers": total_fillers,
            "speech_duration": round(elapsed_time, 2),
            "s3_url": s3_url,
            "full_text": self.full_text
        }

    @property
    def session_id(self):
        return self._session_id

    @session_id.setter
    def session_id(self, value):
        if self._session_id != value:
            self.start_time = time.time()
            self.end_time = None
        self._session_id = value

# ====================
# 📌 AI 피드백 생성
# ====================
async def generate_ai_feedback(analysis_result: dict) -> str:
    """Gemini를 사용하여 분석 결과에 대한 전문가 같은 피드백 생성"""
    try:
        # 기본 분석 결과 추출
        spm = analysis_result.get('spm', 0)
        spm_feedback = analysis_result.get('spm_feedback', '')
        total_fillers = analysis_result.get('total_fillers', 0)
        filler_words = {k: v for k, v in analysis_result.get('filler_words', {}).items() if v > 0}
        speech_duration = analysis_result.get('speech_duration', 0)
        full_text = analysis_result.get('full_text', '')
        word_count = analysis_result.get('word_count', 0)
        
        # 발화 속도 평가
        if spm < 150:
            speed_assessment = "다소 느림"
        elif 150 <= spm <= 180:
            speed_assessment = "적절함"
        elif 180 < spm <= 250:
            speed_assessment = "다소 빠름"
        else:
            speed_assessment = "매우 빠름"

        
        # 필러 단어 사용량 평가
        filler_assessment = "적절함"
        filler_ratio = (total_fillers / word_count * 100) if word_count > 0 else 0        
        if filler_ratio > 10:
            filler_assessment = "많이 사용됨"
        elif filler_ratio > 5:
            filler_assessment = "다소 많음"
        else:
            filler_assessment = "적절함"

        # 프롬프트 구성
        prompt = f"""
        당신은 발표 코칭 전문가입니다. 다음 발화 분석 결과를 바탕으로 전문가 같은 피드백을 제공해주세요.
        
        [발화 내용]
        {full_text}
        
        [분석 결과]
        1. 발화 속도: {spm:.1f} SPM ({speed_assessment})
           - {spm_feedback}

        2. 필러 단어 사용량: {total_fillers}회 ({filler_assessment})
        """
        
        # 필러 단어가 있는 경우에만 상세 정보 추가
        if filler_words:
            prompt += f"""
            3. 주요 필터 단어 사용 횟수:
               {', '.join([f'{k}: {v}회' for k, v in filler_words.items()])}
            """
        
        # 추가 지시사항
        prompt += f"""
        
        [피드백 요청사항]
        다음 내용을 고려하여 한국어로 전문가 같은 피드백을 제공해주세요:
        
        1. 발화 속도 평가:
           - 현재 속도({spm:.1f} SPM)가 적절한지 여부   
           - 청중이 이해하기 좋은 이상적인 발화 속도 제안
           
        2. 필러 단어 사용 분석:
           - 사용된 필러 단어 패턴 분석
           - 각 필러 단어 대신 사용할 수 있는 적절한 표현 제안
           
        3. 내용 구성:
           - 논리적 흐름이 적절했는지
           - 핵심 메시지 전달이 효과적이었는지
           
        4. 개선을 위한 구체적인 조언:
           - 발화 속도 조절 방법
           - 필러 단어 줄이기 위한 실천 방안
           - 전반적인 전달력 향상을 위한 팁
           
        [주의사항]
        - 반말이 아닌 존댓말로 작성해주세요.
        - 부정적인 표현보다는 긍정적인 조언 위주로 작성해주세요.
        - 구체적인 예시를 들어 설명해주세요.
        - 전체적으로 격려의 메시지를 포함해주세요.
        - 피드백은 2-3개의 단락으로 구성해주세요.
        - 요구 사항 별로 숫자를 붙여 작성해주세요.
        """
        
        # AI 모델 호출
        print(f"[DEBUG] Gemini에 전송할 프롬프트 길이: {len(prompt)}자")
        response = gemini_model.generate_content(prompt)
        
        # 응답 처리
        if response.text:
            print(f"[DEBUG] AI 피드백 생성 완료 - 길이: {len(response.text)}자")
            return response.text.strip()
        else:
            print("[WARNING] AI 피드백이 비어있습니다.")
            return "죄송합니다. AI 피드백을 생성하는 데 실패했습니다. 다시 시도해주세요."
            
    except Exception as e:
        print(traceback.format_exc()) 
        raise HTTPException(
            status_code=500,
            detail=f"AI 피드백을 생성하는 중 오류가 발생했습니다: {str(e)}"
        )

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
            
        # 한국 시간대 설정 (UTC+9)
        kst = timezone(timedelta(hours=9))
        result_copy['analyzed_at'] = datetime.now(kst).isoformat()
            
        # MongoDB에 저장
        result_id = collection.insert_one(result_copy).inserted_id
        
        # 저장된 문서 조회
        saved_doc = collection.find_one({"_id": result_id})
        return mongo_to_dict(saved_doc)
    except Exception as e:
        print(f"MongoDB 저장 실패: {e}")
        return result


# S3 클라이언트 초기화 (S3 사용 시)
s3_client = None
S3_BUCKET = os.getenv('S3_BUCKET_NAME')
if os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY') and S3_BUCKET:
    s3_client = boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_REGION', 'ap-southeast-1')
    )

def upload_to_s3(data: dict, file_name: str) -> Optional[str]:
    """S3에 파일 업로드"""
    if not s3_client:
        return None
        
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=f"speech_analysis/{file_name}",
            Body=json.dumps(data, ensure_ascii=False, indent=2),
            ContentType='application/json'
        )
        return f"https://{S3_BUCKET}.s3.amazonaws.com/speech_analysis/{file_name}"
    except Exception as e:
        print(f"S3 업로드 오류: {e}")
        return None

# ====================
# 📌 API 라우팅
# ====================

@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_text(request: TextAnalysisRequest):
    print(f"[DEBUG] 요청 수신 - session_id: {request.session_id}, generate_ai_feedback: {request.generate_ai_feedback}")
    print(f"[DEBUG] 요청 텍스트 길이: {len(request.text)}자")
    print(f"[DEBUG] 요청에서 받은 start_time: {request.start_time}, end_time: {request.end_time}")


    if not request.text.strip():
        raise HTTPException(status_code=400, detail="텍스트를 입력해주세요.")

    try:
        # 세션 관리
        if request.session_id not in sessions:
            print(f"[DEBUG] 새 세션 생성: {request.session_id}")
            analyzer = SpeechAnalyzer()
            analyzer.session_id = request.session_id
            sessions[request.session_id] = analyzer
        
        analyzer = sessions[request.session_id]
        
        # 텍스트 분석
        analyzer.add_text(
            request.text,
            start_time=request.start_time,
            end_time=request.end_time
        )
        result = analyzer.get_analysis()
        
        # 분석 결과에 추가 메타데이터 추가
        result["analyzed_at"] = datetime.now().isoformat()
        result["text_length"] = len(request.text)
        result["word_count"] = len(request.text.split())
        
        print(f"[DEBUG] 기본 분석 완료 - 단어 수: {result['word_count']}개, SPM: {result['spm']:.1f}, 필러: {result['total_fillers']}회")

        # AI 피드백 생성 (요청된 경우에만)
        if request.generate_ai_feedback:
            print("[DEBUG] AI 피드백 생성 시작")
            try:
                # 최소 10단어 이상인 경우에만 AI 피드백 생성
                if result['word_count'] >= 10:
                    ai_feedback = await generate_ai_feedback(result)
                    result["ai_feedback"] = ai_feedback
                    print("[DEBUG] AI 피드백 생성 완료")
                else:
                    result["ai_feedback"] = "발화 내용이 너무 짧아 AI 피드백을 생성하기 어렵습니다. 더 긴 문장으로 시도해주세요."
                    print("[DEBUG] 발화 내용이 짧아 AI 피드백 생성 생략")
            except Exception as e:
                error_msg = f"AI 피드백 생성 중 오류: {str(e)}"
                print(f"[ERROR] {error_msg}")
                result["ai_feedback"] = error_msg
        else:
            print("[DEBUG] AI 피드백 생성 생략 (요청되지 않음)")
            result["ai_feedback"] = None

        # 결과 저장
        try:
            saved_result = save_result_to_db(result)
            print("[DEBUG] 결과 저장 완료")
        except Exception as e:
            print(f"[ERROR] 결과 저장 실패: {str(e)}")
            saved_result = result
        
        # 최종 응답 구성
        response_data = {
            "success": True,
            "analysis": saved_result
        }
        
        print("[DEBUG] 분석 완료 및 응답 반환")
        return response_data
        
    except Exception as e:
        error_msg = f"분석 중 오류 발생: {str(e)}"
        print(f"[ERROR] {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

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