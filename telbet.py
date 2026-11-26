from difflib import SequenceMatcher
import html as html_lib
import math
import os
import re
import sys
import time
from datetime import datetime
import pandas as pd
import requests
from nba_api.stats.endpoints import (
    leaguedashteamstats,
    leaguegamelog,
    scheduleleaguev2,
)

try:
    from supabase import create_client
except ImportError:
    create_client = None

# ================= 통합 설정값 =================
# 모든 민감한 키는 GitHub Secrets 또는 OS 환경변수로 설정합니다.
FOOTBALL_API_KEY = os.getenv("FOOTBALL_DATA_API_KEY", "")
ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "@AIPCK")
TELEGRAM_SUMMARY_ONLY = False

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
_sb_client = (
    create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    if (create_client and SUPABASE_URL and SUPABASE_SERVICE_KEY)
    else None
)

# 구글 블로거 API 설정 (Secrets에 등록 시 자동 발행)
BLOGGER_BLOG_ID = os.getenv("BLOGGER_BLOG_ID", "")
BLOGGER_CLIENT_ID = os.getenv("BLOGGER_CLIENT_ID", "")
BLOGGER_CLIENT_SECRET = os.getenv("BLOGGER_CLIENT_SECRET", "")
BLOGGER_REFRESH_TOKEN = os.getenv("BLOGGER_REFRESH_TOKEN", "")

WEB_SITE_URL = os.getenv("WEB_SITE_URL", "https://ahne119.github.io/ai-pickster/")
TELEGRAM_CHANNEL_URL = "https://t.me/AIPCK"

AUTO_INTERVAL_HOURS = 24
BET_STAKE_KRW = 10000
BET_MIN_TIER = 2
BET_ONLY_POSITIVE_EV = False
LEDGER_FILENAME = "virtual_bets.csv"

TARGET_SOCCER_LEAGUES = {
    "PL": ("🏴󠁧󠁢󠁥󠁮󠁧󠁿 EPL", "soccer_epl"),
    "PD": ("🇪🇸 라리가", "soccer_spain_la_liga"),
    "BL1": ("🇩🇪 분데스리가", "soccer_germany_bundesliga"),
    "SA": ("🇮🇹 세리에 A", "soccer_italy_serie_a"),
    "CL": ("🏆 챔피언스리그", "soccer_uefa_champs_league"),
}

SCHEDULE_DAYS = 3
NBA_ANALYSIS_HOURS = 36
SOCCER_ANALYSIS_HOURS = 48
SAVE_TO_FILE = True
REPORT_FILENAME = "pickster_report.txt"
# ==============================================

WEEKDAYS_KR = ["월", "화", "수", "목", "금", "토", "일"]
FOOTBALL_BASE_URL = "https://api.football-data.org/v4"
ODDS_BASE_URL = "https://api.the-odds-api.com/v4"
_rate_limit_wait_until = 0.0
_odds_remaining_credits = None

LEDGER_COLUMNS = [
    "bet_id", "placed_at_kst", "kickoff_kst", "sport", "match",
    "pick_side", "pick_label", "tier", "prob_pct", "odd", "ev_pct",
    "stake", "status", "score", "payout", "profit", "settled_at_kst",
]

TEAM_ALIASES = {
    "man city": "manchester city",
    "man united": "manchester united",
    "man utd": "manchester united",
    "spurs": "tottenham hotspur",
    "tottenham": "tottenham hotspur",
    "wolves": "wolverhampton wanderers",
    "wolverhampton": "wolverhampton wanderers",
    "nottm forest": "nottingham forest",
    "brighton": "brighton and hove albion",
    "west ham": "west ham united",
    "newcastle": "newcastle united",
    "psg": "paris saint germain",
    "paris sg": "paris saint germain",
    "inter": "inter milan",
    "internazionale": "inter milan",
    "milan": "ac milan",
    "bayern": "bayern munich",
    "bayern munchen": "bayern munich",
    "dortmund": "borussia dortmund",
    "leverkusen": "bayer leverkusen",
    "gladbach": "borussia monchengladbach",
    "rb leipzig": "leipzig",
    "atleti": "atletico madrid",
    "atletico": "atletico madrid",
    "barca": "barcelona",
    "athletic": "athletic bilbao",
    "sociedad": "real sociedad",
    "betis": "real betis",
    "la clippers": "los angeles clippers",
    "la lakers": "los angeles lakers",
}


def format_kst_datetime(dt_kst: pd.Timestamp) -> str:
    wd = WEEKDAYS_KR[dt_kst.weekday()]
    return f"{dt_kst.strftime('%Y-%m-%d')} ({wd}) {dt_kst.strftime('%H:%M')} KST"


def normal_cdf(x: float, std_dev: float = 11.5) -> float:
    return 0.5 * (1.0 + math.erf(x / (std_dev * math.sqrt(2.0))))


def poisson_pmf(k: int, lam: float) -> float:
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def is_odds_enabled() -> bool:
    return bool(ODDS_API_KEY and ODDS_API_KEY.strip() and "여기에_" not in ODDS_API_KEY)


def is_telegram_enabled() -> bool:
    token_ok = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN.strip() and "여기에_" not in TELEGRAM_BOT_TOKEN)
    chan_ok = bool(TELEGRAM_CHANNEL_ID and TELEGRAM_CHANNEL_ID.strip() and "여기에_" not in TELEGRAM_CHANNEL_ID)
    return token_ok and chan_ok


def is_blogger_enabled() -> bool:
    return all(
        bool(v and v.strip())
        for v in (BLOGGER_BLOG_ID, BLOGGER_CLIENT_ID, BLOGGER_CLIENT_SECRET, BLOGGER_REFRESH_TOKEN)
    )


def normalize_team_name(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\b(fc|cf|sc|ac|as|ssc|rc|rcd|cd|ud|sd|ca|sv|vfl|vfb|tsg|fsv)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return TEAM_ALIASES.get(s, s)


def name_similarity(name1: str, name2: str) -> float:
    n1 = normalize_team_name(name1)
    n2 = normalize_team_name(name2)
    if not n1 or not n2:
        return 0.0
    if n1 == n2 or n1 in n2 or n2 in n1:
        return 0.95
    return SequenceMatcher(None, n1, n2).ratio()


def fetch_odds_events(sport_key: str, region: str = "eu") -> list:
    global _odds_remaining_credits
    if not is_odds_enabled():
        return []

    url = f"{ODDS_BASE_URL}/sports/{sport_key}/odds/"
    params = {"apiKey": ODDS_API_KEY, "regions": region, "markets": "h2h", "oddsFormat": "decimal"}
    try:
        resp = requests.get(url, params=params, timeout=15)
        rem = resp.headers.get("x-requests-remaining")
        if rem is not None:
            _odds_remaining_credits = rem

        if resp.status_code == 401:
            print("⚠️ [배당 API] API 키가 유효하지 않습니다.")
            return []
        if resp.status_code in (402, 429):
            print("⚠️ [배당 API] 월간 무료 크레딧 소진 또는 호출 제한에 걸렸습니다.")
            return []
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️ [배당 API] {sport_key} 조회 실패: {e}")
        return []


def match_game_odds(odds_events: list, home_name: str, away_name: str, dt_utc: pd.Timestamp, is_soccer: bool) -> dict | None:
    if not odds_events:
        return None

    best_event, best_score = None, 0.0
    for ev in odds_events:
        ev_time = pd.to_datetime(ev.get("commence_time"), utc=True, errors="coerce")
        if pd.isna(ev_time) or abs((ev_time - dt_utc).total_seconds()) > 7200:
            continue
        h_sim = name_similarity(home_name, ev.get("home_team", ""))
        a_sim = name_similarity(away_name, ev.get("away_team", ""))
        score = (h_sim + a_sim) / 2.0
        if h_sim >= 0.55 and a_sim >= 0.55 and score > best_score:
            best_score, best_event = score, ev

    if not best_event:
        return None

    ev_home, ev_away = best_event["home_team"], best_event["away_team"]
    h_prices, d_prices, a_prices = [], [], []

    for bm in best_event.get("bookmakers", []):
        for mkt in bm.get("markets", []):
            if mkt.get("key") != "h2h":
                continue
            for out in mkt.get("outcomes", []):
                o_name, price = out.get("name", ""), out.get("price")
                if not price:
                    continue
                if o_name == ev_home:
                    h_prices.append(float(price))
                elif o_name == ev_away:
                    a_prices.append(float(price))
                elif is_soccer and o_name.lower() == "draw":
                    d_prices.append(float(price))

    if not h_prices or not a_prices:
        return None

    return {
        "home_odd": sum(h_prices) / len(h_prices),
        "draw_odd": (sum(d_prices) / len(d_prices)) if d_prices else None,
        "away_odd": sum(a_prices) / len(a_prices),
        "book_count": len(h_prices),
    }


def calc_ev_pct(prob_pct: float, decimal_odd: float | None) -> float | None:
    if not decimal_odd or decimal_odd <= 1.0:
        return None
    return ((prob_pct / 100.0) * decimal_odd - 1.0) * 100.0


# =========================================================
# 🏀 PART 1. NBA 모듈 (공식 API + 클라우드용 백업 엔진)
# =========================================================
def get_current_nba_season() -> str:
    now = pd.Timestamp.now(tz="Asia/Seoul")
    year = now.year
    return f"{year}-{str(year + 1)[-2:]}" if now.month >= 10 else f"{year - 1}-{str(year)[-2:]}"


def get_nba_team_context(team_id: int, game_date_et: str, season_df: pd.DataFrame, last10_df: pd.DataFrame, logs_df: pd.DataFrame) -> dict:
    s_row = season_df[season_df["TEAM_ID"] == team_id].iloc[0]
    l_row_df = last10_df[last10_df["TEAM_ID"] == team_id]
    l_row = l_row_df.iloc[0] if not l_row_df.empty else s_row

    eff_ortg = s_row["OFF_RATING"] * 0.6 + l_row["OFF_RATING"] * 0.4
    eff_drtg = s_row["DEF_RATING"] * 0.6 + l_row["DEF_RATING"] * 0.4
    eff_pace = s_row["PACE"] * 0.6 + l_row["PACE"] * 0.4

    team_logs = logs_df[(logs_df["TEAM_ID"] == team_id) & (logs_df["GAME_DATE"] < game_date_et)]
    rest_days, recent_5 = None, "정보없음"

    if not team_logs.empty and pd.notna(game_date_et):
        last_date = datetime.strptime(team_logs.iloc[0]["GAME_DATE"], "%Y-%m-%d")
        target_date = datetime.strptime(game_date_et, "%Y-%m-%d")
        rest_days = (target_date - last_date).days
        recent_5 = "".join(team_logs.head(5)["WL"].tolist())

    return {
        "ortg": eff_ortg,
        "drtg": eff_drtg,
        "net_rtg": eff_ortg - eff_drtg,
        "pace": eff_pace,
        "is_b2b": (rest_days == 1),
        "recent_5": recent_5,
    }


def build_nba_fallback_stats(schedule_df: pd.DataFrame) -> tuple[dict, float]:
    """stats.nba.com 차단 시 ScheduleLeagueV2의 시즌 종료 경기들로 팀 득실점 통계를 계산합니다."""
    finished = schedule_df[
        (schedule_df["gameStatus"] == 3)
        & schedule_df["homeTeam_score"].notna()
        & schedule_df["awayTeam_score"].notna()
    ].copy()

    # 정규시즌/플레이오프 경기 우선 (프리시즌 001 제외)
    reg = finished[finished["gameId"].astype(str).str.startswith(("002", "004"))]
    if len(reg) >= 20:
        finished = reg

    if finished.empty:
        return {}, 113.0

    team_games = {}
    all_pts = []
    for _, r in finished.iterrows():
        hid, aid = int(r["homeTeam_teamId"]), int(r["awayTeam_teamId"])
        hs, aws = float(r["homeTeam_score"]), float(r["awayTeam_score"])
        gdate = r["game_date_et"]
        all_pts.extend([hs, aws])
        team_games.setdefault(hid, []).append((gdate, hs, aws, "W" if hs > aws else "L"))
        team_games.setdefault(aid, []).append((gdate, aws, hs, "W" if aws > hs else "L"))

    league_avg_ppg = sum(all_pts) / len(all_pts) if all_pts else 113.0
    stats_map = {}
    prior = 3.0

    for tid, gl in team_games.items():
        gl.sort(key=lambda x: x[0] or "", reverse=True)
        n = len(gl)
        s_for = (sum(x[1] for x in gl) + prior * league_avg_ppg) / (n + prior)
        s_agn = (sum(x[2] for x in gl) + prior * league_avg_ppg) / (n + prior)
        l10 = gl[:10]
        l_for = sum(x[1] for x in l10) / len(l10)
        l_agn = sum(x[2] for x in l10) / len(l10)

        eff_for = s_for * 0.6 + l_for * 0.4
        eff_agn = s_agn * 0.6 + l_agn * 0.4
        stats_map[tid] = {
            "eff_for": eff_for,
            "eff_agn": eff_agn,
            "net_ppg": eff_for - eff_agn,
            "games": gl,
        }
    return stats_map, league_avg_ppg


def get_nba_fallback_context(team_id: int, game_date_et: str, stats_map: dict, league_avg_ppg: float) -> dict:
    info = stats_map.get(team_id)
    if not info:
        return {
            "eff_for": league_avg_ppg, "eff_agn": league_avg_ppg,
            "net_ppg": 0.0, "is_b2b": False, "recent_5": "정보없음",
        }
    prev_games = [g for g in info["games"] if g[0] and game_date_et and g[0] < game_date_et]
    rest_days, recent_5 = None, "정보없음"
    if prev_games:
        last_date = datetime.strptime(prev_games[0][0], "%Y-%m-%d")
        target_date = datetime.strptime(game_date_et, "%Y-%m-%d")
        rest_days = (target_date - last_date).days
        recent_5 = "".join(g[3] for g in prev_games[:5])
    return {
        "eff_for": info["eff_for"],
        "eff_agn": info["eff_agn"],
        "net_ppg": info["net_ppg"],
        "is_b2b": (rest_days == 1),
        "recent_5": recent_5,
    }


def run_nba_module(now_kst: pd.Timestamp):
    season = get_current_nba_season()
    print(f"📡 [NBA] {season} 시즌 데이터를 불러오는 중...")

    schedule_df = scheduleleaguev2.ScheduleLeagueV2(season=season, timeout=30).season_games.get_data_frame()
    time.sleep(0.5)

    schedule_df["dt_utc"] = pd.to_datetime(schedule_df["gameDateTimeUTC"], utc=True, errors="coerce")
    schedule_df = schedule_df.dropna(subset=["dt_utc"]).copy()
    schedule_df["dt_kst"] = schedule_df["dt_utc"].dt.tz_convert("Asia/Seoul")
    schedule_df["game_date_et"] = pd.to_datetime(schedule_df["gameDateTimeEst"], errors="coerce").dt.strftime("%Y-%m-%d")
    schedule_df = schedule_df.sort_values("dt_kst")

    use_official_stats = False
    season_df = last10_df = logs_df = None
    fallback_stats, league_avg_ppg = {}, 113.0

    try:
        season_df = leaguedashteamstats.LeagueDashTeamStats(
            season=season, season_type_all_star="Regular Season", measure_type_detailed_defense="Advanced", timeout=12
        ).get_data_frames()[0]
        time.sleep(0.5)
        last10_df = leaguedashteamstats.LeagueDashTeamStats(
            season=season, season_type_all_star="Regular Season", measure_type_detailed_defense="Advanced", last_n_games=10, timeout=12
        ).get_data_frames()[0]
        time.sleep(0.5)
        logs_df = leaguegamelog.LeagueGameLog(
            season=season, season_type_all_star="Regular Season", player_or_team_abbreviation="T", direction="DESC", sorter="DATE", timeout=12
        ).get_data_frames()[0]
        use_official_stats = True
    except Exception as e:
        print(f"⚠️ [NBA] 공식 스탯 서버 응답 지연 -> 일정 기반 득실점 백업 모델로 전환합니다 ({type(e).__name__})")
        fallback_stats, league_avg_ppg = build_nba_fallback_stats(schedule_df)

    settled_lookup = {}
    finished_nba = schedule_df[schedule_df["gameStatus"] == 3]
    for _, r in finished_nba.iterrows():
        if pd.isna(r["homeTeam_score"]) or pd.isna(r["awayTeam_score"]):
            continue
        hs, aws = int(r["homeTeam_score"]), int(r["awayTeam_score"])
        settled_lookup[f"NBA_{r['gameId']}"] = {
            "status": "FINISHED",
            "winner": "home" if hs > aws else "away",
            "score": f"{aws}:{hs} (원정:홈)",
        }

    start_bound = now_kst - pd.Timedelta(hours=3)
    end_bound = now_kst + pd.Timedelta(days=SCHEDULE_DAYS)
    sched_window = schedule_df[(schedule_df["dt_kst"] >= start_bound) & (schedule_df["dt_kst"] <= end_bound)]

    schedule_rows = []
    for _, row in sched_window.iterrows():
        away_c, home_c = row["awayTeam_teamTricode"], row["homeTeam_teamTricode"]
        a_w = 0 if pd.isna(row["awayTeam_wins"]) else int(row["awayTeam_wins"])
        a_l = 0 if pd.isna(row["awayTeam_losses"]) else int(row["awayTeam_losses"])
        h_w = 0 if pd.isna(row["homeTeam_wins"]) else int(row["homeTeam_wins"])
        h_l = 0 if pd.isna(row["homeTeam_losses"]) else int(row["homeTeam_losses"])

        st = row["gameStatus"]
        if st == 1:
            badge = "예정"
        else:
            a_s = 0 if pd.isna(row["awayTeam_score"]) else int(row["awayTeam_score"])
            h_s = 0 if pd.isna(row["homeTeam_score"]) else int(row["homeTeam_score"])
            badge = f"{'진행중' if st == 2 else '종료'} {a_s}:{h_s}"

        schedule_rows.append({
            "schedule_id": f"NBA_{row['gameId']}",
            "kickoff_iso": row["dt_utc"].isoformat(),
            "dt_kst": row["dt_kst"],
            "sport_tag": "🏀 NBA",
            "matchup": f"[원정] {away_c}({a_w}-{a_l}) @ [홈] {home_c}({h_w}-{h_l})",
            "badge": badge,
        })

    analysis_end = now_kst + pd.Timedelta(hours=NBA_ANALYSIS_HOURS)
    upcoming_df = schedule_df[
        (schedule_df["gameStatus"] == 1)
        & (schedule_df["dt_kst"] >= now_kst)
        & (schedule_df["dt_kst"] <= analysis_end)
    ]

    nba_odds_events = []
    if not upcoming_df.empty and is_odds_enabled():
        print("💰 [배당] NBA 실시간 배당률을 불러오는 중...")
        nba_odds_events = fetch_odds_events("basketball_nba", region="us")

    valid_ids = set(season_df["TEAM_ID"].values) if use_official_stats else set()
    league_avg_ortg = season_df["OFF_RATING"].mean() if use_official_stats else 114.0
    reports, top_picks, analysis_rows = [], [], []

    for _, game in upcoming_df.iterrows():
        home_id, away_id = int(game["homeTeam_teamId"]), int(game["awayTeam_teamId"])
        home_code, away_code = game["homeTeam_teamTricode"], game["awayTeam_teamTricode"]
        if not home_code or not away_code:
            continue

        home_full = f"{game['homeTeam_teamCity']} {game['homeTeam_teamName']}".strip()
        away_full = f"{game['awayTeam_teamCity']} {game['awayTeam_teamName']}".strip()

        if use_official_stats and home_id in valid_ids and away_id in valid_ids:
            h_ctx = get_nba_team_context(home_id, game["game_date_et"], season_df, last10_df, logs_df)
            a_ctx = get_nba_team_context(away_id, game["game_date_et"], season_df, last10_df, logs_df)

            expected_pace = (h_ctx["pace"] + a_ctx["pace"]) / 2.0
            h_exp_ortg = h_ctx["ortg"] + a_ctx["drtg"] - league_avg_ortg
            a_exp_ortg = a_ctx["ortg"] + h_ctx["drtg"] - league_avg_ortg

            h_pred_pts = (h_exp_ortg / 100.0) * expected_pace + 1.2
            a_pred_pts = (a_exp_ortg / 100.0) * expected_pace - 1.2
            h_net, a_net, metric_name = h_ctx["net_rtg"], a_ctx["net_rtg"], "공수마진(NetRtg)"
            pace_txt = f"예상 페이스 {expected_pace:.1f}"
        else:
            h_ctx = get_nba_fallback_context(home_id, game["game_date_et"], fallback_stats, league_avg_ppg)
            a_ctx = get_nba_fallback_context(away_id, game["game_date_et"], fallback_stats, league_avg_ppg)

            h_pred_pts = h_ctx["eff_for"] + (a_ctx["eff_agn"] - league_avg_ppg) + 1.2
            a_pred_pts = a_ctx["eff_for"] + (h_ctx["eff_agn"] - league_avg_ppg) - 1.2
            h_net, a_net, metric_name = h_ctx["net_ppg"], a_ctx["net_ppg"], "득실점마진(PPG)"
            pace_txt = "득실점 백업모델"

        if h_ctx["is_b2b"]:
            h_pred_pts -= 1.5
            a_pred_pts += 0.8
        if a_ctx["is_b2b"]:
            a_pred_pts -= 1.5
            h_pred_pts += 0.8

        margin = h_pred_pts - a_pred_pts
        total_pts = h_pred_pts + a_pred_pts
        home_win_prob = normal_cdf(margin) * 100.0
        away_win_prob = 100.0 - home_win_prob

        if home_win_prob >= away_win_prob:
            pick_side, pick_team, pick_prob = "home", home_code, home_win_prob
            spread_str = f"{home_code} -{abs(margin):.1f}"
        else:
            pick_side, pick_team, pick_prob = "away", away_code, away_win_prob
            spread_str = f"{away_code} -{abs(margin):.1f}"

        if pick_prob >= 68:
            tier_score, conf = 3, "⭐⭐⭐ (주력)"
        elif pick_prob >= 58:
            tier_score, conf = 2, "⭐⭐ (일반)"
        else:
            tier_score, conf = 1, "⭐ (박빙/패스권장)"

        odds_info = match_game_odds(nba_odds_events, home_full, away_full, game["dt_utc"], is_soccer=False)
        odds_line, pick_odd, pick_ev = "", None, None
        if odds_info:
            pick_odd = odds_info["home_odd"] if pick_side == "home" else odds_info["away_odd"]
            pick_ev = calc_ev_pct(pick_prob, pick_odd)
            ev_badge = f" | 추천픽 기댓값(EV): {pick_ev:+.1f}% {'💎밸류!' if pick_ev >= 5.0 else ''}" if pick_ev is not None else ""
            odds_line = (
                f"\n💰 해외 평균배당: {away_code} {odds_info['away_odd']:.2f}  |  {home_code} {odds_info['home_odd']:.2f}"
                f" ({odds_info['book_count']}개사){ev_badge}"
            )

        reasons = []
        if abs(h_net - a_net) >= 3.5:
            better = home_code if h_net > a_net else away_code
            reasons.append(f"• {metric_name} {better} 우위 (홈 {h_net:+.1f} vs 원정 {a_net:+.1f})")
        else:
            reasons.append(f"• {metric_name} 호각세 (홈 {h_net:+.1f} vs 원정 {a_net:+.1f})")

        if h_ctx["is_b2b"] or a_ctx["is_b2b"]:
            b2b_list = [t for cond, t in [(h_ctx["is_b2b"], f"홈 {home_code}"), (a_ctx["is_b2b"], f"원정 {away_code}")] if cond]
            reasons.append(f"• ⚠️ 백투백(연전) 피로도: {', '.join(b2b_list)}")

        reasons.append(f"• 최근 5경기: {away_code}({a_ctx['recent_5']}) vs {home_code}({h_ctx['recent_5']})")
        kst_str = format_kst_datetime(game["dt_kst"])
        match_id_str = f"NBA_{game['gameId']}"

        reports.append(
            f"--------------------------------------------------\n"
            f"🏀 [원정] {away_full} ({away_code})  @  [홈] {home_full} ({home_code})\n"
            f"🕒 경기 일시   : {kst_str}\n"
            f"📊 예측 스코어 : {away_code} {a_pred_pts:.1f} - {h_pred_pts:.1f} {home_code}\n"
            f"📈 승리 확률   : {away_code} {away_win_prob:.1f}% | {home_code} {home_win_prob:.1f}%"
            f"{odds_line}\n"
            f"🔥 예상 총득점 : {total_pts:.1f}점 ({pace_txt})\n"
            f"🎯 픽스터 추천 : [{pick_team} 승] (예상핸디 {spread_str}) | {conf}\n"
            f"📝 분석 근거   :\n" + "\n".join(reasons)
        )

        analysis_rows.append({
            "match_id": match_id_str,
            "sport": "🏀 NBA",
            "is_soccer": False,
            "kickoff_kst": kst_str,
            "kickoff_iso": game["dt_utc"].isoformat(),
            "home_team": home_code,
            "away_team": away_code,
            "pred_summary": f"{away_code} {a_pred_pts:.1f} - {h_pred_pts:.1f} {home_code}",
            "home_prob": round(home_win_prob, 1),
            "draw_prob": None,
            "away_prob": round(away_win_prob, 1),
            "home_odd": round(odds_info["home_odd"], 2) if odds_info else None,
            "draw_odd": None,
            "away_odd": round(odds_info["away_odd"], 2) if odds_info else None,
            "pick_label": f"{pick_team} 승",
            "pick_prob": round(pick_prob, 1),
            "pick_ev": round(pick_ev, 1) if pick_ev is not None else None,
            "tier": tier_score,
            "conf_label": conf,
            "extra_info": f"예상 총득점 {total_pts:.1f}점 ({pace_txt}) | 예상핸디 {spread_str}",
            "reasons": "\n".join(reasons),
        })

        if tier_score >= 2:
            top_picks.append({
                "bet_id": match_id_str,
                "tier": tier_score,
                "prob": pick_prob,
                "sport": "🏀 NBA",
                "time": kst_str,
                "match": f"{away_code} @ {home_code}",
                "pick_side": pick_side,
                "pick": f"{pick_team} 승",
                "odd": pick_odd,
                "ev": pick_ev,
                "conf": conf,
            })

    return schedule_rows, reports, top_picks, settled_lookup, analysis_rows


# =========================================================
# ⚽ PART 2. 유럽축구 모듈
# =========================================================
def fetch_soccer_league_matches(league_code: str) -> list:
    global _rate_limit_wait_until
    url = f"{FOOTBALL_BASE_URL}/competitions/{league_code}/matches"
    headers = {"X-Auth-Token": FOOTBALL_API_KEY}

    while True:
        now = time.time()
        if now < _rate_limit_wait_until:
            sleep_sec = _rate_limit_wait_until - now
            print(f"⏳ [축구 API] 분당 호출 제한 보호를 위해 {sleep_sec:.1f}초 대기 중...")
            time.sleep(sleep_sec)

        resp = requests.get(url, headers=headers, timeout=20)
        remaining = resp.headers.get("X-Requests-Available-Minute")
        reset_sec = resp.headers.get("X-RequestCounter-Reset")

        if resp.status_code == 429:
            wait_sec = int(reset_sec) + 1 if reset_sec and reset_sec.isdigit() else 60
            print(f"⏳ [축구 API] 호출 제한(429) 도달! {wait_sec}초 대기 후 재시도합니다...")
            time.sleep(wait_sec)
            continue
        if resp.status_code == 403:
            raise PermissionError("축구 API 키가 올바르지 않거나 권한이 없습니다.")
        resp.raise_for_status()

        if remaining is not None and remaining.isdigit() and int(remaining) <= 0:
            wait_sec = int(reset_sec) + 1 if reset_sec and reset_sec.isdigit() else 60
            _rate_limit_wait_until = time.time() + wait_sec

        return resp.json().get("matches", [])


def parse_soccer_df(raw_matches: list, league_code: str, league_name: str) -> pd.DataFrame:
    rows = []
    for m in raw_matches:
        score_ft = m.get("score", {}).get("fullTime", {})
        home, away = m.get("homeTeam", {}), m.get("awayTeam", {})
        if not home.get("id") or not away.get("id"):
            continue
        rows.append({
            "match_id": m["id"],
            "league_code": league_code,
            "league_name": league_name,
            "status": m["status"],
            "utcDate": m["utcDate"],
            "home_id": home["id"],
            "home_name": home.get("shortName") or home.get("name"),
            "home_full_name": home.get("name") or home.get("shortName"),
            "away_id": away["id"],
            "away_name": away.get("shortName") or away.get("name"),
            "away_full_name": away.get("name") or away.get("shortName"),
            "home_goals": score_ft.get("home"),
            "away_goals": score_ft.get("away"),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["dt_utc"] = pd.to_datetime(df["utcDate"], utc=True, errors="coerce")
    df = df.dropna(subset=["dt_utc"]).copy()
    df["dt_kst"] = df["dt_utc"].dt.tz_convert("Asia/Seoul")
    return df.sort_values("dt_kst")


def get_soccer_form(league_df: pd.DataFrame, team_id: int) -> str:
    finished = league_df[
        (league_df["status"] == "FINISHED")
        & ((league_df["home_id"] == team_id) | (league_df["away_id"] == team_id))
    ].sort_values("dt_kst", ascending=False).head(5)

    if finished.empty:
        return "기록없음"

    form = []
    for _, r in finished.iterrows():
        hg, ag = r["home_goals"], r["away_goals"]
        if pd.isna(hg) or pd.isna(ag):
            continue
        if r["home_id"] == team_id:
            form.append("W" if hg > ag else ("D" if hg == ag else "L"))
        else:
            form.append("W" if ag > hg else ("D" if ag == hg else "L"))
    return "".join(form) if form else "기록없음"


def calculate_poisson(league_df: pd.DataFrame, home_id: int, away_id: int) -> dict:
    finished = league_df[
        (league_df["status"] == "FINISHED")
        & league_df["home_goals"].notna()
        & league_df["away_goals"].notna()
    ]

    if len(finished) < 10:
        avg_home_g, avg_away_g = 1.50, 1.20
    else:
        avg_home_g, avg_away_g = finished["home_goals"].mean(), finished["away_goals"].mean()

    prior = 4.0
    h_home = finished[finished["home_id"] == home_id]
    home_attack = ((h_home["home_goals"].sum() + prior * avg_home_g) / (len(h_home) + prior)) / avg_home_g
    home_defense = ((h_home["away_goals"].sum() + prior * avg_away_g) / (len(h_home) + prior)) / avg_away_g

    a_away = finished[finished["away_id"] == away_id]
    away_attack = ((a_away["away_goals"].sum() + prior * avg_away_g) / (len(a_away) + prior)) / avg_away_g
    away_defense = ((a_away["home_goals"].sum() + prior * avg_home_g) / (len(a_away) + prior)) / avg_home_g

    lam_home = max(0.25, min(4.2, home_attack * away_defense * avg_home_g))
    lam_away = max(0.20, min(4.0, away_attack * home_defense * avg_away_g))

    p_home = p_draw = p_away = p_over25 = p_btts = 0.0
    score_probs = []

    for hg in range(8):
        ph = poisson_pmf(hg, lam_home)
        for ag in range(8):
            prob = ph * poisson_pmf(ag, lam_away)
            score_probs.append((f"{hg}:{ag}", prob))
            if hg > ag:
                p_home += prob
            elif hg == ag:
                p_draw += prob
            else:
                p_away += prob
            if hg + ag >= 3:
                p_over25 += prob
            if hg >= 1 and ag >= 1:
                p_btts += prob

    total_p = p_home + p_draw + p_away
    p_home, p_draw, p_away = (p_home / total_p) * 100, (p_draw / total_p) * 100, (p_away / total_p) * 100
    p_over25, p_btts = (p_over25 / total_p) * 100, (p_btts / total_p) * 100
    score_probs.sort(key=lambda x: x[1], reverse=True)

    return {
        "lam_home": lam_home, "lam_away": lam_away,
        "p_home": p_home, "p_draw": p_draw, "p_away": p_away,
        "p_over25": p_over25, "p_under25": 100.0 - p_over25,
        "p_btts": p_btts,
        "top_scores": [f"{s} ({p * 100:.1f}%)" for s, p in score_probs[:2]],
    }


def run_soccer_module(now_kst: pd.Timestamp):
    if not FOOTBALL_API_KEY.strip():
        raise ValueError("축구 API 키가 설정되지 않았습니다.")

    print("📡 [축구] 주요 유럽 리그 일정을 불러오는 중...")
    league_dfs = {}
    for code, (name, _) in TARGET_SOCCER_LEAGUES.items():
        try:
            raw = fetch_soccer_league_matches(code)
            df = parse_soccer_df(raw, code, name)
            if not df.empty:
                league_dfs[code] = df
            time.sleep(0.4)
        except Exception as e:
            print(f"⚠️ {name}({code}) 수집 실패: {e}")

    if not league_dfs:
        return [], [], [], {}, []

    all_df = pd.concat(league_dfs.values(), ignore_index=True).sort_values("dt_kst")

    settled_lookup = {}
    for _, r in all_df.iterrows():
        key = f"SOC_{r['match_id']}"
        if r["status"] == "FINISHED" and pd.notna(r["home_goals"]) and pd.notna(r["away_goals"]):
            hg, ag = int(r["home_goals"]), int(r["away_goals"])
            settled_lookup[key] = {
                "status": "FINISHED",
                "winner": "home" if hg > ag else ("draw" if hg == ag else "away"),
                "score": f"{hg}:{ag} (홈:원정)",
            }
        elif r["status"] == "CANCELLED":
            settled_lookup[key] = {"status": "CANCELLED", "winner": None, "score": "취소"}

    start_bound = now_kst - pd.Timedelta(hours=3)
    end_bound = now_kst + pd.Timedelta(days=SCHEDULE_DAYS)
    sched_window = all_df[(all_df["dt_kst"] >= start_bound) & (all_df["dt_kst"] <= end_bound)]

    schedule_rows = []
    for _, row in sched_window.iterrows():
        st = row["status"]
        hg = 0 if pd.isna(row["home_goals"]) else int(row["home_goals"])
        ag = 0 if pd.isna(row["away_goals"]) else int(row["away_goals"])
        if st in ("SCHEDULED", "TIMED"):
            badge = "예정"
        elif st in ("IN_PLAY", "PAUSED"):
            badge = f"진행중 {hg}:{ag}"
        elif st == "FINISHED":
            badge = f"종료 {hg}:{ag}"
        else:
            badge = st

        schedule_rows.append({
            "schedule_id": f"SOC_{row['match_id']}",
            "kickoff_iso": row["dt_utc"].isoformat(),
            "dt_kst": row["dt_kst"],
            "sport_tag": row["league_name"],
            "matchup": f"[홈] {row['home_name']} vs [원정] {row['away_name']}",
            "badge": badge,
        })

    analysis_end = now_kst + pd.Timedelta(hours=SOCCER_ANALYSIS_HOURS)
    upcoming_df = all_df[
        (all_df["status"].isin(["SCHEDULED", "TIMED"]))
        & (all_df["dt_kst"] >= now_kst)
        & (all_df["dt_kst"] <= analysis_end)
    ]

    soccer_odds_by_league = {}
    if not upcoming_df.empty and is_odds_enabled():
        print("💰 [배당] 예정된 축구 리그의 실시간 배당률을 불러오는 중...")
        for l_code in upcoming_df["league_code"].unique():
            _, sport_key = TARGET_SOCCER_LEAGUES[l_code]
            soccer_odds_by_league[l_code] = fetch_odds_events(sport_key, region="eu")
            time.sleep(0.3)

    reports, top_picks, analysis_rows = [], [], []

    for _, row in upcoming_df.iterrows():
        l_code = row["league_code"]
        l_df = league_dfs[l_code]
        pred = calculate_poisson(l_df, row["home_id"], row["away_id"])
        h_form = get_soccer_form(l_df, row["home_id"])
        a_form = get_soccer_form(l_df, row["away_id"])

        probs = [
            ("home", "홈 승", pred["p_home"]),
            ("draw", "무승부", pred["p_draw"]),
            ("away", "원정 승", pred["p_away"]),
        ]
        probs.sort(key=lambda x: x[2], reverse=True)
        best_side, best_pick, best_prob = probs[0]
        _, second_pick, second_prob = probs[1]

        tier_score, pick_label, conf = 1, "", "⭐ (박빙)"
        if best_prob >= 58.0:
            tier_score, conf = 3, "⭐⭐⭐ (주력)"
            target = row["home_name"] if best_pick == "홈 승" else row["away_name"]
            pick_label = f"{target} {best_pick}"
            wdl_rec = f"[{pick_label}] ({conf})"
        elif best_prob - second_prob >= 8.0:
            tier_score, conf = 2, "⭐⭐ (일반)"
            target = row["home_name"] if best_pick == "홈 승" else (row["away_name"] if best_pick == "원정 승" else "무승부")
            pick_label = f"{target} ({best_pick})"
            wdl_rec = f"[{pick_label}] ({conf})"
        else:
            if {best_pick, second_pick} == {"홈 승", "무승부"}:
                wdl_rec = f"[{row['home_name']} 승/무 (1X) 추천] (박빙 ⭐)"
            elif {best_pick, second_pick} == {"원정 승", "무승부"}:
                wdl_rec = f"[{row['away_name']} 무/패 (X2) 추천] (박빙 ⭐)"
            else:
                wdl_rec = "[승무패 패스 권장 - 이변 주의 ⭐]"

        odds_events = soccer_odds_by_league.get(l_code, [])
        odds_info = match_game_odds(odds_events, row["home_full_name"], row["away_full_name"], row["dt_utc"], is_soccer=True)
        odds_line, pick_odd, pick_ev = "", None, None

        if odds_info:
            d_str = f"{odds_info['draw_odd']:.2f}" if odds_info["draw_odd"] else "-"
            pick_odd = odds_info["home_odd"] if best_side == "home" else (odds_info["draw_odd"] if best_side == "draw" else odds_info["away_odd"])
            pick_ev = calc_ev_pct(best_prob, pick_odd) if tier_score >= 2 else None
            ev_badge = f" | 추천픽 EV: {pick_ev:+.1f}% {'💎밸류!' if pick_ev >= 5.0 else ''}" if pick_ev is not None else ""
            odds_line = (
                f"\n💰 해외 평균배당: 홈 {odds_info['home_odd']:.2f} | 무 {d_str} | 원정 {odds_info['away_odd']:.2f}"
                f" ({odds_info['book_count']}개사){ev_badge}"
            )

        if pred["p_over25"] >= 57.0:
            ou_rec = f"2.5 오버 추천 ({pred['p_over25']:.1f}%)"
        elif pred["p_under25"] >= 57.0:
            ou_rec = f"2.5 언더 추천 ({pred['p_under25']:.1f}%)"
        else:
            ou_rec = f"기준점 2.5 관망 (오버 {pred['p_over25']:.1f}%)"

        btts_str = f"양팀 득점 높음({pred['p_btts']:.1f}%)" if pred["p_btts"] >= 56.0 else f"양팀 득점 {pred['p_btts']:.1f}%"
        kst_str = format_kst_datetime(row["dt_kst"])
        match_id_str = f"SOC_{row['match_id']}"

        reports.append(
            f"--------------------------------------------------\n"
            f"[{row['league_name']}]  🏠 {row['home_name']}  vs  ✈️ {row['away_name']}\n"
            f"🕒 경기 일시   : {kst_str}\n"
            f"⚽ 기대 득점   : {row['home_name']} {pred['lam_home']:.2f}골  vs  {row['away_name']} {pred['lam_away']:.2f}골\n"
            f"📈 승무패 확률 : 홈 승 {pred['p_home']:.1f}% | 무승부 {pred['p_draw']:.1f}% | 원정 승 {pred['p_away']:.1f}%"
            f"{odds_line}\n"
            f"🎯 유력 스코어 : {', '.join(pred['top_scores'])}\n"
            f"💡 승무패 픽   : {wdl_rec}\n"
            f"🔥 언오버 픽   : {ou_rec}  |  {btts_str}\n"
            f"📝 최근 5경기  : 홈 {row['home_name']}({h_form}) vs 원정 {row['away_name']}({a_form})"
        )

        analysis_rows.append({
            "match_id": match_id_str,
            "sport": row["league_name"],
            "is_soccer": True,
            "kickoff_kst": kst_str,
            "kickoff_iso": row["dt_utc"].isoformat(),
            "home_team": row["home_name"],
            "away_team": row["away_name"],
            "pred_summary": f"기대득점 {row['home_name']} {pred['lam_home']:.2f}골 vs {row['away_name']} {pred['lam_away']:.2f}골",
            "home_prob": round(pred["p_home"], 1),
            "draw_prob": round(pred["p_draw"], 1),
            "away_prob": round(pred["p_away"], 1),
            "home_odd": round(odds_info["home_odd"], 2) if odds_info else None,
            "draw_odd": round(odds_info["draw_odd"], 2) if (odds_info and odds_info.get("draw_odd")) else None,
            "away_odd": round(odds_info["away_odd"], 2) if odds_info else None,
            "pick_label": pick_label if pick_label else wdl_rec,
            "pick_prob": round(best_prob, 1),
            "pick_ev": round(pick_ev, 1) if pick_ev is not None else None,
            "tier": tier_score,
            "conf_label": conf,
            "extra_info": f"{ou_rec} | {btts_str} | 유력: {', '.join(pred['top_scores'])}",
            "reasons": f"• 최근 5경기: 홈 {row['home_name']}({h_form}) vs 원정 {row['away_name']}({a_form})",
        })

        if tier_score >= 2:
            top_picks.append({
                "bet_id": match_id_str,
                "tier": tier_score,
                "prob": best_prob,
                "sport": row["league_name"],
                "time": kst_str,
                "match": f"{row['home_name']} vs {row['away_name']}",
                "pick_side": best_side,
                "pick": pick_label,
                "odd": pick_odd,
                "ev": pick_ev,
                "conf": conf,
            })

    return schedule_rows, reports, top_picks, settled_lookup, analysis_rows


# =========================================================
# 💵 PART 3. 가상 배팅 장부 & Supabase 동기화
# =========================================================
def load_bet_ledger() -> list[dict]:
    if _sb_client:
        try:
            res = _sb_client.table("pickster_virtual_bets").select("*").execute()
            if res.data:
                return res.data
        except Exception as e:
            print(f"⚠️ [Supabase] 장부 불러오기 실패 (로컬 CSV 사용): {e}")

    if not os.path.exists(LEDGER_FILENAME):
        return []
    df = pd.read_csv(LEDGER_FILENAME, encoding="utf-8-sig", dtype={"bet_id": str, "score": str, "settled_at_kst": str})
    records = df.to_dict("records")
    for r in records:
        if pd.isna(r.get("score")):
            r["score"] = ""
        if pd.isna(r.get("settled_at_kst")):
            r["settled_at_kst"] = ""
        if pd.isna(r.get("ev_pct")):
            r["ev_pct"] = None
    return records


def save_bet_ledger(records: list[dict]):
    if _sb_client and records:
        clean_records = []
        for r in records:
            item = dict(r)
            for k, v in item.items():
                if isinstance(v, float) and math.isnan(v):
                    item[k] = None
            clean_records.append(item)
        try:
            _sb_client.table("pickster_virtual_bets").upsert(clean_records, on_conflict="bet_id").execute()
        except Exception as e:
            print(f"⚠️ [Supabase] 장부 저장 실패: {e}")

    df = pd.DataFrame(records, columns=LEDGER_COLUMNS)
    df.to_csv(LEDGER_FILENAME, index=False, encoding="utf-8-sig")


def sync_web_data_to_supabase(analysis_rows: list[dict], schedule_rows: list[dict]):
    if not _sb_client:
        return
    try:
        if analysis_rows:
            _sb_client.table("pickster_match_analyses").upsert(analysis_rows, on_conflict="match_id").execute()
        if schedule_rows:
            sched_payload = [
                {
                    "schedule_id": r["schedule_id"],
                    "kickoff_iso": r["kickoff_iso"],
                    "kickoff_kst": format_kst_datetime(r["dt_kst"]),
                    "sport_tag": r["sport_tag"],
                    "matchup": r["matchup"],
                    "badge": r["badge"],
                }
                for r in schedule_rows if "schedule_id" in r
            ]
            if sched_payload:
                _sb_client.table("pickster_schedules").upsert(sched_payload, on_conflict="schedule_id").execute()
        print(f"☁️ [Supabase] 웹사이트 데이터 동기화 완료 (분석 {len(analysis_rows)}건 / 일정 {len(schedule_rows)}건)")
    except Exception as e:
        print(f"⚠️ [Supabase] 웹 데이터 저장 실패: {e}")


def settle_pending_bets(records: list[dict], settled_lookup: dict, now_kst: pd.Timestamp) -> list[str]:
    newly_settled_msgs = []
    now_str = now_kst.strftime("%Y-%m-%d %H:%M")

    for r in records:
        if r["status"] != "PENDING":
            continue
        res = settled_lookup.get(r["bet_id"])
        if not res:
            continue

        stake, odd = int(r["stake"]), float(r["odd"])

        if res["status"] == "CANCELLED":
            r["status"], r["score"], r["payout"], r["profit"], r["settled_at_kst"] = "REFUND", "취소", stake, 0, now_str
            newly_settled_msgs.append(f"  ↩️ [취소환불] [{r['sport']}] {r['match']} | {r['pick_label']} -> ±0원")
            continue

        r["score"], r["settled_at_kst"] = res["score"], now_str

        if r["pick_side"] == res["winner"]:
            payout = int(round(stake * odd))
            profit = payout - stake
            r["status"], r["payout"], r["profit"] = "WON", payout, profit
            newly_settled_msgs.append(
                f"  ✅ [적중] [{r['sport']}] {r['match']} ({res['score']}) | {r['pick_label']} @{odd:.2f} -> {profit:+,d}원"
            )
        else:
            r["status"], r["payout"], r["profit"] = "LOST", 0, -stake
            newly_settled_msgs.append(
                f"  ❌ [미적] [{r['sport']}] {r['match']} ({res['score']}) | {r['pick_label']} @{odd:.2f} -> {-stake:+,d}원"
            )

    return newly_settled_msgs


def place_new_virtual_bets(records: list[dict], candidates: list[dict], now_kst: pd.Timestamp) -> list[str]:
    existing_ids = {r["bet_id"] for r in records}
    now_str = now_kst.strftime("%Y-%m-%d %H:%M")
    newly_placed_msgs = []

    for c in candidates:
        if c["bet_id"] in existing_ids or c["tier"] < BET_MIN_TIER or not c.get("odd"):
            continue
        if BET_ONLY_POSITIVE_EV and (c.get("ev") is None or c["ev"] <= 0):
            continue

        ev_val = round(c["ev"], 1) if c.get("ev") is not None else None
        records.append({
            "bet_id": c["bet_id"],
            "placed_at_kst": now_str,
            "kickoff_kst": c["time"],
            "sport": c["sport"],
            "match": c["match"],
            "pick_side": c["pick_side"],
            "pick_label": c["pick"],
            "tier": int(c["tier"]),
            "prob_pct": round(c["prob"], 1),
            "odd": round(float(c["odd"]), 2),
            "ev_pct": ev_val,
            "stake": BET_STAKE_KRW,
            "status": "PENDING",
            "score": "",
            "payout": 0,
            "profit": 0,
            "settled_at_kst": "",
        })
        existing_ids.add(c["bet_id"])
        ev_str = f" | EV {ev_val:+.1f}%" if ev_val is not None else ""
        newly_placed_msgs.append(
            f"  🎫 [{c['sport']}] {c['match']} -> {c['pick']} @{c['odd']:.2f}{ev_str} ({BET_STAKE_KRW:,d}원)"
        )

    return newly_placed_msgs


def calc_stats_summary(settled_rows: list[dict], label: str) -> str:
    if not settled_rows:
        return f"  • {label}: 정산 완료 경기 없음"
    wins = sum(1 for r in settled_rows if r["status"] == "WON")
    losses = sum(1 for r in settled_rows if r["status"] == "LOST")
    total_games = wins + losses
    hit_rate = (wins / total_games * 100) if total_games > 0 else 0.0
    total_stake = sum(int(r["stake"]) for r in settled_rows if r["status"] in ("WON", "LOST"))
    total_payout = sum(int(r["payout"]) for r in settled_rows if r["status"] in ("WON", "LOST"))
    net_profit = total_payout - total_stake
    roi = (net_profit / total_stake * 100) if total_stake > 0 else 0.0
    return (
        f"  • {label}: {total_games}전 {wins}승 {losses}패 (적중률 {hit_rate:.1f}%)"
        f" | 배팅 {total_stake:,d}원 -> 환급 {total_payout:,d}원"
        f" | 순수익 {net_profit:+,d}원 (ROI {roi:+.1f}%)"
    )


def build_virtual_wallet_report(records: list[dict], settled_msgs: list[str], placed_msgs: list[str]) -> str:
    lines = [f"\n💵 [가상 배팅 시뮬레이터 현황 (1경기 {BET_STAKE_KRW:,d}원 기준)]", "=" * 52]

    if settled_msgs:
        lines.append(f"🔔 방금 정산 완료된 경기 ({len(settled_msgs)}건):")
        lines.extend(settled_msgs)
    else:
        lines.append("🔔 방금 새로 정산된 경기가 없습니다.")

    if placed_msgs:
        lines.append(f"\n🆕 신규 가상 배팅 기록 ({len(placed_msgs)}건):")
        lines.extend(placed_msgs)
    else:
        lines.append("\n🆕 새로 추가된 가상 배팅이 없습니다.")

    settled = [r for r in records if r["status"] in ("WON", "LOST")]
    pending = [r for r in records if r["status"] == "PENDING"]
    tier3_settled = [r for r in settled if int(r["tier"]) == 3]
    plus_ev_settled = [r for r in settled if r.get("ev_pct") is not None and not pd.isna(r["ev_pct"]) and float(r["ev_pct"]) > 0]

    lines.append("\n📊 누적 가상 계좌 성적표:")
    lines.append(calc_stats_summary(settled, "전체 추천 픽"))
    lines.append(calc_stats_summary(tier3_settled, "⭐⭐⭐ 주력 픽만"))
    lines.append(calc_stats_summary(plus_ev_settled, "💎 +EV 꿀픽만"))
    lines.append(f"  • 결과 대기중(PENDING): {len(pending)}건 ({sum(int(r['stake']) for r in pending):,d}원)")
    lines.append("=" * 52)
    return "\n".join(lines)


# =========================================================
# 📨 PART 4. 텔레그램 & 구글 블로거 자동 발송 모듈
# =========================================================
def split_message_chunks(text: str, max_len: int = 3800) -> list[str]:
    if len(text) <= max_len:
        return [text]

    chunks, current, current_len = [], [], 0
    for line in text.splitlines():
        line_len = len(line) + 1
        if current_len + line_len > max_len and current:
            chunks.append("\n".join(current))
            current, current_len = [line], line_len
        elif line_len > max_len:
            if current:
                chunks.append("\n".join(current))
                current, current_len = [], 0
            for i in range(0, len(line), max_len):
                chunks.append(line[i:i + max_len])
        else:
            current.append(line)
            current_len += line_len

    if current:
        chunks.append("\n".join(current))
    return chunks


def send_telegram_channel(blocks: list[str]):
    if not is_telegram_enabled():
        print("\nℹ️ 텔레그램 봇 토큰/채널 아이디가 설정되지 않아 채널 발송은 건너뜁니다.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    all_chunks = []
    for blk in blocks:
        if blk and blk.strip():
            all_chunks.extend(split_message_chunks(blk.strip(), max_len=3800))

    print(f"\n📨 텔레그램 채널({TELEGRAM_CHANNEL_ID})로 총 {len(all_chunks)}개 메시지 전송 시작...")
    sent_count = 0

    for idx, chunk in enumerate(all_chunks, 1):
        payload = {
            "chat_id": TELEGRAM_CHANNEL_ID,
            "text": chunk,
            "disable_web_page_preview": True,
        }
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", 5)
                time.sleep(retry_after + 1)
                resp = requests.post(url, json=payload, timeout=15)

            if not resp.ok:
                print(f"❌ 텔레그램 전송 실패 ({idx}/{len(all_chunks)}): [{resp.status_code}] {resp.text}")
                break

            sent_count += 1
            time.sleep(0.6)
        except Exception as e:
            print(f"❌ 텔레그램 전송 중 오류 ({idx}/{len(all_chunks)}): {e}")
            break

    if sent_count == len(all_chunks):
        print(f"✅ 텔레그램 채널({TELEGRAM_CHANNEL_ID}) 발송 완료! ({sent_count}/{len(all_chunks)}건)")


def build_blogger_html(now_kst: pd.Timestamp, top_picks: list, analyses: list, schedule_rows: list, ledger_records: list) -> tuple[str, str]:
    end_kst = now_kst + pd.Timedelta(days=2)
    date_range_str = f"{now_kst.strftime('%m/%d')} ~ {end_kst.strftime('%m/%d')}"
    ampm = "오전" if now_kst.hour < 12 else "오후"
    post_title = f"🤖 AI 스포츠 픽스터 통합 리포트 ({date_range_str} {ampm})"
    esc = html_lib.escape

    settled = [r for r in ledger_records if r["status"] in ("WON", "LOST")]
    wins = sum(1 for r in settled if r["status"] == "WON")
    losses = sum(1 for r in settled if r["status"] == "LOST")
    total_games = wins + losses
    hit_rate = (wins / total_games * 100) if total_games else 0.0
    net_profit = sum(int(r["profit"]) for r in settled)
    total_stake = sum(int(r["stake"]) for r in settled)
    roi = (net_profit / total_stake * 100) if total_stake else 0.0

    # 1. BEST PICKS 테이블 행
    sorted_picks = sorted(top_picks, key=lambda x: (x["tier"], x["prob"]), reverse=True)[:10]
    pick_rows_html = ""
    for idx, p in enumerate(sorted_picks, 1):
        tier_badge = (
            '<span style="background:#fef3c7;color:#b45309;padding:3px 8px;border-radius:6px;font-size:12px;font-weight:700;">⭐⭐⭐ 주력</span>'
            if p["tier"] == 3
            else '<span style="background:#e0e7ff;color:#3730a3;padding:3px 8px;border-radius:6px;font-size:12px;font-weight:700;">⭐⭐ 일반</span>'
        )
        odd_str = f"{p['odd']:.2f}" if p.get("odd") else "-"
        ev_badge = ""
        if p.get("ev") is not None:
            ev_bg = "#d1fae5;color:#065f46" if p["ev"] >= 5 else "#f1f5f9;color:#334155"
            gem = " 💎" if p["ev"] >= 5 else ""
            ev_badge = f' <span style="background:{ev_bg};padding:3px 7px;border-radius:6px;font-size:12px;font-weight:700;">EV {p["ev"]:+.1f}%{gem}</span>'

        pick_rows_html += f"""
        <tr style="border-bottom:1px solid #e2e8f0;">
          <td style="padding:12px 8px;text-align:center;color:#64748b;font-weight:600;">{idx}</td>
          <td style="padding:12px 8px;">{esc(p['sport'])}</td>
          <td style="padding:12px 8px;font-weight:600;color:#0f172a;">{esc(p['match'])}</td>
          <td style="padding:12px 8px;"><b>{esc(p['pick'])}</b> ({p['prob']:.1f}%) {tier_badge}</td>
          <td style="padding:12px 8px;">{odd_str}{ev_badge}</td>
          <td style="padding:12px 8px;color:#475569;font-size:13px;">{esc(p['time'])}</td>
        </tr>"""

    if not pick_rows_html:
        pick_rows_html = '<tr><td colspan="6" style="padding:18px;text-align:center;color:#64748b;">현재 추천 기준에 부합하는 경기가 없습니다.</td></tr>'

    # 2. 상세 분석 카드
    analysis_cards_html = ""
    for a in analyses[:16]:
        probs_txt = (
            f"홈 {a['home_prob']:.1f}% | 무 {a['draw_prob']:.1f}% | 원정 {a['away_prob']:.1f}%"
            if a.get("draw_prob") is not None
            else f"원정 {a['away_prob']:.1f}% | 홈 {a['home_prob']:.1f}%"
        )
        analysis_cards_html += f"""
        <div style="border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin-bottom:14px;background:#ffffff;">
          <div style="display:flex;justify-content:space-between;font-size:12px;color:#64748b;margin-bottom:6px;">
            <span style="font-weight:700;color:#1d4ed8;">{esc(a['sport'])}</span>
            <span>{esc(a['kickoff_kst'])}</span>
          </div>
          <div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:4px;">
            {esc(a['home_team'])} (홈) vs {esc(a['away_team'])} (원정)
          </div>
          <div style="font-size:13px;color:#1e40af;margin-bottom:6px;">{esc(a['pred_summary'])}</div>
          <div style="font-size:13px;color:#334155;margin-bottom:4px;">📈 승률: {probs_txt}</div>
          <div style="font-size:13px;color:#475569;margin-bottom:8px;">🔥 {esc(a['extra_info'])}</div>
          <div style="background:#f8fafc;border-radius:8px;padding:10px;font-size:12px;color:#475569;white-space:pre-line;margin-bottom:8px;">{esc(a['reasons'])}</div>
          <div style="font-size:13px;font-weight:700;color:#059669;">🎯 AI 추천: {esc(a['pick_label'])} · {esc(a['conf_label'])}</div>
        </div>"""

    if not analysis_cards_html:
        analysis_cards_html = '<p style="color:#64748b;">예정된 분석 경기가 없습니다.</p>'

    html_body = f"""
<div style="max-width:860px;margin:0 auto;font-family:'Pretendard','Apple SD Gothic Neo','Malgun Gothic',sans-serif;line-height:1.6;color:#1e293b;">
  <div style="background:linear-gradient(135deg,#0f172a 0%,#1e3a8a 100%);color:#ffffff;padding:24px 26px;border-radius:14px;margin-bottom:18px;">
    <div style="font-size:22px;font-weight:800;margin-bottom:6px;">🤖 AI 스포츠 픽스터 통합 리포트 ({date_range_str})</div>
    <div style="font-size:13px;color:#cbd5e1;">생성 시각: {esc(format_kst_datetime(now_kst))} | 대상 종목: NBA · EPL · 라리가 · 분데스리가 · 세리에 A · 챔피언스리그</div>
  </div>

  <div style="background:#f0f7ff;border:1px solid #bfdbfe;border-radius:12px;padding:18px 20px;margin-bottom:20px;">
    <div style="font-size:15px;font-weight:700;color:#1e3a8a;margin-bottom:6px;">📊 실시간 AI 대시보드 &amp; 커뮤니티 오픈!</div>
    <div style="font-size:14px;color:#334155;margin-bottom:14px;">
      실시간 경기 일정, 누적 가상배팅 성적표, 회원 커뮤니티 게시판은 웹사이트에서 바로 확인하실 수 있습니다.
    </div>
    <a href="{esc(WEB_SITE_URL)}" target="_blank" style="display:inline-block;background:#1d4ed8;color:#ffffff;text-decoration:none;padding:10px 16px;border-radius:8px;font-size:13px;font-weight:700;margin-right:8px;margin-bottom:6px;">🌐 AI 픽스터 웹사이트 바로가기</a>
    <a href="{esc(TELEGRAM_CHANNEL_URL)}" target="_blank" style="display:inline-block;background:#0284c7;color:#ffffff;text-decoration:none;padding:10px 16px;border-radius:8px;font-size:13px;font-weight:700;margin-bottom:6px;">✈️ 텔레그램 채널 바로가기</a>
  </div>

  <p style="font-size:14px;color:#334155;margin-bottom:22px;">
    다가오는 주요 NBA 및 유럽 5대 프로축구 리그 경기의 AI 통계 모델 예측 리포트입니다. 핵심 주력 픽 TOP 10과 누적 가상배팅 성적, 상세 기대 득점 및 해외 배당 기댓값(EV)을 확인해 보세요.
  </p>

  <div style="border-left:5px solid #1d4ed8;padding-left:12px;font-size:18px;font-weight:800;color:#0f172a;margin:24px 0 12px;">
    🏆 오늘의 AI 픽스터 핵심 추천 요약 (BEST PICKS)
  </div>
  <div style="overflow-x:auto;border:1px solid #e2e8f0;border-radius:12px;background:#ffffff;margin-bottom:26px;">
    <table style="width:100%;border-collapse:collapse;font-size:13px;min-width:620px;">
      <thead>
        <tr style="background:#f8fafc;border-bottom:2px solid #e2e8f0;color:#475569;text-align:left;">
          <th style="padding:12px 8px;text-align:center;">순위</th>
          <th style="padding:12px 8px;">종목/리그</th>
          <th style="padding:12px 8px;">매치업</th>
          <th style="padding:12px 8px;">AI 추천 픽 (확률)</th>
          <th style="padding:12px 8px;">배당 / 기댓값(EV)</th>
          <th style="padding:12px 8px;">경기 일시 (KST)</th>
        </tr>
      </thead>
      <tbody>{pick_rows_html}</tbody>
    </table>
  </div>

  <div style="border-left:5px solid #1d4ed8;padding-left:12px;font-size:18px;font-weight:800;color:#0f172a;margin:24px 0 12px;">
    💵 AI 가상 배팅 누적 성적표 (1만원 기준)
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:16px;font-size:14px;margin-bottom:26px;">
    <b>누적 전적:</b> {total_games}전 {wins}승 {losses}패 (적중률 {hit_rate:.1f}%) &nbsp;|&nbsp;
    <b>순수익:</b> <span style="color:{'#059669' if net_profit >= 0 else '#e11d48'};font-weight:700;">{net_profit:+,d}원</span> (ROI {roi:+.1f}%)
  </div>

  <div style="border-left:5px solid #1d4ed8;padding-left:12px;font-size:18px;font-weight:800;color:#0f172a;margin:24px 0 12px;">
    🔍 경기별 AI 상세 분석
  </div>
  {analysis_cards_html}

  <p style="font-size:12px;color:#94a3b8;margin-top:28px;border-top:1px solid #e2e8f0;padding-top:12px;">
    ※ 본 게시물은 통계 모델 기반 자동 분석 리포트이며, 가상 배팅 시뮬레이션 결과는 실제 수익을 보장하지 않습니다.
  </p>
</div>
"""
    return post_title, html_body


def publish_to_blogger(title: str, html_content: str, labels: list[str] | None = None):
    if not is_blogger_enabled():
        print("\nℹ️ [블로거] API 설정이 없어 블로그 자동 발행은 건너뜁니다.")
        return

    try:
        token_resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": BLOGGER_CLIENT_ID,
                "client_secret": BLOGGER_CLIENT_SECRET,
                "refresh_token": BLOGGER_REFRESH_TOKEN,
                "grant_type": "refresh_token",
            },
            timeout=20,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        post_url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/"
        payload = {
            "kind": "blogger#post",
            "blog": {"id": BLOGGER_BLOG_ID},
            "title": title,
            "content": html_content,
            "labels": labels or ["NBA", "유럽축구", "AI픽스터"],
        }
        res = requests.post(
            post_url,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=payload,
            timeout=25,
        )
        res.raise_for_status()
        print(f"📝 [블로거] 자동 포스팅 완료! -> {res.json().get('url', '')}")
    except Exception as e:
        print(f"⚠️ [블로거] 포스팅 실패: {e}")


# =========================================================
# 🏆 PART 5. 통합 출력 및 실행 루프
# =========================================================
def build_unified_schedule_text(schedule_rows: list) -> str:
    lines = [f"\n📅 [향후 {SCHEDULE_DAYS}일간 통합 경기 일정 (KST)]", "=" * 52]
    if not schedule_rows:
        lines.append("해당 기간에 예정된 경기가 없습니다.")
        lines.append("=" * 52)
        return "\n".join(lines)

    df = pd.DataFrame(schedule_rows).sort_values("dt_kst")
    df["date_group"] = df["dt_kst"].apply(lambda x: f"{x.strftime('%Y-%m-%d')} ({WEEKDAYS_KR[x.weekday()]})")

    for date_label, group in df.groupby("date_group", sort=False):
        lines.append(f"\n🗓️  {date_label}")
        lines.append("-" * 52)
        for _, r in group.iterrows():
            lines.append(f"  • {r['dt_kst'].strftime('%H:%M')} | [{r['sport_tag']}] {r['matchup']} | [{r['badge']}]")
    lines.append("=" * 52)
    return "\n".join(lines)


def build_top_picks_text(top_picks: list) -> str:
    lines = ["\n🏆 [오늘의 AI 픽스터 BEST PICKS 요약]", "=" * 52]
    if not top_picks:
        lines.append("추천 기준(일반/주력 등급)에 부합하는 경기가 아직 없습니다.")
        lines.append("=" * 52)
        return "\n".join(lines)

    sorted_picks = sorted(top_picks, key=lambda x: (x["tier"], x["prob"]), reverse=True)
    for idx, p in enumerate(sorted_picks[:10], 1):
        odd_str = f" | @{p['odd']:.2f}" if p.get("odd") else ""
        ev_str = f" (EV {p['ev']:+.1f}%{'💎' if p['ev'] >= 5.0 else ''})" if p.get("ev") is not None else ""
        lines.append(f"  {idx:2d}. [{p['sport']}] {p['match']} 👉 {p['pick']} ({p['prob']:.1f}%{odd_str}{ev_str}) | {p['conf']}")
        lines.append(f"      └ 🕒 {p['time']}")
    lines.append("=" * 52)
    return "\n".join(lines)


def execute_bot(run_nba: bool, run_soccer: bool):
    global _rate_limit_wait_until, _odds_remaining_credits
    _rate_limit_wait_until = 0.0
    _odds_remaining_credits = None

    now_kst = pd.Timestamp.now(tz="Asia/Seoul")
    all_schedule_rows, nba_reports, soccer_reports, all_top_picks, all_analyses = [], [], [], [], []
    all_settled_lookup = {}

    if run_nba:
        try:
            s_rows, reps, picks, nba_settled, nba_analyses = run_nba_module(now_kst)
            all_schedule_rows.extend(s_rows)
            nba_reports.extend(reps)
            all_top_picks.extend(picks)
            all_settled_lookup.update(nba_settled)
            all_analyses.extend(nba_analyses)
        except Exception as e:
            print(f"❌ [NBA] 데이터 처리 중 오류 발생: {e}")

    if run_soccer:
        try:
            s_rows, reps, picks, soc_settled, soc_analyses = run_soccer_module(now_kst)
            all_schedule_rows.extend(s_rows)
            soccer_reports.extend(reps)
            all_top_picks.extend(picks)
            all_settled_lookup.update(soc_settled)
            all_analyses.extend(soc_analyses)
        except Exception as e:
            print(f"❌ [축구] 데이터 처리 중 오류 발생: {e}")

    ledger_records = load_bet_ledger()
    settled_msgs = settle_pending_bets(ledger_records, all_settled_lookup, now_kst)
    placed_msgs = place_new_virtual_bets(ledger_records, all_top_picks, now_kst)
    save_bet_ledger(ledger_records)
    sync_web_data_to_supabase(all_analyses, all_schedule_rows)

    header_txt = f"🤖 AI 스포츠 픽스터 통합 리포트\n🕒 생성 시각: {format_kst_datetime(now_kst)}"
    wallet_txt = build_virtual_wallet_report(ledger_records, settled_msgs, placed_msgs)
    best_txt = build_top_picks_text(all_top_picks)
    schedule_txt = build_unified_schedule_text(all_schedule_rows)

    nba_block = ""
    if run_nba:
        nba_body = "\n".join(nba_reports) if nba_reports else "해당 시간 내 예정된 NBA 경기가 없습니다."
        nba_block = f"🏀 [NBA 상세 분석 (향후 {NBA_ANALYSIS_HOURS}시간 이내: {len(nba_reports)}경기)]\n{nba_body}"

    soccer_block = ""
    if run_soccer:
        soc_body = "\n".join(soccer_reports) if soccer_reports else "해당 시간 내 예정된 유럽축구 경기가 없습니다."
        soccer_block = f"⚽ [유럽축구 상세 분석 (향후 {SOCCER_ANALYSIS_HOURS}시간 이내: {len(soccer_reports)}경기)]\n{soc_body}"

    footer_lines = []
    if _odds_remaining_credits is not None:
        footer_lines.append(f"💳 [배당 API] 이번 달 남은 무료 크레딧: {_odds_remaining_credits} / 500")
    footer_lines.append(
        "※ 본 분석은 통계 모델 기반 참고 자료이며, 가상 배팅 시뮬레이션 결과는 실제 수익을 보장하지 않습니다."
    )
    footer_txt = "\n".join(footer_lines)

    full_sections = [header_txt, wallet_txt, best_txt, schedule_txt]
    if nba_block:
        full_sections.append("\n" + nba_block)
    if soccer_block:
        full_sections.append("\n" + soccer_block)
    full_sections.append("\n" + footer_txt)

    full_text = "\n".join(full_sections)
    print(full_text)

    if SAVE_TO_FILE:
        with open(REPORT_FILENAME, "w", encoding="utf-8") as f:
            f.write(full_text)
        print(f"\n💾 리포트 저장 완료: '{REPORT_FILENAME}' | 장부: '{LEDGER_FILENAME}'")

    if "--no-tg" not in sys.argv:
        tg_blocks = [f"{header_txt}\n{wallet_txt}\n{best_txt}", schedule_txt]
        if not TELEGRAM_SUMMARY_ONLY:
            if nba_block:
                tg_blocks.append(nba_block)
            if soccer_block:
                tg_blocks.append(soccer_block)
        tg_blocks.append(footer_txt)
        send_telegram_channel(tg_blocks)

    if "--no-blog" not in sys.argv and all_analyses:
        blog_title, blog_html = build_blogger_html(now_kst, all_top_picks, all_analyses, all_schedule_rows, ledger_records)
        publish_to_blogger(blog_title, blog_html)


def run_24h_auto_loop():
    print(f"🔁 {AUTO_INTERVAL_HOURS}시간 자동 반복 모드를 시작합니다. (중지하려면 Ctrl+C 를 누르세요)")
    cycle_num = 1
    while True:
        cycle_start = time.time()
        print(f"\n==================== [자동 실행 #{cycle_num}] ====================")
        try:
            execute_bot(run_nba=True, run_soccer=True)
        except Exception as e:
            print(f"❌ 자동 실행 #{cycle_num} 중 오류 발생: {e}")

        next_run_ts = cycle_start + AUTO_INTERVAL_HOURS * 3600
        next_run_kst = pd.Timestamp.fromtimestamp(next_run_ts, tz="Asia/Seoul")
        print(f"\n😴 다음 자동 실행 예정 시각: {format_kst_datetime(next_run_kst)} (종료: Ctrl+C)")

        try:
            while time.time() < next_run_ts:
                time.sleep(min(30, max(1, next_run_ts - time.time())))
        except KeyboardInterrupt:
            print("\n🛑 사용자 요청으로 24시간 자동 실행을 종료합니다.")
            break

        cycle_num += 1


def main():
    if "--loop" in sys.argv:
        run_24h_auto_loop()
        return

    if "--auto" in sys.argv:
        execute_bot(run_nba=True, run_soccer=True)
        return

    print("==================================================")
    print("🤖 AI 스포츠 픽스터 통합 봇 (텔레그램 + 웹 + 블로거)")
    print("==================================================")
    print("1. 1회 전체 실행 (NBA + 유럽축구)")
    print("2. 🏀 NBA만 보기")
    print("3. ⚽ 유럽축구만 보기")
    print(f"4. 🔁 {AUTO_INTERVAL_HOURS}시간마다 자동 전체 실행 (무한 반복)")
    try:
        choice = input("원하는 번호를 입력하세요 (엔터 시 1회 전체 실행): ").strip() or "1"
    except EOFError:
        choice = "1"

    if choice == "4":
        run_24h_auto_loop()
    else:
        run_nba = choice in ("1", "2")
        run_soccer = choice in ("1", "3")
        if not run_nba and not run_soccer:
            run_nba = run_soccer = True
        execute_bot(run_nba=run_nba, run_soccer=run_soccer)


if __name__ == "__main__":
    main()
