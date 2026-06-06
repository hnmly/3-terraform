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

# EKS 클러스터 인증 정보 (클러스터 생성 후 helm/kubernetes 프로바이더가 사용)
data "aws_eks_cluster_auth" "this" {
  name = module.eks.cluster_name
}

provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
  token                  = data.aws_eks_cluster_auth.this.token
}

provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
    token                  = data.aws_eks_cluster_auth.this.token
  }
}
