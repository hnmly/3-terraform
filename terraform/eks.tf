###############################################################################
# eks.tf
# 컨테이너 오케스트레이션: EKS (ECS 금지)
# 컴퓨팅: EC2 t3.medium 관리형 노드그룹만 사용 (Fargate 금지)
###############################################################################

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.37"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  # API 서버 퍼블릭 엔드포인트 (kubectl 접근용). 운영시 private 권장.
  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  enable_irsa = true

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  node_security_group_tags = {
    "karpenter.sh/discovery" = var.cluster_name
  }

  # 핵심 애드온 (관찰가능성/네트워킹 기본기)
  cluster_addons = {
    coredns    = { most_recent = true }
    kube-proxy = { most_recent = true }
    vpc-cni = {
      most_recent = true
    }
    eks-pod-identity-agent = { most_recent = true }
    aws-ebs-csi-driver = {
      most_recent              = true
      service_account_role_arn = module.ebs_csi_irsa.iam_role_arn
    }
  }

  # EC2 t3.medium 관리형 노드그룹 (문제 요구사항: t3.medium 만)
  eks_managed_node_group_defaults = {
    ami_type = "AL2023_x86_64_STANDARD"
  }

  eks_managed_node_groups = {
    app = {
      instance_types = [var.node_instance_type] # t3.medium

      min_size     = var.node_min_size
      max_size     = var.node_max_size
      desired_size = var.node_desired_size

      capacity_type = "ON_DEMAND"

      labels = {
        workload = "app"
      }

      # 노드 디스크 (비용최적화: 과도한 스토리지 지양)
      block_device_mappings = {
        xvda = {
          device_name = "/dev/xvda"
          ebs = {
            volume_size           = 30
            volume_type           = "gp3"
            delete_on_termination = true
          }
        }
      }
    }
  }

  # 클러스터 생성자에게 admin 권한 부여 (kubectl 접근)
  enable_cluster_creator_admin_permissions = true

  tags = local.tags
}
