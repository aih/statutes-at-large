# shellcheck shell=bash
# Shared by the scripts in deploy/. Source it from the repository root:
#
#   cd "$(dirname "$0")/.."
#   . deploy/lib.sh
#
# Reads .env (the contract in docker-compose.prod.yml) without exporting it.

# env_value KEY [DEFAULT]: the value of KEY in .env, or DEFAULT.
env_value() {
    local value
    value="$(grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
    printf '%s' "${value:-${2:-}}"
}

# site_host: the hostname in SITE_ADDRESS, without scheme or port.
# `http://statutes.linkedlegislation.org:8000` -> `statutes.linkedlegislation.org`.
site_host() {
    local address
    address="$(env_value SITE_ADDRESS)"
    address="${address#*://}"
    address="${address%%/*}"
    printf '%s' "${address%%:*}"
}

# The instance id from IMDSv2, empty off EC2.
imds_instance_id() {
    local token
    token="$(curl -sX PUT --max-time 2 http://169.254.169.254/latest/api/token \
        -H "X-aws-ec2-metadata-token-ttl-seconds: 60" 2>/dev/null || true)"
    [ -n "$token" ] || return 0
    curl -s --max-time 2 -H "X-aws-ec2-metadata-token: $token" \
        http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null || true
}
