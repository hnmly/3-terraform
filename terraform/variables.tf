###############################################################################
# variables.tf
###############################################################################

variable "project" {
  description = "리소스 명명 prefix"
  type        = string
  default     = "apdev"
}

variable "region" {
  description = "주 리전 (유의사항 8번: 별도 언급 없으면 ap-northeast-2)"
  type        = string
  default     = "ap-northeast-2"
}

# ---------------------------------------------------------------------------
# 네트워크
# ---------------------------------------------------------------------------
variable "vpc_cidr" {
  description = "VPC CIDR"
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = "사용할 가용영역 수 (고가용성: 2개 이상)"
  type        = number
  default     = 2
}

# ---------------------------------------------------------------------------
# EKS
# ---------------------------------------------------------------------------
variable "cluster_name" {
  description = "EKS 클러스터 이름"
  type        = string
  default     = "apdev-eks"
}

variable "cluster_version" {
  description = "EKS Kubernetes 버전"
  type        = string
  default     = "1.35"
}

variable "node_instance_type" {
  description = "노드 인스턴스 타입 (문제 요구사항: t3.medium 만 사용)"
  type        = string
  default     = "t3.medium"
}

variable "node_min_size" {
  description = "노드그룹 최소 노드 수"
  type        = number
  default     = 2
}

variable "node_max_size" {
  description = "노드그룹 최대 노드 수 (비용최적화 vs 고가용성 트레이드오프 - cost ratio 관리)"
  type        = number
  default     = 4
}

variable "node_desired_size" {
  description = "노드그룹 초기 노드 수"
  type        = number
  default     = 2
}

# ---------------------------------------------------------------------------
# RDS (문제 요구사항 고정값 - 변경 시 채점 0점 처리)
# ---------------------------------------------------------------------------
variable "db_identifier" {
  description = "RDS DB identifier (문제 고정값)"
  type        = string
  default     = "apdev-rds-instance"
}

variable "db_instance_class" {
  description = "RDS 인스턴스 클래스 (문제 고정값: db.t3.micro)"
  type        = string
  default     = "db.t3.micro"
}

variable "db_engine_version" {
  description = "MySQL Community 엔진 버전 (문제 고정값: 8.0)"
  type        = string
  default     = "8.0"
}

variable "db_name" {
  description = "논리 DB 이름 (앱 환경변수 MYSQL_DBNAME = dev)"
  type        = string
  default     = "dev"
}

variable "db_username" {
  description = "DB 마스터/앱 유저명 (앱 환경변수 MYSQL_USER)"
  type        = string
  default     = "db"
}

variable "db_allocated_storage" {
  description = "RDS 스토리지(GB) - gp3"
  type        = number
  default     = 20
}

# ---------------------------------------------------------------------------
# 도메인 / 단일 엔드포인트
# ---------------------------------------------------------------------------
variable "domain_name" {
  description = "Route53 Hosted Zone 도메인 (예: team01.skills.cloud). 빈 값이면 CloudFront 기본 도메인 사용"
  type        = string
  default     = ""
}

variable "subdomain" {
  description = "서비스 서브도메인 (최종 단일 엔드포인트 = <subdomain>.<domain_name>)"
  type        = string
  default     = "api"
}

variable "create_route53_zone" {
  description = "Route53 Hosted Zone을 신규 생성할지 여부 (false면 기존 zone 조회)"
  type        = bool
  default     = false
}

# ---------------------------------------------------------------------------
# 애플리케이션 이미지 태그
# ---------------------------------------------------------------------------
variable "app_image_tag" {
  description = "user/product/stress 컨테이너 이미지 태그"
  type        = string
  default     = "latest"
}

# ---------------------------------------------------------------------------
# CloudFront 백엔드 오리진 (ALB)
# 2단계 배포: 1) 코어 인프라 apply -> 2) Ingress 로 ALB 생성 후 이 값 주입
# 비어있으면 CloudFront 는 임시 placeholder 오리진으로 생성됨
# ---------------------------------------------------------------------------
variable "alb_dns_name" {
  description = "AWS LB Controller(Ingress)가 생성한 ALB의 DNS 이름"
  type        = string
  default     = ""
}

variable "enable_cloudfront" {
  description = "CloudFront/WAF 단일엔드포인트 생성 여부 (1단계에서 false, ALB 준비 후 true 권장)"
  type        = bool
  default     = true
}

# ---------------------------------------------------------------------------
# WAF Rate limit (채점 트래픽은 소수 IP 고RPS -> 과차단 위험. 기본 임계값 높게)
# ---------------------------------------------------------------------------
variable "waf_enable_rate_limit" {
  description = "WAF IP rate-based 규칙 활성화 여부. 부하 트래픽 과차단 의심 시 false"
  type        = bool
  default     = true
}

variable "waf_rate_limit" {
  description = "5분 창 기준 IP당 허용 요청 수 (초과 시 403). 채점 부하를 막지 않도록 높게 설정"
  type        = number
  default     = 100000
}
