# 구현 및 검증 현황

2026-10-25 KST. **전체 명세 완료 버전은 아니다.** 실행 가능한 초기 메타데이터 뉴스 리더를 구현했다.

| 단계 | 실제 상태 | 검증과 남은 범위 |
|---|---|---|
| 1. 구조·Compose·인증 | 기본 게이트 통과 | 빈 named volume 기동, 관리자 로그인, 비로그인401, 일반 사용자403, CSRF, 사용자 격리, 로그아웃 검증 |
| 2. 수집·상태·지면 | 메타데이터 구현·live 확인 | 원래10후보 모두 시도 후3곳 교체. 활성10곳 worker 수집 성공. 독립 smoke는8곳 성공/경제지2곳403. 동아 공개 지면66건 확인. 장기 안정성과 상세 이용 조건 추가 확인 필요 |
| 3. 이슈·순위 | 보수적 초기 규칙 구현 | 정확한 제목+날짜 병합, origin 불명 미가산,7기간 snapshot, 결측 처리, 분야 제한, 관리자 잠정 정정. 정교한 사건/전재/중요 전개/영향 판정은 미구현 |
| 4. 관심·비교·AI | 관심·사용자 상태 구현, AI 미구현 | 관심·제외·선호 매체·저장·읽음·숨김. 허용 본문 미확보로 비교 불가 표시. AI 공급자/검증/예산/캐시는 미구현이며 예약 환경변수·테이블만 존재 |
| 5. 반응형·PWA·운영 | 브라우저·백업 검증 통과 | Chromium360/768/1440, 페이지 오류0, manifest/아이콘, 로그아웃. 실제 Android/iOS 설치 및 도메인 TLS는 미검증 |
| 6. 통합·문서·Git | 검증·문서 작성, 초기 커밋 | main 초기화. 사용자 지정 작성자 pscho / ggbebe7@gmail.com을 저장소 로컬에 설정. 한국어 초기 커밋, 원격 push 없음 |

## 실행한 검증

- `docker compose config --quiet`: 성공.
- `docker compose up -d --build`: db/migrate/app/worker 기동. app/worker healthcheck 통과. DB 호스트 포트 미공개, 실제 .env는 무작위 생성·권한600·Git 제외.
- `APP_PORT=18080 docker compose -p newschops-verify up -d --build`: 별도 새 volume/포트에서 한 명령 기동 성공. 활성10곳 정상, 기사593건, 이슈579개, 스냅샷7개, 현재10개 선정. 검증 뒤 시험 프로젝트만 중지/제거하고 볼륨은 보존.
- 단위/fixture22개 통과: `docker run --rm -v "$PWD:/work" -w /work newschops-test python -m pytest -q`. FastAPI/Starlette testclient의 httpx 사용 중단 예고1건은 실패가 아니다. SSRF/검증 IP 고정/SNI/304, 실패→0건 성공 복구, 지면 날짜·면수·순서, 발행·수정 시각 분리, KST·주차·미래 기사 제외 등을 검증한다.
- 소스10곳 fixture 중 매경/한경은 합성 fixture, 나머지는 live 최소 메타데이터다. fixture 성공과 실제 외부 연결 성공을 구분한다.
- `npm --prefix frontend run build`: TypeScript/Vite 빌드 성공. Vite7.3.7로 취약 버전을 수정했고 `npm audit` 알려진 취약점0.
- `scripts/integration_smoke.py`를 app 컨테이너 안에서 실행: 실제 HTTP 로그인·계정 생성·일반 사용자403·사용자 설정 격리·로그아웃·PostgreSQL advisory 중복 잠금 통과. 임시 사용자는 정리한다.
- `NODE_PATH=/tmp/newschops-browser/node_modules node tests/browser_smoke.cjs`: 별도 설치한 Playwright/Chromium으로 로그인·관리자/설정/지면 화면·360/768/1440 가로 넘침·manifest/아이콘·로그아웃을 검증했다. 스크린샷은 /tmp/newschops-mobile.png, /tmp/newschops-desktop.png이며 Git에 넣지 않는다. 재현하려면 별도 개발 경로에 Playwright와 Chromium을 설치한다.
- 백업1차: 실제 dump를 별도 `newschops_restore_test` DB에 복구하여 사용자1명/기사445건/스냅샷7개 확인 후 시험 DB만 삭제했다. 원래 DB는 유지했다. migration003 뒤 최종 백업도 생성했다. 최종 백업 복구 결과는 아래 인계 기록에 추가한다.
- 재기동 후 실제 DB 기사593건/이슈578개/스냅샷12개 유지, migration003 확인.

## 성능 실측

같은 호스트의 Docker/PostgreSQL17, 기사593건·이슈578개, 2026-10-25 KST 단발 측정이다. 현재 순위 재계산128.73ms, 최대10개 선정, AI 호출0. 초기 N+1 조회2,700.03ms를 bulk 조회로 개선했다. 전체7기간 잡의 합산 소요시간은 측정하지 않았다.

초기 수집은 매체별 약2.0~6.2초(동시성3)이며 네트워크 영향을 받는다. idle 단발 메모리는 app66.49MiB/worker57.75MiB/DB70.65MiB이며 peak 측정이 아니다. 최종 JS는 약211KB(gzip67KB), 한국어 글꼴은 별도 정적 subset assets다. 운영 성능 보장 수치가 아니다.

## 다음 작업

1. 초기 커밋 후 실제 Git 상태를 확인한다. 작성자는 사용자 지정 pscho / ggbebe7@gmail.com이며 저장소 로컬에만 설정했다. 제공 두 문서를 보존했다.
2. 소스별 재이용 조건 추가 확인. 한겨레 발행 시각 미제공, 경향 수정 시각만 제공은 각각 NULL/별도 수정 시각으로 보존한다. 세계일보의 비표준 RFC 날짜는 timezone이 있는 원래 pubDate를 파싱한다. 경제지 간헐403은 장기 관측이 필요하다.
3. 독립 취재·전재 origin의 증거 확보와 사건 실체·중요 전개 탐지. 현재 정확 제목 규칙은 유사 사건의 과소 병합을 허용하는 보수적 제한이다.
4. 허용 본문 처리 범위 확보 후 선택 AI 공급자·구조화 검증·예산의 원자 예약·캐시·실패 fallback·출처 연결 구현. 현재 AI 환경변수만 입력해도 활성화되지 않는다.
5. 관리자 병합/분리 API의 화면, 순위 가중치/적격 기준/대형 사건 설정 버전 UI, 확정 기간 정정 버전. 현재 정정은 잠정5기간만 새 버전을 만든다.
6. 소스 상태24시간 집계·추이·상세 오류 유형/복구 이력 보강. 현재 최근8회 이력, 개별 소요시간, 최근 확인, 실패 수, 기능별 상태를 제공한다.
7. 실제 도메인 HTTPS 및 Android/iOS 설치·오프라인·업데이트 실기기 시험. 현재 프록시 로그인 제한은 peer 단위 공유이므로 trusted proxy 허용목록 기반 IP 처리가 후속 작업이다.
8. 사용자 재활성화, 피드백 전용 UI, 관심 기간 설정, 장기 데이터의 부하·보존 시험.

## 최종 인계 확인

- migration003 이후 최종 백업도 별도 시험 DB에 복구했다. 사용자1명·기사593건·지면66건·schema003 확인 후 시험 DB만 삭제했다.
- 운영 앱은 http://localhost:8080 에서 실행 중이다. 임시 newschops-verify 프로젝트 컨테이너는 제거했고 별도 시험 볼륨은 보존했다.
- 최종 비밀 검사: 실제 .env의 DB 비밀번호·관리자 비밀번호·세션 비밀·AI 키가 staged 파일에 없는지 검사했고 통과했다. .env/node_modules/백업은 추적되지 않는다. `git diff --cached --check` 통과.
- 초기 커밋을 `git -c user.useConfigOnly=true commit`으로 실제 시도했으나 `Author identity unknown` / 이메일 미설정으로 종료128. 임의 작성자 추론을 차단했다. 프로젝트 파일72개는 stage 상태이며 커밋 해시는 없다.
- 최종 재기동 후 HTTP/DB 통합 검증 재통과. 수집이 계속되어 당시 기사596건·이슈581개·snapshot17개, 현재 순위 재계산133.98ms였다. 앞선593건 조건의128.73ms 측정과 구분한다.

- 작성자 차단 해소: 사용자가 pscho / ggbebe7@gmail.com을 지정했다. 이 저장소의 로컬 Git 설정에 적용하고 한국어 초기 커밋을 진행했다. 커밋 해시는 Git log로 확인하며 전역 설정과 원격은 변경하지 않았다.
