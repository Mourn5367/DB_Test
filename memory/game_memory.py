"""
TRPG 게임별 메모리 관리 시스템
LangChain의 메모리 시스템을 게임 세션별로 관리
"""

from typing import Dict, List, Any, Optional
from langchain.memory import ConversationSummaryBufferMemory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_ollama import OllamaLLM

from config.settings import get_config

class TRPGMemoryManager:
    """TRPG 게임별 메모리 관리자"""

    def __init__(self):
        self.game_memories: Dict[str, ConversationSummaryBufferMemory] = {}
        self.ollama_config = get_config("ollama")
        self.memory_config = get_config("memory")

        # 로거 초기화
        import logging
        self.logger = logging.getLogger(__name__)

        # Ollama LLM 초기화 (요약용)
        self.llm = OllamaLLM(
            base_url=self.ollama_config["base_url"],
            model=self.ollama_config["model"],
            temperature=0.3  # 요약은 더 일관되게
        )

    def get_memory(self, game_id: str) -> ConversationSummaryBufferMemory:
        """게임별 메모리 가져오기"""
        if game_id not in self.game_memories:
            # 새 메모리 생성
            memory = ConversationSummaryBufferMemory(
                llm=self.llm,
                max_token_limit=self.memory_config["max_token_limit"],
                return_messages=True,
                memory_key="chat_history"
            )
            self.game_memories[game_id] = memory

        return self.game_memories[game_id]

    def add_message(self, game_id: str, human_input: str, ai_response: str, metadata: Dict[str, Any] = None):
        """대화 메시지 추가"""
        # LangChain 메모리에 추가
        memory = self.get_memory(game_id)
        memory.chat_memory.add_user_message(human_input)
        memory.chat_memory.add_ai_message(ai_response)

    def get_chat_history(self, game_id: str) -> List[BaseMessage]:
        """채팅 히스토리 반환"""
        memory = self.get_memory(game_id)
        return memory.chat_memory.messages

    def get_summary(self, game_id: str) -> str:
        """현재까지의 대화 요약 반환"""
        memory = self.get_memory(game_id)
        if hasattr(memory, 'moving_summary_buffer') and memory.moving_summary_buffer:
            return memory.moving_summary_buffer
        return "아직 요약할 만한 대화가 없습니다."

    def clear_memory(self, game_id: str):
        """특정 게임의 메모리 초기화"""
        if game_id in self.game_memories:
            self.game_memories[game_id].clear()

    def reset_game_memory(self, game_id: str):
        """게임 메모리 완전 리셋 (새 게임 시작 시)"""
        if game_id in self.game_memories:
            del self.game_memories[game_id]

    def get_recent_messages(self, game_id: str, n: int = 10) -> List[BaseMessage]:
        """최근 N개 메시지만 반환"""
        messages = self.get_chat_history(game_id)
        return messages[-n:] if len(messages) > n else messages

    def get_memory_stats(self, game_id: str) -> Dict[str, Any]:
        """메모리 상태 정보 반환"""
        if game_id not in self.game_memories:
            return {"exists": False}

        memory = self.game_memories[game_id]
        messages = memory.chat_memory.messages

        return {
            "exists": True,
            "total_messages": len(messages),
            "human_messages": len([m for m in messages if isinstance(m, HumanMessage)]),
            "ai_messages": len([m for m in messages if isinstance(m, AIMessage)]),
            "has_summary": bool(getattr(memory, 'moving_summary_buffer', None)),
            "summary_length": len(getattr(memory, 'moving_summary_buffer', ''))
        }

class SessionContextManager:
    """세션별 컨텍스트 관리 (캐릭터 정보, 게임 상태 등)"""

    def __init__(self):
        self.session_contexts: Dict[str, Dict[str, Any]] = {}

    def set_context(self, game_id: str, key: str, value: Any):
        """컨텍스트 정보 설정"""
        # 메모리에 저장
        if game_id not in self.session_contexts:
            self.session_contexts[game_id] = {}
        self.session_contexts[game_id][key] = value

    def get_context(self, game_id: str, key: str = None) -> Any:
        """컨텍스트 정보 가져오기"""
        if game_id not in self.session_contexts:
            self.session_contexts[game_id] = {}

        if key:
            return self.session_contexts[game_id].get(key)
        return self.session_contexts[game_id]

    def update_character_info(self, game_id: str, character_data: Dict[str, Any]):
        """캐릭터 정보 업데이트"""
        self.set_context(game_id, "characters", character_data)

    def update_scenario_info(self, game_id: str, scenario_data: Dict[str, Any]):
        """시나리오 정보 업데이트"""
        self.set_context(game_id, "scenario", scenario_data)

    def get_full_context(self, game_id: str) -> str:
        """게임의 전체 컨텍스트를 문자열로 반환"""
        context = self.get_context(game_id)
        if not context:
            return "새로운 게임 세션입니다."

        context_parts = []

        # 시나리오 정보
        scenario = context.get("scenario", {})
        if scenario:
            scenario_text = "\n".join([f"  - {k}: {v}" for k, v in scenario.items()])
            context_parts.append(f"=== 시나리오 정보 ===\n{scenario_text}")

        # 게임 상태
        game_state = context.get("game_state", {})
        if game_state:
            state_text = "\n".join([f"  - {k}: {v}" for k, v in game_state.items()])
            context_parts.append(f"=== 게임 상태 ===\n{state_text}")

        # 캐릭터 정보
        characters = context.get("characters", {})
        if characters:
            if isinstance(characters, list):
                char_text = "\n".join([f"  - {c.get('name', '이름없음')}: {c.get('description', '')}" for c in characters])
            elif isinstance(characters, dict):
                char_text = "\n".join([f"  - {k}: {v}" for k, v in characters.items()])
            else:
                char_text = f"  - {characters}"
            context_parts.append(f"=== 캐릭터 정보 ===\n{char_text}")

        return "\n\n".join(context_parts) if context_parts else "컨텍스트 정보가 없습니다."

# 전역 인스턴스
memory_manager = TRPGMemoryManager()
context_manager = SessionContextManager()