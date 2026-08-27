"""정적 회귀 검사 - 존재하지 않는 속성/메서드 호출을 실행 전에 잡는다.

배경: 대시보드 수정 폼이 `Database.update_watch` 라는 **존재하지 않는 메서드**를
호출해 저장할 때마다 죽는 버그가 있었다. 실제 메서드명은 update_watch_fields다.
문법 오류가 아니라 스모크 테스트로도 잡히지 않았고, 그 화면을 눌러 봐야만
드러났다. 같은 부류(AI가 지어낸 이름, 오타 Literal)를 아래에서 기계적으로 막는다.

    python tests/static_check.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Database 인스턴스가 담기는 것으로 알려진 변수명들
DB_VARS = {"db", "dbase", "d_", "fresh_db", "database", "_db"}

# 감시 조건 trip_type 은 모델 Literal 상 "one-way"(하이픈)여야 한다
FORBIDDEN_LITERALS = {"one_way": 'trip_type은 "one-way"(하이픈)여야 합니다'}

failures: list[str] = []


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class_members(tree: ast.Module, class_name: str) -> set[str]:
    """클래스의 메서드 + __init__에서 self.X = ... 로 만드는 속성."""
    members: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    members.add(item.name)
            for sub in ast.walk(node):
                if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name):
                    if sub.value.id == "self" and isinstance(sub.ctx, ast.Store):
                        members.add(sub.attr)
    return members


def _module_names(tree: ast.Module) -> set[str]:
    """모듈 최상위에서 정의·할당·임포트된 이름 전부."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                names.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, (ast.If, ast.Try)):  # try/except 임포트 등
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    for a in sub.names:
                        names.add(a.asname or a.name.split(".")[0])
                elif isinstance(sub, (ast.FunctionDef, ast.ClassDef)):
                    names.add(sub.name)
    return names


def _py_files() -> list[Path]:
    out: list[Path] = []
    for d in ("app", "streamlit_app"):
        out += sorted((ROOT / d).rglob("*.py"))
    out.append(ROOT / "monitor.py")
    return [p for p in out if p.exists()]


def check_attribute_usage(label: str, holder_names: set[str], allowed: set[str]) -> None:
    """holder_names 변수에 대한 속성 접근이 allowed 안에 있는지 검사."""
    for path in _py_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
                continue
            if node.value.id not in holder_names:
                continue
            if node.attr.startswith("__") or node.attr in allowed:
                continue
            failures.append(
                f"{path.relative_to(ROOT)}:{node.lineno} "
                f"{label}에 없는 이름을 씁니다: {node.value.id}.{node.attr}"
            )


def check_forbidden_literals() -> None:
    for path in _py_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                reason = FORBIDDEN_LITERALS.get(node.value)
                if reason:
                    failures.append(
                        f"{path.relative_to(ROOT)}:{node.lineno} "
                        f'금지된 문자열 "{node.value}" - {reason}'
                    )


def main() -> int:
    db_tree = _parse(ROOT / "app" / "database.py")
    check_attribute_usage("Database", DB_VARS, _class_members(db_tree, "Database"))

    shared_tree = _parse(ROOT / "streamlit_app" / "shared.py")
    check_attribute_usage("shared 모듈", {"shared"}, _module_names(shared_tree))

    cfg_tree = _parse(ROOT / "app" / "config.py")
    cfg_allowed = _module_names(cfg_tree)
    for node in ast.walk(cfg_tree):  # __getattr__ 이 처리하는 _KEYS 도 허용
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_KEYS" for t in node.targets
        ):
            cfg_allowed |= {
                e.value for e in ast.walk(node.value)
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
    check_attribute_usage("config 모듈", {"config", "cfg"}, cfg_allowed)

    check_forbidden_literals()

    if failures:
        print(f"FAIL - {len(failures)}건\n")
        for f in failures:  # 콘솔 인코딩(cp949) 호환을 위해 ASCII 불릿을 쓴다
            print("  -", f)
        return 1
    print("PASS - 정적 검사 통과 (Database / shared / config 속성, 금지 리터럴)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
