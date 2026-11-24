# Launch and discovery checklist

Do not announce an installable product before it is installable, or imply live trading performance from fixture tests.

## Repository metadata (maintainer settings)

- Description: IBKR Portfolio Analyzer — local-first read-only multi-account portfolio analytics and risk dashboard.
- Suggested topics: ibkr, interactive-brokers, portfolio-tracker, portfolio-management, personal-finance, investment, tauri, nextjs, fastapi, dashboard, local-first.
- Download social-preview.png from a successful Public fixture demo workflow and upload it in repository Settings → Social preview. The artifact also includes demo-screenshot.png, a browser capture of the fixture report.
- Enable private vulnerability reporting, and consider Discussions when moderation capacity exists.
- Set the homepage only after an actual verified deployment.
- Pin the three related repositories on the owner profile.

## Distribution

Focus on IBKR users, local-first software and portfolio-management communities. Lead with a working demo and signed installer once available.

Follow community self-promotion policies. Avoid automated posting, bought stars, vote solicitation and claims not backed by evidence. Use public synthetic examples, not real brokerage data.

## Measure

Record unique visitors, clones, stars, forks and issue/contributor activity weekly. GitHub traffic data has a limited retention window. Treat conversion estimates as hypotheses until measured.

## Optional zero-install demo deployment

After the launch PR passes checks and is merged, enable GitHub Pages with GitHub Actions as the source in Settings. Manually run **Publish synthetic demo to GitHub Pages** on main. It generates only a static fixture report and never deploys the live application or broker/API integration. Verify the published URL and content before adding a Live Demo link or setting it as the homepage. Do not enable Pages for personal financial data.
