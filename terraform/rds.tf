###############################################################################
# rds.tf
# 관계형 데이터베이스 - 문제 요구사항 고정값 (위반 시 성능/비용 0점)
#   - DB identifier      : apdev-rds-instance
#   - Deployment         : Multi-AZ DB instance (고가용성)
#   - DB instance class  : db.t3.micro
#   - Storage type       : gp3
#   - Engine             : MySQL Community 8.0
#   - 논리 DB 이름        : dev
###############################################################################

# DB 마스터 비밀번호 (랜덤 생성 -> Secrets Manager 저장)
resource "random_password" "db" {
  length  = 20
  special = false # MySQL/URL 호환 위해 특수문자 제외
}

# --- DB 보안그룹: EKS 노드(워커)에서 3306 인바운드만 허용 --------------------
resource "aws_security_group" "rds" {
  name        = "${local.name}-rds-sg"
  description = "Allow MySQL from EKS nodes only"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description     = "MySQL from EKS node security group"
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${local.name}-rds-sg" })
}

# --- 파라미터 그룹 (트래픽 패턴 대응 튜닝 여지) ------------------------------
resource "aws_db_parameter_group" "mysql8" {
  name        = "${local.name}-mysql80"
  family      = "mysql8.0"
  description = "MySQL 8.0 parameter group for task3"

  parameter {
    name  = "max_connections"
    value = "256"
  }

  parameter {
    name  = "character_set_server"
    value = "utf8mb4"
  }

  lifecycle {
    create_before_destroy = true
  }

  tags = local.tags
}

# --- RDS 인스턴스 -----------------------------------------------------------
resource "aws_db_instance" "main" {
  identifier     = var.db_identifier # apdev-rds-instance (고정)
  engine         = "mysql"
  engine_version = var.db_engine_version # 8.0
  instance_class = var.db_instance_class # db.t3.micro

  # gp3 스토리지
  storage_type          = "gp3"
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = 100 # 스토리지 오토스케일링 (성능 안정성)

  # Multi-AZ DB instance (고가용성)
  multi_az = true

  db_name  = var.db_name # dev
  username = var.db_username
  password = random_password.db.result
  port     = 3306

  db_subnet_group_name   = module.vpc.database_subnet_group_name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.mysql8.name

  # 비용최적화: 외부 노출 금지
  publicly_accessible = false

  # 안정성
  backup_retention_period    = 1
  skip_final_snapshot        = true
  deletion_protection        = false
  auto_minor_version_upgrade = true
  apply_immediately          = true

  # 관찰가능성: 에러/슬로우 쿼리 로그를 CloudWatch로
  enabled_cloudwatch_logs_exports = ["error", "slowquery"]

  performance_insights_enabled = true

  tags = merge(local.tags, { Name = var.db_identifier })
}

# --- DB 접속정보를 Secrets Manager에 저장 (앱이 External Secrets로 참조 가능) -
resource "aws_secretsmanager_secret" "db" {
  name        = "${local.name}/rds/credentials"
  description = "RDS MySQL credentials for task3 apps"
  tags        = local.tags

  recovery_window_in_days = 0 # 대회 환경: 즉시 삭제 가능
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({
    MYSQL_USER     = var.db_username
    MYSQL_PASSWORD = random_password.db.result
    MYSQL_HOST     = aws_db_instance.main.address # DNS 주소 (엔진명 미포함)
    MYSQL_PORT     = tostring(aws_db_instance.main.port)
    MYSQL_DBNAME   = var.db_name
  })
}
