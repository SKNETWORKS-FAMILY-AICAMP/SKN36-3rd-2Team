# 팀원 로컬 실행 가이드

## 1. 사전 준비

Windows PowerShell 기준입니다.

필요한 프로그램:

- Git
- Python 3.13
- uv
- Node.js / npm
- Docker Desktop
- Ollama

## 2. 프로젝트 다운로드

처음 설치하는 경우:

```powershell
git clone https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN36-3rd-2Team.git
cd SKN36-3rd-2Team
git switch dev
```

이미 설치한 경우:

```powershell
git switch dev
git pull origin dev
```

이 문서는 팀원 실행 환경 작업이 `dev`에 병합된 이후를 기준으로 합니다.

## 3. 환경변수 설정

프로젝트 루트에서:

```powershell
if (!(Test-Path .env)) {
    Copy-Item .env.example .env
}

if (!(Test-Path backend/.env)) {
    Copy-Item backend/.env.example backend/.env
}
```

루트 `.env`에는 Docker용 Neo4j 비밀번호를 설정합니다.

```dotenv
NEO4J_PASSWORD=각자_설정한_비밀번호
```

`backend/.env`에는 동일한 Neo4j 비밀번호를 설정하고 다음 항목을 확인합니다.

```dotenv
CRIMESCENE_ENABLE_CHAT=true
CRIMESCENE_COOKIE_SECURE=false
CRIMESCENE_DB_PATH=data/game_state.sqlite3
CRIMESCENE_CASE001_ROOT=.local/case001_v7_1
CRIMESCENE_SESSION_SECRET=충분히_긴_무작위_비밀키
```

비밀키 생성:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

생성한 값을 `CRIMESCENE_SESSION_SECRET`에 설정합니다. 서버 재시작 때마다 새로 생성하지 마세요. 기존 세션 인증이 실패할 수 있습니다.

LLM을 Ollama로 사용하는 경우:

```dotenv
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3:8b
OLLAMA_BASE_URL=http://localhost:11434
```

OpenAI로 사용하는 경우:

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=본인의_API_KEY
```

OpenAI를 사용하더라도 임베딩용 Ollama `bge-m3`는 필요합니다.

**실제 `.env`, API 키 및 비공개 사건 데이터를 GitHub에 올리지 마세요.**

## 4. 비공개 CASE-001 데이터 설치

담당자에게 검증된 CASE-001 v7.1 원본을 별도로 전달받습니다.

프로젝트 루트에 다음 경로로 배치합니다.

```text
.local/
└── case001_v7_1/
    └── 검증된 CASE-001 원본 구조
```

폴더 확인:

```powershell
Test-Path .local/case001_v7_1
```

반환값이 `True`여야 합니다.

압축파일에 추가 상위 폴더가 있거나 필수 원본 파일이 빠져 있으면 적재가 실패합니다. 원본 구조와 무결성은 다음 데이터 적재 단계에서 검증합니다.

범인 지목 및 엔딩까지 테스트하려면 서버 전용 정답 원장도 전달받아야 합니다.

`backend/.env`:

```dotenv
CRIMESCENE_CASE_TRUTH_PATH=정답_원장_파일의_절대경로
```

정답 원장은 프론트엔드에 넣지 않습니다.

## 5. Docker 실행

Docker Desktop 실행 후 프로젝트 루트에서:

```powershell
docker compose up -d
docker compose ps
```

접속 주소:

- Qdrant: http://127.0.0.1:6333
- Neo4j Browser: http://127.0.0.1:7474
- Neo4j Bolt: `bolt://127.0.0.1:7687`

기존 데이터가 있다면 `docker compose down -v`를 사용하지 마세요.

기존 Neo4j 볼륨이 있다면 `.env`의 비밀번호를 바꾸는 것만으로 기존 인증 정보가 바뀌지 않습니다.

## 6. Ollama 모델 준비

```powershell
ollama pull bge-m3
ollama pull qwen3:8b
ollama list
```

Ollama 서비스는 실행 상태여야 합니다.

OpenAI로 답변을 생성한다면 `qwen3:8b`는 필수가 아니지만 `bge-m3`는 필요합니다.

## 7. 백엔드 의존성 설치

```powershell
cd backend
uv sync --locked
```

## 8. Qdrant 컬렉션 초기화

`backend` 폴더에서 실행합니다.

```powershell
uv run python -c "from qdrant_client import QdrantClient; from crimescene.db.qdrant_collection import ensure_qdrant_collection; from crimescene.settings import settings; c=QdrantClient(url=settings.qdrant_url); print('CREATED' if ensure_qdrant_collection(c) else 'EXISTS'); c.close()"
```

기존 컬렉션은 삭제하지 않고 설정을 검증합니다.

## 9. CASE-001 데이터 적재

먼저 Dry Run으로 원본과 DB 상태를 확인합니다.

```powershell
uv run python -m crimescene.db.data_pipeline --root ../.local/case001_v7_1
```

신규 로컬 DB이거나 변경사항 적용이 필요한 경우:

```powershell
uv run python -m crimescene.db.data_pipeline --root ../.local/case001_v7_1 --apply
```

기존 데이터 삭제가 필요하다는 오류가 발생하면 임의로 `--allow-delete`를 추가하지 말고 담당자에게 확인합니다.

적재 후 다시 검사합니다.

```powershell
uv run python -m crimescene.db.data_pipeline --root ../.local/case001_v7_1
```

정상 동기화 상태라면 다음과 같이 출력됩니다.

```text
TOTAL CHANGES: 0
DRY RUN ONLY - NO DATABASE CHANGES
```

## 10. 백엔드 실행

`backend` 폴더에서:

```powershell
uv run uvicorn crimescene.api.main:app --host 127.0.0.1 --port 8000
```

API 문서:

http://127.0.0.1:8000/docs

## 11. 프론트엔드 실행

새 PowerShell 창에서 프로젝트 루트의 `frontend` 폴더로 이동합니다.

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

게임 주소:

http://127.0.0.1:5173/

Mock 모드는 제거됐으며 실제 FastAPI만 호출합니다.

## 12. 플레이 테스트

다음 항목을 순서대로 확인합니다.

- [ ] START로 새 게임 생성
- [ ] C01과 실제 AI 대화
- [ ] 증거