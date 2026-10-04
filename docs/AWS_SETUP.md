# AWS setup for scheduled runs (ADR-009)

Scheduled jobs read their secrets from AWS SSM Parameter Store. GitHub proves which repository and
branch a job runs on (OIDC), AWS hands it a one-hour role, and the role can only read Parakh's own
parameters. No AWS key is stored anywhere. Locally nothing changes: the `.env` is still used.

Everything below is done once, in the AWS console, in region **Asia Pacific (Mumbai) ap-south-1**.

## 1. Create the role (about 3 minutes)

1. Open **CloudFormation** and check the region shows Mumbai.
2. **Create stack** → **With new resources (standard)**.
3. **Choose an existing template** → **Upload a template file** → pick
   `infra/aws/parakh-github-oidc.yaml` from the repo → **Next**.
4. Stack name: `parakh-github-oidc`. Leave the parameters as they are → **Next**.
5. On the last page tick **I acknowledge that AWS CloudFormation might create IAM resources with
   custom names** → **Submit**.
6. Wait for `CREATE_COMPLETE`, open the **Outputs** tab and copy **RoleArn**.

## 2. Store the secrets (about 10 minutes)

Open **Systems Manager** → **Parameter Store** (region Mumbai). For each row: **Create parameter**,
name exactly as shown, tier **Standard**, type **SecureString**, KMS key source **My current
account** with the default `alias/aws/ssm`, and paste the value from your `.env`.

| Name | Needed for |
|---|---|
| `/parakh/prod/TELEGRAM_BOT_TOKEN` | every alert and the bot |
| `/parakh/prod/TELEGRAM_CHAT_ID` | every alert and the bot |
| `/parakh/prod/SUPABASE_URL` | runs, snapshots, audit |
| `/parakh/prod/SUPABASE_SERVICE_KEY` | runs, snapshots, audit |
| `/parakh/prod/ANTHROPIC_API_KEY` | Monthly Reviewer and Event Triage |
| `/parakh/prod/SMTP_USER`, `/parakh/prod/SMTP_PASSWORD`, `/parakh/prod/MAIL_TO` | optional: monthly email, and the fallback when Telegram fails |
| `/parakh/prod/LANGFUSE_PUBLIC_KEY`, `/parakh/prod/LANGFUSE_SECRET_KEY` | optional: tracing |
| `/parakh/prod/NTFY_TOPIC` | optional: ntfy |

Not stored here: `CAS_PASSWORD` and `PARAKH_ACCOUNT_KEY`. The CAS is parsed only on your PC (P6).

The parameter name's last part must equal the `.env` variable name. A job loads every parameter
under `/parakh/prod` into its environment; values are never logged.

## 3. Tell GitHub which role to use (about 2 minutes)

In the repository: **Settings** → **Secrets and variables** → **Actions** → **Variables** tab →
**New repository variable**, twice:

| Name | Value |
|---|---|
| `AWS_ROLE_ARN` | the RoleArn from step 1 |
| `AWS_REGION` | `ap-south-1` |

These are variables, not secrets: a role ARN is not sensitive, and it is useless outside this
repository's `main` branch.

## 4. Check

Run the **heartbeat** workflow by hand (**Actions** → **heartbeat** → **Run workflow**). The step
"secrets from AWS SSM (OIDC)" must be green and a heartbeat message must reach Telegram.

| Symptom | Cause |
|---|---|
| `Not authorized to perform sts:AssumeRoleWithWebIdentity` | the workflow ran on a branch other than `main`, or the repository name in the stack parameters is wrong |
| `AccessDeniedException ... ssm:GetParametersByPath` | the parameters are not under `/parakh/prod`, or not in Mumbai |
| The job runs but sends nothing | a parameter name is misspelt; compare with the table above |

## Later

- **Rotating a secret:** edit the parameter's value. The next job picks it up.
- **Staging:** a second stack with `ParameterPath` `parakh/staging` and a different role name, and
  `PARAKH_SSM_PATH=/parakh/staging` in that workflow (plan 14 §3).
- **Free plan:** the AWS account is on the free plan, which ends after its period or when the
  credits run out. Upgrade to the paid plan before then; standard parameters cost nothing.
