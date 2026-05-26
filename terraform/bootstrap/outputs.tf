output "state_bucket" {
  description = "Paste this into terraform/main.tf -> backend \"s3\" -> bucket."
  value       = aws_s3_bucket.tf_state.id
}

output "region" {
  description = "Paste this into terraform/main.tf -> backend \"s3\" -> region."
  value       = var.region
}

output "backend_config_snippet" {
  description = "Copy-paste this into terraform/main.tf"
  value       = <<EOT
  backend "s3" {
    bucket       = "${aws_s3_bucket.tf_state.id}"
    key          = "webapp/terraform.tfstate"
    region       = "${var.region}"
    encrypt      = true
    use_lockfile = true
  }
EOT
}
