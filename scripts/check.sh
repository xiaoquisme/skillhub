#!/usr/bin/env bash
# scripts/check.sh — 自动化反馈控制脚本
# Agent 在每个 task 完成后运行此脚本，获取结构化的 PASS/FAIL 结果。
# 这是 Steering Loop 中 Sensors 阶段的计算型控制。
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

PASS=0
FAIL=0
RESULTS=()

# ── Helper ───────────────────────────────────────────────
pass() { PASS=$((PASS + 1)); RESULTS+=("PASS  $1"); }
fail() { FAIL=$((FAIL + 1)); RESULTS+=("FAIL  $1"); }

# ── 1. 测试 ─────────────────────────────────────────────
echo "=== Running tests ==="
# Use venv python if available, otherwise fall back to python3
PYTHON="${PROJECT_ROOT}/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    PYTHON=python3
fi

if "$PYTHON" -m pytest --tb=short -q 2>&1; then
    pass "pytest"
else
    fail "pytest"
fi

# ── 2. Gotcha 检查（计算型控制）────────────────────────
echo ""
echo "=== Checking known gotchas ==="

# 2a. 不要引入 passlib
if grep -rn "from passlib\|import passlib" skillhub/ --include="*.py" 2>/dev/null; then
    fail "passlib detected — use bcrypt native API (see docs/conventions/gotchas.md)"
else
    pass "no passlib usage"
fi

# 2b. 不要引入 exp 在 JWT token 中（已知设计：无过期时间）
# 这是一个信息性检查，不是错误
if grep -rn "exp.*datetime\|expires" skillhub/auth.py 2>/dev/null | grep -v "^#" >/dev/null 2>&1; then
    # 有 exp 相关代码 — 可能是好事（加了过期），也可能是坏事
    # 标记为 INFO 而不是 FAIL
    RESULTS+=("INFO  JWT token has expiry — verify this is intentional")
else
    pass "JWT no expiry (by design)"
fi

# 2c. 检查 CORS 配置
if grep -n 'allow_origins=\["\*"\]' skillhub/main.py >/dev/null 2>&1; then
    # 这是已知状态，不是 bug，但标记提醒
    RESULTS+=("INFO  CORS is wide open (allow_origins=[\"*\"]) — tighten before production")
else
    pass "CORS origins restricted"
fi

# 2d. 确认 state/ 目录存在
if [ -d "state" ] && [ -f "state/roadmap.md" ] && [ -f "state/progress.json" ]; then
    pass "state/ directory intact"
else
    fail "state/ directory missing or incomplete"
fi

# 2e. 确认 scripts/check.sh 自身存在且可执行
if [ -x "scripts/check.sh" ]; then
    pass "check.sh is executable"
else
    fail "check.sh is not executable"
fi

# 2f. 确认 docs/conventions/gotchas.md 存在
if [ -f "docs/conventions/gotchas.md" ]; then
    pass "gotchas.md exists"
else
    fail "docs/conventions/gotchas.md missing"
fi

# ── 报告 ─────────────────────────────────────────────────
echo ""
echo "==============================="
echo "  CHECK RESULTS"
echo "==============================="
for r in "${RESULTS[@]}"; do
    echo "  $r"
done
echo "==============================="
echo "  Total: $((PASS + FAIL))  |  PASS: $PASS  |  FAIL: $FAIL"
echo "==============================="

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "RESULT: FAIL — fix the issues above before proceeding."
    exit 1
else
    echo ""
    echo "RESULT: PASS — all checks passed."
    exit 0
fi
