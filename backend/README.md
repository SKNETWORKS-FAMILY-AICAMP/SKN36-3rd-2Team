# backend 디렉터리

FastAPI 백엔드의 실행 환경과 전체 디렉터리 구조.

## 파일 구성

| 파일 | 역할 |
|---|---|
| [`.env.example`](./.env.example) | 필요한 환경변수 설정 예시 |
| [`.python-version`](./.python-version) | 프로젝트 Python 버전 설정 |
| [`pyproject.toml`](./pyproject.toml) | Python 프로젝트 의존성 및 개발 도구 설정 |
| [`uv.lock`](./uv.lock) | Python 의존성 버전 잠금 파일 |

## 하위 폴더

| 폴더 | 설명 |
|---|---|
| [`data/`](./data/) | 시나리오 데이터 디렉터리 구조와 공개 범위 |
| [`scripts/`](./scripts/) | RAG 검색 평가, NPC 검증 및 데이터 점검 스크립트 |
| [`src/`](./src/) | src 관련 파일 |
| [`tests/`](./tests/) | 백엔드 자동화 테스트 및 회귀 검증 |

## 관련 문서

- [프로젝트 전체 README](../README.md)
