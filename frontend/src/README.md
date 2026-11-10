# src 디렉터리

React 애플리케이션 진입점과 주요 기능 모듈.

## 파일 구성

| 파일 | 역할 |
|---|---|
| [`App.tsx`](./App.tsx) | React 최상위 앱 및 화면 구성 |
| [`config.ts`](./config.ts) | 프론트엔드 런타임 설정 |
| [`main.tsx`](./main.tsx) | React 애플리케이션 마운트 진입점 |
| [`vite-env.d.ts`](./vite-env.d.ts) | Vite 환경 타입 선언 |

## 하위 폴더

| 폴더 | 설명 |
|---|---|
| [`api/`](./api/) | FastAPI 통신, 요청·응답 타입 및 Mock API |
| [`components/`](./components/) | 재사용 가능한 UI 컴포넌트 |
| [`data/`](./data/) | 프론트엔드에서 사용하는 공개 정적 데이터 |
| [`mock/`](./mock/) | 백엔드 없이 개발할 때 사용하는 Mock 데이터 |
| [`screens/`](./screens/) | 메인·대화·증거·관계도·지목·엔딩 화면 |
| [`store/`](./store/) | Zustand 기반 클라이언트 상태 관리 |
| [`styles/`](./styles/) | 공통 디자인 토큰, 타이포그래피와 UI 스타일 |

## 관련 문서

- [프로젝트 전체 README](../../README.md)
