# retriever 디렉터리

Hybrid RAG 검색, 접근 제어 및 검색 평가.

## 파일 구성

| 파일 | 역할 |
|---|---|
| [`__init__.py`](./__init__.py) | Python 패키지 초기화 파일 |
| [`authorized_hybrid_search.py`](./authorized_hybrid_search.py) | GameState 접근 제어를 적용한 Hybrid RAG 검색. |
| [`authorized_multisource_context.py`](./authorized_multisource_context.py) | CASE-001 3중 Hybrid RAG 최종 접근 제어 및 컨텍스트 생성. |
| [`dense_search.py`](./dense_search.py) | Qdrant Dense Vector 기반 RAG 검색 후보 조회. |
| [`graph_context_builder.py`](./graph_context_builder.py) | CASE-001 권한 검증 기반 Graph RAG 컨텍스트 생성. |
| [`graph_evidence_search.py`](./graph_evidence_search.py) | GameState 기반 Neo4j 증거 보유 관계 검색. |
| [`graph_retriever.py`](./graph_retriever.py) | CASE-001 인물 관계 및 증거 통합 Graph Retriever. |
| [`graph_search.py`](./graph_search.py) | GameState 기반 Neo4j 관계 검색. |
| [`hybrid_search.py`](./hybrid_search.py) | Dense + Sparse + RRF 기반 Hybrid Search. |
| [`korean_bm25.py`](./korean_bm25.py) | Kiwi 기반 한국어 BM25 Sparse Vector Encoder. |
| [`multisource_rrf.py`](./multisource_rrf.py) | Dense + BM25 + Neo4j Graph 기반 3중 RRF 검색 결과 통합. |
| [`multisource_search.py`](./multisource_search.py) | CASE-001 Qdrant + Neo4j 통합 검색 실행기. |
| [`npc_graph_knowledge_guard.py`](./npc_graph_knowledge_guard.py) | CASE-001 NPC별 Graph 지식 범위 검증. |
| [`npc_output_guard.py`](./npc_output_guard.py) | CASE-001 NPC LLM 응답의 출처 및 원문 인용 검증. |
| [`npc_presearch_access.py`](./npc_presearch_access.py) | CASE-001 NPC별 검색 전 Qdrant 접근 권한 필터. |
| [`npc_response_gate.py`](./npc_response_gate.py) | CASE-001 NPC 응답 전 최종 근거 및 접근 권한 검증. |
| [`query_entity_extractor.py`](./query_entity_extractor.py) | CASE-001 자연어 질문의 엔티티 추출. |
| [`query_graph_retriever.py`](./query_graph_retriever.py) | 자연어 질문 기반 CASE-001 Neo4j Graph Retrieval. |
| [`retrieval_benchmark.py`](./retrieval_benchmark.py) | CASE-001 Dense/BM25/Hybrid 검색 성능 벤치마크. |
| [`retrieval_eval_dataset.py`](./retrieval_eval_dataset.py) | CASE-001 검색 품질 평가 데이터셋 로더 및 검증. |
| [`retrieval_metrics.py`](./retrieval_metrics.py) | RAG 검색 결과의 순위 기반 평가 지표. |
| [`rrf_fusion.py`](./rrf_fusion.py) | Dense 및 Sparse 검색 결과를 RRF로 결합한다. |
| [`search_comparison.py`](./search_comparison.py) | Dense / BM25 / Hybrid 검색 결과 비교 및 평가. |
| [`sparse_search.py`](./sparse_search.py) | Qdrant BM25 Sparse Vector 기반 검색 후보 조회. |

## 관련 문서

- [프로젝트 전체 README](../../../../README.md)
