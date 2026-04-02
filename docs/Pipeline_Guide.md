# AWS SFTP Malware Router — CI/CD Pipeline Guide

This guide covers all the manual setup steps required to enable the automated SAM deployment pipeline via GitHub Actions.

---

## Pipeline Architecture

```
feature/* branch ──► PR to dev ──► Validate (lint + build)
                                        │
                                   Merge to dev
                                        │
                              Push triggers dev-deploy.yml
                                        │
                              Validate ──► Deploy to Dev
                                              │
                                    CloudFormation Stack
                                  (dev-sftp-malware-router)


(Future)
qa branch   ──► qa-deploy.yml   ──► Deploy to QA
prod branch ──► prod-deploy.yml ──► Deploy to Prod (with approval gate)
```

### Workflow Files

| File | Trigger | Action |
|---|---|---|
| `.github/workflows/dev-deploy.yml` | Push to `dev` | Validate + Deploy to Dev |
| `.github/workflows/dev-deploy.yml` | PR to `dev` | Validate only (no deploy) |
| `.github/workflows/qa-deploy.yml` | *(create later)* | Validate + Deploy to QA |
| `.github/workflows/prod-deploy.yml` | *(create later)* | Validate + Deploy to Prod |

### What SAM Deploys Automatically

All of the following are created/updated by the SAM template on each deploy:

- S3 Buckets (inbound + infected quarantine)
- S3 Bucket Policies (production + infected)
- SNS Topic + Email Subscription
- IAM Roles (Lambda, SFTP User, EventBridge)
- Lambda Function (with environment variables)
- EventBridge Rule (GuardDuty → Lambda)
- AWS Transfer Family SFTP Server

---

## Step 1: Create AWS OIDC Identity Provider for GitHub

This allows GitHub Actions to authenticate with AWS without storing access keys.

1. Go to **IAM Console** → **Identity providers** → **Add provider**.
2. Fill in:
   - **Provider type:** OpenID Connect
   - **Provider URL:** `https://token.actions.githubusercontent.com`
   - Click **Get thumbprint**
   - **Audience:** `sts.amazonaws.com`
3. Click **Add provider**.

---

## Step 2: Create the GitHub Actions Deploy Role

### 2.1 — Create the Role

1. Go to **IAM Console** → **Roles** → **Create role**.
2. **Trusted entity type:** Web identity.
3. **Identity provider:** `token.actions.githubusercontent.com`
4. **Audience:** `sts.amazonaws.com`
5. Click **Next**.

### 2.2 — Attach Permissions

Attach the following AWS managed policies (or create a scoped custom policy):

| Policy | Purpose |
|---|---|
| `AWSCloudFormationFullAccess` | Create/update/delete CloudFormation stacks |
| `IAMFullAccess` | Create IAM roles and policies within the stack |
| `AmazonS3FullAccess` | Create S3 buckets and bucket policies |
| `AWSLambda_FullAccess` | Deploy Lambda functions |
| `AmazonSNSFullAccess` | Create SNS topics and subscriptions |
| `AmazonEventBridgeFullAccess` | Create EventBridge rules |
| `AWSTransferFullAccess` | Create Transfer Family servers |

> **Production recommendation:** Replace the above with a minimal custom policy scoped to only the resources this stack manages.

### 2.3 — Name and Create

1. **Role name:** `github-actions-sftp-deploy-role`
2. Click **Create role**.

### 2.4 — Restrict Trust Policy to Your Repository

1. Go to the role → **Trust relationships** tab → **Edit trust policy**.
2. Replace with:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Federated": "arn:aws:iam::744640651507:oidc-provider/token.actions.githubusercontent.com"
            },
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Condition": {
                "StringEquals": {
                    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                },
                "StringLike": {
                    "token.actions.githubusercontent.com:sub": "repo:maksandaruwan/AWS-SFTP-PORTAL:*"
                }
            }
        }
    ]
}
```
3. Click **Update policy**.
4. Copy the **Role ARN** (e.g., `arn:aws:iam::744640651507:role/github-actions-sftp-deploy-role`).

---

## Step 3: Enable GuardDuty Malware Protection

> This is a one-time per-account/region setup. Cannot be automated via SAM.

1. Go to **Amazon GuardDuty Console**.
2. If not enabled, click **Enable GuardDuty**.
3. Go to **Malware Protection** → **Malware Protection for S3**.
4. Click **Enable** and select the **`dev-sftp-inbound-quarantine`** bucket.

> Repeat this step for QA/Prod buckets when those environments are deployed.

---

## Step 4: Configure GitHub Repository

### 4.1 — Add the Deploy Secret

1. Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions**.
2. Click **New repository secret**.
3. **Name:** `AWS_DEPLOY_ROLE_ARN`
4. **Value:** The Role ARN from Step 2.4 (e.g., `arn:aws:iam::744640651507:role/github-actions-sftp-deploy-role`)
5. Click **Add secret**.

### 4.2 — Create GitHub Environments

1. Go to **Settings** → **Environments**.
2. Click **New environment** → Name: `dev` → **Configure environment**.
   - No protection rules needed for Dev.
3. *(Later)* Create `qa` environment — optionally add required reviewers.
4. *(Later)* Create `production` environment — **add required reviewers** for approval gate.

### 4.3 — Create the `dev` Branch

```bash
git checkout main
git pull origin main
git checkout -b dev
git push -u origin dev
```

### 4.4 — Merge the Feature Branch

Option A — Via GitHub UI:
1. Go to the repo on GitHub.
2. Create a **Pull Request** from `feature/automation-pipeline` → `dev`.
3. Review and **Merge**.

Option B — Via CLI:
```bash
git checkout dev
git merge feature/automation-pipeline
git push origin dev
```

> Merging to `dev` will trigger the first pipeline run automatically.

---

## Step 5: Verify the First Pipeline Run

1. Go to your repo → **Actions** tab.
2. You should see the **"Dev - Deploy SFTP Malware Router"** workflow running.
3. It will:
   - **Validate:** SAM lint + build
   - **Deploy:** Create the CloudFormation stack `dev-sftp-malware-router`
4. Once complete, go to **AWS CloudFormation Console** → verify the stack status is `CREATE_COMPLETE`.
5. Check the **Outputs** tab for:
   - SFTP Server endpoint
   - Bucket names
   - Role ARNs

---

## Step 6: Post-Deploy Manual Tasks

### 6.1 — Confirm SNS Email Subscription

1. After the first deploy, the email address in `samconfig.toml` receives a confirmation email.
2. Click the **Confirm subscription** link in the email.
3. Without this, malware alert emails will not be delivered.

### 6.2 — Add SFTP Users

SFTP users must be added manually (one-time per client).

1. Go to **AWS Transfer Family Console** → select the SFTP server created by the stack.
2. Click **Add user**.
3. Fill in:
   - **Username:** e.g., `healthworks-user`
   - **Role:** Use the `SFTPUserRoleArn` from the stack Outputs
   - **Home directory bucket:** `dev-sftp-inbound-quarantine`
   - **Home directory prefix:** `healthworks/<username>/uploads`
   - **Restricted:** Yes
4. **SSH public keys:** Paste the client's public key.
5. Click **Add**.
6. Share the connection details with the client:

| Detail | Value |
|---|---|
| Host | `SFTPServerEndpoint` from stack Outputs |
| Port | 22 |
| Username | The username you created |
| Auth | Client's SSH private key |
| Allowed files | `.pdf` / `.PDF` only |
| Upload path | `/healthworks/<username>/uploads/` |

---

## Step 7: Update samconfig.toml for QA / Prod

When ready to add QA or Prod, update these placeholders in `samconfig.toml`:

```toml
# QA
[qa.deploy.parameters]
parameter_overrides = [
    "Environment=qa",
    "CleanBucketName=<YOUR-QA-CLEAN-BUCKET>",
    "AlertEmail=<YOUR-QA-ALERT-EMAIL>",
    "AuthorizedUserArns=<ARN1>,<ARN2>"
]

# PROD
[prod.deploy.parameters]
parameter_overrides = [
    "Environment=prod",
    "CleanBucketName=<YOUR-PROD-CLEAN-BUCKET>",
    "AlertEmail=<YOUR-PROD-ALERT-EMAIL>",
    "AuthorizedUserArns=<ARN1>,<ARN2>"
]
```

---

## Step 8: Create QA and Prod Workflow Files

When ready, create these files following the same pattern as `dev-deploy.yml`:

### qa-deploy.yml

Copy `dev-deploy.yml` and change:
- `name:` → `QA - Deploy SFTP Malware Router`
- `branches:` → `qa` (both push and PR)
- `environment:` → `qa`
- `--config-env` → `qa`

### prod-deploy.yml

Copy `dev-deploy.yml` and change:
- `name:` → `Prod - Deploy SFTP Malware Router`
- `branches:` → `main` (push and PR)
- `environment:` → `production` (with required reviewers for approval gate)
- `--config-env` → `prod`

---

## Git Branching Strategy

```
feature/*  ──► PR to dev  ──► merge ──► auto-deploy to Dev
dev        ──► PR to qa   ──► merge ──► auto-deploy to QA
qa         ──► PR to main ──► merge ──► deploy to Prod (approval required)
```

---

## Quick Reference — File Inventory

| File | Purpose |
|---|---|
| `template.yaml` | SAM/CloudFormation template — all AWS resources |
| `samconfig.toml` | Per-environment parameters (bucket names, emails, ARNs) |
| `lambda/lambda_function.py` | Malware router Lambda code (reads env vars) |
| `.github/workflows/dev-deploy.yml` | GitHub Actions workflow for Dev |
| `.gitignore` | Excludes SAM build artifacts |
| `docs/Deployment_Guide.md` | Manual deployment guide (console click-by-click) |
| `docs/Pipeline_Guide.md` | This file — CI/CD pipeline setup |

---

## Troubleshooting Pipeline Issues

| Issue | Check |
|---|---|
| Workflow not triggering | Verify the workflow file is on the target branch (e.g., `dev-deploy.yml` must exist on `dev`) |
| OIDC auth failure | Verify the trust policy `sub` condition matches your repo name exactly |
| `AccessDenied` during deploy | Verify the deploy role has all required permissions (CloudFormation, IAM, S3, Lambda, SNS, EventBridge, Transfer) |
| Stack creation fails | Check CloudFormation Events tab for the specific resource that failed. Common: IAM role name conflicts if stack was partially created before |
| SNS emails not arriving | Subscription must be confirmed. Check **SNS Console** → subscription status |
| GuardDuty not scanning | GuardDuty Malware Protection for S3 must be enabled manually per bucket |
