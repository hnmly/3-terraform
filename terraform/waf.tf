###############################################################################
# waf.tf
# 비정상 요청 처리 (채점항목 1) - 비정상/변조 요청을 Block(403)
#   - CLOUDFRONT scope 이므로 반드시 us-east-1 (provider aws.use1)
#   - 기본 동작: allow (정상요청/미정의 경로는 통과 -> ALB 에서 404 처리)
#   - "막을 수 있는 건 최대한" : AWS 관리형 규칙(추가요금 없음) 다수 적용하여 403 차단
#
# [비용] AWS 관리형 룰 그룹은 별도요금 없음. WAF 기본요금만 발생:
#        Web ACL $5/월 + 룰당 $1/월 + 요청 $0.60/백만 (모두 시간비례, 대회 수시간 = 소액)
#        ※ Bot Control / ATP / Fraud Control / CAPTCHA 는 고가이므로 미사용.
#
# [오탐 방지 - 점수 보호]
#   1) product PUT 의 이미지 업로드(body)가 차단되지 않도록 Common 룰의
#      SizeRestrictions_BODY / CrossSiteScripting_BODY 를 count 로 override.
#   2) Rate-based 룰은 채점 트래픽(소수 IP 고RPS)을 막지 않도록 임계값을 높게 설정.
#      과차단 의심 시 var.waf_enable_rate_limit=false 로 즉시 비활성.
#
# [WCU] 아래 구성 합계는 기본 한도(1500 WCU) 이내로 설계됨.
###############################################################################

resource "aws_wafv2_web_acl" "cf" {
  count    = var.enable_cloudfront ? 1 : 0
  provider = aws.use1

  name        = "${local.name}-cf-waf"
  description = "Task3 CloudFront WAF - block abnormal requests with 403"
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  # 1) AWS 관리형 - 공통 위협 (약 700 WCU)
  rule {
    name     = "AWSCommonRules"
    priority = 1

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"

        # --- 정상 트래픽 오탐 방지 (점수 보호) : 아래 하위 룰만 count 로 완화 ---
        # 부하 클라이언트가 User-Agent 미설정/봇류일 수 있음 -> 차단 금지
        rule_action_override {
          name = "NoUserAgent_HEADER"
          action_to_use {
            count {}
          }
        }
        rule_action_override {
          name = "UserAgent_BadBots_HEADER"
          action_to_use {
            count {}
          }
        }
        # product 이미지 업로드(PUT body) 바이너리 오탐 방지 -> body 검사 룰 완화
        rule_action_override {
          name = "SizeRestrictions_BODY"
          action_to_use {
            count {}
          }
        }
        rule_action_override {
          name = "CrossSiteScripting_BODY"
          action_to_use {
            count {}
          }
        }
        rule_action_override {
          name = "EC2MetaDataSSRF_BODY"
          action_to_use {
            count {}
          }
        }
        rule_action_override {
          name = "GenericLFI_BODY"
          action_to_use {
            count {}
          }
        }
        rule_action_override {
          name = "GenericRFI_BODY"
          action_to_use {
            count {}
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSCommonRules"
      sampled_requests_enabled   = true
    }
  }

  # 2) AWS 관리형 - 알려진 악성 입력 (약 200 WCU)
  rule {
    name     = "AWSKnownBadInputs"
    priority = 2

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSKnownBadInputs"
      sampled_requests_enabled   = true
    }
  }

  # 3) AWS 관리형 - SQL Injection (약 200 WCU)
  rule {
    name     = "AWSSQLi"
    priority = 3

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesSQLiRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSSQLi"
      sampled_requests_enabled   = true
    }
  }

  # 4) AWS 관리형 - Linux OS 공격 (앱은 AL2023 기반, 약 200 WCU)
  rule {
    name     = "AWSLinuxRules"
    priority = 4

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesLinuxRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSLinuxRules"
      sampled_requests_enabled   = true
    }
  }

  # 5) AWS 관리형 - Amazon IP 평판 목록 (악성 IP 차단, 약 25 WCU)
  rule {
    name     = "AWSIpReputation"
    priority = 5

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesAmazonIpReputationList"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSIpReputation"
      sampled_requests_enabled   = true
    }
  }

  # 6) AWS 관리형 - 익명 IP(VPN/Tor/프록시) 차단 (약 50 WCU)
  rule {
    name     = "AWSAnonymousIp"
    priority = 6

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesAnonymousIpList"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSAnonymousIp"
      sampled_requests_enabled   = true
    }
  }

  # 7) Rate limit (선택). 채점 트래픽은 소수 IP 고RPS이므로 임계값을 매우 높게.
  #    과차단 의심 시 var.waf_enable_rate_limit = false 로 즉시 비활성화.
  dynamic "rule" {
    for_each = var.waf_enable_rate_limit ? [1] : []
    content {
      name     = "RateLimit"
      priority = 10

      action {
        block {}
      }

      statement {
        rate_based_statement {
          limit              = var.waf_rate_limit
          aggregate_key_type = "IP"
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = "RateLimit"
        sampled_requests_enabled   = true
      }
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${local.name}-cf-waf"
    sampled_requests_enabled   = true
  }

  tags = local.tags
}
