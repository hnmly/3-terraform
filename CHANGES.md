# 대회 당일 변경 대응 치트시트 (CHANGES.md)

실제 대회는 기준 문제에서 ~20% 정도 값이 바뀝니다(인스턴스 타입, 리전, DB, 앱 등).
"무엇이 바뀌면 어느 파일을 고치는가"를 정리합니다. 대부분 `terraform/variables.tf` 한 곳이지만,
**여러 파일을 동시에 고쳐야 하는 항목(⚠️)** 을 놓치지 마세요.

## 변경 맵

| 바뀌는 것 | 수정 파일 / 위치 | 비고 |
|---|---|---|
| 리전 (ap-northeast-2 → 다른 곳) | ⚠️ ① `terraform/variables.tf` `region` ② `deploy.ps1` `$REGION` ③ `k8s/11-product.yaml` `AWS_REGION` | CloudFront/WAF용 us-east-1(acm.tf/waf.tf/tools `--waf-region`)은 그대로 둠 |
| DB 인스턴스 타입 (db.t3.micro → ) | `terraform/variables.tf` `db_instance_class` | 상위 타입이면 `rds.tf` `performance_insights_enabled=true` 가능 |
| DB identifier | `terraform/variables.tf` `db_identifier` | |
| DB 엔진 버전 (8.0 → 8.4 등) | ⚠️ ① `terraform/variables.tf` `db_engine_version` ② `rds.tf` 파라미터그룹 `family` | family는 `mysql8.4` 식으로 메이저 일치 필요 |
| 논리 DB 이름 (dev → ) | ⚠️ ① `terraform/variables.tf` `db_name` ② `db/init.sql` 의 `CREATE DATABASE`/`USE` | 앱 MYSQL_DBNAME 은 Secret 자동 주입(수정 불필요) |
| DB 계정 / 스토리지 | `terraform/variables.tf` `db_username` / `db_allocated_storage`, `rds.tf` `storage_type` | |
| Multi-AZ 여부 | `rds.tf` `multi_az` | |
| 노드 인스턴스 타입 (t3.medium → 다른 x86) | ⚠️ ① `terraform/variables.tf` `node_instance_type` ② `k8s/karpenter/01-nodepool.yaml` `instance-type values` | 두 곳 반드시 동시 변경 |
| 노드가 ARM(t4g 등)으로 | 위 2곳 + ③ `eks.tf` `ami_type=AL2023_ARM64_STANDARD` ④ `nodepool.yaml` `arch:["arm64"]` ⑤ `deploy.ps1` `--platform linux/arm64` ⑥ ARM 바이너리 | 아키텍처 변경은 영향 큼 |
| 노드 수 / 스케일 | `terraform/variables.tf` `node_min/max/desired_size`, `nodepool.yaml` `limits.cpu` | |
| EKS 버전 | `terraform/variables.tf` `cluster_version` (+필요시 `karpenter_version`) | |
| 앱 개수/이름 (user/product/stress → ) | ⚠️ ① `ecr.tf` `ecr_repos` ② `k8s/1x-*.yaml` ③ `deploy.ps1` `$apps` ④ `iam.tf` product SA ⑤ `k8s/20-ingress.yaml` 경로 | |
| 앱 포트 (8080 → ) | `k8s/1x-*.yaml` `containerPort`/`targetPort`/probe, `20-ingress.yaml` healthcheck | |
| API 경로 (/v1/user 등) | ⚠️ ① `k8s/20-ingress.yaml` 라우팅 ② `tools/*` 경로 | 404 동작도 ingress 에서 |
| SLO 목표시간 (0.2s/1s → ) | `tools/log_analyzer.py`·`tools/web_dashboard.py` `SLO_MS` | 분석용(인프라 무관) |
| 이미지 경로 (/images → ) | `cloudfront.tf` `/images/*` behavior | |
| 도메인 사용 | `terraform/variables.tf` `domain_name`/`subdomain`/`create_route53_zone` | ACM·R53 자동 |
| VPC 대역 / AZ 수 | `terraform/variables.tf` `vpc_cidr`/`az_count` | |
| WAF 규칙 / 차단 | `waf.tf` (룰 추가/완화), `variables.tf` `waf_rate_limit` | |

## 가장 자주 틀리는 "동시 수정" 3가지
1. 노드 타입 → `variables.tf` + `k8s/karpenter/01-nodepool.yaml` (둘 다). 한쪽만 바꾸면 관리형 노드와 Karpenter 노드 타입이 어긋남.
2. 리전 → `variables.tf` + `deploy.ps1` + `k8s/11-product.yaml` (세 곳).
3. DB 엔진 버전 → `variables.tf` + `rds.tf` 파라미터그룹 `family`.

## 변경 후 적용
- 인프라 변경(노드타입/DB/리전 등):
  ```
  terraform apply -var="enable_cloudfront=true" -var="alb_dns_name=$ALB"
  ```
- k8s 매니페스트 변경(앱/포트/경로/노드풀):
  ```
  .\deploy.ps1
  ```
- DB 이름 변경: terraform apply 후 db-init Job 재생성, 또는 수동 적재(README 참고).

## RDS 고정값 주의 (채점 0점 위험)
DB 타입/대수는 문제에서 지정한 값을 그대로 따라야 합니다. 문제가 새 값을 제시하면
그 값으로 `variables.tf` 를 바꾸되, 임의로 추가 인스턴스(read replica 등)를 만들지 마세요.