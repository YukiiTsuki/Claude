#!/usr/bin/env python3
"""Manchester City 賽後通知：比分、進球者與時間，加上指定球員（預設 Rúben Dias）的個人數據。

資料來源：API-Football (https://www.api-football.com/)
推送方式：ntfy (https://ntfy.sh/) → Android 手機

需要的環境變數：
  API_FOOTBALL_KEY  API-Football 的 API key
  NTFY_TOPIC        你在 ntfy App 訂閱的主題名稱（請取一個別人猜不到的名字）
選用：
  NTFY_SERVER       預設 https://ntfy.sh
  DRY_RUN=1         只印出通知內容，不推送也不寫入狀態
"""

from __future__ import annotations

import json
import os
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ===== 設定 =====
TEAM_ID = 50  # Manchester City
LEAGUES = {39: "英超", 2: "歐冠"}  # Premier League, UEFA Champions League
PLAYER_ID = None  # 若已知 API-Football 的球員 ID 可填入；否則用名字比對
PLAYER_NAME_KEYWORDS = ["dias"]  # 名字比對（不分大小寫、忽略重音符號）
PLAYER_DISPLAY_NAME = "Rúben Dias"

FINISHED = {"FT", "AET", "PEN"}
# 終場後如果評分還沒出來，最多等這麼久再直接推送（沒有評分也推）
RATING_WAIT = timedelta(hours=2)

API_BASE = "https://v3.football.api-sports.io"
STATE_FILE = Path(__file__).parent / "state" / "notified.json"


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


class ApiError(RuntimeError):
    pass


def api_get(path: str, params: dict) -> list:
    key = os.environ.get("API_FOOTBALL_KEY")
    if not key:
        raise ApiError("缺少 API_FOOTBALL_KEY")
    query = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(f"{API_BASE}/{path}?{query}", headers={"x-apisports-key": key})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    errors = data.get("errors")
    if errors:  # API-Football 在錯誤時回傳 dict 或非空 list
        raise ApiError(f"API-Football 回傳錯誤：{errors}")
    return data.get("response", [])


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"notified": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def minute_str(t: dict) -> str:
    m = f"{t.get('elapsed')}"
    if t.get("extra"):
        m += f"+{t['extra']}"
    return m + "'"


def format_goals(fixture: dict) -> list[str]:
    """回傳每隊一行的進球列表。"""
    home_id = fixture["teams"]["home"]["id"]
    by_team: dict[int, list[str]] = {fixture["teams"]["home"]["id"]: [], fixture["teams"]["away"]["id"]: []}
    for ev in fixture.get("events") or []:
        if ev.get("type") != "Goal":
            continue
        detail = ev.get("detail") or ""
        comments = (ev.get("comments") or "").lower()
        if detail == "Missed Penalty" or "shootout" in comments:
            continue
        name = (ev.get("player") or {}).get("name") or "?"
        tag = ""
        if detail == "Penalty":
            tag = "（PK）"
        elif detail == "Own Goal":
            tag = "（烏龍）"
        team_id = (ev.get("team") or {}).get("id")
        by_team.setdefault(team_id, []).append(f"{name} {minute_str(ev.get('time') or {})}{tag}")

    lines = []
    for side in ("home", "away"):
        team = fixture["teams"][side]
        scorers = by_team.get(team["id"]) or []
        if scorers:
            lines.append(f"{team['name']}：" + "、".join(scorers))
    return lines


def find_player(fixture: dict) -> dict | None:
    for team_block in fixture.get("players") or []:
        if (team_block.get("team") or {}).get("id") != TEAM_ID:
            continue
        for p in team_block.get("players") or []:
            info = p.get("player") or {}
            if PLAYER_ID is not None and info.get("id") == PLAYER_ID:
                return p
            name = strip_accents(info.get("name") or "")
            if PLAYER_ID is None and any(k in name for k in PLAYER_NAME_KEYWORDS):
                return p
    return None


def format_player(p: dict | None) -> tuple[str, bool]:
    """回傳 (文字, 評分是否已出來)。"""
    if p is None:
        return f"👤 {PLAYER_DISPLAY_NAME}：未進入大名單", True
    st = (p.get("statistics") or [{}])[0]
    games = st.get("games") or {}
    minutes = games.get("minutes")
    if not minutes:
        return f"👤 {PLAYER_DISPLAY_NAME}：未上場", True
    rating = games.get("rating")
    goals = (st.get("goals") or {}).get("total") or 0
    assists = (st.get("goals") or {}).get("assists") or 0
    cards = st.get("cards") or {}
    yellow = cards.get("yellow") or 0
    red = cards.get("red") or 0
    sub = "（替補）" if games.get("substitute") else "（先發）"
    rating_txt = f"{float(rating):.1f}" if rating else "尚未公布"
    card_txt = "🟨" * yellow + "🟥" * red or "無"
    text = (
        f"⭐ {PLAYER_DISPLAY_NAME}：評分 {rating_txt}\n"
        f"⚽ 進球 {goals}｜🅰️ 助攻 {assists}｜牌 {card_txt}｜⏱️ {minutes}'{sub}"
    )
    return text, bool(rating)


def build_message(fixture: dict) -> tuple[str, str, bool]:
    f = fixture["fixture"]
    league = fixture["league"]
    home, away = fixture["teams"]["home"], fixture["teams"]["away"]
    goals = fixture["goals"]
    status = f["status"]["short"]

    score = f"{home['name']} {goals['home']} - {goals['away']} {away['name']}"
    if status == "PEN":
        pen = (fixture.get("score") or {}).get("penalty") or {}
        score += f"（PK {pen.get('home')}-{pen.get('away')}）"
    elif status == "AET":
        score += "（延長賽）"

    title = f"{LEAGUES.get(league['id'], league['name'])}｜{score}"
    parts = [f"🏆 {league['name']}｜{league.get('round', '')}"]
    goal_lines = format_goals(fixture)
    parts.append("🥅 " + "\n🥅 ".join(goal_lines) if goal_lines else "🥅 無進球")
    player_text, rating_ready = format_player(find_player(fixture))
    parts.append(player_text)
    return title, "\n".join(parts), rating_ready


def push(title: str, message: str) -> None:
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        raise RuntimeError("缺少 NTFY_TOPIC")
    body = json.dumps({"topic": topic, "title": title, "message": message, "tags": ["soccer"]}).encode()
    req = urllib.request.Request(server, data=body, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()


def candidate_dates(now: datetime) -> list[str]:
    dates = [now.date()]
    # 凌晨時也檢查前一天，避免跨日的比賽漏掉
    if now.hour < 4:
        dates.append((now - timedelta(days=1)).date())
    return [d.isoformat() for d in dates]


def main() -> int:
    dry_run = os.environ.get("DRY_RUN") == "1"
    now = datetime.now(timezone.utc)
    state = load_state()
    notified = set(state.get("notified", []))
    changed = False

    for date in candidate_dates(now):
        for fx in api_get("fixtures", {"team": TEAM_ID, "date": date}):
            fid = fx["fixture"]["id"]
            if fx["league"]["id"] not in LEAGUES or fid in notified:
                continue
            if fx["fixture"]["status"]["short"] not in FINISHED:
                continue
            # 抓完整比賽資料（含事件、球員數據），只花 1 次請求
            detail = api_get("fixtures", {"id": fid})
            if not detail:
                continue
            title, message, rating_ready = build_message(detail[0])
            kickoff = datetime.fromtimestamp(fx["fixture"]["timestamp"], tz=timezone.utc)
            # 比賽約 2 小時；評分還沒出來就等下一輪再試
            if not rating_ready and now < kickoff + timedelta(hours=2) + RATING_WAIT:
                print(f"[{fid}] 評分尚未公布，稍後再試")
                continue
            print(f"--- {title}\n{message}\n")
            if not dry_run:
                push(title, message)
                notified.add(fid)
                changed = True
            time.sleep(1)

    if changed:
        state["notified"] = sorted(notified)
        save_state(state)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ApiError, urllib.error.URLError) as e:
        print(f"錯誤：{e}", file=sys.stderr)
        sys.exit(1)
