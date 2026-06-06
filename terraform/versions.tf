###############################################################################
# versions.tf
# Terraform / Provider 버전 고정 (재현성 확보 - Well-Architected: Reliability)
###############################################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.95"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.17"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.35"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # 대회 환경에서는 로컬 state 사용. 운영 시 S3 backend 권장.
  # backend "s3" {
  #   bucket = "apdev-tfstate-<account-id>"
  #   key    = "task3/terraform.tfstate"
  #   region = "ap-northeast-2"
  # }
}
