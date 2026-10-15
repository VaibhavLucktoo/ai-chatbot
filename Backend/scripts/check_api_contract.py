"""Compare the refactored API with the saved pre-refactor contract."""

import argparse
from collections import Counter
import importlib
import json
from pathlib import Path
import pkgutil

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
BASELINE = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "api_contract_before_refactor.json"
)


def operations(schema):
    return {
        (path, method): operation
        for path, item in schema["paths"].items()
        for method, operation in item.items()
        if method in HTTP_METHODS
    }


def check_contract(before, after, *, documentation_updates=False):
    original, current = operations(before), operations(after)
    assert len(current) == 39, f"Expected 39 operations, found {len(current)}"
    assert original.keys() == current.keys(), "Route paths or HTTP methods changed"
    ids = Counter(operation["operationId"] for operation in current.values())
    assert len(ids) == len(current), "Duplicate OpenAPI operation IDs"
    for key, previous in original.items():
        actual = current[key]
        for field in (
            "operationId",
            "parameters",
            "requestBody",
            "security",
            "summary",
            "description",
        ):
            assert previous.get(field) == actual.get(field), f"{key}: {field} changed"
        expected_tags = (
            [tag.lower() for tag in previous.get("tags", [])]
            if documentation_updates
            else previous.get("tags", [])
        )
        assert expected_tags == actual.get("tags", []), (
            f"{key}: tags changed unexpectedly"
        )
        assert previous["responses"].keys() == actual["responses"].keys(), (
            f"{key}: response status codes changed"
        )
        for status, response in previous["responses"].items():
            replacement = actual["responses"][status]
            if documentation_updates and status.startswith("2"):
                response = json.loads(json.dumps(response))
                original_json = response.get("content", {}).get("application/json", {})
                new_json = replacement.get("content", {}).get("application/json", {})
                if original_json.get("schema") == {} and new_json.get("schema"):
                    original_json["schema"] = new_json["schema"]
            assert response == replacement, (
                f"{key}: response {status} changed beyond added typing"
            )
    for name, definition in before.get("components", {}).get("schemas", {}).items():
        assert definition == after["components"]["schemas"].get(name), (
            f"Existing schema changed: {name}"
        )
    return len(current), len(ids)


def check_imports():
    import app

    modules = sorted(
        item.name for item in pkgutil.walk_packages(app.__path__, prefix="app.")
    )
    for name in modules:
        importlib.import_module(name)
    return len(modules)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Disallow even the planned tag/response typing changes.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    from app.main import create_app

    schema = create_app().openapi()
    count, unique = check_contract(
        json.loads(args.baseline.read_text(encoding="utf-8")),
        schema,
        documentation_updates=not args.strict,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"OpenAPI operations: {count}")
    print(f"Unique operation IDs: {unique}")
    print(f"Duplicate operation IDs: {count - unique}")
    print(
        "Paths, methods, parameters, request schemas, status codes and existing response schemas: unchanged"
    )
    print("Tags: consistent" if not args.strict else "Tags: unchanged")
    print(f"Application modules imported successfully: {check_imports()}")


if __name__ == "__main__":
    main()
