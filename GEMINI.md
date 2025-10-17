# GEMINI.md

## 프로젝트 개요

이 프로젝트는 LangChain과 Ollama를 사용하여 지능형 게임 마스터를 만드는 TRPG(테이블탑 롤플레잉 게임) 시스템입니다. 백엔드에는 Flask, 실시간 통신에는 Socket.IO, 데이터 저장소에는 MongoDB를 사용합니다. 이 시스템은 새로운 에이전트, 도구 및 프롬프트 템플릿을 쉽게 추가할 수 있도록 확장 가능하도록 설계되었습니다.

애플리케이션의 핵심은 게임 요청을 처리하고 대규모 언어 모델을 사용하여 응답을 생성하는 `LangChainGameMaster` 에이전트입니다. 에이전트는 메인 게임 마스터 체인, 이미지 생성 체인 및 캐릭터 상호 작용 체인의 조합을 사용하여 다양한 유형의 요청을 처리합니다.

이 시스템에는 LangChain의 `ConversationSummaryBufferMemory`를 사용하여 대화 기록을 저장하고 검색하는 메모리 관리 시스템도 포함되어 있습니다. 메모리는 MongoDB 데이터베이스에 유지되므로 나중에 게임 세션을 다시 시작할 수 있습니다.

이미지 생성은 게임 마스터의 프롬프트에 따라 이미지를 생성하기 위해 ComfyUI 서버에 연결하는 `ComfyUIManager`에 의해 처리됩니다.

## 빌드 및 실행

### 1. 사전 요구 사항

*   Python 3.8 이상
*   `llama3.1:8b` 모델이 포함된 Ollama
*   MongoDB
*   ComfyUI (선택 사항, 이미지 생성용)

### 2. 설치

```bash
pip install -r requirements.txt
```

### 3. 환경 변수

프로젝트 루트에 다음 변수를 사용하여 `.env` 파일을 만듭니다.

```
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
SECRET_KEY=your-secret-key
DEBUG=True
MONGO_HOST=localhost
MONGO_PORT=27017
MONGO_DB=trpg_nosql
```

### 4. 애플리케이션 실행

```bash
python app.py
```

애플리케이션은 `http://localhost:5001`에서 사용할 수 있습니다.

## 개발 규칙

*   **코드 스타일:** 이 프로젝트는 Python 코드에 대한 PEP 8 스타일 가이드를 따릅니다.
*   **테스트:** 이 프로젝트에는 WebSocket 기능을 테스트하기 위한 `simple_ws_client.py` 및 `test_ws_client.py`가 포함되어 있습니다.
*   **모듈성:** 프로젝트는 모듈로 구성되며 각 모듈은 특정 기능을 담당합니다.
*   **구성:** 모든 구성은 `config/settings.py` 파일에 저장됩니다.
*   **로깅:** 이 프로젝트는 `logging` 모듈을 사용하여 애플리케이션 상태에 대한 정보를 기록합니다.
