#!/usr/bin/env bash
# First setup of this site on the US Code site's box (docs/plans/
# 2026-09-08-deployment-plan.md, section 4). Run once, over SSM, as root:
#
#   SITE_ADDRESS=statutes.linkedlegislation.org \
#   ECR_REGISTRY=739065237548.dkr.ecr.us-east-1.amazonaws.com \
#   BACKUP_BUCKET=statutes-linkedlegislation \
#   GOVINFO_API_KEY=… \
#     sudo -E bash bootstrap-box.sh
#
# Mounts the data volume deploy/provision.sh attached at /var/lib/statutes,
# clones the repository beside ~/uscode-redesign, writes .env once and
# installs the cron file. Idempotent: re-running it formats nothing that has
# a filesystem, re-clones nothing, and keeps an existing .env. Docker, the
# compose plugin and git are usually on the box already; each is installed
# only when absent. No secret is echoed.
set -euo pipefail

SITE_HOST="${SITE_ADDRESS:?set SITE_ADDRESS to the public hostname}"
SITE_HOST="${SITE_HOST#*://}"; SITE_HOST="${SITE_HOST%%/*}"; SITE_HOST="${SITE_HOST%%:*}"
ECR_REGISTRY="${ECR_REGISTRY:?set ECR_REGISTRY}"
BACKUP_BUCKET="${BACKUP_BUCKET:-statutes-linkedlegislation}"
GOVINFO_API_KEY="${GOVINFO_API_KEY:-}"
DATA_ROOT="${DATA_ROOT:-/var/lib/statutes}"
USCODE_ORIGIN="${USCODE_ORIGIN:-https://uscode.linkedlegislation.org}"
REPO_URL="${REPO_URL:-https://github.com/aih/statutes-at-large.git}"
REPO_DIR="${REPO_DIR:-/home/ec2-user/statutes-at-large}"

echo "==> packages"
missing=()
command -v docker >/dev/null || missing+=(docker)
command -v git >/dev/null || missing+=(git)
if [ "${#missing[@]}" -gt 0 ]; then
    echo "    installing ${missing[*]}"
    dnf install -y "${missing[@]}" >/dev/null
else
    echo "    docker and git already installed"
fi
systemctl enable --now docker >/dev/null
usermod -aG docker ec2-user

# AL2023's docker package carries no compose plugin.
COMPOSE_PLUGIN=/usr/libexec/docker/cli-plugins/docker-compose
if [ -x "$COMPOSE_PLUGIN" ]; then
    echo "    compose plugin already installed ($("$COMPOSE_PLUGIN" version --short 2>/dev/null))"
else
    echo "    installing the docker compose plugin"
    COMPOSE_TAG="${COMPOSE_TAG:-$(curl -fsSLI -o /dev/null -w '%{url_effective}' \
        https://github.com/docker/compose/releases/latest | sed 's#.*/tag/##')}"
    COMPOSE_URL="https://github.com/docker/compose/releases/download/${COMPOSE_TAG}/docker-compose-linux-$(uname -m)"
    curl -fsSL "$COMPOSE_URL" -o /tmp/docker-compose
    if curl -fsSL "${COMPOSE_URL}.sha256" -o /tmp/docker-compose.sha256; then
        expected="$(awk '{print $1}' /tmp/docker-compose.sha256)"
        actual="$(sha256sum /tmp/docker-compose | awk '{print $1}')"
        if [ "$expected" != "$actual" ]; then
            echo "compose checksum mismatch: expected $expected, got $actual" >&2
            exit 1
        fi
        echo "    checksum verified"
    else
        echo "    no published checksum for ${COMPOSE_TAG}; installing unverified" >&2
    fi
    mkdir -p "$(dirname "$COMPOSE_PLUGIN")"
    install -m 0755 /tmp/docker-compose "$COMPOSE_PLUGIN"
    rm -f /tmp/docker-compose /tmp/docker-compose.sha256
    echo "    installed compose ${COMPOSE_TAG}"
fi

echo "==> data volume at $DATA_ROOT"
mkdir -p "$DATA_ROOT"
if mountpoint -q "$DATA_ROOT"; then
    echo "    already mounted ($(findmnt -no SOURCE "$DATA_ROOT"))"
else
    # By elimination: the disks that are neither the root disk nor mounted
    # anywhere (the US Code site's volume is mounted at /var/lib/uscode).
    root_disk="$(lsblk -no PKNAME "$(findmnt -no SOURCE /)" 2>/dev/null || true)"
    candidates=()
    while read -r name; do
        [ -n "$name" ] || continue
        [ "$name" = "$root_disk" ] && continue
        if lsblk -no MOUNTPOINTS "/dev/$name" | grep -q .; then
            continue
        fi
        candidates+=("/dev/$name")
    done < <(lsblk -dn -o NAME,TYPE | awk '$2 == "disk" {print $1}')
    if [ "${#candidates[@]}" -eq 0 ]; then
        echo "no unmounted disk found — was the volume attached (deploy/provision.sh)?" >&2
        lsblk >&2
        exit 1
    fi
    if [ "${#candidates[@]}" -gt 1 ]; then
        echo "more than one unmounted disk: ${candidates[*]} — mount the right one by hand" >&2
        lsblk >&2
        exit 1
    fi
    DATA_DEV="${candidates[0]}"
    if ! blkid "$DATA_DEV" >/dev/null 2>&1; then
        echo "    formatting $DATA_DEV (no filesystem on it)"
        mkfs.ext4 -q "$DATA_DEV"
    else
        echo "    $DATA_DEV already has a filesystem — leaving it alone"
    fi
    # By UUID: NVMe device names are not stable across reboots, and this box
    # has two data volumes.
    uuid="$(blkid -s UUID -o value "$DATA_DEV")"
    if ! grep -q "UUID=$uuid" /etc/fstab; then
        echo "UUID=$uuid $DATA_ROOT ext4 defaults,nofail 0 2" >> /etc/fstab
    fi
    mount -a
    mountpoint -q "$DATA_ROOT" || { echo "$DATA_ROOT did not mount" >&2; exit 1; }
    echo "    mounted $DATA_DEV (UUID=$uuid)"
fi

mkdir -p "$DATA_ROOT"/{pgdata,data,caddy,edge-caddy,logs}
chown -R ec2-user:ec2-user "$DATA_ROOT"

echo "==> repository at $REPO_DIR"
if [ ! -d "$REPO_DIR/.git" ]; then
    sudo -u ec2-user git clone --quiet "$REPO_URL" "$REPO_DIR"
    echo "    cloned"
else
    echo "    already cloned"
fi

echo "==> .env"
ENV_FILE="$REPO_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    echo "    .env exists — keeping it"
else
    POSTGRES_PASSWORD="$(openssl rand -base64 32 | tr -d '\n')"
    cat > "$ENV_FILE" <<ENVEOF
SITE_ADDRESS=http://${SITE_HOST}:8000
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
DATA_ROOT=${DATA_ROOT}
ECR_REGISTRY=${ECR_REGISTRY}
BACKUP_BUCKET=${BACKUP_BUCKET}
GOVINFO_API_KEY=${GOVINFO_API_KEY}
SITE_ORIGIN=https://${SITE_HOST}
USCODE_ORIGIN=${USCODE_ORIGIN}
ENVEOF
    chown ec2-user:ec2-user "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "    written (the password was generated here and is not echoed)"
fi

echo "==> schedule"
export DATA_ROOT REPO_DIR
bash "$REPO_DIR/deploy/install-crons.sh"

echo
echo "Bootstrap complete. Next, in the order of the plan's section 4:"
echo "  1. the US Code site's edge branch deployed (its proxy joins the edge network)"
echo "  2. bash deploy/edge/up.sh   (the network and the edge Caddy on 80 and 443)"
echo "  3. bash deploy/deploy-on-box.sh <sha>"
