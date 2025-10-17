"""
간단한 WebSocket 클라이언트
서버의 특정 게임 세션 네임스페이스에 연결
"""

import socketio
import time
import sys

SERVER_URL = "http://localhost:5001"


class GameWebSocketClient:
    """게임 WebSocket 클라이언트"""

    def __init__(self, server_url=SERVER_URL):
        self.server_url = server_url
        self.sio = None
        self.namespace = None
        self.game_id = None
        self.connected = False

    def connect_to_game(self, game_id):
        """게임 세션 ID로 WebSocket 연결"""
        self.game_id = game_id
        self.namespace = f"/game/{game_id}"

        print(f"🎮 게임 세션: {game_id}")
        print(f"🔌 연결 시도: {self.server_url}{self.namespace}")

        # SocketIO 클라이언트 생성
        self.sio = socketio.Client()

        # 이벤트 핸들러 등록
        @self.sio.on('status', namespace=self.namespace)
        def on_status(data):
            print(f"📢 {data.get('message')}")

        @self.sio.on('game_response', namespace=self.namespace)
        def on_game_response(data):
            print(f"\n{'='*50}")
            print(f"📥 게임 응답:")
            print(f"   {data.get('response')}")
            print(f"{'='*50}\n")

        @self.sio.on('error', namespace=self.namespace)
        def on_error(data):
            print(f"⚠️  에러: {data}")

        @self.sio.on('connect', namespace=self.namespace)
        def on_connect():
            self.connected = True
            print(f"✅ 연결 성공!")

        @self.sio.on('disconnect', namespace=self.namespace)
        def on_disconnect():
            self.connected = False
            print(f"❌ 연결 종료")

        try:
            # WebSocket 연결
            self.sio.connect(self.server_url, namespaces=[self.namespace])
            time.sleep(0.5)
            return True

        except Exception as e:
            print(f"❌ 연결 실패: {e}")
            print(f"\n⚠️  서버 확인 사항:")
            print(f"   1. test_ws_server.py가 실행 중인가요?")
            print(f"   2. 세션이 생성되었나요?")
            print(f"      curl -X POST {self.server_url}/api/session/create \\")
            print(f"        -H 'Content-Type: application/json' \\")
            print(f"        -d '{{\"game_id\": \"{game_id}\"}}'")
            return False

    def send_message(self, message):
        """메시지 전송"""
        if not self.connected:
            print("⚠️  WebSocket이 연결되지 않았습니다")
            return False

        try:
            print(f"💬 전송: {message}")
            self.sio.emit('message', {'message': message}, namespace=self.namespace)
            return True
        except Exception as e:
            print(f"❌ 전송 실패: {e}")
            return False

    def disconnect(self):
        """연결 종료"""
        if self.sio and self.connected:
            self.sio.disconnect()

    def keep_alive(self):
        """연결 유지 (계속 실행)"""
        print("\n📝 메시지를 입력하세요 (종료: quit)")
        print("-" * 50)

        try:
            while self.connected:
                user_input = input("\n> ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ['quit', 'exit', '종료']:
                    break

                self.send_message(user_input)
                time.sleep(0.5)

        except KeyboardInterrupt:
            print("\n")
        except EOFError:
            print("\n")

        self.disconnect()
        print("👋 종료")


if __name__ == "__main__":
    try:
        import socketio
    except ImportError:
        print("❌ 필요한 패키지를 설치하세요:")
        print("   pip install python-socketio[client]")
        sys.exit(1)

    print("=" * 50)
    print("🎮 WebSocket 클라이언트")
    print("=" * 50)

    # 게임 세션 ID 입력
    if len(sys.argv) > 1:
        game_id = sys.argv[1]
    else:
        print("\n게임 세션 ID를 입력하세요")
        print("(서버에 먼저 세션이 생성되어 있어야 합니다)")
        game_id = input("게임 세션 ID: ").strip()

    if not game_id:
        print("❌ 세션 ID가 필요합니다")
        sys.exit(1)

    print(f"\n연결 정보:")
    print(f"  서버: {SERVER_URL}")
    print(f"  게임 ID: {game_id}")
    print("-" * 50)

    # 연결 및 실행
    client = GameWebSocketClient(SERVER_URL)

    if client.connect_to_game(game_id):
        # 연결 성공 시 계속 실행
        client.keep_alive()
    else:
        print("\n❌ 연결 실패")
        sys.exit(1)
