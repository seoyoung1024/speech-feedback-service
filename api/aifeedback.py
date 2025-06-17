import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# Gemini API 키 설정
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Gemini 모델 초기화
model = genai.GenerativeModel('gemini-2.0-flash')

def load_analysis_result(file_path):
    """분석 결과 JSON 파일 로드"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"분석 결과 파일을 로드하는 중 오류 발생: {e}")
        return None

def generate_feedback(analysis_result):
    """Gemini를 사용하여 분석 결과에 대한 피드백 생성"""
    if not analysis_result:
        return "분석 결과를 로드할 수 없습니다."
    
    try:
        # 분석 결과에서 주요 정보 추출
        wpm = analysis_result.get('wpm', 0)
        wpm_feedback = analysis_result.get('wpm_feedback', '')
        total_fillers = analysis_result.get('total_fillers', 0)
        filler_words = analysis_result.get('filler_words', {})
        speech_duration = analysis_result.get('speech_duration', 0)
        full_text = analysis_result.get('full_text', '')
        
        # 피드백을 위한 프롬프트 구성
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
        
        피드백은 3-4문단으로 구성해주세요.
        """
        
        # Gemini API 호출
        response = model.generate_content(prompt)
        return response.text
    
    except Exception as e:
        print(f"피드백 생성 중 오류 발생: {e}")
        return "피드백을 생성하는 중 오류가 발생했습니다."

def main():
    # 분석 결과 파일 경로 (실제 경로로 수정 필요)
    analysis_file = "results/speech_analysis_default_1750041493.json"
    
    # 분석 결과 로드
    analysis_result = load_analysis_result(analysis_file)
    if not analysis_result:
        return
    
    print("분석 결과를 기반으로 피드백을 생성 중입니다...\n")
    
    # 피드백 생성
    feedback = generate_feedback(analysis_result)
    
    # 결과 출력
    print("=" * 50)
    print("생성된 피드백:")
    print("=" * 50)
    print(feedback)
    print("=" * 50)
    
    # 별도 파일로 저장 (선택사항)
    try:
        output_file = "feedback_result.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(feedback)
        print(f"\n피드백이 {output_file}에 저장되었습니다.")
    except Exception as e:
        print(f"파일 저장 중 오류 발생: {e}")

if __name__ == "__main__":
    main()