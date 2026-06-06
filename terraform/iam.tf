###############################################################################
# iam.tf  - IRSA (IAM Roles for Service Accounts)
###############################################################################

# --- EBS CSI Driver (PV ?™ì  ?„ë¡œë¹„ì??? -----------------------------------
module "ebs_csi_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.48"

  role_name             = "${local.name}-ebs-csi-irsa"
  attach_ebs_csi_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:ebs-csi-controller-sa"]
    }
  }

  tags = local.tags
}

# --- AWS Load Balancer Controller (ALB Ingress ?„ë¡œë¹„ì??? -------------------
module "lb_controller_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.48"

  role_name                              = "${local.name}-lb-controller-irsa"
  attach_load_balancer_controller_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:aws-load-balancer-controller"]
    }
  }

  tags = local.tags
}

# --- ExternalDNS (Route53 ?ˆì½”???ë™ ê´€ë¦? ?„ë©”???¬ìš© ?? ------------------
module "external_dns_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.48"

  count = local.use_domain ? 1 : 0

  role_name                     = "${local.name}-external-dns-irsa"
  attach_external_dns_policy    = true
  external_dns_hosted_zone_arns = ["arn:aws:route53:::hostedzone/*"]

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:external-dns"]
    }
  }

  tags = local.tags
}

# --- ? í”Œë¦¬ì??´ì…˜??S3 ?‘ê·¼ IRSA (product ???´ë?ì§€ ?…ë¡œ?? ------------------
data "aws_iam_policy_document" "app_s3" {
  statement {
    sid    = "AppS3ObjectAccess"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${aws_s3_bucket.images.arn}/*"]
  }

  statement {
    sid       = "AppS3ListBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.images.arn]
  }
}

resource "aws_iam_policy" "app_s3" {
  name   = "${local.name}-app-s3-policy"
  policy = data.aws_iam_policy_document.app_s3.json
  tags   = local.tags
}

module "app_s3_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.48"

  role_name = "${local.name}-app-s3-irsa"

  role_policy_arns = {
    s3 = aws_iam_policy.app_s3.arn
  }

  oidc_providers = {
    main = {
      provider_arn = module.eks.oidc_provider_arn
      # apps ?¤ìž„?¤íŽ˜?´ìŠ¤??product ?œë¹„?¤ì–´ì¹´ìš´??      namespace_service_accounts = ["apps:product-sa"]
    }
  }

  tags = local.tags
}

