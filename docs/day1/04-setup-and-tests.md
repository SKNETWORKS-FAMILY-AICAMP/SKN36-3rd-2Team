# Day 1 — Django + DRF 초기 구축 및 검증

## 1. 작업 정보

- 날짜: 2026-11-20
- GitHub Issue: #97
- 브랜치: feature/97-django-setup
- 목적: 기존 FastAPI와 독립된 Django 서비스 구축

## 2. 설치 환경

| 항목 | 버전 |
|---|---|
| Python | 3.13 |
| Django | 5.2.19 |
| Django REST Framework | 3.16.1 |
| python-dotenv | 1.2.4 |
| 의존성 관리자 | uv |
| 개발 DB | SQLite |

## 3. 디렉터리 구조

```text
backend/
├── src/crimescene/          # 기존 FastAPI
└── django_service/
    ├── manage.py
    ├── pyproject.toml
    ├── uv.lock
    ├── .env.example
    ├── config/
    │   ├── settings.py
    │   ├── urls.py
    │   ├── asgi.py
    │   └── wsgi.py
    └── apps/
        ├── __init__.py
        └── content/
            ├── apps.py
            ├── models.py
            ├── views.py
            ├── admin.py
            └── migrations/
```

로컬의 .venv, .env, db.sqlite3는 Git에서 제외한다.

## 4. 신규 개발 환경 설치

저장소를 받은 후 다음 명령어를 사용한다.

```powershell
cd backend/django_service
uv sync --frozen
Copy-Item .env.example .env
```

.env의 DJANGO_SECRET_KEY는 각 개발자가
안전한 난수로 별도 생성해야 한다.

키 생성 명령:

```powershell
uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

출력된 값을 .env의 DJANGO_SECRET_KEY에 설정한다.
실제 비밀키를 Git 또는 문서에 기록하지 않는다.

## 5. 환경변수

| 변수 | 설명 |
|---|---|
| DJANGO_SECRET_KEY | Django 비밀 서명키 |
| DJANGO_DEBUG | 개발 모드 설정 |
| DJANGO_ALLOWED_HOSTS | 허용 호스트 목록 |

개발 설정:

- DEBUG=true
- ALLOWED_HOSTS=localhost,127.0.0.1

운영 환경에서는 DEBUG=false로 설정한다.
운영용 SECRET_KEY는 개발 키와 분리한다.

## 6. Django 설정

INSTALLED_APPS:

- rest_framework
- apps.content.apps.ContentConfig

DRF 기본 인증:

- SessionAuthentication

DRF 기본 권한:

- IsAuthenticated

일반적인 DRF API는 기본적으로 인증이 필요하다.
공개 API는 향후 별도 권한 정책으로 설정한다.

## 7. 데이터베이스 생성

```powershell
uv run python manage.py migrate --noinput
uv run python manage.py showmigrations
```

확인 결과:

- 기본 마이그레이션 18개 적용
- SQLite 테이블 10개 생성
- content 앱은 아직 사용자 정의 모델 없음

Django 콘텐츠 모델 6종은 후속 이슈에서 구현한다.

## 8. 서버 실행

```powershell
uv run python manage.py check
uv run python manage.py runserver 127.0.0.1:8001
```

접속 주소:

- http://127.0.0.1:8001/
- http://127.0.0.1:8001/admin/

FastAPI는 기존 8000 포트를 사용한다.

## 9. 관리자 계정

로컬 개발용 관리자 생성:

```powershell
uv run python manage.py createsuperuser
```

검증 결과:

- Django Admin 로그인 성공
- Users 메뉴 정상 표시
- Groups 메뉴 정상 표시

관리자 비밀번호와 개발 DB는 Git에 올리지 않는다.

## 10. 실제 검증 결과

| 검증 | 결과 |
|---|---|
| Django import | PASS |
| DRF import | PASS |
| dotenv import | PASS |
| Django system check | PASS |
| Content App 등록 | PASS |
| DRF 인증 설정 | PASS |
| DRF 권한 설정 | PASS |
| SQLite 초기 migration | PASS |
| 8001 서버 실행 | PASS |
| Django Admin 로그인 | PASS |

검증 방식:
- Django 관리 명령 실행
- Python import 및 설정 확인
- 로컬 브라우저 수동 접속 확인

아직 Django 전용 자동화 테스트는 작성하지 않았다.
Health API와 자동화 테스트는 별도 이슈에서 진행한다.

## 11. 후속 작업

- Django Health API 구현 및 테스트
- 콘텐츠 모델 6종 구현
- Django Admin 콘텐츠 관리 기능
- DRF 콘텐츠 조회 API
- FastAPI와 내부 콘텐츠 API 연동
- 배포 환경 보안 검사 및 설정
