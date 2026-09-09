#!/usr/bin/env bash
# CloudWatch alarms for this site, and the SNS topic that mails them.
#
#   ALERT_EMAIL=you@example.org bash deploy/alarms.sh <instance-id>
#
# Two alarms: statutes-site-down on Statutes/SiteUp (deploy/watchdog.sh's
# metric; missing data breaches, so a box too wedged to run cron alarms too)
# and statutes-disk-high on this site's data volume. The CPU, credit-balance,
# status-check and network alarms on the box are the US Code site's
# (its deploy/alarms.sh) and are not duplicated here.
#
# Idempotent: put-metric-alarm and create-topic upsert, and a repeat
# subscribe of an address already subscribed is a no-op.
set -euo pipefail

INSTANCE_ID="${1:?usage: ALERT_EMAIL=you@example.org alarms.sh <instance-id>}"
ALERT_EMAIL="${ALERT_EMAIL:?set ALERT_EMAIL to the address that should receive alarms}"
REGION="${AWS_REGION:-us-east-1}"
TOPIC_NAME="statutes-alerts"
DATA_ROOT="${DATA_ROOT:-/var/lib/statutes}"

echo "==> SNS topic $TOPIC_NAME"
TOPIC_ARN="$(aws sns create-topic --name "$TOPIC_NAME" --region "$REGION" \
    --query TopicArn --output text)"
echo "    $TOPIC_ARN"

echo "==> subscribing $ALERT_EMAIL"
aws sns subscribe --topic-arn "$TOPIC_ARN" --protocol email \
    --notification-endpoint "$ALERT_EMAIL" --region "$REGION" >/dev/null
echo "    AWS sends nothing until the subscription is confirmed from that mailbox"

DIM="Name=InstanceId,Value=${INSTANCE_ID}"

# Minimum over five one-minute periods: one failed probe during a deploy's
# proxy recreate does not page; five consecutive minutes down does.
echo "==> alarm statutes-site-down"
aws cloudwatch put-metric-alarm \
    --alarm-name statutes-site-down \
    --alarm-description "statutes.linkedlegislation.org is not answering — /health or /app/healthz has failed for five consecutive minutes, or the box has stopped reporting" \
    --namespace Statutes \
    --metric-name SiteUp \
    --statistic Minimum \
    --period 60 \
    --evaluation-periods 5 \
    --threshold 1 \
    --comparison-operator LessThanThreshold \
    --dimensions "$DIM" \
    --alarm-actions "$TOPIC_ARN" \
    --ok-actions "$TOPIC_ARN" \
    --treat-missing-data breaching \
    --region "$REGION"

# CWAgent/disk_used_percent exists only with the CloudWatch agent on the box
# (the US Code site's setup); without it this alarm sits in INSUFFICIENT_DATA.
echo "==> alarm statutes-disk-high"
aws cloudwatch put-metric-alarm \
    --alarm-name statutes-disk-high \
    --alarm-description "The statutes data volume (${DATA_ROOT}) is over 80% full" \
    --namespace CWAgent \
    --metric-name disk_used_percent \
    --statistic Average \
    --period 300 \
    --evaluation-periods 2 \
    --threshold 80 \
    --comparison-operator GreaterThanThreshold \
    --dimensions "$DIM" "Name=path,Value=${DATA_ROOT}" \
    --alarm-actions "$TOPIC_ARN" \
    --treat-missing-data notBreaching \
    --region "$REGION"

echo
echo "Confirm the subscription in $ALERT_EMAIL, then prove delivery:"
echo "  aws cloudwatch set-alarm-state --alarm-name statutes-site-down \\"
echo "    --state-value ALARM --state-reason 'testing delivery' --region $REGION"
