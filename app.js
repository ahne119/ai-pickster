// ================= Supabase 설정 =================
// Supabase 대시보드 > Settings > API 에서 Project URL 과 anon public 키를 복사해 넣으세요.
const SUPABASE_URL = "https://gffpfxbogevyecydmdim.supabase.co";
const SUPABASE_ANON_KEY = "sb_publishable_K5cV3hYlPLNGT4_wqJ4_IA_HZnmB5GO";
// =================================================

const isConfigured =
  SUPABASE_URL.startsWith("https://") && !SUPABASE_URL.includes("여기에_");
const sb = isConfigured
  ? window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  : null;

// 스팸 필터링 키워드 (필요에 따라 추가)
const SPAM_WORDS = ["사설", "충전", "보증업체", "카톡문의", "텔레문의", "토토사이트"];

let state = {
  analyses: [],
  schedules: [],
  bets: [],
  posts: [],
  sportFilter: "ALL",
  postCategory: "전체",
  user: null,
  profile: null,
  isSignUpMode: false,
  currentPostId: null,
};

// 데모 데이터 (Supabase 연결 전 미리보기용)
const DEMO_DATA = {
  analyses: [
    {
      match_id: "NBA_DEMO_1",
      sport: "🏀 NBA",
      is_soccer: false,
      kickoff_kst: "2026-11-26 (목) 12:00 KST",
      home_team: "LAL",
      away_team: "GSW",
      pred_summary: "GSW 112.4 - 118.1 LAL",
      home_prob: 69.2,
      draw_prob: null,
      away_prob: 30.8,
      home_odd: 1.58,
      draw_odd: null,
      away_odd: 2.45,
      pick_label: "LAL 승",
      pick_prob: 69.2,
      pick_ev: 9.3,
      tier: 3,
      conf_label: "⭐⭐⭐ (주력)",
      extra_info: "예상 총득점 230.5점 | 예상핸디 LAL -5.7",
      reasons: "• 공수마진(NetRtg) LAL 우위 (+5.2 vs +0.8)\n• 원정 GSW 백투백(연전) 피로도\n• 최근 5경기: GSW(WLWLL) vs LAL(WWWWL)",
    },
    {
      match_id: "SOC_DEMO_1",
      sport: "🏴󠁧󠁢󠁥󠁮󠁧󠁿 EPL",
      is_soccer: true,
      kickoff_kst: "2026-11-26 (목) 05:00 KST",
      home_team: "Arsenal",
      away_team: "Chelsea",
      pred_summary: "기대득점 Arsenal 1.95골 vs Chelsea 1.02골",
      home_prob: 60.5,
      draw_prob: 22.1,
      away_prob: 17.4,
      home_odd: 1.75,
      draw_odd: 3.8,
      away_odd: 4.5,
      pick_label: "Arsenal 홈 승",
      pick_prob: 60.5,
      pick_ev: 5.9,
      tier: 3,
      conf_label: "⭐⭐⭐ (주력)",
      extra_info: "2.5 오버 추천 (59.4%) | 유력 스코어: 2:1 (10.8%), 1:0 (9.5%)",
      reasons: "• 최근 5경기: 홈 Arsenal(WWWDW) vs 원정 Chelsea(WDLLW)",
    },
  ],
  schedules: [
    { kickoff_kst: "2026-11-26 (목) 05:00 KST", sport_tag: "🏴󠁧󠁢󠁥󠁮󠁧󠁿 EPL", matchup: "[홈] Arsenal vs [원정] Chelsea", badge: "예정" },
    { kickoff_kst: "2026-11-26 (목) 12:00 KST", sport_tag: "🏀 NBA", matchup: "[원정] GSW(10-7) @ [홈] LAL(13-4)", badge: "예정" },
  ],
  bets: [
    { bet_id: "1", sport: "🏀 NBA", match: "BOS @ MIA", pick_label: "BOS 승", odd: 1.62, ev_pct: 6.4, stake: 10000, status: "WON", profit: 6200, tier: 3, kickoff_kst: "2026-11-24 09:30 KST" },
    { bet_id: "2", sport: "🇪🇸 라리가", match: "Real Madrid vs Sevilla", pick_label: "Real Madrid 홈 승", odd: 1.45, ev_pct: 3.1, stake: 10000, status: "WON", profit: 4500, tier: 3, kickoff_kst: "2026-11-24 05:00 KST" },
    { bet_id: "3", sport: "🏴󠁧󠁢󠁥󠁮󠁧󠁿 EPL", match: "Arsenal vs Chelsea", pick_label: "Arsenal 홈 승", odd: 1.75, ev_pct: 5.9, stake: 10000, status: "PENDING", profit: 0, tier: 3, kickoff_kst: "2026-11-26 05:00 KST" },
  ],
  posts: [
    { id: 1, category: "분석공유", title: "오늘 LAL vs GSW 부상자 명단 공유합니다", content: "GSW 백투백이라 주전 일부 휴식 가능성 있다네요. AI 픽대로 LAL 승이 좋아 보입니다!", author_name: "농구팬", created_at: "2026-11-25T10:00:00Z", user_id: "demo" },
    { id: 2, category: "적중인증", title: "어제 AI 주력픽 2연승 달달하네요", content: "가상배팅이랑 같이 참고 중인데 최근 주력픽 적중률 좋네요 ㅎㅎ", author_name: "픽스터러버", created_at: "2026-11-25T08:30:00Z", user_id: "demo" },
  ],
};

// XSS 방지를 위한 HTML 이스케이프 함수
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// 초기화
document.addEventListener("DOMContentLoaded", async () => {
  if (!sb) {
    document.getElementById("demo-banner").classList.remove("hidden");
    state.analyses = DEMO_DATA.analyses;
    state.schedules = DEMO_DATA.schedules;
    state.bets = DEMO_DATA.bets;
    state.posts = DEMO_DATA.posts;
    renderAll();
    return;
  }

  await syncAuthUser();
  sb.auth.onAuthStateChange(async () => {
    await syncAuthUser();
  });
  await fetchAllData();
});

async function syncAuthUser() {
  const { data } = await sb.auth.getUser();
  state.user = data?.user || null;
  state.profile = null;
  if (state.user) {
    const { data: prof } = await sb
      .from("pickster_profiles")
      .select("*")
      .eq("id", state.user.id)
      .single();
    state.profile = prof || {
      nickname: state.user.email?.split("@")[0] || "회원",
      is_admin: false,
    };
  }
  renderAuthArea();
}

async function fetchAllData() {
  const cutoffIso = new Date(Date.now() - 4 * 3600 * 1000).toISOString();

  const [anRes, scRes, betRes, postRes] = await Promise.all([
    sb.from("pickster_match_analyses").select("*").gte("kickoff_iso", cutoffIso).order("kickoff_iso", { ascending: true }),
    sb.from("pickster_schedules").select("*").gte("kickoff_iso", cutoffIso).order("kickoff_iso", { ascending: true }),
    sb.from("pickster_virtual_bets").select("*").order("placed_at_kst", { ascending: false }),
    sb.from("pickster_posts").select("*").order("created_at", { ascending: false }).limit(50),
  ]);

  if (anRes.error) console.error("분석 데이터 조회 오류:", anRes.error);
  if (scRes.error) console.error("일정 데이터 조회 오류:", scRes.error);
  if (betRes.error) console.error("장부 데이터 조회 오류:", betRes.error);
  if (postRes.error) console.error("게시판 데이터 조회 오류:", postRes.error);

  state.analyses = anRes.data || [];
  state.schedules = scRes.data || [];
  state.bets = betRes.data || [];
  state.posts = postRes.data || [];
  renderAll();
}

function renderAll() {
  renderKPIs();
  renderBestPicks();
  renderAnalyses();
  renderSchedules();
  renderLedger();
  renderBoard();
}

// 탭 전환
function switchTab(tabName) {
  ["dashboard", "schedule", "ledger", "board"].forEach((name) => {
    document.getElementById(`sec-${name}`).classList.toggle("hidden", name !== tabName);
    const btn = document.getElementById(`tab-${name}`);
    if (name === tabName) {
      btn.className = "nav-btn px-3 py-1.5 rounded-lg font-medium bg-indigo-600 text-white";
    } else {
      btn.className = "nav-btn px-3 py-1.5 rounded-lg font-medium text-slate-300 hover:bg-slate-800";
    }
  });
}

// KPI 계산 및 렌더링
function renderKPIs() {
  const settled = state.bets.filter((b) => b.status === "WON" || b.status === "LOST");
  const pending = state.bets.filter((b) => b.status === "PENDING");
  const wins = settled.filter((b) => b.status === "WON").length;
  const losses = settled.filter((b) => b.status === "LOST").length;
  const total = wins + losses;
  const hitRate = total > 0 ? ((wins / total) * 100).toFixed(1) : "0.0";

  const totalStake = settled.reduce((acc, b) => acc + Number(b.stake || 0), 0);
  const netProfit = settled.reduce((acc, b) => acc + Number(b.profit || 0), 0);
  const roi = totalStake > 0 ? ((netProfit / totalStake) * 100).toFixed(1) : "0.0";

  const t3 = settled.filter((b) => Number(b.tier) === 3);
  const t3Wins = t3.filter((b) => b.status === "WON").length;
  const t3Total = t3.length;
  const t3Stake = t3.reduce((acc, b) => acc + Number(b.stake || 0), 0);
  const t3Profit = t3.reduce((acc, b) => acc + Number(b.profit || 0), 0);
  const t3Roi = t3Stake > 0 ? ((t3Profit / t3Stake) * 100).toFixed(1) : "0.0";

  document.getElementById("kpi-hitrate").textContent = `${hitRate}%`;
  document.getElementById("kpi-record").textContent = `${total}전 ${wins}승 ${losses}패`;

  const profitEl = document.getElementById("kpi-profit");
  profitEl.textContent = `${netProfit >= 0 ? "+" : ""}${netProfit.toLocaleString()}원`;
  profitEl.className = `text-2xl font-bold mt-1 ${netProfit >= 0 ? "text-emerald-400" : "text-rose-400"}`;

  document.getElementById("kpi-pending").textContent = `대기중 ${pending.length}건`;
  document.getElementById("kpi-roi").textContent = `${Number(roi) >= 0 ? "+" : ""}${roi}%`;
  document.getElementById("kpi-tier3").textContent = `${t3Wins}승 ${t3Total - t3Wins}패`;
  document.getElementById("kpi-tier3-roi").textContent = `ROI ${Number(t3Roi) >= 0 ? "+" : ""}${t3Roi}%`;
}

function renderBestPicks() {
  const container = document.getElementById("best-picks-list");
  const picks = state.analyses
    .filter((a) => Number(a.tier) >= 2)
    .sort((a, b) => Number(b.tier) - Number(a.tier) || Number(b.pick_prob) - Number(a.pick_prob))
    .slice(0, 8);

  if (picks.length === 0) {
    container.innerHTML = `<p class="text-slate-400">현재 추천 기준에 부합하는 예정 경기가 없습니다.</p>`;
    return;
  }

  container.innerHTML = picks
    .map((p) => {
      const evBadge =
        p.pick_ev != null
          ? `<span class="px-2 py-0.5 rounded text-xs ${p.pick_ev >= 5 ? "bg-emerald-500/20 text-emerald-300" : "bg-slate-800 text-slate-300"}">EV ${p.pick_ev >= 0 ? "+" : ""}${Number(p.pick_ev).toFixed(1)}%${p.pick_ev >= 5 ? " 💎" : ""}</span>`
          : "";
      return `
      <div class="flex flex-wrap items-center justify-between gap-2 bg-slate-800/50 border border-slate-800 rounded-lg px-3 py-2.5">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-xs px-2 py-0.5 rounded bg-slate-700 text-slate-200">${escapeHtml(p.sport)}</span>
          <span class="font-medium text-white">${escapeHtml(p.away_team)} vs ${escapeHtml(p.home_team)}</span>
          <span class="text-indigo-400 font-semibold">👉 ${escapeHtml(p.pick_label)} (${Number(p.pick_prob).toFixed(1)}%)</span>
        </div>
        <div class="flex items-center gap-2 text-xs">
          ${evBadge}
          <span class="text-amber-300">${escapeHtml(p.conf_label)}</span>
          <span class="text-slate-400">${escapeHtml(p.kickoff_kst)}</span>
        </div>
      </div>`;
    })
    .join("");
}

function filterAnalyses(filter) {
  state.sportFilter = filter;
  document.querySelectorAll("#sport-filter-btns button").forEach((btn, idx) => {
    const types = ["ALL", "NBA", "SOCCER"];
    btn.className =
      types[idx] === filter
        ? "filter-chip px-3 py-1.5 rounded-full bg-indigo-600 text-white"
        : "filter-chip px-3 py-1.5 rounded-full bg-slate-800 text-slate-300";
  });
  renderAnalyses();
}

function renderAnalyses() {
  const grid = document.getElementById("analyses-grid");
  const filtered = state.analyses.filter((a) => {
    if (state.sportFilter === "NBA") return !a.is_soccer;
    if (state.sportFilter === "SOCCER") return a.is_soccer;
    return true;
  });

  if (filtered.length === 0) {
    grid.innerHTML = `<div class="col-span-full text-center py-10 text-slate-400 bg-slate-900 border border-slate-800 rounded-xl">표시할 분석 경기가 없습니다.</div>`;
    return;
  }

  grid.innerHTML = filtered
    .map((a) => {
      const hProb = Number(a.home_prob || 0).toFixed(1);
      const dProb = a.draw_prob != null ? Number(a.draw_prob).toFixed(1) : null;
      const aProb = Number(a.away_prob || 0).toFixed(1);

      const oddStr = a.home_odd
        ? `💰 배당: ${a.is_soccer ? `홈 ${Number(a.home_odd).toFixed(2)} | 무 ${a.draw_odd ? Number(a.draw_odd).toFixed(2) : "-"} | 원정 ${Number(a.away_odd).toFixed(2)}` : `원정 ${Number(a.away_odd).toFixed(2)} | 홈 ${Number(a.home_odd).toFixed(2)}`}`
        : "";

      return `
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3 flex flex-col justify-between">
        <div class="space-y-3">
          <div class="flex items-center justify-between text-xs">
            <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-200 font-medium">${escapeHtml(a.sport)}</span>
            <span class="text-slate-400">${escapeHtml(a.kickoff_kst)}</span>
          </div>
          <div>
            <h3 class="text-base font-bold text-white">${escapeHtml(a.home_team)} (홈) vs ${escapeHtml(a.away_team)} (원정)</h3>
            <p class="text-xs text-indigo-300 mt-0.5">${escapeHtml(a.pred_summary)}</p>
          </div>

          <!-- 승률 바 -->
          <div class="space-y-1">
            <div class="flex justify-between text-[11px] text-slate-300">
              <span>홈 ${hProb}%</span>
              ${dProb !== null ? `<span>무 ${dProb}%</span>` : ""}
              <span>원정 ${aProb}%</span>
            </div>
            <div class="w-full h-2.5 rounded-full overflow-hidden flex bg-slate-800">
              <div style="width:${hProb}%" class="bg-indigo-500"></div>
              ${dProb !== null ? `<div style="width:${dProb}%" class="bg-slate-500"></div>` : ""}
              <div style="width:${aProb}%" class="bg-rose-500"></div>
            </div>
          </div>

          ${oddStr ? `<p class="text-xs text-slate-300">${oddStr}</p>` : ""}
          <p class="text-xs text-slate-400">${escapeHtml(a.extra_info)}</p>
          <pre class="text-xs text-slate-400 bg-slate-950/60 rounded-lg p-2.5 whitespace-pre-wrap font-sans leading-relaxed">${escapeHtml(a.reasons)}</pre>
        </div>

        <div class="pt-2 border-t border-slate-800 flex items-center justify-between text-xs">
          <span class="font-bold text-emerald-400">🎯 ${escapeHtml(a.pick_label)}</span>
          <span class="text-amber-300">${escapeHtml(a.conf_label)}</span>
        </div>
      </div>`;
    })
    .join("");
}

function renderSchedules() {
  const container = document.getElementById("schedule-container");
  if (state.schedules.length === 0) {
    container.innerHTML = `<p class="text-slate-400 bg-slate-900 border border-slate-800 rounded-xl p-6 text-center">예정된 경기 일정이 없습니다.</p>`;
    return;
  }

  const groups = {};
  state.schedules.forEach((s) => {
    const dateKey = (s.kickoff_kst || "").slice(0, 14);
    if (!groups[dateKey]) groups[dateKey] = [];
    groups[dateKey].push(s);
  });

  container.innerHTML = Object.entries(groups)
    .map(
      ([dateLabel, items]) => `
    <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
      <div class="bg-slate-800/60 px-4 py-2.5 text-sm font-bold text-white">🗓️ ${escapeHtml(dateLabel)}</div>
      <div class="divide-y divide-slate-800">
        ${items
          .map(
            (r) => `
          <div class="px-4 py-3 flex flex-wrap items-center justify-between gap-2 text-sm">
            <div class="flex items-center gap-2">
              <span class="text-xs text-slate-400 font-mono">${escapeHtml((r.kickoff_kst || "").slice(15, 20))}</span>
              <span class="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-200">${escapeHtml(r.sport_tag)}</span>
              <span class="text-slate-100">${escapeHtml(r.matchup)}</span>
            </div>
            <span class="text-xs px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300">${escapeHtml(r.badge)}</span>
          </div>`
          )
          .join("")}
      </div>
    </div>`
    )
    .join("");
}

function renderLedger() {
  const filter = document.getElementById("ledger-filter").value;
  const tbody = document.getElementById("ledger-tbody");
  const rows = state.bets.filter((b) => filter === "ALL" || b.status === filter);

  if (rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="px-4 py-8 text-center text-slate-400">배팅 내역이 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = rows
    .map((b) => {
      const badge =
        b.status === "WON"
          ? `<span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300">✅ 적중</span>`
          : b.status === "LOST"
          ? `<span class="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300">❌ 미적</span>`
          : b.status === "REFUND"
          ? `<span class="px-2 py-0.5 rounded bg-slate-700 text-slate-300">↩️ 취소</span>`
          : `<span class="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300">⏳ 대기</span>`;

      const profitNum = Number(b.profit || 0);
      const profitColor = profitNum > 0 ? "text-emerald-400" : profitNum < 0 ? "text-rose-400" : "text-slate-400";
      const evTxt = b.ev_pct != null ? ` (${b.ev_pct >= 0 ? "+" : ""}${Number(b.ev_pct).toFixed(1)}%)` : "";

      return `
      <tr class="hover:bg-slate-800/40">
        <td class="px-4 py-3">${escapeHtml(b.sport)}</td>
        <td class="px-4 py-3 font-medium text-white">${escapeHtml(b.match)}</td>
        <td class="px-4 py-3 text-indigo-300">${escapeHtml(b.pick_label)}</td>
        <td class="px-4 py-3">@${Number(b.odd).toFixed(2)}${evTxt}</td>
        <td class="px-4 py-3">${badge}</td>
        <td class="px-4 py-3 font-semibold ${profitColor}">${b.status === "PENDING" ? "-" : `${profitNum >= 0 ? "+" : ""}${profitNum.toLocaleString()}원`}</td>
        <td class="px-4 py-3 text-slate-400 text-xs">${escapeHtml(b.kickoff_kst)}</td>
      </tr>`;
    })
    .join("");
}

// ================= 게시판 & 인증 =================
function renderAuthArea() {
  const area = document.getElementById("auth-area");
  if (!state.user) {
    area.innerHTML = `<button onclick="openAuthModal()" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200">로그인 / 가입</button>`;
    return;
  }
  const nick = escapeHtml(state.profile?.nickname || "회원");
  const adminBadge = state.profile?.is_admin ? `<span class="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/30 text-rose-300">관리자</span>` : "";
  area.innerHTML = `
    <span class="text-slate-300 text-xs sm:text-sm">${nick} ${adminBadge}</span>
    <button onclick="logout()" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-slate-300">로그아웃</button>
  `;
}

function openAuthModal() {
  if (!sb) return alert("Supabase 연결 후 로그인 기능을 사용할 수 있습니다.");
  document.getElementById("auth-modal").classList.remove("hidden");
}
function closeAuthModal() { document.getElementById("auth-modal").classList.add("hidden"); }

function toggleAuthMode() {
  state.isSignUpMode = !state.isSignUpMode;
  document.getElementById("auth-modal-title").textContent = state.isSignUpMode ? "회원가입" : "로그인";
  document.getElementById("btn-auth-submit").textContent = state.isSignUpMode ? "가입하기" : "로그인";
  document.getElementById("btn-toggle-auth-mode").textContent = state.isSignUpMode ? "이미 계정이 있으신가요? 로그인" : "계정이 없으신가요? 회원가입";
  document.getElementById("login-nickname").classList.toggle("hidden", !state.isSignUpMode);
}

async function submitAuth() {
  const email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value;
  const nickname = document.getElementById("login-nickname").value.trim();
  if (!email || !password) return alert("이메일과 비밀번호를 입력하세요.");

  if (state.isSignUpMode) {
    if (!nickname) return alert("닉네임을 입력하세요.");
    const { data, error } = await sb.auth.signUp({ email, password, options: { data: { nickname } } });
    if (error) return alert("가입 실패: " + error.message);
    if (data?.session) {
      alert("가입 및 로그인이 완료되었습니다!");
    } else {
      alert("가입이 완료되었습니다! 이메일 인증이 켜져 있다면 메일함을 확인해 주세요.");
    }
    closeAuthModal();
  } else {
    const { error } = await sb.auth.signInWithPassword({ email, password });
    if (error) return alert("로그인 실패: " + error.message);
    closeAuthModal();
  }
}

async function logout() {
  await sb.auth.signOut();
}

function filterPosts(cat) {
  state.postCategory = cat;
  document.querySelectorAll(".post-cat-btn").forEach((btn) => {
    btn.className =
      btn.textContent === cat
        ? "post-cat-btn px-3 py-1.5 rounded-full bg-indigo-600 text-white"
        : "post-cat-btn px-3 py-1.5 rounded-full bg-slate-800 text-slate-300";
  });
  renderBoard();
}

function renderBoard() {
  const list = document.getElementById("board-list");
  const filtered = state.posts.filter((p) => state.postCategory === "전체" || p.category === state.postCategory);
  if (filtered.length === 0) {
    list.innerHTML = `<p class="p-8 text-center text-slate-400 text-sm">등록된 게시글이 없습니다.</p>`;
    return;
  }

  list.innerHTML = filtered
    .map((p) => {
      const dateStr = new Date(p.created_at).toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
      return `
      <div onclick="openPostDetail(${p.id})" class="p-4 hover:bg-slate-800/50 cursor-pointer flex items-center justify-between gap-3">
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-xs px-2 py-0.5 rounded bg-slate-800 text-indigo-300 shrink-0">${escapeHtml(p.category)}</span>
            <p class="font-medium text-white truncate">${escapeHtml(p.title)}</p>
          </div>
          <p class="text-xs text-slate-400 mt-1">${escapeHtml(p.author_name)} · ${dateStr}</p>
        </div>
        <span class="text-slate-500 text-xs shrink-0">보기 ›</span>
      </div>`;
    })
    .join("");
}

function openPostModal() {
  if (!sb) return alert("Supabase 연결 후 글쓰기가 가능합니다.");
  if (!state.user) return openAuthModal();
  document.getElementById("post-modal").classList.remove("hidden");
}
function closePostModal() { document.getElementById("post-modal").classList.add("hidden"); }

async function submitPost() {
  const category = document.getElementById("post-category").value;
  const title = document.getElementById("post-title").value.trim();
  const content = document.getElementById("post-content").value.trim();
  if (!title || !content) return alert("제목과 내용을 입력하세요.");
  if (SPAM_WORDS.some((w) => title.includes(w) || content.includes(w))) {
    return alert("부적절한 홍보성 키워드가 포함되어 있습니다.");
  }

  const author_name = state.profile?.nickname || state.user.email?.split("@")[0] || "회원";
  const { error } = await sb.from("pickster_posts").insert({ user_id: state.user.id, author_name, category, title, content });
  if (error) return alert("등록 실패: " + error.message);

  document.getElementById("post-title").value = "";
  document.getElementById("post-content").value = "";
  closePostModal();
  await fetchAllData();
}

async function openPostDetail(postId) {
  const post = state.posts.find((p) => p.id === postId);
  if (!post) return;
  state.currentPostId = postId;

  document.getElementById("detail-category").textContent = post.category;
  document.getElementById("detail-title").textContent = post.title;
  document.getElementById("detail-meta").textContent = `${post.author_name} · ${new Date(post.created_at).toLocaleString("ko-KR")}`;
  document.getElementById("detail-content").textContent = post.content;

  const canDelete = state.user && (state.user.id === post.user_id || state.profile?.is_admin);
  document.getElementById("detail-actions").innerHTML = canDelete
    ? `<button onclick="deletePost(${post.id})" class="text-xs px-3 py-1 rounded bg-rose-500/20 text-rose-300 hover:bg-rose-500/30">게시글 삭제</button>`
    : "";

  document.getElementById("post-detail-modal").classList.remove("hidden");
  await loadComments(postId);
}

function closeDetailModal() { document.getElementById("post-detail-modal").classList.add("hidden"); }

async function loadComments(postId) {
  const box = document.getElementById("detail-comments");
  if (!sb) {
    box.innerHTML = `<p class="text-xs text-slate-400">데모 모드에서는 댓글을 불러올 수 없습니다.</p>`;
    return;
  }
  const { data } = await sb
    .from("pickster_comments")
    .select("*")
    .eq("post_id", postId)
    .order("created_at", { ascending: true });
  if (!data || data.length === 0) {
    box.innerHTML = `<p class="text-xs text-slate-400">아직 댓글이 없습니다.</p>`;
    return;
  }
  box.innerHTML = data
    .map((c) => {
      const canDel = state.user && (state.user.id === c.user_id || state.profile?.is_admin);
      return `
      <div class="bg-slate-800/60 rounded-lg px-3 py-2 text-xs flex justify-between items-start gap-2">
        <div>
          <span class="font-semibold text-indigo-300">${escapeHtml(c.author_name)}</span>
          <p class="text-slate-200 mt-0.5">${escapeHtml(c.content)}</p>
        </div>
        ${canDel ? `<button onclick="deleteComment(${c.id})" class="text-rose-400 hover:underline shrink-0">삭제</button>` : ""}
      </div>`;
    })
    .join("");
}

async function submitComment() {
  if (!sb) return alert("Supabase 연결 후 댓글 작성이 가능합니다.");
  if (!state.user) return openAuthModal();
  const input = document.getElementById("comment-input");
  const content = input.value.trim();
  if (!content) return;
  if (SPAM_WORDS.some((w) => content.includes(w))) return alert("금지된 키워드가 포함되어 있습니다.");

  const author_name = state.profile?.nickname || state.user.email?.split("@")[0] || "회원";
  const { error } = await sb.from("pickster_comments").insert({
    post_id: state.currentPostId,
    user_id: state.user.id,
    author_name,
    content,
  });
  if (error) return alert("댓글 등록 실패: " + error.message);
  input.value = "";
  await loadComments(state.currentPostId);
}

async function deletePost(postId) {
  if (!confirm("정말 삭제하시겠습니까?")) return;
  const { error } = await sb.from("pickster_posts").delete().eq("id", postId);
  if (error) return alert("삭제 실패: " + error.message);
  closeDetailModal();
  await fetchAllData();
}

async function deleteComment(commentId) {
  const { error } = await sb.from("pickster_comments").delete().eq("id", commentId);
  if (error) return alert("삭제 실패: " + error.message);
  await loadComments(state.currentPostId);
}