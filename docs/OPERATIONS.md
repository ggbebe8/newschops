# 운영

## 실행과 업데이트

Docker/Compose가 필요하다. .env 준비 후 `docker compose up -d --build`. `docker compose ps`, `docker compose logs --tail=80 app worker migrate`로 상태를 확인한다. 로그에 환경변수/원문/비밀을 출력하지 않는다. 기존 .env의 ADMIN_PASSWORD 변경으로 DB 비밀번호가 바뀌지 않는다. UI에서 비밀번호 변경 또는 관리자 초기화 API를 사용한다.

업데이트 전 `sh scripts/backup.sh`와 별도 안전 위치에 .env/Caddyfile 백업. `docker compose up -d --build`. 중지는 `docker compose stop`. 일반 운영에 volume 삭제 명령을 사용하지 않는다. migration이 비호환이면 앱 이미지 롤백만으로 복구되지 않는다. 이전 이미지와 이전 DB 백업을 함께 복원해야 한다.

## HTTPS

1. 기존 HTTPS reverse proxy: APP_ORIGIN=https://news.example.com, APP_BIND=0.0.0.0. 프록시는 172.21.0.1:38475 또는 호스트 포트로 전달한다. Caddy 등 역방향 프록시에서 `X-Forwarded-Proto: https`를 전달하며 Secure 쿠키가 자동 적용된다.
   - 현재 호스트에서는 `livesync-caddy`가 `newschops.ggbebe8.duckdns.org` 도메인으로 `172.21.0.1:38475`에 대한 HTTPS 종단 및 Let's Encrypt 인증서를 자동 관리한다.
2. 자체 Caddy 프로필: DOMAIN=news.example.com, TLS_EMAIL, APP_ORIGIN=https://news.example.com. `docker compose --profile tls up -d --build`. DNS A/AAAA와 80/443 접근은 사용자 인프라 사전조건. Caddy가 HTTPS를 종료하므로 Secure 쿠키가 설정된다.

공개 회원가입 없음. 관리자 생성/비활성화/초기화 API는 관리자 세션+CSRF 필요. `/api/admin/users` GET/POST, `POST /api/admin/users/{id}/disable`, `POST /api/admin/users/{id}/reset-password` (username/password JSON). 사용자 생성/비활성화/초기화는 관리자 사용자 관리 화면에서도 제공한다. 비밀번호 변경/초기화 시 모든 기존 세션 폐기. 세션 만료12시간. 로그인 15분10회(프로세스 메모리; app 단일 프로세스 기준).

## 백업과 복구

`sh scripts/backup.sh`: Git 제외 backups/에 pg_dump custom format. 파일 권한 umask077. .env와 Caddyfile은 백업 파일과 별도로 안전하게 보관한다. DB 백업에는 세션/비밀번호 해시/사용자 관심이 있어 접근을 제한한다.

기존 데이터 교체는 `sh scripts/restore.sh backups/파일.dump`. 스크립트는 app/worker 중지 → DB clean restore → app/worker 재시작한다. 먼저 별도 DB에 복구 시험을 한다:

```
docker compose exec -T db createdb -U newschops newschops_restore_test
docker compose exec -T db pg_restore -U newschops -d newschops_restore_test --exit-on-error < backups/파일.dump
docker compose exec -T db psql -U newschops -d newschops_restore_test -c 'SELECT count(*) FROM users; SELECT count(*) FROM articles;'
docker compose exec -T db dropdb -U newschops newschops_restore_test
```

본 DB와 시험 DB가 서로 다름을 확인한다. 복구 실행 결과는 docs/TASKS에 기록한다.

## 보존/장애

기사90일(ARTICLE_RETENTION_DAYS), snapshot90일, 수집이력30일, 만료 세션 자동삭제. 본문 보관 없음. 기사 삭제 시 관련 빈 이슈/사용자 상태도 정리되며 과거 snapshot JSON은 남는다. audit365일, AI 결과90일 자동 정리. 설정 버전은 크기가 작은 운영 이력으로 보존한다. 지면 목차30일. Docker 로그 10MB×3/서비스.

실패 매체만 지수 backoff(15분~4시간). 429 Retry-After 초/HTTP-date를 존중하며 backoff에 jitter를 더한다. 수집 동시성 기본3, timeout10초, 응답2MB, redirect최대4. worker 전체 세션 advisory lock은 연결이 끊기면 PostgreSQL이 해제한다. 재시작 시 현재 슬롯과 기한지난 수집만 수행한다. 무거운 전체 백필 없음.

PWA는 정적 assets/icons/오프라인 안내만 캐시. API/index 사용자 데이터 캐시 제외, 모든 API no-store. 로그아웃은 세션 폐기·화면 초기화·사용자 캐시 삭제. 사용자 데이터 캐시는 생성하지 않으며 정적 셸 캐시는 유지한다. Android/iOS 실제 설치 시험은 별도 기기 필요. 서비스워커 설치/업데이트를 위해 HTTPS 또는 localhost 사용.

## 관리자 계정 교체

기존 관리자 로그인 → 사용자 관리에서 새 아이디/비밀번호와 관리자 권한으로 계정 생성 → 로그아웃 후 새 관리자 로그인 → 사용자 관리에서 기존 admin 비활성화. 자기 계정 비활성화는 차단된다. 비밀번호만 바꾸려면 개인 설정에서 변경하며 기존 세션은 폐기된다. ADMIN_USERNAME/ADMIN_PASSWORD 환경변수는 최초 설치에만 사용하므로 기존 계정의 이름이나 비밀번호 변경 수단이 아니다.

호스트 기본 포트는38475, 컨테이너 내부는8080이다. 다른 서비스의38471/38473/38501 사용을 확인한 뒤 선택했다. 포트를 바꾸면 APP_PORT와 HTTP 접속용 APP_ORIGIN을 함께 갱신한다. HTTPS 프록시 사용 시 APP_ORIGIN은 실제 도메인으로 유지한다.
