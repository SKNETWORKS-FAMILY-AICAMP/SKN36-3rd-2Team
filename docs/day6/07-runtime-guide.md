# Day 6 - Runtime Guide

## 1. Prerequisites

| Service | Local Port |
|---|---:|
| Expanded Django | 18004 |
| Qdrant | 6333 |
| Neo4j Bolt | 7687 |
| Ollama | 11434 |

FastAPI와 Django는 별도 가상환경을 사용한다.

## 2. Runtime Configuration

- Content Version: case001_1120
- Release Version: v0.15.0
- Qdrant: case001_rag_1120_revision2
- Embedding: BGE-M3

필요한 원본 및 릴리스 자료는 프로젝트 로컬 영역에 있다.
서비스 토큰, SQLite DB 및 비공개 자료는 커밋하지 않는다.

## 3. FastAPI Start

콘텐츠 Django 및 검색 서비스 준비 후 backend에서 실행한다.

```powershell
$env:CRIMESCENE_EXPANDED_RELEASE_VERSION = "v0.15.0"

& .\.venv\Scripts\python.exe -m uvicorn `
    crimescene.api.expanded_main:app `
    --host 127.0.0.1 `
    --port 8000
```

포트 8000은 로컬 실행 예시이다.
기존 서비스와 충돌하지 않는지 확인해야 한다.

## 4. Startup Validation

- RELEASE RUNTIME READY
- APPROVED CHAPTER RULES
- EXPANDED APPLICATION READY
- RELEASE VERSION: v0.15.0
- RAG COLLECTION: case001_rag_1120_revision2

## 5. Regression Tests

```powershell
python -m pytest tests -q --tb=short -rs
```

## 6. Ollama Integration

```powershell
$env:RUN_OLLAMA_INTEGRATION = "1"
python -m pytest tests/test_ollama_embedder_integration.py -v
Remove-Item Env:RUN_OLLAMA_INTEGRATION
```

## 7. External Integration

- Neo4j Sync: 독립된 빈 7688 서버에서만 실행한다.
- Legacy Live: Django 8002/8003에 별도 복제 DB를 사용한다.
- 확장 Runtime: 기존 18004 서버와 임시 게임 DB를 사용한다.

실제 서비스 테스트는 필요한 환경을 준비한 후 실행한다.
기존 Graph DB에 삭제 테스트를 실행하지 않는다.

## 8. Deployment Readiness

현재 v0.15.0은 로컬 통합 테스트 릴리스이다.

다른 개발 환경이나 운영 서버에서 재현하려면
승인된 콘텐츠, RAG Dataset, Graph Snapshot,
릴리스 Manifest 및 환경 설정을 안전하게 공급해야 한다.

현재 문서만으로 모든 배포 환경이 자동 구축되지는 않는다.
