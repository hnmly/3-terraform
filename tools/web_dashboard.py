#!/usr/bin/env python3
"""3과제 로그 대시보드 (탭/그래프/앱별 로그/차단·통과 상세)"""
import argparse, json, subprocess, time
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

SLO_MS = {"user": 200, "product": 200, "stress": 1000}
CFG = {"namespace": "apps", "waf_log_group": "aws-waf-logs-apdev-cf", "waf_region": "us-east-1"}
APPS = ("user", "product", "stress")


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout or ""
    except Exception:
        return ""


def pctv(v, q):
    if not v:
        return 0
    s = sorted(v)
    return s[min(len(s) - 1, int(round(q / 100.0 * (len(s) - 1))))]


def ep(t):
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def series(recs, nb=40):
    eps = [e for e in (ep(r.get("ts", "")) for r in recs) if e]
    if len(eps) < 2:
        return []
    lo, hi = min(eps), max(eps)
    w = (hi - lo) / nb or 1
    bk = [{"t": int(lo + i * w), "total": 0, "ok": 0, "e4": 0, "e5": 0, "durs": []} for i in range(nb)]
    for r in recs:
        e = ep(r.get("ts", ""))
        if not e:
            continue
        b = bk[min(nb - 1, int((e - lo) / w))]
        b["total"] += 1
        st = str(r.get("status", ""))
        b["ok"] += st.startswith("2")
        b["e4"] += st.startswith("4")
        b["e5"] += st.startswith("5")
        d = r.get("dur_ms")
        if isinstance(d, (int, float)):
            b["durs"].append(d)
    return [{"t": b["t"], "total": b["total"], "ok": b["ok"], "e4": b["e4"], "e5": b["e5"], "p95": pctv(b["durs"], 95)} for b in bk]


def collect_app(app, since):
    out = run(["kubectl", "logs", "-n", CFG["namespace"], "-l", "app=" + app, "--since=" + since, "--tail=-1", "--prefix=false"])
    recs = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                recs.append(json.loads(line))
            except Exception:
                pass
    return recs


def app_detail(app, since):
    recs = collect_app(app, since)
    ur = [r for r in recs if r.get("path", "").split("?")[0] != "/healthcheck"]
    total = len(ur)
    status = Counter(str(r.get("status")) for r in ur)
    ok2 = sum(c for s, c in status.items() if s.startswith("2"))
    e4 = sum(c for s, c in status.items() if s.startswith("4"))
    e5 = sum(c for s, c in status.items() if s.startswith("5"))
    durs = [r.get("dur_ms", 0) for r in ur if isinstance(r.get("dur_ms"), (int, float))]
    slo = SLO_MS.get(app, 200)
    within = sum(1 for d in durs if d <= slo)
    eps = [e for e in (ep(r.get("ts", "")) for r in ur) if e]
    span = (max(eps) - min(eps)) if len(eps) >= 2 else 0
    ok_paths = Counter(r.get("path", "").split("?")[0] for r in ur if str(r.get("status", "")).startswith("2")).most_common(12)
    err_paths = Counter((r.get("path", "").split("?")[0], r.get("status")) for r in ur if str(r.get("status", "")).startswith(("4", "5"))).most_common(12)
    recent = [{"ts": r.get("ts", "")[11:23], "method": r.get("method"), "path": r.get("path"),
               "status": r.get("status"), "dur": r.get("dur_ms"), "ip": r.get("client_ip")} for r in ur[-80:]][::-1]
    return {"app": app, "total": total, "rps": round(total / span, 2) if span else 0,
            "status": dict(sorted(status.items())), "ok2": ok2, "e4": e4, "e5": e5,
            "ok_rate": round(100.0 * ok2 / total, 1) if total else 0,
            "err_rate": round(100.0 * (e4 + e5) / total, 1) if total else 0,
            "slo_ms": slo, "p50": pctv(durs, 50), "p90": pctv(durs, 90), "p99": pctv(durs, 99), "max": max(durs) if durs else 0,
            "slo_rate": round(100.0 * within / len(durs), 1) if durs else 0,
            "series": series(ur), "ok_paths": ok_paths, "err_paths": err_paths,
            "top_ips": Counter(r.get("client_ip", "?") for r in ur).most_common(8), "recent": recent}


def waf_detail(minutes):
    start_ms = int((time.time() - minutes * 60) * 1000)
    ev, token = [], None
    for _ in range(20):
        cmd = ["aws", "logs", "filter-log-events", "--log-group-name", CFG["waf_log_group"], "--region", CFG["waf_region"],
               "--start-time", str(start_ms), "--limit", "10000", "--output", "json"]
        if token:
            cmd += ["--next-token", token]
        out = run(cmd)
        if not out:
            break
        try:
            data = json.loads(out)
        except Exception:
            break
        for e in data.get("events", []):
            try:
                ev.append(json.loads(e["message"]))
            except Exception:
                pass
        token = data.get("nextToken")
        if not token:
            break
    def g(e, *k):
        x = e
        for kk in k:
            x = x.get(kk, {}) if isinstance(x, dict) else {}
        return x if x not in ({}, None) else "?"
    times = sorted(e.get("timestamp", 0) for e in ev)
    sr = []
    if len(times) >= 2:
        lo, hi = times[0], times[-1]
        nb = 40
        w = (hi - lo) / nb or 1
        cnt = [0] * nb
        for e in ev:
            cnt[min(nb - 1, int((e.get("timestamp", lo) - lo) / w))] += 1
        sr = [{"t": int((lo + i * w) / 1000), "block": cnt[i]} for i in range(nb)]
    recent = [{"ts": datetime.fromtimestamp(e.get("timestamp", 0) / 1000, timezone.utc).astimezone().strftime("%H:%M:%S"),
               "ip": g(e, "httpRequest", "clientIp"), "method": g(e, "httpRequest", "httpMethod"),
               "uri": g(e, "httpRequest", "uri"), "rule": e.get("terminatingRuleId", "?")} for e in ev[-80:]][::-1]
    return {"total": len(ev),
            "by_rule": Counter(e.get("terminatingRuleId", "?") for e in ev).most_common(10),
            "by_ip": Counter(g(e, "httpRequest", "clientIp") for e in ev).most_common(10),
            "by_uri": Counter(g(e, "httpRequest", "uri") for e in ev).most_common(10),
            "by_method": Counter(g(e, "httpRequest", "httpMethod") for e in ev).most_common(),
            "series": sr, "recent": recent}

def cluster_detail():
    ns = CFG["namespace"]
    pods = []
    for ln in run(["kubectl", "top", "pods", "-n", ns, "--no-headers"]).splitlines():
        x = ln.split()
        if len(x) >= 3:
            pods.append({"name": x[0], "cpu": x[1], "mem": x[2]})
    ntop = {}
    for ln in run(["kubectl", "top", "nodes", "--no-headers"]).splitlines():
        x = ln.split()
        if len(x) >= 5:
            ntop[x[0]] = {"cpu": x[1], "cpu_pct": x[2], "mem": x[3], "mem_pct": x[4]}
    nodes = []
    try:
        nj = json.loads(run(["kubectl", "get", "nodes", "-o", "json"]) or "{}")
    except Exception:
        nj = {}
    for it in nj.get("items", []):
        nm = it["metadata"]["name"]
        lab = it["metadata"].get("labels", {})
        ready = "?"
        for cc in it.get("status", {}).get("conditions", []):
            if cc.get("type") == "Ready":
                ready = "Ready" if cc.get("status") == "True" else "NotReady"
        t = ntop.get(nm, {})
        nodes.append({"name": nm, "type": lab.get("node.kubernetes.io/instance-type", "?"),
                      "karpenter": "karpenter.sh/nodepool" in lab, "ready": ready,
                      "cpu": t.get("cpu", "-"), "cpu_pct": t.get("cpu_pct", "-"),
                      "mem": t.get("mem", "-"), "mem_pct": t.get("mem_pct", "-")})
    hpas = []
    try:
        hj = json.loads(run(["kubectl", "get", "hpa", "-n", ns, "-o", "json"]) or "{}")
    except Exception:
        hj = {}
    for it in hj.get("items", []):
        sp = it.get("spec", {})
        st = it.get("status", {})
        cur = "-"
        for m in (st.get("currentMetrics") or []):
            r = m.get("resource", {})
            if r.get("name") == "cpu":
                cur = str(r.get("current", {}).get("averageUtilization", "?")) + "%"
        tgt = "-"
        for m in (sp.get("metrics") or []):
            r = m.get("resource", {})
            if r.get("name") == "cpu":
                tgt = str(r.get("target", {}).get("averageUtilization", "?")) + "%"
        hpas.append({"name": it["metadata"]["name"], "cur": cur, "tgt": tgt,
                     "min": sp.get("minReplicas"), "max": sp.get("maxReplicas"),
                     "replicas": st.get("currentReplicas")})
    ncs = []
    try:
        ncj = json.loads(run(["kubectl", "get", "nodeclaim", "-o", "json"]) or "{}")
    except Exception:
        ncj = {}
    for it in ncj.get("items", []):
        lab = it["metadata"].get("labels", {})
        ready = "?"
        for cc in it.get("status", {}).get("conditions", []):
            if cc.get("type") == "Ready":
                ready = "Ready" if cc.get("status") == "True" else str(cc.get("status"))
        ncs.append({"name": it["metadata"]["name"], "type": lab.get("node.kubernetes.io/instance-type", "?"),
                    "cap": lab.get("karpenter.sh/capacity-type", "?"), "ready": ready,
                    "node": it.get("status", {}).get("nodeName", "-")})
    return {"pods": pods, "nodes": nodes, "hpa": hpas, "nodeclaims": ncs}


HTML = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>3과제 로그 대시보드</title>
<style>
 :root{--bg:#070b14;--panel:#0f1626;--panel2:#131c30;--line:#1f2c44;--muted:#7e93b4;--txt:#e8eefb;--accent:#5b8cff}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--txt);font-family:'Segoe UI','Malgun Gothic',sans-serif;font-size:14px}
 header{background:rgba(10,16,28,.85);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:12px 24px;display:flex;align-items:center;gap:18px;position:sticky;top:0;z-index:20}
 header h1{font-size:16px;font-weight:600;margin:0;letter-spacing:.4px}
 .ctl{display:flex;align-items:center;gap:7px;color:var(--muted);font-size:13px}
 select,button{background:var(--panel2);color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:7px 12px;font-size:13px;cursor:pointer;outline:none}
 button:hover{border-color:var(--accent)}
 #status{margin-left:auto;font-size:12px;color:var(--muted)}
 .dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px}
 nav{display:flex;gap:4px;padding:14px 24px 0;flex-wrap:wrap}
 nav .tab{padding:9px 18px;border-radius:9px 9px 0 0;background:transparent;border:1px solid transparent;color:var(--muted);cursor:pointer;font-size:13px;font-weight:500}
 nav .tab:hover{color:var(--txt)}
 nav .tab.on{background:var(--panel);border-color:var(--line);border-bottom-color:var(--panel);color:var(--txt)}
 main{padding:0 24px 40px}
 .panelbar{border-top:1px solid var(--line);margin-top:-1px}
 .wrap{padding:20px 0}
 .grid{display:grid;gap:16px}
 .g2{grid-template-columns:repeat(auto-fit,minmax(380px,1fr))}
 .g3{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
 .g4{grid-template-columns:repeat(auto-fit,minmax(230px,1fr))}
 .card{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--line);border-radius:14px;padding:18px}
 .card h2{margin:0 0 14px;font-size:14px;font-weight:600;display:flex;justify-content:space-between;align-items:baseline;color:#cdd9ef}
 .card h2 .sub{font-size:12px;color:var(--muted);font-weight:400}
 .kpi{font-size:34px;font-weight:700;line-height:1}
 .kpi.sm{font-size:22px}
 .lbl{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px}
 .row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--line);font-size:13px}
 .row:last-child{border:0}
 .good{color:#46e3a0}.warn{color:#ffcb57}.bad{color:#ff6b81}.muted{color:var(--muted)}
 .bar{height:8px;background:#0a1220;border-radius:5px;overflow:hidden;margin:8px 0 4px}
 .bar>div{height:100%;border-radius:5px;transition:width .5s}
 table{width:100%;border-collapse:collapse;font-size:12.5px}
 th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
 th{color:var(--muted);font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.5px}
 td.n{text-align:right;color:var(--muted);font-variant-numeric:tabular-nums}
 .pill{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600}
 .p2{background:rgba(70,227,160,.15);color:#46e3a0}.p4{background:rgba(255,203,87,.15);color:#ffcb57}.p5{background:rgba(255,107,129,.15);color:#ff6b81}
 .logbox{background:#060a12;border:1px solid var(--line);border-radius:10px;max-height:460px;overflow:auto;font-family:Consolas,monospace;font-size:12px}
 .logbox table{font-family:Consolas,monospace}
 .tip{border-left:3px solid;border-radius:10px;padding:13px 16px;background:var(--panel);margin-bottom:11px}
 .tip.bad{border-color:#ff6b81}.tip.warn{border-color:#ffcb57}.tip.good{border-color:#46e3a0}.tip.dim{border-color:#3b4d70}
 .tip h3{margin:0 0 6px;font-size:13.5px;font-weight:600}
 .tip pre{margin:8px 0 0;background:#060a12;border:1px solid var(--line);border-radius:8px;padding:10px 12px;font-size:12px;white-space:pre-wrap;color:#bcd0ef;overflow-x:auto}
 canvas{width:100%;height:200px;display:block}
 .legend{display:flex;gap:14px;font-size:11px;color:var(--muted);margin-top:6px}
 .legend span{display:flex;align-items:center;gap:5px}
 .sw{width:10px;height:10px;border-radius:2px;display:inline-block}
</style></head><body><header>
 <h1>3과제 로그 대시보드</h1>
 <span class="ctl">기간 <select id="since"><option>5m</option><option selected>15m</option><option>30m</option><option>1h</option></select></span>
 <span class="ctl">자동 <select id="auto"><option value="0">수동</option><option value="10" selected>10s</option><option value="30">30s</option></select></span>
 <button onclick="load()">새로고침</button>
 <span id="status"></span>
</header>
<nav id="tabs"></nav>
<main class="panelbar"><div id="view" class="wrap"></div></main>
<script>
var DATA=null, TAB='overview';
var C={ok:'#46e3a0',e4:'#ffcb57',e5:'#ff6b81',line:'#5b8cff',grid:'#1f2c44',mut:'#7e93b4'};
function cr(v,g,w){return v>=g?'good':(v>=w?'warn':'bad')}
function el(h){var d=document.createElement('div');d.innerHTML=h;return d.firstChild}
function fmtRows(rows,cols){var h='<table><tr>'+cols.map(function(c){return '<th'+(c[2]?' style="text-align:right"':'')+'>'+c[0]+'</th>'}).join('')+'</tr>';
 h+=rows.map(function(r){return '<tr>'+cols.map(function(c){return '<td'+(c[2]?' class=n':'')+'>'+c[1](r)+'</td>'}).join('')+'</tr>'}).join('');return h+'</table>'}
function stPill(s){s=''+s;var c=s[0]==='2'?'p2':(s[0]==='4'?'p4':'p5');return '<span class="pill '+c+'">'+s+'</span>'}

function chart(cv,sv,keys,colors,sloLine){
 var ctx=cv.getContext('2d'),W=cv.width=cv.clientWidth*2,H=cv.height=400,pad=36*2;
 ctx.clearRect(0,0,W,H);ctx.scale(1,1);
 if(!sv||!sv.length){ctx.fillStyle=C.mut;ctx.font='24px sans-serif';ctx.fillText('데이터 없음',pad,H/2);return}
 var maxv=1;sv.forEach(function(b){keys.forEach(function(k){if(b[k]>maxv)maxv=b[k]})});
 if(sloLine&&sloLine>maxv)maxv=sloLine*1.1;
 var x0=pad,x1=W-20,y0=20,y1=H-44;
 ctx.strokeStyle=C.grid;ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(x0,y1);ctx.lineTo(x1,y1);ctx.stroke();
 ctx.fillStyle=C.mut;ctx.font='20px sans-serif';
 for(var g=0;g<=4;g++){var yy=y1-(y1-y0)*g/4;ctx.strokeStyle=C.grid;ctx.globalAlpha=.5;ctx.beginPath();ctx.moveTo(x0,yy);ctx.lineTo(x1,yy);ctx.stroke();ctx.globalAlpha=1;ctx.fillText(Math.round(maxv*g/4),4,yy+6)}
 function px(i){return x0+(x1-x0)*i/Math.max(sv.length-1,1)}
 function py(v){return y1-(y1-y0)*Math.min(v,maxv)/maxv}
 if(sloLine){ctx.strokeStyle='#ff6b81';ctx.setLineDash([6,6]);ctx.beginPath();ctx.moveTo(x0,py(sloLine));ctx.lineTo(x1,py(sloLine));ctx.stroke();ctx.setLineDash([])}
 keys.forEach(function(k,ki){ctx.strokeStyle=colors[ki];ctx.lineWidth=3;ctx.beginPath();sv.forEach(function(b,i){var X=px(i),Y=py(b[k]);i?ctx.lineTo(X,Y):ctx.moveTo(X,Y)});ctx.stroke();
  ctx.fillStyle=colors[ki];sv.forEach(function(b,i){ctx.beginPath();ctx.arc(px(i),py(b[k]),3,0,7);ctx.fill()})})
}
function legend(items){return '<div class=legend>'+items.map(function(i){return '<span><span class=sw style="background:'+i[1]+'"></span>'+i[0]+'</span>'}).join('')+'</div>'}

function appCard(a){
 var slo=cr(a.slo_rate,90,70),ok=cr(a.ok_rate,90,70);
 return '<div class=card><div class=lbl>'+a.app+'</div>'
 +'<div class="kpi '+slo+'">'+a.slo_rate+'%</div><div class=muted style="font-size:12px;margin-top:3px">SLO ≤'+a.slo_ms+'ms 충족</div>'
 +'<div class=bar><div class="'+slo+'" style="width:'+a.slo_rate+'%;background:currentColor"></div></div>'
 +'<div class=row><span>요청 / RPS</span><span>'+a.total+' / '+a.rps+'</span></div>'
 +'<div class=row><span>성공률</span><span class="'+ok+'">'+a.ok_rate+'%</span></div>'
 +'<div class=row><span>p50/p90/p99</span><span>'+a.p50+'/'+a.p90+'/'+a.p99+'ms</span></div>'
 +'<div class=row><span>4xx / 5xx</span><span>'+a.e4+' / '+a.e5+'</span></div></div>'
}
function diagnose(d){var t=[];
 d.apps.forEach(function(a){
  if(a.total===0){t.push(['dim',a.app+' · 트래픽 없음','요청이 아직 없습니다.']);return}
  if(a.slo_rate<90)t.push(['bad',a.app+' 응답 지연 높음 — SLO '+a.slo_rate+'% (p99 '+a.p99+'ms, 목표 ≤'+a.slo_ms+'ms)',
   'replica/리소스로 분산하세요:\nkubectl scale deploy/'+a.app+' -n apps --replicas=6\nkubectl patch hpa '+a.app+'-hpa -n apps --type=merge -p \'{"spec":{"metrics":[{"type":"Resource","resource":{"name":"cpu","target":{"type":"Utilization","averageUtilization":35}}}]}}\'\nkubectl get pods -n apps | findstr Pending']);
  else if(a.slo_rate<99)t.push(['warn',a.app+' SLO 약간 미달 ('+a.slo_rate+'%)','replica 1~2개 증설 또는 HPA 임계값 하향 권장.']);
  if(a.e5>0)t.push(['bad',a.app+' 5xx '+a.e5+'건','DB/서버 오류. RDS CPU·커넥션 확인:\nkubectl logs -n apps -l app='+a.app+' --tail=100 | findstr 500']);
  if(a.e4>0&&a.err_rate>=5)t.push(['warn',a.app+' 4xx 비율 '+a.err_rate+'%','400=요청형식 / 404=데이터 미적재(dump)·캐시된404 확인.']);
 });
 var w=d.waf;if(w.total>0){var legit=w.by_uri.some(function(u){return /^\/(v1\/(user|product|stress)|healthcheck)$/.test(u[0])});
  if(legit)t.push(['warn','WAF가 정상 경로 차단 의심 ('+w.total+'건)','정상 /v1/* 차단 시 가용성↓. 해당 룰을 waf.tf에서 count로 완화 후 apply.']);
  else t.push(['good','WAF 정상 차단 ('+w.total+'건)','악성/비정상 요청만 403 차단 중. 정상경로 차단 없음.'])}
 if(!t.length)t.push(['good','이상 없음','모든 앱 SLO 충족, 오류 없음.']);return t}function viewOverview(d){
 var h='<div class=grid style="margin-bottom:16px" class=g3><div class="grid g3">';
 h=d.apps.map(appCard).join('');
 var grid='<div class="grid g3">'+h+'</div>';
 var diag='<div style="margin:22px 0 10px" class=lbl>진단 및 처방</div>'+diagnose(d).map(function(t){return '<div class="tip '+t[0]+'"><h3>'+t[1]+'</h3><pre>'+t[2]+'</pre></div>'}).join('');
 var waf='<div style="margin:22px 0 10px" class=lbl>WAF 요약</div><div class="grid g3"><div class=card><div class=lbl>총 차단(403)</div><div class="kpi bad">'+d.waf.total+'</div></div>'
  +'<div class=card><div class=lbl>통과(앱 도달) 합계</div><div class="kpi good">'+d.apps.reduce(function(s,a){return s+a.total},0)+'</div></div>'
  +'<div class=card><div class=lbl>차단 룰 Top</div>'+fmtRows(d.waf.by_rule.slice(0,5),[['룰',function(r){return r[0]}],['건수',function(r){return r[1]},1]])+'</div></div>';
 return grid+diag+waf;
}
function viewApp(a){
 var slo=cr(a.slo_rate,90,70),ok=cr(a.ok_rate,90,70);
 var kpis='<div class="grid g4">'
  +'<div class=card><div class=lbl>SLO 충족 (≤'+a.slo_ms+'ms)</div><div class="kpi '+slo+'">'+a.slo_rate+'%</div></div>'
  +'<div class=card><div class=lbl>성공률 2xx</div><div class="kpi '+ok+'">'+a.ok_rate+'%</div></div>'
  +'<div class=card><div class=lbl>요청 / RPS</div><div class="kpi sm">'+a.total+' <span class=muted style="font-size:14px">/ '+a.rps+'</span></div></div>'
  +'<div class=card><div class=lbl>p99 / max</div><div class="kpi sm">'+a.p99+' <span class=muted style="font-size:14px">/ '+a.max+'ms</span></div></div></div>';
 var charts='<div class="grid g2" style="margin-top:16px">'
  +'<div class=card><h2>요청 추이 <span class=sub>2xx / 4xx / 5xx</span></h2><canvas id="cReq"></canvas>'+legend([['2xx',C.ok],['4xx',C.e4],['5xx',C.e5]])+'</div>'
  +'<div class=card><h2>지연 p95 추이 <span class=sub>빨강 점선 = SLO</span></h2><canvas id="cLat"></canvas>'+legend([['p95(ms)',C.line],['SLO '+a.slo_ms+'ms','#ff6b81']])+'</div></div>';
 var paths='<div class="grid g2" style="margin-top:16px">'
  +'<div class=card><h2>2xx 경로</h2>'+fmtRows(a.ok_paths,[['경로',function(r){return r[0]}],['건수',function(r){return r[1]},1]])+'</div>'
  +'<div class=card><h2>에러 경로 (4xx/5xx)</h2>'+(a.err_paths.length?fmtRows(a.err_paths,[['상태',function(r){return stPill(r[0][1])}],['경로',function(r){return r[0][0]}],['건수',function(r){return r[1]},1]]):'<div class=muted>에러 없음</div>')+'</div></div>';
 var logs='<div class=card style="margin-top:16px"><h2>최근 로그 <span class=sub>최신 80건</span></h2><div class=logbox>'
  +fmtRows(a.recent,[['시각',function(r){return r.ts}],['M',function(r){return r.method}],['경로',function(r){return r.path}],['상태',function(r){return stPill(r.status)}],['ms',function(r){return r.dur},1],['IP',function(r){return r.ip}]])+'</div></div>';
 return kpis+charts+paths+logs;
}
function viewWaf(d){
 var w=d.waf;
 var kpis='<div class="grid g3"><div class=card><div class=lbl>총 차단(403)</div><div class="kpi bad">'+w.total+'</div></div>'
  +'<div class=card><div class=lbl>통과(앱 도달)</div><div class="kpi good">'+d.apps.reduce(function(s,a){return s+a.total},0)+'</div></div>'
  +'<div class=card><div class=lbl>차단 메서드</div>'+fmtRows(w.by_method,[['메서드',function(r){return r[0]}],['건수',function(r){return r[1]},1]])+'</div></div>';
 var chart='<div class=card style="margin-top:16px"><h2>차단 추이</h2><canvas id="cWaf"></canvas>'+legend([['차단/구간',C.e5]])+'</div>';
 var tb='<div class="grid g3" style="margin-top:16px">'
  +'<div class=card><h2>차단 룰</h2>'+fmtRows(w.by_rule,[['룰',function(r){return r[0]}],['건수',function(r){return r[1]},1]])+'</div>'
  +'<div class=card><h2>차단 IP</h2>'+fmtRows(w.by_ip,[['IP',function(r){return r[0]}],['건수',function(r){return r[1]},1]])+'</div>'
  +'<div class=card><h2>차단 URI</h2>'+fmtRows(w.by_uri,[['URI',function(r){return r[0]}],['건수',function(r){return r[1]},1]])+'</div></div>';
 var logs='<div class=card style="margin-top:16px"><h2>최근 차단 요청 <span class=sub>최신 80건</span></h2><div class=logbox>'
  +(w.recent.length?fmtRows(w.recent,[['시각',function(r){return r.ts}],['M',function(r){return r.method}],['URI',function(r){return r.uri}],['룰',function(r){return r.rule}],['IP',function(r){return r.ip}]]):'<div class=muted style="padding:12px">차단 없음</div>')+'</div></div>';
 return kpis+chart+tb+logs;
}
function viewCluster(d){
 var c=d.cluster;
 var nodes='<div class=card><h2>노드 <span class=sub>'+c.nodes.length+'대</span></h2>'+fmtRows(c.nodes,[
  ['노드',function(r){return r.name.split('.')[0]}],
  ['타입',function(r){return r.type+(r.karpenter?' <span class="pill p2">karpenter</span>':' <span class="pill p4">base</span>')}],
  ['상태',function(r){return r.ready}],
  ['CPU',function(r){return r.cpu+' ('+r.cpu_pct+')'}],
  ['MEM',function(r){return r.mem+' ('+r.mem_pct+')'}]])+'</div>';
 var hpa='<div class=card><h2>HPA</h2>'+fmtRows(c.hpa,[
  ['이름',function(r){return r.name}],
  ['CPU 현재/목표',function(r){return r.cur+' / '+r.tgt}],
  ['min/max',function(r){return r.min+' / '+r.max}],
  ['replicas',function(r){return r.replicas},1]])+'</div>';
 var nc='<div class=card><h2>Karpenter NodeClaim <span class=sub>'+c.nodeclaims.length+'</span></h2>'+
  (c.nodeclaims.length?fmtRows(c.nodeclaims,[
   ['이름',function(r){return r.name}],['타입',function(r){return r.type}],
   ['cap',function(r){return r.cap}],['상태',function(r){return r.ready}],
   ['노드',function(r){return (r.node||'-').split('.')[0]}]]):'<div class=muted style="padding:8px">활성 NodeClaim 없음 (부하 없을 때 정상)</div>')+'</div>';
 var pods='<div class=card style="margin-top:16px"><h2>Pod 리소스 <span class=sub>'+c.pods.length+'개</span></h2><div class=logbox>'+
  (c.pods.length?fmtRows(c.pods,[['Pod',function(r){return r.name}],['CPU',function(r){return r.cpu},1],['MEM',function(r){return r.mem},1]]):'<div class=muted style="padding:8px">metrics-server 수집 대기 중</div>')+'</div></div>';
 return '<div class="grid g2">'+nodes+hpa+'</div><div class="grid g2" style="margin-top:16px">'+nc+'</div>'+pods;
}
function renderTabs(){
 var tabs=[['overview','개요']].concat(DATA.apps.map(function(a){return [a.app,a.app]})).concat([['waf','WAF'],['cluster','클러스터']]);
 document.getElementById('tabs').innerHTML=tabs.map(function(t){return '<div class="tab'+(t[0]===TAB?' on':'')+'" onclick="setTab(\''+t[0]+'\')">'+t[1]+'</div>'}).join('');
}
function draw(){
 if(TAB==='waf'){var c=document.getElementById('cWaf');if(c)chart(c,DATA.waf.series,['block'],[C.e5])}
 else if(TAB!=='overview'){var a=DATA.apps.find(function(x){return x.app===TAB});if(!a)return;
  var r=document.getElementById('cReq');if(r)chart(r,a.series,['ok','e4','e5'],[C.ok,C.e4,C.e5]);
  var l=document.getElementById('cLat');if(l)chart(l,a.series,['p95'],[C.line],a.slo_ms)}
}
function renderView(){
 if(!DATA)return;
 var v=document.getElementById('view');
 if(TAB==='overview')v.innerHTML=viewOverview(DATA);
 else if(TAB==='waf')v.innerHTML=viewWaf(DATA);
 else{var a=DATA.apps.find(function(x){return x.app===TAB});v.innerHTML=a?viewApp(a):''}
 draw();
}
function setTab(t){TAB=t;renderTabs();renderView()}
function setStatus(x,c){document.getElementById('status').innerHTML='<span class=dot style="background:'+c+'"></span>'+x}
async function load(){
 setStatus('불러오는 중','#ffcb57');var since=document.getElementById('since').value;
 try{var r=await fetch('/api/data?since='+since+'&waf_minutes='+parseInt(since));DATA=await r.json();
  localStorage.setItem('dash',JSON.stringify(DATA));renderTabs();renderView();setStatus('갱신 '+new Date().toLocaleTimeString(),'#46e3a0')}
 catch(e){setStatus('연결 오류 (이전 데이터 유지)','#ff6b81')}
}
var timer=null;function setAuto(){if(timer)clearInterval(timer);var s=+document.getElementById('auto').value;if(s)timer=setInterval(load,s*1000)}
document.getElementById('auto').onchange=setAuto;document.getElementById('since').onchange=load;
window.addEventListener('resize',draw);
try{var c=localStorage.getItem('dash');if(c){DATA=JSON.parse(c);renderTabs();renderView()}}catch(e){}
load();setAuto();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            self.close_connection = True

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            self._send(200, "text/html; charset=utf-8", HTML.encode("utf-8"))
        elif u.path == "/api/data":
            q = parse_qs(u.query)
            since = q.get("since", ["15m"])[0]
            wm = int(q.get("waf_minutes", ["15"])[0])
            data = {"apps": [app_detail(a, since) for a in APPS], "waf": waf_detail(wm), "cluster": cluster_detail()}
            self._send(200, "application/json; charset=utf-8", json.dumps(data).encode("utf-8"))
        else:
            self._send(404, "text/plain", b"not found")

    def _send(self, code, ctype, body):
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--namespace", default="apps")
    ap.add_argument("--waf-log-group", default="aws-waf-logs-apdev-cf")
    ap.add_argument("--waf-region", default="us-east-1")
    a = ap.parse_args()
    CFG["namespace"] = a.namespace
    CFG["waf_log_group"] = a.waf_log_group
    CFG["waf_region"] = a.waf_region
    bar = "-" * 52
    print(bar + "\n  3과제 로그 대시보드\n  http://127.0.0.1:%d\n  Ctrl+C 로 종료\n" % a.port + bar)
    try:
        Server(("127.0.0.1", a.port), H).serve_forever()
    except KeyboardInterrupt:
        print("\n  종료되었습니다.")


if __name__ == "__main__":
    main()