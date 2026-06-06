###############################################################################
# route53.tf
# 도메인 사용 시 Hosted Zone 생성 또는 기존 조회.
# 단일 엔드포인트(CloudFront)로의 Alias 레코드는 cloudfront.tf 에서 생성.
###############################################################################

resource "aws_route53_zone" "this" {
  count = local.use_domain && var.create_route53_zone ? 1 : 0
  name  = var.domain_name
  tags  = local.tags
}

data "aws_route53_zone" "this" {
  count        = local.use_domain && !var.create_route53_zone ? 1 : 0
  name         = var.domain_name
  private_zone = false
}

locals {
  zone_id = local.use_domain ? (
    var.create_route53_zone ? aws_route53_zone.this[0].zone_id : data.aws_route53_zone.this[0].zone_id
  ) : ""
}
