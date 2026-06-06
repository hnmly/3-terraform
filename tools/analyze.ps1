# =============================================================================
# analyze.ps1 - 로그 분석 도구 콘솔 래퍼 (UTF-8 출력 자동 설정)
# 사용: .\tools\analyze.ps1 [옵션]
#   예) .\tools\analyze.ps1 --since 30m --waf-minutes 30
#       .\tools\analyze.ps1 --app stress --since 10m
#       .\tools\analyze.ps1 --no-waf
# =============================================================================
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
python "$PSScriptRoot\log_analyzer.py" @args