# schemas 디렉터리

Pydantic 기반 사건 및 게임 상태 데이터 모델.

## 파일 구성

| 파일 | 역할 |
|---|---|
| [`__init__.py`](./__init__.py) | Python 패키지 초기화 파일 |
| [`access_policy.py`](./access_policy.py) | CASE-001 v7.1 문서 및 NPC 지식 접근 정책. |
| [`character.py`](./character.py) | NPC 지식 카드 공개 후 발생 가능한 게임 상태 효과. |
| [`document.py`](./document.py) | CASE-001 플레이어용 문서 데이터 모델. |
| [`evidence.py`](./evidence.py) | 개별 증거의 수집 및 활용 규칙. |
| [`game_state.py`](./game_state.py) | 증거별 발견 및 해결 진행 상태. |
| [`relationship.py`](./relationship.py) | v7.1 원본 인물·사건 관계 데이터. |

## 관련 문서

- [프로젝트 전체 README](../../../../../README.md)
