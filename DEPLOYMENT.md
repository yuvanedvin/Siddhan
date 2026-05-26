# Deployment Guide

Complete end-to-end walkthrough — from a freshly configured AWS CLI to a
live, CI/CD-deployed application. Roughly 30–45 minutes.

Commands shown in **PowerShell** since the project was developed on Windows.
Bash equivalents are noted only where the syntax meaningfully differs.

> ⚠️ Two PowerShell-specific gotchas that bit the project during development
> and are pre-fixed in the commands below:
>
> 1. PowerShell's pipe re-encodes data as UTF-16, which breaks
>    `docker login --password-stdin`. Use `--password` instead.
> 2. PowerShell 5.1's `Set-Content -Encoding utf8` writes a BOM, which AWS
>    IAM rejects as invalid JSON. Use `Out-File -Encoding ascii` (the
>    policy is ASCII-only) or `[System.IO.File]::WriteAllText`.

---

## Phase 0 — Prerequisites

```powershell
aws --version                  # AWS CLI v2.x
terraform -version             # >= 1.10.0 (required for use_lockfile)
docker --version
git --version
```

Set UTF-8 output for this session (also fixes both gotchas above for the
rest of the shell):

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
```

To make permanent, add those lines to `notepad $PROFILE`.

## Phase 1 — IAM user (one-time)

See [`docs/iam-setup.md`](docs/iam-setup.md) for the full guide. Short
version: create a dedicated IAM user with `PowerUserAccess` +
`IAMFullAccess`, configure a named CLI profile.

```powershell
$env:AWS_PROFILE = "siddhan"
aws sts get-caller-identity        # confirm
```

## Phase 2 — Bootstrap the remote state bucket (one-time)

The bucket has to be globally unique across all of AWS. Pick a name with
your handle and some entropy if the default is taken.

```powershell
cd terraform/bootstrap
terraform init
terraform apply -var="state_bucket_name=yuvan-siddhan-webapp-tfstate"
```

If you change the name here, **also** update `terraform/main.tf` line ~17
(`bucket = "..."`) to match — they must agree.

## Phase 3 — Deploy the main infrastructure

```powershell
cd ..                              # back to terraform/
terraform init                     # initializes S3 backend
terraform plan                     # review ~45 resources
terraform apply                    # type yes — ~5-8 min (NAT is slow)
```

Capture the outputs for later phases:

```powershell
$REGION  = "ap-south-2"
$ECR     = terraform output -raw ecr_repository_url
$CLUSTER = terraform output -raw ecs_cluster_name
$SERVICE = terraform output -raw ecs_service_name
$ALB     = terraform output -raw alb_dns_name

Write-Host "ECR:     $ECR"
Write-Host "Cluster: $CLUSTER"
Write-Host "Service: $SERVICE"
Write-Host "ALB:     $ALB"
```

## Phase 4 — Build and push the first image

ECS is already running, but the ECR repo is empty — tasks will keep
restarting until you push an image.

```powershell
cd ..                              # back to project root

# Capture password to a variable to avoid PowerShell pipe encoding issues
$pwd = aws ecr get-login-password --region $REGION
docker login --username AWS --password $pwd $ECR

docker build -t webapp ./app
docker tag webapp:latest "${ECR}:latest"
docker push "${ECR}:latest"
```

## Phase 5 — Force ECS to pull the new image

```powershell
aws ecs update-service --cluster $CLUSTER --service $SERVICE --force-new-deployment --region $REGION

# Wait ~2 min for rollout to complete
aws ecs wait services-stable --cluster $CLUSTER --services $SERVICE --region $REGION

# Verify (use curl.exe, NOT the PowerShell curl alias which is Invoke-WebRequest)
curl.exe "http://$ALB/"
curl.exe "http://$ALB/health"
```

You should see JSON from `/` and `{"status":"ok"}` from `/health`. **The
app is live.**

## Phase 6 — Wire up CI/CD

### 6a. Push the project to GitHub

Create an empty repo on github.com first. Then:

```powershell
git init -b main
git add .
git commit -m "Initial commit: cloud architecture assessment"
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

A browser opens for GitHub authentication on first push — approve it.

> **Why HTTPS, not SSH?** Git for Windows ships with Git Credential Manager,
> which uses an OAuth browser flow. Avoids the SSH-key setup overhead.

### 6b. Create the OIDC provider (one-time per AWS account)

```powershell
aws iam create-open-id-connect-provider `
  --url https://token.actions.githubusercontent.com `
  --client-id-list sts.amazonaws.com `
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

"Already exists" is fine — skip.

### 6c. Create the deploy role

```powershell
$ACCOUNT_ID = aws sts get-caller-identity --query Account --output text
$GH_USER = "<your-github-username>"      # ← replace
$REPO    = "<your-repo-name>"            # ← replace

$trustPolicy = @"
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Federated": "arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com" },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
      "StringLike":   { "token.actions.githubusercontent.com:sub": "repo:${GH_USER}/${REPO}:ref:refs/heads/main" }
    }
  }]
}
"@

# Out-File -Encoding ascii avoids the UTF-8 BOM that PowerShell 5.1 adds
# with -Encoding utf8 (and that AWS IAM rejects as invalid JSON)
$trustPolicy | Out-File -FilePath .\trust.json -Encoding ascii

# Verify: first byte should be 123 (the '{' character), not 239 (start of BOM)
$bytes = [System.IO.File]::ReadAllBytes((Resolve-Path .\trust.json).Path)
"First byte: $($bytes[0])  (expected 123)"
```

If the path ever gives `PathTooLongException`, write to `C:\Temp\trust.json`
instead and reference `file://C:/Temp/trust.json` below.

```powershell
aws iam create-role --role-name github-deploy-webapp --assume-role-policy-document file://trust.json

aws iam attach-role-policy --role-name github-deploy-webapp --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser
aws iam attach-role-policy --role-name github-deploy-webapp --policy-arn arn:aws:iam::aws:policy/AmazonECS_FullAccess
aws iam attach-role-policy --role-name github-deploy-webapp --policy-arn arn:aws:iam::aws:policy/IAMReadOnlyAccess

$DEPLOY_ROLE_ARN = aws iam get-role --role-name github-deploy-webapp --query Role.Arn --output text
Write-Host $DEPLOY_ROLE_ARN

Remove-Item .\trust.json
```

### 6d. Add the GitHub secret

On github.com → your repo → **Settings → Secrets and variables → Actions →
New repository secret**:

- **Name:** `AWS_DEPLOY_ROLE_ARN`
- **Value:** the ARN printed above

### 6e. Fill role ARNs into the task definition

```powershell
$EXEC_ARN = aws iam get-role --role-name webapp-dev-task-execution --query Role.Arn --output text
$TASK_ARN = aws iam get-role --role-name webapp-dev-task --query Role.Arn --output text

$path = ".github\ecs\task-definition.json"

(Get-Content $path) `
  -replace 'REPLACE_WITH_EXECUTION_ROLE_ARN', $EXEC_ARN `
  -replace 'REPLACE_WITH_TASK_ROLE_ARN', $TASK_ARN |
  Set-Content $path -Encoding utf8

Select-String -Pattern "RoleArn" -Path $path
```

### 6f. Commit and trigger the pipeline

```powershell
git add .github/ecs/task-definition.json
git commit -m "Wire CI/CD with role ARNs"
git push
```

Go to GitHub → **Actions** tab → watch `build-and-deploy`. ~3 minutes.
When green, hit the ALB again — the `host` field in the response should
change, proving new tasks rolled in.

## Phase 7 — Verify monitoring

```powershell
# Live tail logs (Ctrl+C to stop)
aws logs tail /ecs/webapp-dev --follow --region $REGION

# Open the dashboard
$DASHBOARD = terraform -chdir=terraform output -raw dashboard_url
Start-Process $DASHBOARD

# Alarm states — should be OK or INSUFFICIENT_DATA early on
aws cloudwatch describe-alarms --alarm-name-prefix webapp-dev --query "MetricAlarms[].{Name:AlarmName,State:StateValue}" --output table

# Generate traffic so dashboard widgets fill in
1..50 | ForEach-Object { Invoke-RestMethod "http://$ALB/" | Out-Null; Start-Sleep -Milliseconds 200 }
```

## Phase 8 — Submission checklist

- [ ] Live ALB URL noted at the top of the README
- [ ] Git repo on GitHub with all Terraform, app, and CI/CD code committed
- [ ] At least one green Actions run on `main`
- [ ] `docs/architecture.svg` renders in the README on GitHub
- [ ] README covers design decisions, trade-offs, cost
- [ ] DEPLOYMENT.md (this file) committed

---

## Tear down

### 1. Destroy main infrastructure

```powershell
$env:AWS_PROFILE = "siddhan"
cd terraform
terraform destroy             # ~5 min
```

ECR has `force_delete = true`, so this cleans up images too.

### 2. Optional — remove the GitHub deploy role

```powershell
aws iam detach-role-policy --role-name github-deploy-webapp --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser
aws iam detach-role-policy --role-name github-deploy-webapp --policy-arn arn:aws:iam::aws:policy/AmazonECS_FullAccess
aws iam detach-role-policy --role-name github-deploy-webapp --policy-arn arn:aws:iam::aws:policy/IAMReadOnlyAccess
aws iam delete-role --role-name github-deploy-webapp
```

### 3. Optional — tear down the bootstrap state bucket

The bucket has `prevent_destroy = true` and versioning enabled, so this is
deliberate work. Skip if you might come back to this project.

```powershell
# 3a. Remove the lifecycle guard from bootstrap/main.tf
cd bootstrap
(Get-Content main.tf -Raw) -replace '(?s)\s*lifecycle\s*\{\s*prevent_destroy\s*=\s*true\s*\}', '' | Set-Content main.tf -NoNewline

# 3b. Empty the bucket — including all object versions AND delete markers
$bucket = "yuvan-siddhan-webapp-tfstate"
$obj = aws s3api list-object-versions --bucket $bucket --output json | ConvertFrom-Json

$toDelete = @()
if ($obj.Versions)      { $toDelete += @($obj.Versions      | ForEach-Object { @{ Key = $_.Key; VersionId = $_.VersionId } }) }
if ($obj.DeleteMarkers) { $toDelete += @($obj.DeleteMarkers | ForEach-Object { @{ Key = $_.Key; VersionId = $_.VersionId } }) }

if ($toDelete.Count -gt 0) {
  $payload = @{ Objects = $toDelete; Quiet = $true } | ConvertTo-Json -Depth 4 -Compress
  [System.IO.File]::WriteAllText("$PWD\delete-payload.json", $payload)
  aws s3api delete-objects --bucket $bucket --delete file://delete-payload.json
  Remove-Item .\delete-payload.json
}

# 3c. Verify empty
aws s3api list-object-versions --bucket $bucket

# 3d. Destroy
terraform destroy
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `No valid credential sources found` | `AWS_PROFILE` not set | `$env:AWS_PROFILE = "siddhan"` |
| `docker login ... 400 Bad Request` | PowerShell pipe encoding | Use `$pwd = aws ...; docker login --password $pwd ...` |
| `MalformedPolicyDocument: invalid JSON` | UTF-8 BOM from `Set-Content -Encoding utf8` | Use `Out-File -Encoding ascii` |
| `PathTooLongException` | .NET hates the long folder name | Write to `C:\Temp\trust.json` instead |
| `Permission denied (publickey)` on `git push` | SSH remote without registered key | Switch to HTTPS: `git remote set-url origin https://github.com/USER/REPO.git` |
| `BucketAlreadyExists` | Bucket name not globally unique | Add suffix; update `terraform/main.tf` to match |
| `RepositoryNotEmptyException` on destroy | Images in ECR | Already fixed via `force_delete = true` |
| `BucketNotEmpty` on destroy of bootstrap | Versioned bucket has versions/markers | Run the version-cleanup snippet in Tear down step 3b |
| `NoSuchEntity` on `iam create-role` | OIDC provider missing | Run `create-open-id-connect-provider` first |
| ALB returns 503 for ~90s after deploy | Health checks haven't passed yet | Wait, don't debug |
