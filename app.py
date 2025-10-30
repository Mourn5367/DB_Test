"""
LangChain 기반 TRPG 시스템 메인 애플리케이션
Flask + LangChain + Ollama를 사용한 간소화된 구조
"""

import os
import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, Namespace, emit
import logging
from datetime import datetime
import uuid
import time

# 프로젝트 모듈 임포트
from config.settings import get_config
from agents.gamemaster import gamemaster
from memory.game_memory import memory_manager, context_manager
from comfy_manager import ComfyUIManager
import copy

# Flask 앱 초기화
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'langchain-trpg-secret-key')
socketio = SocketIO(
    app,
        cors_allowed_origins="*",
    async_mode='eventlet',
    ping_timeout=60,
    ping_interval=25
)

# CORS 설정 (모든 HTTP 요청에 대해)
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# 게임 세션 저장소
game_sessions = {}

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 설정 로드
config = get_config()
image_config = get_config("image_storage")
comfyui_config = get_config("comfyui")

# 이미지 저장 디렉토리 생성
IMAGE_STORAGE_DIR = image_config["storage_directory"]
os.makedirs(IMAGE_STORAGE_DIR, exist_ok=True)
logger.info(f"📁 이미지 저장 디렉토리: {IMAGE_STORAGE_DIR}")

# ComfyUI 매니저 초기화
try:
    comfyui_url = comfyui_config["server_url"]
    logger.info(f"🔌 ComfyUI 연결 시도: {comfyui_url}")
    comfy_manager = ComfyUIManager(
        server_url=comfyui_url,
        timeout=comfyui_config["timeout"]
    )

    # 서버 연결 상태 확인
    if comfy_manager.is_available():
        comfy_manager.connect_websocket()
        logger.info("✅ ComfyUI 연결 성공")
    else:
        logger.error("❌ ComfyUI 서버에 접근할 수 없습니다")
        logger.error("   1. ComfyUI 서버가 실행 중인지 확인하세요")
        logger.error(f"   2. 주소가 올바른지 확인하세요: {comfyui_url}")
        comfy_manager = None
except Exception as e:
    logger.error(f"❌ ComfyUI 초기화 실패: {e}")
    import traceback
    logger.error(traceback.format_exc())
    comfy_manager = None


def generate_image_async(game_id: str, prompt: str):
    """비동기로 이미지 생성 및 클라이언트에게 전송"""
    if not comfy_manager:
        logger.warning(f"[{game_id}] ComfyUI가 초기화되지 않았습니다 (서버 시작 시 연결 실패)")
        return

    if not comfy_manager.is_available():
        logger.warning(f"[{game_id}] ComfyUI 서버에 연결할 수 없습니다")
        logger.warning(f"   ComfyUI 서버 확인: {comfyui_config['server_url']}/system_stats")
        return

    try:
        logger.info(f"🎨 [{game_id}] 이미지 생성 시작: {prompt}")

        # lora.json 워크플로우 복사 및 프롬프트 수정
        workflow = copy.deepcopy(comfy_manager.default_workflow)

        # 노드 6번: 프롬프트 설정
        if "6" in workflow:
            workflow["6"]["inputs"]["text"] = prompt

        # 워크플로우 큐에 추가
        prompt_id = comfy_manager.queue_prompt(workflow)

        if not prompt_id:
            logger.error(f"[{game_id}] 이미지 생성 큐 추가 실패")
            return

        logger.info(f"🎨 [{game_id}] 이미지 생성 큐 추가 완료: {prompt_id}")

        # 완료 대기 (폴링 방식으로 직접 확인)
        def wait_and_send():
            import time
            max_wait = 300  # 5분
            start_time = time.time()

            logger.info(f"⏳ [{game_id}] 이미지 생성 대기 중... (prompt_id: {prompt_id})")

            while time.time() - start_time < max_wait:
                # 히스토리에서 결과 확인
                history = comfy_manager.get_history(prompt_id)

                if history and prompt_id in history:
                    outputs = history[prompt_id].get('outputs', {})

                    # 이미지 찾기
                    image_urls = []
                    for node_id, output in outputs.items():
                        if 'images' in output:
                            logger.info(f"🖼️  [{game_id}] 이미지 발견: 노드 {node_id}, {len(output['images'])}개")

                            for img_info in output['images']:
                                # 이미지 다운로드
                                img_data = comfy_manager.get_image(
                                    img_info['filename'],
                                    img_info.get('subfolder', ''),
                                    img_info.get('type', 'output')
                                )

                                if img_data:
                                    # 고유한 파일명 생성
                                    timestamp = int(time.time() * 1000)
                                    unique_id = str(uuid.uuid4())[:8]
                                    file_ext = img_info['filename'].split('.')[-1] if '.' in img_info['filename'] else 'png'
                                    new_filename = f"game_{game_id}_{timestamp}_{unique_id}.{file_ext}"

                                    # 서버에 이미지 저장
                                    save_path = os.path.join(IMAGE_STORAGE_DIR, new_filename)
                                    with open(save_path, 'wb') as f:
                                        f.write(img_data)

                                    # URL 생성
                                    image_url = f"{image_config['base_url']}/{new_filename}"
                                    image_urls.append(image_url)

                                    logger.info(f"✅ [{game_id}] 이미지 저장 완료: {save_path}")
                                    logger.info(f"🔗 [{game_id}] 이미지 URL: {image_url}")

                    if image_urls:
                        # 전송할 데이터 구조 로깅
                        logger.info(f"\n{'='*60}")
                        logger.info(f"📤 [{game_id}] 이미지 URL 전송 준비")
                        logger.info(f"{'='*60}")
                        logger.info(f"   네임스페이스: /game/{game_id}")
                        logger.info(f"   이미지 개수: {len(image_urls)}")

                        for idx, url in enumerate(image_urls):
                            logger.info(f"   이미지 {idx+1}: {url}")

                        # WebSocket으로 이미지 URL 전송
                        namespace = f"/game/{game_id}"
                        payload = {
                            'success': True,
                            'game_id': game_id,
                            'prompt': prompt,
                            'image_urls': image_urls,
                            'timestamp': datetime.now().isoformat()
                        }

                        logger.info(f"\n🚀 [{game_id}] socketio.emit() 호출:")
                        logger.info(f"   이벤트: 'game_image'")
                        logger.info(f"   네임스페이스: {namespace}")

                        import json
                        logger.info(f"   페이로드 구조:\n{json.dumps(payload, indent=2, ensure_ascii=False)}")

                        socketio.emit('game_image', payload, namespace=namespace)

                        # ChromaDB에 이미지 URL 저장
                        try:
                            from memory.vector_memory import vector_memory_manager

                            # 이미지 정보를 별도 문서로 저장
                            first_image_url = image_urls[0] if image_urls else None
                            if first_image_url:
                                logger.info(f"📝 [{game_id}] ChromaDB에 이미지 URL 추가: {first_image_url}")
                                # 새로운 문서로 이미지 정보 추가
                                image_content = f"[생성된 이미지]\n프롬프트: {prompt}\nURL: {first_image_url}"
                                image_metadata = {
                                    "type": "conversation",
                                    "role": "assistant",
                                    "source": "generated_image",
                                    "game_id": game_id,
                                    "image_url": first_image_url,
                                    "prompt": prompt
                                }
                                vector_memory_manager.add_scenario_data(game_id, image_content, image_metadata)
                                logger.info(f"✅ [{game_id}] 이미지 정보 ChromaDB에 저장 완료")
                        except Exception as e:
                            logger.error(f"❌ [{game_id}] ChromaDB 저장 실패: {e}")

                        logger.info(f"✅ [{game_id}] 이미지 URL 전송 완료!")
                        logger.info(f"{'='*60}\n")
                        return
                    else:
                        logger.warning(f"⚠️  [{game_id}] 히스토리에 이미지 없음")
                        return

                # 2초 대기 후 재시도
                time.sleep(2)

            logger.error(f"❌ [{game_id}] 이미지 생성 시간 초과 ({max_wait}초)")

        # 별도 스레드에서 실행
        import threading
        thread = threading.Thread(target=wait_and_send, daemon=True)
        thread.start()

    except Exception as e:
        logger.error(f"[{game_id}] 이미지 생성 실패: {e}")

@app.route('/')
def index():
    """메인 페이지"""
    return render_template('index.html')

@app.route('/images/<path:filename>')
def serve_image(filename):
    """생성된 이미지 파일 서빙"""
    return send_from_directory(IMAGE_STORAGE_DIR, filename)

@app.route('/health')
def health_check():
    """시스템 상태 확인"""
    try:
        # 간단한 LLM 테스트
        test_response = gamemaster.llm.invoke("Hello")

        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "components": {
                "langchain": True,
                "ollama": bool(test_response),
                "memory": True
            }
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/api/session/create', methods=['POST'])
def create_session():
    """
    Node.js에서 게임 세션 정보 받아서 WebSocket 네임스페이스 등록

    Request:
    {
        "game_id": "13",
        "session_id": "uuid-xxx"
    }
    """
    try:
        data = request.get_json()
        game_id = data.get('game_id')
        session_id = data.get('session_id')

        if not game_id:
            return jsonify({
                "success": False,
                "error": "game_id가 필요합니다"
            }), 400

        logger.info(f"\n{'='*50}")
        logger.info(f"📡 게임 세션 등록 요청")
        logger.info(f"   게임 ID: {game_id}")
        logger.info(f"   세션 ID: {session_id}")
        logger.info(f"{'='*50}")

        # 이미 존재하는 세션인지 확인
        if game_id in game_sessions:
            logger.info(f"⚠️  세션 이미 존재: {game_id}")
            return jsonify({
                "success": True,
                "game_id": game_id,
                "websocket_namespace": f"/game/{game_id}",
                "status": "already_exists"
            })

        # 세션 등록
        game_sessions[game_id] = {
            "session_id": session_id,
            "active": True,
            "connection_count": 0
        }

        namespace = f"/game/{game_id}"

        # 동적으로 네임스페이스 등록
        socketio.on_namespace(GameNamespace(namespace, game_id))

        logger.info(f"✅ WebSocket 네임스페이스 등록 완료: {namespace}")

        return jsonify({
            "success": True,
            "game_id": game_id,
            "session_id": session_id,
            "websocket_namespace": namespace
        })

    except Exception as e:
        logger.error(f"❌ 세션 생성 실패: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    """채팅 API - LangChain 메모리 사용"""
    try:
        data = request.get_json()
        user_input = data.get('message', '')
        game_id = data.get('game_id', 'default-game')

        if not user_input.strip():
            return jsonify({
                "success": False,
                "error": "메시지를 입력해주세요."
            }), 400

        # GameMaster 처리
        result = gamemaster.process_game_request(game_id, user_input)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Chat API error: {e}")
        return jsonify({
            "success": False,
            "error": "서버 오류가 발생했습니다.",
            "details": str(e)
        }), 500

@app.route('/api/memory/<game_id>')
def get_memory_info(game_id):
    """게임 메모리 정보 조회"""
    try:
        stats = gamemaster.get_memory_stats(game_id)
        return jsonify({
            "success": True,
            "game_id": game_id,
            "memory_stats": stats
        })
    except Exception as e:
        logger.error(f"Memory info error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/reset/<game_id>', methods=['POST'])
def reset_game(game_id):
    """게임 리셋"""
    try:
        gamemaster.reset_game(game_id)
        return jsonify({
            "success": True,
            "message": f"게임 {game_id}가 리셋되었습니다."
        })
    except Exception as e:
        logger.error(f"Reset game error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/context/<game_id>')
def get_game_context(game_id):
    """게임 컨텍스트 조회"""
    try:
        context = context_manager.get_context(game_id)
        return jsonify({
            "success": True,
            "game_id": game_id,
            "context": context
        })
    except Exception as e:
        logger.error(f"Context error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/history/<game_id>')
def get_chat_history(game_id):
    """채팅 히스토리 조회 - ChromaDB에서 원문 전체 조회"""
    try:
        from memory.vector_memory import vector_memory_manager

        # 벡터 스토어 초기화 (없으면 생성)
        if game_id not in vector_memory_manager.vector_stores:
            vector_memory_manager._initialize_game_vector_store(game_id)

        vector_store = vector_memory_manager.vector_stores.get(game_id)

        if not vector_store:
            return jsonify({
                "success": True,
                "game_id": game_id,
                "history": [],
                "total": 0
            })

        # 대화 타입만 필터링하여 전체 조회
        try:
            results = vector_store.get(
                where={"type": "conversation"}
            )

            history = []
            if results and 'documents' in results:
                for idx, (doc, metadata) in enumerate(zip(results['documents'], results['metadatas'])):
                    history.append({
                        "content": doc,  # 원문 텍스트
                        "role": metadata.get('role', 'unknown'),  # user 또는 assistant
                        "timestamp": metadata.get('timestamp', ''),
                        "sequence_number": metadata.get('sequence_number', idx),
                        "image_url": metadata.get('image_url'),  # 이미지 URL (있으면)
                        "game_id": metadata.get('game_id', game_id)
                    })

            # timestamp 또는 sequence_number로 정렬 (오래된 것 → 최신 순)
            history.sort(key=lambda x: (x.get('timestamp', ''), x.get('sequence_number', 0)))

            return jsonify({
                "success": True,
                "game_id": game_id,
                "history": history,
                "total": len(history),
                "source": "chromadb_original_text"
            })

        except Exception as e:
            logger.error(f"ChromaDB query error: {e}")
            return jsonify({
                "success": True,
                "game_id": game_id,
                "history": [],
                "total": 0,
                "error": str(e)
            })

    except Exception as e:
        logger.error(f"History API error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# 게임별 WebSocket 네임스페이스 클래스
class GameNamespace(Namespace):
    """게임별 WebSocket 네임스페이스 - AI 모델 실행"""

    def __init__(self, namespace, game_id):
        super().__init__(namespace)
        self.game_id = game_id

    def on_connect(self):
        """클라이언트 연결"""
        logger.info(f"🔌 [{self.game_id}] 클라이언트 연결: {request.sid}")

        if self.game_id in game_sessions:
            game_sessions[self.game_id]["connection_count"] += 1

        self.emit('status', {
            'message': f'게임 세션 {self.game_id}에 연결되었습니다.'
        })

    def on_disconnect(self):
        """클라이언트 연결 해제"""
        logger.info(f"❌ [{self.game_id}] 클라이언트 연결 해제: {request.sid}")

        if self.game_id in game_sessions:
            game_sessions[self.game_id]["connection_count"] -= 1

    def on_message(self, data):
        """메시지 수신 - GameMaster AI 모델 실행"""
        try:
            # 문자열 또는 딕셔너리 처리
            if isinstance(data, dict):
                message = data.get('message', '')
            else:
                message = str(data)

            logger.info(f"💬 [{self.game_id}] 메시지 수신: {message}")

            # GameMaster AI 처리
            logger.info(f"🤖 [{self.game_id}] AI 모델 실행 중...")
            result = gamemaster.process_game_request(self.game_id, message)

            # LLM 생성 결과 전체 로깅 (디버깅용)
            logger.info(f"\n{'='*60}")
            logger.info(f"🔍 [{self.game_id}] LLM 생성 결과 (전체):")
            logger.info(f"{'='*60}")
            import json
            logger.info(json.dumps(result, indent=2, ensure_ascii=False))
            logger.info(f"{'='*60}\n")

            # AI 응답 전송
            response = {
                "success": result.get("success", True),
                "game_id": self.game_id,
                "message": result.get("message", ""),
                "response": result.get("message", ""),
                "options": result.get("options", []),
                "need_image": result.get("need_image", False),
                "image_info": result.get("image_info"),
                "timestamp": result.get("timestamp")
            }

            # 클라이언트로 전송하는 데이터도 로깅
            logger.info(f"📤 [{self.game_id}] 클라이언트로 전송:")
            logger.info(json.dumps(response, indent=2, ensure_ascii=False))

            self.emit('game_response', response)
            logger.info(f"✅ [{self.game_id}] AI 응답 전송 완료")

            # 이미지 생성이 필요한 경우 비동기로 생성
            if result.get("need_image", False):
                image_info = result.get("image_info")
                if image_info and image_info.get("prompt"):
                    logger.info(f"🎨 [{self.game_id}] 이미지 생성 요청: {image_info['prompt']}")
                    generate_image_async(self.game_id, image_info["prompt"])

        except Exception as e:
            logger.error(f"⚠️  [{self.game_id}] 메시지 처리 실패: {e}")
            self.emit('error', {'message': str(e)})


# 기본 네임스페이스 핸들러 (잘못된 연결 처리)
@socketio.on('connect')
def handle_connect():
    """기본 네임스페이스 연결 - 에러 안내"""
    logger.warning(f"⚠️  기본 네임스페이스 연결: {request.sid}")
    emit('error', {
        'message': '게임 세션 네임스페이스로 연결해주세요. 예: /game/{game_id}'
    })

@socketio.on('disconnect')
def handle_disconnect():
    """기본 네임스페이스 연결 해제"""
    logger.info(f"❌ 기본 네임스페이스 연결 해제: {request.sid}")

if __name__ == '__main__':
    # 템플릿 폴더 생성 (없으면)
    os.makedirs('templates', exist_ok=True)

    # 개발 서버 실행
    debug_mode = os.getenv('DEBUG', 'True').lower() == 'true'

    logger.info("🎮 LangChain TRPG 시스템 시작")
    logger.info(f"🔗 Ollama URL: {config['ollama']['base_url']}")
    logger.info(f"🤖 Model: {config['ollama']['model']}")

    socketio.run(
        app,
        host='0.0.0.0',
        port=5001,
        debug=debug_mode
    )