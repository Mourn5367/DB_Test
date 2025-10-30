"""
ComfyUI API 매니저

ComfyUI 서버와의 통신을 담당하는 클래스입니다.
"""

import requests
import json
import websocket
import uuid
import threading
import time
import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
import io
import base64
from PIL import Image

class ComfyUIManager:
    """ComfyUI API 연동 매니저"""
    
    def __init__(self, server_url: str = "http://13.209.173.228:8188", timeout: int = 300):
        """
        ComfyUIManager 초기화
        
        Args:
            server_url: ComfyUI 서버 URL
            timeout: 요청 타임아웃 (초)
        """
        self.server_url = server_url.rstrip('/')
        self.timeout = timeout
        self.logger = logging.getLogger("ComfyUIManager")
        
        # WebSocket 연결
        self.ws = None
        self.ws_thread = None
        self.connected = False
        
        # 작업 추적
        self.pending_jobs = {}
        self.completed_jobs = {}
        
        # 콜백 함수들
        self.on_progress = None
        self.on_complete = None
        self.on_error = None
        
        # 기본 워크플로우 로드
        self.default_workflow = self._load_default_workflow()
        
        # 서버 연결 확인
        self._check_server_connection()
    
    def _load_default_workflow(self) -> Dict[str, Any]:
        """lora.json에서 LoRA 워크플로우를 로드합니다."""
        try:
            import os
            # 현재 파일과 같은 디렉토리에서 lora.json 찾기
            current_dir = os.path.dirname(os.path.abspath(__file__))
            lora_json_path = os.path.join(current_dir, "lora.json")

            self.logger.info(f"lora.json 검색 경로: {lora_json_path}")

            if os.path.exists(lora_json_path):
                with open(lora_json_path, 'r', encoding='utf-8') as f:
                    workflow = json.load(f)
                self.logger.info("✅ lora.json에서 LoRA 워크플로우 로드 완료")
                return workflow
            else:
                self.logger.error(f"❌ lora.json 파일을 찾을 수 없습니다: {lora_json_path}")
                raise FileNotFoundError(f"lora.json 파일을 찾을 수 없습니다: {lora_json_path}")

        except Exception as e:
            self.logger.error(f"lora.json 로드 실패: {e}")
            raise e  # lora.json 로드 실패시 예외 발생
    
    def _get_fallback_workflow(self) -> Dict[str, Any]:
        """기본 폴백 워크플로우를 반환합니다."""
        return {
            "3": {
                "inputs": {
                    "seed": 964096532003700,
                    "steps": 20,
                    "cfg": 8,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0]
                },
                "class_type": "KSampler"
            },
            "4": {
                "inputs": {
                    "ckpt_name": "animatBackgroundV1_04.safetensors"
                },
                "class_type": "CheckpointLoaderSimple"
            },
            "5": {
                "inputs": {
                    "width": 1024,
                    "height": 1024,
                    "batch_size": 1
                },
                "class_type": "EmptyLatentImage"
            },
            "6": {
                "inputs": {
                    "text": "beautiful scenery nature glass bottle landscape, purple galaxy bottle, detail, masterpiece,",
                    "clip": ["4", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "7": {
                "inputs": {
                    "text": "text, watermark",
                    "clip": ["4", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "8": {
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                },
                "class_type": "VAEDecode"
            },
            "9": {
                "inputs": {
                    "filename_prefix": "ComfyUI",
                    "images": ["8", 0]
                },
                "class_type": "SaveImage"
            }
        }
    
    def _check_server_connection(self) -> bool:
        """ComfyUI 서버 연결을 확인합니다."""
        try:
            response = requests.get(f"{self.server_url}/system_stats", timeout=5)
            if response.status_code == 200:
                self.logger.info("ComfyUI 서버 연결 성공")
                return True
            else:
                self.logger.warning(f"ComfyUI 서버 응답 오류: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            self.logger.error(f"ComfyUI 서버 연결 실패: {e}")
            return False
    
    def is_available(self) -> bool:
        """ComfyUI 서버 사용 가능 여부 확인"""
        return self._check_server_connection()
    
    def connect_websocket(self):
        """WebSocket 연결을 시작합니다."""
        if self.connected:
            return
        
        try:
            ws_url = self.server_url.replace('http://', 'ws://').replace('https://', 'wss://') + '/ws'
            self.ws = websocket.WebSocketApp(
                ws_url,
                on_open=self._on_ws_open,
                on_message=self._on_ws_message,
                on_error=self._on_ws_error,
                on_close=self._on_ws_close
            )
            
            # 별도 스레드에서 WebSocket 실행
            self.ws_thread = threading.Thread(target=self.ws.run_forever)
            self.ws_thread.daemon = True
            self.ws_thread.start()
            
            # 연결 대기
            for _ in range(10):  # 5초 대기
                if self.connected:
                    break
                time.sleep(0.5)
                
        except Exception as e:
            self.logger.error(f"WebSocket 연결 실패: {e}")
    
    def _on_ws_open(self, ws):
        """WebSocket 연결 시"""
        self.connected = True
        self.logger.info("ComfyUI WebSocket 연결됨")
    
    def _on_ws_message(self, ws, message):
        """WebSocket 메시지 수신"""
        try:
            data = json.loads(message)
            self._handle_ws_message(data)
        except json.JSONDecodeError:
            self.logger.error(f"WebSocket 메시지 파싱 실패: {message}")
    
    def _on_ws_error(self, ws, error):
        """WebSocket 오류"""
        self.logger.error(f"WebSocket 오류: {error}")
    
    def _on_ws_close(self, ws, close_status_code, close_msg):
        """WebSocket 연결 해제"""
        self.connected = False
        self.logger.info("ComfyUI WebSocket 연결 해제")
    
    def _handle_ws_message(self, data: Dict[str, Any]):
        """WebSocket 메시지 처리"""
        msg_type = data.get('type')
        
        if msg_type == 'status':
            # 상태 업데이트
            pass
        elif msg_type == 'progress':
            # 진행률 업데이트
            prompt_id = data.get('data', {}).get('prompt_id')
            if prompt_id and self.on_progress:
                self.on_progress(prompt_id, data.get('data', {}))
        elif msg_type == 'executing':
            # 실행 상태 업데이트
            prompt_id = data.get('data', {}).get('prompt_id')
            if prompt_id in self.pending_jobs:
                node = data.get('data', {}).get('node')
                if node is None:  # 완료됨
                    self._handle_job_completion(prompt_id)
        elif msg_type == 'executed':
            # 노드 실행 완료
            pass
    
    def _handle_job_completion(self, prompt_id: str):
        """작업 완료 처리"""
        if prompt_id not in self.pending_jobs:
            return
        
        try:
            # 결과 이미지 가져오기
            history = self.get_history(prompt_id)
            if history and prompt_id in history:
                outputs = history[prompt_id].get('outputs', {})
                
                # 이미지 다운로드
                images = []
                for node_id, output in outputs.items():
                    if 'images' in output:
                        for img_info in output['images']:
                            img_data = self.get_image(
                                img_info['filename'], 
                                img_info['subfolder'], 
                                img_info['type']
                            )
                            if img_data:
                                images.append({
                                    'filename': img_info['filename'],
                                    'data': img_data
                                })
                
                # 완료 상태로 이동
                job_info = self.pending_jobs.pop(prompt_id)
                job_info['status'] = 'completed'
                job_info['completed_at'] = datetime.now()
                job_info['images'] = images
                self.completed_jobs[prompt_id] = job_info
                
                # 콜백 실행
                if self.on_complete:
                    self.on_complete(prompt_id, job_info)
                    
                self.logger.info(f"작업 완료: {prompt_id}, 이미지 {len(images)}개 생성")
                
        except Exception as e:
            self.logger.error(f"작업 완료 처리 실패 ({prompt_id}): {e}")
            if self.on_error:
                self.on_error(prompt_id, str(e))
    
    def queue_prompt(self, workflow: Dict[str, Any]) -> Optional[str]:
        """워크플로우를 큐에 추가합니다."""
        try:
            prompt_id = str(uuid.uuid4())
            payload = {
                "prompt": workflow,
                "client_id": prompt_id
            }
            
            response = requests.post(
                f"{self.server_url}/prompt",
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                actual_prompt_id = result.get('prompt_id', prompt_id)
                
                # 작업 추적 정보 저장
                self.pending_jobs[actual_prompt_id] = {
                    'prompt_id': actual_prompt_id,
                    'workflow': workflow,
                    'status': 'queued',
                    'created_at': datetime.now(),
                    'images': []
                }
                
                self.logger.info(f"워크플로우 큐에 추가: {actual_prompt_id}")
                return actual_prompt_id
            else:
                self.logger.error(f"워크플로우 큐 추가 실패: {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"워크플로우 큐 추가 요청 실패: {e}")
            return None
    
    def get_history(self, prompt_id: str = None) -> Optional[Dict]:
        """히스토리를 가져옵니다."""
        try:
            url = f"{self.server_url}/history"
            if prompt_id:
                url += f"/{prompt_id}"
            
            response = requests.get(url, timeout=self.timeout)
            if response.status_code == 200:
                return response.json()
            else:
                self.logger.error(f"히스토리 조회 실패: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"히스토리 조회 요청 실패: {e}")
            return None
    
    def get_image(self, filename: str, subfolder: str = "", folder_type: str = "output") -> Optional[bytes]:
        """이미지를 다운로드합니다."""
        try:
            params = {
                "filename": filename,
                "type": folder_type
            }
            if subfolder:
                params["subfolder"] = subfolder
            
            response = requests.get(
                f"{self.server_url}/view",
                params=params,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.content
            else:
                self.logger.error(f"이미지 다운로드 실패: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"이미지 다운로드 요청 실패: {e}")
            return None
    
    def get_job_status(self, prompt_id: str) -> Dict[str, Any]:
        """작업 상태를 조회합니다."""
        if prompt_id in self.completed_jobs:
            return self.completed_jobs[prompt_id]
        elif prompt_id in self.pending_jobs:
            return self.pending_jobs[prompt_id]
        else:
            return {"status": "not_found"}
    
    def wait_for_completion(self, prompt_id: str, timeout: int = None) -> bool:
        """작업 완료까지 대기합니다."""
        if not timeout:
            timeout = self.timeout
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if prompt_id in self.completed_jobs:
                return True
            elif prompt_id not in self.pending_jobs:
                return False  # 작업이 사라짐 (오류)
            
            time.sleep(1)
        
        self.logger.warning(f"작업 대기 시간 초과: {prompt_id}")
        return False
    
    def get_queue_info(self) -> Optional[Dict]:
        """큐 정보를 가져옵니다."""
        try:
            response = requests.get(f"{self.server_url}/queue", timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                return None
        except requests.exceptions.RequestException:
            return None
    
    def clear_queue(self) -> bool:
        """큐를 비웁니다."""
        try:
            response = requests.post(f"{self.server_url}/queue", json={"clear": True}, timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
    
    def interrupt_current(self) -> bool:
        """현재 실행 중인 작업을 중단합니다."""
        try:
            response = requests.post(f"{self.server_url}/interrupt", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
    
    def get_system_stats(self) -> Optional[Dict]:
        """시스템 통계를 가져옵니다."""
        try:
            response = requests.get(f"{self.server_url}/system_stats", timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                return None
        except requests.exceptions.RequestException:
            return None
    
    def set_callbacks(self, on_progress: Callable = None, on_complete: Callable = None, on_error: Callable = None):
        """콜백 함수들을 설정합니다."""
        self.on_progress = on_progress
        self.on_complete = on_complete
        self.on_error = on_error
    
    def disconnect(self):
        """연결을 해제합니다."""
        self.connected = False
        if self.ws:
            self.ws.close()
        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=5)
    
    def __del__(self):
        """소멸자"""
        self.disconnect()