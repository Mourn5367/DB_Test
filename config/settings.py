"""
LangChain TRPG 시스템 설정
"""
import os
from typing import Dict, Any

# External API 설정
EXTERNAL_API_CONFIG = {
    "base_url": os.getenv("EXTERNAL_API_URL", "http://192.168.26.165:1024")
}

# Ollama 설정
OLLAMA_CONFIG = {
    "base_url": os.getenv("OLLAMA_URL", "http://ollama.aikopo.net"),
    "model": os.getenv("OLLAMA_MODEL", "gpt-oss:20b"),
    "temperature": 0.7,
    "timeout": 120
}

# MySQL 데이터베이스 설정 (기존 설정과 일치)
DATABASE_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "user"),
    "password": os.getenv("DB_PASSWORD", "1234"),
    "database": os.getenv("DB_NAME", "game"),
    "port": int(os.getenv("DB_PORT", "3306"))
}

# MongoDB 설정
MONGODB_CONFIG = {
    "host": os.getenv("MONGO_HOST", "localhost"),
    "port": int(os.getenv("MONGO_PORT", "27017")),
    "database": os.getenv("MONGO_DB", "trpg_nosql"),
    "username": os.getenv("MONGO_USER", ""),
    "password": os.getenv("MONGO_PASSWORD", "")
}

# ChromaDB 설정
CHROMA_CONFIG = {
    "persist_directory": os.getenv("CHROMA_PATH", "./chroma_db"),
    "collection_name": "trpg_memories"
}

# 메모리 관리 설정
MEMORY_CONFIG = {
    "max_token_limit": 4000,  # 대화 히스토리 최대 토큰
    "summary_threshold": 3000,  # 요약 시작 토큰 수
    "conversation_window": 20,  # 최근 N개 대화 유지
    "auto_summary": True
}

# 게임 설정
GAME_CONFIG = {
    "default_scenario": "medieval_fantasy",
    "max_characters_per_game": 6,
    "auto_save_interval": 300,  # 5분마다 자동 저장
    "session_timeout": 3600  # 1시간 세션 타임아웃
}

# 프롬프트 설정
PROMPT_CONFIG = {
    "system_prompt_max_length": 2000,
    "user_input_max_length": 1000,
    "response_max_length": 2000
}

# 벡터 메모리 설정
VECTOR_MEMORY_CONFIG = {
    "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
    "storage_directory": "./vector_stores",
    "chunk_size": 500,
    "chunk_overlap": 50,
    "retrieval_k": 5  # 검색할 문서 수
}

# 이미지 저장 설정
IMAGE_STORAGE_CONFIG = {
    "storage_directory": os.getenv("IMAGE_STORAGE_PATH", "./static/images"),
    "base_url": os.getenv("IMAGE_BASE_URL", "http://192.168.26.165:5001/images"),
    "max_file_size_mb": 10,
    "allowed_formats": ["png", "jpg", "jpeg", "webp"]
}

def get_config(section: str = None) -> Dict[str, Any]:
    """설정 정보 반환"""
    configs = {
        "external_api": EXTERNAL_API_CONFIG,
        "ollama": OLLAMA_CONFIG,
        "database": DATABASE_CONFIG,
        "mongodb": MONGODB_CONFIG,
        "chroma": CHROMA_CONFIG,
        "memory": MEMORY_CONFIG,
        "game": GAME_CONFIG,
        "prompt": PROMPT_CONFIG,
        "vector_memory": VECTOR_MEMORY_CONFIG,
        "image_storage": IMAGE_STORAGE_CONFIG
    }

    if section:
        return configs.get(section, {})
    return configs