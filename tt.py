from database.db_manager import DatabaseManager
import trpg_config as tc

try:
    db_manager = DatabaseManager(tc.DB_CONFIG)

    # 연결 생성
    connection = db_manager.get_connection()
    if connection:
        # 시나리오 템플릿 조회
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM scenario_templates WHERE is_active = TRUE")
        templates = cursor.fetchall()

        print("저장된 시나리오 템플릿들:")
        for template in templates:
            print(f"- ID: {template['id']}")
            print(f"  이름: {template['name']}")
            print(f"  카테고리: {template['category']}")
            print(f"  난이도: {template['difficulty']}")
            print(f"  설명: {template['description'][:100]}...")
            print("---")

        cursor.close()
        connection.close()
    else:
        print("데이터베이스 연결 실패")

except Exception as e:
    print(f"오류 발생: {e}")
