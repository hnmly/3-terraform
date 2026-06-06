#!/usr/bin/env python3
"""
web_dashboard.py - 3과제 로그/오류/블락/알로우 브라우저 대시보드

실행:  python tools/web_dashboard.py   (기본 http://127.0.0.1:8080)
옵션:  --port 8080  --namespace apps  --waf-log-group aws-waf-logs-apdev-cf  --waf-region us-east-1
브라우저에서 http://localhost:8080 접속. 상단에서 기간 선택, 자동 새로고침.
요구: kubectl(컨텍스트=apdev-eks), aws CLI, python3
"""
import argparse, json, subprocess, sys, time
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

SLO_MS = {"user": 200, "product": 200, "stress": 1000}
CFG = {"namespace": "apps", "waf_log_group": "aws-waf-logs-apdev-cf", "waf_region": "us-east-1"}


def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return p.stdout or ""
    except Exception as e:
        sys.stderr.write(f"[warn] {e}\n")
        return ""


def pctv(values, q):
    if not values:
        return 0
    s = sorted(values); i = min(len(s) - 1, int(round((q / 100.0) * (len(s) - 1))))
    return s[i]


def collect_app(app, since):
    out = run(["kubectl", "logs", "-n", CFG["namespace"], "-l", f"app={app}",
               f"--since={since}", "--tail=-1", "--prefix=false"])
    recs = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                recs.append(json.loads(line))
            except Exception:
                pass
    return recs


def app_stats(app, since):
    recs = collect_app(app, since)
    ur = [r for r in recs if r.get("path", "").split("?")[0] != "/healthcheck"]
    hc = len(recs) - len(ur)
    total = len(ur)
    status = Counter(str(r.get("status")) for r in ur)
    ok2 = sum(c for s, c in status.items() if s.startswith("2"))
    e4 = sum(c for s, c in status.items() if s.startswith("4"))
    e5 = sum(c for s, c in status.items() if s.startswith("5"))
    durs = [r.get("dur_ms", 0) for r in ur if isinstance(r.get("dur_ms"), (int, float))]
    slo = SLO_MS.get(app, 200)
    within = sum(1 for d in durs if d <= slo)
    ts = []
    for r in ur:
        t = r.get("ts")
        if t:
            try:
                ts.append(datetime.fromisoformat(t.replace("Z", "+00:00")))
            except Exception:
                pass
    span = (max(ts) - min(ts)).total_seconds() if len(ts) >= 2 else 0
    return {
        "app": app, "total": total, "healthcheck": hc,
        "rps": round(total / span, 2) if span else 0, "span": round(span),
        "status": dict(sorted(status.items())),
        "ok2": ok2, "e4": e4, "e5": e5,
        "ok_rate": round(100.0 * ok2 / total, 1) if total else 0,
        "err_rate": round(100.0 * (e4 + e5) / total, 1) if total else 0,
        "slo_ms": slo,
        "p50": pctv(durs, 50), "p90": pctv(durs, 90), "p99": pctv(durs, 99),
        "max": max(durs) if durs else 0,
        "slo_rate": round(100.0 * within / len(durs), 1) if durs else 0,
        "top_paths": Counter(r.get("path", "").split("?")[0] for r in ur).most_common(8),
        "top_ips": Counter(r.get("client_ip", "?") for r in ur).most_common(8),
        "top_errors": Counter((r.get("path", "").split("?")[0], r.get("status"))
                              for r in ur if str(r.get("status", "")).startswith(("4", "5"))).most_common(8),
    }


def waf_stats(minutes):
    start_ms = int((time.time() - minutes * 60) * 1000)
    events, token = [], None
    for _ in range(20):
        cmd = ["aws", "logs", "filter-log-events", "--log-group-name", CFG["waf_log_group"],
               "--region", CFG["waf_region"], "--start-time", str(start_ms), "--limit", "10000", "--output", "json"]
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
                events.append(json.loads(e["message"]))
            except Exception:
                pass
        token = data.get("nextToken")
        if not token:
            break
    return {
        "total": len(events),
        "by_rule": Counter(e.get("terminatingRuleId", "?") for e in events).most_common(10),
        "by_ip": Counter(e.get("httpRequest", {}).get("clientIp", "?") for e in events).most_common(10),
        "by_uri": Counter(e.get("httpRequest", {}).get("uri", "?") for e in events).most_common(10),
        "by_method": Counter(e.get("httpRequest", {}).get("httpMethod", "?") for e in events).most_common(),
    }


HTML = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>3과제 로그 대시보드</title>
<style>
 body{font-family:Segoe UI,Malgun Gothic,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}
 header{background:#1e293b;padding:12px 20px;display:flex;gap:16px;align-items:center;flex-wrap:wrap;position:sticky;top:0}
 h1{font-size:18px;margin:0}
 select,button{background:#334155;color:#e2e8f0;border:1px solid #475569;border-radius:6px;padding:6px 10px}
 .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:14px;padding:16px}
 .card{background:#1e293b;border-radius:10px;padding:14px;border:1px solid #334155}
 .card h2{margin:0 0 10px;font-size:15px;display:flex;justify-content:space-between}
 .m{display:flex;justify-content:space-between;padding:3px 0;font-size:13px;border-bottom:1px solid #273449}
 .big{font-size:26px;font-weight:700}
 .good{color:#4ade80}.warn{color:#fbbf24}.bad{color:#f87171}.dim{color:#94a3b8}
 table{width:100%;font-size:12px;border-collapse:collapse;margin-top:6px}
 td{padding:2px 4px;border-bottom:1px solid #273449}
 td.n{text-align:right;color:#94a3b8;width:60px}
 .bar{height:8px;background:#334155;border-radius:4px;overflow:hidden;margin-top:4px}
 .bar>div{height:100%}
 #ts{font-size:12px;color:#94a3b8;margin-left:auto}
</style></head><body>
<header>
 <h1>3과제 로그 대시보드</h1>
 기간 <select id="since"><option>5m</option><option selected>15m</option><option>30m</option><option>1h</option></select>
 새로고침 <select id="auto"><option value="0">수동</option><option value="10" selected>10초</option><option value="30">30초</option></select>
 <button onclick="load()">새로고침</button>
 <span id="ts"></span>
</header>
<div id="root" class="grid"></div>
<script>
function colorRate(v,good,warn){return v>=good?'good':(v>=warn?'warn':'bad')}
function tbl(rows){return '<table>'+rows.map(r=>'<tr><td>'+r[0]+'</td><td class=n>'+r[1]+'</td></tr>').join('')+'</table>'}
function appCard(a){
 var slo=colorRate(a.slo_rate,90,70), ok=colorRate(a.ok_rate,90,70);
 return '<div class=card><h2>'+a.app+' <span class=dim>'+a.rps+' req/s · '+a.total+'건</span></h2>'
 +'<div class=m><span>성공률(2xx)</span><span class="'+ok+'">'+a.ok_rate+'%</span></div>'
 +'<div class=m><span>오류율(4xx/5xx)</span><span>'+a.e4+' / '+a.e5+'</span></div>'
 +'<div class=m><span>SLO ≤'+a.slo_ms+'ms 충족</span><span class="big '+slo+'">'+a.slo_rate+'%</span></div>'
 +'<div class=m><span>지연 p50/p90/p99/max</span><span>'+a.p50+'/'+a.p90+'/'+a.p99+'/'+a.max+' ms</span></div>'
 +'<div class=bar><div class="'+slo+'" style="width:'+a.slo_rate+'%;background:currentColor"></div></div>'
 +(a.top_errors.length?'<div class=dim style="margin-top:8px">오류 상위</div>'+tbl(a.top_errors.map(e=>['['+e[0][1]+'] '+e[0][0],e[1]])):'')
 +'<div class=dim style="margin-top:8px">Top IP</div>'+tbl(a.top_ips)
 +'</div>';
}
function wafCard(w){
 return '<div class=card><h2>WAF 블락(403) <span class=dim>'+w.total+'건</span></h2>'
 +'<div class=dim>차단 룰</div>'+tbl(w.by_rule)
 +'<div class=dim style="margin-top:8px">차단 IP</div>'+tbl(w.by_ip)
 +'<div class=dim style="margin-top:8px">차단 URI</div>'+tbl(w.by_uri)
 +'</div>';
}
async function load(){
 document.getElementById('ts').textContent='불러오는 중...';
 var since=document.getElementById('since').value;
 try{
  var r=await fetch('/api/data?since='+since+'&waf_minutes='+parseInt(since)); var d=await r.json();
  var html=d.apps.map(appCard).join('')+wafCard(d.waf);
  document.getElementById('root').innerHTML=html;
  document.getElementById('ts').textContent='갱신: '+new Date().toLocaleTimeString();
 }catch(e){document.getElementById('ts').textContent='오류: '+e}
}
var timer=null;
function setAuto(){if(timer)clearInterval(timer);var s=+document.getElementById('auto').value;if(s)timer=setInterval(load,s*1000);}
document.getElementById('auto').onchange=setAuto;
document.getElementById('since').onchange=load;
load();setAuto();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            self._send(200, "text/html; charset=utf-8", HTML.encode("utf-8"))
        elif u.path == "/api/data":
            q = parse_qs(u.query)
            since = q.get("since", ["15m"])[0]
            wm = int(q.get("waf_minutes", ["15"])[0])
            data = {"apps": [app_stats(a, since) for a in ("user", "product", "stress")],
                    "waf": waf_stats(wm),
                    "generated": datetime.now(timezone.utc).astimezone().isoformat()}
            self._send(200, "application/json; charset=utf-8", json.dumps(data).encode("utf-8"))
        else:
            self._send(404, "text/plain", b"not found")

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


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
    print(f"  대시보드:  http://127.0.0.1:{a.port}")
    print("  종료: Ctrl+C")
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()