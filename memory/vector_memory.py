"""
VectorStore 기반 시나리오 및 컨텍스트 메모리 관리
과거 이벤트, 시나리오, 캐릭터 배경 등을 벡터 검색으로 참조
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from langchain.memory import VectorStoreRetrieverMemory
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

from config.settings import get_config
from data.mongo_manager import scenario_data_manager

class VectorMemoryManager:
    """벡터 스토어 기반 메모리 관리자"""

    def __init__(self):
        self.config = get_config("vector_memory")
        self.chroma_config = get_config("chroma")
        self.logger = logging.getLogger(__name__)

        # 임베딩 모델 초기화
        self.embeddings = HuggingFaceEmbeddings(
            model_name=self.config["embedding_model"],
            model_kwargs={'device': 'cpu'}
        )

        # 텍스트 분할기
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config["chunk_size"],
            chunk_overlap=self.config["chunk_overlap"]
        )

        # 게임별 벡터 스토어 저장소
        self.vector_stores: Dict[str, Chroma] = {}
        self.retrievers: Dict[str, VectorStoreRetrieverMemory] = {}

        # Chroma 지속성 디렉토리
        self.persist_directory = self.chroma_config["persist_directory"]
        os.makedirs(self.persist_directory, exist_ok=True)

        # 기본 시나리오 데이터 준비
        self.base_scenarios = None

    def get_vector_memory(self, game_id: str) -> VectorStoreRetrieverMemory:
        """게임별 VectorStoreRetrieverMemory 반환"""
        if game_id not in self.retrievers:
            self._initialize_game_vector_store(game_id)

        return self.retrievers[game_id]

    def _initialize_game_vector_store(self, game_id: str):
        """게임별 벡터 스토어 초기화"""
        collection_name = f"game_{game_id}"

        try:
            # Chroma 벡터 스토어 생성/로드
            vector_store = Chroma(
                collection_name=collection_name,
                embedding_function=self.embeddings,
                persist_directory=self.persist_directory
            )

            # 기존 데이터 확인
            existing_count = vector_store._collection.count()

            if existing_count > 0:
                self.logger.info(f"Loaded existing vector store for game {game_id} with {existing_count} documents")
            else:
                # 기본 시나리오 데이터 추가
                self._add_base_scenarios_to_store(vector_store, game_id)

                # MongoDB에서 기존 대화 히스토리도 벡터화
                try:
                    chat_history = scenario_data_manager.get_chat_history(game_id, limit=100)
                    if chat_history:
                        self.logger.info(f"Adding {len(chat_history)} existing conversations to vector store for game {game_id}")

                        for chat in chat_history:
                            event_content = f"사용자: {chat['user_input']}\nGM: {chat['ai_response']}"
                            metadata = {
                                "type": "conversation",
                                "source": "restored_dialogue",
                                "game_id": game_id,
                                "sequence_number": chat.get("sequence_number", 0)
                            }

                            doc = Document(page_content=event_content, metadata=metadata)
                            vector_store.add_documents([doc])

                        self.logger.info(f"Successfully added existing conversations to vector store")

                except Exception as e:
                    self.logger.warning(f"Failed to load existing conversations to vector store: {e}")

                self.logger.info(f"Initialized vector store for game {game_id} with base scenarios and existing conversations")

            self.vector_stores[game_id] = vector_store

            # VectorStoreRetrieverMemory 생성
            retriever = vector_store.as_retriever(
                search_kwargs={"k": self.config["retrieval_k"]}
            )

            self.retrievers[game_id] = VectorStoreRetrieverMemory(
                retriever=retriever,
                memory_key="scenario_context",
                input_key="user_input"
            )

        except Exception as e:
            self.logger.error(f"Failed to initialize vector store for {game_id}: {e}")
            raise

    def _add_base_scenarios_to_store(self, vector_store: Chroma, game_id: str):
        """기본 시나리오 데이터를 벡터 스토어에 추가"""
        try:
            # MongoDB에서 기본 데이터 로드
            if self.base_scenarios is None:
                self.base_scenarios = scenario_data_manager.get_all_data_for_vectorization()

            # 문서 생성
            documents = []
            for data in self.base_scenarios:
                # 게임별 메타데이터 추가
                metadata = data["metadata"].copy()
                metadata.update({
                    "game_id": game_id,
                    "timestamp": datetime.now().isoformat(),
                    "source": "base_scenario"
                })

                doc = Document(
                    page_content=data["content"],
                    metadata=metadata
                )
                documents.append(doc)

            # 벡터 스토어에 추가
            if documents:
                vector_store.add_documents(documents)
                self.logger.info(f"Added {len(documents)} base scenario documents to game {game_id}")

        except Exception as e:
            self.logger.error(f"Failed to add base scenarios to vector store: {e}")

    def add_scenario_data(self, game_id: str, content: str, metadata: Dict[str, Any] = None):
        """시나리오 데이터 추가"""
        if metadata is None:
            metadata = {}

        # type이 이미 설정되어 있으면 유지, 없으면 "scenario"로 설정
        if "type" not in metadata:
            metadata["type"] = "scenario"

        metadata.update({
            "game_id": game_id,
            "timestamp": datetime.now().isoformat()
        })

        # 텍스트 분할
        chunks = self._split_text(content)

        # 문서 생성
        documents = []
        for i, chunk in enumerate(chunks):
            doc_metadata = metadata.copy()
            doc_metadata["chunk_id"] = i
            documents.append(Document(page_content=chunk, metadata=doc_metadata))

        # 벡터 스토어에 추가
        vector_store = self.vector_stores.get(game_id)
        if vector_store is None:
            self._initialize_game_vector_store(game_id)
            vector_store = self.vector_stores[game_id]

        vector_store.add_documents(documents)
        # ChromaDB는 자동으로 지속성을 관리하므로 별도 저장 불필요

        self.logger.info(f"Added {len(documents)} scenario chunks to game {game_id}")

    def add_character_background(self, game_id: str, character_name: str, background: str):
        """캐릭터 배경 추가"""
        metadata = {
            "type": "character_background",
            "character_name": character_name
        }
        self.add_scenario_data(game_id, background, metadata)

    def add_past_event(self, game_id: str, event_description: str, importance: str = "normal"):
        """과거 이벤트 추가"""
        metadata = {
            "type": "past_event",
            "importance": importance
        }
        self.add_scenario_data(game_id, event_description, metadata)

    def add_location_info(self, game_id: str, location_name: str, description: str):
        """위치 정보 추가"""
        metadata = {
            "type": "location",
            "location_name": location_name
        }
        self.add_scenario_data(game_id, description, metadata)

    def search_relevant_context(self, game_id: str, query: str, k: int = None) -> List[Document]:
        """관련 컨텍스트 검색"""
        if game_id not in self.vector_stores:
            self._initialize_game_vector_store(game_id)

        vector_store = self.vector_stores[game_id]
        k = k or self.config["retrieval_k"]

        try:
            results = vector_store.similarity_search(query, k=k)
            self.logger.info(f"Retrieved {len(results)} relevant documents for query: {query[:50]}...")
            return results
        except Exception as e:
            self.logger.error(f"Error searching vector store: {e}")
            return []

    def get_memory_stats(self, game_id: str) -> Dict[str, Any]:
        """벡터 메모리 통계 반환"""
        if game_id not in self.vector_stores:
            return {"exists": False, "total_documents": 0}

        vector_store = self.vector_stores[game_id]

        # Chroma 컬렉션 크기 확인
        try:
            total_docs = vector_store._collection.count()
        except:
            total_docs = 0

        return {
            "exists": True,
            "total_documents": total_docs,
            "collection_name": f"game_{game_id}",
            "persist_directory": self.persist_directory
        }

    def reset_vector_memory(self, game_id: str):
        """벡터 메모리 리셋"""
        try:
            # 메모리에서 제거
            if game_id in self.vector_stores:
                del self.vector_stores[game_id]
            if game_id in self.retrievers:
                del self.retrievers[game_id]

            # ChromaDB 컬렉션 삭제
            collection_name = f"game_{game_id}"
            try:
                import chromadb
                client = chromadb.PersistentClient(path=self.persist_directory)
                client.delete_collection(name=collection_name)
                self.logger.info(f"Deleted Chroma collection for game {game_id}")
            except Exception as e:
                self.logger.warning(f"Failed to delete Chroma collection for {game_id}: {e}")

            self.logger.info(f"Reset vector memory for game {game_id}")

        except Exception as e:
            self.logger.error(f"Error resetting vector memory for {game_id}: {e}")

    def _split_text(self, text: str) -> List[str]:
        """텍스트 분할"""
        return self.text_splitter.split_text(text)

    def bulk_import_scenarios(self, game_id: str, scenarios: List[Dict[str, Any]]):
        """시나리오 일괄 임포트"""
        for scenario in scenarios:
            content = scenario.get("content", "")
            metadata = scenario.get("metadata", {})

            if content:
                self.add_scenario_data(game_id, content, metadata)

        self.logger.info(f"Bulk imported {len(scenarios)} scenarios for game {game_id}")

# 전역 벡터 메모리 매니저 인스턴스
vector_memory_manager = VectorMemoryManager()