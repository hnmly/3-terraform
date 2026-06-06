###############################################################################
# providers.tf
###############################################################################

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "Terraform"
      Task      = "skills-cloud-task3"
    }
  }
}

# CloudFront ACM 인증서 / WAF(CLOUDFRONT scope)는 반드시 us-east-1 에 생성해야 함
provider "aws" {
  alias  = "use1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "Terraform"
      Task      = "skills-cloud-task3"
    }
  }
}

# EKS 인증: exec 플러그인으로 매 호출마다 신선한 토큰 발급 (토큰 만료 방지)
# - aws CLI 가 PATH 에 있어야 함
provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name, "--region", var.region]
  }
}

provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)

    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name, "--region", var.region]
    }
  }
}