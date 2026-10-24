import "@fontsource/noto-sans-kr/400.css";
import "@fontsource/noto-sans-kr/700.css";
import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
type User = {
  username: string;
  admin: boolean;
  csrf: string;
  preferences?: any;
};
const periods = [
  ["current", "현재 TOP 10"],
  ["hour", "최근 1시간"],
  ["today", "오늘"],
  ["daily-final", "일간 확정"],
  ["week", "이번 주"],
  ["weekly-final", "주간 확정"],
  ["7days", "최근 7일"],
];
function App() {
  const [user, setUser] = useState<User | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [tab, setTab] = useState("news"),
    [period, setPeriod] = useState("current"),
    [category, setCategory] = useState(""),
    [source, setSource] = useState(""),
    [q, setQ] = useState(""),
    [data, setData] = useState<any>({ entries: [] }),
    [sources, setSources] = useState<any[]>([]),
    [detail, setDetail] = useState<any>(null),
    [status, setStatus] = useState<any>(null),
    [dark, setDark] = useState(localStorage.getItem("theme") === "dark"),
    [format, setFormat] = useState("short"),
    [refresh, setRefresh] = useState(0),
    [update, setUpdate] = useState(false);
  async function api(path: string, method = "GET", body?: any) {
    const r = await fetch("/api" + path, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": user?.csrf || "",
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) {
      if (r.status === 401) setUser(null);
      let d;
      try {
        d = await r.json();
      } catch {}
      throw Error(
        typeof d?.detail === "string" ? d.detail : `요청 실패 (${r.status})`,
      );
    }
    return r.json();
  }

  function getTabFromHash() {
    const h = location.hash.replace(/^#/, "");
    if (h.startsWith("detail-")) return null;
    if (
      ["news", "paper", "interest", "saved", "settings", "users", "admin"].includes(
        h,
      )
    ) {
      return h;
    }
    return null;
  }

  function navigateTab(newTab: string) {
    if (tab === newTab && !detail) return;
    setTab(newTab);
    setDetail(null);
    history.pushState({ tab: newTab, detailId: null }, "", "#" + newTab);
  }

  function openDetail(issueId: string) {
    history.pushState({ tab, detailId: issueId }, "", "#detail-" + issueId);
    api("/issues/" + issueId)
      .then(setDetail)
      .catch((e) => setError(e.message));
  }

  function closeDetail() {
    if (location.hash.startsWith("#detail-")) {
      history.back();
    } else {
      setDetail(null);
    }
  }

  useEffect(() => {
    const initialTab = getTabFromHash() || "news";
    setTab(initialTab);
    if (!history.state) {
      history.replaceState(
        { tab: initialTab, detailId: null },
        "",
        location.hash || "#" + initialTab,
      );
    }

    const onPopState = (e: PopStateEvent) => {
      const h = location.hash.replace(/^#/, "");
      if (h.startsWith("detail-")) {
        const detailId = h.replace("detail-", "");
        api("/issues/" + detailId)
          .then(setDetail)
          .catch((err) => setError(err.message));
      } else {
        setDetail(null);
        const targetTab = e.state?.tab || getTabFromHash() || "news";
        setTab(targetTab);
      }
    };

    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);
  useEffect(() => {
    fetch("/api/me")
      .then((r) => (r.ok ? r.json() : null))
      .then(setUser)
      .finally(() => setLoading(false));
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").then((r) => {
        r.onupdatefound = () => {
          const w = r.installing;
          if (w)
            w.onstatechange = () => {
              if (w.state === "installed" && navigator.serviceWorker.controller)
                setUpdate(true);
            };
        };
      });
    }
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);
  useEffect(() => {
    if (!user) return;
    setLoading(true);
    setError("");
    setDetail(null);
    Promise.all([
      api("/sources").then(setSources),
      tab === "admin"
        ? api("/admin/status").then(setStatus)
        : api(
            `/${["interest", "saved"].includes(tab) || source || q ? "feed" : "rankings"}?period=${period}&category=${encodeURIComponent(category)}&source=${encodeURIComponent(source)}&q=${encodeURIComponent(q)}&view=${tab}`,
          ).then(setData),
    ])
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [user, tab, period, category, source, q, refresh]);
  async function logout() {
    try {
      await api("/logout", "POST");
      setUser(null);
      setData({ entries: [] });
      setDetail(null);
      setStatus(null);
      if ("caches" in window)
        for (const key of await caches.keys())
          if (key.startsWith("newschops-user-")) await caches.delete(key);
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function state(entry: any, key: string) {
    try {
      await api(`/issues/${entry.id}/state`, "PUT", {
        ...entry.state,
        [key]: !entry.state?.[key],
      });
      setRefresh((x) => x + 1);
    } catch (e: any) {
      setError(e.message);
    }
  }
  if (!user)
    return (
      <main className="login">
        <div className="wordmark">
          news<span>chops</span>
          <b>●</b>
        </div>
        <div className="login-box">
          <span className="eyebrow">YOUR DAILY PERSPECTIVE</span>
          <h1>
            뉴스를 모으고,
            <br />
            맥락을 읽다.
          </h1>
          <p>나에게 필요한 오늘의 소식을 한곳에서.</p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setError("");
              const f = new FormData(e.currentTarget);
              try {
                setUser(await api("/login", "POST", Object.fromEntries(f)));
              } catch (e: any) {
                setError(e.message);
              }
            }}
          >
            <label>
              아이디
              <input name="username" autoComplete="username" required />
            </label>
            <label>
              비밀번호
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                required
              />
            </label>
            <button className="primary">로그인 →</button>
          </form>
          <p role="alert">{error}</p>
          <small>관리자가 발급한 계정으로 로그인하세요.</small>
        </div>
      </main>
    );
  return (
    <>
      <header>
        <button
          className="wordmark"
          onClick={() => {
            setTab("news");
            setDetail(null);
          }}
        >
          news<span>chops</span>
          <b>●</b>
        </button>
        <div className="header-right">
          <small>{user.username}</small>
          <button aria-label="테마 전환" onClick={() => setDark(!dark)}>
            {dark ? "☀" : "☾"}
          </button>
          <button onClick={logout}>로그아웃</button>
        </div>
      </header>
      <div className="shell">
        <aside>
          <div className="eyebrow">MY NEWSROOM</div>
          <nav>
            {[
              ["news", "◉", "주요 뉴스"],
              ["interest", "✧", "관심 뉴스"],
              ["saved", "▱", "저장한 뉴스"],
              ["paper", "▤", "언론사 · 지면"],
              ["settings", "⚙", "개인 설정"],
              ...(user.admin
                ? [
                    ["admin", "⌁", "수집 상태"],
                    ["users", "♙", "사용자 관리"],
                  ]
                : []),
            ].map(([id, icon, label]) => (
              <button
                className={tab === id ? "active" : ""}
                key={id}
                onClick={() => navigateTab(id)}
              >
                <span>{icon}</span>
                {label}
              </button>
            ))}
          </nav>
          <div className="side-note">
            <b>다양한 시선, 하나의 맥락.</b>
            <p>
              원문을 확인하고,
              <br />
              근거와 함께 읽으세요.
            </p>
            <small>Asia / Seoul</small>
          </div>
        </aside>
        <main className="content">
          {update && (
            <div className="notice">
              새 버전이 있습니다.{" "}
              <button
                onClick={async () => {
                  const registration =
                    await navigator.serviceWorker.getRegistration();
                  if (registration?.waiting) {
                    navigator.serviceWorker.addEventListener(
                      "controllerchange",
                      () => location.reload(),
                      { once: true },
                    );
                    registration.waiting.postMessage({
                      type: "ACTIVATE_UPDATE",
                    });
                  } else location.reload();
                }}
              >
                새로고침
              </button>
            </div>
          )}
          {error && (
            <div role="alert" className="notice">
              {error}
            </div>
          )}
          {tab === "settings" ? (
            <Settings
              user={user}
              api={api}
              done={() => setRefresh((x) => x + 1)}
            />
          ) : tab === "users" ? (
            <UserAdmin api={api} currentUser={user} />
          ) : tab === "admin" ? (
            <>
              <div className="eyebrow">OPERATIONS</div>
              <h1>수집 상태</h1>
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  try {
                    await api("/admin/rankings/rebuild", "POST", {
                      reason: f.get("reason"),
                    });
                    setError("순위 정정이 대기열에 등록되었습니다.");
                  } catch (e: any) {
                    setError(e.message);
                  }
                }}
              >
                <input
                  name="reason"
                  aria-label="순위 정정 이유"
                  placeholder="순위 정정 이유 (5자 이상)"
                  minLength={5}
                  required
                />
                <button>새 정정 버전 생성</button>
              </form>
              <p className="muted">
                연결 성공과 신규 기사 발견을 구분합니다. 본문·지면·AI는 별도
                지원 상태입니다.
              </p>
              <p>Worker heartbeat · {fmt(status?.heartbeat)}</p>
              <div className="notice">AI 비활성 · {status?.ai?.reason}</div>
              {status?.sources.map((s: any) => (
                <article key={s.id} className="card">
                  <div className="row">
                    <h2>{s.name}</h2>
                    <span className="badge">{s.state}</span>
                  </div>
                  <p>
                    최근 시도 {fmt(s.last_attempt)} · 정상 확인{" "}
                    {fmt(s.last_success)}
                  </p>
                  <p>
                    최근 신규 {fmt(s.last_new)} · 연속 실패 {s.failures}회
                  </p>
                  <p className="muted">
                    {Object.entries(s.capabilities)
                      .map(([k, v]) => `${k}: ${v}`)
                      .join(" / ")}
                  </p>
                  <div className="row">
                    <button
                      onClick={() =>
                        api(`/admin/sources/${s.id}/collect`, "POST")
                          .then(() => setRefresh((x) => x + 1))
                          .catch((e) => setError(e.message))
                      }
                    >
                      수동 수집
                    </button>
                    <button
                      onClick={() =>
                        api(
                          `/admin/sources/${s.id}/${s.enabled ? "pause" : "resume"}`,
                          "POST",
                        )
                          .then(() => setRefresh((x) => x + 1))
                          .catch((e) => setError(e.message))
                      }
                    >
                      {s.enabled ? "일시중지" : "재개"}
                    </button>
                  </div>
                  <details>
                    <summary>최근 실행 이력</summary>
                    {s.runs.map((r: any, i: number) => (
                      <p key={i}>
                        {fmt(r.created)} · {r.status} · 신규 {r.count}건 ·{" "}
                        {r.duration_ms}ms {r.error}
                      </p>
                    ))}
                  </details>
                </article>
              ))}
            </>
          ) : tab === "paper" ? (
            <>
              <div className="eyebrow">SOURCES & PRINT</div>
              <h1>언론사 · 지면</h1>
              <PaperView api={api} />
              <div className="source-grid">
                {sources.map((s) => (
                  <article className="card" key={s.id}>
                    <h2>{s.name}</h2>
                    <p>{s.state}</p>
                    <small>지면 {s.paper}</small>
                    <p>
                      <button
                        onClick={() => {
                          setSource(s.name);
                          setTab("news");
                        }}
                      >
                        관련 이슈 보기 →
                      </button>
                    </p>
                  </article>
                ))}
              </div>
            </>
          ) : detail ? (
            <>
              <button onClick={closeDetail}>← 뉴스 목록</button>
              <div className="eyebrow">ISSUE BRIEFING</div>
              <h1>{detail.title}</h1>
              {detail.comparison && !detail.comparison.startsWith("비교 불가") && (
                <div className="notice">{detail.comparison}</div>
              )}
              <h2>매체별 원문</h2>
              {detail.articles.map((a: any) => (
                <article className="card" key={a.id}>
                  <div className="row">
                    <span className="badge">{a.source}</span>
                    <small>
                      {fmt(a.published)} · {a.basis} · {a.paper}
                    </small>
                  </div>
                  <h2>
                    <a href={a.url} target="_blank" rel="noopener noreferrer">
                      {a.title} ↗
                    </a>
                  </h2>
                </article>
              ))}
            </>
          ) : (
            <>
              <div className="heading">
                <div>
                  <div className="eyebrow">THE DAILY BRIEFING</div>
                  <h1>
                    {tab === "interest"
                      ? "나의 관심 뉴스"
                      : tab === "saved"
                        ? "저장한 뉴스"
                        : "오늘, 알아야 할 이야기"}
                  </h1>
                  <p className="muted">
                    흩어진 뉴스를 모아, 중요한 흐름을 살펴보세요.
                  </p>
                </div>
                <span className="date">
                  {new Intl.DateTimeFormat("ko-KR", {
                    dateStyle: "full",
                    timeZone: "Asia/Seoul",
                  }).format(new Date())}
                </span>
              </div>
              <div className="periods">
                {periods.map(([id, label]) => (
                  <button
                    key={id}
                    className={period === id ? "selected" : ""}
                    onClick={() => setPeriod(id)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="category-bar">
                {[
                  ["", "종합"],
                  ["정치", "정치"],
                  ["경제", "경제"],
                  ["사회", "사회"],
                  ["국제", "국제"],
                  ["연예", "연예"],
                  ["스포츠", "스포츠"],
                  ["산업/기술", "IT/기술"],
                  ["문화", "문화"],
                ].map(([val, label]) => (
                  <button
                    key={val}
                    className={`cat-chip ${category === val ? "active" : ""}`}
                    onClick={() => setCategory(val)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="filters">
                <select
                  aria-label="언론사"
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                >
                  <option value="">모든 언론사</option>
                  {sources.map((s) => (
                    <option key={s.id}>{s.name}</option>
                  ))}
                </select>
                <input
                  aria-label="제목 검색"
                  placeholder="제목에서 검색"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
                <select
                  aria-label="읽기 형식"
                  value={format}
                  onChange={(e) => setFormat(e.target.value)}
                >
                  <option value="title">제목</option>
                  <option value="short">짧은 요약</option>
                  <option value="detail">상세 브리핑</option>
                </select>
              </div>
              <div className="coverage">
                <span className="dot" />
                {sources.filter((s) => s.state === "정상").length} /{" "}
                {sources.length}곳 정상{" "}
                <span>· 순위 갱신 {fmt(data.as_of)}</span>
              </div>
              <div className="section-label">
                <h2>
                  {source ||
                  category ||
                  q ||
                  ["interest", "saved"].includes(tab)
                    ? "뉴스 탐색"
                    : periods.find((p) => p[0] === period)?.[1]}
                </h2>
                <small>
                  {source ||
                  category ||
                  q ||
                  ["interest", "saved"].includes(tab)
                    ? "최근 수집 목록 · 최대 100개"
                    : "최대 10개 이슈 · 매시간 갱신"}
                </small>
              </div>
              {loading ? (
                <div className="empty">뉴스를 불러오고 있습니다…</div>
              ) : !data.entries.length ? (
                <div className="empty">
                  <span>▤</span>
                  <h2>아직 표시할 이슈가 없습니다</h2>
                  <p>
                    {tab === "interest"
                      ? "개인 설정에서 관심 키워드와 선호 매체를 등록하세요."
                      : "수집 작업을 기다리거나 기간과 필터를 변경해 보세요."}
                  </p>
                  <button onClick={() => setRefresh((x) => x + 1)}>
                    다시 확인
                  </button>
                </div>
              ) : (
                data.entries.map((r: any, i: number) => (
                  <article className="news-card" key={r.id}>
                    <div className="rank">{String(i + 1).padStart(2, "0")}</div>
                    <div className="news-body">
                      <div className="meta">
                        <span>{r.category}</span>
                        <span>{r.sources.length}개 매체</span>
                        <span>{fmt(r.occurred)}</span>
                      </div>
                      {r.url ? (
                        <a
                          href={r.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="headline"
                        >
                          {r.title} <span className="link-ext">↗</span>
                        </a>
                      ) : (
                        <button
                          className="headline"
                          onClick={() => openDetail(r.id)}
                        >
                          {r.title}
                        </button>
                      )}
                      <div className="source-line">
                        <span>{r.sources.join(" · ")}</span>
                        {r.sources.length > 1 && (
                          <button
                            className="compare-link"
                            onClick={() => openDetail(r.id)}
                          >
                            매체별 보도 ({r.sources.length}개)
                          </button>
                        )}
                        {r.match_reason && (
                          <span> · 관심 일치: {r.match_reason.join(", ")}</span>
                        )}
                      </div>
                      {format === "detail" && (
                        <p className="muted">
                          점수 {r.score.toFixed(1)} · 독립 취재 확인{" "}
                          {r.independent_origins} · 근거 충실도{" "}
                          {Math.round(r.evidence * 100)}% · 결측{" "}
                          {r.missing.join(", ")}
                        </p>
                      )}
                      <div className="actions">
                        <button
                          aria-pressed={!!r.state?.saved}
                          onClick={() => state(r, "saved")}
                        >
                          {r.state?.saved ? "★ 저장됨" : "☆ 저장"}
                        </button>
                        <button onClick={() => state(r, "read")}>
                          {r.state?.read ? "✓ 읽음" : "읽음 표시"}
                        </button>
                        <button onClick={() => state(r, "hidden")}>숨김</button>
                        <details>
                          <summary>
                            {r.evidence === 0 ? "수집 정보" : "선정 근거"}
                          </summary>
                          <p>
                            {r.confidence} · 점수 {r.score.toFixed(2)} · 결측:{" "}
                            {r.missing.join(", ")}
                            {r.selection_reason && ` · ${r.selection_reason}`}
                          </p>
                        </details>
                      </div>
                    </div>
                  </article>
                ))
              )}
              <p className="footnote">{data.notice}</p>
            </>
          )}
          <footer>
            newschops <span>뉴스의 출처는 각 언론사에 있습니다.</span>
            <details>
              <summary>앱 설치 안내</summary>
              <p>
                Android Chrome 메뉴에서 앱 설치를 선택하세요. iOS Safari에서는
                공유 → 홈 화면에 추가를 선택하세요. HTTPS 또는 localhost가
                필요합니다.
              </p>
            </details>
          </footer>
        </main>
      </div>
    </>
  );
}
function fmt(date: any) {
  return date
    ? new Intl.DateTimeFormat("ko-KR", {
        timeZone: "Asia/Seoul",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(date))
    : "확인 전";
}
function PaperView({ api }: { api: any }) {
  const [paper, setPaper] = useState<any>(null),
    [date, setDate] = useState(""),
    [error, setError] = useState("");
  useEffect(() => {
    api("/paper?date=" + date)
      .then(setPaper)
      .catch((e: any) => setError(e.message));
  }, [date]);
  return (
    <>
      <div className="notice">
        <h2>동아일보 실제 지면 목차</h2>
        <p>{error || paper?.message || "목차를 불러오고 있습니다…"}</p>
        <a
          href="https://www.donga.com/news"
          target="_blank"
          rel="noopener noreferrer"
        >
          공식 지면 페이지 ↗
        </a>
      </div>
      {paper?.supported && (
        <>
          <label>
            신문 발행일{" "}
            <select
              aria-label="신문 발행일"
              value={date || paper.date}
              onChange={(e) => setDate(e.target.value)}
            >
              {paper.dates.map((d: string) => (
                <option key={d}>{d}</option>
              ))}
            </select>
          </label>
          <div className="card">
            {paper.entries.map((p: any) => (
              <div
                className="paper-row"
                key={`${p.section}-${p.page}-${p.position}`}
              >
                <span className="badge">
                  {p.section}
                  {p.page}면 · {p.position}
                </span>
                <a href={p.url} target="_blank" rel="noopener noreferrer">
                  {p.title} ↗
                </a>
              </div>
            ))}
          </div>
        </>
      )}
      <h2>기본 수집 언론사</h2>
    </>
  );
}
function UserAdmin({
  api,
  currentUser,
}: {
  api: any;
  currentUser: User | null;
}) {
  const [users, setUsers] = useState<any[]>([]),
    [message, setMessage] = useState("");
  const reload = () =>
    api("/admin/users")
      .then(setUsers)
      .catch((e: any) => setMessage(e.message));
  useEffect(() => {
    reload();
  }, []);
  return (
    <>
      <div className="eyebrow">ACCESS MANAGEMENT</div>
      <h1>사용자 관리</h1>
      <p role="status">{message}</p>
      <form
        className="card settings"
        onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          try {
            await api("/admin/users", "POST", {
              username: f.get("username"),
              password: f.get("password"),
              admin: f.get("admin") === "on",
            });
            setMessage("계정이 생성되었습니다.");
            reload();
          } catch (e: any) {
            setMessage(e.message);
          }
        }}
      >
        <h2>계정 생성</h2>
        <label>
          아이디
          <input name="username" required autoComplete="off" />
        </label>
        <label>
          초기 비밀번호
          <input
            name="password"
            type="password"
            minLength={6}
            required
            autoComplete="new-password"
          />
        </label>
        <label>
          관리자 권한
          <input name="admin" type="checkbox" />
        </label>
        <button className="primary">생성</button>
      </form>
      {users.map((u) => (
        <article className="card" key={u.id}>
          <div className="row">
            <h2>{u.username}</h2>
            <span>
              {u.admin ? "관리자" : "일반 사용자"} ·{" "}
              {u.active ? "활성" : "비활성"}
            </span>
            <button
              disabled={!u.active || u.username === currentUser?.username}
              onClick={async () => {
                try {
                  await api(`/admin/users/${u.id}/disable`, "POST");
                  setMessage(`${u.username} 계정이 비활성화되었습니다.`);
                  reload();
                } catch (e: any) {
                  setMessage(e.message);
                }
              }}
            >
              {u.username === currentUser?.username
                ? "본인 계정"
                : u.active
                ? "비활성화"
                : "비활성 상태"}
            </button>
          </div>
          <details>
            <summary>비밀번호 초기화</summary>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                try {
                  await api(`/admin/users/${u.id}/reset-password`, "POST", {
                    username: u.username,
                    password: f.get("password"),
                  });
                  setMessage("비밀번호가 변경되어 기존 세션이 폐기되었습니다.");
                } catch (e: any) {
                  setMessage(e.message);
                }
              }}
            >
              <input
                aria-label="새 비밀번호"
                name="password"
                type="password"
                minLength={6}
                required
                autoComplete="new-password"
              />
              <button>초기화</button>
            </form>
          </details>
        </article>
      ))}
    </>
  );
}
function Settings({
  user,
  api,
  done,
}: {
  user: User;
  api: any;
  done: () => void;
}) {
  const [p, setP] = useState(user.preferences || {}),
    [message, setMessage] = useState("");
  return (
    <>
      <div className="eyebrow">PREFERENCES</div>
      <h1>나에게 맞는 뉴스</h1>
      <form
        className="card settings"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api("/preferences", "PUT", p);
            setMessage("설정이 저장되었습니다.");
            done();
          } catch (e: any) {
            setMessage(e.message);
          }
        }}
      >
        {[
          ["keywords", "관심 키워드 · 기업 · 주제"],
          ["excluded", "제외 키워드"],
          ["sources", "선호 매체 이름"],
          ["excluded_categories", "제외 분야"],
        ].map(([k, label]) => (
          <label key={k}>
            {label}
            <input
              value={(p[k] || []).join(", ")}
              onChange={(e) =>
                setP({
                  ...p,
                  [k]: e.target.value
                    .split(",")
                    .map((x) => x.trim())
                    .filter(Boolean),
                })
              }
              placeholder="쉼표로 구분하세요"
            />
          </label>
        ))}
        <button className="primary">관심 설정 저장</button>
        <p role="status">{message}</p>
      </form>
      <h2>비밀번호 변경</h2>
      <form
        className="card settings"
        onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          try {
            await api("/password", "POST", {
              username: user.username,
              password: f.get("password"),
            });
            location.reload();
          } catch (e: any) {
            setMessage(e.message);
          }
        }}
      >
        <label>
          새 비밀번호
          <input
            name="password"
            type="password"
            minLength={6}
            required
            autoComplete="new-password"
          />
        </label>
        <button>변경하고 다시 로그인</button>
      </form>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
