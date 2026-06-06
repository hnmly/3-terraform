###############################################################################
# locals.tf  /  data sources
###############################################################################

data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

locals {
  name = var.project
  azs  = slice(data.aws_availability_zones.available.names, 0, var.az_count)

  # 도메인 사용 여부 (도메인 미지정 시 CloudFront 기본 도메인으로 동작)
  use_domain = var.domain_name != ""
  fqdn       = local.use_domain ? "${var.subdomain}.${var.domain_name}" : ""

  # 서브넷 CIDR 자동 분할 (/16 -> /20)
  public_subnets   = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 4, i)]
  private_subnets  = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 4, i + 4)]
  database_subnets = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 4, i + 8)]

  tags = {
    Project = var.project
  }
}
