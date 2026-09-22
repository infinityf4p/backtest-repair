"""Conservative static protection of strategy parameters and unaffected behavior."""
from __future__ import annotations
import ast
from collections import Counter
from pathlib import Path


def _parts(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8-sig"))
    imports, declarations, methods, conditions = [], [], {}, []
    def visit_scope(nodes, prefix=""):
        for node in nodes:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(ast.dump(node, include_attributes=False))
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                declarations.append((prefix, ast.dump(node, include_attributes=False)))
            elif isinstance(node, ast.ClassDef):
                declarations.append((prefix + node.name, repr([ast.dump(b, include_attributes=False) for b in node.bases])))
                visit_scope(node.body, prefix + node.name + ".")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = prefix + node.name
                methods[name] = ast.dump(node, include_attributes=False)
                for child in ast.walk(node):
                    if isinstance(child, ast.Compare):
                        conditions.append((name, ast.dump(child, include_attributes=False)))
            elif not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                declarations.append((prefix, ast.dump(node, include_attributes=False)))
    visit_scope(tree.body)
    return imports, declarations, methods, Counter(conditions)


def check_preservation(original, candidate, policy=None):
    policy = policy or {}
    before, after = _parts(original), _parts(candidate)
    errors = []
    if before[0] != after[0]:
        errors.append("Imports changed outside the declared strategy repair")
    if before[1] != after[1]:
        errors.append("Class/module parameters or inheritance changed")
    editable = set(policy.get("editable_methods", []))
    for name in before[2].keys() | after[2].keys():
        if name not in editable and before[2].get(name) != after[2].get(name):
            errors.append("Protected method changed: " + name)
    if policy.get("preserve_conditions", True) and before[3] != after[3]:
        errors.append("Trading comparison predicates changed")
    return {"status": "fail" if errors else "pass", "errors": errors, "editable_methods": sorted(editable)}
