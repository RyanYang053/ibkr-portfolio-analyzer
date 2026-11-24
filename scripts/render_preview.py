"""Capture the real fixture report and rasterize repository artwork.

Run only against the generated synthetic report, not personal financial data.
Requires Playwright and an installed Chromium browser.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = args.report.resolve(strict=True)
    if "SYNTHETIC RESEARCH DEMO" not in report.read_text(encoding="utf-8"):
        raise SystemExit("Expected the synthetic demo, not a personal portfolio report")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
        # The previews are local static files; deny all external network requests.
        page.route("http://**/*", lambda route: route.abort())
        page.route("https://**/*", lambda route: route.abort())
        page.goto(report.as_uri(), wait_until="load")
        assert page.get_by_text("SYNTHETIC RESEARCH DEMO", exact=True).count() == 1
        page.screenshot(path=str(args.output_dir / "demo-screenshot.png"), animations="disabled")
        page.set_viewport_size({"width": 1280, "height": 640})
        svg = (ROOT / "docs" / "assets" / "banner.svg").read_text(encoding="utf-8")
        page.set_content('<html><body style="margin:0;background:#0b1423;display:grid;place-items:center;height:100vh">'+svg+'</body></html>')
        page.screenshot(path=str(args.output_dir / "social-preview.png"), animations="disabled")
        browser.close()

if __name__ == "__main__":
    main()
