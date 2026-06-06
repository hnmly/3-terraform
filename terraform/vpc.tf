###############################################################################
# vpc.tf
# 고가용성: 2개 이상 AZ에 서브넷 분산
# - public  : NAT GW, ALB(인터넷 facing) 배치
# - private : EKS 노드(EC2) 배치
# - database: RDS Multi-AZ 배치
# 비용최적화: NAT GW는 단일(single_nat_gateway=true)로 비용 절감.
#            완전한 AZ 장애 격리가 필요하면 one_nat_gateway_per_az 로 전환.
###############################################################################

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.19"

  name = "${local.name}-vpc"
  cidr = var.vpc_cidr
  azs  = local.azs

  public_subnets   = local.public_subnets
  private_subnets  = local.private_subnets
  database_subnets = local.database_subnets

  create_database_subnet_group = true

  enable_nat_gateway   = true
  single_nat_gateway   = true # 비용 절감 (cost ratio 관리)
  enable_dns_hostnames = true
  enable_dns_support   = true

  # Kubernetes / AWS Load Balancer Controller 서브넷 자동 디스커버리 태그
  public_subnet_tags = {
    "kubernetes.io/role/elb"                    = "1"
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb"           = "1"
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "karpenter.sh/discovery"                    = var.cluster_name
  }

  tags = local.tags
}
