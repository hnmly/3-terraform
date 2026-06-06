###############################################################################
# helm.tf
# 클러스터 부가 컴포넌트:
#   - AWS Load Balancer Controller : Ingress -> ALB 프로비저닝 (필수)
#   - ExternalDNS                  : Route53 레코드 자동화 (도메인 사용 시)
#   - metrics-server               : HPA 동작에 필요한 메트릭 제공
###############################################################################

# 앱 네임스페이스
resource "kubernetes_namespace" "apps" {
  metadata {
    name = "apps"
    labels = {
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }
}

# product 앱용 ServiceAccount (S3 업로드 IRSA 연결)
resource "kubernetes_service_account" "product" {
  metadata {
    name      = "product-sa"
    namespace = kubernetes_namespace.apps.metadata[0].name
    annotations = {
      "eks.amazonaws.com/role-arn" = module.app_s3_irsa.iam_role_arn
    }
  }
}

# --- AWS Load Balancer Controller ------------------------------------------
resource "kubernetes_service_account" "lb_controller" {
  metadata {
    name      = "aws-load-balancer-controller"
    namespace = "kube-system"
    annotations = {
      "eks.amazonaws.com/role-arn" = module.lb_controller_irsa.iam_role_arn
    }
    labels = {
      "app.kubernetes.io/component" = "controller"
      "app.kubernetes.io/name"      = "aws-load-balancer-controller"
    }
  }
}

resource "helm_release" "lb_controller" {
  name       = "aws-load-balancer-controller"
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  namespace  = "kube-system"
  version    = "1.13.0"

  set {
    name  = "clusterName"
    value = module.eks.cluster_name
  }
  set {
    name  = "serviceAccount.create"
    value = "false"
  }
  set {
    name  = "serviceAccount.name"
    value = kubernetes_service_account.lb_controller.metadata[0].name
  }
  set {
    name  = "region"
    value = var.region
  }
  set {
    name  = "vpcId"
    value = module.vpc.vpc_id
  }

  depends_on = [module.eks]
}

# --- metrics-server (HPA 용) ------------------------------------------------
resource "helm_release" "metrics_server" {
  name       = "metrics-server"
  repository = "https://kubernetes-sigs.github.io/metrics-server/"
  chart      = "metrics-server"
  namespace  = "kube-system"
  version    = "3.12.2"

  set {
    name  = "args[0]"
    value = "--kubelet-insecure-tls"
  }

  depends_on = [module.eks]
}

# --- ExternalDNS (도메인 사용 시) -------------------------------------------
resource "kubernetes_service_account" "external_dns" {
  count = local.use_domain ? 1 : 0

  metadata {
    name      = "external-dns"
    namespace = "kube-system"
    annotations = {
      "eks.amazonaws.com/role-arn" = module.external_dns_irsa[0].iam_role_arn
    }
  }
}

resource "helm_release" "external_dns" {
  count = local.use_domain ? 1 : 0

  name       = "external-dns"
  repository = "https://kubernetes-sigs.github.io/external-dns/"
  chart      = "external-dns"
  namespace  = "kube-system"
  version    = "1.15.2"

  set {
    name  = "provider"
    value = "aws"
  }
  set {
    name  = "serviceAccount.create"
    value = "false"
  }
  set {
    name  = "serviceAccount.name"
    value = kubernetes_service_account.external_dns[0].metadata[0].name
  }
  set {
    name  = "policy"
    value = "sync"
  }
  set {
    name  = "txtOwnerId"
    value = var.cluster_name
  }
  set {
    name  = "domainFilters[0]"
    value = var.domain_name
  }

  depends_on = [module.eks]
}
