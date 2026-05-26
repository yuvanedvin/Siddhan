# IAM setup for this project

## TL;DR

Create **one dedicated IAM user** for this project (don't use root, don't reuse
a personal admin). It needs permissions to create the infrastructure in
`terraform/` and the bootstrap bucket in `terraform/bootstrap/`.

## Recommended approach

```bash
# 1. Create the user
aws iam create-user --user-name terraform-webapp

# 2. For the assessment, attach PowerUserAccess + IAMFullAccess.
#    PowerUser covers VPC/ECS/ECR/ALB/CloudWatch/S3.
#    IAMFullAccess is needed because the project creates IAM roles.
aws iam attach-user-policy --user-name terraform-webapp \
  --policy-arn arn:aws:iam::aws:policy/PowerUserAccess
aws iam attach-user-policy --user-name terraform-webapp \
  --policy-arn arn:aws:iam::aws:policy/IAMFullAccess

# 3. Generate an access key
aws iam create-access-key --user-name terraform-webapp
# Save the AccessKeyId and SecretAccessKey it prints — you won't see the secret again.

# 4. Configure a named CLI profile so you don't pollute your default
aws configure --profile webapp
#   AWS Access Key ID     [None]: <paste>
#   AWS Secret Access Key [None]: <paste>
#   Default region        [None]: ap-south-2
#   Default output format [None]: json

# 5. Use the profile for every Terraform command
export AWS_PROFILE=webapp
aws sts get-caller-identity   # should show terraform-webapp user
```

Then run `terraform apply` as normal — it'll pick up `AWS_PROFILE` from the env.

## Should it be a user or a role?

- **IAM user with access keys**: simplest, works from anywhere. Fine for an
  assessment / single developer.
- **IAM role assumed via SSO (IAM Identity Center)**: better, no long-lived
  keys. Use this if you already have SSO set up.

The CI/CD pipeline already uses an OIDC role (see README step 2) — that's
separate from this local-dev user.

## Tighter policy (production-ish)

`PowerUserAccess` is broad. If you want a least-privilege policy, attach this
inline policy instead. It covers exactly what this project provisions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Networking",
      "Effect": "Allow",
      "Action": [
        "ec2:*Vpc*", "ec2:*Subnet*", "ec2:*InternetGateway*",
        "ec2:*NatGateway*", "ec2:*RouteTable*", "ec2:*Route",
        "ec2:*SecurityGroup*", "ec2:*Address*", "ec2:DescribeAvailabilityZones",
        "ec2:DescribeNetworkInterfaces", "ec2:CreateTags", "ec2:DeleteTags"
      ],
      "Resource": "*"
    },
    {
      "Sid": "LoadBalancing",
      "Effect": "Allow",
      "Action": ["elasticloadbalancing:*"],
      "Resource": "*"
    },
    {
      "Sid": "Containers",
      "Effect": "Allow",
      "Action": ["ecs:*", "ecr:*", "application-autoscaling:*"],
      "Resource": "*"
    },
    {
      "Sid": "Observability",
      "Effect": "Allow",
      "Action": ["logs:*", "cloudwatch:*"],
      "Resource": "*"
    },
    {
      "Sid": "IAMForRoles",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:PassRole",
        "iam:AttachRolePolicy", "iam:DetachRolePolicy",
        "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy",
        "iam:ListAttachedRolePolicies", "iam:ListRolePolicies",
        "iam:TagRole", "iam:UntagRole",
        "iam:CreateOpenIDConnectProvider", "iam:GetOpenIDConnectProvider",
        "iam:CreateServiceLinkedRole"
      ],
      "Resource": "*"
    },
    {
      "Sid": "BackendBucket",
      "Effect": "Allow",
      "Action": ["s3:*"],
      "Resource": [
        "arn:aws:s3:::*-tfstate-*",
        "arn:aws:s3:::*-tfstate-*/*"
      ]
    }
  ]
}
```

Save as `iam-policy.json` and attach:

```bash
aws iam put-user-policy --user-name terraform-webapp \
  --policy-name terraform-webapp-inline \
  --policy-document file://iam-policy.json
```

## Cleanup when you're done

```bash
aws iam list-access-keys --user-name terraform-webapp
aws iam delete-access-key --user-name terraform-webapp --access-key-id <id>
aws iam detach-user-policy --user-name terraform-webapp --policy-arn ...
aws iam delete-user --user-name terraform-webapp
```
