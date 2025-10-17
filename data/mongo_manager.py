"""
MongoDB 기반 TRPG 데이터 관리 시스템
게임 데이터, 템플릿, 대화 히스토리를 NoSQL로 관리
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, OperationFailure
from bson import ObjectId

from config.settings import get_config

class MongoManager:
    """MongoDB 연결 및 기본 관리"""

    def __init__(self):
        self.config = get_config("mongodb")
        self.logger = logging.getLogger(__name__)
        self.client = None
        self.db = None
        self._connect()
        self._create_indexes()

    def _connect(self):
        """MongoDB 연결"""
        try:
            connection_string = f"mongodb://{self.config['host']}:{self.config['port']}/"
            self.client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)

            # 연결 테스트
            self.client.admin.command('ping')
            self.db = self.client[self.config['database']]
            self.logger.info("MongoDB connected successfully")
        except ConnectionFailure as e:
            self.logger.error(f"MongoDB connection failed: {e}")
            raise

    def _create_indexes(self):
        """필요한 인덱스 생성"""
        try:
            # 게임 세션 인덱스
            self.db.game_sessions.create_index("game_id", unique=True)
            self.db.game_sessions.create_index("created_at")

            # 대화 히스토리 인덱스
            self.db.chat_history.create_index([("game_id", ASCENDING), ("sequence_number", ASCENDING)], unique=True)
            self.db.chat_history.create_index([("game_id", ASCENDING), ("timestamp", DESCENDING)])
            self.db.chat_history.create_index("game_id")

            # 스토리 이벤트 인덱스
            self.db.story_events.create_index([("game_id", ASCENDING), ("timestamp", DESCENDING)])
            self.db.story_events.create_index([("game_id", ASCENDING), ("importance", ASCENDING)])

            # 템플릿 인덱스
            self.db.scenarios.create_index("scenario_type", unique=True)
            self.db.character_templates.create_index("character_type", unique=True)
            self.db.locations.create_index("location_key", unique=True)
            self.db.event_templates.create_index("event_type", unique=True)

            self.logger.info("MongoDB indexes created successfully")
        except OperationFailure as e:
            self.logger.error(f"Error creating indexes: {e}")

    def get_collection(self, collection_name: str):
        """컬렉션 반환"""
        return self.db[collection_name]

    def close(self):
        """연결 종료"""
        if self.client:
            self.client.close()
            self.logger.info("MongoDB connection closed")

class ScenarioDataManager:
    """MongoDB 기반 시나리오 및 게임 데이터 관리"""

    def __init__(self):
        self.mongo = MongoManager()
        self.logger = logging.getLogger(__name__)
        self._initialize_default_data()

    def get_scenario_by_type(self, scenario_type: str) -> Dict[str, Any]:
        """시나리오 타입별 데이터 반환"""
        collection = self.mongo.get_collection("scenarios")
        scenario = collection.find_one({"scenario_type": scenario_type})

        if scenario:
            scenario["_id"] = str(scenario["_id"])  # ObjectId를 문자열로 변환
            return scenario

        # 기본 시나리오 반환
        return self.get_scenario_by_type("medieval_fantasy")

    def get_character_template(self, character_type: str) -> Dict[str, Any]:
        """캐릭터 템플릿 반환"""
        collection = self.mongo.get_collection("character_templates")
        template = collection.find_one({"character_type": character_type})

        if template:
            template["_id"] = str(template["_id"])
            return template

        # 기본 템플릿 반환
        return self.get_character_template("adventurer")

    def get_location_info(self, location_key: str) -> Optional[Dict[str, Any]]:
        """위치 정보 반환"""
        collection = self.mongo.get_collection("locations")
        location = collection.find_one({"location_key": location_key.lower()})

        if location:
            location["_id"] = str(location["_id"])
            return location

        return None

    def get_event_template(self, event_type: str) -> Dict[str, Any]:
        """이벤트 템플릿 반환"""
        collection = self.mongo.get_collection("event_templates")
        template = collection.find_one({"event_type": event_type})

        if template:
            template["_id"] = str(template["_id"])
            return template

        # 기본 템플릿 반환
        return self.get_event_template("random_encounter")

    def get_all_data_for_vectorization(self) -> List[Dict[str, Any]]:
        """벡터화를 위한 모든 데이터 반환"""
        data_list = []

        # 시나리오 데이터
        scenarios = self.mongo.get_collection("scenarios").find()
        for scenario in scenarios:
            key_elements = ", ".join(scenario.get("key_elements", []))
            data_list.append({
                "content": f"시나리오: {scenario['title']}\n설명: {scenario['description']}\n배경: {scenario['background']}\n핵심 요소: {key_elements}",
                "metadata": {
                    "type": "scenario",
                    "scenario_type": scenario["scenario_type"],
                    "title": scenario["title"],
                    "id": str(scenario["_id"])
                }
            })

        # 캐릭터 템플릿
        templates = self.mongo.get_collection("character_templates").find()
        for template in templates:
            traits = ", ".join(template.get("traits", []))
            data_list.append({
                "content": f"캐릭터 유형: {template['name']}\n설명: {template['description']}\n특성: {traits}\n성격: {template.get('personality', '')}",
                "metadata": {
                    "type": "character_template",
                    "character_type": template["character_type"],
                    "name": template["name"],
                    "id": str(template["_id"])
                }
            })

        # 위치 정보
        locations = self.mongo.get_collection("locations").find()
        for location in locations:
            features = ", ".join(location.get("features", []))
            data_list.append({
                "content": f"위치: {location['name']}\n설명: {location['description']}\n분위기: {location.get('atmosphere', '')}\n특징: {features}",
                "metadata": {
                    "type": "location",
                    "location_key": location["location_key"],
                    "name": location["name"],
                    "id": str(location["_id"])
                }
            })

        # 이벤트 템플릿
        events = self.mongo.get_collection("event_templates").find()
        for event in events:
            examples = ", ".join(event.get("examples", []))
            data_list.append({
                "content": f"이벤트: {event['name']}\n설명: {event['description']}\n발생 조건: {event.get('trigger_condition', '')}\n예시: {examples}",
                "metadata": {
                    "type": "event_template",
                    "event_type": event["event_type"],
                    "name": event["name"],
                    "id": str(event["_id"])
                }
            })

        return data_list

    def save_game_session(self, game_id: str, scenario_type: str, current_location: str, game_state: Dict[str, Any]):
        """게임 세션 저장"""
        collection = self.mongo.get_collection("game_sessions")

        session_data = {
            "game_id": game_id,
            "scenario_type": scenario_type,
            "current_location": current_location,
            "game_state": game_state,
            "updated_at": datetime.now(timezone.utc)
        }

        collection.update_one(
            {"game_id": game_id},
            {"$set": session_data, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
            upsert=True
        )

    def get_game_session(self, game_id: str) -> Optional[Dict[str, Any]]:
        """게임 세션 조회"""
        collection = self.mongo.get_collection("game_sessions")
        session = collection.find_one({"game_id": game_id})

        if session:
            session["_id"] = str(session["_id"])

        return session

    def add_chat_message(self, game_id: str, user_input: str, ai_response: str, metadata: Dict[str, Any] = None):
        """채팅 메시지 추가 (시퀀스 넘버 자동 부여)"""
        collection = self.mongo.get_collection("chat_history")

        # 현재 게임의 최대 시퀀스 넘버 조회
        max_seq_doc = collection.find_one(
            {"game_id": game_id},
            sort=[("sequence_number", DESCENDING)]
        )

        next_sequence = (max_seq_doc["sequence_number"] + 1) if max_seq_doc else 1

        message_data = {
            "game_id": game_id,
            "sequence_number": next_sequence,
            "user_input": user_input,
            "ai_response": ai_response,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc)
        }

        try:
            result = collection.insert_one(message_data)
            return str(result.inserted_id)
        except Exception as e:
            # 동시성으로 인한 중복 시퀀스 에러시 재시도
            if "duplicate key" in str(e).lower():
                self.logger.warning(f"Sequence conflict for game {game_id}, retrying...")
                return self.add_chat_message(game_id, user_input, ai_response, metadata)
            raise

    def get_chat_history(self, game_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """채팅 히스토리 조회 (시퀀스 순서로 정렬)"""
        collection = self.mongo.get_collection("chat_history")

        # 시퀀스 넘버 기준으로 최신 N개 조회
        messages = list(collection.find(
            {"game_id": game_id}
        ).sort("sequence_number", DESCENDING).limit(limit))

        # ObjectId를 문자열로 변환하고 시퀀스 순서로 정렬
        for message in messages:
            message["_id"] = str(message["_id"])

        # 시퀀스 순서대로 정렬 (오래된 것부터)
        return sorted(messages, key=lambda x: x["sequence_number"])

    def add_story_event(self, game_id: str, event_type: str, event_description: str,
                       importance: str = "normal", location: str = None, characters_involved: List[str] = None):
        """스토리 이벤트 추가"""
        collection = self.mongo.get_collection("story_events")

        event_data = {
            "game_id": game_id,
            "event_type": event_type,
            "event_description": event_description,
            "importance": importance,
            "location": location,
            "characters_involved": characters_involved or [],
            "timestamp": datetime.now(timezone.utc)
        }

        result = collection.insert_one(event_data)
        return str(result.inserted_id)

    def get_story_events(self, game_id: str, limit: int = 10, importance: str = None) -> List[Dict[str, Any]]:
        """스토리 이벤트 조회"""
        collection = self.mongo.get_collection("story_events")

        query = {"game_id": game_id}
        if importance:
            query["importance"] = importance

        events = list(collection.find(query).sort("timestamp", DESCENDING).limit(limit))

        for event in events:
            event["_id"] = str(event["_id"])

        return events

    def reset_game_data(self, game_id: str):
        """게임 데이터 리셋"""
        collections = ["game_sessions", "chat_history", "story_events"]

        for collection_name in collections:
            collection = self.mongo.get_collection(collection_name)
            result = collection.delete_many({"game_id": game_id})
            self.logger.info(f"Deleted {result.deleted_count} documents from {collection_name} for game {game_id}")

    def get_memory_stats(self, game_id: str) -> Dict[str, Any]:
        """메모리 통계 반환"""
        stats = {
            "game_id": game_id,
            "exists": False,
            "chat_messages": 0,
            "story_events": 0,
            "has_session": False
        }

        # 채팅 메시지 수
        chat_collection = self.mongo.get_collection("chat_history")
        stats["chat_messages"] = chat_collection.count_documents({"game_id": game_id})

        # 스토리 이벤트 수
        events_collection = self.mongo.get_collection("story_events")
        stats["story_events"] = events_collection.count_documents({"game_id": game_id})

        # 세션 존재 여부
        session_collection = self.mongo.get_collection("game_sessions")
        stats["has_session"] = session_collection.count_documents({"game_id": game_id}) > 0

        stats["exists"] = stats["chat_messages"] > 0 or stats["story_events"] > 0 or stats["has_session"]

        return stats

    def _initialize_default_data(self):
        """기본 데이터 초기화"""
        # 시나리오 데이터가 없으면 기본 데이터 삽입
        scenarios_collection = self.mongo.get_collection("scenarios")
        if scenarios_collection.count_documents({}) == 0:
            self._insert_default_scenarios()
            self._insert_default_character_templates()
            self._insert_default_locations()
            self._insert_default_event_templates()

    def _insert_default_scenarios(self):
        """기본 시나리오 삽입"""
        collection = self.mongo.get_collection("scenarios")

        scenarios = [
            {
                "scenario_type": "medieval_fantasy",
                "title": "중세 판타지 모험",
                "description": "마법과 검이 지배하는 중세 판타지 세계에서의 모험",
                "background": "고대 마법이 깃든 대륙에서 영웅들이 악의 세력과 맞서는 이야기",
                "starting_location": "마을 여관",
                "mood": "모험적이고 신비로운",
                "key_elements": ["마법", "검투", "던전 탐험", "몬스터", "보물", "마법사"],
                "created_at": datetime.now(timezone.utc)
            },
            {
                "scenario_type": "cyberpunk",
                "title": "사이버펑크 2080",
                "description": "하이테크와 로우라이프가 공존하는 미래 도시",
                "background": "거대 기업이 지배하는 네온 도시에서 해커와 용병들의 활약",
                "starting_location": "지하 바",
                "mood": "어둡고 긴장감 넘치는",
                "key_elements": ["해킹", "사이버웨어", "기업 음모", "AI", "가상현실", "반란"],
                "created_at": datetime.now(timezone.utc)
            },
            {
                "scenario_type": "space_exploration",
                "title": "은하계 탐험",
                "description": "광활한 우주를 탐험하며 새로운 문명을 발견하는 이야기",
                "background": "인류가 은하계로 진출하며 외계 종족들과 만나는 시대",
                "starting_location": "우주선 다리",
                "mood": "웅장하고 미지의",
                "key_elements": ["우주선", "외계인", "행성 탐험", "우주 전투", "외교", "과학 기술"],
                "created_at": datetime.now(timezone.utc)
            }
        ]

        collection.insert_many(scenarios)
        self.logger.info("Default scenarios inserted")

    def _insert_default_character_templates(self):
        """기본 캐릭터 템플릿 삽입"""
        collection = self.mongo.get_collection("character_templates")

        templates = [
            {
                "character_type": "adventurer",
                "name": "모험가",
                "description": "용감하고 호기심 많은 일반적인 모험가",
                "traits": ["용감함", "호기심", "팀워크", "생존 본능"],
                "typical_actions": ["탐험", "전투", "문제 해결", "동료와 협력"],
                "personality": "낙관적이고 행동력이 뛰어남",
                "created_at": datetime.now(timezone.utc)
            },
            {
                "character_type": "wizard",
                "name": "마법사",
                "description": "고대의 지식과 마법의 힘을 다루는 현자",
                "traits": ["지혜", "신중함", "마법 지식", "연구욕"],
                "typical_actions": ["마법 시전", "고대 문헌 연구", "조언 제공", "수수께끼 해결"],
                "personality": "신중하고 학구적이며 때로는 신비로움",
                "created_at": datetime.now(timezone.utc)
            },
            {
                "character_type": "warrior",
                "name": "전사",
                "description": "강한 의지와 무력을 가진 전투의 전문가",
                "traits": ["용맹", "명예", "충성", "전투 기술"],
                "typical_actions": ["전면 전투", "동료 보호", "전략 수립", "리더십 발휘"],
                "personality": "직선적이고 명예를 중시하며 보호본능이 강함",
                "created_at": datetime.now(timezone.utc)
            }
        ]

        collection.insert_many(templates)
        self.logger.info("Default character templates inserted")

    def _insert_default_locations(self):
        """기본 위치 정보 삽입"""
        collection = self.mongo.get_collection("locations")

        locations = [
            {
                "location_key": "마을_여관",
                "name": "마을 여관",
                "description": "여행자들이 모이는 따뜻하고 활기찬 곳",
                "atmosphere": "따뜻하고 친근한",
                "features": ["벽난로", "주점", "숙박시설", "정보 교환의 장"],
                "typical_events": ["정보 수집", "의뢰 접수", "휴식", "새로운 동료 만남"],
                "created_at": datetime.now(timezone.utc)
            },
            {
                "location_key": "어두운_숲",
                "name": "어두운 숲",
                "description": "고목들이 하늘을 가린 신비롭고 위험한 숲",
                "atmosphere": "신비롭고 위험한",
                "features": ["거대한 고목", "안개", "야생동물", "고대 유적"],
                "typical_events": ["몬스터 조우", "길 잃음", "고대 비밀 발견", "자연의 시험"],
                "created_at": datetime.now(timezone.utc)
            },
            {
                "location_key": "고대_던전",
                "name": "고대 던전",
                "description": "잊혀진 문명의 유적으로 보물과 위험이 공존하는 곳",
                "atmosphere": "음산하고 신비로운",
                "features": ["돌 복도", "함정", "보물", "고대 문자"],
                "typical_events": ["함정 발견", "보물 발견", "수수께끼 해결", "가디언과의 전투"],
                "created_at": datetime.now(timezone.utc)
            }
        ]

        collection.insert_many(locations)
        self.logger.info("Default locations inserted")

    def _insert_default_event_templates(self):
        """기본 이벤트 템플릿 삽입"""
        collection = self.mongo.get_collection("event_templates")

        events = [
            {
                "event_type": "random_encounter",
                "name": "무작위 조우",
                "description": "예상치 못한 상황이나 인물과의 만남",
                "trigger_condition": "이동 중이거나 탐험할 때",
                "possible_outcomes": ["전투", "대화", "정보 획득", "새로운 퀘스트"],
                "examples": ["도적단 습격", "상인과의 만남", "부상당한 여행자 발견"],
                "created_at": datetime.now(timezone.utc)
            },
            {
                "event_type": "puzzle_challenge",
                "name": "수수께끼 도전",
                "description": "지혜와 논리로 해결해야 하는 퍼즐이나 수수께끼",
                "trigger_condition": "던전이나 고대 유적 탐험 시",
                "possible_outcomes": ["진행 가능", "보상 획득", "함정 발동", "힌트 발견"],
                "examples": ["고대 문자 해독", "기계 장치 조작", "논리 퍼즐 해결"],
                "created_at": datetime.now(timezone.utc)
            },
            {
                "event_type": "combat_encounter",
                "name": "전투 조우",
                "description": "적대적인 생명체나 세력과의 전투",
                "trigger_condition": "위험한 지역이나 갈등 상황에서",
                "possible_outcomes": ["승리", "패배", "도주", "항복"],
                "examples": ["몬스터와의 전투", "도적과의 싸움", "보스 몬스터 조우"],
                "created_at": datetime.now(timezone.utc)
            }
        ]

        collection.insert_many(events)
        self.logger.info("Default event templates inserted")

# 전역 시나리오 데이터 매니저 인스턴스
scenario_data_manager = ScenarioDataManager()