###############################################################################
# karpenter.tf
# 노드 오토스케일링 - Karpenter (인스턴스 타입을 t3.medium 으로 명시 제한)
#   - 기본 관리형 노드그룹(시스템)은 최소 유지 -> 평상시 비용 최저(낮은 cost ratio)
#   - 부하 시 Karpenter 가 t3.medium 노드만 추가 -> 로드 처리(가용성/성능 확보)
#   - 부하 감소 시 consolidation 으로 빈/저활용 노드 신속 제거 -> 비용 회수
#   * NodePool / EC2NodeClass 는 k8s/karpenter/ 에서 적용 (t3.medium 만 허용)
###############################################################################

module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "~> 20.37"

  cluster_name = module.eks.cluster_name

  # Karpenter v1 권한 세트
  enable_v1_permissions = true
  namespace             = "kube-system"

  # Pod Identity 로 컨트롤러 권한 연결 (SA: karpenter)
  enable_pod_identity             = true
  create_pod_identity_association = true

  # 노드 IAM 역할에 SSM 권한 추가 (세션 접근/디버깅)
  node_iam_role_additional_policies = {
    AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  }

  tags = local.tags
}

resource "helm_release" "karpenter" {
  name       = "karpenter"
  namespace  = "kube-system"
  repository = "oci://public.ecr.aws/karpenter"
  chart      = "karpenter"
  version    = var.karpenter_version
  wait       = true

  values = [yamlencode({
    settings = {
      clusterName       = module.eks.cluster_name
      interruptionQueue = module.karpenter.queue_name
    }
    serviceAccount = {
      name = module.karpenter.service_account
    }
    controller = {
      resources = {
        requests = { cpu = "100m", memory = "256Mi" }
        limits   = { memory = "512Mi" }
      }
    }
  })]

  depends_on = [module.eks]
}