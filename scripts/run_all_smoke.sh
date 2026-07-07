#!/usr/bin/env bash
# Run all skill smoke tests in parallel, collect results, emit GH step summary.
# Usage: bash scripts/run_all_smoke.sh
#
# Classification (per skill):
#   FAIL   - the smoke test exited non-zero.
#   GATED  - exited clean but ran no real data: every data step was skipped for
#            want of a credential (API key / personal token). Nothing to verify.
#   PASS   - exercised real upstream data and all assertions held. A skill still
#            counts as PASS if some steps degraded to [SKIP] for transient
#            reasons (bot-wall, browser-only, one flaky endpoint) as long as at
#            least one real data assertion ran.

RESULTS_DIR=/tmp/smoke-results
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$RESULTS_DIR"
export RESULTS_DIR REPO_ROOT

# Portable list (no mapfile: macOS ships Bash 3.2). The worker body is inlined
# into the xargs subshell so it does not depend on `export -f` surviving into a
# freshly spawned bash (which it does not on Bash 3.2).
skills=$(ls "$REPO_ROOT/skills/" | sort)
count=$(printf '%s\n' "$skills" | grep -c .)
echo "Running ${count} skills (<=16 parallel)..."

printf '%s\n' "$skills" | xargs -P 16 -I{} bash -c '
    skill="$1"
    uv_args=(run --no-project)
    if [[ "${COLAB_SMOKE_WITH_CLOAKBROWSER:-}" == "1" ]]; then
        uv_args+=(--with cloakbrowser)
    fi
    uv "${uv_args[@]}" python "$REPO_ROOT/skills/$skill/scripts/smoke_test.py" \
        > "$RESULTS_DIR/${skill}.log" 2>&1
    printf "%d\n" $? > "$RESULTS_DIR/${skill}.exit"
' _ {}

pass=0; gated=0; fail=0
failed_skills=(); gated_skills=(); table_rows=()

for skill in $skills; do
    ec=1
    [[ -f "$RESULTS_DIR/${skill}.exit" ]] && ec=$(<"$RESULTS_DIR/${skill}.exit")
    log="$RESULTS_DIR/${skill}.log"

    # The exit code is authoritative: each smoke test already decides pass/fail
    # and handles its own skips. We only *further* distinguish two exit-0 cases,
    # and only for tests using the [PASS]/[SKIP] bracket convention (many skills
    # print free-form "OK ..." lines — those are trusted as PASS on exit 0):
    #   GATED  - no real data ran; every data step skipped for a missing
    #            credential (regex below). Nothing was actually verified.
    #   PASS*  - real data ran but some step degraded to [SKIP] (bot-wall,
    #            browser-only, one flaky endpoint).
    if [[ "$ec" -ne 0 ]]; then
        result=FAIL; emoji="❌"
        fail=$((fail+1)); failed_skills+=("$skill")
    elif [[ -f "$log" ]] && grep -q '\[SKIP\]' "$log" \
         && [[ "$(grep '\[PASS\]' "$log" | grep -v -- '--help' | grep -vc 'skips without')" -eq 0 ]] \
         && grep -qiE 'requires .*(api[_ ]?key|token)|intentionally skipped|[A-Z]+_API_KEY' "$log"; then
        result=GATED; emoji="🔑"
        gated=$((gated+1)); gated_skills+=("$skill")
    else
        if [[ -f "$log" ]] && grep -qE '\[SKIP\]' "$log"; then
            result="PASS*"; emoji="✅"
        else
            result=PASS; emoji="✅"
        fi
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
        echo "**PASS: ${pass} | GATED: ${gated} | FAIL: ${fail}**"
        echo ""
        echo "_PASS\* = passed with some steps skipped (transient/browser-only). GATED = needs a credential; nothing ran._"
        if [[ ${#gated_skills[@]} -gt 0 ]]; then
            echo ""
            echo "GATED (missing credential): ${gated_skills[*]}"
        fi
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
    (IFS=", "; echo "PASS: ${pass}, GATED: ${gated}, FAIL: ${fail} (${failed_skills[*]})")
    for skill in "${failed_skills[@]}"; do
        echo "===== FAIL: ${skill} ====="
        cat "$RESULTS_DIR/${skill}.log"
        echo "============================="
    done
else
    echo "PASS: ${pass}, GATED: ${gated}, FAIL: ${fail}"
fi

[[ $fail -eq 0 ]]
