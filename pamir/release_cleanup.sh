#!/bin/bash
# Tidy GitHub releases of this repo: keep the newest $1 stable releases (the latest one always) and the
# newest $2 test pre-releases; delete the rest together with their tags. $3=1 only prints the plan.
# The app updater and the site mirror read releases/latest, so older releases are not needed by anyone.
set -u
KEEP_STABLE=${1:-3}; KEEP_TESTS=${2:-1}; DRY=${3:-0}
OUT=${GITHUB_STEP_SUMMARY:-/dev/stdout}
LIST=$(gh release list -R "$GITHUB_REPOSITORY" --limit 300 --json tagName,isPrerelease,isLatest,isDraft,publishedAt) || exit 1
PLAN=$(python3 - "$KEEP_STABLE" "$KEEP_TESTS" "$LIST" <<'PY'
import json, sys
keep_s, keep_t, rel = int(sys.argv[1]), int(sys.argv[2]), json.loads(sys.argv[3])
rel.sort(key=lambda r: r.get("publishedAt") or "", reverse=True)
stable = [r for r in rel if not r["isPrerelease"] and not r["isDraft"]]
tests = [r for r in rel if r["isPrerelease"] or r["isDraft"]]
keep = {r["tagName"] for r in stable[:keep_s] + tests[:keep_t]} | {r["tagName"] for r in rel if r["isLatest"]}
for r in rel:
    print(("keep" if r["tagName"] in keep else "delete"), r["tagName"])
PY
) || exit 1
{
  echo "### Релизы: оставить $KEEP_STABLE обычных и $KEEP_TESTS тестовых$([ "$DRY" = 1 ] && echo ' (только показ, ничего не удалено)')"
  echo "$PLAN" | awk '{print "- " ($1=="keep" ? "оставить" : "удалить") " `" $2 "`"}'
} >> "$OUT"
[ "$DRY" = 1 ] && exit 0
FAIL=0
for tag in $(echo "$PLAN" | awk '$1=="delete"{print $2}'); do
  if gh release delete "$tag" -R "$GITHUB_REPOSITORY" --yes --cleanup-tag; then echo "удалён $tag"
  else echo "::warning::не удалось удалить $tag"; FAIL=1; fi
done
exit $FAIL
