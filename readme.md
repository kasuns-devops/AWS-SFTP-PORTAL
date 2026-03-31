# AWS SFTP Malware Router (Development)

Automated DevSecOps pipeline for the Healthworks SFTP landing zone, featuring automated malware scanning and duplicate file handling.

## 🛠️ System Constraints & Security
* **File Validation:** Only `.pdf` and `.PDF` files are permitted. [cite_start]This is enforced at the IAM level for the SFTP user[cite: 7, 123].
* **Authentication:** Strict SSH Key-based authentication. [cite_start]No passwords.
* **Identity:** Managed via AWS Transfer Family Service-Managed users.
* **Encryption:** All buckets use **SSE-S3** (Amazon S3 Managed Keys).

---

## 📂 Repository Structure

| File Path | Description |
| :--- | :--- |
| `lambda/sftp_malware_router.py` | [cite_start]Python 3.12 script with collision-avoidance logic[cite: 80, 81]. |
| `eventbridge/event_pattern.json` | [cite_start]JSON pattern to capture GuardDuty scan results[cite: 70]. |
| `iam/s3_file_transfer_policy.json` | [cite_start]Permissions for the Lambda to route files and send alerts[cite: 28, 30]. |
| `iam/SFTP-Transfer-Service-Role.json` | [cite_start]**(Updated)** User policy enforcing PDF-only uploads and path access[cite: 7, 25]. |
| `iam/s3_inbound_bucket_policy.json` | [cite_start]Bucket-level policy enforcing SSL/TLS encrypted transport[cite: 8, 10]. |
| `iam/eventbridge_invoke_role.json` | Role allowing EventBridge to trigger the Lambda function. |

---

## ⚙️ Service Configurations

### 1. AWS Transfer Family (SFTP)
* **Server:** Dev-SFTP-Server.
* **User Authentication:** 1. Import the client's **Public SSH Key** into the Transfer Family Console.
    2. [cite_start]Assign the **SFTP-Transfer-Service-Role** to the user to restrict them to their `/healthworks/` directory and `.pdf` files.

### 2. SNS Alerting
* [cite_start]**Topic:** `dev-SFTP-Malware-Detected-Alert`[cite: 94].
* **Subscription:** Healthcare IT/Security team email addresses.
* [cite_start]**Function:** Notifies the team immediately when `THREATS_FOUND` is reported by GuardDuty[cite: 137, 150].

---

## 🚀 Deployment & Configuration

### ⚠️ Manual Variable Update
[cite_start]Ensure the following variables in `lambda/sftp_malware_router.py` match your environment before deployment:
* [cite_start]`CLEAN_BUCKET`: `healthworks-lambda-manage-productionencounterbucke-yoqwb36evr2x`[cite: 91].
* [cite_start]`INFECTED_BUCKET`: `dev-sftp-infected-quarantine`[cite: 93].
* [cite_start]`SNS_TOPIC_ARN`: `arn:aws:sns:us-east-1:744640651507:dev-SFTP-Malware-Detected-Alert`[cite: 94].

### 🧪 Verification Steps
1.  **Extension Test:** Attempt to upload `image.png`. [cite_start]The SFTP client should return an **Access Denied** error.
2.  **Collision Test:** Upload `medical_report.pdf` twice. [cite_start]Verify the second file is saved as `medical_report_1.pdf`[cite: 107, 160].
3.  **Malware Test:** Upload an EICAR test string as a `.pdf`. [cite_start]Verify it is moved to the infected bucket and an SNS alert is sent[cite: 161].