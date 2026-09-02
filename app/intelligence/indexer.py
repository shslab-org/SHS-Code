from __future__ import annotations

"""
SHS Code — Source Indexer (Project Intelligence Layer, spec §2/§4)
==================================================================
Language-aware symbol + dependency extraction.

Python  : full `ast` parsing — classes, functions, methods, async defs,
          imports (from/import), module docstrings.
JS/TS   : structural regex — functions, classes, arrow consts, imports,
          exports, interfaces, types, React components.
Kotlin  : classes, interfaces, objects, fun declarations, package/imports.
Java    : classes, interfaces, package/imports.
PHP     : classes, interfaces, functions, namespace/use.
Go      : package, funcs, types, structs, imports.
Markdown: headings (as outline symbols).

Zero external dependencies — pure stdlib. Every extraction degrades
gracefully: an unreadable/undecodable file yields no symbols, never an
exception. Bounds: file size cap + per-file symbol cap so pathological
inputs cannot stall indexing.
"""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

MAX_FILE_BYTES = 1_500_000     # skip files > 1.5 MB (generated/minified)
MAX_SYMBOLS_PER_FILE = 400

LANGUAGE_BY_EXT = {
    ".py": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".kt": "kotlin", ".kts": "kotlin",
    ".java": "java",
    ".php": "php",
    ".go": "go",
    ".md": "markdown", ".markdown": "markdown",
    ".rs": "rust", ".rb": "ruby", ".cs": "csharp", ".cpp": "cpp", ".cc": "cpp",
    ".h": "c_header", ".hpp": "cpp", ".c": "c", ".swift": "swift",
    ".scala": "scala", ".sh": "shell", ".sql": "sql", ".vue": "vue", ".svelte": "svelte",
}

# Directories never indexed (generated / vendored / vcs / build output)
IGNORED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "venv", ".venv", "env", "virtualenv",
    "build", "dist", "target", "out", ".gradle", ".idea", ".vscode", ".vs",
    "vendor", "bower_components", "coverage", ".tox", ".next", ".nuxt",
    ".terraform", "Pods", "DerivedData", ".cache", ".parcel-cache",
    "site-packages", "bin", "obj",
}


@dataclass
class Symbol:
    name: str
    kind: str                 # class | function | method | interface | object | type | heading | const
    path: str
    line: int
    end_line: int = 0
    signature: str = ""       # short one-line signature/summary
    doc: str = ""

    def to_row(self) -> tuple:
        return (self.path, self.name, self.kind, self.line, self.end_line,
                self.signature[:300], self.doc[:300])


@dataclass
class ImportStmt:
    path: str
    module: str
    kind: str                 # import | from | require | use | package
    names: List[str] = field(default_factory=list)

    def to_row(self) -> tuple:
        return (self.path, self.module[:200], self.kind, ",".join(self.names)[:300])


@dataclass
class FileIndex:
    path: str
    language: str
    lines: int
    mtime: float
    size: int
    symbols: List[Symbol] = field(default_factory=list)
    imports: List[ImportStmt] = field(default_factory=list)

    @property
    def symbol_count(self) -> int:
        return len(self.symbols)


def should_skip_path(p: Path) -> bool:
    name = p.name
    if name.startswith(".") and name not in (".github", ".env.example"):
        return True
    for part in p.parts:
        if part in IGNORED_DIRS or part.endswith(".egg-info"):
            return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Python — full AST
# ──────────────────────────────────────────────────────────────────────────────

def _py_doc(node) -> str:
    try:
        d = ast.get_docstring(node)
        return (d or "").strip().split("\n")[0][:200]
    except Exception:
        return ""


def _py_signature(node) -> str:
    try:
        args = []
        defaults_offset = len(node.args.args) - len(node.args.defaults)
        for i, a in enumerate(node.args.args):
            arg = a.arg
            if a.annotation is not None:
                arg += f": {ast.unparse(a.annotation)}"
            di = i - defaults_offset
            if 0 <= di < len(node.args.defaults):
                arg += f" = {ast.unparse(node.args.defaults[di])}"
            args.append(arg)
        if node.args.vararg:
            args.append("*" + node.args.vararg.arg)
        if node.args.kwarg:
            args.append("**" + node.args.kwarg.arg)
        ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {node.name}({', '.join(args)}){ret}"[:300]
    except Exception:
        return f"{node.name}(…)"


def index_python(path: str, source: str) -> Tuple[List[Symbol], List[ImportStmt]]:
    symbols: List[Symbol] = []
    imports: List[ImportStmt] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Degraded mode: regex fallback for broken files
        return _index_python_regex(path, source)

    def walk(node, prefix: str = ""):
        if len(symbols) >= MAX_SYMBOLS_PER_FILE:
            return
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(Symbol(
                    name=child.name, kind="method" if prefix else "function",
                    path=path, line=child.lineno,
                    end_line=getattr(child, "end_lineno", child.lineno) or child.lineno,
                    signature=_py_signature(child), doc=_py_doc(child)))
                walk(child)
            elif isinstance(child, ast.ClassDef):
                symbols.append(Symbol(
                    name=child.name, kind="class", path=path, line=child.lineno,
                    end_line=getattr(child, "end_lineno", child.lineno) or child.lineno,
                    signature=f"class {child.name}", doc=_py_doc(child)))
                walk(child, prefix=f"{child.name}.")
            elif isinstance(child, ast.Import):
                for alias in child.names:
                    imports.append(ImportStmt(
                        path=path, module=alias.name, kind="import",
                        names=[alias.asname or alias.name]))
            elif isinstance(child, ast.ImportFrom):
                mod = "." * child.level + (child.module or "")
                imports.append(ImportStmt(
                    path=path, module=mod, kind="from",
                    names=[a.name for a in child.names]))
            else:
                walk(child, prefix)

    walk(tree)
    return symbols, imports


def _index_python_regex(path: str, source: str) -> Tuple[List[Symbol], List[ImportStmt]]:
    symbols, imports = [], []
    for i, line in enumerate(source.split("\n"), 1):
        m = re.match(r"\s*(?:async\s+)?def\s+(\w+)", line)
        if m:
            symbols.append(Symbol(m.group(1), "function", path, i, 0, line.strip()[:200]))
            continue
        m = re.match(r"\s*class\s+(\w+)", line)
        if m:
            symbols.append(Symbol(m.group(1), "class", path, i, 0, line.strip()[:200]))
            continue
        m = re.match(r"\s*(?:from\s+[\w.]+\s+)?import\s+(.+)", line)
        if m:
            imports.append(ImportStmt(path, m.group(1)[:120], "import", []))
    return symbols[:MAX_SYMBOLS_PER_FILE], imports


# ──────────────────────────────────────────────────────────────────────────────
# JS / TS — structural regex
# ──────────────────────────────────────────────────────────────────────────────

_JS_PATTERNS = [
    (re.compile(r"^(?:export\s+)?(?:default\s+)?async\s+function\s+(\w+)\s*\(([^)]*)\)"),
     "function", "async function {n}({args})"),
    (re.compile(r"^(?:export\s+)?(?:default\s+)?function\s+(\w+)\s*\(([^)]*)\)"),
     "function", "function {n}({args})"),
    (re.compile(r"^(?:export\s+)?(?:default\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?"),
     "class", "class {n}"),
    (re.compile(r"^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)"),
     "class", "class {n}"),
    (re.compile(r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*(?::\s*[\w<>\[\] |]+)?\s*=>"),
     "function", "const {n} = ({args}) =>"),
    (re.compile(r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?function"),
     "function", "{n} = function"),
    (re.compile(r"^(?:export\s+)?type\s+(\w+)\s*[=<]"),
     "type", "type {n}"),
    (re.compile(r"^(?:export\s+)?interface\s+(\w+)"),
     "interface", "interface {n}"),
]

_JS_IMPORTS = [
    # import X from "m" | import {a} from "m" | import "m"
    (re.compile(r"^import\s+(?:.*\bfrom\s+)?['\"]([^'\"]+)['\"]"), "import"),
    (re.compile(r"^const\s+\{([^}]*)\}\s*=\s*require\(['\"]([^'\"]+)['\"]\)"), "require"),
]


def index_js_ts(path: str, source: str, lang: str = "javascript") -> Tuple[List[Symbol], List[ImportStmt]]:
    symbols: List[Symbol] = []
    imports: List[ImportStmt] = []
    for i, line in enumerate(source.split("\n"), 1):
        if len(symbols) >= MAX_SYMBOLS_PER_FILE:
            break
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("*"):
            continue
        matched = False
        for rx, kind, sig_tmpl in _JS_PATTERNS:
            m = rx.match(stripped)
            if m:
                name = m.group(1)
                args = m.group(2).strip() if (m.lastindex or 0) >= 2 and m.group(2) else ""
                sig = sig_tmpl.replace("{n}", name).replace("{args}", args)
                symbols.append(Symbol(name, kind, path, i, 0, sig[:250]))
                matched = True
                break
        if matched:
            continue
        for rx, kind in _JS_IMPORTS:
            m = rx.match(stripped)
            if m:
                if kind == "require" and (m.lastindex or 0) >= 2:
                    names = [x.strip() for x in (m.group(1) or "").split(",") if x.strip()]
                    imports.append(ImportStmt(path, m.group(2), kind, names))
                else:
                    imports.append(ImportStmt(path, m.group(1) or "(import)", kind, []))
                break
    return symbols, imports


# ──────────────────────────────────────────────────────────────────────────────
# Kotlin / Java / PHP / Go — structural regex
# ──────────────────────────────────────────────────────────────────────────────

_KT_JAVA_PATTERNS = [
    (re.compile(r"^\s*(?:public\s+|private\s+|protected\s+|internal\s+|open\s+|abstract\s+|sealed\s+|data\s+|final\s+|static\s+|)*"
                r"(class|interface|object|enum class|record)\s+(\w+)"), "class"),
    (re.compile(r"^\s*(?:public\s+|private\s+|protected\s+|internal\s+|open\s+|abstract\s+|suspend\s+|inline\s+|operator\s+|override\s+|final\s+|static\s+|)*"
                r"(?:fun|def)\s+(?:[\w.]+\s+)?(\w+)\s*\("), "function"),
]
_KT_IMPORT = re.compile(r"^\s*(?:import|package)\s+([\w.]+)")
_JAVA_PACKAGE = re.compile(r"^\s*package\s+([\w.]+);")

_PHP_PATTERNS = [
    (re.compile(r"^\s*(?:abstract\s+|final\s+)?(?:class|interface|trait)\s+(\w+)"), "class"),
    (re.compile(r"^\s*(?:public\s+|private\s+|protected\s+|static\s+|abstract\s+|)*function\s+(\w+)\s*\("), "function"),
]
_PHP_IMPORT = re.compile(r"^\s*(?:use|namespace)\s+([\w\\]+)")

_GO_PATTERNS = [
    (re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?(\w+)\s*\("), "function"),
    (re.compile(r"^\s*type\s+(\w+)\s+(?:struct|interface)"), "type"),
]
_GO_IMPORT = re.compile(r'^\s*"([^"]+)"')


def index_kotlin_java(path: str, source: str, lang: str) -> Tuple[List[Symbol], List[ImportStmt]]:
    symbols, imports = [], []
    for i, line in enumerate(source.split("\n"), 1):
        if len(symbols) >= MAX_SYMBOLS_PER_FILE:
            break
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("*"):
            continue
        matched = False
        for rx, kind in _KT_JAVA_PATTERNS:
            m = rx.match(line)
            if m:
                symbols.append(Symbol(m.group(2) if kind == "class" else m.group(1),
                                       kind, path, i, 0, stripped[:250]))
                matched = True
                break
        if matched:
            continue
        m = _KT_IMPORT.match(line) or _JAVA_PACKAGE.match(line)
        if m:
            imports.append(ImportStmt(path, m.group(1), "import", []))
    return symbols, imports


def index_php(path: str, source: str) -> Tuple[List[Symbol], List[ImportStmt]]:
    symbols, imports = [], []
    for i, line in enumerate(source.split("\n"), 1):
        if len(symbols) >= MAX_SYMBOLS_PER_FILE:
            break
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("#"):
            continue
        matched = False
        for rx, kind in _PHP_PATTERNS:
            m = rx.match(line)
            if m:
                symbols.append(Symbol(m.group(1),
                                       "interface" if "interface" in line else kind,
                                       path, i, 0, stripped[:250]))
                matched = True
                break
        if matched:
            continue
        m = _PHP_IMPORT.match(line)
        if m:
            imports.append(ImportStmt(path, m.group(1).replace("\\", "."), "use", []))
    return symbols, imports


def index_go(path: str, source: str) -> Tuple[List[Symbol], List[ImportStmt]]:
    symbols, imports = [], []
    in_import_block = False
    for i, line in enumerate(source.split("\n"), 1):
        if len(symbols) >= MAX_SYMBOLS_PER_FILE:
            break
        stripped = line.strip()
        if stripped.startswith("import ("):
            in_import_block = True
            continue
        if in_import_block:
            if stripped == ")":
                in_import_block = False
                continue
            m = _GO_IMPORT.match(stripped)
            if m:
                imports.append(ImportStmt(path, m.group(1), "import", []))
            continue
        matched = False
        for rx, kind in _GO_PATTERNS:
            m = rx.match(line)
            if m:
                symbols.append(Symbol(m.group(1), kind, path, i, 0, stripped[:250]))
                matched = True
                break
        if matched:
            continue
        if stripped.startswith("package "):
            imports.append(ImportStmt(path, stripped[8:], "package", []))
        elif stripped.startswith("import "):
            m = _GO_IMPORT.match(stripped[7:])
            if m:
                imports.append(ImportStmt(path, m.group(1), "import", []))
    return symbols, imports


def index_markdown(path: str, source: str) -> Tuple[List[Symbol], List[ImportStmt]]:
    symbols = []
    for i, line in enumerate(source.split("\n"), 1):
        m = re.match(r"^(#{1,3})\s+(.+)$", line)
        if m:
            symbols.append(Symbol(m.group(2).strip(), "heading", path, i, 0,
                                  f"{'#' * len(m.group(1))} {m.group(2).strip()}"[:200]))
    return symbols, []


_GENERIC_PATTERNS = [
    (re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)"), "function"),
    (re.compile(r"^\s*(?:pub\s+)?(?:struct|enum|trait|mod)\s+(\w+)"), "type"),
    (re.compile(r"^\s*(?:public|private|protected|internal|virtual|override|\s)*(?:class|struct|enum)\s+(\w+)"), "class"),
    (re.compile(r"^\s*def\s+(\w+)"), "function"),
]


def index_generic(path: str, source: str, lang: str) -> Tuple[List[Symbol], List[ImportStmt]]:
    symbols = []
    for i, line in enumerate(source.split("\n"), 1):
        if len(symbols) >= MAX_SYMBOLS_PER_FILE:
            break
        for rx, kind in _GENERIC_PATTERNS:
            m = rx.match(line)
            if m:
                symbols.append(Symbol(m.group(1), kind, path, i, 0, line.strip()[:250]))
                break
    return symbols, []


# ──────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ──────────────────────────────────────────────────────────────────────────────

def index_file(path: str, source: str, lang: str) -> Tuple[List[Symbol], List[ImportStmt]]:
    """Index one file's source. Never raises — returns empty on failure."""
    try:
        if lang == "python":
            return index_python(path, source)
        if lang in ("javascript", "typescript"):
            return index_js_ts(path, source, lang)
        if lang in ("kotlin", "java"):
            return index_kotlin_java(path, source, lang)
        if lang == "php":
            return index_php(path, source)
        if lang == "go":
            return index_go(path, source)
        if lang == "markdown":
            return index_markdown(path, source)
        return index_generic(path, source, lang)
    except Exception:
        return [], []


def read_source(p: Path) -> Optional[str]:
    """Read a source file with graceful encoding fallback. None = skip."""
    try:
        if p.stat().st_size > MAX_FILE_BYTES:
            return None
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def walk_source_files(root: Path, max_files: int = 20000) -> List[Path]:
    """Walk the tree respecting ignore rules. Bounded by max_files."""
    out: List[Path] = []
    root = Path(root)
    stack = [root]
    while stack and len(out) < max_files:
        cur = stack.pop()
        try:
            entries = sorted(cur.iterdir(), reverse=True)
        except OSError:
            continue
        for e in entries:
            if len(out) >= max_files:
                break
            if should_skip_path(e):
                continue
            if e.is_dir():
                stack.append(e)
            elif e.is_file() and e.suffix.lower() in LANGUAGE_BY_EXT:
                out.append(e)
    return out
