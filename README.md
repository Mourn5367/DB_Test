# 🎮 LangChain TRPG System

LangChain과 Ollama를 사용한 차세대 TRPG(테이블탑 롤플레잉 게임) 시스템입니다.

## ✨ 주요 특징

### 🔗 LangChain 통합
- **자동 메모리 관리**: LangChain의 ConversationSummaryBufferMemory 사용
- **체인 기반 처리**: 프롬프트 템플릿과 체인으로 구조화된 AI 응답
- **확장 가능한 아키텍처**: 새로운 에이전트와 도구 쉽게 추가 가능

### 🤖 스마트 게임마스터
- **맥락 인식**: 게임 상태와 캐릭터 정보를 기억하는 AI
- **자동 이미지 생성 판단**: 상황에 맞는 시각적 연출 결정
- **실시간 상호작용**: WebSocket을 통한 즉시 응답

### 🎯 게임 세션 관리
- **게임별 독립 메모리**: 각 게임마다 별도의 컨텍스트 유지
- **자동 요약**: 긴 대화를 지능적으로 요약하여 메모리 효율성 확보
- **세션 지속성**: 게임 중단 후에도 상태 유지

## 🚀 빠른 시작

### 1. 필수 요구사항

```bash
# Ollama 설치 및 모델 다운로드
ollama pull llama3.1:8b

# Python 3.8+ 필요
python --version
```

### 2. 설치

```bash
cd langchain_trpg
pip install -r requirements.txt
```

### 3. 환경 설정

`.env` 파일 생성:
```bash
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
SECRET_KEY=your-secret-key
DEBUG=True
```

### 4. 실행

```bash
python app.py
```

브라우저에서 `http://localhost:5000` 접속

## 📁 프로젝트 구조

```
langchain_trpg/
├── app.py                 # Flask 메인 애플리케이션
├── requirements.txt       # Python 의존성
├── README.md             # 이 파일
│
├── config/               # 설정 관리
│   ├── __init__.py
│   └── settings.py       # 시스템 설정
│
├── agents/               # AI 에이전트
│   ├── __init__.py
│   └── gamemaster.py     # LangChain 기반 게임마스터
│
├── memory/               # 메모리 관리
│   ├── __init__.py
│   └── game_memory.py    # 게임별 메모리 시스템
│
├── prompts/              # 프롬프트 템플릿
│   ├── __init__.py
│   └── gamemaster_templates.py
│
└── templates/            # 웹 템플릿
    └── index.html        # 메인 UI
```

## 🎯 사용법

### 기본 게임 플레이

1. **게임 시작**
   - 브라우저에서 시스템 접속
   - 고유한 게임 ID 입력 (예: `my-adventure`)
   - 첫 번째 메시지 전송

2. **게임 진행**
   ```
   사용자: "마을 여관에서 모험을 시작하고 싶어"
   GM: "따뜻한 아침 햇살이 창문으로 들어옵니다..."
   ```

3. **선택지 활용**
   - AI가 제공하는 선택지 버튼 클릭
   - 또는 직접 행동 입력

### 고급 기능

#### API 엔드포인트

- `POST /api/chat` - 채팅 메시지 전송
- `GET /api/memory/{game_id}` - 메모리 상태 확인
- `POST /api/reset/{game_id}` - 게임 리셋
- `GET /api/context/{game_id}` - 게임 컨텍스트 조회
- `GET /api/history/{game_id}` - 채팅 히스토리 조회

#### 실시간 통신 (WebSocket)

```javascript
socket.emit('game_message', {
    game_id: 'my-game',
    message: '동굴로 들어간다'
});

socket.on('game_response', (data) => {
    console.log(data.message);
    console.log(data.options);
});
```

## ⚙️ 설정 옵션

### config/settings.py

```python
# Ollama 설정
OLLAMA_CONFIG = {
    "base_url": "http://localhost:11434",
    "model": "llama3.1:8b",
    "temperature": 0.7
}

# 메모리 관리
MEMORY_CONFIG = {
    "max_token_limit": 4000,
    "conversation_window": 20,
    "auto_summary": True
}

# 게임 설정
GAME_CONFIG = {
    "default_scenario": "medieval_fantasy",
    "max_characters_per_game": 6
}
```

## 🔧 커스터마이징

### 새로운 프롬프트 템플릿 추가

```python
# prompts/gamemaster_templates.py
CUSTOM_TEMPLATE = PromptTemplate(
    input_variables=["user_input", "context"],
    template="""
    커스텀 프롬프트 내용...
    사용자 입력: {user_input}
    컨텍스트: {context}
    """
)
```

### 새로운 체인 생성

```python
# agents/gamemaster.py
self.custom_chain = LLMChain(
    llm=self.llm,
    prompt=CUSTOM_TEMPLATE,
    verbose=True
)
```

## 🔍 모니터링 및 디버깅

### 메모리 상태 확인

```bash
curl http://localhost:5000/api/memory/my-game
```

### 로그 확인

```python
import logging
logging.basicConfig(level=logging.INFO)
```

### 건강 상태 체크

```bash
curl http://localhost:5000/health
```

## 🚀 기존 시스템과의 비교

| 기능 | 기존 시스템 | LangChain 시스템 |
|------|-------------|------------------|
| 메모리 관리 | 수동 구현 | LangChain 자동 관리 |
| 프롬프트 관리 | 하드코딩 | 템플릿 기반 |
| 체인 구성 | 복잡한 분기 | 체인 조합 |
| 확장성 | 제한적 | 높은 확장성 |
| 유지보수 | 어려움 | 쉬움 |

## 🌟 주요 개선사항

1. **단순화된 아키텍처**: 복잡한 멀티 에이전트 시스템을 LangChain 체인으로 간소화
2. **자동 메모리 관리**: 수동 메모리 관리 제거, LangChain의 메모리 시스템 활용
3. **표준화된 프롬프트**: PromptTemplate을 사용한 구조화된 프롬프트 관리
4. **실시간 통신**: WebSocket을 통한 즉시 응답과 상호작용

## 🛠 개발 모드

```bash
# 개발 서버 실행 (자동 재시작)
export DEBUG=True
python app.py

# 테스트 실행
pytest tests/

# 의존성 업데이트
pip install -r requirements.txt --upgrade
```

## 📝 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 🤝 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📞 지원

문제가 있거나 개선 제안이 있으시면 이슈를 등록해 주세요.

---

**즐거운 TRPG 모험을 시작하세요! 🎲✨**