"""
테스트용 WebSocket 클라이언트
1. HTTP로 게임 세션 ID 등록
2. 받은 네임스페이스로 WebSocket 연결
3. 메시지 송수신
"""

import socketio
import requests
import time
import sys

SERVER_URL = "http://localhost:5001"


def create_game_session(game_id):
    """게임 세션 생성 및 WebSocket 네임스페이스 받기"""
    print(f"📡 게임 세션 생성 요청: {game_id}")

    try:
        response = requests.post(
            f"{SERVER_URL}/api/session/create",
            json={"game_id": game_id},
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            namespace = data.get('websocket_namespace')
            print(f"✅ 세션 생성 성공!")
            print(f"   게임 ID: {data.get('game_id')}")
            print(f"   네임스페이스: {namespace}")
            return namespace
        else:
            print(f"❌ 세션 생성 실패: {response.text}")
            return None

    except Exception as e:
        print(f"❌ 연결 실패: {e}")
        return None


def test_websocket_communication(namespace, game_id):
    """WebSocket 통신 테스트"""
    print(f"\n🔌 WebSocket 연결 시작: {namespace}")

    # SocketIO 클라이언트 생성
    sio = socketio.Client()

    # 이벤트 핸들러 등록
    @sio.on('status', namespace=namespace)
    def on_status(data):
        print(f"📢 상태: {data.get('message')}")

    @sio.on('game_response', namespace=namespace)
    def on_game_response(data):
        print(f"\n📥 응답 수신:")
        print(f"   게임 ID: {data.get('game_id')}")
        print(f"   에코: {data.get('echo')}")
        print(f"   응답: {data.get('response')}")
        print()

    @sio.on('error', namespace=namespace)
    def on_error(data):
        print(f"⚠️  에러: {data}")

    try:
        # WebSocket 연결
        print(f"   연결 중...")
        sio.connect(SERVER_URL, namespaces=[namespace])
        print(f"✅ WebSocket 연결 성공!")

        time.sleep(1)

        # 테스트 메시지 전송
        test_messages = [
            "안녕하세요",
            "이것은 테스트입니다",
            f"게임 세션 {game_id}입니다"
        ]

        for i, msg in enumerate(test_messages, 1):
            print(f"\n📤 메시지 전송 [{i}/{len(test_messages)}]: {msg}")
            sio.emit('message', {'message': msg}, namespace=namespace)
            time.sleep(2)  # 응답 대기

        print("\n✅ 모든 메시지 전송 완료")

        # 잠시 대기 후 연결 종료
        time.sleep(2)
        sio.disconnect()
        print("👋 연결 종료")

    except Exception as e:
        print(f"❌ WebSocket 통신 실패: {e}")
        if sio.connected:
            sio.disconnect()


def main():
    """메인 함수"""
    print("=" * 50)
    print("🧪 WebSocket 클라이언트 테스트")
    print("=" * 50)

    # 게임 세션 ID 입력
    if len(sys.argv) > 1:
        game_id = sys.argv[1]
    else:
        game_id = input("\n게임 세션 ID 입력 (예: test-game-001): ").strip()
        if not game_id:
            game_id = "test-game-001"

    print(f"\n🎮 게임 세션 ID: {game_id}")
    print("-" * 50)

    # 1단계: 세션 생성
    namespace = create_game_session(game_id)
    if not namespace:
        print("\n❌ 테스트 실패: 세션 생성 불가")
        print("서버가 실행 중인지 확인하세요: python test_ws_server.py")
        return

    # 2단계: WebSocket 연결 및 통신
    time.sleep(1)
    test_websocket_communication(namespace, game_id)

    print("\n" + "=" * 50)
    print("✅ 테스트 완료!")
    print("=" * 50)


if __name__ == "__main__":
    try:
        import socketio
        import requests
    except ImportError:
        print("❌ 필요한 패키지를 설치하세요:")
        print("   pip install python-socketio[client] requests")
        sys.exit(1)

    main()
