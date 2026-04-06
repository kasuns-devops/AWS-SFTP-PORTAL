# AWS SFTP Malware Router

Healthworks AWS SFTP ingestion pipeline with malware scanning and file routing.

## Overview

This solution processes files uploaded through AWS Transfer Family (SFTP):
1. Files land in an inbound S3 bucket.
2. Amazon GuardDuty Malware Protection scans each object.
3. EventBridge triggers the Lambda router.
4. Lambda routes files:
    - Clean files to the production bucket
    - Infected files to the quarantine bucket and sends an SNS alert

Security model:
- Only `.pdf` and `.PDF` uploads are allowed for SFTP users via IAM policy.
- SSH key authentication only (no password auth).
- S3 buckets are private and encrypted (SSE-S3).

## Canonical Documentation

Use these docs as the source of truth:
- `docs/Deployment_and_Pipeline_Guide.md`
- `docs/Deployment_and_Pipeline_Guide.pdf`

The unified guide includes manual deployment, CI/CD bootstrap, environment promotion, testing, and troubleshooting.

## Repository Structure

| Path | Purpose |
|---|---|
| `template.yaml` | AWS SAM/CloudFormation template for infrastructure |
| `samconfig.toml` | Environment-specific SAM deployment configuration |
| `.github/workflows/dev-deploy.yml` | Dev branch validation and deployment pipeline |
| `lambda/lambda_function.py` | Malware routing Lambda function |
| `eventbridge/event_pattern.json` | EventBridge rule pattern for GuardDuty scan events |
| `iam-policies/` | IAM policies and trust policy definitions |
| `S3-bucket/` | S3 bucket policy documents |
| `docs/Deployment_and_Pipeline_Guide.md` | Unified deployment and pipeline runbook |
| `docs/Deployment_and_Pipeline_Guide.pdf` | PDF version of unified runbook |

## Quick Start

1. Open `docs/Deployment_and_Pipeline_Guide.md`.
2. Choose your path:
    - Manual deployment mode
    - CI/CD bootstrap mode (recommended)
3. Complete post-deploy tasks:
    - Confirm SNS subscription
    - Add Transfer Family users and SSH public keys
4. Run the end-to-end verification checklist from the guide.

## Environments

- Current workflow file: `.github/workflows/dev-deploy.yml`
- Planned extensions: QA and Production workflows using separate config environments (`qa`, `prod`)

## Notes

- GuardDuty Malware Protection for S3 must be enabled manually per inbound bucket (per account/region).
- If resource names or ARNs change, update `samconfig.toml`, IAM policy documents, and any environment-specific parameters consistently.