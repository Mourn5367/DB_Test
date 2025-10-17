from database.db_manager import DatabaseManager
import trpg_config as tc

db_manager = DatabaseManager(tc.DB_CONFIG)

# 기본 캐릭터 생성
character_data = {
    'game_id': 'default-game-001',
    'character_name': '아리스',
    'nickname': '초보 모험가',
    'strength': 12,
    'agility': 14,
    'intelligence': 10,
    'luck': 13,
    'hp': 100,
    'max_hp': 100,
    'mp': 50,
    'max_mp': 50,
    'level': 1,
    'experience': 0,
    'gold': 150,
    'status': 'alive',
    'location': '여관 로비'
}

# 캐릭터 생성 (DB에 INSERT)
connection = db_manager.get_connection()
if connection:
    try:
        cursor = connection.cursor()
        query = """
        INSERT INTO characters
        (game_id, character_name, nickname, strength, agility, intelligence, luck,
        hp, max_hp, mp, max_mp, level, experience, gold, status, location)
        VALUES (%(game_id)s, %(character_name)s, %(nickname)s, %(strength)s, %(agility)s,
                %(intelligence)s, %(luck)s, %(hp)s, %(max_hp)s, %(mp)s, %(max_mp)s,
                %(level)s, %(experience)s, %(gold)s, %(status)s, %(location)s)
        """
        cursor.execute(query, character_data)
        connection.commit()

        character_id = cursor.lastrowid
        print(f"캐릭터 생성 완료! ID: {character_id}, 이름:{character_data['character_name']}")

        cursor.close()
        connection.close()

    except Exception as e:
        print(f"캐릭터 생성 실패: {e}")
    else:
        print("데이터베이스 연결 실패")