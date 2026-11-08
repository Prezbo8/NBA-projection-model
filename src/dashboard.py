"""Build docs/index.html (GitHub Pages dashboard) from docs/today.json.

Totals first (user, Nov 8 2026): the v1 total and its play (edge >= 3, paper-traded) lead; spreads are
a secondary column and props the last tab (no edge). Styling follows the NHL dashboard (same palette, light + dark).

  python src/dashboard.py
"""
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
SRC = os.path.join(ROOT, "docs", "today.json")
OUT = os.path.join(ROOT, "docs", "index.html")

PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NBA Projection Model</title>
<style>
:root{--bg:#f3f5f8;--card:#fff;--ink:#0f1a2a;--muted:#5f6b7a;--line:#dfe4ea;--ice:#e8eef5;--accent:#1f6feb;
  --gold:#c99700;--gold-soft:#fff4cc;--pos:#1a7f37;--neg:#c62828}
@media (prefers-color-scheme:dark){:root{--bg:#0b1119;--card:#131c27;--ink:#e8edf3;--muted:#93a1b2;--line:#233040;
  --ice:#18222f;--accent:#58a6ff;--gold:#e3b341;--gold-soft:#2b2410;--pos:#3fb950;--neg:#f85149;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:0 14px 40px}
.hero{background:linear-gradient(135deg,#17408b,#c9082a);color:#fff;padding:20px 0 16px;margin-bottom:16px}
.hero h1{margin:0;font-size:24px}.hero .sub{opacity:.85;font-size:13px;margin-top:2px}
.hero .stats{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
.hero .stat{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.2);border-radius:10px;padding:6px 12px;font-size:12.5px}
.hero .stat b{display:block;font-size:16px}
.banner{background:var(--gold-soft);border:1px solid var(--line);border-left:5px solid var(--gold);border-radius:10px;
  padding:10px 14px;margin:0 0 14px;font-size:13.5px}
.switch{display:inline-flex;gap:4px;padding:4px;margin:0 0 14px;background:var(--ice);border:1px solid var(--line);border-radius:999px}
.switch button{font:inherit;font-size:14px;font-weight:800;padding:7px 22px;border:0;border-radius:999px;background:transparent;color:var(--muted);cursor:pointer}
.switch button.on{background:var(--card);color:var(--ink);box-shadow:0 1px 3px rgba(0,0,0,.25)}
.chips{display:flex;flex-wrap:wrap;gap:4px;margin:0 0 10px;align-items:center}
.chips button{font:inherit;font-size:12.5px;font-weight:700;padding:5px 12px;border:1px solid var(--line);border-radius:999px;background:transparent;color:var(--muted);cursor:pointer}
.chips button.on{background:var(--card);color:var(--ink);border-color:var(--muted)}
.chips input{font:inherit;font-size:13px;padding:5px 10px;border:1px solid var(--line);border-radius:999px;background:var(--card);color:var(--ink);margin-left:auto;min-width:180px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:6px;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:13.5px}
th{font-size:10.5px;color:var(--muted);font-weight:800;text-transform:uppercase;letter-spacing:.05em;text-align:left;padding:8px 8px;background:var(--ice);white-space:nowrap;cursor:default}
th.sort{cursor:pointer}th.sort:hover{color:var(--ink)}
td{padding:8px 8px;border-top:1px solid var(--line);vertical-align:top;white-space:nowrap}
td.num,th.num{text-align:right}
.mu b{font-size:14.5px}.time{font-weight:800;font-size:12px;color:var(--muted)}
.b2b{display:inline-block;font-size:10px;font-weight:800;padding:1px 6px;border-radius:999px;background:#dc2626;color:#fff;margin-left:6px;vertical-align:middle}
.small{font-size:11.5px;color:var(--muted)}
.edge{display:inline-block;min-width:46px;text-align:center;font-weight:800;border-radius:6px;padding:1px 6px}
.e0{background:transparent}.e1{background:color-mix(in srgb,var(--accent) 16%,transparent)}
.e2{background:color-mix(in srgb,var(--accent) 32%,transparent)}.e3{background:color-mix(in srgb,var(--accent) 52%,transparent)}
.lean{font-size:10.5px;font-weight:800;padding:2px 7px;border-radius:999px;border:1px solid var(--line);color:var(--muted)}
.out{display:block;font-size:12px;white-space:normal;max-width:300px}.out .x{color:var(--neg);font-weight:700}
.paperpill{display:inline-block;font-size:10px;font-weight:800;padding:2px 7px;border-radius:999px;background:var(--gold);color:#111;margin-top:3px}
.rec{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 12px}.rec .card{padding:10px 14px;min-width:220px}.rec b{font-size:18px}
.W{color:var(--pos);font-weight:800}.L{color:var(--neg);font-weight:800}.P{color:var(--muted);font-weight:800}
.lean0{background:color-mix(in srgb,var(--muted) 16%,transparent)}
footer{margin-top:16px;font-size:12px;color:var(--muted)}
@media (max-width:760px){.hide-m{display:none}td,th{padding:6px 5px}table{font-size:12.5px}.chips input{min-width:120px;margin-left:0}}
</style></head><body>
<div class="hero"><div class="wrap">
  <h1>NBA Projection Model</h1>
  <div class="sub" id="sub"></div>
  <div class="stats" id="stats"></div>
</div></div>
<div class="wrap">
  <div class="banner"><b>Paper trading only. No real bets.</b> The focus is <b>game totals</b>: v1 beat the <i>opening</i>
    total 55.4% in 2023-26 (1,713 bets with edge &ge; 3, +96.9 u at -110) but lost to the closing line, so plays are logged
    at the line when first flagged and judged by closing-line value. Spreads (v2) are untested; props have no edge.</div>
  <div class="switch"><button class="on" data-tab="games">Totals</button><button data-tab="paper">Paper record</button><button data-tab="props">Props (no edge)</button></div>
  <div id="games"></div>
  <div id="props" hidden>
    <div class="banner" style="border-left-color:var(--muted)">Backtest 2023-26 (500k+ props): the market's line beat the model in
      every market, and real over rates track the market's price, not the model's. The lean column is the model's opinion only.</div>
    <div class="chips" id="mkts"></div>
    <div class="card"><table id="pt"></table></div>
  </div>
  <div id="paper" hidden></div>
  <footer id="foot"></footer>
</div>
<script>
const D = __DATA__;
const ET = s => new Date(s).toLocaleTimeString("en-US",{hour:"numeric",minute:"2-digit",timeZone:"America/New_York"});
const f1 = x => x==null ? "–" : (Math.round(x*10)/10).toFixed(1);
const sg = x => x==null ? "–" : (x>0?"+":"")+f1(x);
const pct = x => x==null ? "–" : Math.round(x*100)+"%";
const ecls = (x,a,b,c) => { const v=Math.abs(x||0); return v>=c?"e3":v>=b?"e2":v>=a?"e1":"e0"; };
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const MK = {pts:"PTS",reb:"REB",ast:"AST",fg3m:"3PM",pra:"PRA",pr:"P+R",pa:"P+A",ra:"R+A",stl:"STL",blk:"BLK",stocks:"STL+BLK"};

document.getElementById("sub").textContent = `${D.date} · updated ${D.generated_et} ET · team ${D.model?.team||""} · props ${D.model?.props||""}`;
const PLAY = 3;   // v1 total edge that gets paper-traded (paper.py K["v1_total"])
const plays = D.games.filter(g=>g.v1_edge_total!=null && Math.abs(g.v1_edge_total)>=PLAY);
const v1g = (D.paper||[]).filter(b=>b.strategy==="v1_total" && b.result);
document.getElementById("stats").innerHTML = [["Games",D.games.length],["Totals plays (edge ≥ 3)",plays.length],
  ["v1 totals paper",`${v1g.filter(b=>b.result==="W").length}-${v1g.filter(b=>b.result==="L").length}`]]
  .map(([k,v])=>`<div class="stat">${k}<b>${v}</b></div>`).join("");

function outs(pl){
  const o = pl.filter(p=>p.p_out>=0.5).sort((a,b)=>b.min*b.value-a.min*a.value);
  const q = pl.filter(p=>p.p_out>0 && p.p_out<0.5);
  return (o.length?`<span class="x">Out:</span> ${o.map(p=>esc(p.player)).join(", ")}`:"")
    + (q.length?`${o.length?"<br>":""}<span class="small">Questionable: ${q.map(p=>esc(p.player)+" ("+pct(1-p.p_out)+")").join(", ")}</span>`:"")
    || '<span class="small">nobody listed</span>';
}
function pills(g){
  return (D.paper||[]).filter(b=>String(b.an_game_id)===String(g.an_game_id))
    .map(b=>`<div class="paperpill">LOGGED ${b.strategy==="v1_total"?"v1 "+b.side+" "+f1(b.line):"v2 "+b.side+" "+sg(b.line)}</div>`).join("");
}
function games(){
  if(!D.games.length) return '<div class="card" style="padding:14px">No games today.</div>';
  const rows = D.games.slice().sort((a,b)=>a.start_utc.localeCompare(b.start_utc)).map(g=>`<tr>
    <td><span class="time">${ET(g.start_utc)}</span></td>
    <td class="mu"><b>${g.away}</b>${g.away_b2b?'<span class="b2b">B2B</span>':""} @ <b>${g.home}</b>${g.home_b2b?'<span class="b2b">B2B</span>':""}
      <div class="small">${f1(g.v1_away)} – ${f1(g.v1_home)} · pace ${f1(g.proj_pace)}</div></td>
    <td class="num"><b>${f1(g.v1_total)}</b><div class="small">v2 ${f1(g.proj_total)}</div></td><td class="num">${f1(g.total)}<div class="small">open ${f1(g.open_total)}</div></td>
    <td class="num"><span class="edge ${ecls(g.v1_edge_total,1.5,PLAY,6)}">${sg(g.v1_edge_total)}</span><div class="small">v2 ${sg(g.edge_total)}</div></td>
    <td>${g.v1_edge_total!=null&&Math.abs(g.v1_edge_total)>=PLAY?`<b>${g.v1_edge_total>0?"OVER":"UNDER"} ${f1(g.total)}</b>`:'<span class="small">pass</span>'}${pills(g)}</td>
    <td class="num hide-m">${g.home} ${sg(g.proj_spread_home)}<div class="small">line ${sg(g.spread_home)} · edge ${sg(g.edge_spread)}</div></td>
    <td class="hide-m"><span class="out"><b>${g.away}</b> ${outs(g.away_players)}</span><span class="out"><b>${g.home}</b> ${outs(g.home_players)}</span></td></tr>`).join("");
  return `<div class="card"><table><thead><tr><th>Time</th><th>Matchup · v1 proj score</th><th class="num">Proj total (v1)</th>
    <th class="num">Total line</th><th class="num">Edge (v1)</th><th>Play</th><th class="num hide-m">Spread (v2, secondary)</th>
    <th class="hide-m">Injuries (Rotowire / ESPN)</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
document.getElementById("games").innerHTML = games();

let mkt = "all", q = "", sortKey = "gap";
const mkts = ["all", ...Object.keys(MK).filter(m=>D.props.some(p=>p.market===m))];
const mb = document.getElementById("mkts");
mb.innerHTML = mkts.map(m=>`<button data-m="${m}" class="${m==="all"?"on":""}">${m==="all"?"All":MK[m]}</button>`).join("")
  + '<input id="q" placeholder="Search player or team">';
mb.addEventListener("click", e=>{ const m=e.target.dataset.m; if(!m) return; mkt=m;
  mb.querySelectorAll("button").forEach(b=>b.classList.toggle("on", b.dataset.m===m)); props(); });
document.getElementById("q").addEventListener("input", e=>{ q=e.target.value.toLowerCase(); props(); });
function props(){
  let P = D.props.filter(p=>(mkt==="all"||p.market===mkt) && (!q || (p.player+" "+p.team).toLowerCase().includes(q)));
  P.forEach(p=>p.gap = p.mkt_over==null ? 0 : p.p_over - p.mkt_over);
  P.sort(sortKey==="gap" ? (a,b)=>Math.abs(b.gap)-Math.abs(a.gap) : (a,b)=>a.player.localeCompare(b.player));
  const rows = P.slice(0,300).map(p=>{ const over = p.gap>0, best = over?p.best_over:p.best_under; return `<tr>
    <td><b>${esc(p.player)}</b><div class="small">${p.team} vs ${p.opp} · ${ET(p.start_utc)} · ${f1(p.exp_min)} min</div></td>
    <td>${MK[p.market]}</td><td class="num"><b>${f1(p.proj)}</b></td>
    <td class="num">${f1(p.line)}<div class="small">${p.over>0?"+":""}${p.over} / ${p.under>0?"+":""}${p.under}${p.open_line!=null&&p.open_line!==p.line?" · open "+f1(p.open_line):""}</div></td>
    <td class="num">${pct(p.p_over)}</td><td class="num">${pct(p.mkt_over)}</td>
    <td class="num"><span class="edge lean0">${sg(p.gap*100)}</span></td>
    <td><span class="lean">${p.gap>0?"OVER":p.gap<0?"UNDER":"–"}</span></td>
    <td class="hide-m">${best?`${best.book} ${best.odds>0?"+":""}${best.odds}`:'<span class="small">–</span>'}</td></tr>`; }).join("");
  document.getElementById("pt").innerHTML = `<thead><tr><th class="sort" data-s="name">Player</th><th>Market</th><th class="num">Proj</th>
    <th class="num">Line (consensus)</th><th class="num">Model over</th><th class="num">Market over (no vig)</th>
    <th class="num sort" data-s="gap">Model lean (pts, no proven edge)</th><th>Lean</th><th class="hide-m">Best price at this line</th></tr></thead>
    <tbody>${rows || '<tr><td colspan="9" class="small">No props match.</td></tr>'}</tbody>`;
  document.querySelectorAll("#pt th.sort").forEach(th=>th.onclick=()=>{ sortKey=th.dataset.s; props(); });
}
props();
function paper(){
  const P = D.paper||[], name = {v1_total:"v1 totals (edge ≥ 3)", v2_spread:"v2 spreads, injury signal (edge ≥ 3)"};
  const rec = Object.keys(name).map(s=>{ const b=P.filter(x=>x.strategy===s), g=b.filter(x=>x.result);
    const w=g.filter(x=>x.result==="W").length, l=g.filter(x=>x.result==="L").length, p=g.filter(x=>x.result==="P").length;
    const u=g.reduce((a,x)=>a+(+x.units||0),0), risk=g.filter(x=>x.result!=="P").length;
    const cl = g.filter(x=>x.clv!=null && x.clv!==""), clv = cl.length ? cl.reduce((a,x)=>a+(+x.clv),0)/cl.length : null;
    const beat = cl.filter(x=>+x.clv>0).length;
    return `<div class="card">${name[s]}<br><b>${w}-${l}${p?"-"+p:""}</b> · ${u>=0?"+":""}${u.toFixed(2)} u
      <div class="small">${b.length} logged · ${g.length} graded · ROI ${risk?(u/risk*100).toFixed(1)+"%":"–"}</div>
      <div class="small">vs closing line: ${clv==null?"–":(clv>=0?"+":"")+clv.toFixed(2)+" pts avg, beat the close "+beat+"/"+cl.length}</div></div>`; }).join("");
  const rows = P.slice().sort((a,b)=>b.start_utc.localeCompare(a.start_utc)).slice(0,200).map(b=>`<tr>
    <td>${b.date}</td><td>${b.away} @ ${b.home}</td><td>${b.strategy==="v1_total"?"v1 total":"v2 spread"}</td>
    <td><b>${b.strategy==="v1_total"?b.side+" "+f1(b.line):b.side+" "+sg(b.line)}</b> <span class="small">${b.odds>0?"+":""}${b.odds}</span></td>
    <td class="num">${f1(b.proj)}</td><td class="num">${sg(b.edge)}</td><td class="small">${b.logged_et}<br>open ${b.open_line!=null&&b.open_line!==""?(b.strategy==="v1_total"?f1(b.open_line):sg(b.open_line)):"–"}${b.close_line!=null&&b.close_line!==""?" · close "+(b.strategy==="v1_total"?f1(b.close_line):sg(b.close_line)):""}</td>
    <td>${b.result?`<span class="${b.result}">${b.result}</span> <span class="small">${b.away_pts}-${b.home_pts} · ${(+b.units>=0?"+":"")+(+b.units).toFixed(2)}u</span>`:'<span class="small">pending</span>'}</td></tr>`).join("");
  document.getElementById("paper").innerHTML = `<div class="rec">${rec}</div><div class="card"><table><thead><tr><th>Date</th><th>Game</th>
    <th>Strategy</th><th>Bet (logged line, price)</th><th class="num">Proj</th><th class="num">Edge</th><th>Logged (ET) · open / close</th><th>Result</th>
    </tr></thead><tbody>${rows||'<tr><td colspan="8" class="small">No paper bets yet: they start with the next game-day run.</td></tr>'}</tbody></table></div>
    <p class="small">Each bet is logged once, at the consensus line and price when it's first flagged, and graded at that price. "vs closing line" (CLV) is how much better the logged line was than the final line: a real edge should beat the close on average, and that shows up long before the win-loss record means anything. Judge the record after 100+ graded bets per strategy.</p>`;
}
paper();
document.querySelector(".switch").addEventListener("click", e=>{ const t=e.target.dataset.tab; if(!t) return;
  document.querySelectorAll(".switch button").forEach(b=>b.classList.toggle("on", b.dataset.tab===t));
  ["games","props","paper"].forEach(x=>document.getElementById(x).hidden = t!==x); });
document.getElementById("foot").innerHTML = "Lines: Action Network consensus (current) and opening line. Injuries: Rotowire play-chance, ESPN as backup. "
  + "Model over chance uses each market's fitted outcome spread (backtest 2021-23); on 2023-26 lines the market's no-vig price was better calibrated. "
  + '<a href="https://github.com/Prezbo8/NBA-projection-model">Code</a>';
</script></body></html>
"""


if __name__ == "__main__":
    data = json.load(open(SRC))
    log = os.path.join(ROOT, "data", "paper", "paper_trades.csv")
    if os.path.exists(log):
        import pandas as pd
        data["paper"] = json.loads(pd.read_csv(log, dtype={"an_game_id": str}).to_json(orient="records"))
    # </script> inside the JSON would end the script tag early
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    open(OUT, "w").write(PAGE.replace("__DATA__", blob))
    print(f"wrote {OUT} ({len(data['games'])} games, {len(data['props'])} props)")
