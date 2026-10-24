# newschops 구조

FastAPI가 인증 API와 Vite 빌드 결과를 동일 출처로 제공한다. React는 서버의 저장된 순위를 읽는다. 브라우저 요청으로 수집/순위 작업을 실행하지 않는다. PostgreSQL 17의 named volume에 데이터가 유지된다.

- backend/app/db.py: ORM 엔터티. users, sessions(토큰 SHA-256), sources, articles, issues, ranking_snapshots(JSON 불변 근거), collection_runs, user_issue_states, jobs, audit_events, issue_events, origin_groups, placement_observations, settings_versions, ai_results.
- backend/app/main.py: 세션 인증, CSRF, 관심·저장·설정, 관리자 수집/사용자/병합·분리 API.
- backend/app/collector.py: RSS/Atom 메타데이터 증분 처리. 출처 10곳은 sources.py의 개별 설정으로 분리. 본문을 수집·보관하지 않는다.
- backend/app/security.py: URL 정규화, 도메인·DNS·주소 검증, 검증 IP 연결 고정과 TLS SNI, redirect별 재검증, 2MB 제한.
- backend/app/ranking.py: UTC/KST 기간, 결측 점수와 선정 정책.
- backend/app/worker.py: 수집 concurrency 1~4, PostgreSQL 세션 advisory lock으로 worker 간 중복 실행 방지, heartbeat, 주기별 snapshot UNIQUE, 보존 정리.
- backend/migrations: Alembic 001. 전용 migrate 서비스가 advisory lock으로 실행하고 최초 관리자를 생성한다. app/worker는 migrate 성공 뒤 시작한다.

제목과 같은 날짜가 정확히 일치할 때만 이슈를 합친다. 유사 제목을 자동 병합하지 않아 오병합보다 누락을 선택한다. 발행 시각 부재는 NULL로 보존하고 순위에서 제외한다. 최초발견은 현재 시각이며 발행 시각과 혼동하지 않는다. 독립 취재를 확인할 수 없는 origin은 unknown으로 표시하고 독립 확산도에 가산하지 않는다. 관리자 병합/분리는 기사 연결과 이력을 변경하며 과거 snapshot을 수정하지 않는다.

동아일보 공개 지면 목차는 backend/app/paper.py가 별도 수집한다. paper_entries에 날짜·섹션·면수·순서·원문 링크·근거와 관측시각을 저장한다. 본문과 지면 이미지/PDF는 요청하지 않는다. migration 002는 지면 목록, 003은 기사 수정시각과 이슈 시각 추정 표시를 추가한다. 001은 schema_v1.py에 동결되어 후속 ORM 변경이 과거 migration을 바꾸지 않는다.

현재 제한: 정교한 사건 실체/중요 전개 추출, 전재 출처 확인, AI 공급자, 영향 근거 평가는 아직 운영 구현이 아니다. 주요배치는 동아일보 A1면 기타85 관측만 지원한다. 테이블이 있다는 사실이 해당 기능 완료를 뜻하지 않는다. docs/TASKS.md 참조.
