# crimescene 디렉터리

CASE-001 Python 패키지의 모듈별 책임.

## 파일 구성

| 파일 | 역할 |
|---|---|
| [`__init__.py`](./__init__.py) | Python 패키지 초기화 파일 |
| [`settings.py`](./settings.py) | settings 관련 구현 또는 설정 |

## 하위 폴더

| 폴더 | 설명 |
|---|---|
| [`advisor/`](./advisor/) | advisor 관련 파일 |
| [`api/`](./api/) | FastAPI 엔드포인트와 RAG 런타임 초기화 |
| [`chat/`](./chat/) | LLM 호출, NPC 대화, 페르소나 및 대화 기록 |
| [`db/`](./db/) | Qdrant·Neo4j 연결, 적재, 동기화 및 무결성 검사 |
| [`engine/`](./engine/) | engine 관련 파일 |
| [`ingest/`](./ingest/) | 시나리오 문서 로딩, 청킹 및 임베딩 |
| [`retriever/`](./retriever/) | Hybrid RAG 검색, 접근 제어 및 검색 평가 |
| [`scenario/`](./scenario/) | 게임 상태, 증거, 접근 정책 및 판정 규칙 |
| [`trigger/`](./trigger/) | NPC 대화 트리거, 증거 제시 및 원자적 저장 |

## 관련 문서

- [프로젝트 전체 README](../../../README.md)
