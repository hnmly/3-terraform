###############################################################################
# outputs.tf
###############################################################################

output "region" {
  description = "리전"
  value       = var.region
}

output "cluster_name" {
  description = "EKS 클러스터 이름"
  value       = module.eks.cluster_name
}

output "configure_kubectl" {
  description = "kubectl 설정 명령"
  value       = "aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}"
}

output "ecr_repository_urls" {
  description = "ECR 리포지토리 URL (docker push 대상)"
  value       = { for k, v in aws_ecr_repository.app : k => v.repository_url }
}

output "rds_endpoint" {
  description = "RDS 엔드포인트 (MYSQL_HOST)"
  value       = aws_db_instance.main.address
}

output "rds_port" {
  description = "RDS 포트"
  value       = aws_db_instance.main.port
}

output "db_secret_name" {
  description = "RDS 자격증명 Secrets Manager 이름"
  value       = aws_secretsmanager_secret.db.name
}

output "s3_images_bucket" {
  description = "이미지 S3 버킷 이름"
  value       = aws_s3_bucket.images.id
}

output "cloudfront_domain_name" {
  description = "CloudFront 도메인 (도메인 미사용 시 이 값이 단일 엔드포인트)"
  value       = var.enable_cloudfront ? aws_cloudfront_distribution.main[0].domain_name : null
}

output "single_endpoint" {
  description = "채점 플랫폼에 입력할 단일 엔드포인트 (프로토콜 포함, 경로 제외)"
  value = var.enable_cloudfront ? (
    local.use_domain ? "https://${local.fqdn}" : "https://${aws_cloudfront_distribution.main[0].domain_name}"
  ) : "CloudFront 비활성화 상태 - enable_cloudfront=true 로 배포 필요"
}

output "waf_web_acl_arn" {
  description = "CloudFront WAF Web ACL ARN"
  value       = var.enable_cloudfront ? aws_wafv2_web_acl.cf[0].arn : null
}

output "lb_controller_role_arn" {
  description = "AWS Load Balancer Controller IRSA Role ARN"
  value       = module.lb_controller_irsa.iam_role_arn
}

output "product_sa_role_arn" {
  description = "product 앱 S3 접근 IRSA Role ARN"
  value       = module.app_s3_irsa.iam_role_arn
}


output "karpenter_node_iam_role_name" {
  description = "Karpenter 노드 IAM 역할 이름 (EC2NodeClass.spec.role 에 사용)"
  value       = module.karpenter.node_iam_role_name
}
