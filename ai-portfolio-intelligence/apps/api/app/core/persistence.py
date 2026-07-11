from __future__ import annotations

import os


def update_env_file(updates: dict[str, str]) -> None:
    import sys
    if "pytest" in sys.modules:
        return
    # Point env_path to apps/api/.env
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
    existing: dict[str, str] = {}
    
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines:
            if "=" in line and not line.strip().startswith("#"):
                parts = line.split("=", 1)
                existing[parts[0].strip()] = parts[1].strip()

    # Apply updates
    for key, val in updates.items():
        existing[key] = val

    # Write back to .env
    with open(env_path, "w", encoding="utf-8") as f:
        for key, val in sorted(existing.items()):
            f.write(f"{key}={val}\n")
