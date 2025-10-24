"""
LangChain 기반 GameMaster 에이전트
기존 복잡한 메모리 관리를 LangChain으로 단순화
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import requests
import copy

from langchain.chains import LLMChain
from langchain_ollama import OllamaLLM
from langchain.schema import BaseMessage

from config.settings import get_config
from memory.game_memory import memory_manager, context_manager
from memory.vector_memory import vector_memory_manager
from prompts.gamemaster_templates import (
    GAMEMASTER_CHAT_PROMPT,
    IMAGE_GENERATION_TEMPLATE,
    CHARACTER_INTERACTION_TEMPLATE,
    get_prompt_template
)


def _deep_merge(source, destination):
    """재귀적으로 딕셔너리를 병합합니다."""
    for key, value in source.items():
        if isinstance(value, dict):
            # 딕셔너리인 경우 재귀적으로 병합
            node = destination.setdefault(key, {})
            _deep_merge(value, node)
        elif isinstance(value, list):
            # 리스트인 경우 전체 교체 (병합하지 않음)
            destination[key] = value
        else:
            # 기본값은 그냥 덮어쓰기
            destination[key] = value
    return destination

class LangChainGameMaster:
    """LangChain 기반 게임마스터 에이전트"""

    def __init__(self):
        # 설정 로드
        self.ollama_config = get_config("ollama")
        self.memory_config = get_config("memory")
        self.game_config = get_config("game")
        self.api_config = get_config("external_api")

        # LLM 초기화
        self.llm = OllamaLLM(
            base_url=self.ollama_config["base_url"],
            model=self.ollama_config["model"],
            temperature=self.ollama_config["temperature"]
        )

        # 메인 게임마스터 체인
        self.gm_chain = LLMChain(
            llm=self.llm,
            prompt=GAMEMASTER_CHAT_PROMPT,
            verbose=True
        )

        # 이미지 생성 판단 체인
        self.image_chain = LLMChain(
            llm=self.llm,
            prompt=IMAGE_GENERATION_TEMPLATE,
            verbose=False
        )

        # 캐릭터 상호작용 체인
        self.character_chain = LLMChain(
            llm=self.llm,
            prompt=CHARACTER_INTERACTION_TEMPLATE,
            verbose=False
        )

        # 로깅
        self.logger = logging.getLogger(__name__)

    def process_game_request(self, game_id: str, user_input: str) -> Dict[str, Any]:
        """게임 요청 처리 - Vector Memory + LangChain 통합"""
        import time
        start_time = time.time()

        try:
            # 1. 게임 컨텍스트 준비
            step_start = time.time()
            game_context = self._prepare_game_context(game_id)
            self.logger.info(f"[TIMING] 게임 컨텍스트 준비: {time.time() - step_start:.2f}초")

            # 2. 벡터 메모리에서 관련 컨텍스트 검색
            step_start = time.time()
            vector_memory = vector_memory_manager.get_vector_memory(game_id)
            relevant_context = vector_memory_manager.search_relevant_context(
                game_id, user_input, k=10
            )
            self.logger.info(f"[TIMING] 벡터 컨텍스트 검색: {time.time() - step_start:.2f}초")

            # 3. 관련 컨텍스트를 문자열로 변환
            step_start = time.time()
            context_info = "\n".join([doc.page_content for doc in relevant_context]) if relevant_context else ""
            self.logger.info(f"[TIMING] 컨텍스트 변환: {time.time() - step_start:.2f}초")

            # 4. 하이브리드 대화 히스토리 구성 (ChromaDB 원문 + 벡터 검색)
            step_start = time.time()
            chat_summary_parts = []

            # ChromaDB에서 전체 대화 조회
            vector_store = vector_memory_manager.vector_stores.get(game_id)
            all_conversations = []

            if vector_store:
                try:
                    results = vector_store.get(where={"type": "conversation"})
                    if results and 'documents' in results:
                        for doc, metadata in zip(results['documents'], results['metadatas']):
                            all_conversations.append({
                                'content': doc,
                                'timestamp': metadata.get('timestamp', ''),
                                'sequence': metadata.get('sequence_number', 0)
                            })
                        # 시간순 정렬
                        all_conversations.sort(key=lambda x: (x['timestamp'], x['sequence']))
                except Exception as e:
                    self.logger.warning(f"ChromaDB 대화 조회 실패: {e}")

            # 최근 N개는 원문 그대로 사용 (기본값: 10개)
            RECENT_LIMIT = 10
            total_count = len(all_conversations)

            if total_count > RECENT_LIMIT:
                # 오래된 대화는 벡터 검색으로 관련성 높은 것만
                old_conversations = all_conversations[:-RECENT_LIMIT]
                recent_conversations = all_conversations[-RECENT_LIMIT:]

                # 벡터 검색으로 관련 있는 오래된 대화 찾기
                if relevant_context:
                    chat_summary_parts.append(f"[과거 관련 대화 (벡터 검색)]\n{context_info}\n")

                # 최근 대화는 원문 그대로
                if recent_conversations:
                    recent_texts = [conv['content'] for conv in recent_conversations]
                    chat_summary_parts.append(f"[최근 대화 ({len(recent_conversations)}턴)]\n" + "\n".join(recent_texts))

            else:
                # 전체가 RECENT_LIMIT 이하면 모두 원문 사용
                if all_conversations:
                    all_texts = [conv['content'] for conv in all_conversations]
                    chat_summary_parts.append(f"[대화 내역 ({len(all_conversations)}턴)]\n" + "\n".join(all_texts))

            chat_summary = "\n".join(chat_summary_parts) if chat_summary_parts else "새로운 게임 세션입니다."
            self.logger.info(f"[TIMING] 하이브리드 메모리 구성 (전체: {total_count}, 최근: {min(total_count, RECENT_LIMIT)}): {time.time() - step_start:.2f}초")

            # 5. GameMaster 체인 실행 (벡터 컨텍스트 포함) - 여기서 /api/generate 호출
            step_start = time.time()
            self.logger.info("[TIMING] AI 모델 호출 시작 - 여기서 /api/generate 요청 발생")
            gm_response = self.gm_chain.run(
                game_context=game_context,
                chat_summary=chat_summary,
                relevant_context=context_info,
                user_input=user_input
            )
            self.logger.info(f"[TIMING] AI 모델 응답: {time.time() - step_start:.2f}초")

            # JSON 응답 파싱
            try:
                # gm_response가 None이거나 빈 문자열인 경우 처리
                if not gm_response or not gm_response.strip():
                    self.logger.error("LLM 응답이 비어있습니다")
                    response_data = {
                        "message": "죄송합니다. 응답을 생성할 수 없습니다. 다시 시도해주세요.",
                        "options": ["다시 시도", "상황 확인"],
                        "need_image": False
                    }
                else:
                    response_data = json.loads(gm_response)
            except json.JSONDecodeError as e:
                # JSON 파싱 실패 시 기본 응답
                self.logger.error(f"JSON 파싱 실패: {e}, 원본 응답: {gm_response[:200] if gm_response else 'None'}")
                response_data = {
                    "message": gm_response if gm_response else "응답 생성 실패",
                    "options": ["계속 진행", "상황 확인", "다른 행동"],
                    "need_image": False
                }
            except Exception as e:
                self.logger.error(f"응답 처리 중 예외 발생: {e}")
                response_data = {
                    "message": "시스템 오류가 발생했습니다.",
                    "options": ["다시 시도"],
                    "need_image": False
                }

            # 6. 캐릭터 정보 업데이트 처리 (게임 ID로 업데이트)
            if "update_character" in response_data:
                update_info = response_data["update_character"]
                # update_info가 None이 아니고 딕셔너리인지 확인
                if update_info and isinstance(update_info, dict):
                    updated_char = self._update_character_info(game_id, update_info)

                    # 체력이 0 이하인 경우 죽음 처리
                    if updated_char and updated_char.get('health', 1) <= 0:
                        death_response = self._handle_character_death(game_id, updated_char, user_input, response_data["message"])
                        return death_response
                else:
                    self.logger.warning(f"update_character 값이 유효하지 않습니다: {update_info}")

            # 7. 메모리에 대화 저장 (LangChain)
            step_start = time.time()
            metadata = {
                "has_relevant_context": bool(relevant_context),
                "context_sources": [doc.metadata.get("type", "unknown") for doc in relevant_context] if relevant_context else []
            }
            memory_manager.add_message(game_id, user_input, response_data["message"], metadata)
            self.logger.info(f"[TIMING] 메모리 저장: {time.time() - step_start:.2f}초")

            # 8. 사용자 입력을 먼저 벡터 저장소에 저장
            step_start = time.time()
            self._add_user_input_to_vector_storage(game_id, user_input)

            # 9. AI 응답도 벡터 저장소에 저장
            if response_data and "message" in response_data:
                self._add_ai_response_to_vector_storage(game_id, response_data["message"], response_data.get("image_url"))
            else:
                self.logger.warning(f"response_data가 비어있거나 message 키가 없습니다: {response_data}")
            self.logger.info(f"[TIMING] 벡터DB 저장: {time.time() - step_start:.2f}초")

            # 이미지 생성 정보 (첫 번째 응답에서 이미 포함됨)
            image_info = None
            if response_data.get("need_image", False) and response_data.get("image_prompt"):
                image_info = {
                    "should_generate": True,
                    "prompt": response_data["image_prompt"],
                    "reason": "Scene visualization"
                }

            # 결과 반환
            result = {
                "success": True,
                "message": response_data["message"],
                "options": response_data.get("options", []),
                "need_image": response_data.get("need_image", False),
                "image_info": image_info,
                "relevant_context_found": bool(relevant_context),
                "timestamp": datetime.now().isoformat()
            }

            total_time = time.time() - start_time
            self.logger.info(f"[TIMING] 전체 처리 시간: {total_time:.2f}초")
            self.logger.info(f"GameMaster processed request for game {game_id}")
            return result

        except Exception as e:
            import traceback
            self.logger.error(f"Error processing game request: {e}")
            self.logger.error(f"상세 에러:\n{traceback.format_exc()}")
            return self._handle_error(e)

    def _prepare_game_context(self, game_id: str) -> str:
        """API를 통해 게임 및 캐릭터 컨텍스트 준비"""
        base_url = self.api_config["base_url"]
        context_parts = []

        # 게임 정보 가져오기
        try:
            game_api_url = f"{base_url}/api/games/{game_id}/title"
            response = requests.get(game_api_url)
            response.raise_for_status()
            data = response.json()
            
            title = data.get("title", "알 수 없는 제목")
            genre = data.get("genre", "알 수 없는 장르")
            scenario = data.get("scenario", {})
            
            context_parts.extend([
                f"=== 게임 정보 ===",
                f"- 제목: {title}",
                f"- 장르: {genre}",
                f"\n=== 시나리오 ===",
                f"- 도입: {scenario.get('hook', '')}",
                f"- 당신의 역할: {scenario.get('role', '')}",
                f"- 임무: {scenario.get('mission', '')}"
            ])

        except requests.exceptions.RequestException as e:
            self.logger.error(f"게임 정보 API 호출 실패: {e}")
            context_parts.append("게임 정보를 불러오는 데 실패했습니다.")
        except json.JSONDecodeError:
            self.logger.error("게임 정보 API 응답 파싱 실패")
            context_parts.append("게임 정보 형식이 올바르지 않습니다.")

        # 캐릭터 정보 가져오기
        try:
            char_api_url = f"{base_url}/api/games/{game_id}/characters"
            response = requests.get(char_api_url)
            response.raise_for_status()
            characters = response.json()
            
            if characters:
                context_parts.append("\n=== 캐릭터 정보 ===")
                for char in characters:
                    context_parts.append(f"- 이름: {char.get('name', '알 수 없음')} (ID: {char.get('id')})")
                    context_parts.append(f"  - 직업: {char.get('class', '알 수 없음')}, 레벨: {char.get('level', 0)}")
                    context_parts.append(f"  - 체력: {char.get('health', 0)}/{char.get('maxHealth', 0)}")
                    context_parts.append(f"  - 능력치: {json.dumps(char.get('stats', {}), ensure_ascii=False)}")
                    context_parts.append(f"  - 인벤토리: {json.dumps(char.get('inventory', []), ensure_ascii=False)}")
                
                # 나중에 업데이트를 위해 캐릭터 정보 저장
                context_manager.set_context(game_id, "characters", characters)

        except requests.exceptions.RequestException as e:
            self.logger.error(f"캐릭터 정보 API 호출 실패: {e}")
        except json.JSONDecodeError:
            self.logger.error("캐릭터 정보 API 응답 파싱 실패")

        return "\n".join(context_parts)

    def _update_character_info(self, game_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """API를 통해 캐릭터 정보 업데이트 (게임 ID 기반)"""
        base_url = self.api_config["base_url"]
        api_url = f"{base_url}/api/characters/game/{game_id}"

        # 1. 기존 캐릭터 정보 가져오기 (첫 번째 캐릭터 사용)
        all_characters = context_manager.get_context(game_id, "characters")
        if not all_characters or len(all_characters) == 0:
            self.logger.warning(f"캐릭터 정보가 없어 업데이트를 건너뜁니다: game_id={game_id}")
            return None

        # 게임에 첫 번째 캐릭터를 업데이트 대상으로 사용
        original_char_data = all_characters[0]

        # 2. 변경분 병합 (Deep Merge)
        merged_data = copy.deepcopy(original_char_data)
        update_payload = {k: v for k, v in update_data.items()}
        merged_data = _deep_merge(update_payload, merged_data)

        # API 페이로드 생성 (변경된 필드만 포함)
        payload_to_send = {}
        allowed_fields = ["name", "class", "level", "stats", "inventory", "avatar", "health"]

        for field in allowed_fields:
            if field in update_payload:
                payload_to_send[field] = merged_data.get(field)

        if not payload_to_send:
            self.logger.warning(f"업데이트할 필드가 없습니다: {update_data}")
            return None

        try:
            self.logger.info(f"캐릭터 정보 업데이트 요청: game_id={game_id}, payload={payload_to_send}")
            response = requests.patch(api_url, json=payload_to_send)
            response.raise_for_status()
            updated_char = response.json()
            self.logger.info(f"캐릭터 정보 업데이트 성공: {updated_char}")

            # 메모리에 저장된 캐릭터 정보도 업데이트
            all_characters[0] = updated_char
            context_manager.set_context(game_id, "characters", all_characters)

            return updated_char

        except requests.exceptions.RequestException as e:
            self.logger.error(f"캐릭터 정보 업데이트 API 호출 실패: {e}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                self.logger.error(f"응답 내용: {e.response.text}")
            return None

    def _handle_character_death(self, game_id: str, character: Dict[str, Any], final_action: str, death_context: str) -> Dict[str, Any]:
        """캐릭터 죽음 처리 - 죽음 원인과 서사 요약 생성"""
        try:
            # ChromaDB에서 전체 대화 히스토리 가져오기
            vector_store = vector_memory_manager.vector_stores.get(game_id)
            if not vector_store:
                vector_memory_manager._initialize_game_vector_store(game_id)
                vector_store = vector_memory_manager.vector_stores.get(game_id)

            # 전체 대화 내역 조회
            results = vector_store.get(where={"type": "conversation"})

            conversation_history = []
            if results and 'documents' in results:
                for doc, metadata in zip(results['documents'], results['metadatas']):
                    conversation_history.append({
                        'content': doc,
                        'timestamp': metadata.get('timestamp', ''),
                        'role': metadata.get('role', 'unknown')
                    })
                # 시간순 정렬
                conversation_history.sort(key=lambda x: x['timestamp'])

            # 대화 내역을 텍스트로 변환
            history_text = "\n".join([conv['content'] for conv in conversation_history[-20:]])  # 최근 20개

            # LLM에게 죽음 원인 및 서사 요약 요청
            death_prompt = f"""캐릭터가 사망했습니다. 다음 정보를 바탕으로 죽음의 원인과 캐릭터의 여정을 요약해주세요.

=== 캐릭터 정보 ===
이름: {character.get('name', '알 수 없음')}
직업: {character.get('class', '알 수 없음')}
레벨: {character.get('level', 1)}

=== 최근 게임 진행 ===
{history_text}

=== 마지막 행동 ===
{final_action}

=== 죽음의 순간 ===
{death_context}

다음 형식으로 응답해주세요:
1. 죽음의 원인을 2-3문장으로 설명
2. 캐릭터의 여정을 3-4문장으로 요약 (시작부터 끝까지)
3. 감동적이고 극적인 마무리 문장

전체를 하나의 자연스러운 이야기로 작성하세요."""

            death_summary = self.llm.invoke(death_prompt)

            # 죽음 메시지 구성
            final_message = f"""
═══════════════════════════════════════
        {character.get('name', '모험가')}의 마지막
═══════════════════════════════════════

{death_summary}

체력: 0/{character.get('maxHealth', 0)}

게임이 종료되었습니다.
═══════════════════════════════════════
"""

            self.logger.info(f"캐릭터 사망 처리 완료: {character.get('name')} (game_id={game_id})")

            return {
                "success": True,
                "message": final_message,
                "options": [],  # 옵션 없음
                "need_image": False,
                "game_over": True,
                "character_death": True,
                "character_name": character.get('name'),
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            self.logger.error(f"죽음 처리 중 에러: {e}")
            # 에러 발생 시 기본 메시지 반환
            return {
                "success": True,
                "message": f"{character.get('name', '캐릭터')}는 쓰러졌습니다...\n\n게임이 종료되었습니다.",
                "options": [],
                "need_image": False,
                "game_over": True,
                "timestamp": datetime.now().isoformat()
            }

    def _check_image_generation(self, user_input: str, gm_response: str, game_context: str) -> Optional[Dict[str, Any]]:
        """이미지 생성 필요성 확인"""
        try:
            image_decision = self.image_chain.run(
                user_input=user_input,
                gm_response=gm_response,
                current_situation=game_context
            )

            image_data = json.loads(image_decision)

            if image_data.get("need_image", False):
                return {
                    "should_generate": True,
                    "prompt": image_data.get("image_prompt", "fantasy scene"),
                    "reason": image_data.get("reason", "Scene visualization")
                }

        except Exception as e:
            self.logger.error(f"Error in image generation check: {e}")

        return None

    def handle_character_action(self, game_id: str, character_data: Dict, user_action: str) -> Dict[str, Any]:
        """캐릭터 행동 처리"""
        try:
            current_scene = context_manager.get_context(game_id, "current_scene") or "일반적인 상황"

            response = self.character_chain.run(
                character_data=json.dumps(character_data, ensure_ascii=False),
                user_action=user_action,
                current_scene=current_scene
            )

            # 메모리에 저장
            memory_manager.add_message(game_id, f"캐릭터 행동: {user_action}", response)

            return {
                "success": True,
                "response": response,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            self.logger.error(f"Error handling character action: {e}")
            return self._handle_error(e)

    def get_memory_stats(self, game_id: str) -> Dict[str, Any]:
        """메모리 상태 정보 반환 (LangChain + Vector)"""
        # LangChain 메모리 통계
        langchain_stats = memory_manager.get_memory_stats(game_id)

        # 벡터 메모리 통계
        vector_stats = vector_memory_manager.get_memory_stats(game_id)

        return {
            "langchain_memory": langchain_stats,
            "vector_memory": vector_stats,
            "total_exists": any([
                langchain_stats.get("exists", False),
                vector_stats.get("exists", False)
            ])
        }

    def reset_game(self, game_id: str):
        """게임 리셋 (모든 메모리 시스템)"""
        # LangChain 메모리 리셋
        memory_manager.reset_game_memory(game_id)

        # 세션 컨텍스트 리셋
        context_manager.session_contexts.pop(game_id, None)

        # 벡터 메모리 리셋
        vector_memory_manager.reset_vector_memory(game_id)

        self.logger.info(f"Game {game_id} has been completely reset")

    def clear_memory(self, game_id: str):
        """메모리만 클리어 (컨텍스트는 유지)"""
        memory_manager.clear_memory(game_id)
        self.logger.info(f"Memory cleared for game {game_id}")

    def update_game_context(self, game_id: str, context_type: str, data: Dict[str, Any]):
        """게임 컨텍스트 업데이트"""
        context_manager.set_context(game_id, context_type, data)
        self.logger.info(f"Updated {context_type} context for game {game_id}")

    def get_chat_history(self, game_id: str, limit: int = 10) -> List[BaseMessage]:
        """채팅 히스토리 반환"""
        return memory_manager.get_recent_messages(game_id, limit)

    def _add_user_input_to_vector_storage(self, game_id: str, user_input: str):
        """사용자 입력을 벡터 저장소에 추가"""
        try:
            metadata = {
                "type": "conversation",
                "source": "user_input",
                "game_id": game_id,
                "role": "user"
            }
            vector_memory_manager.add_scenario_data(game_id, f"사용자: {user_input}", metadata)
            self.logger.info(f"사용자 입력 저장 완료: {user_input[:50]}...")
        except Exception as e:
            self.logger.warning(f"Failed to add user input to vector storage: {e}")

    def _add_ai_response_to_vector_storage(self, game_id: str, ai_response: str, image_url: Optional[str] = None):
        """AI 응답을 벡터 저장소에 추가 (이미지 URL 포함)"""
        try:
            content = f"GM: {ai_response}"
            if image_url:
                content += f"\n[이미지: {image_url}]"

            metadata = {
                "type": "conversation",
                "source": "ai_response",
                "game_id": game_id,
                "role": "assistant"
            }

            if image_url:
                metadata["image_url"] = image_url

            vector_memory_manager.add_scenario_data(game_id, content, metadata)
            self.logger.info(f"AI 응답 저장 완료 (이미지 URL: {image_url})")
        except Exception as e:
            self.logger.warning(f"Failed to add AI response to vector storage: {e}")

    def _handle_error(self, error: Exception) -> Dict[str, Any]:
        """에러 처리"""
        error_responses = [
            "죄송합니다. 잠시 문제가 발생했습니다. 다시 시도해 주세요.",
            "게임 진행 중 오류가 발생했습니다. 다른 행동을 시도해보세요.",
            "시스템에 일시적인 문제가 있습니다. 곧 다시 정상화될 예정입니다."
        ]

        import random
        return {
            "success": False,
            "message": random.choice(error_responses),
            "options": ["다시 시도", "상태 확인", "도움말"],
            "error": str(error),
            "timestamp": datetime.now().isoformat()
        }

# 전역 GameMaster 인스턴스
gamemaster = LangChainGameMaster()