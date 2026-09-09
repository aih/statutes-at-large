#!/usr/bin/env bash
# One-time IAM setup, by an identity that may create IAM resources:
#
#   AWS_PROFILE=<admin> bash deploy/admin-grant.sh
#
# admin-grant-bootstrap-policy.json is exactly the IAM actions called here,
# scoped to statutes-* names and the uscode-site role. Attach it, run this,
# detach it; nothing in the deploy path needs IAM write.
#
# What it creates, and nothing more:
#
#   - the inline policy `statutes-backups` on the existing instance role
#     `uscode-site`: read, write and list on the backup bucket
#   - the OIDC role `statutes-github-deploy`, trusted by the existing GitHub
#     provider for repo:aih/statutes-at-large, with ECR push on the two
#     statutes repositories, SSM SendCommand on the instance tagged
#     Name=uscode-site, GetCommandInvocation and DescribeInstances
#
# The OIDC provider and the instance role are the US Code site's
# (its deploy/admin-grant.sh); this script stops when either is absent.
# Idempotent: existence checks before each create; put-role-policy upserts.
set -euo pipefail

ACCOUNT_ID="739065237548"
REGION="us-east-1"
GITHUB_REPO="aih/statutes-at-large"
SITE_ROLE="uscode-site"
SITE_INLINE_POLICY="statutes-backups"
GITHUB_ROLE="statutes-github-deploy"
BUCKET="${BACKUP_BUCKET:-statutes-linkedlegislation}"
OIDC_PROVIDER_URL="token.actions.githubusercontent.com"
OIDC_PROVIDER_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/${OIDC_PROVIDER_URL}"

echo "=== statutes one-time IAM setup (account ${ACCOUNT_ID}, region ${REGION}) ==="
echo "Using AWS_PROFILE=${AWS_PROFILE:-<default>}"
echo

TMP_FILES=()
cleanup() {
    [ "${#TMP_FILES[@]}" -eq 0 ] || rm -f "${TMP_FILES[@]}"
}
trap cleanup EXIT

mktemp_tracked() {
    local f
    f="$(mktemp)"
    TMP_FILES+=("$f")
    echo "$f"
}

# 0 when the role exists, 1 when IAM says NoSuchEntity; any other failure
# (AccessDenied, an invalid token) is printed and stops the script, so a
# denied GetRole does not read as a missing role.
iam_role_exists() {
    local err
    if err="$(aws iam get-role --role-name "$1" 2>&1 >/dev/null)"; then
        return 0
    fi
    case "$err" in
        *NoSuchEntity*) return 1 ;;
        *)
            echo "aws iam get-role ${1} failed under $(aws sts get-caller-identity --query Arn --output text 2>/dev/null || echo '<unknown identity>'):" >&2
            echo "$err" >&2
            exit 1
            ;;
    esac
}

# ------------------------------------------- a. the instance role's grant ---

echo "--- (a) inline policy ${SITE_INLINE_POLICY} on role ${SITE_ROLE} ---"

if ! iam_role_exists "$SITE_ROLE"; then
    echo "role ${SITE_ROLE} does not exist; run the US Code site's deploy/admin-grant.sh first" >&2
    exit 1
fi

SITE_INLINE_DOC="$(mktemp_tracked)"
cat > "$SITE_INLINE_DOC" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "StatutesBackups",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::${BUCKET}",
        "arn:aws:s3:::${BUCKET}/*"
      ]
    }
  ]
}
EOF

aws iam put-role-policy --role-name "$SITE_ROLE" \
    --policy-name "$SITE_INLINE_POLICY" --policy-document "file://${SITE_INLINE_DOC}"
echo "put inline policy ${SITE_INLINE_POLICY} on ${SITE_ROLE}"
echo

# ------------------------------------------------- b. the GitHub OIDC role ---

echo "--- (b) role ${GITHUB_ROLE} ---"

if ! providers="$(aws iam list-open-id-connect-providers \
        --query "OpenIDConnectProviderList[?contains(Arn, '${OIDC_PROVIDER_URL}')]" \
        --output text)"; then
    echo "aws iam list-open-id-connect-providers failed (the error is above)" >&2
    exit 1
fi
if [ -z "$providers" ]; then
    echo "no OIDC provider for ${OIDC_PROVIDER_URL}; run the US Code site's deploy/admin-grant.sh first" >&2
    exit 1
fi
echo "OIDC provider for ${OIDC_PROVIDER_URL} exists"

# GitHub issues `sub` both as `repo:OWNER/REPO:…` and with numeric ids
# appended (`repo:OWNER@id/REPO@id:…`); both spellings are accepted. The
# StringEquals on `repository` is the exact scope.
GITHUB_TRUST_DOC="$(mktemp_tracked)"
cat > "$GITHUB_TRUST_DOC" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Federated": "${OIDC_PROVIDER_ARN}" },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:repository": "${GITHUB_REPO}"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": [
            "repo:${GITHUB_REPO%%/*}@*/${GITHUB_REPO##*/}@*:*",
            "repo:${GITHUB_REPO}:*"
          ]
        }
      }
    }
  ]
}
EOF

if iam_role_exists "$GITHUB_ROLE"; then
    echo "role ${GITHUB_ROLE} already exists, updating trust policy"
    aws iam update-assume-role-policy --role-name "$GITHUB_ROLE" \
        --policy-document "file://${GITHUB_TRUST_DOC}"
else
    aws iam create-role --role-name "$GITHUB_ROLE" \
        --assume-role-policy-document "file://${GITHUB_TRUST_DOC}" >/dev/null
    echo "created role ${GITHUB_ROLE}"
fi

GITHUB_PERMISSIONS_DOC="$(mktemp_tracked)"
cat > "$GITHUB_PERMISSIONS_DOC" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EcrAuth",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "EcrPush",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": [
        "arn:aws:ecr:${REGION}:${ACCOUNT_ID}:repository/statutes-api",
        "arn:aws:ecr:${REGION}:${ACCOUNT_ID}:repository/statutes-frontend"
      ]
    },
    {
      "Sid": "SsmSendCommandUscodeSite",
      "Effect": "Allow",
      "Action": "ssm:SendCommand",
      "Resource": "arn:aws:ec2:${REGION}:${ACCOUNT_ID}:instance/*",
      "Condition": {
        "StringEquals": { "ssm:resourceTag/Name": "uscode-site" }
      }
    },
    {
      "Sid": "SsmSendCommandDocument",
      "Effect": "Allow",
      "Action": "ssm:SendCommand",
      "Resource": "arn:aws:ssm:${REGION}::document/AWS-RunShellScript"
    },
    {
      "Sid": "SsmPollCommand",
      "Effect": "Allow",
      "Action": "ssm:GetCommandInvocation",
      "Resource": "*"
    },
    {
      "Sid": "Ec2Describe",
      "Effect": "Allow",
      "Action": "ec2:DescribeInstances",
      "Resource": "*"
    }
  ]
}
EOF

aws iam put-role-policy --role-name "$GITHUB_ROLE" \
    --policy-name "${GITHUB_ROLE}-policy" --policy-document "file://${GITHUB_PERMISSIONS_DOC}"
echo "put permissions policy on ${GITHUB_ROLE}"

GITHUB_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${GITHUB_ROLE}"
echo
echo "GitHub repository variable AWS_DEPLOY_ROLE_ARN:"
echo "  ${GITHUB_ROLE_ARN}"
echo "  gh variable set AWS_DEPLOY_ROLE_ARN --repo ${GITHUB_REPO} --body '${GITHUB_ROLE_ARN}'"
echo
echo "Next: bash deploy/provision.sh (the volume, the bucket, the ECR repositories)."
