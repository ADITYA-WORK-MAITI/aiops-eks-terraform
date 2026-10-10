variable "project" {
  description = "Project name, used as a prefix for all resources."
  type        = string
  default     = "aiops"
}

variable "environment" {
  description = "Deployment environment (e.g. dev, staging, prod)."
  type        = string
  default     = "dev"
}

variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "ap-south-1"
}

# --- Networking -------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones to spread subnets and nodes across."
  type        = number
  default     = 3

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "az_count must be 2 or 3 (EKS requires at least two AZs)."
  }
}

variable "single_nat_gateway" {
  description = "Use one shared NAT gateway instead of one per AZ. Cheaper, but not highly available."
  type        = bool
  default     = true
}

# --- EKS --------------------------------------------------------------------

variable "cluster_version" {
  description = "Kubernetes version of the EKS control plane."
  type        = string
  default     = "1.33"
}

variable "node_instance_types" {
  description = "EC2 instance types for the managed node group."
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_capacity_type" {
  description = "Capacity type for worker nodes: ON_DEMAND or SPOT."
  type        = string
  default     = "ON_DEMAND"

  validation {
    condition     = contains(["ON_DEMAND", "SPOT"], var.node_capacity_type)
    error_message = "node_capacity_type must be ON_DEMAND or SPOT."
  }
}

variable "node_min_size" {
  description = "Minimum number of worker nodes."
  type        = number
  default     = 2
}

variable "node_desired_size" {
  description = "Initial number of worker nodes. Cluster Autoscaler adjusts this afterwards."
  type        = number
  default     = 2
}

variable "node_max_size" {
  description = "Maximum number of worker nodes Cluster Autoscaler may scale out to."
  type        = number
  default     = 5
}

variable "cluster_admin_arns" {
  description = "IAM principal ARNs granted cluster-admin access through EKS access entries."
  type        = list(string)
  default     = []
}

# --- Add-ons ----------------------------------------------------------------

variable "lb_controller_chart_version" {
  description = "Helm chart version of the AWS Load Balancer Controller."
  type        = string
  default     = "1.13.3"
}

variable "cluster_autoscaler_chart_version" {
  description = "Helm chart version of Cluster Autoscaler. Its app version should match cluster_version."
  type        = string
  default     = "9.47.0"
}

variable "metrics_server_chart_version" {
  description = "Helm chart version of metrics-server (required by the HorizontalPodAutoscaler)."
  type        = string
  default     = "3.12.2"
}

# --- CI/CD ------------------------------------------------------------------

variable "github_repository" {
  description = "GitHub repository (owner/name) allowed to deploy via OIDC. Leave empty to skip creating the role."
  type        = string
  default     = ""
}

variable "ecr_force_delete" {
  description = "Allow terraform destroy to delete the ECR repository even if it still contains images."
  type        = bool
  default     = false
}
