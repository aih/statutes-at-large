# Go-live prompt

The deployment is built and rehearsed (BUILDLOG 2026-09-08, ADR-0017,
ADR-0018). This session takes it to AWS and the box. The first section is
what the user does before and during the session; the prompt to paste
follows the rule.

## What the user does

Before starting the session:

1. **Push this repository's `main`** (four commits ahead of `origin/main`
   after the deployment session: `git log origin/main..main`). CI runs
   `make test`, `make test-web` and the config validation; `deploy.yml`
   skips while the repository variable `AWS_DEPLOY_ROLE_ARN` is unset.
   Or leave it and tell the session to push.
2. **The US Code site's `shared-edge` branch** is in
   `../uscode-redesign/.claude/worktrees/shared-edge` (three commits on
   `main`, not pushed). Push it and merge it into that repository's `main`
   when you are ready for the cut-over, not before: its deploy stops the
   proxy publishing 80 and 443, and the site is unreachable until the edge
   is up (its `docs/deploy.md` section 9). The session will tell you when
   in the sequence to merge it. `statutes-links` (also unmerged there) is
   independent and can wait.
3. **Choose the AWS identities** and have their profiles configured:
   - one that may create IAM resources, for `deploy/admin-grant.sh`, run
     once with `deploy/admin-grant-bootstrap-policy.json` attached to it
     and detached after;
   - the ordinary deploy identity (`linkedlegislation-deploy` on the US
     Code site) for `deploy/provision.sh`, `deploy/alarms.sh` and SSM. It
     needs, beyond the US Code site's `uscode-deploy-policy`:
     `ec2:CreateVolume`, `ec2:AttachVolume`, `ec2:CreateTags` (it has
     these), `s3:CreateBucket` and the bucket configuration calls on
     `statutes-linkedlegislation`, `ecr:CreateRepository` and
     `ecr:PutLifecyclePolicy` on `statutes-*`, `sns:*` on
     `statutes-alerts`, `cloudwatch:PutMetricAlarm`.
     `deploy/provision-policy.json` is that set, scoped to this site's
     names, ready to attach; the session will report an `AccessDenied`
     rather than work around it.
4. **DNS**: an A record `statutes.linkedlegislation.org` pointing at the
   box's Elastic IP, in the zone that holds `uscode.linkedlegislation.org`.
   The deploy identity has no Route 53 permissions; create the record by
   hand when the session asks, or grant `route53:ChangeResourceRecordSets`
   on that zone and tell the session the zone id.
5. **Secrets you type yourself**: `GOVINFO_API_KEY` goes into the box's
   `.env` through `deploy/bootstrap-box.sh`, which you run in your own SSM
   session (`aws ssm start-session --target <instance-id>`), so the key is
   never in a transcript. `ALERT_EMAIL` for the SNS topic; confirm the
   subscription from that mailbox when the mail arrives.
6. **The cut-over window**: the US Code site is down between its
   `shared-edge` deploy finishing and `deploy/edge/up.sh` completing, about
   a minute if you run them back to back. Pick the time.

During the session, at each section the agent stops and asks for a
go-ahead. Say "go" for the section, or say what to change. When the agent
prints a command for you to run (the IAM step, the bootstrap with the
key, an SSM session), run it and paste the output back, or type
`! <command>` in the prompt so the output lands in the conversation.

---

Take statutes.linkedlegislation.org live, following
docs/plans/2026-09-08-deployment-plan.md sections 3 to 8 with the shape
built on 2026-09-08 (ADR-0017 two sites one edge, ADR-0018 the weekly
update). Read first: CLAUDE.md, README.md ("Running it" and
"Deployment"), BUILDLOG.md (the last entry), docs/adr/0017 and 0018,
the plan in full, docker-compose.prod.yml, deploy/edge/README.md,
deploy/edge/up.sh, deploy/provision.sh, deploy/admin-grant.sh and its
bootstrap policy, deploy/bootstrap-box.sh, deploy/deploy-on-box.sh,
deploy/update-sources.sh, deploy/watchdog.sh, deploy/alarms.sh,
deploy/install-crons.sh, deploy/lib.sh, .github/workflows/deploy.yml and
update-sources.yml, Makefile (`load-prod`, `update-prod`). Then in
../uscode-redesign, read only: `git log main..shared-edge` and the diff of
that branch (`.claude/worktrees/shared-edge`), its docs/deploy.md
section 9 "Sharing the box", its ADR-0020 amendment. Prose follows
~/.claude/CLAUDE.md.

State on 2026-09-08: everything is built and rehearsed on this machine
without AWS (the edge on :8020 with both dev proxies joined; 419 pytest,
68 vitest, 26 Playwright over the edge; a forged `X-Forwarded-For`
replaced at the edge; one address drained while another answers). `main`
here holds it (check `git log origin/main..main`; push it if the user
has not). The US Code site's `shared-edge` branch is unpushed and
unmerged. Nothing exists on AWS for this site: no volume, bucket, ECR
repositories, IAM role, DNS record, GitHub variable. The box is the US
Code site's `t4g.large` tagged `Name=uscode-site` in us-east-1, account
739065237548, ECR registry 739065237548.dkr.ecr.us-east-1.amazonaws.com,
`/var/lib/uscode` mounted, Docker, compose and git installed, SSM access,
no SSH. Known: `statutes-disk-high` stays in INSUFFICIENT_DATA until the
box's CloudWatch agent config publishes `disk_used_percent` for
`/var/lib/statutes` (today it publishes `/var/lib/uscode`); `deploy-on-box.sh`
exits 1 after the stack is up when no container of compose project
`edge` is running, and its robots check needs the edge's certificate for
this hostname, which needs the DNS record resolving.

Rules for this session: one section at a time; stop and ask before
each; run only what the user said to run; report the output of every
command before the next section, trimmed but verbatim where it matters;
an `AccessDenied` or a failed check is reported, not worked around by
widening a policy or skipping a step; never print a secret (the
`GOVINFO_API_KEY`, `POSTGRES_PASSWORD`, an ECR token); the user runs the
IAM step and the box bootstrap themselves; the US Code site's `shared-edge`
merge is the user's action at the cut-over; nothing is deleted on AWS.
Every SSM command you send goes through `aws ssm send-command` with
`AWS-RunShellScript` targeting the instance id, polled with
`get-command-invocation`, its stdout and stderr shown. Before section 3,
a preflight with no side effects: `aws sts get-caller-identity` for each
profile the user names, `gh auth status`, the instance id and state
(`aws ec2 describe-instances --filters Name=tag:Name,Values=uscode-site`),
the Elastic IP, the availability zone, the block devices already attached,
`aws ssm describe-instance-information` for the instance, whether
`statutes-linkedlegislation` and the ECR repositories already exist,
whether the DNS name resolves, and the CI status of `main` on GitHub
(`gh run list --workflow ci.yml --limit 1`).

Sections, in order, each on a go-ahead:

3. AWS, once. (1) Print the exact command for the user:
   `AWS_PROFILE=<admin> bash deploy/admin-grant.sh` with the bootstrap
   policy attached; wait for the pasted output; verify with
   `aws iam get-role --role-name statutes-github-deploy` and
   `aws iam get-role-policy --role-name uscode-site --policy-name statutes-backups`
   under the deploy identity. (2) `bash deploy/provision.sh` under the
   deploy identity; verify the volume is attached (`describe-volumes` by
   tag `Name=statutes-data`, state `in-use`), the bucket's lifecycle and
   public-access block, both ECR repositories and their lifecycle policy.
   (3) DNS: ask the user to create the A record, or do it in Route 53 if
   they gave a zone id; verify with `dig +short statutes.linkedlegislation.org`
   against the Elastic IP. (4) Do not set `AWS_DEPLOY_ROLE_ARN` yet: a
   push would then deploy onto a box that is not bootstrapped.

4. The box. (1) Print the bootstrap command for the user to run in
   their own SSM session (the `bootstrap-box.sh` header has it; the
   script is fetched onto the box by `curl -fsSL https://raw.githubusercontent.com/aih/statutes-at-large/main/deploy/bootstrap-box.sh -o bootstrap-box.sh`
   after `main` is pushed); wait for the pasted output; verify over SSM:
   `findmnt /var/lib/statutes`, `ls /var/lib/statutes`, `/etc/fstab`'s
   new line, `ls /home/ec2-user/statutes-at-large`, `.env` exists with
   mode 600 (`stat -c %a`; never `cat` it), `/etc/cron.d/statutes`.
   (2) The cut-over, back to back: the user merges `shared-edge` into
   the US Code site's `main` and its deploy runs (watch
   `gh run watch` in that repository); the moment it finishes, over SSM
   as ec2-user: `cd ~/statutes-at-large && bash deploy/edge/up.sh`; then
   `curl -s --resolve uscode.linkedlegislation.org:443:127.0.0.1 https://uscode.linkedlegislation.org/robots.txt`
   and a reader page through the edge, and from this workstation
   `curl -sI https://uscode.linkedlegislation.org/` (a certificate from
   the edge's own store). If the US Code site does not answer through
   the edge within two minutes, the rollback is its docs/deploy.md
   section 9; do it only if the user says so. (3) Set the GitHub variable
   (`gh variable set AWS_DEPLOY_ROLE_ARN --repo aih/statutes-at-large --body <arn>`),
   then `gh workflow run deploy.yml --repo aih/statutes-at-large` and
   `gh run watch`; the box's `${DATA_ROOT}/logs/deploy.log` over SSM if
   it fails. Verify from this workstation: `/health`, `/app/healthz`,
   `/robots.txt`, `/api/v1/status` (empty collections, `stale` false is
   not expected yet: nothing is loaded, and `stale` reads only loaded
   collections), the certificate. (4) `ALERT_EMAIL=<address> bash deploy/alarms.sh <instance-id>`;
   ask the user to confirm the subscription; then the CloudWatch agent
   config over SSM so `disk_used_percent` covers `/var/lib/statutes`
   (read the agent's current config on the box first:
   `/opt/aws/amazon-cloudwatch-agent/etc/`; add the path, restart the
   agent; report the JSON diff).

5. The load, over SSM, detached, resumable:
   `cd ~/statutes-at-large && nohup make load-prod > /var/lib/statutes/logs/load-prod.log 2>&1 &`,
   then poll the log and `/api/v1/status` (the `STATUTE` volume count
   climbing toward 137) every few minutes with a background task, and
   report progress at each check without asking; expect about an hour
   for the volumes and about six hours for the COMPS walk (`comps poll
   --limit 400` repeated until it reports nothing due; the API allows
   1,000 calls an hour). When `/status` shows 137 `STATUTE` volumes,
   seven `PLAW` congresses, the citation index and the classification
   mirror, take the first dump (the plan's section 5 command), verify the
   object in the bucket, and run the plan's smoke test from this
   workstation plus `make test-e2e` with `BASE_URL=https://statutes.linkedlegislation.org`.
   Then `make update-prod-check` over SSM and show its log.

6. After the load: `STATUTES_ORIGIN=https://statutes.linkedlegislation.org`
   on the US Code site's `frontend` once `statutes-links` is merged
   there (the user's call; it is a `.env` line and a `docker compose up -d
   frontend` on the box). A BUILDLOG entry here for the session with the
   outputs that matter (instance id, volume id, the dump's key, the
   smoke test results, `/status` counts, the alarms), and
   `docs/plans/2026-09-08-deployment-plan.md` amended where the built
   shape differs from its words (already: the trusted subnet, ADR-0017).
   Commit and push. Remove the merged worktree
   `.claude/worktrees/agent-a74dc1144172938f5` (`git worktree remove`)
   and prune the stale ones `git worktree prune` reports; leave the US
   Code site's worktrees alone.

Constraints: no token, key or password in source or in the transcript;
nothing on AWS is deleted or resized; the US Code site's containers are
never restarted by this session (the cut-over restarts its proxy through
its own deploy); the dev stacks on this machine are not touched; report
faithfully at the end of each section what passed, what failed with the
output, and what was skipped.
