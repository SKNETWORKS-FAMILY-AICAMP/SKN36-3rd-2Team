# Day 6 - Live Service Integration

> 관련 이슈: #158, #159

## 1. 실제 서비스 구성

| Service | Port | Purpose |
|---|---:|---|
| Qdrant | 6333 | Vector Search |
| Neo4j | 7687 | 기존 그래프 DB |
| Ollama | 11434 | Embedding |
| Django Original | 8002 | 기존 콘텐츠 |
| Django Isolated | 8003 | 승인 테스트 |
| Neo4j Test | 7688 | 그래프 동기화 테스트 |

8001번 포트는 기존 Redis Insight와 충돌하므로 사용하지 않았다.

## 2. Qdrant 및 Ollama

| Item | Value |
|---|---|
| Collection | case001_rag_v1 |
| Points | 116 |
| Indexed vectors | 116 |
| Embedding model | bge-m3 |
| Dimension | 1024 |
| Distance | Cosine |

기존 Qdrant Collection을 재생성하지 않았다.

## 3. Neo4j

| Item | Count |
|---|---:|
| Nodes | 146 |
| Relationships | 166 |
| CASE_RELATION | 37 |
| EVIDENCE_HOLDER | 10 |
| ADMIN_MENTIONS | 119 |

기존 그래프 DB는 읽기 전용으로 조회했다.

## 4. Django 원본 DB

- CASE-001: DRAFT
- ContentRelease: 0
- 런타임 승인 콘텐츠: 0
- E01~E10 증거 승인 API: HTTP 404

원본 DB는 강제로 승인하지 않았다.

## 5. 재현 준비

프로젝트 루트에서:

```powershell
docker ps
ollama list

cd backend

uv sync --locked
uv run python -c "import crimescene"
```

기존 CASE-001 로컬 데이터와 Qdrant 및 Neo4j 적재 상태가
정상적으로 준비되어 있어야 한다.

기존 Django .env 및 서비스 인증 토큰이 필요하다.
실제 토큰을 문서 또는 Git에 기록하지 않는다.

### 기존 Django 서버

별도 터미널:

```powershell
cd backend/django_service
uv sync
uv run python manage.py check
uv run python manage.py runserver 127.0.0.1:8002 --noreload
```

### 격리된 Django 테스트 서버

아래 절차는 원본 DB의 복사본에만 테스트 승인 정보를 구성한다.

1. OS 임시 디렉터리에 SQLite Backup API로 db.sqlite3 복제
2. 임시 settings 모듈의 DATABASES를 복제 DB로 지정
3. 실제 연결 DB 경로와 원본 DB 경로가 다른지 검증
4. 복제 DB의 CASE-001 상태를 PUBLISHED로 설정
5. 복제 DB의 E01 metadata에 다음 Boolean 값 지정

```json
{
  "runtime_enabled": true,
  "canon_approved": true,
  "publication_approved": true
}
```

6. E01의 선행 증거가 없는지 검사
7. 승인된 증거가 E01 하나뿐인지 확인
8. 테스트 settings 모듈을 PYTHONPATH에 추가
9. DJANGO_SETTINGS_MODULE을 테스트 모듈로 지정
10. Django 서버를 8003번 포트에서 실행

원본 DB에서는 위 승인 변경을 실행하지 않는다.
ContentRelease를 생성하는 정식 게시 절차가 아닌
통합 테스트용 Fixture이다.

### 승인 격리 확인

| Evidence | Original | Isolated |
|---|---:|---:|
| E01 | 404 | 200 |
| E02 | 404 | 404 |
| E11 | 404 | 404 |

## 6. Neo4j 동기화 전용 컨테이너

기존 Neo4j와 볼륨을 공유하지 않는다.
아래 명령은 7688번 포트와 테스트 컨테이너 이름이 비어
있는 경우에만 실행한다.

```powershell
$testPassword = [guid]::NewGuid().ToString("N")

docker run -d `
    --name crimescene-day6-neo4j-test `
    --label "crimescene.purpose=day6-integration-test" `
    -p 127.0.0.1:7688:7687 `
    -e "NEO4J_AUTH=neo4j/$testPassword" `
    neo4j:5.26.32

$env:CRIMESCENE_TEST_NEO4J_URI = "bolt://127.0.0.1:7688"
$env:CRIMESCENE_TEST_NEO4J_PASSWORD = $testPassword
```

테스트는 기존 데이터가 없는 전용 DB에서만 실행한다.
테스트 코드에 DETACH DELETE 쿼리가 포함되어 있다.

## 7. 전체 외부 서비스 테스트

backend 디렉터리에서:

```powershell
$env:RUN_DAY6_LIVE_INTEGRATION = "1"
$env:RUN_OLLAMA_INTEGRATION = "1"
$env:DJANGO_CONTENT_BASE_URL = "http://127.0.0.1:8002"

uv run pytest `
    tests/test_day6_live_service_integration.py `
    tests/test_neo4j_sync_integration.py `
    tests/test_ollama_embedder_integration.py `
    -v --tb=short

uv run pytest -q --tb=short
```

최종 외부 서비스 테스트 구성:

- Day 6 Live Integration: 14개
- Neo4j Sync Integration: 6개
- Ollama Integration: 3개

## 8. 테스트 종료

테스트 Neo4j 컨테이너의 이름과 라벨을 확인한 뒤
해당 컨테이너 및 익명 볼륨만 삭제한다.

Django 8003 서버를 종료하고 생성한 임시 DB를 정리한다.

기존 Docker Compose 서비스와 원본 DB는 삭제하지 않는다.

실행 옵션을 제거하면 기본 pytest에서는 외부 테스트가
Skip되도록 유지한다.
