locals {
  name_prefix = "${var.project_name}-${var.environment}"
  azs         = slice(data.aws_availability_zones.available.names, 0, 2)

  # If no image is passed in, the ECS task uses the ECR repo's :latest tag.
  # CI/CD pushes new tags and updates the service via aws ecs update-service.
  image = var.container_image != "" ? var.container_image : "${aws_ecr_repository.app.repository_url}:latest"
}
