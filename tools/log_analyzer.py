#!/usr/bin/env python3
"""
log_analyzer.py - 3과제 로그/오류/블락/알로우 분석 도구

데이터 소스:
  - 앱 access 로그 (user/product/stress, JSON lines)  : kubectl logs  -> "알로우(통과)" 요청, 오류, 지연(SLO)
  - WAF 블락 로그 (CloudWatch Logs)                    : aws logs      -> "블락(403)" 요청

사용 예:
  python log_analyzer.py --since 15m --waf-minutes 15
  python log_analyzer.py --no-waf --since 5m
  python log_analyzer.py --app user --since 30m

요구: kubectl(현재 컨텍스트=apdev-eks), aws CLI (자격증명), python3
"""
import argparse, json, subprocess, sys, time
from collections import Counter, defaultdict
from datetime import datetime, timezone

# SLO 목표 응답시간(ms): 문제 기준
SLO_MS = {"user": 200, "product": 200, "stress": 1000}


def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return p.stdout or ""
    except Exception as e:
        print(f"[warn] command failed: {' '.join(cmd)} :: {e}", file=sys.stderr)
        return ""


def pct(values, q):
    if not values:
        return 0
    s = sorted(values)
    i = min(len(s) - 1, int(round((q / 100.0) * (len(s) - 1))))
    return s[i]


# ---------------- 앱 로그 분석 ----------------
def collect_app_logs(app, namespace, since):
    out = run(["kubectl", "logs", "-n", namespace, "-l", f"app={app}",
               f"--since={since}", "--tail=-1", "--prefix=false"])
    recs = []
    for line in out.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            recs.append(json.loads(line))
        except Exception:
            continue
    return recs


def analyze_app(app, recs, top):
    print(f"\n===== APP [{app}] =====")
    if not recs:
        print("  (로그 없음)")
        return
    # /healthcheck 는 ALB 헬스체크 -> 사용자 트래픽 분석에서 분리
    user_recs = [r for r in recs if r.get("path", "").split("?")[0] != "/healthcheck"]
    hc = len(recs) - len(user_recs)

    total = len(user_recs)
    status = Counter(str(r.get("status")) for r in user_recs)
    err4 = sum(c for s, c in status.items() if s.startswith("4"))
    err5 = sum(c for s, c in status.items() if s.startswith("5"))
    ok2 = sum(c for s, c in status.items() if s.startswith("2"))

    durs = [r.get("dur_ms", 0) for r in user_recs if isinstance(r.get("dur_ms"), (int, float))]
    slo = SLO_MS.get(app, 200)
    within = sum(1 for d in durs if d <= slo)

    # 시간창(RPS 추정)
    ts = []
    for r in user_recs:
        t = r.get("ts")
        if t:
            try:
                ts.append(datetime.fromisoformat(t.replace("Z", "+00:00")))
            except Exception:
                pass
    span = (max(ts) - min(ts)).total_seconds() if len(ts) >= 2 else 0
    rps = (total / span) if span > 0 else 0

    print(f"  사용자요청 {total}건 (+healthcheck {hc}건)  |  관측창 {span:.0f}s  |  평균 {rps:.1f} req/s")
    print(f"  상태분포: " + ", ".join(f"{s}:{c}" for s, c in sorted(status.items())))
    print(f"  성공(2xx) {ok2} ({pctf(ok2,total)})  |  4xx {err4} ({pctf(err4,total)})  |  5xx {err5} ({pctf(err5,total)})")
    if durs:
        print(f"  지연(ms): p50={pct(durs,50)} p90={pct(durs,90)} p99={pct(durs,99)} max={max(durs)}")
        print(f"  SLO(<= {slo}ms) 충족률: {within}/{len(durs)} ({pctf(within,len(durs))})")
    print(f"  Top 경로:")
    for path, c in Counter(r.get("path", "").split("?")[0] for r in user_recs).most_common(top):
        print(f"    {c:>6}  {path}")
    print(f"  Top 클라이언트 IP:")
    for ip, c in Counter(r.get("client_ip", "?") for r in user_recs).most_common(top):
        print(f"    {c:>6}  {ip}")
    # 오류 상위 경로
    errs = [r for r in user_recs if str(r.get("status", "")).startswith(("4", "5"))]
    if errs:
        print(f"  오류 상위 (경로/상태):")
        ec = Counter((r.get("path", "").split("?")[0], r.get("status")) for r in errs)
        for (path, st), c in ec.most_common(top):
            print(f"    {c:>6}  [{st}] {path}")


def pctf(n, d):
    return f"{(100.0*n/d):.1f}%" if d else "0%"


# ---------------- WAF 블락 분석 ----------------
def collect_waf_blocks(log_group, region, minutes):
    start_ms = int((time.time() - minutes * 60) * 1000)
    events = []
    token = None
    for _ in range(20):  # 최대 20페이지
        cmd = ["aws", "logs", "filter-log-events", "--log-group-name", log_group,
               "--region", region, "--start-time", str(start_ms), "--limit", "10000",
               "--output", "json"]
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
    return events


def analyze_waf(events, top):
    print(f"\n===== WAF 블락 분석 (403 차단) =====")
    if not events:
        print("  (차단 로그 없음 - 최근 차단이 없거나 로깅 활성화 직후)")
        return
    print(f"  총 차단(BLOCK): {len(events)}건")
    print(f"  차단 룰(terminatingRuleId) Top:")
    for rid, c in Counter(e.get("terminatingRuleId", "?") for e in events).most_common(top):
        print(f"    {c:>6}  {rid}")
    print(f"  차단 클라이언트 IP Top:")
    for ip, c in Counter(e.get("httpRequest", {}).get("clientIp", "?") for e in events).most_common(top):
        print(f"    {c:>6}  {ip}")
    print(f"  차단 URI Top:")
    for uri, c in Counter(e.get("httpRequest", {}).get("uri", "?") for e in events).most_common(top):
        print(f"    {c:>6}  {uri}")
    print(f"  차단 메서드:")
    for m, c in Counter(e.get("httpRequest", {}).get("httpMethod", "?") for e in events).most_common():
        print(f"    {c:>6}  {m}")


def main():
    ap = argparse.ArgumentParser(description="3과제 로그/오류/블락/알로우 분석")
    ap.add_argument("--namespace", default="apps")
    ap.add_argument("--app", default=None, help="특정 앱만 (user|product|stress)")
    ap.add_argument("--since", default="15m", help="kubectl logs --since (예: 5m, 1h)")
    ap.add_argument("--waf-minutes", type=int, default=15)
    ap.add_argument("--waf-region", default="us-east-1")
    ap.add_argument("--waf-log-group", default="aws-waf-logs-apdev-cf")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--no-app", action="store_true")
    ap.add_argument("--no-waf", action="store_true")
    args = ap.parse_args()

    print("=" * 64)
    print(f"  3과제 로그 분석  ({datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')})")
    print("=" * 64)

    if not args.no_app:
        apps = [args.app] if args.app else ["user", "product", "stress"]
        for app in apps:
            recs = collect_app_logs(app, args.namespace, args.since)
            analyze_app(app, recs, args.top)

    if not args.no_waf:
        events = collect_waf_blocks(args.waf_log_group, args.waf_region, args.waf_minutes)
        analyze_waf(events, args.top)

    print("\n" + "=" * 64)


if __name__ == "__main__":
    main()