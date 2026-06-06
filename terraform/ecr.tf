###############################################################################
# ecr.tf
# 컨테이너 이미지 레포지토리 - user / product / stress
###############################################################################

locals {
  ecr_repos = ["user", "product", "stress"]
}

resource "aws_ecr_repository" "app" {
  for_each = toset(local.ecr_repos)

  name                 = "${local.name}/${each.value}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # 대회 환경: 정리 편의

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(local.tags, { App = each.value })
}

# 오래된 이미지 정리 (비용최적화: 스토리지 누적 방지)
resource "aws_ecr_lifecycle_policy" "app" {
  for_each = aws_ecr_repository.app

  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
