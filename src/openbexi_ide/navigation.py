"""Bounded, source-only Python completion and project navigation.

This module reads Python syntax, never imports or evaluates project code. It
intentionally leaves dynamic attributes and installed-library definitions to a
future language-server integration. Call it on a worker, not the GUI thread.
"""
from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass
import keyword
from itertools import islice
import os
from pathlib import Path
import re
import tokenize


MAX_FILES = 2000
MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 20_000_000
SKIP_DIRECTORIES = {".git", ".venv", "venv", "env", "__pycache__", "node_modules",
                    "build", "dist", ".tox", ".qualification"}


@dataclass(frozen=True)
class Symbol:
    path: Path
    name: str
    kind: str
    line: int
    column: int
    scope: tuple[str, ...] = ()
    module: str | None = None
    imported: str | None = None
    level: int = 0
    value: str | None = None

    @property
    def qualified_name(self):
        return ".".join((*self.scope, self.name))


@dataclass(frozen=True)
class Completion:
    name: str
    kind: str


@dataclass
class Module:
    path: Path
    symbols: list[Symbol]
    scopes: list[tuple[int, int, tuple[str, ...]]]

    def scope_at(self, line):
        matches = [scope for start, end, scope in self.scopes if start <= line <= end]
        return max(matches, key=len, default=())

    def visible(self, line):
        scope = self.scope_at(line)
        names = {}
        for length in range(len(scope) + 1):
            for symbol in self.symbols:
                if symbol.scope == scope[:length]:
                    names[symbol.name] = symbol
        return names


def _expression(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _expression(node.value)
        return parent + "." + node.attr if parent else None
    if isinstance(node, ast.Call):
        return _expression(node.func)
    return None


class _Index(ast.NodeVisitor):
    def __init__(self, path, source):
        self.path, self.lines = path, source.splitlines()
        self.scope = ()
        self.symbols, self.scopes = [], []

    def add(self, name, kind, node, **extra):
        # AST columns count UTF-8 bytes; the editor consumes Unicode columns.
        line = self.lines[node.lineno - 1] if node.lineno <= len(self.lines) else ""
        column = len(line.encode("utf-8")[:node.col_offset].decode("utf-8", "ignore"))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            match = re.search(r"\b" + re.escape(name) + r"\b", line[column:])
            if match:
                column += match.start()
        self.symbols.append(Symbol(self.path, name, kind, node.lineno, column, self.scope, **extra))

    def _body(self, node, kind):
        self.add(node.name, kind, node)
        old = self.scope
        self.scope = (*old, node.name)
        self.scopes.append((node.lineno, node.end_lineno, self.scope))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs,
                             *([node.args.vararg] if node.args.vararg else []),
                             *([node.args.kwarg] if node.args.kwarg else [])]:
                self.add(argument.arg, "parameter", argument)
        for child in node.body:
            self.visit(child)
        self.scope = old

    def visit_FunctionDef(self, node):
        self._body(node, "function")

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self._body(node, "class")

    def _target(self, node, value=None):
        if isinstance(node, ast.Name):
            self.add(node.id, "variable", node, value=value)
        elif isinstance(node, (ast.Tuple, ast.List)):
            for child in node.elts:
                self._target(child)

    def visit_Assign(self, node):
        for target in node.targets:
            self._target(target, _expression(node.value))

    def visit_AnnAssign(self, node):
        self._target(node.target, _expression(node.value) or _expression(node.annotation))

    def visit_NamedExpr(self, node):
        self._target(node.target, _expression(node.value))

    def visit_For(self, node):
        self._target(node.target)
        self.generic_visit(node)

    visit_AsyncFor = visit_For

    def visit_With(self, node):
        for item in node.items:
            if item.optional_vars:
                self._target(item.optional_vars)
        self.generic_visit(node)

    visit_AsyncWith = visit_With

    def visit_Import(self, node):
        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            module = alias.name if alias.asname else name
            self.add(name, "module", node, module=module)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            if alias.name != "*":
                self.add(alias.asname or alias.name, "import", node, module=node.module or "",
                         imported=alias.name, level=node.level)


def parse_module(path, source):
    """Recover a few incomplete editing lines without executing any source."""
    lines = source.splitlines(keepends=True)
    candidate = list(lines)
    for _ in range(8):
        try:
            tree = ast.parse("".join(candidate), filename=str(path))
            index = _Index(path, source)
            index.visit(tree)
            return Module(path, index.symbols, index.scopes)
        except (SyntaxError, ValueError) as error:
            number = getattr(error, "lineno", None)
            if not number or not 1 <= number <= len(candidate):
                break
            line = candidate[number - 1]
            replacement = line[:len(line) - len(line.lstrip())] + "pass\n"
            if replacement == line:
                break
            candidate[number - 1] = replacement
        except (RecursionError, MemoryError):
            break
    return Module(path, [], [])


def word_at(text, line, column, *, before=False):
    """Return a dotted identifier at a Unicode (not UTF-16) cursor column."""
    lines = text.split("\n")
    current = lines[line - 1] if 0 < line <= len(lines) else ""
    column = min(max(column, 0), len(current))
    left = re.search(r"[\w.]*$", current[:column])
    right = re.match(r"\w*", current[column:])
    return left.group() + ("" if before else right.group())


class ProjectIndex:
    def __init__(self, root: Path, buffers: dict[Path, str] | None = None):
        self.root = root.resolve()
        self.buffers = {Path(path).resolve(): source for path, source in (buffers or {}).items()
                        if Path(path).resolve().is_relative_to(self.root)}
        self.modules = {}
        self.total_bytes = 0
        self.limited = False

    def load(self, path):
        path = Path(path).resolve()
        if not path.is_relative_to(self.root):
            return None
        if path in self.modules:
            return self.modules[path]
        if len(self.modules) >= MAX_FILES:
            self.limited = True
            return None
        try:
            if path.is_dir():
                module = Module(path, [], [])
                self.modules[path] = module
                return module
            if path.suffix not in {".py", ".pyi"}:
                return None
            if path in self.buffers:
                source = self.buffers[path]
                size = len(source.encode("utf-8"))
            else:
                size = path.stat().st_size
                if size > MAX_FILE_BYTES or self.total_bytes + size > MAX_TOTAL_BYTES:
                    self.limited = True
                    return None
                with tokenize.open(path) as stream:
                    source = stream.read(MAX_FILE_BYTES + 1)
                size = len(source.encode("utf-8"))
            if size > MAX_FILE_BYTES or self.total_bytes + size > MAX_TOTAL_BYTES:
                self.limited = True
                return None
            self.total_bytes += size
            module = parse_module(path, source)
            self.modules[path] = module
            return module
        except (OSError, UnicodeError, SyntaxError):
            return None

    def _module_path(self, dotted):
        if not dotted or any(not part.isidentifier() for part in dotted.split(".")):
            return None
        for base in (self.root, self.root / "src"):
            candidate = base.joinpath(*dotted.split("."))
            for path in (candidate.with_suffix(".py"), candidate / "__init__.py",
                         candidate.with_suffix(".pyi")):
                if path.is_file() and path.resolve().is_relative_to(self.root):
                    return path.resolve()
            if candidate.is_dir() and candidate.resolve().is_relative_to(self.root):
                return candidate.resolve()
        return None

    def _import_module_name(self, symbol):
        if not symbol.level:
            return symbol.module or ""
        path = symbol.path
        base = self.root / "src" if path.is_relative_to(self.root / "src") else self.root
        package = list(path.relative_to(base).parent.parts)
        if symbol.level > len(package):
            return ""
        package = package[:len(package) - symbol.level + 1]
        return ".".join([*package, *filter(None, (symbol.module or "").split("."))])

    def _follow(self, target, seen):
        if not isinstance(target, Symbol) or target in seen or len(seen) > 30:
            return target
        seen = seen | {target}
        if target.module is not None:
            name = self._import_module_name(target)
            path = self._module_path(name)
            module = self.load(path) if path else None
            if target.imported:
                if module:
                    member = next((s for s in module.symbols if not s.scope and s.name == target.imported), None)
                    if member:
                        return self._follow(member, seen)
                path = self._module_path(name + "." + target.imported)
                return self.load(path) if path else None
            return module
        return target

    def _members(self, target, seen=None):
        seen = set() if seen is None else seen
        target = self._follow(target, seen)
        if isinstance(target, Module):
            members = {s.name: s for s in target.symbols if not s.scope}
            if target.path.is_dir() or target.path.name == "__init__.py":
                directory = target.path if target.path.is_dir() else target.path.parent
                try:
                    for path in islice(directory.iterdir(), MAX_FILES):
                        if path.is_dir() and path.name.isidentifier() and path.name not in SKIP_DIRECTORIES:
                            init = path / "__init__.py"
                            module = self.load(init if init.is_file() else path)
                            if module:
                                members.setdefault(path.name, module)
                        elif path.suffix in {".py", ".pyi"} and path.stem != "__init__":
                            module = self.load(path)
                            if module:
                                members.setdefault(path.stem, module)
                except OSError:
                    pass
            return members
        if isinstance(target, Symbol):
            if target.value and target not in seen:
                module = self.load(target.path)
                value = self.resolve(module, target.value, target.line, seen | {target})
                return self._members(value, seen | {target})
            if target.kind == "class":
                module = self.load(target.path)
                return {s.name: s for s in module.symbols if s.scope == (*target.scope, target.name)}
        return {}

    def resolve(self, module, expression, line, seen=None):
        if not module or not expression:
            return None
        seen = set() if seen is None else seen
        parts = expression.split(".")
        target = module.visible(line).get(parts[0])
        if parts[0] in {"self", "cls"} and len(parts) > 1:
            scope = module.scope_at(line)
            owner = next((s for s in module.symbols if s.kind == "class"
                          and (*s.scope, s.name) == scope[:-1]), None)
            target = owner or target
        for part in parts[1:]:
            target = self._members(target, seen).get(part)
        return self._follow(target, seen)

    def complete(self, path, source, line, column):
        module = self.load(path)
        expression = word_at(source, line, column, before=True)
        if "." in expression:
            parent, prefix = expression.rsplit(".", 1)
            target = self.resolve(module, parent, line)
            names = {name: symbol.kind if isinstance(symbol, Symbol) else "module"
                     for name, symbol in self._members(target).items()}
        else:
            prefix = expression
            names = {name: "keyword" for name in (*keyword.kwlist, *keyword.softkwlist)}
            names.update({name: "builtin" for name in dir(builtins) if not name.startswith("_")})
            if module:
                names.update({name: symbol.kind for name, symbol in module.visible(line).items()})
        return [Completion(name, names[name]) for name in sorted(names, key=str.casefold)
                if name.startswith(prefix) and name != prefix][:300]

    def definition(self, path, source, line, column):
        target = self.resolve(self.load(path), word_at(source, line, column), line)
        if isinstance(target, Module):
            if target.path.is_dir():
                return None  # A namespace package has no source location to open.
            return Symbol(target.path, target.path.stem, "module", 1, 0)
        return target

    def symbols(self):
        paths = set(self.buffers)
        for count, (directory, subdirs, files) in enumerate(os.walk(self.root, followlinks=False)):
            if count >= MAX_FILES:
                self.limited = True
                break
            subdirs[:] = sorted(name for name in subdirs if not name.startswith(".")
                               and name not in SKIP_DIRECTORIES
                               and not (Path(directory) / name).is_symlink())
            for name in sorted(files):
                if name.endswith((".py", ".pyi")):
                    paths.add(Path(directory) / name)
                    if len(paths) >= MAX_FILES:
                        self.limited = True
                        break
            if self.limited:
                break
        result = []
        for path in sorted(paths):
            module = self.load(path)
            if module:
                result.extend(symbol for symbol in module.symbols
                              if symbol.kind in {"class", "function", "variable"})
        return sorted(result, key=lambda symbol: (symbol.name.casefold(), str(symbol.path), symbol.line))
