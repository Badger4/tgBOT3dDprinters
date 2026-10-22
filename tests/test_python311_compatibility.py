"""tests/test_python311_compatibility.py

Automated Python 3.11 Compatibility & Static Guardrail Test Suite.
Validates that code written in the repository does not use Python 3.12+ syntax
or standard library features, even when executed by developers on Python 3.13/3.14.
"""

import ast
import os
import shutil
import subprocess
import tokenize
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "logs",
    "printers_storage",
    "webapp",
    "scratch",
    ".gemini",
    ".agents",
}

DISALLOWED_312_IMPORTS = {
    "typing": {"override", "TypeAliasType", "TypeIs"},
    "itertools": {"batched"},
    "sys": {"monitoring"},
    "warnings": {"deprecated"},
}


def get_all_python_files():
    """Yield all Python files in the project excluding virtualenvs and cache directories."""
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            if file.endswith(".py"):
                yield Path(root) / file


class Python311ASTCompatibilityVisitor(ast.NodeVisitor):
    """AST visitor that checks for Python 3.12+ syntax and stdlib constructs."""

    def __init__(self, filename: Path):
        self.filename = filename
        self.errors: list[str] = []

    def visit_TypeAlias(self, node):
        # PEP 695 type statement: `type X = int` (Python 3.12+)
        self.errors.append(
            f"{self.filename}:{node.lineno}:{node.col_offset}: "
            f"PEP 695 'type' statement is only supported in Python 3.12+"
        )
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        if getattr(node, "type_params", None):
            self.errors.append(
                f"{self.filename}:{node.lineno}:{node.col_offset}: "
                f"PEP 695 generic function syntax 'def {node.name}[T]():' is Python 3.12+"
            )
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        if getattr(node, "type_params", None):
            self.errors.append(
                f"{self.filename}:{node.lineno}:{node.col_offset}: "
                f"PEP 695 generic async function syntax 'async def {node.name}[T]():' is Python 3.12+"
            )
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        if getattr(node, "type_params", None):
            self.errors.append(
                f"{self.filename}:{node.lineno}:{node.col_offset}: "
                f"PEP 695 generic class syntax 'class {node.name}[T]:' is Python 3.12+"
            )
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name in ("sys.monitoring",):
                self.errors.append(
                    f"{self.filename}:{node.lineno}: Import '{alias.name}' is only available in Python 3.12+"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module in DISALLOWED_312_IMPORTS:
            disallowed = DISALLOWED_312_IMPORTS[node.module]
            for alias in node.names:
                if alias.name in disallowed:
                    hint = " (use typing_extensions.override instead)" if alias.name == "override" else ""
                    self.errors.append(
                        f"{self.filename}:{node.lineno}: Importing '{alias.name}' from '{node.module}' "
                        f"is Python 3.12+{hint}"
                    )
        self.generic_visit(node)


def check_pep701_fstrings(file_path: Path) -> list[str]:
    """
    Validates that f-strings adhere to Python 3.11 restrictions:
    1. No backslashes ('\\') anywhere within '{ ... }' expressions.
    2. No reuse of enclosing quote delimiters inside '{ ... }' expressions.
    """
    errors = []
    try:
        with open(file_path, "rb") as f:
            tokens = list(tokenize.tokenize(f.readline))
    except Exception as e:
        return [f"{file_path}: Tokenization failed: {e}"]

    fstring_quotes_stack: list[str] = []
    expr_depth = 0

    for tok in tokens:
        tok_name = tokenize.tok_name.get(tok.type, "")
        if tok_name == "FSTRING_START":
            # Extract quote delimiter (e.g. ', ", ''', """)
            quote = tok.string.lstrip("fFrRbBuU")
            fstring_quotes_stack.append(quote)
        elif tok_name == "FSTRING_END":
            if fstring_quotes_stack:
                fstring_quotes_stack.pop()
        elif fstring_quotes_stack:
            if tok_name == "OP" and tok.string == "{":
                expr_depth += 1
            elif tok_name == "OP" and tok.string == "}":
                expr_depth = max(0, expr_depth - 1)
            elif expr_depth > 0:
                # Inside an f-string expression:
                if "\\" in tok.string:
                    errors.append(
                        f"{file_path}:{tok.start[0]}:{tok.start[1]}: "
                        f"Backslash in f-string expression is forbidden on Python <= 3.11 (PEP 701, added in 3.12)"
                    )
                if tok_name == "STRING":
                    outer_quote = fstring_quotes_stack[-1]
                    inner_quote = tok.string[0]
                    if inner_quote in outer_quote:
                        errors.append(
                            f"{file_path}:{tok.start[0]}:{tok.start[1]}: "
                            f"Reusing outer f-string quotes inside expression is forbidden on Python <= 3.11"
                        )
    return errors


class TestPython311Compatibility:
    """Test suite ensuring strict Python 3.11 compatibility."""

    def test_ast_python311_compatibility(self):
        """Scans all Python source files using AST visitor for 3.12+ features."""
        all_errors = []
        for py_file in get_all_python_files():
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    content = f.read()
                tree = ast.parse(content, filename=str(py_file))
                visitor = Python311ASTCompatibilityVisitor(py_file)
                visitor.visit(tree)
                all_errors.extend(visitor.errors)
            except Exception as e:
                all_errors.append(f"{py_file}: Parse failure: {e}")

        assert not all_errors, (
            f"Detected {len(all_errors)} Python 3.12+ syntax/import violations:\n"
            + "\n".join(all_errors)
        )

    def test_pep701_fstrings_python311(self):
        """Ensures no PEP 701 f-string features (backslashes or quote reuse) are used."""
        all_errors = []
        for py_file in get_all_python_files():
            errors = check_pep701_fstrings(py_file)
            all_errors.extend(errors)

        assert not all_errors, (
            f"Detected {len(all_errors)} PEP 701 f-string violations that break on Python 3.11:\n"
            + "\n".join(all_errors)
        )

    def test_ruff_target_version_311_syntax(self):
        """Runs Ruff with --target-version py311 to assert 0 syntax errors under 3.11 grammar."""
        ruff_bin = shutil.which("ruff")
        if not ruff_bin:
            candidate = PROJECT_ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("ruff.exe" if os.name == "nt" else "ruff")
            if candidate.exists():
                ruff_bin = str(candidate)

        if not ruff_bin:
            pytest.skip("Ruff binary not installed in environment; skipping Ruff syntax verification.")

        result = subprocess.run(
            [ruff_bin, "check", "--target-version", "py311", "--select", "invalid-syntax,E999", "--output-format", "concise", "."],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        syntax_errors = [
            line for line in result.stdout.splitlines()
            if "invalid-syntax" in line or "E999" in line
        ]
        assert not syntax_errors, (
            f"Ruff flagged {len(syntax_errors)} syntax errors for Python 3.11 target:\n"
            + "\n".join(syntax_errors)
        )

    def test_toolchain_configurations_target_311(self):
        """Validates that pyproject.toml, mypy.ini, and CI workflows strictly target Python 3.11."""
        pyproject_path = PROJECT_ROOT / "pyproject.toml"
        assert pyproject_path.exists(), "pyproject.toml not found"
        pyproject_text = pyproject_path.read_text(encoding="utf-8")

        assert 'requires-python = ">=3.11"' in pyproject_text, "requires-python must be '>=3.11'"
        assert 'target-version = "py311"' in pyproject_text, (
            "pyproject.toml [tool.ruff] target-version MUST be 'py311'"
        )

        if "[tool.mypy]" in pyproject_text:
            assert 'python_version = "3.11"' in pyproject_text, (
                "pyproject.toml [tool.mypy] python_version MUST be '3.11'"
            )

        mypy_ini_path = PROJECT_ROOT / "mypy.ini"
        if mypy_ini_path.exists():
            mypy_ini_text = mypy_ini_path.read_text(encoding="utf-8")
            assert "python_version = 3.11" in mypy_ini_text, "mypy.ini python_version MUST be 3.11"

        ci_path = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
        if ci_path.exists():
            ci_text = ci_path.read_text(encoding="utf-8")
            assert '"3.11"' in ci_text or "'3.11'" in ci_text, "CI matrix must test on Python 3.11"
