# =============================================================================
# deploy.ps1 - 이미지 빌드/푸시 + Karpenter/앱 매니페스트 치환 적용 (Windows PowerShell)
#
# 사전조건:
#   - terraform apply 완료 (ECR/EKS/S3/Karpenter 생성됨)
#   - 앱 바이너리를 docker/user, docker/product, docker/stress 로 배치
#   - aws eks update-kubeconfig 로 kubectl 컨텍스트 설정 완료
#
# 사용: ./deploy.ps1
# =============================================================================
$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)

$REGION = "ap-northeast-2"
$ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$ECR_BASE = "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
Write-Host "ECR base: $ECR_BASE"

# 치환 후 UTF-8(BOM 없음)으로 렌더링하는 헬퍼
function Render-Dir($srcDir, $outDir, [hashtable]$map) {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    Get-ChildItem "$srcDir/*.yaml" | ForEach-Object {
        $text = [System.IO.File]::ReadAllText($_.FullName)
        foreach ($k in $map.Keys) { $text = $text.Replace($k, $map[$k]) }
        [System.IO.File]::WriteAllText((Join-Path $outDir $_.Name), $text, $utf8)
    }
}

# 1) ECR 로그인
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR_BASE

# 2) 이미지 빌드 & 푸시 (docker/<app> 바이너리. 파일명 = user/product/stress)
$apps = @("user", "product", "stress")
foreach ($app in $apps) {
    if (-not (Test-Path "docker/$app")) {
        Write-Error "바이너리가 없습니다: docker/$app (docker/ 폴더에 user/product/stress 바이너리를 두세요)"
        exit 1
    }
    $img = "$ECR_BASE/apdev/$app`:latest"
    Write-Host "Building $img (binary: $app) ..."
    docker build --platform linux/amd64 --build-arg APP_BINARY=$app -t $img -f docker/Dockerfile docker
    docker push $img
}

# 3) Terraform output 조회
Push-Location terraform
$S3_BUCKET     = (terraform output -raw s3_images_bucket)
$CLUSTER_NAME  = (terraform output -raw cluster_name)
$KARPENTER_ROLE = (terraform output -raw karpenter_node_iam_role_name)
Pop-Location

# 4) Karpenter NodePool/EC2NodeClass 먼저 적용 (t3.medium 노드 프로비저닝 준비)
Render-Dir "k8s/karpenter" "k8s/.rendered/karpenter" @{
    "__KARPENTER_NODE_ROLE__" = $KARPENTER_ROLE
    "__CLUSTER_NAME__"        = $CLUSTER_NAME
}
kubectl apply -f k8s/.rendered/karpenter

# 5) 앱 매니페스트 치환 후 적용
Render-Dir "k8s" "k8s/.rendered/apps" @{
    "__ECR_USER__"    = "$ECR_BASE/apdev/user"
    "__ECR_PRODUCT__" = "$ECR_BASE/apdev/product"
    "__ECR_STRESS__"  = "$ECR_BASE/apdev/stress"
    "__S3_BUCKET__"   = "$S3_BUCKET"
}
kubectl apply -f k8s/.rendered/apps

Write-Host "`n배포 완료. ALB 생성 대기:"
Write-Host "  kubectl get ingress -n apps -w"
Write-Host "Karpenter 노드/프로비저닝 상태:"
Write-Host "  kubectl get nodepool,ec2nodeclass; kubectl get nodes -L node.kubernetes.io/instance-type"
Write-Host "ALB DNS 확인 후 terraform 2단계: -var alb_dns_name=<dns> -var enable_cloudfront=true"