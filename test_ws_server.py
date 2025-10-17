"""
테스트용 WebSocket 서버
게임 세션 ID별로 WebSocket 네임스페이스 제공
세션 생성 시 자동으로 내부 클라이언트 연결
"""
# 1. Eventlet을 임포트하고 monkey_patch()를 호출합니다.
import eventlet
eventlet.monkey_patch() # 표준 라이브러리를 비동기 버전으로 패치

from flask import Flask, request, jsonify
from flask_socketio import SocketIO, Namespace, emit
import logging
import socketio as socketio_client
# threading 대신 eventlet.greenthread를 사용하는 것이 더 안전하지만,
# monkey_patch()를 하면 threading도 eventlet 환경에서 작동하게 됩니다.
import threading

app = Flask(__name__)
app.secret_key = 'test-secret-key'
# Eventlet을 사용하도록 명시적으로 설정할 수도 있지만, monkey_patch를 하면 대부분 자동으로 인식됩니다.
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet') 

# CORS 설정 (수동)
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 게임 세션 저장소
game_sessions = {}
# 자동 연결된 내부 클라이언트들
auto_clients = {}


@app.route('/health')
def health():
    """헬스 체크"""
    return jsonify({"status": "ok"})


@app.route('/api/session/create', methods=['POST'])
def create_session():
    """
    외부에서 게임 ID와 세션 ID 받기
    WebSocket 네임스페이스 생성 및 등록

    Request:
    {
        "game_id": "my-game-001",
        "session_id": "session-12345"
    }

    Response:
    {
        "success": true,
        "game_id": "my-game-001",
        "session_id": "session-12345",
        "websocket_namespace": "/game/my-game-001"
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

        if not session_id:
            return jsonify({
                "success": False,
                "error": "session_id가 필요합니다"
            }), 400

        logger.info(f"\n{'='*50}")
        logger.info(f"📡 외부에서 데이터 수신")
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

        logger.info(f"✅ 로컬 WebSocket 네임스페이스 등록 완료: {game_id}")
        logger.info(f"📡 로컬 대기 주소: ws://192.168.26.165:5001{namespace}")

        # 외부 WebSocket 서버에 자동 연결
        def auto_connect_external():
            try:
                import time
                time.sleep(0.5)

                # 외부 WebSocket 서버 연결
                # python-socketio 클라이언트는 http:// 형식 사용 (자동으로 WebSocket으로 업그레이드)
                external_url = "http://192.168.26.165:3000"
                external_namespace = f"/game/{game_id}"

                client = socketio_client.Client()

                @client.on('connect', namespace=external_namespace)
                def on_connect():
                    logger.info(f"🌐 외부 서버 연결 완료: {external_url}{external_namespace}")

                @client.on('disconnect', namespace=external_namespace)
                def on_disconnect():
                    logger.info(f"🌐 외부 서버 연결 해제: {game_id}")

                @client.on('status', namespace=external_namespace)
                def on_status(data):
                    logger.info(f"[외부-{game_id}] 📢 {data.get('message')}")

                @client.on('game_response', namespace=external_namespace)
                def on_response(data):
                    logger.info(f"[외부-{game_id}] 📥 응답: {data.get('response')}")
                    # 로컬 네임스페이스로 브로드캐스트
                    socketio.emit('game_response', data, namespace=namespace)

                # 외부 서버 연결 (네임스페이스 포함)
                logger.info(f"🔌 외부 서버 연결 시도: {external_url}{external_namespace}")
                client.connect(external_url, namespaces=[external_namespace])
                auto_clients[game_id] = client
                logger.info(f"✅ 외부 서버 연결 성공: {game_id}")

            except Exception as e:
                logger.error(f"❌ 외부 서버 연결 실패: {e}")

        # 백그라운드에서 연결
        threading.Thread(target=auto_connect_external, daemon=True).start()

        return jsonify({
            "success": True,
            "game_id": game_id,
            "session_id": session_id,
            "websocket_namespace": namespace,
            "auto_client": "connecting"
        })

    except Exception as e:
        logger.error(f"❌ 세션 생성 실패: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# 기본 네임스페이스 핸들러 (잘못된 연결 처리)
@socketio.on('connect')
def handle_default_connect():
    """기본 네임스페이스 연결 - 에러 안내"""
    logger.warning(f"⚠️  잘못된 연결: {request.sid} - 게임별 네임스페이스를 사용하세요")
    emit('error', {
        'message': '게임 세션 네임스페이스로 연결해주세요. 예: /game/{game_id}'
    })
    return False  # 연결 거부

@socketio.on('disconnect')
def handle_default_disconnect():
    """기본 네임스페이스 연결 해제"""
    logger.info(f"❌ 기본 네임스페이스 연결 해제: {request.sid}")


class GameNamespace(Namespace):
    """게임별 WebSocket 네임스페이스"""

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
        """메시지 수신"""
        try:
            # 문자열 또는 딕셔너리 처리
            if isinstance(data, dict):
                message = data.get('message', '')
            else:
                message = str(data)

            logger.info(f"💬 [{self.game_id}] 메시지 수신: {message}")

            # 테스트 응답 생성
            response = {
                "success": True,
                "game_id": self.game_id,
                "echo": message,
                "response": f"[{self.game_id}] 받은 메시지: {message}"
            }

            # 응답 전송
            self.emit('game_response', response)
            logger.info(f"📤 [{self.game_id}] 응답 전송 완료")

        except Exception as e:
            logger.error(f"⚠️  [{self.game_id}] 메시지 처리 실패: {e}")
            self.emit('error', {'message': str(e)})


if __name__ == '__main__':
    print("=" * 50)
    print("🧪 테스트용 WebSocket 서버")
    print("=" * 50)
    print("\n사용 방법:")
    print("1. POST /api/session/create - 게임 세션 생성")
    print("   Body: {\"game_id\": \"my-game\"}")
    print("2. WebSocket 연결: ws://localhost:5001/game/{game_id}")
    print("3. 메시지 전송: emit('message', {'message': '안녕'})")
    print("=" * 50)
    print()

    socketio.run(
        app,
        host='0.0.0.0',
        port=5001,
        debug=True
    )
