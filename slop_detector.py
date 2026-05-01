"""AI Slop Detector — 9 heuristic signals to detect AI-generated code patterns."""

import re
import math
import logging
from pathlib import Path
from collections import Counter

logger = logging.getLogger(__name__)

# ── Constants ──

SKIP_EXTS = {
    ".png", ".jpg", ".gif", ".svg", ".ico", ".woff", ".ttf", ".eot",
    ".mp3", ".mp4", ".zip", ".tar", ".gz", ".pyc", ".class", ".o",
    ".so", ".dll", ".exe", ".bin", ".lock", ".sum", ".min.js", ".min.css", ".map",
}
SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", ".venv", "venv", "dist",
    "build", ".next", ".turbo", "target", ".gradle",
}

GENERIC_NAMES = {
    "data", "temp", "tmp", "result", "results", "foo", "bar", "baz",
    "test", "thing", "stuff", "item", "items", "obj", "object",
    "value", "values", "param", "params", "arg", "args", "info",
    "config", "cfg", "settings", "options", "flag", "flags",
}

TEMPLATE_FINGERPRINTS = {
    "create-react-app": {
        "files": {"src/App.js", "src/App.css", "src/index.js", "src/reportWebVitals.js",
                  "public/index.html", "public/manifest.json"},
        "weight": 1.0,
    },
    "next.js": {
        "files": {"pages/index.tsx", "pages/_app.tsx", "next.config.js",
                  "styles/globals.css", "pages/api/hello.ts"},
        "weight": 1.0,
    },
    "vite-react": {
        "files": {"src/App.tsx", "src/main.tsx", "vite.config.ts",
                  "index.html", "src/index.css"},
        "weight": 1.0,
    },
    "django": {
        "files": {"manage.py", "settings.py", "urls.py", "wsgi.py", "asgi.py"},
        "weight": 0.8,
    },
    "express": {
        "files": {"app.js", "routes/index.js", "routes/users.js",
                  "public/stylesheets/style.css", "views/index.ejs"},
        "weight": 1.0,
    },
}

PYTHON_STDLIB = {
    "os", "sys", "re", "json", "math", "datetime", "time", "random",
    "collections", "itertools", "functools", "typing", "pathlib",
    "subprocess", "argparse", "logging", "hashlib", "uuid", "io",
    "csv", "shutil", "tempfile", "glob", "threading", "asyncio",
    "unittest", "http", "urllib", "email", "xml", "html", "sqlite3",
    "abc", "dataclasses", "enum", "concurrent", "contextlib",
    "copy", "pickle", "struct", "socket", "ssl", "base64", "textwrap",
    "string", "types", "traceback", "warnings", "weakref", "pprint",
    "ast", "inspect", "importlib", "pkgutil", "platform", "signal",
    "atexit", "getpass", "getopt", "configparser", "secrets",
    "statistics", "decimal", "fractions", "numbers", "bisect",
    "heapq", "array", "queue", "multiprocessing", "ctypes",
    "unittest.mock", "doctest", "zipfile", "tarfile", "fnmatch",
    "linecache", "tokenize", "keyword", "operator", "posixpath",
    "ntpath", "gettext", "locale", "codecs",
}

TOP_NPM_PACKAGES = {
    "react", "vue", "angular", "next", "express", "lodash", "axios",
    "moment", "typescript", "webpack", "babel", "eslint", "jest",
    "redux", "tailwindcss", "bootstrap", "sass", "postcss", "dotenv",
    "chalk", "commander", "yargs", "inquirer", "ora", "uuid",
    "dayjs", "date-fns", "zod", "yup", "formik", "react-hook-form",
    "swr", "tanstack", "prisma", "drizzle", "typeorm", "sequelize",
    "mongoose", "socket.io", "ws", "graphql", "apollo", "trpc",
    "vite", "rollup", "esbuild", "tsup", "turbo", "nx", "lerna",
    "nx", "changesets", "semver", "prettier", "eslint", "stylelint",
    "vitest", "playwright", "cypress", "puppeteer", "cheerio",
    "marked", "highlight.js", "prismjs", "three", "d3", "echarts",
    "antd", "element-ui", "arco-design", "@mui/material", "chakra-ui",
    "zustand", "jotai", "mobx", "rxjs", "i18next", "react-i18next",
    "react-router", "react-query", "@tanstack/react-query",
    "framer-motion", "gsap", "animejs", "nuxt", "svelte", "solid-js",
    "astro", "remix", "gatsby", "expo", "react-native",
    "electron", "tauri", "pkg", "nexe", "pm2", "nodemon", "ts-node",
    "nx", "turborepo", "storybook", "chromatic", "plop", "hygen",
}

SLOP_COMMENT_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"//\s*increment\s+(the\s+)?(counter|i|idx|index|n|count)\b",
        r"//\s*set\s+(the\s+)?(value|variable|name|title|flag)\b",
        r"//\s*(return|returns)\s+(the\s+)?(result|value|data|object|array)\b",
        r"//\s*loop\s+(through|over)\b",
        r"//\s*check\s+if\b",
        r"//\s*initialize\b",
        r"//\s*create\s+(a\s+)?(new\s+)?(function|class|variable|object)\b",
        r"//\s*(this|here)\s+(is|we)\s+(the|our)\b",
        r"#\s*(this|here)\s+(is|we)\s+(the|our)\s+(function|method|class|variable)\b",
        r"#\s*increment\b",
        r"#\s*set\s+the\s+value\b",
        r"#\s*initialize\s+(the\s+)?variable\b",
    ]
]

# ── Helper functions ──

def _read_file(filepath: Path) -> str | None:
    try:
        return filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None


def _is_source_file(filepath: Path) -> bool:
    ext = filepath.suffix.lower()
    source_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
                   ".java", ".c", ".cpp", ".h", ".cs", ".rb", ".php",
                   ".swift", ".kt", ".scala", ".r", ".lua", ".sh", ".bash",
                   ".md", ".rst", ".txt", ".yaml", ".yml", ".toml", ".json",
                   ".html", ".css", ".scss", ".less", ".vue", ".svelte"}
    return ext in source_exts


def _should_skip(filepath: Path) -> bool:
    if filepath.suffix.lower() in SKIP_EXTS:
        return True
    parts = set(filepath.parts)
    if parts & SKIP_DIRS:
        return True
    return False


def _count_lines(source: str) -> int:
    return source.count("\n") + 1


# ── Main detector class ──

class SlopDetector:
    """Detects AI-generated code patterns using 9 heuristic signals."""

    WEIGHTS = {
        "commit_bombing": 2.0,
        "generic_naming": 1.5,
        "over_commenting": 1.0,
        "no_tests": 2.0,
        "hallucinated_imports": 2.0,
        "single_contributor": 1.0,
        "template_structure": 1.5,
        "spray_pray_prs": 0.5,
        "placeholder_todos": 2.0,
    }
    MAX_PENALTY = 10.0 * sum(WEIGHTS.values())  # 135.0

    def __init__(self):
        self.reset()

    def reset(self):
        self.total_files = 0
        self.total_source_files = 0
        self.total_lines = 0
        self.red_flags: list[dict] = []
        self.stats: dict = {}
        self.recommendations: list[str] = []

    # ── Flag 1: Commit Bombing ──

    def _detect_commit_bombing(self, repo_path: Path, git_data: dict) -> tuple[float, list[str]]:
        commits = git_data.get("commits", [])
        total = git_data.get("total_commits", len(commits))
        evidence = []

        if total == 0:
            return 3.0, ["Unable to analyze commit history"]

        score = 0.0
        if total <= 2:
            score = 10.0
            evidence.append(f"Only {total} commit(s) total")
        elif total <= 5:
            score = 7.0
            evidence.append(f"Only {total} commits — very low for a real project")
        elif total <= 10:
            score = 4.0
            evidence.append(f"Only {total} commits — below typical for sustained development")

        massive_count = 0
        massive_lines = []
        for c in commits[:100]:
            changes = c.get("changes", 0)
            if changes > 500:
                massive_count += 1
                msg = c.get("message", "")[:80]
                massive_lines.append(f"{c['hash'][:7]}: +{changes} lines — {msg}")

        if total > 0 and massive_count / min(total, 100) > 0.5:
            score = max(score, 8.0)
            evidence.append(f"{massive_count}/{min(total,100)} commits exceed 500 lines")
            evidence.extend(massive_lines[:5])

        if evidence:
            return score, evidence
        return 0.0, []

    # ── Flag 2: Generic Naming ──

    def _detect_generic_naming(self, source_files: list[tuple[Path, str]]) -> tuple[float, list[str]]:
        all_identifiers = []
        generic_hits = []

        identifier_re = re.compile(r'\b([a-zA-Z_]\w{0,30})\b')

        for filepath, source in source_files[:500]:
            ext = filepath.suffix.lower()
            if ext not in (".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
                           ".java", ".c", ".cpp", ".cs", ".rb", ".php", ".swift", ".kt"):
                continue
            # Skip string literals and comments (simple heuristic)
            code_only = re.sub(r'(["\'""\'\'])(?:(?!\1)[^\\]|\\.)*\1', '', source)
            code_only = re.sub(r'#.*$', '', code_only, flags=re.MULTILINE)
            code_only = re.sub(r'//.*$', '', code_only, flags=re.MULTILINE)
            identifiers = identifier_re.findall(code_only)
            all_identifiers.extend(identifiers)

            for ident in identifiers:
                if ident.lower() in GENERIC_NAMES:
                    generic_hits.append((filepath.name, ident))

        if not all_identifiers:
            return 0.0, []

        total_idents = len(all_identifiers)
        generic_count = len(generic_hits)
        ratio = generic_count / total_idents

        # Count unique files with generic names
        files_with_generics = len(set(f for f, _ in generic_hits))

        if ratio > 0.08:
            score = 10.0
        elif ratio > 0.05:
            score = 7.0
        elif ratio > 0.03:
            score = 5.0
        elif ratio > 0.01:
            score = 3.0
        else:
            score = 0.0

        evidence = []
        if score > 0:
            top_generics = Counter(n for _, n in generic_hits).most_common(5)
            evidence.append(
                f"{generic_count}/{total_idents} identifiers are generic ({ratio:.1%}) "
                f"across {files_with_generics} files"
            )
            evidence.append(f"Top offenders: {', '.join(f'{n}({c}x)' for n, c in top_generics)}")

        return score, evidence

    # ── Flag 3: Over-Commenting ──

    def _detect_over_commenting(self, source_files: list[tuple[Path, str]]) -> tuple[float, list[str]]:
        total_code_lines = 0
        total_comment_lines = 0
        slop_comment_count = 0
        slop_examples = []

        for filepath, source in source_files[:500]:
            lines = source.split("\n")
            ext = filepath.suffix.lower()
            comment_prefixes = ("#", "//", "/*", " *", "*/", "<!--", "-->", "%", "; comment",
                                "REM ", "' comment", "<!--")
            code_prefixes = ("def ", "class ", "function ", "if ", "for ", "while ",
                             "return ", "import ", "from ", "const ", "let ", "var ",
                             "export ", "require(", "print(", "console.", "assert",
                             "async ", "await ", "try ", "catch ", "finally ")

            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue

                is_comment = any(stripped.startswith(p) for p in comment_prefixes)
                if not is_comment:
                    total_code_lines += 1
                    continue

                total_comment_lines += 1
                for pat in SLOP_COMMENT_PATTERNS:
                    if pat.search(stripped):
                        slop_comment_count += 1
                        if len(slop_examples) < 5:
                            slop_examples.append(f"{filepath.name}:{stripped[:80]}")
                        break

        total_lines = total_code_lines + total_comment_lines
        if total_lines == 0:
            return 0.0, []

        comment_ratio = total_comment_lines / total_lines
        evidence = []

        score = 0.0
        if comment_ratio > 0.40:
            score = 10.0
        elif comment_ratio > 0.30:
            score = 7.0
        elif comment_ratio > 0.20:
            score = 4.0

        if slop_comment_count > 0:
            score = max(score, min(10.0, slop_comment_count * 1.5))
            evidence.append(f"{slop_comment_count} obvious/redundant comments detected")
            evidence.extend(slop_examples)

        if score > 0 and not evidence:
            evidence.append(f"Comment-to-code ratio: {comment_ratio:.1%}")

        return score, evidence

    # ── Flag 4: No Tests ──

    def _detect_no_tests(self, repo_path: Path, git_data: dict) -> tuple[float, list[str]]:
        test_patterns = [
            "test_*.py", "*_test.py", "*.test.js", "*.test.ts",
            "*.test.jsx", "*.test.tsx", "*.spec.js", "*.spec.ts",
            "*.spec.jsx", "*.spec.tsx", "test_*.go", "*_test.go",
            "*Test.java", "*Tests.java", "*_test.rs", "test_*.rb",
        ]

        test_files = []
        for pattern in test_patterns:
            test_files.extend(repo_path.rglob(pattern))

        test_dirs = []
        for test_dir_name in ("tests", "test", "__tests__", "spec", "__spec__"):
            d = repo_path / test_dir_name
            if d.is_dir():
                test_dirs.append(d)

        has_tests = len(test_files) > 0 or len(test_dirs) > 0

        readme_claims = []
        for readme_name in ("README.md", "README.rst", "README.txt", "readme.md"):
            readme_path = repo_path / readme_name
            if readme_path.exists():
                content = _read_file(readme_path) or ""
                productive_patterns = [
                    r"\bproduction.ready\b", r"\bbattle.tested\b",
                    r"\benterprise\b", r"\brobust\b", r"\breliable\b",
                    r"\bhigh.quality\b", r"\bwell.tested\b", r"\bthoroughly.tested\b",
                ]
                for pat in productive_patterns:
                    m = re.search(pat, content, re.IGNORECASE)
                    if m:
                        readme_claims.append(f"{readme_name}: claims '{m.group()}'")

        evidence = []
        score = 0.0

        if not has_tests and readme_claims:
            score = 10.0
            evidence.append("0 test files found but README claims production quality")
            evidence.extend(readme_claims[:3])
        elif not has_tests:
            score = 7.0
            evidence.append("No test files or test directories found")
        elif len(test_files) < 3 and len(test_dirs) == 0:
            score = 4.0
            evidence.append(f"Only {len(test_files)} test file(s) — minimal coverage")
        else:
            return 0.0, []

        self.stats["has_tests"] = has_tests
        self.stats["test_file_count"] = len(test_files)
        return score, evidence

    # ── Flag 5: Hallucinated Imports ──

    def _detect_hallucinated_imports(self, source_files: list[tuple[Path, str]]) -> tuple[float, list[str]]:
        py_import_re = re.compile(r'^(?:from|import)\s+(\w+(?:\.\w+)*)', re.MULTILINE)
        js_import_re = re.compile(r'(?:require\(|from\s+)[\'"]([@\w][\w./-]*\w)', re.MULTILINE)

        unknown_imports = []

        for filepath, source in source_files[:500]:
            ext = filepath.suffix.lower()

            if ext == ".py":
                for m in py_import_re.finditer(source):
                    pkg = m.group(1).split(".")[0]
                    if pkg not in PYTHON_STDLIB and pkg not in TOP_NPM_PACKAGES:
                        if pkg.lower() not in {s.lower() for s in PYTHON_STDLIB}:
                            unknown_imports.append((filepath.name, pkg, "Python"))

            elif ext in (".js", ".ts", ".jsx", ".tsx"):
                for m in js_import_re.finditer(source):
                    pkg = m.group(1).split("/")[0]
                    if pkg.startswith("@") and "/" in m.group(1):
                        pkg = "/".join(m.group(1).split("/")[:2])
                    if pkg.startswith(".") or pkg.startswith(".."):
                        continue  # relative import
                    if pkg not in TOP_NPM_PACKAGES:
                        unknown_imports.append((filepath.name, pkg, "JS/TS"))

        if not unknown_imports:
            return 0.0, []

        # Deduplicate by package name
        seen = set()
        unique_unknowns = []
        for fname, pkg, lang in unknown_imports:
            key = pkg.lower()
            if key not in seen:
                seen.add(key)
                unique_unknowns.append((fname, pkg, lang))

        count = len(unique_unknowns)
        evidence = [f"{count} potentially unknown import(s) detected"]
        evidence.extend(f"{pkg} ({lang}) in {f}" for f, pkg, _ in unique_unknowns[:5])

        if count >= 5:
            return 10.0, evidence
        elif count >= 3:
            return 7.0, evidence
        elif count >= 2:
            return 5.0, evidence
        else:
            return 3.0, evidence

    # ── Flag 6: Single Contributor ──

    def _detect_single_contributor(self, repo_path: Path, git_data: dict) -> tuple[float, list[str]]:
        contributors = git_data.get("contributors", [])
        count = git_data.get("contributor_count", len(contributors))

        evidence = []
        if count == 0:
            return 0.0, []

        if count == 1:
            name = contributors[0] if isinstance(contributors[0], str) else contributors[0].get("name", "unknown")
            return 10.0, [f"Single contributor: {name}"]
        elif count == 2:
            return 5.0, [f"Only {count} contributors"]
        elif count <= 3:
            return 2.0, [f"Only {count} contributors"]

        return 0.0, []

    # ── Flag 7: Template Structure ──

    def _detect_template_structure(self, repo_path: Path, git_data: dict) -> tuple[float, list[str]]:
        all_files = set()
        for fp in repo_path.rglob("*"):
            if fp.is_file() and not _should_skip(fp):
                try:
                    rel = str(fp.relative_to(repo_path)).replace("\\", "/")
                    all_files.add(rel)
                except Exception:
                    pass

        best_match = None
        best_ratio = 0.0

        for template_name, tmpl in TEMPLATE_FINGERPRINTS.items():
            if not tmpl["files"]:
                continue
            matches = sum(1 for f in tmpl["files"] if f in all_files)
            ratio = matches / len(tmpl["files"])
            weighted = ratio * tmpl["weight"]
            if weighted > best_ratio:
                best_ratio = weighted
                best_match = template_name

        if best_ratio > 0.7:
            score = 10.0 if best_ratio > 0.9 else 7.0
            evidence = [f"File structure matches '{best_match}' template ({best_ratio:.0%})"]
            return score, evidence
        elif best_ratio > 0.5:
            return 5.0, [f"Partial match to '{best_match}' template ({best_ratio:.0%})"]
        elif best_ratio > 0.3:
            return 3.0, [f"Some resemblance to '{best_match}' template ({best_ratio:.0%})"]

        return 0.0, []

    # ── Flag 8: Spray-and-Pray PRs ──

    def _detect_spray_pray_prs(self, repo_path: Path, git_data: dict) -> tuple[float, list[str]]:
        branches = git_data.get("branches", [])
        if not branches:
            return 0.0, []

        spray_keywords = {"fix", "update", "wip", "test", "patch", "refactor",
                          "cleanup", "chore", "tweak", "change", "add", "remove"}
        spray_branches = []
        single_commit_branches = 0
        total_branches = len(branches)

        for b in branches:
            name = b.get("name", "").lower()
            commit_count = b.get("commit_count", 1)
            if commit_count <= 1:
                single_commit_branches += 1
            for kw in spray_keywords:
                if kw in name:
                    spray_branches.append(b.get("name", ""))
                    break

        evidence = []
        spray_ratio = len(spray_branches) / max(total_branches, 1)

        if spray_ratio > 0.5:
            score = 8.0
        elif spray_ratio > 0.3:
            score = 5.0
        elif spray_ratio > 0.1:
            score = 2.0
        else:
            score = 0.0

        if score > 0:
            evidence.append(f"{len(spray_branches)}/{total_branches} branches have spray-pattern names")
            evidence.append(f"Examples: {', '.join(spray_branches[:5])}")

        return score, evidence

    # ── Flag 9: Placeholder TODOs ──

    def _detect_placeholder_todos(self, source_files: list[tuple[Path, str]]) -> tuple[float, list[str]]:
        todo_patterns = [
            (re.compile(r'#\s*TODO\b', re.IGNORECASE), "TODO"),
            (re.compile(r'#\s*FIXME\b', re.IGNORECASE), "FIXME"),
            (re.compile(r'#\s*HACK\b', re.IGNORECASE), "HACK"),
            (re.compile(r'//\s*TODO\b', re.IGNORECASE), "TODO"),
            (re.compile(r'//\s*FIXME\b', re.IGNORECASE), "FIXME"),
            (re.compile(r'//\s*HACK\b', re.IGNORECASE), "HACK"),
            (re.compile(r'\bpass\s*$'), "pass"),
            (re.compile(r'raise\s+NotImplementedError'), "NotImplementedError"),
            (re.compile(r'throw\s+new\s+Error\([\'"]Not\s+implemented'), "NotImplemented"),
            (re.compile(r'unimplemented!\s*\(?\s*\)?\s*;?'), "unimplemented!"),
        ]

        total_lines = 0
        placeholder_count = 0
        placeholder_examples = []

        for filepath, source in source_files[:500]:
            lines = source.split("\n")
            total_lines += len(lines)
            for lineno, line in enumerate(lines, 1):
                for pat, label in todo_patterns:
                    if pat.search(line):
                        placeholder_count += 1
                        break

        if total_lines == 0:
            return 0.0, []

        density = placeholder_count / (total_lines / 1000)  # per 1K LOC
        evidence = [f"{placeholder_count} placeholders/TODOs ({density:.1f} per 1K LOC)"]

        if density > 20:
            return 10.0, evidence
        elif density > 10:
            return 7.0, evidence
        elif density > 5:
            return 5.0, evidence
        elif density > 1:
            return 2.0, evidence

        return 0.0, []

    # ── Main analysis entry point ──

    def analyze(self, repo_path: Path, git_data: dict | None = None) -> dict:
        """Run all 9 detectors and return a complete report.

        Args:
            repo_path: Path to the cloned repository
            git_data: Optional dict with keys:
                - commits: list of {hash, message, changes}
                - total_commits: int
                - contributors: list of str or {name, email}
                - contributor_count: int
                - branches: list of {name, commit_count}
                - total_branches: int

        Returns:
            Report dict with score, verdict, red_flags, stats, recommendations
        """
        self.reset()
        git_data = git_data or {}

        # Walk source files
        source_files: list[tuple[Path, str]] = []
        all_files = list(repo_path.rglob("*"))
        file_count = min(len(all_files), 10000)

        for fp in all_files[:10000]:
            if not fp.is_file():
                continue
            if _should_skip(fp):
                continue
            if not _is_source_file(fp):
                continue
            source = _read_file(fp)
            if source is None:
                continue
            source_files.append((fp, source))
            self.total_source_files += 1
            self.total_lines += _count_lines(source)

        self.total_files = file_count
        self.stats.update({
            "total_files": self.total_files,
            "total_source_files": self.total_source_files,
            "total_lines": self.total_lines,
        })

        # Try to get git stats from the repo
        if not git_data:
            git_data = _extract_git_data(repo_path)
        self.stats.update({
            "total_commits": git_data.get("total_commits", 0),
            "contributors": git_data.get("contributor_count", 0),
            "has_readme": (repo_path / "README.md").exists(),
        })

        # Run all detectors
        detectors = [
            ("commit_bombing", self._detect_commit_bombing(repo_path, git_data)),
            ("generic_naming", self._detect_generic_naming(source_files)),
            ("over_commenting", self._detect_over_commenting(source_files)),
            ("no_tests", self._detect_no_tests(repo_path, git_data)),
            ("hallucinated_imports", self._detect_hallucinated_imports(source_files)),
            ("single_contributor", self._detect_single_contributor(repo_path, git_data)),
            ("template_structure", self._detect_template_structure(repo_path, git_data)),
            ("spray_pray_prs", self._detect_spray_pray_prs(repo_path, git_data)),
            ("placeholder_todos", self._detect_placeholder_todos(source_files)),
        ]

        raw_penalty = 0.0
        self.red_flags = []
        self.recommendations = []

        severity_order = {"high": 0, "medium": 1, "low": 2}

        for flag_id, (score, evidence) in detectors:
            weight = self.WEIGHTS[flag_id]
            raw_penalty += score * weight

            if score > 0:
                sev = "high" if score >= 7 else "medium" if score >= 4 else "low"
                label = flag_id.replace("_", " ").title()

                self.red_flags.append({
                    "id": flag_id,
                    "label": label,
                    "severity": sev,
                    "score": round(score, 1),
                    "evidence": evidence,
                })

                if score >= 7:
                    self._add_recommendation(flag_id)

        # Sort red flags by severity then score
        self.red_flags.sort(key=lambda f: (severity_order.get(f["severity"], 3), -f["score"]))

        # Compute final score
        if self.MAX_PENALTY > 0:
            final_score = round(100 * (1 - raw_penalty / self.MAX_PENALTY))
        else:
            final_score = 100
        final_score = max(0, min(100, final_score))

        if final_score >= 80:
            verdict = "clean"
        elif final_score >= 40:
            verdict = "suspicious"
        else:
            verdict = "likely_slop"

        return {
            "score": final_score,
            "verdict": verdict,
            "red_flags": self.red_flags,
            "stats": self.stats,
            "recommendations": self.recommendations,
        }

    def _add_recommendation(self, flag_id: str):
        recs = {
            "commit_bombing": "Break up large commits into logical chunks for reviewability",
            "generic_naming": "Replace generic variable names (data, temp, result) with domain-specific names",
            "over_commenting": "Remove obvious comments. Code should be self-documenting with clear names",
            "no_tests": "Add unit tests — no test files found for a project claiming production readiness",
            "hallucinated_imports": "Verify all imported packages exist in the target language's package registry",
            "single_contributor": "Review code history — single-contributor repos are common in AI-generated projects",
            "template_structure": "Project appears to be based on a stock template with minimal modification",
            "spray_pray_prs": "Clean up branch clutter and use meaningful branch names",
            "placeholder_todos": "Resolve or remove TODO/FIXME/HACK placeholders before claiming completion",
        }
        if flag_id in recs:
            self.recommendations.append(recs[flag_id])


def _extract_git_data(repo_path: Path) -> dict:
    """Extract git metadata from a cloned repository."""
    data = {
        "commits": [],
        "total_commits": 0,
        "contributors": [],
        "contributor_count": 0,
        "branches": [],
        "total_branches": 0,
    }

    try:
        import git
        repo = git.Repo(str(repo_path))

        for c in repo.iter_commits("--all", max_count=100):
            changes = c.stats.total.get("lines", 0) if c.stats.total else 0
            data["commits"].append({
                "hash": c.hexsha,
                "message": c.message.strip(),
                "changes": changes,
            })

        data["total_commits"] = sum(1 for _ in repo.iter_commits("--all"))

        authors = set()
        for c in repo.iter_commits("--all", max_count=500):
            authors.add(c.author.email)
        data["contributors"] = list(authors)
        data["contributor_count"] = len(authors)

        try:
            branches = []
            for ref in repo.references:
                name = ref.name.replace("origin/", "").replace("refs/heads/", "").replace("refs/remotes/", "")
                if name == "HEAD":
                    continue
                count = sum(1 for _ in repo.iter_commits(ref.name, max_count=100))
                branches.append({"name": name, "commit_count": count})
            data["branches"] = branches
            data["total_branches"] = len(branches)
        except Exception:
            pass

    except ImportError:
        logger.warning("gitpython not installed — skipping git metadata extraction")
    except Exception as e:
        logger.warning(f"Git extraction failed: {e}")

    return data
