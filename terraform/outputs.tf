output "region" {
  description = "AWS region the stack is deployed in."
  value       = var.region
}

output "vpc_id" {
  description = "ID of the VPC."
  value       = module.vpc.vpc_id
}

output "cluster_name" {
  description = "Name of the EKS cluster."
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "Endpoint of the EKS API server."
  value       = module.eks.cluster_endpoint
}

output "ecr_repository_url" {
  description = "URL of the ECR repository for the analyzer image."
  value       = aws_ecr_repository.app.repository_url
}

output "github_deploy_role_arn" {
  description = "IAM role assumed by GitHub Actions (empty when github_repository is not set)."
  value       = try(aws_iam_role.github_deploy[0].arn, "")
}

output "configure_kubectl" {
  description = "Command that adds the cluster to your kubeconfig."
  value       = "aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}"
}
