###############################################################################
# cloudfront.tf
# 단일 엔드포인트 (사용자에게 제공되는 유일한 진입점)
#   - 기본 동작(*)      : ALB 오리진(API) -> 캐시 비활성(정확성), 모든 메서드 허용
#   - /images/*         : S3 오리진(OAC) -> 캐시 최적화(이미지 다운로드 성능)
#   - WAF 연결          : 비정상요청 403 차단
#   - HTTPS             : ACM 인증서(도메인) 또는 CloudFront 기본 인증서
###############################################################################

# 관리형 정책 조회
data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_origin_request_policy" "all_viewer" {
  name = "Managed-AllViewer"
}

# S3 오리진 접근용 OAC
resource "aws_cloudfront_origin_access_control" "s3" {
  count = var.enable_cloudfront ? 1 : 0

  name                              = "${local.name}-s3-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

locals {
  # ALB 오리진 도메인. Ingress 미생성 단계에서는 placeholder 사용.
  alb_origin_domain = var.alb_dns_name != "" ? var.alb_dns_name : "alb-not-ready.invalid"
  cf_aliases        = local.use_domain ? [local.fqdn] : []
}

resource "aws_cloudfront_distribution" "main" {
  count = var.enable_cloudfront ? 1 : 0

  enabled         = true
  comment         = "${local.name} task3 single endpoint"
  is_ipv6_enabled = true
  price_class     = "PriceClass_200" # 비용최적화: 아태 포함 리전 한정
  web_acl_id      = aws_wafv2_web_acl.cf[0].arn
  aliases         = local.cf_aliases

  # --- 오리진 1: ALB (API) ---
  origin {
    origin_id   = "alb-api"
    domain_name = local.alb_origin_domain

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only" # CloudFront->ALB 는 HTTP (TLS 종단은 CloudFront)
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # --- 오리진 2: S3 (이미지) ---
  origin {
    origin_id                = "s3-images"
    domain_name              = aws_s3_bucket.images.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.s3[0].id
  }

  # --- 기본 동작: API (ALB) ---
  default_cache_behavior {
    target_origin_id       = "alb-api"
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods  = ["GET", "HEAD"]

    # API 는 캐시 비활성(요청별 requestid/uuid 상이, 쓰기요청 정확성 보장)
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id

    compress = true
  }

  # --- /images/* : S3 정적 컨텐츠 (캐시 최적화) ---
  ordered_cache_behavior {
    path_pattern           = "/images/*"
    target_origin_id       = "s3-images"
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD", "OPTIONS"]
    cached_methods  = ["GET", "HEAD"]

    cache_policy_id = data.aws_cloudfront_cache_policy.caching_optimized.id

    compress = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # HTTPS 인증서
  viewer_certificate {
    cloudfront_default_certificate = local.use_domain ? false : true
    acm_certificate_arn            = local.use_domain ? aws_acm_certificate_validation.cf[0].certificate_arn : null
    ssl_support_method             = local.use_domain ? "sni-only" : null
    minimum_protocol_version       = local.use_domain ? "TLSv1.2_2021" : "TLSv1"
  }

  tags = local.tags
}

# 단일 엔드포인트 Alias 레코드 (도메인 사용 시)
resource "aws_route53_record" "cf_alias" {
  count = var.enable_cloudfront && local.use_domain ? 1 : 0

  zone_id = local.zone_id
  name    = local.fqdn
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.main[0].domain_name
    zone_id                = aws_cloudfront_distribution.main[0].hosted_zone_id
    evaluate_target_health = false
  }
}
