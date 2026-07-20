from pathlib import Path

from app.core.product_scope import CLAIM_SCAN_ALLOWLIST, PROHIBITED_CLAIMS

PUBLIC_ROOTS = (
    Path("app/api"),
    Path("../../web/app"),
    Path("../../web/components"),
)


def test_public_copy_contains_no_prohibited_claims() -> None:
    violations: list[str] = []

    for root in PUBLIC_ROOTS:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx", ".md"}:
                continue

            rel = path.as_posix()
            if any(rel.endswith(allowed) or allowed in rel for allowed in CLAIM_SCAN_ALLOWLIST):
                continue

            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for claim in PROHIBITED_CLAIMS:
                if claim.lower() in text:
                    # Allow explicit negation / disclaimer phrasing.
                    if f"not {claim.lower()}" in text or f"no {claim.lower()}" in text:
                        continue
                    if "does not" in text and claim.lower() in text:
                        continue
                    violations.append(f"{path}: {claim}")

    assert not violations, "\n".join(violations)
