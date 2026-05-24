#!/usr/bin/env bash
# Run all skill smoke tests in parallel, collect results, emit GH step summary.
# Usage: bash scripts/run_all_smoke.sh

RESULTS_DIR=/tmp/smoke-results
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$RESULTS_DIR"

_smoke_one() {
    local skill="$1"
    uv run --no-project python "$REPO_ROOT/skills/$skill/scripts/smoke_test.py" \
        > "$RESULTS_DIR/${skill}.log" 2>&1
    printf '%d\n' $? > "$RESULTS_DIR/${skill}.exit"
}
export -f _smoke_one
export RESULTS_DIR REPO_ROOT

mapfile -t skills < <(ls "$REPO_ROOT/skills/" | sort)
echo "Running ${#skills[@]} skills (≤16 parallel)…"

printf '%s\n' "${skills[@]}" | xargs -P 16 -I{} bash -c '_smoke_one "$@"' _ {}

pass=0; skip=0; fail=0
declare -a failed_skills=() skip_skills=() table_rows=()

for skill in "${skills[@]}"; do
    ec=1
    [[ -f "$RESULTS_DIR/${skill}.exit" ]] && ec=$(<"$RESULTS_DIR/${skill}.exit")

    if [[ "$ec" -ne 0 ]]; then
        result=FAIL; emoji="❌"
        fail=$((fail+1))
        failed_skills+=("$skill")
    elif [[ -f "$RESULTS_DIR/${skill}.log" ]] && grep -q '\[SKIP\]' "$RESULTS_DIR/${skill}.log"; then
        result=SKIP; emoji="⏭️"
        skip=$((skip+1))
        skip_skills+=("$skill")
    else
        result=PASS; emoji="✅"
        pass=$((pass+1))
    fi

    table_rows+=("| ${emoji} | \`${skill}\` | ${result} |")
done

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    {
        echo "## 🥝 Smoke Test Results"
        echo ""
        echo "| | Skill | Result |"
        echo "|---|-------|--------|"
        printf '%s\n' "${table_rows[@]}"
        echo ""
        echo "**PASS: ${pass} | SKIP: ${skip} | FAIL: ${fail}**"
        if [[ ${#failed_skills[@]} -gt 0 ]]; then
            echo ""
            echo "### Failed Skill Logs"
            for skill in "${failed_skills[@]}"; do
                echo ""
                echo "<details>"
                echo "<summary>❌ ${skill}</summary>"
                echo ""
                echo '```'
                cat "$RESULTS_DIR/${skill}.log"
                echo '```'
                echo ""
                echo "</details>"
            done
        fi
    } >> "$GITHUB_STEP_SUMMARY"
fi

if [[ ${#failed_skills[@]} -gt 0 ]]; then
    (IFS=", "; echo "PASS: ${pass}, SKIP: ${skip}, FAIL: ${fail} (${failed_skills[*]})")
else
    echo "PASS: ${pass}, SKIP: ${skip}, FAIL: ${fail}"
fi

[[ $fail -eq 0 ]]
