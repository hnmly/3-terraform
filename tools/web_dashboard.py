#!/usr/bin/env python3
"""
web_dashboard.py - 3과제 로그/오류/블락/알로우 브라우저 대시보드 (+ 진단/처방)
실행:  python tools/web_dashboard.py   ->  http://127.0.0.1:8080
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
    except Exception:
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
        "app": app, "total": total, "rps": round(total / span, 2) if span else 0,
        "status": dict(sorted(status.items())), "ok2": ok2, "e4": e4, "e5": e5,
        "ok_rate": round(100.0 * ok2 / total, 1) if total else 0,
        "err_rate": round(100.0 * (e4 + e5) / total, 1) if total else 0,
        "slo_ms": slo, "p50": pctv(durs, 50), "p90": pctv(durs, 90),
        "p99": pctv(durs, 99), "max": max(durs) if durs else 0,
        "slo_rate": round(100.0 * within / len(durs), 1) if durs else 0,
        "top_ips": Counter(r.get("client_ip", "?") for r in ur).most_common(6),
        "top_errors": Counter((r.get("path", "").split("?")[0], r.get("status"))
                              for r in ur if str(r.get("status", "")).startswith(("4", "5"))).most_common(6),
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
        "by_rule": Counter(e.get("terminatingRuleId", "?") for e in events).most_common(8),
        "by_ip": Counter(e.get("httpRequest", {}).get("clientIp", "?") for e in events).most_common(8),
        "by_uri": Counter(e.get("httpRequest", {}).get("uri", "?") for e in events).most_common(8),
    }


HTML = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>3과제 로그 대시보드</title>
<style>
 :root{--bg:#0b1220;--panel:#151f33;--line:#243248;--muted:#8aa0bd;--txt:#e6edf6}
 *{box-sizing:border-box}
 body{font-family:'Segoe UI','Malgun Gothic',sans-serif;margin:0;background:var(--bg);color:var(--txt)}
 header{background:linear-gradient(90deg,#16223b,#101a2e);padding:14px 22px;display:flex;gap:14px;align-items:center;flex-wrap:wrap;position:sticky;top:0;z-index:9;border-bottom:1px solid var(--line)}
 h1{font-size:17px;margin:0;font-weight:600;letter-spacing:.3px}
 .ctl{display:flex;gap:6px;align-items:center;font-size:13px;color:var(--muted)}
 select,button{background:#22304a;color:var(--txt);border:1px solid var(--line);border-radius:7px;padding:6px 11px;font-size:13px;cursor:pointer}
 button:hover{background:#2c3e5e}
 #status{margin-left:auto;font-size:12px;color:var(--muted)}
 .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;vertical-align:middle}
 .wrap{padding:18px;max-width:1400px;margin:0 auto}
 .sec-title{font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin:6px 2px 10px}
 .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
 .card{background:var(--panel);border-radius:12px;padding:16px;border:1px solid var(--line)}
 .card h2{margin:0 0 12px;font-size:15px;display:flex;justify-content:space-between;align-items:baseline}
 .card h2 .sub{font-size:12px;color:var(--muted);font-weight:400}
 .m{display:flex;justify-content:space-between;padding:5px 0;font-size:13px;border-bottom:1px solid var(--line)}
 .m:last-child{border:0}
 .big{font-size:30px;font-weight:700;line-height:1.1}
 .good{color:#43d685}.warn{color:#f5c451}.bad{color:#ff6b6b}.muted{color:var(--muted)}
 .bar{height:9px;background:#0d1626;border-radius:5px;overflow:hidden;margin:6px 0 2px}
 .bar>div{height:100%;border-radius:5px;transition:width .4s}
 table{width:100%;font-size:12px;border-collapse:collapse;margin-top:4px}
 td{padding:3px 4px;border-bottom:1px solid var(--line);color:#cdd9ea}
 td.n{text-align:right;color:var(--muted);width:55px}
 .diag{display:flex;flex-direction:column;gap:10px}
 .tip{border-left:4px solid;border-radius:8px;padding:10px 13px;background:#101a2e}
 .tip.bad{border-color:#ff6b6b}.tip.warn{border-color:#f5c451}.tip.good{border-color:#43d685}.tip.dim{border-color:#48597a}
 .tip h3{margin:0 0 5px;font-size:14px}
 .tip pre{margin:6px 0 0;background:#0a1322;border:1px solid var(--line);border-radius:6px;padding:8px 10px;font-size:12px;white-space:pre-wrap;color:#bcd0ea;overflow-x:auto}
 .badge{font-size:11px;padding:2px 7px;border-radius:10px;background:#22304a;color:var(--muted)}
</style></head><body>
<header>
 <h1>📊 3과제 로그 대시보드</h1>
 <span class="ctl">기간 <select id="since"><option>5m</option><option selected>15m</option><option>30m</option><option>1h</option></select></span>
 <span class="ctl">자동 <select id="auto"><option value="0">수동</option><option value="10" selected>10초</option><option value="30">30초</option></select></span>
 <button onclick="load()">↻ 새로고침</button>
 <span id="status"></span>
</header>
<div class="wrap">
 <div class="sec-title">진단 & 처방</div>
 <div id="diag" class="diag"></div>
 <div class="sec-title" style="margin-top:22px">애플리케이션</div>
 <div id="apps" class="grid"></div>
 <div class="sec-title" style="margin-top:22px">WAF (블락 / 알로우)</div>
 <div id="waf" class="grid"></div>
</div>
<script>
function cr(v,g,w){return v>=g?'good':(v>=w?'warn':'bad')}
function tbl(rows){return rows.length?'<table>'+rows.map(function(r){return '<tr><td>'+r[0]+'</td><td class=n>'+r[1]+'</td></tr>'}).join('')+'</table>':'<div class=muted style="font-size:12px">없음</div>'}

function diagnose(d){
 var tips=[];
 d.apps.forEach(function(a){
  if(a.total===0){tips.push(['dim',a.app+' · 트래픽 없음','아직 요청이 들어오지 않았습니다. 부하 시작 전이면 정상입니다.']);return;}
  if(a.slo_rate<90){
   tips.push(['bad','⚠ '+a.app+' 응답 지연 높음 — SLO '+a.slo_rate+'% (목표 ≤'+a.slo_ms+'ms, 현재 p99 '+a.p99+'ms)',
    '지연이 SLO를 초과합니다. 처리량을 늘리세요:\n'+
    '1) HPA를 더 공격적으로 (CPU 임계값↓):\n'+
    '   kubectl patch hpa '+a.app+'-hpa -n apps --type=merge -p \'{"spec":{"metrics":[{"type":"Resource","resource":{"name":"cpu","target":{"type":"Utilization","averageUtilization":40}}}]}}\'\n'+
    '2) 최소 replica 상향:  kubectl scale deploy/'+a.app+' -n apps --replicas=4\n'+
    '3) Pending Pod(노드 부족) 확인:  kubectl get pods -n apps | findstr Pending\n'+
    '4) Karpenter 노드 증설 확인:  kubectl get nodeclaim ; kubectl get nodes'])
  }else if(a.slo_rate<99){
   tips.push(['warn','• '+a.app+' SLO 약간 미달 ('+a.slo_rate+'%)','여유를 두려면 replica를 1~2개 늘리거나 HPA 임계값을 조금 낮추세요.'])
  }
  if(a.e5>0){
   tips.push(['bad','⚠ '+a.app+' 5xx 오류 '+a.e5+'건','서버/DB 오류입니다.\n• DB 연결 풀/RDS CPU 확인\n• 로그:  kubectl logs -n apps -l app='+a.app+' --tail=100 | findstr 500\n• RDS 부하면 product는 CloudFront 캐시 TTL↑ 검토'])
  }
  if(a.e4>0 && a.err_rate>=5){
   tips.push(['warn','• '+a.app+' 4xx 비율 높음 ('+a.err_rate+'%)','400=요청 본문 형식 문제 가능 / 404=데이터 미적재(load_user.dump) 또는 캐시된 404.\n• 데이터 확인:  GET 으로 존재해야 할 id 조회\n• dump 적재 여부 점검'])
  }
 })
 var w=d.waf;
 if(w.total>0){
  var hitLegit=w.by_uri.some(function(u){return /^\/(v1\/(user|product|stress)|healthcheck)/.test(u[0])});
  if(hitLegit){
   tips.push(['warn','• WAF가 정상 경로를 차단 중일 수 있음 ('+w.total+'건)','정상 API 경로(/v1/*)가 차단되면 가용성↓. 오탐 룰을 count로 완화:\n• 어떤 룰인지 위 WAF 카드의 "차단 룰" 확인\n• 해당 관리형 룰의 하위 룰을 waf.tf에서 rule_action_override(count) 처리 후 apply'])
  }else{
   tips.push(['good','✓ WAF 정상 차단 ('+w.total+'건)','악성/비정상 요청을 403으로 차단 중입니다. 정상 경로 차단은 없습니다.'])
  }
 }
 if(tips.length===0) tips.push(['good','✓ 이상 징후 없음','모든 앱이 SLO를 충족하고 오류가 없습니다.'])
 return tips
}

function render(d){
 document.getElementById('diag').innerHTML = diagnose(d).map(function(t){
  return '<div class="tip '+t[0]+'"><h3>'+t[1]+'</h3><pre>'+t[2]+'</pre></div>'
 }).join('')
 document.getElementById('apps').innerHTML = d.apps.map(function(a){
  var slo=cr(a.slo_rate,90,70), ok=cr(a.ok_rate,90,70);
  var statusStr=Object.keys(a.status).map(function(k){return k+':'+a.status[k]}).join('  ');
  return '<div class=card><h2>'+a.app+'<span class=sub>'+a.rps+' req/s · '+a.total+'건</span></h2>'
   +'<div class=m><span>성공률(2xx)</span><span class="'+ok+'">'+a.ok_rate+'%</span></div>'
   +'<div class=m><span>SLO ≤'+a.slo_ms+'ms</span><span class="big '+slo+'">'+a.slo_rate+'%</span></div>'
   +'<div class=bar><div class="'+slo+'" style="width:'+a.slo_rate+'%;background:currentColor"></div></div>'
   +'<div class=m><span>지연 p50/p90/p99/max</span><span>'+a.p50+'/'+a.p90+'/'+a.p99+'/'+a.max+'ms</span></div>'
   +'<div class=m><span>오류 4xx / 5xx</span><span>'+a.e4+' / '+a.e5+'</span></div>'
   +'<div class="m muted" style="font-size:12px"><span>상태</span><span>'+statusStr+'</span></div>'
   +(a.top_errors.length?'<div class="muted" style="font-size:12px;margin-top:8px">오류 상위</div>'+tbl(a.top_errors.map(function(e){return ['['+e[0][1]+'] '+e[0][0],e[1]]})):'')
   +'<div class="muted" style="font-size:12px;margin-top:8px">Top IP</div>'+tbl(a.top_ips)
   +'</div>'
 }).join('')
 var w=d.waf;
 document.getElementById('waf').innerHTML =
  '<div class=card><h2>WAF 블락(403)<span class=sub>'+w.total+'건 차단</span></h2>'
  +'<div class="muted" style="font-size:12px">차단 룰</div>'+tbl(w.by_rule)
  +'<div class="muted" style="font-size:12px;margin-top:8px">차단 IP</div>'+tbl(w.by_ip)
  +'<div class="muted" style="font-size:12px;margin-top:8px">차단 URI</div>'+tbl(w.by_uri)+'</div>'
  +'<div class=card><h2>알로우(통과)<span class=sub>앱 도달 = WAF 통과</span></h2>'
  +'<div class="muted" style="font-size:12px">앱별 통과 요청 수</div>'
  +tbl(d.apps.map(function(a){return [a.app, a.total]}))
  +'<div class="muted" style="font-size:11px;margin-top:10px">* 통과(알로우) 요청은 앱 access 로그 기준입니다.</div></div>'
}

function setStatus(txt,color){document.getElementById('status').innerHTML='<span class="dot" style="background:'+color+'"></span>'+txt}

async function load(){
 setStatus('불러오는 중...', '#f5c451')
 var since=document.getElementById('since').value;
 try{
  var r=await fetch('/api/data?since='+since+'&waf_minutes='+parseInt(since));
  var d=await r.json();
  localStorage.setItem('dash', JSON.stringify(d));
  render(d);
  setStatus('갱신 '+new Date().toLocaleTimeString(), '#43d685')
 }catch(e){ setStatus('연결 오류 (이전 데이터 표시 중)', '#ff6b6b') }
}
var timer=null;
function setAuto(){if(timer)clearInterval(timer);var s=+document.getElementById('auto').value;if(s)timer=setInterval(load,s*1000)}
document.getElementById('auto').onchange=setAuto;
document.getElementById('since').onchange=load;
// 새로고침해도 직전 스냅샷 즉시 표시 후 갱신
try{var c=localStorage.getItem('dash'); if(c) render(JSON.parse(c));}catch(e){}
load(); setAuto();
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
            data = {"apps": [app_stats(a, since) for a in ("user", "product", "stress")],
                    "waf": waf_stats(wm)}
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
        pass  # 브라우저 연결 종료 등은 조용히 무시


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
    print(bar)
    print("  3과제 로그 대시보드")
    print(f"  ▶  http://127.0.0.1:{a.port}")
    print("  종료: Ctrl+C")
    print(bar)
    try:
        Server(("127.0.0.1", a.port), H).serve_forever()
    except KeyboardInterrupt:
        print("\n  종료되었습니다.")


if __name__ == "__main__":
    main()