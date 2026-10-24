# newschops 공통 작업 진입점

작업 전 [ai유지보수.md](ai유지보수.md)를 읽고 실제 Git/코드 상태를 확인한다. 요구사항은 CODEX_NEWS_SERVICE_BUILD_SPEC.md, 미완료는 docs/TASKS.md를 읽는다.

사용자 변경 보존. 작업 후 관련 테스트/빌드/필요한 Compose 검증을 실행하고 유지보수 문서·README·CHANGELOG를 코드와 동기화한 뒤 **한국어 메시지로 커밋**한다. Git author 미설정이면 임의 신원을 만들지 말고 사유를 보고한다. 비밀/.env/DB/백업/본문/로그는 커밋하지 않는다. 원격 push는 별도 요청 필요.

서비스에 샘플을 실제 뉴스로 넣거나 미검증 연결/지면/AI 기능을 완료로 표시하지 않는다. 인증/CSRF/사용자 격리/SSRF/순위 시각 누수/불변 snapshot 보호를 유지한다.
