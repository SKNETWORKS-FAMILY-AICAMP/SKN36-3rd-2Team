# db 디렉터리

Qdrant·Neo4j 연결, 적재, 동기화 및 무결성 검사.

## 파일 구성

| 파일 | 역할 |
|---|---|
| [`connections.py`](./connections.py) | Qdrant 서버 연결 상태를 확인합니다. |
| [`data_pipeline.py`](./data_pipeline.py) | CASE-001 Qdrant + Neo4j 통합 데이터 적재 파이프라인. |
| [`ingest_integrity.py`](./ingest_integrity.py) | CASE-001 Qdrant / Neo4j 적재 전 무결성 검증. |
| [`neo4j_event_ingest.py`](./neo4j_event_ingest.py) | CASE-001 관리자 전용 사건 타임라인 그래프 적재. |
| [`neo4j_evidence_ingest.py`](./neo4j_evidence_ingest.py) | CASE-001 증거 노드 Neo4j 적재. |
| [`neo4j_evidence_links.py`](./neo4j_evidence_links.py) | CASE-001 증거 보유자 관계 적재. |
| [`neo4j_ingest.py`](./neo4j_ingest.py) | CASE-001 Neo4j 엔티티 및 관계 적재. |
| [`neo4j_schema.py`](./neo4j_schema.py) | CASE-001 Neo4j 그래프 스키마 관리. |
| [`neo4j_sync.py`](./neo4j_sync.py) | CASE-001 Neo4j 동기화 계획 생성 및 Dry Run. |
| [`neo4j_sync_apply.py`](./neo4j_sync_apply.py) | CASE-001 Neo4j 그래프 변경사항 적용. |
| [`qdrant_collection.py`](./qdrant_collection.py) | CASE-001 Qdrant 컬렉션 생성 및 설정 검증. |
| [`qdrant_ingest.py`](./qdrant_ingest.py) | BGE-M3 임베딩 및 Qdrant 벡터 적재 파이프라인. |
| [`qdrant_points.py`](./qdrant_points.py) | RAG 청크를 Qdrant Point로 변환한다. |
| [`qdrant_sync.py`](./qdrant_sync.py) | CASE-001 Qdrant 데이터 동기화 및 변경사항 검증. |

## 관련 문서

- [프로젝트 전체 README](../../../../README.md)
