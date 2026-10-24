# 수집 출처와 검증

검증일 2026-10-25 KST. 기본 후보 10곳을 실제 HTTP로 모두 시도했고, 404/빈 응답 후보 3곳을 같은 범주의 공개 RSS로 교체했다. 기본 수집 풀은 아래 **10곳**이다. API 연결로 표시하지 않는다. RSS 제목/발행 시각/원문 링크만 보관하며 본문/이미지/PDF를 복제하지 않는다. 콘텐츠 재이용/외부 AI 허용은 RSS 접근 성공에서 추론하지 않는다. 조건 불명 소스는 메타데이터 읽기로 제한한다.

|매체|RSS 엔드포인트|독립 smoke|앱 worker 실수집|공식 확인 출발점|
|---|---|---|---|---|
|동아일보|https://rss.donga.com/total.xml|200 / 50개|정상|https://rss.donga.com/|
|조선일보|https://www.chosun.com/arc/outboundfeeds/rss/?outputType=xml|200 / 100개|정상|피드 자체(공식 도메인)|
|서울신문|https://www.seoul.co.kr/xml/rss/rss_top.xml|200 / 26개|정상|피드 자체(공식 도메인)|
|한겨레|https://www.hani.co.kr/rss/|200 / 30개|정상|공식 RSS 경로(redirect /rss)|
|경향신문|https://www.khan.co.kr/rss/rssdata/total_news.xml|200 / 45개|정상|https://www.khan.co.kr/company/sub03_2.html|
|세계일보|https://www.segye.com/Articles/RSSList/segye_recent.xml|200 / 20개|정상|피드 자체(공식 도메인)|
|연합뉴스|https://www.yna.co.kr/rss/news.xml|200 / 120개|정상|피드 자체(공식 도메인)|
|SBS|https://news.sbs.co.kr/news/newsflashRssFeed.do?plink=RSSREADER|200 / 102개|정상|https://news.sbs.co.kr/news/rss.do|
|매일경제|https://www.mk.co.kr/rss/30000001/|403(별도 호출)|200 / 정상|https://www.mk.co.kr/rss/|
|한국경제|https://www.hankyung.com/feed/all-news|403(별도 호출)|200 / 정상|https://www.hankyung.com/feed|

HTTP 상태는 경로/호출 시점에 따라 달랐다. 매일경제·한국경제의 별도 smoke 403을 숨기지 않고, worker에서 연결·파싱·기사 저장 성공도 구분해 기록한다. 안정성이 장기간 보장된다는 뜻이 아니다. 10곳 모두 최근 성공 상태는 관리자 페이지와 docs/source-worker-verification.json을 확인한다. 연결 결과 JSON에는 기사당 제목·링크 샘플 1개만 남긴다.

SBS 공식 RSS 페이지는 개인 비상업 이용을 허용하며 상업 이용은 별도 문의를 요구한다. 다른 소스의 재배포/AI 처리 범위는 추가 확인이 필요하다. 인증·쿼터가 검증된 API는 없고 RSS 요청은 15분 간격(기본), timeout10초, 동시성3, 실패 backoff, ETag/Last-Modified 조건부 요청을 사용한다. 429 Retry-After는 초/HTTP-date 모두 존중한다. 사설 IP/외부 도메인 리다이렉트/응답2MB 초과를 차단한다. 비공개 자격증명·결제·차단 우회는 사용하지 않았다.

## 원래 후보와 대체

- 중앙일보: https://www.joongang.co.kr/rss → 404. 서울신문(종합지)로 대체.
- 한국일보: https://www.hankookilbo.com/rss → 404. 세계일보(종합지)로 대체.
- KBS: https://world.kbs.co.kr/rss/rss_news.htm?lang=k → 200이지만 응답 본문0바이트, RSS 파싱 불가. KBS WORLD는 KBS 일반 뉴스 전체 범위가 아님도 명시. SBS(방송) 공식 RSS로 대체.
- 교체 전 DB에 있던 후보는 비활성/archived로 남겨 운영 이력을 보존하고 일반 목록/활성 수에서 제외한다. 신규 설치는 교체된10곳만 생성한다.

원래 후보 실제 결과: source-original-candidates.json. 대체 시험: source-alternatives.json. 최종 독립 시험: source-smoke.json. 테스트 fixtures/rss는 성공 소스의 최소 메타데이터이며 매경·한경 파일은 **합성 fixture**다. fixture 성공과 live 성공은 구분한다.

## 동아일보 실제 지면

공식 https://www.donga.com/news 는 실제 제목이 `지면보기｜동아일보`이며, 공개 HTML에 `지면 목차`, 날짜 선택 버튼, `desc_cont`의 면수와 순서별 기사 링크를 제공했다. 지면 이미지 열람은 회원 전용 안내가 있으므로 접근/다운로드하지 않았다. 공개 목차 메타데이터만 처리한다.

검증 사례: 2026-10-24자 A1면 첫 기사 링크의 기사ID `134899958`, A2면 첫 기사ID `134899954`. web 도구의 공식 페이지 목차와 직접 HTTP 파서 결과를 대조했다. 최소 구조 fixture tests/fixtures/donga-paper.html 및 tests/test_core.py가 날짜/면수/순서/목차 밖 웹기사 제외를 검증한다. 수집 당시 날짜를 오늘로 바꾸지 않는다. 일요일 접속 시 전날 신문이 선택될 수 있다.

paper_entries에 날짜·섹션·면·순서·제목·URL·목차 근거URL·관측시각을 저장한다. 일반 RSS와 지면 수집 상태는 분리한다. 확인된 연결만 이슈 상세에 지면 표시. 나머지는 지면 미확인, 다른9곳은 미지원. A1에 실제 연결된 기사에만 '1면 기타85' 배치 관측을 남긴다. 첫 기사라는 이유로 '주요100'을 추정하지 않는다. 관측이 없는 매체/기사는 결측이다. PDF 재배포/회원 로그인 우회 없음.
