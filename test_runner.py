#!/usr/bin/env python3
"""
Test runner for Phase B1 scripts.

Tests each data fetching script individually with real APIs.
Validates output against JSON schemas.
"""

import json
import os
import sys
from pathlib import Path

import jsonschema


def load_schema(schema_name: str) -> dict:
    """Load a JSON schema file."""
    schema_path = f"backend/schemas/{schema_name}"
    with open(schema_path, "r") as f:
        return json.load(f)


def validate_against_schema(data: dict, schema: dict, name: str) -> bool:
    """Validate data against a JSON schema."""
    try:
        jsonschema.validate(instance=data, schema=schema)
        print(f"✅ {name} validation: PASSED")
        return True
    except jsonschema.ValidationError as e:
        print(f"❌ {name} validation: FAILED")
        print(f"   Error: {e.message}")
        print(f"   Path: {' -> '.join(str(p) for p in e.path)}")
        return False


def test_script(script_name: str, output_file: str, schema_file: str) -> bool:
    """Test a single script."""
    print(f"\n{'='*60}")
    print(f"Testing: {script_name}")
    print('='*60)

    # Run the script
    script_path = f"backend/scripts/{script_name}"
    print(f"Running: python {script_path}")

    exit_code = os.system(f"python {script_path}")

    if exit_code == 0:
        print(f"✅ Script execution: SUCCESS (exit code 0)")
    elif exit_code == 256:  # exit(1) in Python
        print(f"⚠️  Script execution: PARTIAL (exit code 1)")
    else:
        print(f"❌ Script execution: FAILED (exit code {exit_code})")
        return False

    # Check if output file was created
    if not os.path.exists(output_file):
        print(f"❌ Output file not created: {output_file}")
        return False

    print(f"✅ Output file created: {output_file}")

    # Load and validate output
    try:
        with open(output_file, "r") as f:
            output_data = json.load(f)

        # Check basic structure
        print(f"   Output keys: {list(output_data.keys())}")

        # Validate against schema if provided
        if schema_file:
            schema = load_schema(schema_file)
            is_valid = validate_against_schema(output_data, schema, script_name)
            if not is_valid:
                return False

        return True

    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON output: {e}")
        return False
    except Exception as e:
        print(f"❌ Validation error: {e}")
        return False


def main():
    """Run all tests."""
    print("="*60)
    print("Phase B1 Script Testing")
    print("="*60)

    # Check if required environment variables are set
    print("\nChecking environment variables...")
    required_vars = {
        "FRED_API_KEY": os.getenv("FRED_API_KEY"),
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID"),
    }

    missing_vars = [var for var, value in required_vars.items() if not value]
    if missing_vars:
        print(f"⚠️  Warning: Missing environment variables: {', '.join(missing_vars)}")
        print("   Some tests may fail without proper credentials")
    else:
        print("✅ All required environment variables are set")

    # Create data directory if it doesn't exist
    os.makedirs("data", exist_ok=True)

    # Test each script
    tests = [
        {
            "name": "fetch_cot.py",
            "output": "data/cot-latest.json",
            "schema": "cot-report.schema.json",
        },
        {
            "name": "fetch_macro.py",
            "output": "data/macro-latest.json",
            "schema": "macro-report.schema.json",
        },
        {
            "name": "fetch_cross_asset.py",
            "output": "data/cross-asset-latest.json",
            "schema": "cross-asset-report.schema.json",
        },
        {
            "name": "fetch_calendar.py",
            "output": "data/calendar-latest.json",
            "schema": None,  # No schema defined yet
        },
    ]

    results = {}
    for test in tests:
        try:
            success = test_script(test["name"], test["output"], test["schema"])
            results[test["name"]] = success
        except Exception as e:
            print(f"❌ Test crashed: {e}")
            results[test["name"]] = False

    # Print summary
    print(f"\n{'='*60}")
    print("Test Summary")
    print('='*60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for script, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {script}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Ready for GitHub Actions pipeline.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please fix issues before running pipeline.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
