###############################################################################
# acm.tf
# CloudFront 용 TLS 인증서 - 반드시 us-east-1 에 생성, DNS(Route53) 검증.
# 도메인 미사용 시에는 생성하지 않고 CloudFront 기본 인증서를 사용.
###############################################################################

locals {
  acm_enabled = var.enable_cloudfront && local.use_domain
}

resource "aws_acm_certificate" "cf" {
  count    = local.acm_enabled ? 1 : 0
  provider = aws.use1

  domain_name       = local.fqdn
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = local.tags
}

# DNS 검증 레코드 (Route53)
resource "aws_route53_record" "cf_cert_validation" {
  for_each = local.acm_enabled ? {
    for dvo in aws_acm_certificate.cf[0].domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  } : {}

  zone_id = local.zone_id
  name    = each.value.name
  type    = each.value.type
  records = [each.value.record]
  ttl     = 60

  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "cf" {
  count    = local.acm_enabled ? 1 : 0
  provider = aws.use1

  certificate_arn         = aws_acm_certificate.cf[0].arn
  validation_record_fqdns = [for r in aws_route53_record.cf_cert_validation : r.fqdn]
}
