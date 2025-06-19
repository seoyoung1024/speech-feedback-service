const express = require('express');
const router = express.Router();
const path = require('path');
const fs = require('fs').promises;
const rateLimit = require('express-rate-limit');
const axios = require('axios');

// FastAPI 서버 설정
const FASTAPI_URL = 'http://localhost:5000';

// 라우트
router.get('/', (req, res) => {
    res.sendFile('index.html', { root: 'public' });
});

// 분석 API - FastAPI로 프록시
router.post('/api/analyze', async (req, res) => {
    try {
        const { session_id: sessionId = 'default', text } = req.body;
        
        if (!text) {
            return res.status(400).json({
                success: false,
                error: '텍스트가 제공되지 않았습니다.'
            });
        }

        // FastAPI로 분석 요청 전달
        const response = await axios.post(`${FASTAPI_URL}/api/analyze`, {
            session_id: sessionId,
            text: text
        });

        // 클라이언트에 결과 전달
        res.json(response.data);

    } catch (error) {
        console.error('분석 중 오류 발생:', error);
        
        // FastAPI 오류 메시지가 있으면 그대로 전달
        const errorMessage = error.response?.data?.error || '내부 서버 오류가 발생했습니다.';
        
        res.status(500).json({
            success: false,
            error: errorMessage
        });
    }
});

// 세션 초기화 API - FastAPI로 프록시
router.post('/api/reset-session', async (req, res) => {
    try {
        const { session_id: sessionId } = req.body;
        
        // FastAPI로 세션 초기화 요청 전달
        const response = await axios.post(`${FASTAPI_URL}/api/reset-session`, {
            session_id: sessionId
        });

        res.json(response.data);
        
    } catch (error) {
        console.error('세션 초기화 중 오류:', error);
        res.status(500).json({
            success: false,
            error: '세션 초기화에 실패했습니다.'
        });
    }
});

  // 새 세션 시작 함수
  async function resetSession() {
    try {
        const response = await fetch('/api/reset-session', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                session_id: sessionId
            })
        });
        
        const result = await response.json();
        if (result.success) {
            // 페이지 새로고침
            location.reload();
        }
    } catch (error) {
        console.error('세션 초기화 오류:', error);
        alert('새 세션을 시작하는 중 오류가 발생했습니다.');
    }
}

// 필러 워드 목록 조회 - FastAPI로 프록시
router.get('/api/filler-words', async (req, res) => {
    try {
        // FastAPI에서 필러 워드 목록 조회
        const response = await axios.get(`${FASTAPI_URL}/api/filler-words`);
        res.json(response.data);
    } catch (error) {
        console.error('필러 워드 목록 조회 실패:', error);
        res.status(500).json({
            success: false,
            error: '필러 워드 목록을 불러오는데 실패했습니다.'
        });
    }
});

// 상태 확인용 엔드포인트
router.get('/health', (req, res) => {
    res.status(200).send('ok');
});

module.exports = router;