# Cluster add-ons installed with Helm. Each controller that calls AWS APIs gets
# its own IAM role bound to its Kubernetes service account (IRSA).

# --- AWS Load Balancer Controller -------------------------------------------
# Watches Ingress resources and provisions Application Load Balancers.

module "lb_controller_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.55"

  role_name                              = "${local.name}-aws-lb-controller"
  attach_load_balancer_controller_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:aws-load-balancer-controller"]
    }
  }
}

resource "helm_release" "aws_lb_controller" {
  name       = "aws-load-balancer-controller"
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  version    = var.lb_controller_chart_version
  namespace  = "kube-system"

  values = [yamlencode({
    clusterName = module.eks.cluster_name
    region      = var.region
    vpcId       = module.vpc.vpc_id
    serviceAccount = {
      name        = "aws-load-balancer-controller"
      annotations = { "eks.amazonaws.com/role-arn" = module.lb_controller_irsa.iam_role_arn }
    }
  })]

  depends_on = [module.eks]
}

# --- Cluster Autoscaler -----------------------------------------------------
# Scales the managed node group between node_min_size and node_max_size.
# EKS tags managed node group ASGs for auto-discovery automatically.

module "cluster_autoscaler_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.55"

  role_name                        = "${local.name}-cluster-autoscaler"
  attach_cluster_autoscaler_policy = true
  cluster_autoscaler_cluster_names = [module.eks.cluster_name]

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:cluster-autoscaler"]
    }
  }
}

resource "helm_release" "cluster_autoscaler" {
  name       = "cluster-autoscaler"
  repository = "https://kubernetes.github.io/autoscaler"
  chart      = "cluster-autoscaler"
  version    = var.cluster_autoscaler_chart_version
  namespace  = "kube-system"

  values = [yamlencode({
    awsRegion = var.region
    autoDiscovery = {
      clusterName = module.eks.cluster_name
    }
    rbac = {
      serviceAccount = {
        name        = "cluster-autoscaler"
        annotations = { "eks.amazonaws.com/role-arn" = module.cluster_autoscaler_irsa.iam_role_arn }
      }
    }
    extraArgs = {
      balance-similar-node-groups = true
      skip-nodes-with-system-pods = false
    }
  })]

  depends_on = [module.eks]
}

# --- metrics-server ---------------------------------------------------------
# Provides the resource metrics API that the HorizontalPodAutoscaler reads.

resource "helm_release" "metrics_server" {
  name       = "metrics-server"
  repository = "https://kubernetes-sigs.github.io/metrics-server"
  chart      = "metrics-server"
  version    = var.metrics_server_chart_version
  namespace  = "kube-system"

  depends_on = [module.eks]
}
