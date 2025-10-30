# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

LangChain TRPG 시스템은 Flask, LangChain, Ollama를 사용한 AI 기반 테이블탑 롤플레잉 게임(TRPG) 플랫폼입니다. 외부 API를 통해 게임/캐릭터 정보를 가져오고, ChromaDB로 대화 메모리를 유지하며, ComfyUI를 통해 이미지를 생성합니다.

## 개발 명령어

### 애플리케이션 실행

```bash
# 서버 시작 (포트 5001)
python app.py

# 서버는 http://192.168.26.165:5001 에서 실행
# WebSocket 네임스페이스: /game/{game_id}
```

### 환경 설정

`.env` 파일 생성:
```
# Ollama LLM 설정
OLLAMA_URL=http://ollama.aikopo.net
OLLAMA_MODEL=gpt-oss:20b

# 외부 게임/캐릭터 API
EXTERNAL_API_URL=http://192.168.26.165:1024

# 이미지 관련 설정
IMAGE_BASE_URL=http://192.168.26.165:5001/images
IMAGE_STORAGE_PATH=./static/images

# ComfyUI 서버 설정
COMFYUI_URL=http://192.168.24.189:8188
COMFYUI_TIMEOUT=300

# Flask 설정
SECRET_KEY=your-secret-key
DEBUG=True
```

### 의존성 설치

```bash
# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 또는
venv\Scripts\activate  # Windows

# 의존성 설치
pip install -r requirements.txt

# 주요 의존성:
# - langchain (v0.3.7+) - AI 체인 및 프롬프트 관리
# - flask + flask-socketio + eventlet - 웹 프레임워크 및 WebSocket
# - chromadb - 벡터 데이터베이스 (대화 메모리 저장)
# - sentence-transformers - 임베딩 모델
# - requests - 외부 API 호출
```

### 캐시 파일 정리

```bash
# Python 캐시 파일 삭제 (EOFError 발생 시)
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
```

## 아키텍처 개요

### 메모리 시스템 (MongoDB 제거됨)

현재 시스템은 **단일 저장소 아키텍처**를 사용합니다:

**ChromaDB 벡터 메모리** (`memory/vector_memory.py`)
- 모든 대화 내역을 벡터화하여 저장
- **원본 텍스트도 함께 저장** (`page_content` 필드)
- 사용자 입력과 AI 응답을 **개별 문서로 저장** (턴당 2개 문서)
- 메타데이터:
  - `type`: "conversation" (대화 내역)
  - `role`: "user" 또는 "assistant"
  - `game_id`: 게임 식별자
  - `timestamp`: ISO 8601 형식
  - `image_url`: 이미지가 있는 경우 URL

**하이브리드 메모리 전략** (`agents/gamemaster.py:104-152`)
- 최근 N개 대화: 원본 텍스트 사용 (`RECENT_LIMIT = 10`)
- 오래된 대화: 벡터 검색으로 관련성 높은 것만 가져오기 (`k=3`)
- AI 컨텍스트 구성 시 두 가지 모두 포함

### 외부 API 통합

**게임/캐릭터 데이터** - 외부 API에서 가져옴 (`http://192.168.26.165:1024`)
- `GET /api/games/{game_id}` - 게임 정보
- `GET /api/games/{game_id}/characters` - 캐릭터 목록
- `PATCH /api/characters/game/{game_id}` - 캐릭터 정보 업데이트
  - body: `{ name?, class?, level?, stats?, inventory?, avatar?, health? }`
  - stats 구조: `{ strength, dexterity, wisdom, charisma }`

### 요청 처리 흐름

플레이어가 WebSocket으로 메시지를 보낼 때:

1. **세션 생성** (`POST /api/session/create`)
   - `game_id`를 받아 동적으로 `/game/{game_id}` 네임스페이스 등록

2. **WebSocket 연결** (클라이언트 → `/game/{game_id}`)
   - `game_message` 이벤트로 메시지 전송

3. **AI 응답 생성** (`agents/gamemaster.py:process_game_request()`)
   - 외부 API에서 게임/캐릭터 컨텍스트 가져오기
   - ChromaDB에서 관련 과거 대화 검색 (벡터 검색 k=3)
   - 최근 대화 원문 가져오기 (최근 10턴)
   - 하이브리드 컨텍스트 구성하여 LLM에 전달
   - `GAMEMASTER_CHAT_PROMPT`로 응답 생성
   - JSON 파싱: `{message, options, need_image, image_prompt, update_character?}`

4. **메모리 저장**
   - 사용자 입력 → ChromaDB (role="user")
   - AI 응답 → ChromaDB (role="assistant")

5. **캐릭터 업데이트** (선택적)
   - AI가 `update_character` 응답 시 외부 API 호출
   - Deep Merge 방식으로 기존 데이터와 병합

6. **이미지 생성** (선택적)
   - `need_image=true` 시 ComfyUI에 비동기 요청
   - 폴링 방식으로 이미지 완성 대기
   - 서버에 파일 저장 → URL 전송
   - ChromaDB에 이미지 URL 저장

### 주요 컴포넌트

**GameMaster 에이전트** (`agents/gamemaster.py`)
- 단일 LLMChain 사용 (`gm_chain`)
- `image_chain`, `character_chain`은 초기화만 되어있고 미사용
- `process_game_request()`: 전체 게임 로직 조율
- `_prepare_game_context()`: 외부 API에서 게임 컨텍스트 준비
- `_update_character_info()`: Deep Merge로 캐릭터 정보 업데이트

**벡터 메모리 매니저** (`memory/vector_memory.py`)
- 게임별 ChromaDB 컬렉션 관리
- `add_scenario_data()`: 대화 저장 (type 메타데이터 보존)
- `search_relevant_context()`: 의미론적 검색
- MongoDB 의존성 제거됨

**프롬프트 템플릿** (`prompts/gamemaster_templates.py`)
- `GAMEMASTER_CHAT_PROMPT`: 메인 게임 프롬프트
- 필수 변수: `game_context`, `chat_summary`, `user_input`
- JSON 응답 형식 강제
- **이미지 프롬프트는 반드시 영어로 작성**

**ComfyUI 매니저** (`comfy_manager.py`)
- LoRA 워크플로우 사용 (`lora.json`)
- 폴링 기반 이미지 생성 확인
- 이미지 파일명: `game_{game_id}_{timestamp}_{uuid}.{ext}`

**WebSocket 네임스페이스** (`app.py:GameNamespace`)
- 게임별 독립 네임스페이스 (`/game/{game_id}`)
- 이벤트: `game_message`, `game_response`, `game_image`, `status`
- eventlet 기반 비동기 처리

## 중요한 패턴

### Deep Merge 패턴

캐릭터 정보 업데이트 시 재귀적 병합 (`_deep_merge()`)
- 딕셔너리: 재귀적으로 병합 (중첩된 stats 등)
- 리스트: 전체 교체 (inventory 등)
- 기본값: 덮어쓰기

### 이미지 저장 및 URL 전송

1. ComfyUI에서 이미지 생성
2. 서버에 파일 저장: `./static/images/game_{game_id}_{timestamp}_{uuid}.png`
3. URL 생성: `http://192.168.26.165:5001/images/{filename}`
4. WebSocket으로 URL 전송 (`game_image` 이벤트)
5. ChromaDB에 이미지 URL 저장 (별도 문서)

### 에러 처리

- LLM 응답이 None 또는 빈 문자열: 기본 응답 반환
- JSON 파싱 실패: 원본 텍스트를 message로 사용
- `update_character`가 None: 안전하게 무시
- 리스트를 딕셔너리처럼 접근: Deep Merge에서 타입 체크

### WebSocket 연결 프로세스

```python
# 1. 세션 생성
POST /api/session/create
body: { game_id: "24", session_id: "uuid" }

# 2. WebSocket 연결
io('http://192.168.26.165:5001/game/24')

# 3. 메시지 전송
socket.emit('game_message', { message: "마을로 간다" })

# 4. 응답 수신
socket.on('game_response', (data) => {
  // data.message, data.options, data.need_image
})

# 5. 이미지 수신 (비동기)
socket.on('game_image', (data) => {
  // data.image_urls[0]
})
```

## API 엔드포인트

### 게임 관리
- `POST /api/session/create` - WebSocket 네임스페이스 등록
- `GET /api/history/{game_id}` - ChromaDB에서 전체 대화 히스토리 조회
- `GET /images/{filename}` - 생성된 이미지 파일 서빙

### WebSocket 이벤트
- `connect` - 클라이언트 연결 성공
- `game_message` - 플레이어 행동 전송: `{message}`
- `game_response` - GM 응답 수신: `{success, message, options, need_image, image_info}`
- `game_image` - 이미지 URL 수신: `{success, game_id, image_urls, timestamp}`
- `status` - 서버 상태 메시지

## 설정

`config/settings.py`에 중앙화:
- `EXTERNAL_API_CONFIG`: 외부 게임/캐릭터 API (환경변수: `EXTERNAL_API_URL`)
- `OLLAMA_CONFIG`: LLM 연결 (환경변수: `OLLAMA_URL`, `OLLAMA_MODEL`)
- `CHROMA_CONFIG`: ChromaDB 영속화 디렉토리 (환경변수: `CHROMA_PATH`)
- `VECTOR_MEMORY_CONFIG`: 임베딩 모델 (all-MiniLM-L6-v2), 검색 k=5
- `IMAGE_STORAGE_CONFIG`: 이미지 저장 디렉토리 (환경변수: `IMAGE_BASE_URL`, `IMAGE_STORAGE_PATH`)
- `COMFYUI_CONFIG`: ComfyUI 서버 주소 (환경변수: `COMFYUI_URL`, `COMFYUI_TIMEOUT`)

**주소 변경 시**: `.env` 파일의 환경변수만 수정하면 자동 반영됩니다. 코드 수정 불필요.

## 개발 참고사항

### MongoDB 관련
- MongoDB 코드는 존재하지만 **사용하지 않음**
- `data/mongo_manager.py` 파일은 있지만 import되지 않음
- `memory/vector_memory.py`에서 MongoDB import 주석 처리됨

### 벡터 저장소
- ChromaDB는 CPU 기반 임베딩 사용 (GPU 불필요)
- 게임별 독립 컬렉션: `trpg_game_{game_id}`
- `./chroma_db/` 디렉토리에 영속화

### eventlet 필수
- Flask-SocketIO는 **반드시 eventlet 모드**로 실행
- `eventlet.monkey_patch()` 필수
- threading 모드는 WebSocket 에러 발생

### 캐시 파일 에러
- `EOFError: marshal data too short` 발생 시 `__pycache__` 삭제
- `.pyc` 파일 손상으로 인한 에러

### 프롬프트 중요 사항
- AI에게 **이미지 프롬프트는 반드시 영어로** 작성하도록 지시
- 캐릭터 업데이트는 게임 ID만 사용 (character_id 불필요)
- stats 필드명: strength, dexterity, wisdom, charisma
- 체력 정보: health (현재), maxHealth (최대)

### 대화 저장 방식
- 사용자 입력과 AI 응답을 **개별 문서로 분리 저장**
- 턴당 2개 문서 생성 (role="user", role="assistant")
- 벡터 검색 시 맥락 유지를 위해 최근 대화는 원문 사용

### 캐릭터 사망 처리
- 체력이 0 이하가 되면 `_handle_character_death()` 호출
- ChromaDB에서 전체 대화 히스토리 로드
- LLM이 죽음의 원인과 캐릭터 여정 요약 생성
- `game_over: true` 플래그와 함께 최종 메시지 반환
- 선택지 없음 (`options: []`)

### ChromaDB 데이터 초기화
- `./chroma_db/` 폴더 삭제 시 모든 대화 내역 삭제됨
- `chroma.sqlite3` 파일도 안전하게 삭제 가능
- 서버 재시작 시 자동으로 재생성됨
- 외부 API 데이터는 영향받지 않음
