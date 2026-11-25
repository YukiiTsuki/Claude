"use strict";

const COMP_ORDER = ["eng.1", "uefa.champions", "eng.fa", "eng.league_cup", "eng.charity"];
const COMP_SHORT = {
  "eng.1": "Premier League",
  "uefa.champions": "Champions League",
  "eng.fa": "FA Cup",
  "eng.league_cup": "Carabao Cup",
  "eng.charity": "Community Shield",
};
const COMP_ABBR = {
  "eng.1": "PL",
  "uefa.champions": "UCL",
  "eng.fa": "FAC",
  "eng.league_cup": "EFL",
  "eng.charity": "CS",
};
const DAY = 24 * 60 * 60 * 1000;

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

const fmtDay = new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short" });
const fmtTime = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });
const fmtMonth = new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric" });
const fmtShort = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });

function ordinal(n) {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

/* Weeks follow UK match days (Mon–Sun, Europe/London), so a Sunday-evening
   kick-off in England counts as Sunday even where it is already Monday. */
const UK_TZ = "Europe/London";
const fmtUkKey = new Intl.DateTimeFormat("en-CA", { timeZone: UK_TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const fmtUkDay = new Intl.DateTimeFormat("en-GB", { timeZone: UK_TZ, weekday: "short", day: "numeric", month: "short" });
const fmtKeyShort = new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", day: "numeric", month: "short" });

/** UK calendar date of an instant, as "YYYY-MM-DD". */
const ukDateKey = (d) => fmtUkKey.format(d);
const keyToUtc = (key) => new Date(`${key}T00:00:00Z`);
const addDays = (key, n) => new Date(keyToUtc(key).getTime() + n * DAY).toISOString().slice(0, 10);

/** UK date key of the Monday of the UK week containing instant d. */
function ukWeekStart(d) {
  const key = ukDateKey(d);
  const offset = (keyToUtc(key).getUTCDay() + 6) % 7; // Mon=0 ... Sun=6
  return addDays(key, -offset);
}
function rangeLabel(startKey) {
  return `${fmtKeyShort.format(keyToUtc(startKey))} – ${fmtKeyShort.format(keyToUtc(addDays(startKey, 6)))} (UK)`;
}

function scoreText(m) {
  if (!m.score) return "";
  let t = `${m.score.for} – ${m.score.against}`;
  return t;
}
function penText(m) {
  const s = m.score;
  if (s && s.penFor != null && s.penAgainst != null) return `${s.penFor}–${s.penAgainst} on pens`;
  return "";
}

function relativeKickoff(date, now) {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diff = Math.round((day - today) / DAY);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  if (diff > 1) return `In ${diff} days`;
  return "";
}

/* ---------- Goals (scorer, minute, assist) ---------- */
function goalItem(g) {
  const tag = g.kind === "pen" ? " (pen)" : g.kind === "og" ? " (OG)" : "";
  return `<li><span class="g-min">${esc(g.minute)}</span>
    <span class="g-who"><span class="g-scorer">${esc(g.scorer)}${tag}</span>${
      g.assist ? `<span class="g-assist">Assist: ${esc(g.assist)}</span>` : ""}</span></li>`;
}
function goalsBlock(m) {
  if (m.state !== "post" || !m.goals?.length) return "";
  const city = m.goals.filter((g) => g.side === "for");
  const opp = m.goals.filter((g) => g.side === "against");
  const [home, away] = m.home ? [city, opp] : [opp, city];
  const list = (gs, cls) => `<ul class="goals ${cls}">${gs.map(goalItem).join("")}</ul>`;
  return `<div class="goal-cols" aria-label="Goals">${list(home, "home")}${list(away, "away")}</div>`;
}

/* ---------- Match card ---------- */
function matchCard(m, data, now, { highlight = false } = {}) {
  const date = new Date(m.date);
  const city = { name: "Man City", logo: data.team.logo };
  const opp = { name: m.opponent.short || m.opponent.name, logo: m.opponent.logo };
  const [home, away] = m.home ? [city, opp] : [opp, city];

  let mid;
  if (m.state === "pre") {
    mid = `<div class="kick">${fmtTime.format(date)}</div><div class="small">Kick-off</div>`;
  } else {
    const pens = penText(m);
    const s = m.score;
    const homeGoals = m.home ? s?.for : s?.against;
    const awayGoals = m.home ? s?.against : s?.for;
    mid = `<div class="score">${homeGoals ?? "-"} – ${awayGoals ?? "-"}</div>
           <div class="small">${esc(m.state === "in" ? m.statusDetail : (pens || m.statusDetail || "FT"))}</div>`;
  }

  const right = m.state === "post"
    ? `<span class="res ${m.result}" title="${m.result === "W" ? "Win" : m.result === "L" ? "Loss" : "Draw"}">${m.result}</span>`
    : m.state === "in"
      ? `<span class="countdown">● Live</span>`
      : `<span class="countdown">${relativeKickoff(date, now)}</span>`;

  return `<article class="card${highlight ? " next" : ""}">
    <div class="card-top">
      <span class="comp-tag ${m.competition}">${esc(COMP_SHORT[m.competition])}</span>
      <span>${esc(fmtDay.format(date))}${fmtDay.format(date) !== fmtUkDay.format(date)
        ? ` <span class="uk-date">(UK ${esc(fmtUkDay.format(date))})</span>` : ""}</span>
    </div>
    <div class="matchup">
      <div class="side"><img src="${esc(home.logo)}" alt="" loading="lazy"><span>${esc(home.name)}</span></div>
      <div class="mid">${mid}</div>
      <div class="side"><img src="${esc(away.logo)}" alt="" loading="lazy"><span>${esc(away.name)}</span></div>
    </div>
    ${goalsBlock(m)}
    <div class="card-bottom">
      <span>${esc([m.round, m.venue].filter(Boolean).join(" · "))}</span>
      ${right}
    </div>
  </article>`;
}

/* ---------- This week / last week ---------- */
function renderWeeks(data, now) {
  const start = ukWeekStart(now);
  const next = addDays(start, 7);
  const prev = addDays(start, -7);
  const within = (m, a, b) => { const k = ukDateKey(new Date(m.date)); return k >= a && k < b; };

  $("#this-week-range").textContent = rangeLabel(start);
  $("#last-week-range").textContent = rangeLabel(prev);

  const thisWeek = data.matches.filter((m) => within(m, start, next));
  const firstUpcoming = thisWeek.find((m) => m.state !== "post");
  if (thisWeek.length) {
    $("#this-week-cards").innerHTML = thisWeek
      .map((m) => matchCard(m, data, now, { highlight: m === firstUpcoming }))
      .join("");
  } else {
    const upcoming = data.matches.find((m) => m.state !== "post" && ukDateKey(new Date(m.date)) >= next);
    $("#this-week-cards").innerHTML = `<div class="empty">No matches this week.${
      upcoming ? " Next up:" : ""}</div>` + (upcoming ? matchCard(upcoming, data, now, { highlight: true }) : "");
  }

  const lastWeek = data.matches.filter((m) => within(m, prev, start) && m.state === "post");
  $("#last-week-cards").innerHTML = lastWeek.length
    ? lastWeek.map((m) => matchCard(m, data, now)).join("")
    : `<div class="empty">No matches last week.</div>`;
}

/* ---------- Header + glance ---------- */
function renderHeader(data) {
  const L = data.league;
  const row = L.table.find((r) => r.id === data.team.id);
  const played = data.matches.filter((m) => m.state === "post");
  const wins = played.filter((m) => m.result === "W").length;
  const goals = played.reduce((a, m) => a + (m.score?.for ?? 0), 0);
  const stats = [
    row && [ordinal(row.pos), "in Premier League"],
    row && [row.pts, "PL points"],
    [`${wins}/${played.length}`, "wins, all comps"],
    [goals, "goals scored"],
  ].filter(Boolean);
  $("#header-stats").innerHTML = stats.map(([b, s]) => `<div class="hstat"><b>${esc(b)}</b><span>${esc(s)}</span></div>`).join("");
  $("#season-label").textContent = `${L.name.replace(/ English Premier League$/, "")} season · all first-team competitions`;
  $("#updated").textContent = `Updated ${new Date(data.generatedAt).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })}`;
}

function renderGlance(data) {
  const played = data.matches.filter((m) => m.state === "post");
  $("#form-strip").innerHTML = played.slice(-5).map((m) =>
    `<div class="form-item" title="${esc(`${COMP_SHORT[m.competition]}: ${m.home ? "vs" : "at"} ${m.opponent.name} ${scoreText(m)}`)}">
      <span class="res ${m.result}">${m.result}</span>
      <span class="comp-tag ${m.competition}">${esc(COMP_ABBR[m.competition])}</span>
      <span class="form-score">${esc(scoreText(m))}</span>
      <span>${m.home ? "vs" : "@"} ${esc(m.opponent.abbr || m.opponent.short)}</span>
      ${m.score?.penFor != null ? `<span class="form-pens">pens ${m.score.penFor}–${m.score.penAgainst}</span>` : ""}
    </div>`).join("");
  const shown = COMP_ORDER.filter((c) => played.slice(-5).some((m) => m.competition === c));
  $("#form-legend").textContent = shown.map((c) => `${COMP_ABBR[c]} = ${COMP_SHORT[c]}`).join(" · ");

  const rows = COMP_ORDER.map((c) => {
    const ms = data.matches.filter((m) => m.competition === c);
    if (!ms.length) return "";
    const p = ms.filter((m) => m.state === "post");
    const cnt = (r) => p.filter((m) => m.result === r).length;
    const gf = p.reduce((a, m) => a + m.score.for, 0);
    const ga = p.reduce((a, m) => a + m.score.against, 0);
    const left = ms.length - p.length;
    return `<tr><td>${esc(COMP_SHORT[c])}</td><td>${p.length}</td><td>${cnt("W")}</td><td>${cnt("D")}</td><td>${cnt("L")}</td>
      <td>${gf}–${ga}</td><td>${left}</td></tr>`;
  }).join("");
  $("#comp-record").innerHTML = `<thead><tr><th>Competition</th><th>P</th><th>W</th><th>D</th><th>L</th><th>Goals</th><th>To play</th></tr></thead><tbody>${rows}</tbody>`;
}

/* ---------- Standings tables (PL + UCL) ---------- */
function changeMark(c) {
  if (c == null) return "";
  if (c > 0) return `<span class="up" title="Up ${c} since last round">▲${c}</span>`;
  if (c < 0) return `<span class="down" title="Down ${-c} since last round">▼${-c}</span>`;
  return `<span class="same" title="No change since last round">–</span>`;
}

function renderStandings(sel, rows, teamOf, cityId, { form = false } = {}) {
  const hasChange = rows.some((r) => r.change != null);
  const body = rows.map((r) => {
    const t = teamOf(r);
    const zone = r.zone?.color ? `style="--zone:${esc(r.zone.color)}"` : "";
    const formCell = form ? `<td><span class="mini-form">${r.form.map((f) => `<span class="res ${f}">${f}</span>`).join("")}</span></td>` : "";
    return `<tr class="${r.id === cityId ? "city" : ""}">
      <td class="pos" ${zone} title="${esc(r.zone?.label || "")}">${r.pos}</td>
      ${hasChange ? `<td class="chg">${changeMark(r.change)}</td>` : ""}
      <td class="team"><div class="team-cell"><img src="${esc(t.logo)}" alt="" loading="lazy">${esc(t.short || t.name)}</div></td>
      <td>${r.p}</td><td>${r.w}</td><td>${r.d}</td><td>${r.l}</td>
      <td>${r.gf}</td><td>${r.ga}</td><td>${r.gd > 0 ? "+" : ""}${r.gd}</td>
      <td class="pts">${r.pts}</td>${formCell}
    </tr>`;
  }).join("");

  const zones = new Map();
  rows.forEach((r) => { if (r.zone?.label && !zones.has(r.zone.label)) zones.set(r.zone.label, r.zone.color); });
  const legend = [...zones].map(([label, color]) => `<span><i style="background:${esc(color)}"></i>${esc(label)}</span>`).join("");

  const table = $(sel);
  table.innerHTML = `<thead><tr><th>#</th>${hasChange ? `<th class="chg" title="Change since last round">+/–</th>` : ""}<th class="team">Club</th><th>P</th><th>W</th><th>D</th><th>L</th>
    <th>GF</th><th>GA</th><th>GD</th><th>Pts</th>${form ? "<th>Form</th>" : ""}</tr></thead><tbody>${body}</tbody>`;
  if (legend) table.insertAdjacentHTML("afterend", `<div class="zone-legend">${legend}</div>`);
}

function renderTable(data) {
  renderStandings("#league-table", data.league.table, (r) => data.league.teams[r.id], data.team.id, { form: true });
}

/* ---------- Champions League ---------- */
function renderUcl(data) {
  const U = data.ucl;
  if (!U) return;
  renderStandings("#ucl-table", U.table, (r) => r, data.team.id);
  const city = U.table.find((r) => r.id === data.team.id);
  if (city) $("#ucl-summary").textContent = `Man City: ${ordinal(city.pos)} · ${city.pts} pts from ${city.p} games`;

  const draw = (onlyCity) => {
    const list = U.fixtures.filter((f) => !onlyCity || f.home.id === data.team.id || f.away.id === data.team.id);
    let round = "", day = "";
    const rows = list.map((f) => {
      const d = new Date(f.date);
      const isCity = f.home.id === data.team.id || f.away.id === data.team.id;
      let head = "";
      if (f.round !== round) { round = f.round; day = ""; head += `<tr class="month"><td colspan="5">${esc(round)}</td></tr>`; }
      const dayLabel = fmtDay.format(d);
      if (dayLabel !== day) { day = dayLabel; head += `<tr class="day"><td colspan="5">${esc(dayLabel)}</td></tr>`; }
      const mid = f.state === "in" && f.score
        ? `<b>${f.score[0]} – ${f.score[1]}</b> <span class="countdown">Live</span>`
        : fmtTime.format(d);
      return `${head}<tr class="${isCity ? "city" : ""}">
        <td class="fx-home"><div class="opp right">${esc(f.home.short || f.home.name)}<img src="${esc(f.home.logo)}" alt="" loading="lazy"></div></td>
        <td class="fx-time">${mid}</td>
        <td class="fx-away"><div class="opp"><img src="${esc(f.away.logo)}" alt="" loading="lazy">${esc(f.away.short || f.away.name)}</div></td>
        <td class="rd venue">${esc(f.venue)}</td>
      </tr>`;
    }).join("");
    $("#ucl-fixtures").innerHTML = `<tbody>${rows || `<tr><td>No upcoming Champions League matches.</td></tr>`}</tbody>`;
  };

  const box = $("#ucl-filters");
  box.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    box.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
    draw(btn.dataset.only === "city");
  });
  draw(false);
}

/* ---------- Charts ---------- */
let charts = [];
function renderCharts(data, compareId) {
  charts.forEach((c) => c.destroy());
  charts = [];
  if (typeof Chart === "undefined") return;

  const L = data.league;
  const labels = Array.from({ length: L.matchweeks }, (_, i) => `MW${i + 1}`);
  const ids = [data.team.id, compareId].filter(Boolean);
  const colors = [css("--series-1"), css("--series-2")];
  const text2 = css("--text-2"), grid = css("--grid"), surface = css("--surface");

  const datasets = (key) => ids.map((id, i) => ({
    label: L.teams[id].short || L.teams[id].name,
    data: L.progression[id][key],
    borderColor: colors[i],
    backgroundColor: colors[i],
    pointBackgroundColor: colors[i],
    pointBorderColor: surface,
    pointBorderWidth: 2,
    borderWidth: 2,
    pointRadius: 4,
    pointHoverRadius: 6,
    tension: 0.3,
    cubicInterpolationMode: "monotone",
    clip: false,
  }));

  const base = (extraY) => ({
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    layout: { padding: { top: 8, right: 8 } },
    plugins: {
      legend: { display: ids.length > 1, labels: { color: text2, boxWidth: 12, boxHeight: 12, usePointStyle: true } },
      tooltip: { padding: 10 },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: text2, maxRotation: 0, autoSkip: true } },
      y: { grid: { color: grid }, border: { display: false }, ticks: { color: text2 }, ...extraY },
    },
  });

  charts.push(new Chart($("#pos-chart"), {
    type: "line",
    data: { labels, datasets: datasets("pos") },
    options: (() => {
      const o = base({ reverse: true, min: 1, max: 20, ticks: { color: text2, stepSize: 1, autoSkip: false, callback: (v) => ([1, 5, 10, 15, 20].includes(v) ? v : "") } });
      o.plugins.tooltip.callbacks = { label: (c) => ` ${c.dataset.label}: ${ordinal(c.parsed.y)}` };
      return o;
    })(),
  }));

  charts.push(new Chart($("#pts-chart"), {
    type: "line",
    data: { labels, datasets: datasets("pts") },
    options: (() => {
      const o = base({ beginAtZero: true });
      o.plugins.tooltip.callbacks = { label: (c) => ` ${c.dataset.label}: ${c.parsed.y} pts` };
      return o;
    })(),
  }));
}

function setupCompare(data) {
  const sel = $("#compare-select");
  const L = data.league;
  L.table.filter((r) => r.id !== data.team.id).forEach((r) => {
    const opt = document.createElement("option");
    opt.value = r.id;
    opt.textContent = `${r.pos}. ${L.teams[r.id].short || L.teams[r.id].name}`;
    sel.appendChild(opt);
  });
  // Default: compare with the league leader (or whoever is right behind City).
  const cityPos = L.table.find((r) => r.id === data.team.id)?.pos;
  const rival = L.table.find((r) => r.pos === (cityPos === 1 ? 2 : 1));
  if (rival) sel.value = rival.id;
  sel.addEventListener("change", () => renderCharts(data, sel.value));
  renderCharts(data, sel.value);
}

/* ---------- Fixtures list ---------- */
function renderFixtures(data, filter) {
  const ms = data.matches.filter((m) => !filter || m.competition === filter);
  let month = "";
  const rows = ms.map((m) => {
    const d = new Date(m.date);
    const mLabel = fmtMonth.format(d);
    const head = mLabel !== month ? `<tr class="month"><td colspan="7">${esc((month = mLabel))}</td></tr>` : "";
    const pens = penText(m);
    const sc = m.state === "pre"
      ? fmtTime.format(d)
      : `${scoreText(m)}${pens ? ` <span class="muted">(${esc(pens)})</span>` : ""}`;
    const res = m.result ? `<span class="res ${m.result}">${m.result}</span>` : (m.state === "in" ? `<span class="countdown">Live</span>` : "");
    return `${head}<tr class="${m.state === "pre" ? "upcoming" : ""}">
      <td>${esc(fmtDay.format(d))}</td>
      <td><span class="comp-tag ${m.competition}">${esc(COMP_SHORT[m.competition])}</span></td>
      <td class="ha">${m.neutral ? "N" : m.home ? "H" : "A"}</td>
      <td><div class="opp"><img src="${esc(m.opponent.logo)}" alt="" loading="lazy">${esc(m.opponent.name)}</div></td>
      <td class="sc">${sc}</td>
      <td>${res}</td>
      <td class="rd">${esc(m.round || m.venue)}</td>
    </tr>`;
  }).join("");
  $("#fixtures").innerHTML = `<tbody>${rows || `<tr><td>No matches.</td></tr>`}</tbody>`;
}

function setupFilters(data) {
  const present = COMP_ORDER.filter((c) => data.matches.some((m) => m.competition === c));
  const box = $("#comp-filters");
  box.innerHTML = [["", "All"], ...present.map((c) => [c, COMP_SHORT[c]])]
    .map(([v, l], i) => `<button type="button" data-comp="${v}" aria-pressed="${i === 0}">${esc(l)}</button>`).join("");
  box.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    box.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
    renderFixtures(data, btn.dataset.comp);
  });
  renderFixtures(data, "");
}

/* ---------- Tabs ---------- */
function setupTabs(onShow) {
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const names = tabs.map((t) => t.id.replace("tab-", ""));
  const show = (name, focus = false) => {
    if (!names.includes(name)) name = names[0];
    tabs.forEach((t) => {
      const on = t.id === `tab-${name}`;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
      if (on && focus) t.focus();
    });
    onShow(name);
  };
  tabs.forEach((t, i) => {
    t.addEventListener("click", () => {
      const name = names[i];
      history.replaceState(null, "", `#${name}`);
      show(name);
      window.scrollTo({ top: 0 });
    });
    t.addEventListener("keydown", (e) => {
      const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (!d) return;
      const name = names[(i + d + names.length) % names.length];
      history.replaceState(null, "", `#${name}`);
      show(name, true);
    });
  });
  window.addEventListener("hashchange", () => show(location.hash.slice(1)));
  show(location.hash.slice(1));
}

/* ---------- Boot ---------- */
async function main() {
  let data;
  try {
    const res = await fetch("data.json", { cache: "no-cache" });
    data = await res.json();
  } catch (err) {
    document.querySelector("main").innerHTML = `<div class="empty" style="margin-top:24px">Could not load match data.</div>`;
    return;
  }
  const now = new Date();
  renderHeader(data);
  renderWeeks(data, now);
  renderGlance(data);
  let chartsReady = false;
  renderTable(data);
  renderUcl(data);
  setupFilters(data);
  setupTabs((name) => {
    if (name === "league" && !chartsReady) { chartsReady = true; setupCompare(data); }
  });

  // Re-colour charts if the OS theme flips.
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (chartsReady) renderCharts(data, $("#compare-select").value); });
}
main();
