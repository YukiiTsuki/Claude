#!/usr/bin/env python3
"""Build the data file for the Man City season site from the ESPN public API.

Output: mancity_site/site/data.json
  - matches:  every Man City first-team match this season, all competitions
  - league:   Premier League table (computed from every PL result) plus the
              position / points of all 20 clubs after each matchweek

No API key needed. Run: python mancity_site/fetch_data.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TEAM_ID = "382"  # ESPN id for Manchester City
COMPETITIONS = {  # ESPN league code -> display name
    "eng.1": "Premier League",
    "uefa.champions": "Champions League",
    "eng.fa": "FA Cup",
    "eng.league_cup": "Carabao Cup",
    "eng.charity": "Community Shield",
}
SITE_API = "https://site.api.espn.com/apis/site/v2/sports/soccer"
STANDINGS_API = "https://site.api.espn.com/apis/v2/sports/soccer/eng.1/standings"
OUT_FILE = Path(__file__).parent / "site" / "data.json"


def get_json(url: str) -> dict:
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "mancity-site/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except Exception as exc:  # network hiccup: back off and retry
            if attempt == 3:
                raise
            print(f"retry {url}: {exc}", file=sys.stderr)
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def team_schedule(league: str, team_id: str) -> list[dict]:
    """Past results + upcoming fixtures for one team in one competition (deduped)."""
    events: dict[str, dict] = {}
    for suffix in ("", "?fixture=true"):
        data = get_json(f"{SITE_API}/{league}/teams/{team_id}/schedule{suffix}")
        for ev in data.get("events", []):
            events[ev["id"]] = ev
    return sorted(events.values(), key=lambda e: e["date"])


def score_of(competitor: dict) -> tuple[int | None, int | None]:
    s = competitor.get("score")
    if isinstance(s, dict):
        val = s.get("value")
        pen = s.get("shootoutScore")
        return (int(val) if val is not None else None, int(pen) if pen is not None else None)
    if s not in (None, ""):
        return int(float(s)), None
    return None, None


def logo_of(team: dict) -> str:
    logos = team.get("logos") or []
    if logos:
        return logos[0].get("href", "")
    return team.get("logo", "")


def simplify_match(ev: dict, league: str) -> dict:
    comp = ev["competitions"][0]
    status = comp["status"]["type"]
    sides = {c["homeAway"]: c for c in comp["competitors"]}
    city = next(c for c in comp["competitors"] if c["id"] == TEAM_ID)
    opp = next(c for c in comp["competitors"] if c["id"] != TEAM_ID)
    state = status.get("state")  # pre / in / post
    gf, pf = score_of(city)
    ga, pa = score_of(opp)

    result = None
    if state == "post" and gf is not None and ga is not None:
        if gf > ga or (gf == ga and pf is not None and pa is not None and pf > pa):
            result = "W"
        elif gf < ga or (gf == ga and pf is not None and pa is not None and pf < pa):
            result = "L"
        else:
            result = "D"

    round_name = ev.get("seasonType", {}).get("name", "")
    if round_name.startswith("20"):  # e.g. "2026-27 English Premier League" -> not a round
        round_name = ""

    return {
        "id": ev["id"],
        "date": ev["date"],
        "competition": league,
        "competitionName": COMPETITIONS[league],
        "round": round_name,
        "home": city["homeAway"] == "home",
        "neutral": bool(comp.get("neutralSite")),
        "venue": comp.get("venue", {}).get("fullName", ""),
        "opponent": {
            "id": opp["id"],
            "name": opp["team"].get("displayName", ""),
            "short": opp["team"].get("shortDisplayName", ""),
            "abbr": opp["team"].get("abbreviation", ""),
            "logo": logo_of(opp["team"]),
        },
        "state": state,
        "statusDetail": status.get("shortDetail") or status.get("detail", ""),
        "score": {"for": gf, "against": ga, "penFor": pf, "penAgainst": pa}
        if gf is not None and state != "pre"
        else None,
        "result": result,
        "homeTeam": sides["home"]["team"].get("displayName", ""),
        "awayTeam": sides["away"]["team"].get("displayName", ""),
    }


def match_goals(league: str, event_id: str) -> list[dict]:
    """Goals of a finished match: minute, side (for/against City), scorer, assist, kind."""
    summary = get_json(f"{SITE_API}/{league}/summary?event={event_id}")
    goals = []
    for k in summary.get("keyEvents") or []:
        if not k.get("scoringPlay"):
            continue
        if (k.get("period") or {}).get("number", 0) >= 5:  # penalty shoot-out kicks
            continue
        kind_text = ((k.get("type") or {}).get("text") or "").lower()
        text = k.get("text") or ""
        people = [p["athlete"].get("displayName", "") for p in k.get("participants") or [] if p.get("athlete")]
        kind = "og" if "own goal" in kind_text else "pen" if "penalty" in kind_text else None
        assist = people[1] if len(people) > 1 and kind is None and "Assisted by" in text else None
        goals.append({
            "minute": (k.get("clock") or {}).get("displayValue", ""),
            # keyEvents credit the goal to the team that benefits (own goals included)
            "side": "for" if str((k.get("team") or {}).get("id")) == TEAM_ID else "against",
            "scorer": people[0] if people else "",
            "assist": assist,
            "kind": kind,
        })
    return goals


def build_matches() -> list[dict]:
    matches = []
    for league in COMPETITIONS:
        for ev in team_schedule(league, TEAM_ID):
            m = simplify_match(ev, league)
            if m["state"] == "post":
                try:
                    m["goals"] = match_goals(league, m["id"])
                except Exception as exc:  # goals are a nice-to-have; keep the match
                    print(f"note: no goal details for {m['id']}: {exc}", file=sys.stderr)
            matches.append(m)
    return sorted(matches, key=lambda m: m["date"])


def build_league() -> dict:
    standings = get_json(STANDINGS_API)
    group = standings["children"][0]
    entries = group["standings"]["entries"]

    teams = {}
    espn_rank = {}
    zones = {}
    for e in entries:
        t = e["team"]
        teams[t["id"]] = {
            "id": t["id"],
            "name": t.get("displayName", ""),
            "short": t.get("shortDisplayName", ""),
            "abbr": t.get("abbreviation", ""),
            "logo": logo_of(t),
        }
        stats = {s["name"]: s.get("value") for s in e.get("stats", [])}
        espn_rank[t["id"]] = int(stats.get("rank") or 0)
        note = e.get("note")
        if note:
            zones[t["id"]] = {"label": note.get("description", ""), "color": note.get("color", "")}

    # Every completed PL match, collected from all 20 clubs' schedules.
    results: dict[str, dict] = {}
    for tid in teams:
        for ev in team_schedule("eng.1", tid):
            comp = ev["competitions"][0]
            if comp["status"]["type"].get("state") != "post":
                continue
            sides = {c["homeAway"]: c for c in comp["competitors"]}
            hg, _ = score_of(sides["home"])
            ag, _ = score_of(sides["away"])
            if hg is None or ag is None:
                continue
            results[ev["id"]] = {
                "date": ev["date"],
                "home": sides["home"]["id"],
                "away": sides["away"]["id"],
                "hg": hg,
                "ag": ag,
            }

    # Each club's results in date order -> table after N games played ("matchweek N").
    per_team: dict[str, list[tuple[int, int]]] = {tid: [] for tid in teams}
    for r in sorted(results.values(), key=lambda r: r["date"]):
        if r["home"] in per_team:
            per_team[r["home"]].append((r["hg"], r["ag"]))
        if r["away"] in per_team:
            per_team[r["away"]].append((r["ag"], r["hg"]))

    def table_after(n: int | None) -> list[dict]:
        rows = []
        for tid, games in per_team.items():
            g = games if n is None else games[:n]
            w = sum(1 for f, a in g if f > a)
            d = sum(1 for f, a in g if f == a)
            l = sum(1 for f, a in g if f < a)
            gf = sum(f for f, _ in g)
            ga = sum(a for _, a in g)
            form = ["W" if f > a else "D" if f == a else "L" for f, a in g[-5:]]
            rows.append({"id": tid, "p": len(g), "w": w, "d": d, "l": l, "gf": gf, "ga": ga,
                         "gd": gf - ga, "pts": 3 * w + d, "form": form})
        rows.sort(key=lambda r: (-r["pts"], -r["gd"], -r["gf"], teams[r["id"]]["name"]))
        for i, r in enumerate(rows, 1):
            r["pos"] = i
        return rows

    # Only count matchweeks every club has completed, so positions compare like with like.
    complete_weeks = min(len(g) for g in per_team.values()) if per_team else 0
    max_weeks = max(len(g) for g in per_team.values()) if per_team else 0
    progression = {tid: {"pos": [], "pts": []} for tid in teams}
    for n in range(1, max_weeks + 1):
        for row in table_after(n):
            progression[row["id"]]["pos"].append(row["pos"])
            progression[row["id"]]["pts"].append(row["pts"])

    table = table_after(None)
    mismatch = [teams[r["id"]]["name"] for r in table if espn_rank.get(r["id"]) and espn_rank[r["id"]] != r["pos"]]
    if mismatch:
        print(f"note: computed table order differs from ESPN for {mismatch}", file=sys.stderr)
    for r in table:
        r["zone"] = zones.get(r["id"])

    return {
        "name": group.get("name", "Premier League"),
        "teams": teams,
        "table": table,
        "matchweeks": max_weeks,
        "completeMatchweeks": complete_weeks,
        "progression": progression,
    }


def main() -> None:
    data = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "team": {"id": TEAM_ID, "name": "Manchester City",
                 "logo": f"https://a.espncdn.com/i/teamlogos/soccer/500/{TEAM_ID}.png"},
        "matches": build_matches(),
        "league": build_league(),
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT_FILE}: {len(data['matches'])} matches, "
          f"{data['league']['matchweeks']} matchweeks")


if __name__ == "__main__":
    main()
