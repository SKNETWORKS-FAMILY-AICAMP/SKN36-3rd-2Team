# validators 디렉터리

인물·문서·관계·타임라인 유효성 검사.

## 파일 구성

| 파일 | 역할 |
|---|---|
| [`__init__.py`](./__init__.py) | Python 패키지 초기화 파일 |
| [`character_knowledge_validator.py`](./character_knowledge_validator.py) | 지식 카드 간 순환 참조를 탐지한다. |
| [`document_validator.py`](./document_validator.py) | 문서·증거·NPC·출처·플래그 참조 무결성을 검증한다. |
| [`relationship_validator.py`](./relationship_validator.py) | NPC 및 관계 데이터의 엔티티 참조 무결성을 검증한다. |
| [`timeline_document_validator.py`](./timeline_document_validator.py) | v7.1 타임라인과 플레이어 문서의 메타데이터를 검증한다. |

## 관련 문서

- [프로젝트 전체 README](../../../../../README.md)
