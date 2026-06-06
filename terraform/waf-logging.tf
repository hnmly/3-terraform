###############################################################################
# waf-logging.tf
# WAF 블락 분석용 로깅: 차단(BLOCK)된 요청만 CloudWatch Logs 로 기록(비용 최소화).
#   - 통과(ALLOW) 요청은 앱 access 로그로 분석하므로 WAF 에선 기록 안 함.
#   - CLOUDFRONT scope -> us-east-1 (provider aws.use1)
#   - 로그그룹 이름은 반드시 "aws-waf-logs-" 로 시작해야 함
###############################################################################

resource "aws_cloudwatch_log_group" "waf" {
  count    = var.enable_cloudfront ? 1 : 0
  provider = aws.use1

  name              = "aws-waf-logs-${local.name}-cf"
  retention_in_days = 1
  tags              = local.tags
}

resource "aws_wafv2_web_acl_logging_configuration" "cf" {
  count    = var.enable_cloudfront ? 1 : 0
  provider = aws.use1

  log_destination_configs = [replace(aws_cloudwatch_log_group.waf[0].arn, ":*", "")]
  resource_arn            = aws_wafv2_web_acl.cf[0].arn

  # 차단(BLOCK)된 요청만 기록 (로그량/비용 최소화)
  logging_filter {
    default_behavior = "DROP"
    filter {
      behavior    = "KEEP"
      requirement = "MEETS_ANY"
      condition {
        action_condition {
          action = "BLOCK"
        }
      }
    }
  }
}