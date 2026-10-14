"""Read-only first-party inventory. Never read local env/secrets, data or caches."""
import ast
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
directories = ["Backend/app", "Backend/tests", "Backend/scripts", "Backend/migrations", "Backend/infra",
               "Backend/evaluation", "frontend/src", "frontend/public", "docs", ".github"]
files = set()
for directory in directories:
    for path in (ROOT / directory).rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix.lower() not in {'.pyc', '.png', '.pdf'}:
            files.add(path)
for name in ("README.md", "NOTES.md", "MVP_REVIEW.md", ".gitignore", "Backend/README.md", "Backend/pyproject.toml",
             "Backend/uv.lock", "Backend/Dockerfile", "Backend/.dockerignore", "Backend/.env.example", "Backend/run.py",
             "Backend/compose.yaml", "Backend/alembic.ini", "frontend/README.md", "frontend/package.json", "frontend/package-lock.json",
             "frontend/.env.example", "frontend/.gitignore", "frontend/tsconfig.json", "frontend/vite.config.ts",
             "frontend/vitest.config.ts", "frontend/index.html", "frontend/metadata.json"):
    path = ROOT / name
    if path.is_file():
        files.add(path)
inventory = []
for path in sorted(files):
    raw = path.read_bytes()
    content = raw.decode('utf-8-sig')
    item = dict(path=path.relative_to(ROOT).as_posix(), lines=len(content.splitlines()), sha256=hashlib.sha256(raw).hexdigest())
    if path.suffix == '.py':
        tree = ast.parse(content)
        item['symbols'] = [{'name': node.name, 'line': node.lineno, 'kind': type(node).__name__}
                           for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        item['tests'] = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test_')]
        item['except_types'] = sorted({ast.unparse(node.type) if node.type else 'bare except' for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)})
        item['validators'] = [{'function': node.name, 'line': node.lineno} for node in ast.walk(tree)
                             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any('validator' in ast.unparse(d) for d in node.decorator_list)]
    inventory.append(item)
result = {'scope': 'First-party application, tests, migrations, scripts, deployment/config examples and documentation. Dependencies/lockfiles inventoried; no CVE claim. No private env, secrets, caches, PDFs or generated vendor sources.',
          'files': inventory}
destination = ROOT / 'docs' / 'architecture-file-inventory-2026-10-14.json'
destination.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({'files': len(inventory), 'python_files': sum(item['path'].endswith('.py') for item in inventory),
                  'test_methods': sum(len(item.get('tests', [])) for item in inventory),
                  'by_area': dict(Counter(item['path'].split('/')[0] for item in inventory)),
                  'empty_scaffolds': [item['path'] for item in inventory if item['lines'] == 0]}, indent=2))
