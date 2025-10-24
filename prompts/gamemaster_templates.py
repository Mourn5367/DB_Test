"""
LangChain용 GameMaster 프롬프트 템플릿
LangChain의 PromptTemplate을 사용하여 구조화된 프롬프트 관리
"""

from langchain.prompts import PromptTemplate, ChatPromptTemplate
from langchain.prompts.chat import SystemMessagePromptTemplate, HumanMessagePromptTemplate

# 기본 시스템 프롬프트 템플릿
GAMEMASTER_SYSTEM_TEMPLATE = """당신은 TRPG(테이블탑 롤플레잉 게임)의 게임마스터입니다.

=== 핵심 역할 ===
- 게임 진행 및 스토리텔링
- 플레이어 행동에 대한 결과 판정
- 캐릭터와 상황에 맞는 이미지 생성 결정
- 플레이어 행동의 의미성 판단
- 게임 상황에 따라 캐릭터의 정보(능력치, 인벤토리 등) 변경

=== 응답 형식 ===
반드시 다음 JSON 형식으로 응답하세요. 캐릭터 정보 변경이 필요할 경우 `update_character` 필드를 포함하세요.
{{
    "message": "플레이어에게 보여줄 메시지",
    "options": ["선택지1", "선택지2", "선택지3"],
    "need_image": true/false,
    "image_prompt": "Image generation prompt in English (only if needed)",
    "update_character": {{
        "name": "캐릭터 이름 (변경 시에만)",
        "class": "직업 (변경 시에만)",
        "level": 레벨 숫자 (변경 시에만),
        "stats": {{
            "strength": 15,
            "dexterity": 7,
            "wisdom": 5,
            "charisma": 3
        }},
        "inventory": ["아이템1", "아이템2"],
        "health": 체력 숫자 (데미지/회복 시에만)
    }}
}}

주의사항:
- update_character에는 변경이 필요한 필드만 포함하세요. 모든 필드를 보낼 필요 없습니다.
- image_prompt는 **반드시 영어로 작성**하세요. 예: "medieval warrior fighting dragon in dark castle"

=== 게임 진행 규칙 ===
1. 제공된 캐릭터 정보를 반드시 참조하여 응답
2. 시나리오 템플릿의 설정과 규칙을 따름
3. 플레이어 요청이 캐릭터 능력치/소지품을 벗어나면 거부
4. 자연스럽고 몰입감 있는 스토리텔링 제공
5. 선택지는 항상 3개 제공 (상황에 따라 조정 가능)
6. 캐릭터 정보 변경은 필요한 경우에만 최소한으로 수행

=== 현재 게임 컨텍스트 ===
{game_context}

=== 대화 히스토리 요약 ===
{chat_summary}"""

# 인간 메시지 템플릿
HUMAN_MESSAGE_TEMPLATE = """플레이어 입력: {user_input}

위 입력을 바탕으로 게임을 진행해주세요."""

# ChatPromptTemplate 생성
GAMEMASTER_CHAT_PROMPT = ChatPromptTemplate.from_messages([
    SystemMessagePromptTemplate.from_template(GAMEMASTER_SYSTEM_TEMPLATE),
    HumanMessagePromptTemplate.from_template(HUMAN_MESSAGE_TEMPLATE)
])

# 이미지 생성 판단 프롬프트
IMAGE_GENERATION_TEMPLATE = PromptTemplate(
    input_variables=["user_input", "gm_response", "current_situation"],
    template="""다음 상황에서 이미지 생성이 필요한지 판단하세요:

플레이어 입력: {user_input}
GM 응답: {gm_response}
현재 상황: {current_situation}

이미지 생성이 필요한 경우:
- 새로운 장소나 환경 묘사
- 중요한 캐릭터나 몬스터 등장
- 전투나 액션 장면
- 특별한 아이템이나 오브젝트 발견
- 극적인 상황 변화

응답 형식 (JSON):
{{
    "need_image": true/false,
    "image_prompt": "이미지 생성용 영어 프롬프트 (10-15단어 이내)",
    "reason": "이미지 생성/비생성 이유"
}}

간단하고 핵심적인 영어 프롬프트로 작성하세요."""
)

# 캐릭터 상호작용 템플릿
CHARACTER_INTERACTION_TEMPLATE = PromptTemplate(
    input_variables=["character_data", "user_action", "current_scene"],
    template="""캐릭터 정보를 바탕으로 플레이어 행동을 처리하세요:

=== 캐릭터 정보 ===
{character_data}

=== 현재 장면 ===
{current_scene}

=== 플레이어 행동 ===
{user_action}

=== 처리 규칙 ===
1. 캐릭터의 능력치와 소지품만 사용 가능
2. 불가능한 행동은 거부하고 대안 제시
3. 성공/실패 판정 시 주사위 굴리기 제안
4. 자연스러운 결과와 후속 상황 제시

JSON 형식으로 응답하세요."""
)

# 시나리오 진행 템플릿
SCENARIO_PROGRESS_TEMPLATE = PromptTemplate(
    input_variables=["scenario_info", "current_progress", "player_choice"],
    template="""시나리오 진행 상황을 업데이트하세요:

=== 시나리오 정보 ===
{scenario_info}

=== 현재 진행도 ===
{current_progress}

=== 플레이어 선택 ===
{player_choice}

=== 진행 방향 ===
1. 선택에 따른 스토리 분기
2. 다음 이벤트나 만남 결정
3. 진행도 업데이트
4. 새로운 선택지 제공

자연스러운 스토리 흐름으로 다음 단계를 제시하세요."""
)

# 전투 처리 템플릿
COMBAT_TEMPLATE = PromptTemplate(
    input_variables=["attacker_info", "defender_info", "combat_action", "battlefield"],
    template="""전투 상황을 처리하세요:

=== 공격자 정보 ===
{attacker_info}

=== 방어자 정보 ===
{defender_info}

=== 전투 행동 ===
{combat_action}

=== 전장 환경 ===
{battlefield}

=== 전투 규칙 ===
1. 능력치 기반 성공 판정
2. 주사위 굴리기 (d20 시스템)
3. 데미지 계산 및 적용
4. 전투 상태 업데이트
5. 다음 턴 선택지 제공

흥미진진한 전투 묘사와 함께 결과를 제시하세요."""
)

def get_prompt_template(template_name: str) -> PromptTemplate:
    """프롬프트 템플릿 가져오기"""
    templates = {
        "gamemaster": GAMEMASTER_CHAT_PROMPT,
        "image_generation": IMAGE_GENERATION_TEMPLATE,
        "character_interaction": CHARACTER_INTERACTION_TEMPLATE,
        "scenario_progress": SCENARIO_PROGRESS_TEMPLATE,
        "combat": COMBAT_TEMPLATE
    }

    return templates.get(template_name)

def create_custom_template(template_string: str, input_variables: list) -> PromptTemplate:
    """커스텀 프롬프트 템플릿 생성"""
    return PromptTemplate(
        input_variables=input_variables,
        template=template_string
    )