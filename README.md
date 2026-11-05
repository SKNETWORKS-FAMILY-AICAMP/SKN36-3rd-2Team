# SKN36-3rd-2Team## 🐳 Docker 개발 환경

AI 크라임씬 프로젝트는 Docker Compose를 이용해 Qdrant와 Neo4j 데이터베이스를 실행합니다.

### 1. 개발 환경

| 구성 요소 | 기술 | 포트 | 용도 |
|---|---|---|---|
| LLM | Ollama + Qwen3 8B | 11434 | NPC 대화 생성 |
| Vector DB | Qdrant 1.16.0 | 6333 | 사건 문서 벡터 검색 |
| Graph DB | Neo4j 5.26.32 | 7474, 7687 | 인물·증거 관계 관리 |
| Backend | Python 3.13 + uv | - | 게임 로직 및 AI 연동 |

Ollama는 로컬 환경에서 실행하며, Qdrant와 Neo4j는 Docker 컨테이너로 관리합니다.

### 2. 환경변수 설정

프로젝트 루트에서 다음 명령어를 실행합니다.

```powershell
Copy-Item .env.example .env
Copy-Item backend/.env.example backend/.env
```

생성된 두 `.env` 파일에 동일한 Neo4j 비밀번호를 설정합니다.

기존 Neo4j 데이터 볼륨이 있는 경우 `NEO4J_PASSWORD` 변경만으로 실제 DB 비밀번호가 변경되지는 않습니다.

### 3. Docker 컨테이너 실행

Docker Desktop을 실행한 뒤 프로젝트 루트에서 다음 명령어를 실행합니다.

```powershell
docker compose up -d
```

컨테이너 상태 확인:

```powershell
docker compose ps
```

### 4. 데이터베이스 접속

**Qdrant**

- API: http://localhost:6333
- Dashboard: http://localhost:6333/dashboard

**Neo4j**

- Browser: http://localhost:7474/browser/
- Bolt: `bolt://localhost:7687`
- Username: `neo4j`
- Password: 루트 `.env`에서 설정한 비밀번호

두 데이터베이스는 개발 PC의 localhost에만 포트를 공개합니다.

### 5. Python 의존성 설치

```powershell
cd backend
uv sync
```

### 6. Python DB 연결 테스트

```powershell
uv run python -m crimescene.db.connections
```

정상 실행 시 다음 메시지가 표시됩니다.

```text
✅ Qdrant 연결 성공
✅ Neo4j 연결 성공
```

### 7. 자동 테스트

```powershell
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
```

### 8. Docker 종료 및 재실행

컨테이너 종료:

```powershell
docker compose stop
```

컨테이너 재실행:

```powershell
docker compose start
```

컨테이너 제거:

```powershell
docker compose down
```

Named Volume을 유지하므로 일반적인 컨테이너 종료 및 재생성 후에도 데이터가 보존됩니다.

**주의:** `docker compose down -v`를 실행하면 프로젝트에서 사용하는 Docker Volume이 삭제될 수 있습니다.

### 9. 데이터 저장소

| Volume | 저장 데이터 |
|---|---|
| `qdrant_data` | 벡터 컬렉션 및 검색 데이터 |
| `neo4j_data` | 그래프 노드 및 관계 |
| `neo4j_logs` | Neo4j 로그 |

Docker Compose가 프로젝트 전용 Named Volume을 관리합니다.

### 10. 보안 주의사항

- `.env` 파일은 Git에 커밋하지 않습니다.
- 실제 Neo4j 비밀번호를 README에 작성하지 않습니다.
- Qdrant는 현재 인증이 없는 로컬 개발용 구성입니다.
- 외부 서버 배포 시에는 별도 인증 및 네트워크 보안 설정이 필요합니다.