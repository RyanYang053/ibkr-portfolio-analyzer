import json
import subprocess
import sys
from pathlib import Path


def test_openapi_schema_exports_required_paths():
    api_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(api_root / "scripts" / "check_openapi_schema.py")],
        cwd=api_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    schema = json.loads((api_root / "openapi.json").read_text(encoding="utf-8"))
    assert "Position" in schema["components"]["schemas"]
    position = schema["components"]["schemas"]["Position"]
    assert "con_id" in position["properties"]
