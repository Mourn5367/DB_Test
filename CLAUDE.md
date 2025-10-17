# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

LangChain TRPG 시스템은 Flask, LangChain, Ollama를 사용한 테이블탑 롤플레잉 게임(TRPG) 플랫폼입니다. AI 기반 게임마스터가 게임 세션을 관리하고, 여러 저장소 시스템에 걸쳐 대화 메모리를 유지하며, 플레이어에게 상황에 맞는 응답을 생성합니다.

## 개발 명령어

### 애플리케이션 실행

```bash
# 서버 시작
python app.py

# 서버는 http://localhost:5000 에서 실행됩니다
# WebSocket 엔드포인트도 같은 주소에서 사용 가능합니다
```

### 환경 설정

`.env` 파일 생성:
```
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
SECRET_KEY=your-secret-key
DEBUG=True
```

### 의존성 설치

```bash
# 의존성 설치
pip install -r requirements.txt

# 주요 의존성:
# - langchain (v0.3.7+)
# - flask + flask-socketio (웹 프레임워크)
# - pymongo (MongoDB 클라이언트)
# - chromadb (벡터 데이터베이스)
# - sentence-transformers (임베딩)
```

### 테스트

```bash
# 테스트 실행
pytest tests/

# 시스템 상태 확인
curl http://localhost:5000/health
```

## 아키텍처 개요

### 3계층 메모리 시스템

시스템은 게임 상태와 대화 컨텍스트를 유지하기 위해 정교한 3계층 메모리 아키텍처를 사용합니다:

1. **LangChain ConversationSummaryBufferMemory** (memory/game_memory.py)
   - 자동 요약 기능이 있는 인메모리 대화 히스토리
   - 토큰 제한: 4000 토큰, 요약 임계값: 3000 토큰
   - 제한 도달 시 오래된 대화를 자동으로 요약
   - 게임 로드 시 MongoDB에서 복원

2. **MongoDB 저장소** (data/mongo_manager.py)
   - 모든 게임 데이터의 영구 저장소
   - 컬렉션: game_sessions, chat_history, story_events, scenarios, character_templates, locations, event_templates
   - 채팅 메시지는 순서 정렬을 위해 sequence_number와 함께 저장
   - 게임 상태 복원을 위한 신뢰할 수 있는 소스

3. **ChromaDB 벡터 메모리** (memory/vector_memory.py)
   - 게임 콘텐츠에 대한 의미론적 검색
   - 저장 항목: 과거 대화, 시나리오 데이터, 캐릭터 배경, 위치 정보, 이벤트 템플릿
   - HuggingFace 임베딩 사용 (all-MiniLM-L6-v2)
   - 관련 과거 이벤트를 검색하여 컨텍스트 인식 응답 가능

### 요청 처리 흐름

플레이어가 메시지를 보낼 때:
1. `app.py`가 WebSocket 또는 REST API를 통해 메시지 수신
2. `agents/gamemaster.py:process_game_request()`가 처리 조율:
   - SessionContextManager에서 게임 컨텍스트 준비
   - ChromaDB에서 관련 과거 컨텍스트 검색 (k=3 문서)
   - LangChain 메모리 검색 (요약된 대화 히스토리)
   - GAMEMASTER_CHAT_PROMPT로 LLMChain 실행
   - LangChain 메모리와 MongoDB에 대화 저장
   - ChromaDB 벡터 저장소에 대화 추가
3. message, options, 이미지 생성 플래그가 포함된 JSON 응답 반환

### 주요 컴포넌트

**GameMaster 에이전트** (agents/gamemaster.py)
- LangChain LLMChain을 사용하는 핵심 AI 에이전트
- 3개의 특화된 체인:
  - `gm_chain`: 메인 게임 내레이션 및 응답 생성
  - `image_chain`: 장면에 시각적 표현이 필요한지 판단
  - `character_chain`: 캐릭터별 상호작용 처리
- `process_game_request()`에서 3개의 메모리 시스템 모두 통합

**메모리 매니저**
- `TRPGMemoryManager`: 게임 세션별 LangChain 대화 메모리 관리, 첫 접근 시 MongoDB에서 복원
- `SessionContextManager`: 게임 상태 추적 (시나리오, 캐릭터, 위치), MongoDB에 영속화
- `VectorMemoryManager`: 게임별 ChromaDB 컬렉션 관리, 의미론적 검색 지원

**데이터 레이어**
- `MongoManager`: MongoDB 연결 및 인덱스 관리
- `ScenarioDataManager`: 시나리오, 캐릭터, 위치, 이벤트에 대한 CRUD 작업, 첫 실행 시 기본 데이터 초기화 포함

**프롬프트 템플릿** (prompts/gamemaster_templates.py)
- 구조화된 LangChain PromptTemplates
- GAMEMASTER_CHAT_PROMPT 필요 변수: game_context, chat_summary, user_input
- JSON 응답 형식 강제: {message, options, need_image, image_prompt}

## 중요한 패턴

### 게임 세션 생명주기

- 각 게임은 고유한 `game_id` 문자열로 식별
- 게임에 첫 접근 시 트리거:
  - LangChain 메모리 생성 및 MongoDB에서 복원
  - ChromaDB 컬렉션 생성 및 기본 시나리오 + 과거 대화 로딩
  - 새 게임인 경우 기본 컨텍스트 설정
- 세션 컨텍스트는 인메모리에 유지되며 업데이트 시 MongoDB에 동기화

### 메모리 동기화

3개의 메모리 시스템 모두 동기화 유지:
- 새 대화 → LangChain 메모리 + MongoDB + ChromaDB
- 게임 리셋 → `gamemaster.reset_game(game_id)`를 통해 3개 시스템 모두 초기화
- 메모리 복원 → LangChain과 ChromaDB가 MongoDB에서 로드

### LLM 통합

- 설정 가능한 모델로 Ollama 사용 (기본값: 원격 서버의 gpt-oss:120b)
- 모든 LLM 호출은 LangChain 추상화를 통해 실행 (LLMChain, PromptTemplate)
- Temperature: 게임플레이는 0.7, 요약은 0.3
- 타임아웃: 요청당 120초

## API 엔드포인트

### 게임 관리
- `POST /api/chat` - 게임 메시지 전송
- `POST /api/reset/{game_id}` - 모든 게임 데이터 리셋
- `GET /api/memory/{game_id}` - 모든 시스템의 메모리 통계 조회
- `GET /api/context/{game_id}` - 현재 게임 컨텍스트 조회
- `GET /api/history/{game_id}?limit=N` - 채팅 히스토리 조회

### 데이터 접근
- `GET /api/scenarios` - 모든 시나리오 템플릿 목록
- `GET /api/scenarios/{type}` - 특정 시나리오 조회
- `GET /api/characters` - 캐릭터 템플릿 목록
- `GET /api/locations` - 위치 데이터 목록
- `GET /api/events` - 이벤트 템플릿 목록

### WebSocket 이벤트
- `connect` - 클라이언트 연결 성공
- `game_message` - 플레이어 행동 전송: {game_id, message}
- `game_response` - GM 응답 수신: {success, message, options, need_image, image_info}
- `error` - 에러 알림

## 설정

모든 설정은 `config/settings.py`에 중앙화:
- `OLLAMA_CONFIG`: LLM 연결 설정
- `MEMORY_CONFIG`: LangChain 메모리 제한 및 요약 임계값
- `MONGODB_CONFIG`: MongoDB 연결 정보
- `CHROMA_CONFIG`: ChromaDB 영속화 디렉토리
- `VECTOR_MEMORY_CONFIG`: 임베딩 모델 및 검색 설정
- `GAME_CONFIG`: 기본 시나리오 및 세션 관리

## 개발 참고사항

- 빈 디렉토리 `chains/`와 `tools/`는 향후 커스텀 LangChain chains/tools 확장을 위한 것으로 보임
- MongoDB는 첫 실행 시 기본 데이터를 자동으로 초기화 (시나리오, 캐릭터, 위치, 이벤트)
- ChromaDB는 `./chroma_db/` 디렉토리에 영속화
- 벡터 저장소는 CPU 기반 임베딩 사용 (GPU 불필요)
- chat_history의 sequence_number는 동시 요청 시에도 올바른 대화 순서를 보장
- 이미지 생성은 계획되어 있지만 완전히 구현되지 않음 (image_chain과 need_image 플래그는 존재)

## 개발 할 것
- api를 통해 게임 ID, 세션 ID 값을 받아서 게임 ID 값으로 웹소켓 연결.
- 연결된 웹소켓을 통해 프롬프트로 쓸 대화 내용을 받아와 Ollama AI 프롬프트 입력.
- 벡터 DB는 그대로 사용하고, 이 외의 DB는 Cluade 사용자가 주는 API를 써서 기존 DB 이용하는 방식 그대로 사용하도록 하기.
- 기존 내용을 그대로 유지하기에는 사용자가 API를 충분하게 제공하지 못한 경우 어떤 API가 필요하다고 얘기하기

