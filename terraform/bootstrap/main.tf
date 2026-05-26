terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }
  # Intentionally NO backend block here — local state.
}

provider "aws" {
  region  = var.region
  profile = "siddhan" # local-dev CLI profile

  default_tags {
    tags = {
      Project   = "webapp"
      Purpose   = "terraform-backend"
      ManagedBy = "terraform"
    }
  }
}

resource "aws_s3_bucket" "tf_state" {
  bucket = var.state_bucket_name

  # Set to true ONLY in throwaway envs. In prod, leave false so an accidental
  # `terraform destroy` here doesn't wipe every state file you've ever stored.
  force_destroy = false

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  versioning_configuration {
    status = "Enabled" # lets you recover from a bad apply
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket                  = aws_s3_bucket.tf_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Expire old state versions so storage doesn't grow forever.
resource "aws_s3_bucket_lifecycle_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {} # apply to whole bucket

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

