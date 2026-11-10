# loaders 디렉터리

사건 데이터별 로딩 및 구조 검증.

## 파일 구성

| 파일 | 역할 |
|---|---|
| [`__init__.py`](./__init__.py) | Python 패키지 초기화 파일 |
| [`access_policy_loader.py`](./access_policy_loader.py) | JSON 객체의 중복 Key를 탐지한다. |
| [`case_truth_loader.py`](./case_truth_loader.py) | Issue #29 - 비공개 CASE-001 정답 원장 로더. |
| [`character_loader.py`](./character_loader.py) | v7.1 등장인물 프로필을 읽고 검증한다. |
| [`document_loader.py`](./document_loader.py) | JSONL 파일에서 플레이어 문서를 읽고 검증한다. |
| [`evidence_loader.py`](./evidence_loader.py) | JSON 객체에서 중복된 Key를 탐지한다. |
| [`relationship_loader.py`](./relationship_loader.py) | v7.1 일반 관계 데이터를 읽고 검증한다. |
| [`statement_assessment_loader.py`](./statement_assessment_loader.py) | 기본 진술 평가에 관리자 검증 결과를 반영한다. |
| [`unlock_graph_loader.py`](./unlock_graph_loader.py) | Issue #28 - CASE-001 실제 게임 해금 규칙 로더. |

## 관련 문서

- [프로젝트 전체 README](../../../../../README.md)
