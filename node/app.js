const express = require('express');
const path = require('path');
const bodyParser = require('body-parser');
const morgan = require('morgan');
const cookieParser = require('cookie-parser');
require('dotenv').config();

const app = express();

// 미들웨어 설정
app.use(morgan('dev'));
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: false }));
app.use(cookieParser());

// 정적 파일 제공
app.use(express.static(path.join(__dirname, 'public')));

// 라우트 연결
const mainRouter = require('./routes/main');
app.use('/', mainRouter);

// 404 처리
app.use((req, res) => {
  res.status(404).send('Not Found');
});

// 에러 처리
app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).send('Server Error');
});

// 서버 실행
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server started on port ${PORT}`);
});

module.exports = app;
