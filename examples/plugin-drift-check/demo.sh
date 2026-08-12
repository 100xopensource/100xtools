#!/bin/sh
# Build a throwaway git repo with planted drift, so drift-check has something real to review.
#
#   ./examples/plugin-drift-check/demo.sh [target-dir]
#
# Copies the four Acme plugins into a fresh repo, commits them as the baseline, then applies
# the-change.patch on a branch. Prints how to run the review. Nothing here touches 100xtools.

set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TARGET=${1:-${TMPDIR:-/tmp}/drift-check-demo}

if [ -e "$TARGET" ]; then
  echo "refusing to write into existing path: $TARGET" >&2
  echo "remove it, or pass a different directory" >&2
  exit 1
fi

mkdir -p "$TARGET/plugins"
cp -R "$HERE/plugins/." "$TARGET/plugins/"

cd "$TARGET"
git init -q -b main
git add -A
git -c user.email=demo@example.com -c user.name=Demo commit -q -m "Four regional plugins, copied from one original"
BASE=$(git rev-parse HEAD)

# The reviewer resolves origin/main by default. There is no remote here, so point the ref
# at the baseline commit — the review then works exactly as it does in a real clone.
git update-ref refs/remotes/origin/main "$BASE"

git switch -q -c fix-week-boundary
git apply "$HERE/the-change.patch"
git add -A
git -c user.email=demo@example.com -c user.name=Demo commit -q -m "acme-north: report on the ISO week, not a rolling 7 days"

# The reviewer vendors into the repo under review, which is the whole point of install-skill.
mkdir -p .claude/skills
cp -R "$HERE/../../plugins/100xdrift-check/templates/skills/drift-check" .claude/skills/drift-check

cat <<EOF

Demo repo ready: $TARGET

  baseline   $BASE  (main, and origin/main)
  branch     fix-week-boundary — 2 files changed in acme-north

The reviewer is already vendored at .claude/skills/drift-check/, so:

  cd $TARGET
  claude
  > /drift-check

Expect four verdicts across two changed files. See expected-report.md next to this script
for the shape of a good answer — the wording will differ, the calls should not.

To rehearse the real setup instead, delete .claude/skills/drift-check and run
/100xdrift-check:install-skill with the plugin installed.
EOF
