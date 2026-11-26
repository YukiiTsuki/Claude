#!/usr/bin/env python3
"""Manchester City 賽後通知：比分、進球者與時間，加上指定球員（預設 Rúben Dias）的個人數據。

資料來源：ESPN 公開 API（免費、不需要 API key，沒有球員評分）
推送方式：ntfy (https://ntfy.sh/) → Android 手機

需要的環境變數：
  NTFY_TOPIC        你在 ntfy App 訂閱的主題名稱（請取一個別人猜不到的名字）
選用：
  NTFY_SERVER       預設 https://ntfy.sh
  DRY_RUN=1         只印出通知內容，不推送也不寫入狀態
  TEST_LATEST=1     測試模式：拿曼城最近一場已完賽的比賽產生通知並印出（不推送）
  TEST_PUSH=1       測試模式下也推送到手機（標題加上【測試】）
  TEST_LEAGUE       測試模式只跑指定賽事，例如 eng.1
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ===== 設定 =====
TEAM_ID = "382"  # ESPN 的 Manchester City ID
LEAGUES = {"eng.1": "英超", "uefa.champions": "歐冠"}  # ESPN 的賽事代碼
PLAYER_NAME_KEYWORDS = ["dias"]  # 名字比對（不分大小寫、忽略重音符號）
PLAYER_DISPLAY_NAME = "Rúben Dias"

API_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
STATE_FILE = Path(__file__).parent / "state" / "notified.json"


def norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "mancity-notify/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"notified": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------- 解析工具 ----------

def clock_minutes(clock: dict | None) -> int | None:
    """把 ESPN 的比賽時鐘轉成分鐘數（補時算進正規時間，例如 90'+3' → 90）。"""
    if not clock:
        return None
    disp = clock.get("displayValue") or ""
    m = re.match(r"(\d+)", disp)
    if m:
        return int(m.group(1))
    if clock.get("value") is not None:
        return int(float(clock["value"]) // 60)
    return None


def stat_value(stats: list, *names: str) -> int:
    for s in stats or []:
        if s.get("name") in names or s.get("abbreviation") in names:
            try:
                return int(float(s.get("value") or s.get("displayValue") or 0))
            except (TypeError, ValueError):
                return 0
    return 0


def status_info(comp: dict) -> tuple[bool, str]:
    """回傳 (是否已完賽, 狀態名稱)。"""
    st = ((comp.get("status") or {}).get("type") or {})
    return bool(st.get("completed")), st.get("name") or ""


# ---------- 組通知 ----------

def format_goals(comp: dict, teams: dict[str, str]) -> list[str]:
    by_team: dict[str, list[str]] = {tid: [] for tid in teams}
    for d in comp.get("details") or []:
        if not d.get("scoringPlay") or d.get("shootout"):
            continue
        athletes = d.get("athletesInvolved") or []
        name = athletes[0].get("displayName") if athletes else "?"
        tag = "（PK）" if d.get("penaltyKick") else "（烏龍）" if d.get("ownGoal") else ""
        minute = (d.get("clock") or {}).get("displayValue") or ""
        tid = str((d.get("team") or {}).get("id"))
        by_team.setdefault(tid, []).append(f"{name} {minute}{tag}")
    return [f"{teams[tid]}：" + "、".join(g) for tid, g in by_team.items() if g and tid in teams]


def find_player(summary: dict) -> dict | None:
    for r in summary.get("rosters") or []:
        if str((r.get("team") or {}).get("id")) != TEAM_ID:
            continue
        for p in r.get("roster") or []:
            name = norm((p.get("athlete") or {}).get("displayName"))
            if any(k in name for k in PLAYER_NAME_KEYWORDS):
                return p
    return None


def player_minutes(p: dict, full: int) -> int:
    subs = [clock_minutes(pl.get("clock")) for pl in (p.get("plays") or []) if pl.get("substitution")]
    subs = [s for s in subs if s is not None]
    starter = p.get("starter")
    if starter:
        return subs[0] if p.get("subbedOut") and subs else full
    if p.get("subbedIn") and subs:
        on = subs[0]
        off = subs[1] if p.get("subbedOut") and len(subs) > 1 else full
        return max(off - on, 1)
    return 0


def format_player(p: dict | None, full: int) -> str:
    if p is None:
        return f"👤 {PLAYER_DISPLAY_NAME}：未進入大名單"
    played = p.get("starter") or p.get("subbedIn")
    if not played:
        return f"👤 {PLAYER_DISPLAY_NAME}：未上場"
    stats = p.get("stats") or []
    goals = stat_value(stats, "totalGoals", "G")
    assists = stat_value(stats, "goalAssists", "A")
    yellow = stat_value(stats, "yellowCards", "YC")
    red = stat_value(stats, "redCards", "RC")
    minutes = player_minutes(p, full)
    role = "先發" if p.get("starter") else "替補"
    cards = "🟨" * yellow + "🟥" * red or "無"
    return f"👤 {PLAYER_DISPLAY_NAME}｜⚽ 進球 {goals}｜🅰️ 助攻 {assists}｜牌 {cards}｜⏱️ {minutes}'（{role}）"


def build_message(league: str, event: dict, summary: dict) -> tuple[str, str]:
    comp = event["competitions"][0]
    _, status = status_info(comp)
    home = next(c for c in comp["competitors"] if c.get("homeAway") == "home")
    away = next(c for c in comp["competitors"] if c.get("homeAway") == "away")
    teams = {str(c["team"]["id"]): c["team"].get("displayName") or c["team"].get("name") for c in (home, away)}

    score = f"{teams[str(home['team']['id'])]} {home.get('score')} - {away.get('score')} {teams[str(away['team']['id'])]}"
    if "PEN" in status:
        score += f"（PK {home.get('shootoutScore', '?')}-{away.get('shootoutScore', '?')}）"
    elif "AET" in status or "EXTRA" in status:
        score += "（延長賽）"
    full = 120 if ("AET" in status or "PEN" in status or "EXTRA" in status) else 90

    title = f"{LEAGUES.get(league, league)}｜{score}"
    goal_lines = format_goals(comp, teams)
    parts = ["🥅 " + "\n🥅 ".join(goal_lines) if goal_lines else "🥅 無進球"]
    parts.append(format_player(find_player(summary), full))
    return title, "\n".join(parts)


# ---------- 推送 ----------

def push(title: str, message: str) -> None:
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        raise RuntimeError("缺少 NTFY_TOPIC")
    body = json.dumps({"topic": topic, "title": title, "message": message, "tags": ["soccer"]}).encode()
    req = urllib.request.Request(server, data=body, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()


# ---------- 主流程 ----------

def city_events_on(league: str, date: str) -> list[dict]:
    data = get_json(f"{API_BASE}/{league}/scoreboard?dates={date}")
    out = []
    for ev in data.get("events") or []:
        comp = (ev.get("competitions") or [{}])[0]
        if any(str((c.get("team") or {}).get("id")) == TEAM_ID for c in comp.get("competitors") or []):
            out.append(ev)
    return out


def summary_of(league: str, event_id: str) -> dict:
    return get_json(f"{API_BASE}/{league}/summary?event={event_id}")


def test_latest() -> int:
    """測試模式：每個賽事各找曼城最近一場完賽的比賽，印出通知內容。"""
    only = os.environ.get("TEST_LEAGUE") or ""
    for league in LEAGUES:
        if only and only != league:
            continue
        sched = get_json(f"{API_BASE}/{league}/teams/{TEAM_ID}/schedule")
        done = sorted(
            (e for e in sched.get("events") or [] if status_info(e["competitions"][0])[0]),
            key=lambda e: e["date"],
        )
        print(f"[{league}] 已完賽：" + "、".join(f"{e['date'][:10]} {e.get('shortName', '')}" for e in done))
        if not done:
            continue
        ev = done[-1]
        # schedule 的資料比較精簡，改從 scoreboard 拿完整的進球明細
        date = ev["date"][:10].replace("-", "")
        full_ev = next((e for e in city_events_on(league, date) if e["id"] == ev["id"]), ev)
        summary = summary_of(league, ev["id"])
        p = find_player(summary)
        print(f"[{league}] event={ev['id']} date={ev['date']}")
        if p:
            debug = {k: p.get(k) for k in ("starter", "subbedIn", "subbedOut")}
            debug["stats"] = {s.get("name"): s.get("value") for s in p.get("stats") or []}
            debug["plays"] = [{k: pl.get(k) for k in ("substitution", "clock")} for pl in p.get("plays") or []]
            print("  球員原始資料：", json.dumps(debug, ensure_ascii=False))
        title, message = build_message(league, full_ev, summary)
        print(f"--- {title}\n{message}\n")
        if os.environ.get("TEST_PUSH") == "1":
            push("【測試】" + title, message)
            print("  已推送到手機")
    return 0


def main() -> int:
    if os.environ.get("TEST_LATEST") == "1":
        return test_latest()

    dry_run = os.environ.get("DRY_RUN") == "1"
    now = datetime.now(timezone.utc)
    # 同時回頭檢查前 2 天（UTC）：補推在檢查時段結束後才完場的比賽。
    # 時段之間最長空檔約 37 小時（例如週四 06:30 → 週五 20:00），
    # 只查前一天會漏掉週四清晨打到延長賽／PK 的歐冠。
    dates = [(now - timedelta(days=d)).strftime("%Y%m%d") for d in range(3)]
    state = load_state()
    notified = set(state.get("notified", []))
    changed = False

    for league in LEAGUES:
        for date in dates:
            for ev in city_events_on(league, date):
                eid = str(ev["id"])
                if eid in notified or not status_info(ev["competitions"][0])[0]:
                    continue
                title, message = build_message(league, ev, summary_of(league, eid))
                print(f"--- {title}\n{message}\n")
                if not dry_run:
                    push(title, message)
                    notified.add(eid)
                    changed = True

    if changed:
        state["notified"] = sorted(notified)
        save_state(state)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.URLError as e:
        print(f"錯誤：{e}", file=sys.stderr)
        sys.exit(1)
