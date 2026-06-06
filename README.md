# 2026 전국기능경기대회 클라우드컴퓨팅 제3과제 (System Operation)

개발된 애플리케이션(user/product/stress)을 EKS 기반으로 배포·운영하고, 단일 엔드포인트로
서비스를 제공하는 인프라를 Terraform 으로 구축합니다. 채점기준표(40점)를 충족하도록 설계했습니다.

---

## 1. 아키텍처

```
                         인터넷 사용자
                              │  (단일 엔드포인트, HTTPS)
                              ▼
                     ┌──────────────────┐
                     │   Route53 (도메인)  │  ← 선택
                     └────────┬─────────┘
                              ▼
                  ┌────────────────────────┐
                  │   CloudFront (단일진입)    │
                  │  + WAF(비정상요청 403 차단)  │
                  └───────┬──────────┬───────┘
              /images/*   │          │  그 외 모든 경로(*)
                          ▼          ▼
                  ┌──────────┐   ┌────────────────────┐
                  │ S3 (OAC) │   │  ALB (internet-facing) │
                  │  이미지     │   │  /v1/user|product|stress│
                  └──────────┘   │  그 외 → 404 고정응답      │
                                 └──────────┬─────────┘
                                            ▼
                            ┌────────────────────────────┐
                            │  EKS (EC2 t3.medium 노드그룹)    │
                            │  apps 네임스페이스                │
                            │   user / product / stress (HPA) │
                            └──────────────┬─────────────┘
                                           ▼
                              ┌──────────────────────────┐
                              │ RDS MySQL 8.0 Multi-AZ      │
                              │ apdev-rds-instance(db.t3.micro)│
                              └──────────────────────────┘
```

- **단일 엔드포인트** = CloudFront. `/images/*` 는 S3, 그 외는 ALB(API) 로 라우팅.
- **비정상 요청 403** = CloudFront WAF, **API 외 경로 404** = ALB 기본 고정응답.
- **컴퓨팅은 EC2(t3.medium)만** 사용 (Fargate/Lambda 미사용 — 사용 시 전체 0점).

---

## 2. 디렉토리 구조

```
task3/
├── terraform/            # 인프라 (VPC/EKS/RDS/ECR/S3/CloudFront/WAF/ACM/R53/IAM/Helm)
│   ├── versions.tf  providers.tf  variables.tf  locals.tf
│   ├── vpc.tf  eks.tf  iam.tf  rds.tf  ecr.tf  s3.tf
│   ├── waf.tf  acm.tf  route53.tf  cloudfront.tf
│   ├── helm.tf  k8s-secret.tf  outputs.tf
│   └── terraform.tfvars.example
├── k8s/                  # 애플리케이션 매니페스트
│   ├── 10-user.yaml  11-product.yaml  12-stress.yaml  20-ingress.yaml
├── docker/Dockerfile     # 제공 Go 바이너리 컨테이너화
├── db/init.sql           # user/product 테이블 생성
└── deploy.ps1            # 이미지 빌드/푸시 + 매니페스트 배포
```

---

## 3. 배포 순서 (2단계)

CloudFront 의 백엔드 오리진은 ALB 인데, ALB 는 EKS Ingress 가 생성합니다.
따라서 **코어 인프라 → 앱/Ingress → CloudFront 연결** 순으로 2단계 배포합니다.

### 사전 준비
```powershell
cd terraform
Copy-Item terraform.tfvars.example terraform.tfvars   # 필요시 값 수정
terraform init
```

### 1단계 — 코어 인프라 (CloudFront 제외)
```powershell
terraform apply -var="enable_cloudfront=false"
# VPC, EKS, RDS, ECR, S3, LB Controller, 앱 네임스페이스/시크릿 생성

# kubectl 컨텍스트 설정
aws eks update-kubeconfig --region ap-northeast-2 --name apdev-eks
```

### DB 초기화 + 이미지 배포
```powershell
# (1) DB 테이블 생성 + load_user.dump 적재 (bastion 또는 임시 Pod 에서)
#     mysql -h <rds_endpoint> -u db -p dev < db/init.sql
#     mysql -h <rds_endpoint> -u db -p dev < load_user.dump

# (2) 이미 빌드된 앱 바이너리(파일명: user / product / stress)를 docker/ 폴더에 배치
#     docker/user   docker/product   docker/stress
cd ..
./deploy.ps1            # ECR 빌드/푸시 + k8s 매니페스트 적용

# (3) ALB 생성 확인
kubectl get ingress -n apps -w     # ADDRESS 컬럼에 ALB DNS 가 뜰 때까지 대기
```

### 2단계 — CloudFront 단일 엔드포인트 연결
```powershell
cd terraform
$ALB = (kubectl get ingress apps-ingress -n apps -o jsonpath="{.status.loadBalancer.ingress[0].hostname}")
terraform apply -var="enable_cloudfront=true" -var="alb_dns_name=$ALB"

# 최종 제출 엔드포인트 확인 (프로토콜 포함, 경로 제외)
terraform output single_endpoint
```

> 도메인을 사용할 경우 `domain_name`, `subdomain`, `create_route53_zone` 변수를 설정하면
> ACM(us-east-1) 인증서 발급·검증과 Route53 Alias 레코드가 자동 구성됩니다.

---

## 4. 채점기준표(40점) 대응 매핑

| 채점 항목 | 배점 | 대응 설계 |
|---|---|---|
| **1. 비정상 요청 처리** | 4 | ① Image 처리율: `/images/*` → CloudFront(S3 OAC) 캐시최적화로 안정 다운로드. ② 비정상요청 처리율: CloudFront **WAF**(CommonRuleSet + KnownBadInputs + RateLimit)가 비정상/변조 요청을 **403** 차단. API 외 경로는 ALB **404** 고정응답 |
| **2. 고가용성 및 안정성** | 12 | 멀티 AZ(2개+) 서브넷, RDS **Multi-AZ**, 노드그룹 2대+, Deployment replica 2+, `topologySpreadConstraints`(AZ 분산), HPA 자동 확장, ALB 헬스체크 `/healthcheck` |
| **3. 성능 효율성** | 12 | user/product SLO 0.2s, stress 1.0s 대응 → HPA(CPU 50~60%) 신속 확장, `least_outstanding_requests` 분산, product 동일 id 빈번조회는 PK 조회 최적, 이미지 엣지 캐시 |
| **4. 비용 최적화** | 12 | 기본 노드 최소(2대) + **Karpenter consolidation**(저활용/빈 노드 즉시 제거), single NAT GW, db.t3.micro, CloudFront PriceClass_200, ECR 라이프사이클. 평상시 노드 최소화로 cost ratio(0.5~3.75)를 낮춤 |

### 실격/0점 방지 체크 (채점 사전준비)
- [x] 제출 엔드포인트 = 선수 시스템 단일 엔드포인트(CloudFront) — `terraform output single_endpoint`
- [x] DB 타입/대수: `apdev-rds-instance`, **db.t3.micro**, **Multi-AZ 1대**, MySQL 8.0, gp3 (변경 시 성능/비용 0점)
- [x] 노드 인스턴스 타입 **t3.medium 만** 사용
- [x] **Lambda / Fargate 미사용** (사용 시 전체 0점)
- [x] 모든 리소스 **ap-northeast-2** 단일 리전, 미사용 리소스 없음

---


## 4-1. 노드 오토스케일링 (Karpenter) — 로드 처리 + 비용 최적화 동시 달성

- **인스턴스 타입 명시 제한**: NodePool 에서 `node.kubernetes.io/instance-type In ["t3.medium"]` 로 고정.
  Karpenter 가 다른 타입을 절대 생성하지 않으므로 "t3.medium 만" 제약을 위반하지 않음.
- **로드 처리(가용성/성능)**: 부하로 Pod 가 Pending 되면 Karpenter 가 즉시 t3.medium 노드를 추가.
- **비용 최적화(cost ratio↓)**:
  - 기본 관리형 노드그룹은 시스템용 최소 2대만 상시 운영(앱도 우선 여기에 배치 → 평상시 추가 노드 0).
  - 부하 감소 시 `consolidationPolicy: WhenEmptyOrUnderutilized` + `consolidateAfter: 30s` 로 빈/저활용 노드를 빠르게 정리.
  - `limits.cpu: 16` 으로 최대 t3.medium 8대까지만 (비용 폭주 가드레일).
- 배포: `deploy.ps1` 가 Terraform output(노드 IAM 역할/클러스터명)으로 NodePool·EC2NodeClass 를 자동 치환 적용.

상태 확인:
```bash
kubectl get nodepool,ec2nodeclass
kubectl get nodes -L node.kubernetes.io/instance-type     # 전부 t3.medium 인지 확인
kubectl logs -n kube-system -l app.kubernetes.io/name=karpenter -f
```

> 더 낮은 cost ratio 가 필요하면: 기본 노드그룹을 `node_desired_size=2, node_max_size=2` 로 고정(버스트는 전부 Karpenter)하고,
> 부하 테스트 동안 차단 없는지 확인하며 `limits.cpu` 와 base 크기를 조정. (spot 전환은 중단 위험이 있어 가용성과 트레이드오프)

## 5. 비정상 요청(WAF) 튜닝 안내

문제의 "비정상 요청"은 load test 가 주입하는 변조/오용 요청입니다. 정확한 패턴은 경기 중
트래픽으로 확인되므로, 경기 시작 후 1시간(트래픽 전) 동안 다음을 점검·조정하세요.

- 기본 골격: AWS 관리형 규칙으로 일반 악성/변조 요청을 403 차단, 정상요청은 통과.
- 정상요청이 과차단되면(가용성 하락) `waf.tf` 의 해당 관리형 룰을 `count` 모드로 완화.
- 특정 비정상 패턴(예: requestid/uuid 누락) 확인 시 custom rule 추가:
  CloudWatch / WAF sampled requests 로 패턴을 분석 후 `aws_wafv2_web_acl` 에 규칙 추가.

## 6. 단일 엔드포인트 강제(선택 하드닝)

ALB 직접 노출 방지를 위해 다음 중 하나를 적용 권장:
- CloudFront origin custom header(비밀값) 추가 + ALB 리스너 규칙에서 헤더 검증, 없으면 403/404.
- 또는 ALB 보안그룹 인바운드를 CloudFront 관리형 prefix list 로 제한.

## 7. 정리(리소스 삭제)
```powershell
# 앱/Ingress 먼저 삭제하여 ALB 정리
kubectl delete -f k8s/.rendered
cd terraform
terraform destroy
```
