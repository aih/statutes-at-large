# ADR-0026: A deploy skips a documentation-only change

Date: 2026-09-10. Status: accepted. Amends the deployment plan
(`docs/plans/2026-09-08-deployment-plan.md`, item 5 and section 7).

## Context

`ci.yml` runs on every push. `deploy.yml` ran on every successful CI run on
`main`, with no look at the diff; `workflow_run` takes no path filter. Both
images change on every commit: the api image's `COPY . .` includes `docs/`
and the Markdown files at the root, and both Dockerfiles take `GIT_COMMIT`
as a build argument, the reader's before `npm run build`. `d5d9228`, which
changed `BUILDLOG.md` only, was built, pushed and deployed: a migration run,
the api and reader containers recreated, the proxy recreated.

The build argument was `github.sha`. Under `workflow_run` that is the latest
commit on the default branch, not the commit CI tested, which the workflow
resolves as `workflow_run.head_sha` and checks out.

## Decisions

1. **A `gate` job runs before the `deploy` job.** It checks out the commit
   with its full history and runs `deploy/deploy-gate.sh <sha>`, which prints
   `deploy=true` or `deploy=false`. The `deploy` job runs only on `true`.
   The gate job carries the conditions the deploy job had: the deploy role
   is set, and the run is a dispatch or a successful CI run on `main`.

2. **Documentation is a path under `docs/`, or a `*.md` file outside
   `frontend/`.** The comparison is against the commit
   `https://statutes.linkedlegislation.org/health` reports as `commit`, so a
   push of several commits is judged as a whole. The gate answers `false`
   when that commit is `<sha>` or an ancestor of it and every path changed
   between them is documentation, including when no path changed.

3. **Anything the gate cannot establish deploys.** `/health` not answering
   within 10 s, a `commit` of `unknown`, a commit the checkout does not hold,
   and a deployed commit that is not an ancestor of `<sha>` all answer `true`.

4. **A dispatch always deploys.** The gate step does not run the script for
   `workflow_dispatch`; a rollback or a redeploy of the same commit goes
   through.

5. **`GIT_COMMIT` is the resolved sha.** Both builds pass
   `steps.sha.outputs.sha`, the commit the box checks out, so `/health`, the
   status block and the footer name that commit.

## Consequences

After a documentation-only merge, `/health` and the footer name the last
commit that deployed, and the box's checkout stays at it. `deploy/*.sh` run
from that checkout, so a change to a script under `deploy/` is not
documentation and deploys. A change under `tests/` or `.github/` deploys.
