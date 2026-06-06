# =============================================================================
# deploy.ps1 - 이미지 빌드/푸시 후 k8s 매니페스트 치환 적용 (Windows PowerShell)
#
# 사전조건:
#   - terraform apply 완료 (ECR/EKS/S3 생성됨)
#   - 각 앱 바이너리를 docker/<app>/app 로 배치 (Dockerfile 과 같은 위치)
#   - aws eks update-kubeconfig 로 kubectl 컨텍스트 설정 완료
#
# 사용: ./deploy.ps1
# =============================================================================
$ErrorActionPreference = "Stop"

$REGION = "ap-northeast-2"
$ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$ECR_BASE = "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

Write-Host "ECR base: $ECR_BASE"

# 1) ECR 로그인
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR_BASE

# 2) 이미지 빌드 & 푸시 (docker/<app> 바이너리 필요. 파일명 = user/product/stress)
$apps = @("user", "product", "stress")
foreach ($app in $apps) {
    $binPath = "docker/$app"
    if (-not (Test-Path $binPath)) {
        Write-Error "바이너리가 없습니다: $binPath  (docker/ 폴더에 user/product/stress 바이너리를 두세요)"
        exit 1
    }
    $img = "$ECR_BASE/apdev/$app`:latest"
    Write-Host "Building $img (binary: $app) ..."
    docker build --platform linux/amd64 --build-arg APP_BINARY=$app -t $img -f docker/Dockerfile docker
    docker push $img
}

# 3) S3 버킷명 조회 (terraform output)
Push-Location terraform
$S3_BUCKET = (terraform output -raw s3_images_bucket)
Pop-Location

# 4) 매니페스트 치환 후 적용
$tmp = "k8s/.rendered"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
Get-ChildItem k8s/*.yaml | ForEach-Object {
    (Get-Content $_.FullName) `
        -replace "__ECR_USER__", "$ECR_BASE/apdev/user" `
        -replace "__ECR_PRODUCT__", "$ECR_BASE/apdev/product" `
        -replace "__ECR_STRESS__", "$ECR_BASE/apdev/stress" `
        -replace "__S3_BUCKET__", "$S3_BUCKET" |
        Set-Content "$tmp/$($_.Name)"
}

kubectl apply -f $tmp

Write-Host "`n배포 완료. ALB 생성 대기:"
Write-Host "  kubectl get ingress -n apps -w"
Write-Host "ALB DNS 확인 후 terraform 2단계: -var alb_dns_name=<dns> -var enable_cloudfront=true"
