# newschops

Docker로 운영하는 한국어 개인 뉴스 리더. FastAPI + PostgreSQL + React/TypeScript. 로그인, RSS 수집, 제목 기반 이슈, 기간별 저장 순위, 관심/저장/숨김, 관리자 수집 상태와 PWA 셸을 제공한다.

**초기 구현이며 전체 명세 완료 버전은 아니다.** 동아일보 공개 지면 목차를 수집한다. 근거 기반 본문 비교, 외부 AI, 고급 이슈 묶기와 일부 관리자 기능은 미구현이다. 미검증 기능을 정상으로 표시하지 않는다. [작업 현황](docs/TASKS.md), [소스 실제 연결](docs/SOURCES.md)을 확인한다.

## 시작

Docker와 Docker Compose를 설치한 환경에서:

```
python3 scripts/generate_env.py
docker compose up -d --build
```

또는 `.env.example`을 `.env`로 복사해 DB_PASSWORD(URL-safe), ADMIN_PASSWORD(14자 이상), SESSION_SECRET(32자 이상)를 채운 뒤 동일 Compose 명령을 실행한다. 기본/빈 비밀번호면 초기화 서비스가 실패한다. `.env` 값에 `$`가 있으면 Compose 보간 방지를 위해 작은따옴표로 감싼다. .env는 Git 제외 및 권한600 유지.

접속: **http://localhost:8080**. 최초 계정은 .env의 ADMIN_USERNAME(기본 admin)과 ADMIN_PASSWORD. 비밀번호는 문서/로그에 출력하지 않는다. 개인 설정에서 변경 가능하며 재로그인이 필요하다. 재시작 시 비밀번호를 덮어쓰지 않는다. DB는 호스트 포트를 공개하지 않는다. 앱 기본 bind127.0.0.1, 외부 접근은 아래 HTTPS 설정을 사용한다.

설치 후 첫 수집을 기다린다. 초기 순위는 worker가 현재 시간 슬롯에 생성한다. 순위는 매시간 갱신되므로 이후 수집 기사는 다음 슬롯부터 반영된다. 분야/매체/관심 탐색은 저장된 전체 기사에서 필터링한다. 샘플 뉴스를 시드하지 않는다.

AI 키가 없어도 실행된다. AI_* 설정은 현재 예약 항목이며 값만 넣어도 AI가 활성화되지는 않는다. 본문 처리 권한/공급자/모델/예산 검증 구현 전 외부 전송은 하지 않는다.

## 검증

```
npm --prefix frontend ci
npm --prefix frontend run build
docker compose config --quiet
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" -v "$PWD:/work" -w /work app python -m pytest -q
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" -v "$PWD:/work" -w /work app python -m scripts.live_smoke
```

live smoke는 별도 외부 연결 시험이고 fixture/단위 테스트와 구분한다. 실제 실행 결과·소스 수·실측은 docs/TASKS.md에 기록한다. 테스트에서 SQLite를 사용하므로 PostgreSQL 잠금/기동/지속성은 Compose 통합 시험으로 별도 확인한다.

[운영 문서](docs/OPERATIONS.md): 기존 HTTPS proxy 또는 Caddy 프로필, 백업/복구, 갱신·롤백·보존 정책. [구조](docs/ARCHITECTURE.md), [순위](docs/RANKING.md), [결정](docs/DECISIONS.md).

새 AI 세션: AGENTS.md → ai유지보수.md → 실제 Git/코드 확인. 작업 후 문서/테스트와 한국어 Git 커밋. 원격 push 없음.

## 실제 검증과 제한

2026-10-25 KST, 활성 10개 소스 모두 worker에서 RSS 파싱·저장 성공. 최초 후보 중 중앙일보·한국일보(404), KBS(빈 응답)는 서울신문·세계일보·SBS로 교체했다. 독립 smoke에서 매일경제·한국경제는 간헐 403이 있었으므로 장기 안정성을 보장하지 않는다. 동아일보 2026-10-24자 공개 지면 목차 66건 확인. 원문 본문·지면 이미지/PDF를 저장하지 않는다.

22개 단위/fixture 테스트, 실제 HTTP 인증/권한/사용자 격리, PostgreSQL worker 중복 잠금, 빈 DB 기동, 백업의 별도 DB 복구, Chromium 360/768/1440px 화면 검증을 통과했다. 실제 Android/iOS 설치와 도메인 HTTPS는 미검증이다.

실측: 기사 593건/이슈 578개에서 현재 순위 재계산 1회 128.73ms, AI 호출 0. 단발 idle 메모리 app 66.49MiB/worker 57.75MiB/DB 70.65MiB. 운영 한계/측정 조건은 TASKS 참조. 전체 시간별 작업의 peak 메모리와 총시간은 별도 측정하지 않았다.

관리자는 사용자 관리 화면에서 계정 생성·비활성화·비밀번호 초기화를 할 수 있다. 수집 상태 화면에서는 수동 수집·중지/재개·잠정 순위 정정 버전을 요청한다. 정정은 worker가 수행하며 기존 snapshot을 보존하고 이유를 남긴다. 이슈 병합/분리는 관리자 API만 제공한다.
