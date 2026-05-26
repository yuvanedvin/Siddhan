variable "project_name" {
  description = "Short name used as a prefix for all resources."
  type        = string
  default     = "webapp"
}

variable "environment" {
  description = "Deployment environment (dev / staging / prod)."
  type        = string
  default     = "dev"
}

variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "ap-south-2"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDRs for public subnets (one per AZ)."
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDRs for private subnets (one per AZ)."
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24"]
}

variable "container_port" {
  description = "Port the container listens on."
  type        = number
  default     = 8080
}

variable "container_image" {
  description = "Full image URI. If empty, falls back to ECR repo + :latest."
  type        = string
  default     = ""
}

variable "task_cpu" {
  description = "Fargate task CPU units (256 = 0.25 vCPU)."
  type        = number
  default     = 256
}

variable "task_memory" {
  description = "Fargate task memory in MiB."
  type        = number
  default     = 512
}

variable "desired_count" {
  description = "Initial number of running tasks."
  type        = number
  default     = 2
}

variable "min_capacity" {
  description = "Minimum tasks for autoscaling."
  type        = number
  default     = 2
}

variable "max_capacity" {
  description = "Maximum tasks for autoscaling."
  type        = number
  default     = 6
}

variable "log_retention_days" {
  description = "CloudWatch log retention. Lower = cheaper."
  type        = number
  default     = 14
}
