output "alb_dns_name" {
  description = "Hit this URL to reach the app."
  value       = aws_lb.app.dns_name
}

output "ecr_repository_url" {
  description = "Push images here."
  value       = aws_ecr_repository.app.repository_url
}

output "ecs_cluster_name" {
  description = "Cluster name (used by CI/CD)."
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "Service name (used by CI/CD)."
  value       = aws_ecs_service.app.name
}

output "cloudwatch_log_group" {
  description = "Where the app's stdout/stderr lands."
  value       = aws_cloudwatch_log_group.app.name
}

output "dashboard_url" {
  description = "CloudWatch dashboard."
  value       = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
}
