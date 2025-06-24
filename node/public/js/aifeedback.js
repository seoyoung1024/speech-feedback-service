let recognition;
let isRecording = false;
let sessionId = 'session_' + Date.now();
let fullTranscript = '';
let startTime, endTime;
let recognitionStartTime, recognitionEndTime;
let timerInterval; //타이머 저장용

const startButton = document.getElementById('startButton');
const stopButton = document.getElementById('stopButton');
const status = document.getElementById('status');
const transcript = document.getElementById('transcript');
const analysisResults = document.getElementById('analysisResults') || createAnalysisDiv();

if (!('webkitSpeechRecognition' in window)) {
    alert('이 브라우저는 음성 인식을 지원하지 않습니다.');
} else {
    setupRecognition();
    registerEventListeners();
}

function setupRecognition() {
    recognition = new webkitSpeechRecognition();
    // 필러워드 인식률을 최대한 높이기 위해 continuous/interimResults 모두 true로 설정
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'ko-KR';
    recognition.maxAlternatives = 1;

    if ('webkitSpeechGrammarList' in window) {
        const grammar = '#JSGF V1.0; grammar punctuation; public <punc> = . | , | ? | ! | ; | :';
        const speechRecognitionList = new webkitSpeechGrammarList();
        speechRecognitionList.addFromString(grammar, 1);
        recognition.grammars = speechRecognitionList;
    }

    recognition.onstart = () => {
        recognitionStartTime = Date.now();
    };
    recognition.onend = () => {
        recognitionEndTime = Date.now();
        // isRecording이 true면 자동 재시작 (실시간 누적)
        if (isRecording) recognition.start();
    };
    recognition.onresult = handleRecognitionResult;
    recognition.onerror = (event) => {
        console.error('음성 인식 오류:', event.error);
        updateStatus('오류: ' + event.error);
        toggleButtons(false);
    };
}

// 모든 결과(중간+최종)를 누적 저장
let allTranscripts = [];
let lastFinalTranscript = '';

function registerEventListeners() {
    startButton.addEventListener('click', startRecording);
    stopButton.addEventListener('click', stopRecording);
}

async function startRecording() {
    startTime = Date.now();
    try {
        await navigator.mediaDevices.getUserMedia({ audio: true });
        isRecording = true;
        fullTranscript = '';
        recognition.start();
        toggleButtons(true);
        updateStatus('녹음 중...');
        transcript.textContent = '말씀해주세요...';
        analysisResults.innerHTML = '';

        //타이머 시작
        const timerEl = document.getElementById('recordingTimer');
        timerEl.textContent = '녹음 시간: 0초';
        timerInterval = setInterval(() => { 
            const elapsedSec = Math.floor((Date.now() - startTime) / 1000);
            timerEl.textContent = `녹음 시간: ${elapsedSec}초`;
        }, 1000);

    } catch (err) {
        console.error('마이크 접근 오류:', err);
        updateStatus('마이크 권한이 필요합니다.');
        toggleButtons(false);
    }
}

async function stopRecording() {
    endTime = Date.now();
    console.log("⏱️ [DEBUG] startTime:", startTime, "endTime:", endTime);

    isRecording = false;
    recognition.stop();
    toggleButtons(false);

    // 타이머 정지
    clearInterval(timerInterval);
    document.getElementById('recordingTimer').textContent += ' 종료됨';

    // 모든 누적 텍스트를 합쳐서 분석 (필러워드 인식률 극대화)
    const fullTextForAnalysis = allTranscripts.join(' ');
    if (!fullTextForAnalysis.trim()) {
        updateStatus('녹음된 내용이 없습니다.');
        return;
    }

    updateStatus('분석 중...');
    // transcript.textContent는 그대로 두어, 발화 내용이 계속 보이게 함
    showLoadingUI();

    try {
        await requestTextAnalysis(fullTextForAnalysis.trim(), startTime, endTime);
        updateStatus('분석이 완료되었습니다.');
    } catch (error) {
        handleAnalysisError(error);
    }
    // 분석 후 누적 배열 초기화 (화면의 발화 내용은 그대로)
    allTranscripts = [];
    fullTranscript = '';
    lastTranscriptText = '';
}

function handleRecognitionResult(event) {
    let interimTranscript = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const transcriptText = result[0].transcript;

        if (result.isFinal) {
            // 중복 누적 방지: 직전 최종 결과와 다를 때만 추가
            if (!fullTranscript.endsWith(transcriptText)) {
                // 새로 추가된 부분만 추출
                let newPart = transcriptText;
                if (transcriptText.startsWith(fullTranscript)) {
                    newPart = transcriptText.slice(fullTranscript.length);
                }
                fullTranscript += newPart + ' ';
                allTranscripts.push(newPart);
            }
            lastFinalTranscript = transcriptText;
        } else {
            interimTranscript = transcriptText;
        }
    }
    // 실시간 표시: 누적된 최종 결과 + 현재 interim
    transcript.textContent = (fullTranscript + interimTranscript).trim();
}

async function requestTextAnalysis(text, startTime, endTime) {
    const payload = {
        session_id: sessionId,
        text,
        generate_ai_feedback: true,
        start_time: startTime / 1000,
        end_time: endTime / 1000
    };

    const response = await fetch('/api/analyze', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        },
        body: JSON.stringify(payload)
    });

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    const result = await response.json();
    if (!result.success || !result.analysis) {
        throw new Error(result.message || '유효하지 않은 분석 결과입니다.');
    }

    displayAnalysis(result.analysis);
}

function showLoadingUI() {
    analysisResults.innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-primary mb-3" role="status">
                <span class="visually-hidden">로딩 중...</span>
            </div>
            <h5 class="text-muted">발화 내용을 분석 중입니다</h5>
            <p class="text-muted small">AI가 발화 내용을 분석하고 피드백을 생성하는 중입니다. 잠시만 기다려주세요...</p>
        </div>
    `;
}

function handleAnalysisError(error) {
    console.error('분석 오류:', error);
    updateStatus('분석 중 오류가 발생했습니다.');
    analysisResults.innerHTML = `
        <div class="alert alert-danger">
            <strong>오류:</strong> ${error.message}
        </div>
    `;
}

function updateStatus(message) {
    status.textContent = message;
}

function toggleButtons(isRecording) {
    startButton.disabled = isRecording;
    stopButton.disabled = !isRecording;
}

// 분석 결과 표시 함수
function displayAnalysis(analysis) {
    console.log('분석 결과 전체:', analysis);
    // SPM, 단어 수, 녹음 시간 등 분석값을 콘솔에도 상세히 출력
    console.log('SPM:', analysis.spm, '단어 수:', analysis.word_count, '녹음 시간(초):', analysis.speech_duration ?? analysis.duration_sec ?? analysis.duration);
    
    // 필러 단어 목록 생성
    let fillerWordsHtml = '';
    if (analysis.filler_words && Object.keys(analysis.filler_words).length > 0) {
        const fillerWordsList = Object.entries(analysis.filler_words)
            .filter(([_, count]) => count > 0)
            .map(([word, count]) => 
                `<span class="badge bg-warning text-dark me-1 mb-1">${word}: ${count}회</span>`
            ).join('\n');
        
        fillerWordsHtml = `
            <div class="filler-words mt-2">
                <p class="mb-2"><strong>사용된 필러 단어:</strong></p>
                <div class="d-flex flex-wrap">
                    ${fillerWordsList}
                </div>
            </div>`;
    }

    // AI 피드백이 있는 경우 HTML 생성
    const aiFeedbackHtml = analysis.ai_feedback ? `
        <div class="ai-feedback mt-4 p-4 rounded-3 bg-light">
            <div class="d-flex align-items-center mb-3">
                <i class="bi bi-robot fs-4 me-2 text-primary"></i>
                <h4 class="mb-0 fw-bold">AI 발표 코칭</h4>
            </div>
            <div class="feedback-content" style="white-space: pre-line;">
                ${analysis.ai_feedback.replace(/\n/g, '<br>')}
            </div>
        </div>` : 
        '<div class="alert alert-warning">AI 피드백을 불러오는 중 오류가 발생했습니다.</div>';

    // 전체 분석 결과 HTML 조립
    analysisResults.innerHTML = `
        <div class="analysis-result">
            <div class="card border-0 shadow-sm mb-4">
                <div class="card-body">
                    <h3 class="card-title h4 mb-4 text-primary">
                        <i class="bi bi-graph-up me-2"></i>발표 분석 결과
                    </h3>
                    
                    <div class="result-item mb-4">
                        <h5 class="d-flex align-items-center mb-3">
                            <i class="bi bi-chat-square-text me-2 text-primary"></i>
                            발화 내용
                        </h5>
                        <div class="p-3 bg-light rounded-2">
                            <p class="mb-0">${analysis.full_text || '분석된 텍스트가 없습니다.'}</p>
                        </div>
                    </div>
                    
                    <div class="row g-4">
                        <div class="col-md-6">
                            <div class="card h-100 border-0 shadow-sm">
                                <div class="card-body">
                                    <h5 class="card-title d-flex align-items-center">
                                        <i class="bi bi-speedometer2 me-2 text-primary"></i>
                                        발화 속도
                                    </h5>
                                    <div class="d-flex align-items-baseline mb-2">
                                        <span class="display-5 fw-bold me-2">${analysis.spm || 0}</span>
                                        <span class="text-muted">SPM</span>
                                    </div>
                                    <ul class="list-unstyled mb-2">
                                        <li><span class="badge bg-info text-dark">총 단어 수: ${analysis.word_count ?? 'N/A'}개</span></li>
                                        <li><span class="badge bg-secondary">총 음절 수: ${analysis.syllable_count ?? 'N/A'}개</span></li>
                                        <li><span class="badge bg-secondary">녹음 시간: ${(analysis.speech_duration ?? analysis.duration_sec ?? analysis.duration ?? 'N/A')}초</span></li>
                                    </ul>
                                    <p class="mb-0 text-muted">${analysis.spm_feedback || '분석 중...'}</p>
                                </div>
                            </div>
                        </div>
                        
                        <div class="col-md-6">
                            <div class="card h-100 border-0 shadow-sm">
                                <div class="card-body">
                                    <h5 class="card-title d-flex align-items-center">
                                        <i class="bi bi-chat-dots me-2 text-primary"></i>
                                        필러 단어 분석
                                    </h5>
                                    <div class="d-flex align-items-baseline mb-2">
                                        <span class="display-5 fw-bold me-2">${analysis.total_fillers || 0}</span>
                                        <span class="text-muted">회 사용</span>
                                    </div>
                                    ${fillerWordsHtml}
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    ${aiFeedbackHtml}
                    
                    <div class="text-center mt-4">
                        <button onclick="location.reload()" class="btn btn-primary px-4">
                            <i class="bi bi-arrow-repeat me-2"></i>새 발표 시작하기
                        </button>
                    </div>
                </div>
            </div>
        </div>`;
}
