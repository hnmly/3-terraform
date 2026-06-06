###############################################################################
# s3.tf
# 제품 이미지 오브젝트 스토리지
#  - 버킷은 비공개. CloudFront(OAC)를 통해서만 /images/<path> 로 제공
#  - product 앱은 IRSA(app_s3_irsa)로 PutObject 하여 이미지 업로드
###############################################################################

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "images" {
  bucket        = "${local.name}-images-${random_id.bucket_suffix.hex}"
  force_destroy = true # 대회 환경: 정리 편의

  tags = merge(local.tags, { Purpose = "product-images" })
}

# 퍼블릭 액세스 전면 차단 (CloudFront OAC로만 접근)
resource "aws_s3_bucket_public_access_block" "images" {
  bucket = aws_s3_bucket.images.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "images" {
  bucket = aws_s3_bucket.images.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# 서버사이드 암호화
resource "aws_s3_bucket_server_side_encryption_configuration" "images" {
  bucket = aws_s3_bucket.images.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# CloudFront OAC만 GetObject 허용하는 버킷 정책 (CloudFront 활성화 시에만)
data "aws_iam_policy_document" "images_bucket" {
  count = var.enable_cloudfront ? 1 : 0

  statement {
    sid       = "AllowCloudFrontOACRead"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.images.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.main[0].arn]
    }
  }
}

resource "aws_s3_bucket_policy" "images" {
  count = var.enable_cloudfront ? 1 : 0

  bucket = aws_s3_bucket.images.id
  policy = data.aws_iam_policy_document.images_bucket[0].json

  depends_on = [aws_s3_bucket_public_access_block.images]
}
