# tests 디렉터리

백엔드 자동화 테스트 및 회귀 검증.

## 파일 구성

| 파일 | 역할 |
|---|---|
| [`test_atomic_dialogue.py`](./test_atomic_dialogue.py) | Issue #24 - GameState와 NPC 대화 기록 단일 트랜잭션 테스트. |
| [`test_authorized_hybrid_search.py`](./test_authorized_hybrid_search.py) | GameState 기반 Hybrid Search 접근 제어 통합 테스트. |
| [`test_authorized_multisource_context.py`](./test_authorized_multisource_context.py) | 3중 Hybrid RAG 최종 접근 제어 테스트. |
| [`test_case001_dialogue.py`](./test_case001_dialogue.py) | Issue #24 - CASE-001 접근 정책과 NPC 대화 연결 테스트. |
| [`test_case_truth.py`](./test_case_truth.py) | 테스트용 사건 진실 데이터를 생성한다. |
| [`test_case_truth_integration.py`](./test_case_truth_integration.py) | case_truth_integration 관련 회귀 테스트 |
| [`test_character_knowledge_validator.py`](./test_character_knowledge_validator.py) | 테스트용 NPC 지식 카드를 생성한다. |
| [`test_character_loader.py`](./test_character_loader.py) | 테스트에 사용할 NPC 데이터. |
| [`test_chunk_models.py`](./test_chunk_models.py) | 테스트용 RAG 청크 데이터 생성. |
| [`test_chunking_config.py`](./test_chunking_config.py) | chunking_config 관련 회귀 테스트 |
| [`test_data_pipeline.py`](./test_data_pipeline.py) | CASE-001 통합 데이터 적재 파이프라인 테스트. |
| [`test_dataset_validator.py`](./test_dataset_validator.py) | 테스트용 JSON 파일 작성. |
| [`test_db_connections.py`](./test_db_connections.py) | db_connections 관련 회귀 테스트 |
| [`test_dense_search.py`](./test_dense_search.py) | Qdrant Dense Vector 검색 단위 테스트. |
| [`test_document_loader.py`](./test_document_loader.py) | 테스트용 플레이어 문서 데이터를 생성한다. |
| [`test_document_validator.py`](./test_document_validator.py) | 테스트용 플레이어 문서를 생성한다. |
| [`test_evidence_loader.py`](./test_evidence_loader.py) | 테스트용 증거 규칙을 생성한다. |
| [`test_evidence_presentation.py`](./test_evidence_presentation.py) | Issue #24 - 증거 제시와 NPC 트리거 통합 테스트. |
| [`test_fixed_chunker.py`](./test_fixed_chunker.py) | fixed_chunker 관련 회귀 테스트 |
| [`test_graph_context_builder.py`](./test_graph_context_builder.py) | Graph RAG 컨텍스트 변환 및 정보 누출 방지 테스트. |
| [`test_graph_evidence_search.py`](./test_graph_evidence_search.py) | Neo4j 증거 관계 검색 테스트. |
| [`test_graph_retriever.py`](./test_graph_retriever.py) | 통합 Graph Retriever 테스트. |
| [`test_graph_search.py`](./test_graph_search.py) | graph_search 관련 회귀 테스트 |
| [`test_hybrid_access.py`](./test_hybrid_access.py) | 테스트용 접근 정책. |
| [`test_hybrid_chunker.py`](./test_hybrid_chunker.py) | 테스트용 원본 RAGChunk 생성. |
| [`test_hybrid_search.py`](./test_hybrid_search.py) | Dense + Sparse + RRF Hybrid Search 단위 테스트. |
| [`test_ingest_integrity.py`](./test_ingest_integrity.py) | CASE-001 데이터 적재 무결성 테스트. |
| [`test_issue25_atomic_social.py`](./test_issue25_atomic_social.py) | Issue #25 - 안전한 일상 응답의 SQLite 원자적 저장 회귀 테스트. |
| [`test_issue27_game_progress.py`](./test_issue27_game_progress.py) | 지목 최소 조건인 증거 5개 및 11점을 충족하는 상태 생성. |
| [`test_issue27_state_repository.py`](./test_issue27_state_repository.py) | issue27_state_repository 관련 회귀 테스트 |
| [`test_issue28_atomic_flags.py`](./test_issue28_atomic_flags.py) | issue28_atomic_flags 관련 회귀 테스트 |
| [`test_issue28_evidence_collection.py`](./test_issue28_evidence_collection.py) | issue28_evidence_collection 관련 회귀 테스트 |
| [`test_issue28_evidence_service.py`](./test_issue28_evidence_service.py) | issue28_evidence_service 관련 회귀 테스트 |
| [`test_issue28_flag_event_integration.py`](./test_issue28_flag_event_integration.py) | issue28_flag_event_integration 관련 회귀 테스트 |
| [`test_issue28_flag_progress.py`](./test_issue28_flag_progress.py) | issue28_flag_progress 관련 회귀 테스트 |
| [`test_issue28_npc_unlock.py`](./test_issue28_npc_unlock.py) | issue28_npc_unlock 관련 회귀 테스트 |
| [`test_issue28_rag_access.py`](./test_issue28_rag_access.py) | Issue #28 - 플래그 지급 전후 RAG 정보 접근 검증. |
| [`test_issue28_real_progression.py`](./test_issue28_real_progression.py) | Issue #28 - 실제 CASE-001 증거 및 NPC 해금 검증. |
| [`test_issue29_accusation.py`](./test_issue29_accusation.py) | Issue #29 - 범인 지목 및 사건 결과 테스트. |
| [`test_issue29_accusation_service.py`](./test_issue29_accusation_service.py) | Issue #29 - 범인 지목 SQLite 통합 테스트. |
| [`test_issue29_real_truth.py`](./test_issue29_real_truth.py) | Issue #29 - 실제 비공개 원장 기반 범인 지목 검증. |
| [`test_issue30_full_game_flow.py`](./test_issue30_full_game_flow.py) | Issue #30 - 게임 시작부터 엔딩까지 API 통합 테스트. |
| [`test_issue32_graph_policy.py`](./test_issue32_graph_policy.py) | Issue #32 - CASE-001 Graph 접근 정책 회귀 테스트. |
| [`test_issue33_npc_scenario.py`](./test_issue33_npc_scenario.py) | Issue #33: CASE-001 게임 진행 규칙 회귀 테스트. |
| [`test_issue60_evidence_relations_api.py`](./test_issue60_evidence_relations_api.py) | Issue #60: collected evidence details must not leak locked relationships. |
| [`test_issue61_accusation_security.py`](./test_issue61_accusation_security.py) | Issue #61: unlocked-only accusation and authoritative ending behavior. |
| [`test_issue62_api_resilience.py`](./test_issue62_api_resilience.py) | Issue #62 - API 재시작, 소유권 및 동시 요청 검증. |
| [`test_issue62_game_api.py`](./test_issue62_game_api.py) | Issue #62 - 게임 시작, 저장, 이어하기 및 NPC 선택 API 테스트. |
| [`test_issue62_multislot_selection.py`](./test_issue62_multislot_selection.py) | Issue #62 - 다중 게임 쿠키와 NPC 선택 원자성 검증. |
| [`test_issue63_chat_api.py`](./test_issue63_chat_api.py) | Issue #63 - NPC 대화 API 검증. |
| [`test_issue63_chat_history_api.py`](./test_issue63_chat_history_api.py) | Issue #63 - NPC 대화 기록 조회 API 테스트. |
| [`test_issue63_evidence_api.py`](./test_issue63_evidence_api.py) | Issue #63: 수집 권한, 해금, 멱등성, SQLite 영구 저장 API 검증. |
| [`test_issue63_evidence_policy_loader.py`](./test_issue63_evidence_policy_loader.py) | Issue #63: 실제 증거 획득 정책 구성의 fail-closed 검증. |
| [`test_issue63_real_acquisition_setup.py`](./test_issue63_real_acquisition_setup.py) | 실제 CASE-001 획득 정책과 위조·선행조건 우회를 검사합니다. |
| [`test_issue63_runtime_binding.py`](./test_issue63_runtime_binding.py) | Issue #63 - API 런타임 DI와 실제 SQLite 커밋 경로 검증. |
| [`test_issue64_accusation_api.py`](./test_issue64_accusation_api.py) | Issue #64 - 범인 지목 FastAPI 통합 테스트. |
| [`test_issue65_dialogue_lock.py`](./test_issue65_dialogue_lock.py) | Issue #65 - 같은 세션 동시 대화 차단 테스트. |
| [`test_issue65_evidence_available_api.py`](./test_issue65_evidence_available_api.py) | Issue #65 - no evidence metadata leaks before the acquisition policy passes. |
| [`test_issue65_evidence_reaction.py`](./test_issue65_evidence_reaction.py) | Regression coverage for collection vs. presentation authorization. |
| [`test_issue65_npc_history_display.py`](./test_issue65_npc_history_display.py) | Issue #65 - 대화 기록의 RAG 내부 메타데이터 비노출 회귀 테스트. |
| [`test_issue65_openai_provider.py`](./test_issue65_openai_provider.py) | API 네트워크 요청 없이 OpenAI 공급자 분기와 JSON 계약을 검증합니다. |
| [`test_json_loader.py`](./test_json_loader.py) | 테스트용 JSON 파일을 생성한다. |
| [`test_korean_bm25.py`](./test_korean_bm25.py) | 한국어 BM25 Sparse Encoder 단위 테스트. |
| [`test_llm_client.py`](./test_llm_client.py) | llm_client 관련 회귀 테스트 |
| [`test_multisource_rrf.py`](./test_multisource_rrf.py) | Dense + BM25 + Graph 3중 RRF 테스트. |
| [`test_multisource_search.py`](./test_multisource_search.py) | CASE-001 Qdrant + Neo4j 통합 검색 테스트. |
| [`test_neo4j_event_ingest.py`](./test_neo4j_event_ingest.py) | neo4j_event_ingest 관련 회귀 테스트 |
| [`test_neo4j_ingest.py`](./test_neo4j_ingest.py) | neo4j_ingest 관련 회귀 테스트 |
| [`test_neo4j_schema.py`](./test_neo4j_schema.py) | neo4j_schema 관련 회귀 테스트 |
| [`test_neo4j_sync.py`](./test_neo4j_sync.py) | Neo4j 동기화 변경사항 탐지 테스트. |
| [`test_neo4j_sync_apply.py`](./test_neo4j_sync_apply.py) | Neo4j 동기화 Apply 기능 테스트. |
| [`test_neo4j_sync_integration.py`](./test_neo4j_sync_integration.py) | 독립 테스트 컨테이너에서 Neo4j 동기화 검증. |
| [`test_npc_access_policy.py`](./test_npc_access_policy.py) | 테스트용 NPC 지식 카드 생성. |
| [`test_npc_behavior.py`](./test_npc_behavior.py) | #22 NPC 행동 규칙: 기존 GameState/정책 검증을 통과한 진술만 사용한다. |
| [`test_npc_chat_runtime.py`](./test_npc_chat_runtime.py) | Issue #23 - NPC RAG, LLM 검증 및 대화 저장 통합 테스트. |
| [`test_npc_graph_knowledge_guard.py`](./test_npc_graph_knowledge_guard.py) | NPC별 Graph 지식 범위 및 정보 유출 차단 테스트. |
| [`test_npc_history_context.py`](./test_npc_history_context.py) | Issue #23 - NPC 대화 기억 및 보안 검증 테스트. |
| [`test_npc_knowledge_chunker.py`](./test_npc_knowledge_chunker.py) | CASE-001 v7.1 형식의 테스트용 NPC 지식 카드. |
| [`test_npc_natural_reply.py`](./test_npc_natural_reply.py) | Issue #25 - 자연스러운 NPC 말풍선 검증. |
| [`test_npc_output_guard.py`](./test_npc_output_guard.py) | NPC LLM 응답의 인용문 검증 및 정보 유출 차단 테스트. |
| [`test_npc_persona.py`](./test_npc_persona.py) | CASE-001 NPC 페르소나의 최소 정보 노출 및 접근 제어 테스트. |
| [`test_npc_persona_case001.py`](./test_npc_persona_case001.py) | Issue #22 - 실제 CASE-001 NPC 페르소나 통합 검증. |
| [`test_npc_presearch_access.py`](./test_npc_presearch_access.py) | NPC별 Qdrant 검색 전 접근 제어 테스트. |
| [`test_npc_rag_service.py`](./test_npc_rag_service.py) | Issue #23 - NPC 세션 및 Hybrid RAG 연결 테스트. |
| [`test_npc_reaction.py`](./test_npc_reaction.py) | Issue #25 - NPC 반응 및 캐릭터 일관성 테스트. |
| [`test_npc_response_gate.py`](./test_npc_response_gate.py) | CASE-001 NPC 근거 기반 응답 게이트 테스트. |
| [`test_npc_session.py`](./test_npc_session.py) | Issue #23 - NPC 대화 세션 관리 테스트. |
| [`test_npc_session_persistence.py`](./test_npc_session_persistence.py) | Issue #23 - NPCSessionStore와 SQLite 영구 저장소 통합 테스트. |
| [`test_npc_session_repository.py`](./test_npc_session_repository.py) | Issue #23 - SQLite NPC 대화 영구 저장소 테스트. |
| [`test_npc_social_dialogue.py`](./test_npc_social_dialogue.py) | Issue #25 - 안전한 NPC 일상 대화 테스트. |
| [`test_npc_statement_progression.py`](./test_npc_statement_progression.py) | npc_statement_progression 관련 회귀 테스트 |
| [`test_npc_trigger.py`](./test_npc_trigger.py) | Issue #24 - NPC 트리거 감지 및 접근 정책 테스트. |
| [`test_ollama_embedder.py`](./test_ollama_embedder.py) | OllamaEmbedder 단위 테스트. |
| [`test_ollama_embedder_integration.py`](./test_ollama_embedder_integration.py) | 실제 Ollama BGE-M3 임베딩 통합 테스트. |
| [`test_player_document_chunker.py`](./test_player_document_chunker.py) | 테스트용 플레이어 문서를 생성한다. |
| [`test_qdrant_collection.py`](./test_qdrant_collection.py) | Qdrant 컬렉션 생성 및 설정 검증 테스트. |
| [`test_qdrant_ingest.py`](./test_qdrant_ingest.py) | BGE-M3 임베딩 및 Qdrant 적재 파이프라인 테스트. |
| [`test_qdrant_point_storage.py`](./test_qdrant_point_storage.py) | Qdrant Point 저장 및 조회 통합 테스트. |
| [`test_qdrant_points.py`](./test_qdrant_points.py) | RAG 청크 → Qdrant Point 변환 단위 테스트. |
| [`test_qdrant_sync.py`](./test_qdrant_sync.py) | Qdrant 데이터 동기화 테스트. |
| [`test_query_entity_extractor.py`](./test_query_entity_extractor.py) | CASE-001 자연어 엔티티 추출 테스트. |
| [`test_query_graph_retriever.py`](./test_query_graph_retriever.py) | 자연어 질문 기반 Graph Retrieval 테스트. |
| [`test_rag_access.py`](./test_rag_access.py) | 로컬 v7.1 원본 데이터를 읽는다. |
| [`test_rag_chunk_integration.py`](./test_rag_chunk_integration.py) | CASE-001 v7.1 원본 데이터 기반 통합 청킹. |
| [`test_relationship_loader.py`](./test_relationship_loader.py) | 테스트용 일반 관계 데이터를 생성한다. |
| [`test_relationship_validator.py`](./test_relationship_validator.py) | 참조 무결성 검사에 필요한 테스트 데이터를 생성한다. |
| [`test_retrieval_benchmark.py`](./test_retrieval_benchmark.py) | CASE-001 검색 벤치마크 검증. |
| [`test_retrieval_eval_dataset.py`](./test_retrieval_eval_dataset.py) | 검색 평가 데이터셋 JSONL 로더 단위 테스트. |
| [`test_retrieval_metrics.py`](./test_retrieval_metrics.py) | 검색 정확도 평가 지표 테스트. |
| [`test_rrf_fusion.py`](./test_rrf_fusion.py) | Dense + Sparse RRF 결합 단위 테스트. |
| [`test_scenario_integrity.py`](./test_scenario_integrity.py) | 테스트용 사건 데이터. |
| [`test_scenario_models.py`](./test_scenario_models.py) | scenario_models 관련 회귀 테스트 |
| [`test_search_comparison.py`](./test_search_comparison.py) | Dense / BM25 / Hybrid 검색 결과 비교 테스트. |
| [`test_semantic_chunker.py`](./test_semantic_chunker.py) | Semantic Chunker 테스트용 설정. |
| [`test_settings.py`](./test_settings.py) | settings 관련 회귀 테스트 |
| [`test_source_chunk_pipeline.py`](./test_source_chunk_pipeline.py) | Source Loader와 Hybrid Chunking 통합 테스트. |
| [`test_source_loader.py`](./test_source_loader.py) | 테스트용 문서 로더 호출. |
| [`test_source_timeline.py`](./test_source_timeline.py) | 테스트용 타임라인 데이터. |
| [`test_sparse_search.py`](./test_sparse_search.py) | Qdrant 한국어 BM25 Sparse 검색 단위 테스트. |
| [`test_statement_assessment.py`](./test_statement_assessment.py) | 테스트용 NPC 진술 평가 데이터를 생성한다. |
| [`test_statement_assessment_loader.py`](./test_statement_assessment_loader.py) | 테스트용 NPC 프로필을 생성한다. |
| [`test_statement_integrity.py`](./test_statement_integrity.py) | 테스트용 사건 및 NPC 진술 데이터. |
| [`test_timeline_adapter.py`](./test_timeline_adapter.py) | 테스트용 v7.1 타임라인 이벤트 생성. |
| [`test_timeline_document_validator.py`](./test_timeline_document_validator.py) | 테스트용 문서와 관리자 타임라인. |

## 관련 문서

- [프로젝트 전체 README](../../README.md)
