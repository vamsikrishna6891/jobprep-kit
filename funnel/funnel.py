#!/usr/bin/env python3
"""
Job Application Funnel - local SQLite-backed dashboard.
Single source of truth: funnel.sqlite (created next to this file on first run).
Bidirectional: dashboard writes the DB; external DB edits show up on the next poll.

Run:  python3 funnel.py     then open http://localhost:8000
Set PORT env var to change the port. No dependencies (Python standard library only).
Nothing leaves your machine.
"""
import sqlite3, json, os, webbrowser, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(HERE, "funnel.sqlite")
SEEDFILE = os.path.join(HERE, "seed.json")
PORT = int(os.environ.get("PORT", "8000"))
COLS = ["id", "company", "role", "archetype", "date", "score", "status", "note", "channel", "posted_date", "stage_reached"]


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def enforce_stage_invariant(c):
    """stage_reached is a forward-only high-water mark. The UI drags it along on
    status edits, but external writers (sqlite CLI, scripts) can leave
    status deeper than stage_reached; heal that here. Returns rows fixed."""
    rank = ("CASE {} WHEN 'screen' THEN 1 WHEN 'interview' THEN 2 "
            "WHEN 'onsite' THEN 3 WHEN 'offer' THEN 4 ELSE 0 END")
    cur = c.execute("UPDATE apps SET stage_reached=status WHERE "
                    + rank.format("status") + " > " + rank.format("stage_reached"))
    if cur.rowcount:
        c.commit()
        print(f"Healed stage_reached on {cur.rowcount} row(s) (status was deeper)")
    return cur.rowcount


def init():
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS apps(
        id TEXT PRIMARY KEY, company TEXT, role TEXT, archetype TEXT,
        date TEXT, score INTEGER, status TEXT, note TEXT,
        channel TEXT DEFAULT 'cold', posted_date TEXT,
        stage_reached TEXT DEFAULT 'applied')""")
    n = c.execute("SELECT COUNT(*) FROM apps").fetchone()[0]
    if n == 0 and os.path.exists(SEEDFILE):
        seed = json.load(open(SEEDFILE))
        for r in seed:
            c.execute("INSERT OR IGNORE INTO apps VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      [r.get(k) for k in COLS])
        c.commit()
        print(f"Seeded {len(seed)} rows into {DB}")
    c.close()


HTML = r'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Application Funnel</title>
<style>
:root{
 --bg:#f6f7f9;--card:#ffffff;--ink:#1a1d21;--muted:#6b7280;--line:#e6e8eb;
 --unconfirmed:#9aa3af;--applied:#3b82f6;--screen:#6366f1;--interview:#f59e0b;
 --onsite:#8b5cf6;--offer:#10b981;--rejected:#ef4444;--withdrawn:#94a3b8;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 font-size:14px;line-height:1.45}
.wrap{max-width:1180px;margin:0 auto;padding:24px 20px 64px}
header{display:flex;align-items:baseline;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:6px}
h1{font-size:21px;margin:0;font-weight:650}
.sub{color:var(--muted);font-size:12.5px;margin:2px 0 20px}
.btn{border:1px solid var(--line);background:var(--card);color:var(--ink);
 padding:7px 12px;border-radius:8px;font-size:12.5px;cursor:pointer}
.btn:hover{background:#f0f1f3}
.actions{display:flex;gap:8px;align-items:center}
.dot{width:8px;height:8px;border-radius:50%;background:var(--offer);display:inline-block;margin-right:5px}
.dot.busy{background:var(--interview)}
.dot.err{background:var(--rejected)}
#sync{font-size:11.5px;color:var(--muted)}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));margin-bottom:18px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:13px 15px}
.kpi .n{font-size:24px;font-weight:680;letter-spacing:-.5px}
.kpi .l{color:var(--muted);font-size:12px;margin-top:2px}
.kpi .d{font-size:11.5px;margin-top:5px;color:var(--muted)}
.panel{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-bottom:18px}
.panel h2{font-size:13px;margin:0 0 14px;font-weight:620;color:#374151}
.frow{display:flex;align-items:center;gap:12px;margin:9px 0}
.fname{width:118px;font-size:12.5px;color:#374151;flex:none}
.fbar{flex:1;background:#eef0f3;border-radius:6px;height:26px;position:relative;overflow:hidden}
.ffill{height:100%;border-radius:6px;display:flex;align-items:center;padding:0 9px;color:#fff;
 font-size:12px;font-weight:600;min-width:34px;transition:width .35s ease}
.fconv{width:120px;font-size:11.5px;color:var(--muted);flex:none;text-align:right}
.split{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media(max-width:760px){.split{grid-template-columns:1fr}}
.distrow{display:flex;align-items:center;gap:10px;margin:6px 0;font-size:12px}
.distrow .dn{width:96px;flex:none;color:#374151;text-transform:capitalize}
.distrow .db{flex:1;background:#eef0f3;border-radius:5px;height:16px;overflow:hidden}
.distrow .df{height:100%;border-radius:5px}
.distrow .dc{width:30px;flex:none;text-align:right;font-variant-numeric:tabular-nums}
.toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
input[type=text]{border:1px solid var(--line);border-radius:8px;padding:7px 10px;font-size:13px;min-width:200px}
.filterbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.filterbar input[type=text]{flex:1;min-width:180px;max-width:320px}
.seg{display:inline-flex;flex-wrap:wrap;border:1px solid var(--line);border-radius:9px;overflow:hidden;background:var(--card)}
.seg button{border:0;background:none;padding:6px 11px;font-size:12.5px;color:#374151;cursor:pointer;border-right:1px solid var(--line)}
.seg button:last-child{border-right:0}
.seg button .n{color:var(--muted);font-size:11px;margin-left:4px;font-variant-numeric:tabular-nums}
.seg button.on{background:var(--ink);color:#fff}.seg button.on .n{color:#cbd5e1}
.fbtn{border:1px solid var(--line);background:var(--card);border-radius:9px;padding:6px 12px;font-size:12.5px;cursor:pointer;display:inline-flex;gap:6px;align-items:center}
.fbtn.open,.fbtn.has{border-color:var(--ink)}
.fbtn .badge{background:var(--ink);color:#fff;border-radius:10px;font-size:10.5px;padding:1px 6px}
.fpanel{border:1px solid var(--line);border-radius:10px;background:#fbfbfc;padding:14px 16px;margin-bottom:10px;
 display:flex;flex-wrap:wrap;gap:14px 20px}
.fgroup{flex:1 1 140px;max-width:220px}.fgroup.st{max-width:none}.fgroup.st{flex:2 1 300px}
.fpanel[hidden]{display:none}
.fgroup .fl{font-size:10.5px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600;margin-bottom:6px}
.fgroup select{width:100%;border:1px solid var(--line);border-radius:7px;padding:5px 7px;font-size:12.5px;background:var(--card)}
.fchecks{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:3px 12px}
.fcheck{display:flex;align-items:center;gap:6px;font-size:12.5px;cursor:pointer;text-transform:capitalize}
.fcheck .sw{width:8px;height:8px;border-radius:50%;flex:none}
.fcheck .n{margin-left:auto;color:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
.pills{display:flex;gap:6px;flex-wrap:wrap;margin:-2px 0 10px}
.pill{background:#eef0f3;border-radius:14px;padding:3px 6px 3px 10px;font-size:11.5px;display:inline-flex;align-items:center;gap:4px}
.pill b{font-weight:600}.pill .x{cursor:pointer;color:var(--muted);padding:0 4px;font-size:13px}.pill .x:hover{color:var(--ink)}
.clear{font-size:11.5px;color:var(--muted);cursor:pointer;text-decoration:underline;align-self:center}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:9px 11px;text-align:left;border-bottom:1px solid var(--line);font-size:12.7px;vertical-align:middle}
th{font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:var(--muted);cursor:pointer;user-select:none;background:#fbfbfc}
tr:last-child td{border-bottom:none}
td:first-child{border-left:3px solid transparent}
td .role{color:var(--muted);font-size:11.5px}
select.st{border:1px solid var(--line);border-radius:7px;padding:4px 6px;font-size:12px;font-weight:600;color:#fff;cursor:pointer}
td.notecell{color:var(--muted);font-size:11.5px;max-width:260px}
td .noteinput{border:1px dashed transparent;border-radius:6px;padding:3px 5px;width:100%;font:inherit;color:var(--muted);background:transparent}
td .noteinput:hover{border-color:var(--line)}
td .noteinput:focus{border-color:var(--applied);outline:none;color:var(--ink)}
.match{font-variant-numeric:tabular-nums;font-weight:600}
.del{color:#cbd0d6;cursor:pointer;font-size:15px}
.del:hover{color:var(--rejected)}
.foot{color:var(--muted);font-size:11.5px;margin-top:14px;text-align:center}
.loading{text-align:center;padding:60px;color:var(--muted)}
</style></head><body>
<div class="wrap">
<header>
 <div><h1>Application Funnel Dashboard</h1></div>
 <div class="actions">
  <span id="sync"><span class="dot" id="dot"></span><span id="synctext">connecting...</span></span>
  <button class="btn" id="add">+ Add</button>
  <button class="btn" id="export">Export CSV</button>
 </div>
</header>
<div class="sub" id="sub"></div>

<div id="app" style="display:none">
 <div class="grid" id="kpis"></div>
 <div class="panel"><h2>Conversion funnel</h2><div id="funnel"></div></div>
 <div class="split">
  <div class="panel"><h2>Status distribution</h2><div id="dist"></div></div>
  <div class="panel"><h2>Applications by week</h2><div id="weeks"></div></div>
 </div>
 <div class="panel">
  <h2>Applications</h2>
  <div class="filterbar">
   <input type="text" id="search" placeholder="Search company or role..."/>
   <div class="seg" id="views"></div>
   <button class="fbtn" id="fbtn">Filters <span class="badge" id="fcount" hidden></span></button>
  </div>
  <div class="fpanel" id="fpanel" hidden>
   <div class="fgroup st"><div class="fl">Status</div><div class="fchecks" id="f-status"></div></div>
   <div class="fgroup"><div class="fl">Type</div><select id="f-arch"></select></div>
   <div class="fgroup"><div class="fl">Channel</div><select id="f-channel"></select></div>
   <div class="fgroup"><div class="fl">Reached at least</div><select id="f-reached"></select></div>
   <div class="fgroup"><div class="fl">Applied</div><select id="f-applied">
    <option value="">Any time</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option></select></div>
  </div>
  <div class="pills" id="pills"></div>
  <table>
   <thead><tr>
    <th data-k="company">Company</th><th data-k="archetype">Type</th>
    <th data-k="date">Date</th><th data-k="score">Match</th>
    <th data-k="status">Status</th><th data-k="stage_reached">Reached</th><th>Notes</th><th></th>
   </tr></thead>
   <tbody id="tbody"></tbody>
  </table>
  <div class="foot" id="foot"></div>
 </div>
</div>
<div class="loading" id="loading">Loading from local database...</div>
</div>
<script>
const STATUSES=["prepped","unconfirmed","applied","screen","interview","onsite","offer","hold","rejected","withdrawn"];
const ACTIVE=["applied","screen","interview","onsite"];
const STAGES=["applied","screen","interview","onsite","offer"];
const RANK={applied:0,screen:1,interview:2,onsite:3,offer:4};
const COLOR={prepped:"#0ea5e9",hold:"#a16207",unconfirmed:"#9aa3af",applied:"#3b82f6",screen:"#6366f1",interview:"#f59e0b",onsite:"#8b5cf6",offer:"#10b981",rejected:"#ef4444",withdrawn:"#94a3b8"};
let data=[], filter=emptyFilter(), sort={k:"date",dir:-1}, pending=0;

function setSync(s,m){const d=document.getElementById("dot"),t=document.getElementById("synctext");
 d.className="dot"+(s==="busy"?" busy":s==="err"?" err":"");t.textContent=m;}
function api(method,path,body){
 return fetch(path,{method,headers:{"Content-Type":"application/json"},body:body?JSON.stringify(body):undefined})
  .then(r=>{if(!r.ok)throw new Error(r.status);return r.json();});
}
function load(silent){
 if(!silent)setSync("busy","syncing...");
 api("GET","/api/rows").then(d=>{
  data=d;document.getElementById("loading").style.display="none";
  document.getElementById("app").style.display="block";
  setSync("ok","synced "+new Date().toLocaleTimeString());render();
 }).catch(()=>setSync("err","server offline - is funnel.py running?"));
}
function write(path,body){
 pending++;setSync("busy","saving...");
 api("POST",path,body).then(()=>{pending--;if(!pending)setSync("ok","saved "+new Date().toLocaleTimeString());})
  .catch(()=>{pending--;setSync("err","save failed");});
}
function counts(){const c={};STATUSES.forEach(s=>c[s]=0);data.forEach(r=>c[r.status]=(c[r.status]||0)+1);return c;}

function render(){
 const c=counts();
 // A withdrawn row that reached a screen or later was submitted first, so it counts as submitted.
 const wSent=data.filter(r=>r.status==="withdrawn"&&(RANK[r.stage_reached]||0)>0).length;
 const submitted=c.applied+c.screen+c.interview+c.onsite+c.offer+c.rejected+wSent;
 // Pipeline depth uses stage_reached (furthest stage ever attained), not status:
 // status collapses history, so a rejected-after-interview app would vanish from these counts.
 const reach=t=>data.filter(r=>(RANK[r.stage_reached]||0)>=RANK[t]).length;
 const screenP=reach("screen"), interviewP=reach("interview"), onsiteP=reach("onsite"), offers=reach("offer");
 const responses=data.filter(r=>(RANK[r.stage_reached]||0)>0||r.status==="rejected").length;
 const pct=(a,b)=>b?Math.round(a/b*100)+"%":"0%";
 document.getElementById("sub").textContent=
  `${data.length} tracked = ${submitted} submitted + ${c.withdrawn-wSent} never sent (withdrawn)`+
  (c.unconfirmed?` + ${c.unconfirmed} unconfirmed`:"")+(c.prepped?` + ${c.prepped} prepped`:"")+(c.hold?` + ${c.hold} on hold`:"")+`  ·  source of truth: funnel.sqlite`;
 const kpis=[
  ["Submitted",submitted,"entered pipeline"],["Unconfirmed",c.unconfirmed,"verify if sent"],
  ["Response rate",pct(responses,submitted),`${responses} of ${submitted}`],
  ["Interview rate",pct(interviewP,submitted),`${interviewP} reached interview`],
  ["Active now",c.applied+c.screen+c.interview+c.onsite,"in progress"],
  ["Offers",offers,offers?"won":"none yet"],["Rejected",c.rejected,""],["Withdrawn",c.withdrawn,""]];
 document.getElementById("kpis").innerHTML=kpis.map(k=>
  `<div class="kpi"><div class="n">${k[1]}</div><div class="l">${k[0]}</div><div class="d">${k[2]}</div></div>`).join("");
 const stages=[["Submitted",submitted,COLOR.applied,null],["Screen+",screenP,COLOR.screen,submitted],
  ["Interview+",interviewP,COLOR.interview,screenP],["Onsite+",onsiteP,COLOR.onsite,interviewP],["Offer",offers,COLOR.offer,onsiteP]];
 const max=submitted||1;
 document.getElementById("funnel").innerHTML=stages.map(s=>{
  const w=Math.max(s[1]/max*100,2);
  const conv=s[3]==null?`${pct(s[1],max)} of total`:`${pct(s[1],s[3])} from prev`;
  return `<div class="frow"><div class="fname">${s[0]}</div>
   <div class="fbar"><div class="ffill" style="width:${w}%;background:${s[2]}">${s[1]}</div></div>
   <div class="fconv">${conv}</div></div>`;}).join("");
 const dmax=Math.max(...STATUSES.map(s=>c[s]),1);
 document.getElementById("dist").innerHTML=STATUSES.map(s=>
  `<div class="distrow"><div class="dn">${s}</div>
   <div class="db"><div class="df" style="width:${c[s]/dmax*100}%;background:${COLOR[s]}"></div></div>
   <div class="dc">${c[s]}</div></div>`).join("");
 const wk={};
 data.forEach(r=>{if(!r.date)return;const d=new Date(r.date+"T00:00:00");if(isNaN(d))return;
  const key=d.getFullYear()+"-"+d.getMonth()+"-w"+Math.ceil(d.getDate()/7);
  wk[key]=wk[key]||{n:0,lbl:monthWk(d),sort:d.getTime()};wk[key].n++;});
 const wks=Object.values(wk).sort((a,b)=>a.sort-b.sort);const wmax=Math.max(...wks.map(x=>x.n),1);
 document.getElementById("weeks").innerHTML=wks.map(x=>
  `<div class="distrow"><div class="dn" style="width:70px">${x.lbl}</div>
   <div class="db"><div class="df" style="width:${x.n/wmax*100}%;background:${COLOR.applied}"></div></div>
   <div class="dc">${x.n}</div></div>`).join("")||"<div class='foot'>no dated rows</div>";
 renderChips(c);renderSelects();renderTable();
}
function monthWk(d){const m=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][d.getMonth()];return `${m} w${Math.ceil(d.getDate()/7)}`;}
function emptyFilter(){return {statuses:new Set(),q:"",arch:"",channel:"",reached:"",applied:""};}
// Quick views are preset status sets. Anything finer goes through the Filters panel checkboxes.
const VIEWS=[["All",[]],["Active",ACTIVE],["Prepped",["prepped"]],["On hold",["hold"]],["Closed",["rejected","withdrawn"]]];
const sameSet=(st,arr)=>st.size==arr.length&&arr.every(x=>st.has(x));
const norm=v=>(v==null?"":String(v)).trim().toLowerCase();
function renderChips(c){
 const st=filter.statuses,v=document.getElementById("views");
 v.innerHTML=VIEWS.map(([lbl,arr],i)=>`<button class="${sameSet(st,arr)?'on':''}" data-i="${i}">${lbl}<span class="n">${arr.length?arr.reduce((n,s)=>n+(c[s]||0),0):data.length}</span></button>`).join("");
 v.querySelectorAll("button").forEach(b=>b.onclick=()=>{st.clear();VIEWS[+b.dataset.i][1].forEach(x=>st.add(x));render();});
 const fs=document.getElementById("f-status");
 fs.innerHTML=STATUSES.map(s=>`<label class="fcheck"><input type="checkbox" value="${s}" ${st.has(s)?'checked':''}/><span class="sw" style="background:${COLOR[s]}"></span>${s}<span class="n">${c[s]}</span></label>`).join("");
 fs.querySelectorAll("input").forEach(i=>i.onchange=()=>{i.checked?st.add(i.value):st.delete(i.value);render();});
}
function fillSelect(id,values,cur){
 document.getElementById(id).innerHTML=`<option value="">Any</option>`+values.map(v=>`<option value="${esc(v)}" ${cur==v?'selected':''}>${esc(v)}</option>`).join("");
}
// Dropdown options come from the data itself, so new archetypes or channels show up without code changes.
function renderSelects(){
 const uniq=k=>[...new Set(data.map(r=>norm(r[k])).filter(Boolean))].sort();
 fillSelect("f-arch",uniq("archetype"),filter.arch);
 fillSelect("f-channel",uniq("channel"),filter.channel);
 fillSelect("f-reached",STAGES,filter.reached);
 document.getElementById("f-applied").value=filter.applied;
}
// Every active filter shows as a removable pill, so the panel can stay closed.
function renderPills(){
 const pills=[];
 if(filter.statuses.size&&!VIEWS.some(([,a])=>a.length&&sameSet(filter.statuses,a)))
  pills.push(["Status",[...filter.statuses].join(", "),()=>filter.statuses.clear()]);
 if(filter.arch)pills.push(["Type",filter.arch,()=>filter.arch=""]);
 if(filter.channel)pills.push(["Channel",filter.channel,()=>filter.channel=""]);
 if(filter.reached)pills.push(["Reached",filter.reached+"+",()=>filter.reached=""]);
 if(filter.applied)pills.push(["Applied","last "+filter.applied+" days",()=>filter.applied=""]);
 const el=document.getElementById("pills");
 el.innerHTML=pills.map((p,i)=>`<span class="pill">${p[0]}: <b>${esc(p[1])}</b><span class="x" data-i="${i}" title="remove">&times;</span></span>`).join("")+
  (pills.length||filter.q?`<span class="clear" id="f-clear">clear all</span>`:"");
 el.querySelectorAll(".x").forEach(x=>x.onclick=()=>{pills[+x.dataset.i][2]();render();});
 const cl=document.getElementById("f-clear");if(cl)cl.onclick=()=>{filter=emptyFilter();document.getElementById("search").value="";render();};
 const n=(filter.statuses.size?1:0)+[filter.arch,filter.channel,filter.reached,filter.applied].filter(Boolean).length;
 const fc=document.getElementById("fcount");fc.hidden=!n;fc.textContent=n;
 document.getElementById("fbtn").classList.toggle("has",n>0);
}
function daysSince(d){if(!d)return null;const t=(Date.now()-new Date(d+"T00:00:00").getTime())/86400000;return isNaN(t)?null:t;}
function renderTable(){
 let rows=data.slice();
 if(filter.statuses.size)rows=rows.filter(r=>filter.statuses.has(r.status));
 if(filter.q){const q=filter.q.toLowerCase();rows=rows.filter(r=>(r.company+" "+r.role).toLowerCase().includes(q));}
 if(filter.arch)rows=rows.filter(r=>norm(r.archetype)==filter.arch);
 if(filter.channel)rows=rows.filter(r=>norm(r.channel)==filter.channel);
 // "Reached" means at least that deep, same rule the funnel uses. Rows with no recorded stage never match.
 if(filter.reached)rows=rows.filter(r=>r.stage_reached in RANK&&RANK[r.stage_reached]>=RANK[filter.reached]);
 if(filter.applied){const n=+filter.applied;rows=rows.filter(r=>{const d=daysSince(r.date);return d!=null&&d<=n;});}
 rows.sort((a,b)=>{let x=a[sort.k]||"",y=b[sort.k]||"";if(sort.k=="score"){x=a.score||0;y=b.score||0;}return (x>y?1:x<y?-1:0)*sort.dir;});
 const tb=document.getElementById("tbody");
 tb.innerHTML=rows.map(r=>{
  const opts=STATUSES.map(s=>`<option value="${s}" ${r.status==s?'selected':''}>${s}</option>`).join("");
  const stg=r.stage_reached||"applied";
  const stgopts=STAGES.map(s=>`<option value="${s}" ${stg==s?'selected':''}>${s}</option>`).join("");
  return `<tr data-id="${esc(r.id)}">
   <td style="border-left-color:${COLOR[r.status]||'#fff'}"><b>${esc(r.company)}</b><div class="role">${esc(r.role)}</div></td>
   <td>${esc(r.archetype||"")}</td><td>${esc(r.date||"")}</td>
   <td class="match">${r.score?r.score+"%":"-"}</td>
   <td><select class="st" style="background:${COLOR[r.status]||'#999'}">${opts}</select></td>
   <td><select class="stg" style="background:${COLOR[stg]||'#999'}">${stgopts}</select></td>
   <td class="notecell"><input class="noteinput" value="${esc(r.note||'')}" placeholder="add note..."/></td>
   <td><span class="del" title="delete">&times;</span></td>
  </tr>`;}).join("");
 tb.querySelectorAll("tr").forEach(tr=>{
  const id=tr.dataset.id,row=data.find(r=>String(r.id)==String(id));
  tr.querySelector(".st").onchange=e=>{row.status=e.target.value;write("/api/update",{id,field:"status",value:e.target.value});
   // stage_reached only moves forward: setting status to a deeper stage drags it along
   if((RANK[e.target.value]||0)>(RANK[row.stage_reached]||0)){row.stage_reached=e.target.value;write("/api/update",{id,field:"stage_reached",value:e.target.value});}
   render();};
  // stage_reached is a forward-only high-water mark. Lowering it is allowed only as an explicit correction.
  tr.querySelector(".stg").onchange=e=>{const v=e.target.value,cur=row.stage_reached||"applied";
   if((RANK[v]||0)<(RANK[cur]||0)&&!confirm(`Lower "furthest stage reached" from ${cur} to ${v}? Only do this to correct a mistake.`)){e.target.value=cur;return;}
   row.stage_reached=v;write("/api/update",{id,field:"stage_reached",value:v});render();};
  tr.querySelector(".noteinput").onchange=e=>{row.note=e.target.value;write("/api/update",{id,field:"note",value:e.target.value});};
  tr.querySelector(".del").onclick=()=>{if(confirm("Delete "+row.company+"?")){data=data.filter(r=>String(r.id)!=String(id));write("/api/delete",{id});render();}};
 });
 document.getElementById("foot").textContent=`showing ${rows.length} of ${data.length}`;
 renderPills();
}
function esc(s){return(s==null?"":String(s)).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}

document.querySelectorAll("th[data-k]").forEach(th=>th.onclick=()=>{const k=th.dataset.k;sort.dir=(sort.k==k)?-sort.dir:1;sort.k=k;render();});
document.getElementById("search").oninput=e=>{filter.q=e.target.value;renderTable();};
[["f-arch","arch"],["f-channel","channel"],["f-reached","reached"],["f-applied","applied"]].forEach(([id,k])=>
 document.getElementById(id).onchange=e=>{filter[k]=e.target.value;renderTable();});
document.getElementById("fbtn").onclick=()=>{const p=document.getElementById("fpanel");p.hidden=!p.hidden;
 document.getElementById("fbtn").classList.toggle("open",!p.hidden);};
document.getElementById("add").onclick=()=>{
 const company=prompt("Company?");if(!company)return;const role=prompt("Role?")||"";
 const row={id:"x"+Date.now(),company,role,archetype:"",date:new Date().toISOString().slice(0,10),score:null,status:"applied",note:"",channel:"cold",posted_date:null,stage_reached:"applied"};
 data.push(row);write("/api/add",row);render();};
document.getElementById("export").onclick=()=>{
 const h=["company","role","archetype","date","score","status","stage_reached","channel","posted_date","note"];
 const csv=[h.join(",")].concat(data.map(r=>h.map(k=>`"${(r[k]==null?"":r[k]).toString().replace(/"/g,'""')}"`).join(","))).join("\n");
 const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));a.download="application-funnel.csv";a.click();};

// bidirectional: pull DB changes every 5s, unless a field is focused or a write is in flight
setInterval(()=>{
 if(pending)return;
 const f=document.activeElement;
 if(f&&(f.tagName=="INPUT"||f.tagName=="SELECT"))return;
 load(true);
},5000);
load();
</script></body></html>'''


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, HTML, "text/html; charset=utf-8")
        elif self.path == "/api/rows":
            c = db()
            rows = [dict(x) for x in c.execute("SELECT * FROM apps ORDER BY date").fetchall()]
            c.close()
            self._send(200, json.dumps(rows))
        else:
            self._send(404, "{}")

    def do_POST(self):
        ln = int(self.headers.get("Content-Length", 0) or 0)
        try:
            data = json.loads(self.rfile.read(ln) or b"{}")
        except Exception:
            return self._send(400, '{"error":"bad json"}')
        c = db()
        try:
            if self.path == "/api/update" and data.get("field") in COLS:
                c.execute(f"UPDATE apps SET {data['field']}=? WHERE id=?", [data.get("value"), data.get("id")])
            elif self.path == "/api/add":
                vals = [data.get(k) for k in COLS]
                vals[COLS.index("channel")] = data.get("channel") or "cold"
                vals[COLS.index("stage_reached")] = data.get("stage_reached") or "applied"
                c.execute("INSERT OR REPLACE INTO apps VALUES (?,?,?,?,?,?,?,?,?,?,?)", vals)
            elif self.path == "/api/delete":
                c.execute("DELETE FROM apps WHERE id=?", [data.get("id")])
            else:
                c.close()
                return self._send(400, '{"error":"unknown op"}')
            c.commit()
            enforce_stage_invariant(c)
        finally:
            c.close()
        self._send(200, '{"ok":true}')

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    init()
    c = db()
    enforce_stage_invariant(c)
    c.close()
    url = f"http://localhost:{PORT}"
    print(f"\n  Application Funnel running at {url}")
    print(f"  Source of truth: {DB}")
    print(f"  Stop with Ctrl+C\n")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        HTTPServer(("127.0.0.1", PORT), H).serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
