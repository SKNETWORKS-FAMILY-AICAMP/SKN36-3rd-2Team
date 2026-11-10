# ingest 디렉터리

시나리오 문서 로딩, 청킹 및 임베딩.

## 파일 구성

| 파일 | 역할 |
|---|---|
| [`__init__.py`](./__init__.py) | Python 패키지 초기화 파일 |
| [`case001_dataset.py`](./case001_dataset.py) | CASE-001 실제 데이터를 RAG 청크로 로딩한다. |
| [`chunk_models.py`](./chunk_models.py) | CASE-001 RAG 검색용 내부 청크 데이터 모델. |
| [`chunking_config.py`](./chunking_config.py) | RAG 문서 청킹 전략. |
| [`fixed_chunker.py`](./fixed_chunker.py) | 문자 수 기준으로 텍스트를 분할한다. |
| [`hybrid_access.py`](./hybrid_access.py) | 검색된 Hybrid 청크 중 접근이 허용된 정보만 반환한다. |
| [`hybrid_chunker.py`](./hybrid_chunker.py) | 원본과 분할 위치를 추적할 수 있는 청크 결과. |
| [`npc_knowledge_chunker.py`](./npc_knowledge_chunker.py) | 청킹에 필요한 CASE-001 v7.1 NPC 데이터 필드. |
| [`ollama_embedder.py`](./ollama_embedder.py) | Ollama 기반 로컬 임베딩 생성 모듈. |
| [`player_document_chunker.py`](./player_document_chunker.py) | 플레이어 문서를 RAG 청크로 변환한다. |
| [`semantic_chunker.py`](./semantic_chunker.py) | 문장 경계에서 텍스트를 분리한다. |
| [`source_chunk_pipeline.py`](./source_chunk_pipeline.py) | 원본 문서 로딩 결과를 Hybrid Chunking에 연결한다. |
| [`source_loader.py`](./source_loader.py) | PDF, Markdown, JSON, JSONL 문서 로딩 모듈. |

## 관련 문서

- [프로젝트 전체 README](../../../../README.md)
