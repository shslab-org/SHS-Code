#!/bin/bash
# Build the benchmark template workspace with git baseline
set -e
TPL=/home/z/my-project/bench/template-ws
rm -rf "$TPL"
mkdir -p "$TPL"/{src,tests,data}

cd "$TPL"

# README
cat > README.md << 'EOF'
# Benchmark Workspace

Tiny repo used by the SHS Code vs rivals controlled benchmark.
Contains a calculator module, string utils, and sales data.
EOF

# --- T2 bug: add() returns a-b ---
cat > src/calc.py << 'EOF'
def add(a, b):
    return a - b

def sub(a, b):
    return a - b
EOF

cat > tests/test_calc.py << 'EOF'
from src.calc import add, sub

def test_add():
    assert add(2, 3) == 5

def test_add_zero():
    assert add(7, 0) == 7

def test_sub():
    assert sub(9, 4) == 5
EOF

# --- T4 refactor: slugify must trim + collapse spaces, tests already expect it ---
cat > src/string_utils.py << 'EOF'
def slugify(s):
    return s.lower().replace(" ", "-")
EOF

cat > tests/test_strings.py << 'EOF'
from src.string_utils import slugify

def test_basic():
    assert slugify("Hello World") == "hello-world"

def test_trim_and_collapse():
    assert slugify("  Hello   World  ") == "hello-world"

def test_case():
    assert slugify("MiXeD CaSe") == "mixed-case"
EOF

# --- T5 data ---
cat > data/sales.csv << 'EOF'
date,region,amount
2026-01-01,dhaka,120
2026-01-02,chittagong,340
2026-01-03,dhaka,80
2026-01-04,sylhet,510
2026-01-05,chittagong,60
2026-01-06,sylhet,90
2026-01-07,dhaka,230
2026-01-08,khulna,150
2026-01-09,khulna,190
2026-01-10,sylhet,40
EOF

# git baseline
git init -q
git config user.email "bench@local"
git config user.name "bench"
git add -A
git commit -qm "baseline"
echo "template built at $TPL"
git log --oneline
