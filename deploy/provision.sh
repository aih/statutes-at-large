#!/usr/bin/env bash
# The AWS resources this site adds to the US Code site's box (docs/plans/
# 2026-09-08-deployment-plan.md, section 3). Run with the ordinary deploy
# identity after deploy/admin-grant.sh:
#
#   bash deploy/provision.sh
#
# Creates, or reuses by name or tag: the data volume (DATA_VOLUME_GB, default
# 40, gp3, tagged Name=statutes-data) in the availability zone of the instance
# tagged Name=uscode-site, attached to it as the next free /dev/xvd* device;
# the bucket statutes-linkedlegislation (private, versioning off, public
# access blocked, `db/` objects expired after 60 days); the ECR repositories
# statutes-api and statutes-frontend, each keeping its last ten tagged images.
#
# A volume created here is never deleted when the instance terminates:
# DeleteOnTermination applies only to volumes created by RunInstances, and this
# one is attached afterwards. The instance, security group, Elastic IP and
# instance role are the US Code site's and are not touched.
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
INSTANCE_NAME="uscode-site"
VOLUME_NAME="statutes-data"
DATA_VOLUME_GB="${DATA_VOLUME_GB:-40}"
BUCKET="${BACKUP_BUCKET:-statutes-linkedlegislation}"
ECR_REPOS=(statutes-api statutes-frontend)

echo "==> instance tagged Name=$INSTANCE_NAME"
read -r INSTANCE_ID AZ < <(aws ec2 describe-instances --region "$REGION" \
    --filters "Name=tag:Name,Values=$INSTANCE_NAME" \
              "Name=instance-state-name,Values=pending,running,stopping,stopped" \
    --query 'Reservations[0].Instances[0].[InstanceId,Placement.AvailabilityZone]' \
    --output text)
if [ -z "${INSTANCE_ID:-}" ] || [ "$INSTANCE_ID" = "None" ]; then
    echo "no instance tagged Name=$INSTANCE_NAME in $REGION" >&2
    exit 1
fi
echo "    $INSTANCE_ID in $AZ"

echo "==> volume tagged Name=$VOLUME_NAME"
VOLUME_ID="$(aws ec2 describe-volumes --region "$REGION" \
    --filters "Name=tag:Name,Values=$VOLUME_NAME" \
              "Name=status,Values=creating,available,in-use" \
    --query 'Volumes[0].VolumeId' --output text 2>/dev/null || echo None)"
if [ "$VOLUME_ID" = "None" ] || [ -z "$VOLUME_ID" ]; then
    VOLUME_ID="$(aws ec2 create-volume --region "$REGION" \
        --availability-zone "$AZ" --size "$DATA_VOLUME_GB" --volume-type gp3 \
        --tag-specifications "ResourceType=volume,Tags=[{Key=Name,Value=$VOLUME_NAME}]" \
        --query VolumeId --output text)"
    echo "    created $VOLUME_ID (${DATA_VOLUME_GB} GB gp3) — waiting for it"
    aws ec2 wait volume-available --region "$REGION" --volume-ids "$VOLUME_ID"
else
    echo "    reusing $VOLUME_ID"
fi

ATTACHED_TO="$(aws ec2 describe-volumes --region "$REGION" --volume-ids "$VOLUME_ID" \
    --query 'Volumes[0].Attachments[0].InstanceId' --output text)"
if [ "$ATTACHED_TO" = "$INSTANCE_ID" ]; then
    echo "    already attached to $INSTANCE_ID"
elif [ "$ATTACHED_TO" != "None" ] && [ -n "$ATTACHED_TO" ]; then
    echo "volume $VOLUME_ID is attached to $ATTACHED_TO, not $INSTANCE_ID" >&2
    exit 1
else
    # The next free /dev/xvd* device after the ones the instance already maps
    # (/dev/xvda root, /dev/xvdb the US Code site's data volume).
    used="$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
        --query 'Reservations[0].Instances[0].BlockDeviceMappings[].DeviceName' --output text)"
    DEVICE=""
    for letter in c d e f g h i j k l m n o p; do
        candidate="/dev/xvd$letter"
        case " $used " in *" $candidate "*) continue ;; esac
        DEVICE="$candidate"
        break
    done
    if [ -z "$DEVICE" ]; then
        echo "no free /dev/xvd* device on $INSTANCE_ID (mapped: $used)" >&2
        exit 1
    fi
    aws ec2 attach-volume --region "$REGION" --volume-id "$VOLUME_ID" \
        --instance-id "$INSTANCE_ID" --device "$DEVICE" >/dev/null
    aws ec2 wait volume-in-use --region "$REGION" --volume-ids "$VOLUME_ID"
    echo "    attached as $DEVICE"
fi

echo "==> bucket $BUCKET"
if aws s3api head-bucket --bucket "$BUCKET" --region "$REGION" >/dev/null 2>&1; then
    echo "    reusing $BUCKET"
else
    # us-east-1 takes no LocationConstraint; every other region requires one.
    if [ "$REGION" = "us-east-1" ]; then
        aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" >/dev/null
    else
        aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
            --create-bucket-configuration "LocationConstraint=$REGION" >/dev/null
    fi
    echo "    created $BUCKET (versioning off)"
fi
aws s3api put-public-access-block --bucket "$BUCKET" --region "$REGION" \
    --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
aws s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" --region "$REGION" \
    --lifecycle-configuration '{
      "Rules": [
        {
          "ID": "expire-db-dumps",
          "Status": "Enabled",
          "Filter": {"Prefix": "db/"},
          "Expiration": {"Days": 60},
          "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 2}
        }
      ]
    }'
echo "    public access blocked; db/ objects expire after 60 days"

echo "==> ECR repositories"
for repo in "${ECR_REPOS[@]}"; do
    if aws ecr describe-repositories --region "$REGION" --repository-names "$repo" >/dev/null 2>&1; then
        echo "    reusing $repo"
    else
        aws ecr create-repository --region "$REGION" --repository-name "$repo" \
            --image-tag-mutability MUTABLE >/dev/null
        echo "    created $repo"
    fi
    # An upsert: the last ten tagged images stay, untagged layers go after a day.
    aws ecr put-lifecycle-policy --region "$REGION" --repository-name "$repo" \
        --lifecycle-policy-text '{
          "rules": [
            {
              "rulePriority": 1,
              "description": "expire untagged images after a day",
              "selection": {"tagStatus": "untagged", "countType": "sinceImagePushed", "countUnit": "days", "countNumber": 1},
              "action": {"type": "expire"}
            },
            {
              "rulePriority": 2,
              "description": "keep the last ten tagged images",
              "selection": {"tagStatus": "tagged", "tagPatternList": ["*"], "countType": "imageCountMoreThan", "countNumber": 10},
              "action": {"type": "expire"}
            }
          ]
        }' >/dev/null
done

echo
echo "volume:   $VOLUME_ID on $INSTANCE_ID"
echo "bucket:   s3://$BUCKET"
echo "registry: ${ECR_REPOS[*]}"
echo
echo "Next: on the box (aws ssm start-session --target $INSTANCE_ID),"
echo "  SITE_ADDRESS=statutes.linkedlegislation.org ECR_REGISTRY=… BACKUP_BUCKET=$BUCKET \\"
echo "  GOVINFO_API_KEY=… sudo -E bash deploy/bootstrap-box.sh"
