# AWS SFTP Malware Router - Unified Deployment and Pipeline Guide

This is the single source of truth for both:
- Manual AWS console deployment
- CI/CD deployment with SAM + GitHub Actions

Use this runbook to avoid duplicate or conflicting setup steps.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Deployment Modes](#deployment-modes)
3. [CI/CD Bootstrap (GitHub Actions + SAM)](#cicd-bootstrap-github-actions--sam)
4. [Prerequisites (All Modes)](#prerequisites-all-modes)
5. [Resource Provisioning (Manual Mode)](#resource-provisioning-manual-mode)
6. [Post-Deploy Manual Tasks (All Modes)](#post-deploy-manual-tasks-all-modes)
7. [End-to-End Testing Checklist](#end-to-end-testing-checklist)
8. [Environment Promotion (QA / Prod)](#environment-promotion-qa--prod)
9. [Monitoring and Operations](#monitoring-and-operations)
10. [Troubleshooting Matrix](#troubleshooting-matrix)
11. [Source Files Reference](#source-files-reference)
12. [Resource Summary (Dev)](#resource-summary-dev)
13. [Appendix A: SSH Key Generation Quick Commands](#appendix-a-ssh-key-generation-quick-commands)
14. [Appendix B: Client Connection Profiles](#appendix-b-client-connection-profiles)

---

<a id="architecture-overview"></a>
## 1) Architecture Overview

```
SFTP Client -> AWS Transfer Family -> S3 Inbound Bucket
                                        |
                            GuardDuty Malware Scan
                                        |
                                  EventBridge Rule
                                        |
                                  Lambda Function
                                   /             \
                              CLEAN              INFECTED
                                |                    |
                         Production Bucket   Quarantine Bucket
                                              + SNS Email Alert
```

Flow summary:
1. SFTP user uploads a `.pdf` file to inbound S3 via Transfer Family.
2. GuardDuty Malware Protection scans the object.
3. EventBridge rule captures scan results and invokes Lambda.
4. Lambda routes objects:
   - Clean -> production bucket
   - Infected -> quarantine bucket and sends SNS alert

---

<a id="deployment-modes"></a>
## 2) Deployment Modes

Choose one mode:
1. Manual Mode (Console-first): follow Sections 4 to 9.
2. CI/CD Mode (recommended): follow Section 3 first, then Sections 8 to 11.

Notes:
- GuardDuty Malware Protection for S3 is always a manual one-time setup per account/region.
- Adding Transfer Family users and importing SSH public keys is always manual.

---

<a id="cicd-bootstrap-github-actions--sam"></a>
## 3) CI/CD Bootstrap (GitHub Actions + SAM)

### 3.1 Create AWS OIDC Identity Provider

1. IAM Console -> Identity providers -> Add provider.
2. Configure:
   - Provider type: OpenID Connect
   - Provider URL: `https://token.actions.githubusercontent.com`
   - Audience: `sts.amazonaws.com`
3. Save.

### 3.2 Create GitHub Deploy Role

1. IAM Console -> Roles -> Create role.
2. Trusted entity type: Web identity.
3. Identity provider: `token.actions.githubusercontent.com`
4. Audience: `sts.amazonaws.com`
5. Attach permissions (minimum required preferred).

Common initial policy set:
- `AWSCloudFormationFullAccess`
- `IAMFullAccess`
- `AmazonS3FullAccess`
- `AWSLambda_FullAccess`
- `AmazonSNSFullAccess`
- `AmazonEventBridgeFullAccess`
- `AWSTransferFullAccess`

Role name:
- `github-actions-sftp-deploy-role`

### 3.3 Restrict Trust Policy to Repository

Update trust policy with your AWS account and GitHub repo:

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

### 3.4 Configure GitHub Repository

1. Add repository secret:
   - Name: `AWS_DEPLOY_ROLE_ARN`
   - Value: IAM role ARN from Section 3.2
2. Create environments:
   - `dev` (no approval required)
   - `qa` (optional reviewers)
   - `production` (required reviewers)
3. Ensure branch strategy exists:
   - `feature/*` -> `dev`
   - `dev` -> `qa`
   - `qa` -> `main`

### 3.5 Pipeline Workflows

Expected workflow files:
- `.github/workflows/dev-deploy.yml`
- `.github/workflows/qa-deploy.yml` (future)
- `.github/workflows/prod-deploy.yml` (future)

What SAM deploys automatically per environment:
- S3 buckets (inbound + infected quarantine)
- S3 bucket policies (production + infected)
- SNS topic and email subscription resource
- IAM roles (Lambda, SFTP user, EventBridge invoke)
- Lambda function and environment configuration
- EventBridge rule (GuardDuty scan result to Lambda)
- AWS Transfer Family SFTP server

Behavior:
- PR to target branch: validate only
- Push/merge to target branch: validate + deploy

### 3.6 First Pipeline Validation

1. Merge feature branch to `dev`.
2. Check GitHub Actions run succeeds.
3. Verify CloudFormation stack status is `CREATE_COMPLETE`.
4. Verify stack outputs include endpoint, bucket names, and role ARNs.

Example branch bootstrap commands:
```bash
git checkout main
git pull origin main
git checkout -b dev
git push -u origin dev
```

---

<a id="prerequisites-all-modes"></a>
## 4) Prerequisites (All Modes)

- AWS account with required IAM privileges
- AWS CLI configured for `us-east-1`
- Python 3.12 runtime for Lambda
- Client SSH public key for SFTP user
- Alert email addresses for SNS notifications

---

<a id="resource-provisioning-manual-mode"></a>
## 5) Resource Provisioning (Manual Mode)

Skip this section if resources are provisioned by SAM pipeline and stack deploy succeeds.

### 5.1 Create S3 Buckets

Create these in `us-east-1` with SSE-S3 and block all public access:
- `dev-sftp-inbound-quarantine` (landing bucket)
- `healthworks-lambda-manage-productionencounterbucke-yoqwb36evr2x` (clean files)
- `dev-sftp-infected-quarantine` (infected files)

Apply bucket policies from:
- `S3-bucket/sftp_production_bucket_policy.json`
- `S3-bucket/sftp_infected_quarantine_bucket policy.json`

### 5.2 Enable GuardDuty Malware Protection for S3

1. GuardDuty Console -> Malware Protection -> Malware Protection for S3.
2. Enable scanning for `dev-sftp-inbound-quarantine`.

### 5.3 IAM Roles and Policies

Create/attach from `iam-policies/`:

1. Lambda execution role:
   - Role: `dev-SFTP-Malware-Router-Role`
   - Policies:
     - `lambda_basic_execution_role.json`
     - `file_transfer_policy.json`

2. Transfer Family user role:
   - Role: `dev-SFTP-Transfer-Service-Role`
   - Policy:
     - `SFTP_S3_Inbound_Access_Policy.json`

3. EventBridge invoke Lambda role:
   - Role: `dev-EventBridge-Invoke-SFTP-Lambda-Role`
   - Trust policy:
     - `Amazon_EventBridge_Invoke_Lambda_trust_policy.json`
   - Permission policy:
     - `Amazon_EventBridge_Invoke_Lambda_role.json`

### 5.4 SNS Topic

1. Create topic: `dev-SFTP-Malware-Detected-Alert`.
2. Add email subscriptions.
3. Confirm each subscription from recipient inbox.

### 5.5 Lambda Function

1. Create function: `dev-SFTP-Malware-Router`.
2. Runtime: Python 3.12.
3. Execution role: `dev-SFTP-Malware-Router-Role`.
4. Deploy code from `lambda/lambda_function.py`.
5. Set timeout >= 30 seconds.
6. Validate constants/environment alignment:
   - `CLEAN_BUCKET`
   - `INFECTED_BUCKET`
   - `SNS_TOPIC_ARN`

### 5.6 EventBridge Rule

1. Create rule: `Dev-Trigger-SFTP-Malware-Router`.
2. Event pattern from `eventbridge/event_pattern.json`.
3. Target: Lambda `dev-SFTP-Malware-Router`.
4. Execution role: `dev-EventBridge-Invoke-SFTP-Lambda-Role`.

### 5.7 Transfer Family SFTP Server + User

1. Create Transfer Family server (SFTP, service-managed identity, S3 domain).
2. Add SFTP user with:
   - Role: `dev-SFTP-Transfer-Service-Role`
   - Home bucket: `dev-sftp-inbound-quarantine`
   - Prefix: `healthworks/<username>/uploads`
   - Restrict to home directory: enabled
   - SSH public key imported

---

<a id="post-deploy-manual-tasks-all-modes"></a>
## 6) Post-Deploy Manual Tasks (All Modes)

1. Confirm SNS email subscription.
2. Add/maintain Transfer Family users and SSH keys.
3. Share SFTP connection details with each client:
   - Host: Transfer server endpoint
   - Port: 22
   - Username: provisioned username
   - Authentication: matching SSH private key
   - Allowed files: `.pdf` / `.PDF`

---

<a id="end-to-end-testing-checklist"></a>
## 7) End-to-End Testing Checklist

1. Non-PDF upload test:
   - Expected: Access denied
2. Clean PDF flow:
   - File removed from inbound bucket
   - File appears in production bucket
   - Lambda logs contain success entry
3. Duplicate filename flow:
   - Subsequent files become `_1`, `_2`, ...
4. Malware flow (EICAR test string):
   - File moved to infected bucket
   - SNS malware alert email sent
   - Lambda logs contain quarantine entry

---

<a id="environment-promotion-qa--prod"></a>
## 8) Environment Promotion (QA / Prod)

### 8.1 samconfig.toml

Set per-environment values in `samconfig.toml`:
- `Environment`
- `CleanBucketName`
- `AlertEmail`
- `AuthorizedUserArns`

### 8.2 Workflow Cloning

Create from dev workflow pattern:
- `qa-deploy.yml` with branch `qa`, environment `qa`, config env `qa`
- `prod-deploy.yml` with branch `main`, environment `production`, config env `prod`

### 8.3 GuardDuty Per Environment

Enable Malware Protection for each inbound bucket in QA and Prod after deployment.

---

<a id="monitoring-and-operations"></a>
## 9) Monitoring and Operations

1. CloudWatch logs:
   - Log group: `/aws/lambda/dev-SFTP-Malware-Router`
   - Watch for `SUCCESS`, `QUARANTINED`, `CRITICAL ERROR`
2. Recommended alarms:
   - Metric filter on `CRITICAL ERROR`
   - Notify operations/SOC SNS topic
3. Recommended lifecycle policies:
   - Quarantine bucket expiry (for example 90 days)
   - Production archival tier transitions based on retention policy

---

<a id="troubleshooting-matrix"></a>
## 10) Troubleshooting Matrix

| Issue | What to check |
|---|---|
| `.pdf` upload denied | Verify Transfer role policy and expected S3 prefix path (`healthworks/*/`) |
| File remains in inbound bucket | GuardDuty S3 malware scan enabled and EventBridge rule enabled |
| Lambda not triggered | EventBridge pattern, target function, and invoke role permissions |
| Lambda S3/SNS errors | Lambda role permissions and bucket/topic identifiers |
| No malware alert emails | SNS subscription status is `Confirmed`; check spam/junk |
| Workflow not triggering | Workflow file exists on target branch and trigger branch names are correct |
| OIDC failure | Role trust policy `aud` and `sub` conditions match account/repository |
| Deploy AccessDenied | Deploy role lacks required CloudFormation/IAM/S3/Lambda/SNS/EventBridge/Transfer permissions |
| Duplicate naming not working | Lambda can read target key existence (`s3:GetObject`/head) |

---

<a id="source-files-reference"></a>
## 11) Source Files Reference

Core project files:
- `template.yaml`
- `samconfig.toml`
- `lambda/lambda_function.py`
- `eventbridge/event_pattern.json`
- `iam-policies/*.json`
- `S3-bucket/*.json`
- `.github/workflows/*.yml`

This document supersedes:
- `docs/Deployment_Guide.md`
- `docs/Pipeline_Guide.md`

---

<a id="resource-summary-dev"></a>
## 12) Resource Summary (Dev)

| Resource | Name / ARN |
|---|---|
| SFTP Server | `Dev-SFTP-Server` |
| Inbound S3 Bucket | `dev-sftp-inbound-quarantine` |
| Production S3 Bucket | `healthworks-lambda-manage-productionencounterbucke-yoqwb36evr2x` |
| Quarantine S3 Bucket | `dev-sftp-infected-quarantine` |
| Lambda Function | `dev-SFTP-Malware-Router` |
| Lambda Role | `dev-SFTP-Malware-Router-Role` |
| SFTP User Role | `dev-SFTP-Transfer-Service-Role` |
| EventBridge Rule | `Dev-Trigger-SFTP-Malware-Router` |
| EventBridge Role | `dev-EventBridge-Invoke-SFTP-Lambda-Role` |
| SNS Topic | `dev-SFTP-Malware-Detected-Alert` |
| AWS Account | `744640651507` |
| Region | `us-east-1` |

---

<a id="appendix-a-ssh-key-generation-quick-commands"></a>
## Appendix A: SSH Key Generation Quick Commands

Windows PowerShell:
```powershell
ssh-keygen -t rsa -b 4096 -f C:\Users\$env:USERNAME\.ssh\healthworks_sftp_key
Get-Content C:\Users\$env:USERNAME\.ssh\healthworks_sftp_key.pub
```

macOS/Linux:
```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/healthworks_sftp_key
cat ~/.ssh/healthworks_sftp_key.pub
```

Important:
- Share only the public key (`.pub`) with administrators.
- Never share private keys.

<a id="appendix-b-client-connection-profiles"></a>
## Appendix B: Client Connection Profiles

AWS Transfer Family accepts SSH key authentication only (no password authentication).

Using WinSCP:
1. Open WinSCP and create a new session.
2. Protocol: SFTP.
3. Host: your Transfer endpoint.
4. Port: `22`.
5. Username: provisioned SFTP username.
6. Advanced -> SSH -> Authentication -> select private key file (`.ppk`).

Using FileZilla:
1. Open FileZilla -> Settings -> SFTP -> Add key file.
2. Add private key file (OpenSSH or `.ppk`).
3. Connect with host `sftp://<transfer-endpoint>`, username, and port `22`.

Using command line:
```bash
sftp -i ~/.ssh/healthworks_sftp_key healthworks-user@<transfer-endpoint>
```
