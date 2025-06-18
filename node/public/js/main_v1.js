let recognition;
let isRecording = false;
let sessionId = 'session_' + Date.now();  // 고유한 세션 ID 생성

// UI 요소
const startButton = document.getElementById('startButton');
const stopButton = document.getElementById('stopButton');
const status = document.getElementById('status');
const transcript = document.getElementById('transcript');
const analysisResults = document.getElementById('analysisResults') || createAnalysisDiv();

// 음성 인식 초기화
if ('webkitSpeechRecognition' in window) {
    recognition = new webkitSpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'ko-KR';

    startButton.addEventListener('click', startRecording);
    stopButton.addEventListener('click', stopRecording);

    recognition.onresult = (event) => {
        let interimTranscript = '';
        
        for (let i = event.resultIndex; i < event.results.length; i++) {
            const result = event.results[i];
            if (result.isFinal) {
                processText(result[0].transcript);
            } else {
                interimTranscript += result[0].transcript;
            }
        }
        
        // 임시 결과 표시
        transcript.textContent = interimTranscript;
    };

    recognition.onerror = (event) => {
        console.error('음성 인식 오류:', event.error);
        status.textContent = '오류: ' + event.error;
    };
} else {
    alert('이 브라우저는 음성 인식을 지원하지 않습니다.');
}

// 녹음 시작
async function startRecording() {
    try {
        await navigator.mediaDevices.getUserMedia({ audio: true });
        isRecording = true;
        recognition.start();
        toggleButtons(true);
        status.textContent = '녹음 중...';
        transcript.textContent = '';
        analysisResults.innerHTML = '<p>분석 중...</p>';
    } catch (err) {
        console.error('마이크 접근 오류:', err);
        status.textContent = '마이크 권한이 필요합니다.';
    }
}

// 녹음 중지
function stopRecording() {
    isRecording = false;
    recognition.stop();
    toggleButtons(false);
    status.textContent = '준비됨';
}

// 버튼 상태 전환
function toggleButtons(isRecording) {
    startButton.disabled = isRecording;
    stopButton.disabled = !isRecording;
}

// 텍스트 처리 및 서버 전송
async function processText(text) {
    if (!text.trim()) return;

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                text: text
            })
        });

        const result = await response.json();
        
        if (result.success && result.analysis) {
            displayAnalysis(result.analysis);
        }
    } catch (error) {
        console.error('분석 요청 오류:', error);
        status.textContent = '분석 중 오류가 발생했습니다.';
    }
}

// 기존 analyzeText 함수 수정
async function analyzeText(text) {
    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                session_id: currentSessionId,
                text: text,
                generate_ai_feedback: true  // AI 피드백 요청
            }),
        });

        const data = await response.json();
        if (data.success) {
            updateAnalysisUI(data.analysis);
            if (data.analysis.ai_feedback) {
                displayAIFeedback(data.analysis.ai_feedback);
            }
        }
    } catch (error) {
        console.error('분석 중 오류 발생:', error);
    }
}

// AI 피드백 표시 함수 추가
function displayAIFeedback(feedback) {
    const feedbackContainer = document.getElementById('ai-feedback-container');
    if (!feedbackContainer) {
        const container = document.createElement('div');
        container.id = 'ai-feedback-container';
        container.className = 'mt-4 p-4 bg-blue-50 rounded-lg';
        container.innerHTML = `
            <h3 class="text-lg font-semibold mb-2">🤖 AI 피드백</h3>
            <div id="ai-feedback-content" class="whitespace-pre-line"></div>
        `;
        document.getElementById('analysis-results').appendChild(container);
    }

    const content = document.getElementById('ai-feedback-content');
    content.textContent = feedback;
}

// 분석 결과 표시
function displayAnalysis(analysis) {
    analysisResults.innerHTML = `
        <h3>🔍 분석 결과</h3>
        <div class="result-item">
            <span class="label">발화 내용:</span>
            <p class="content">${analysis.full_text || '분석 중...'}</p>
        </div>
        <div class="result-item">
            <span class="label">분당 단어 수:</span>
            <span class="value">${analysis.wpm} WPM</span>
            <small class="feedback">${analysis.wpm_feedback || ''}</small>
        </div>
        <div class="result-item">
            <span class="label">필러 단어:</span>
            <span class="value">${analysis.total_fillers}회</span>
            ${analysis.total_fillers > 0 ? `
                <div class="filler-words">
                    ${Object.entries(analysis.filler_words)
                        .filter(([_, count]) => count > 0)
                        .map(([word, count]) => 
                            `<span class="badge bg-warning text-dark">${word} (${count})</span>`
                        ).join(' ')}
                </div>
            ` : ''}
        </div>
        ${analysis.ai_feedback ? `
            <div class="ai-feedback mt-3 p-3 bg-light rounded">
                <h5>🤖 AI 피드백</h5>
                <p>${analysis.ai_feedback}</p>
            </div>
        ` : ''}
        <button onclick="resetSession()" class="btn btn-sm btn-outline-secondary mt-2">
            <i class="bi bi-arrow-repeat"></i> 새 세션 시작
        </button>
    `;
}

// 새 세션 시작
window.resetSession = function() {
    sessionId = 'session_' + Date.now();
    transcript.textContent = '';
    analysisResults.innerHTML = '<p class="text-muted">새 세션이 시작되었습니다.</p>';
}

// 분석 결과 컨테이너 생성
function createAnalysisDiv() {
    const div = document.createElement('div');
    div.id = 'analysisResults';
    div.className = 'mt-4 p-3 border rounded';
    document.querySelector('.container').appendChild(div);
    return div;
}