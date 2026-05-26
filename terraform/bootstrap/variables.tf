variable "region" {
  description = "AWS region for the state bucket. Should match where you deploy."
  type        = string
  default     = "ap-south-2"
}

variable "state_bucket_name" {
  description = <<EOT
S3 bucket name for Terraform remote state.

Must be globally unique across all of AWS. Use a pattern like:
  <yourname>-<project>-tfstate-<account_id_suffix>
e.g. "yuvan-webapp-tfstate-2026"
EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.state_bucket_name))
    error_message = "Bucket name must be 3-63 chars, lowercase, digits/hyphens only."
  }
}
