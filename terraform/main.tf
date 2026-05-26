terraform {
  # 1.10+ required for native S3 state locking (use_lockfile).
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }

  # Remote backend with state locking.
  # Bucket is created by the bootstrap module in terraform/bootstrap/.
  # Replace the bucket name below with the value of the `state_bucket`
  # output from `terraform -chdir=bootstrap apply`.
  backend "s3" {
    bucket       = "yuvan-webapp-tfstate-2026"
    key          = "webapp/dev/terraform.tfstate"
    region       = "ap-south-2"
    profile      = "siddhan" # CLI profile for backend auth (local dev)
    encrypt      = true
    use_lockfile = true # native S3 locking, no DynamoDB needed (TF 1.10+)
  }
}

provider "aws" {
  region = var.region

  # Local-dev convenience: use the named AWS CLI profile automatically.
  # Has no effect in CI/CD (GitHub Actions uses OIDC, not a profile).
  # Remove or change if collaborating with someone using a different profile.
  profile = "siddhan"

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}
