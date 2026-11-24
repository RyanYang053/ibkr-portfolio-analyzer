# Platform and capability matrix

| Surface | Current support | Verification required |
| --- | --- | --- |
| Fixture report | Source checkout, Python | Public demo workflow |
| macOS desktop | Tauri build and DMG workflow | Signed/notarized installer and launch smoke |
| Windows desktop | Tauri build and NSIS workflow | Code signing and launch smoke |
| Linux desktop | Tauri build artifacts | Packaging and distro launch smoke |
| Multi-account analytics | Mock adapter and read-only broker architecture | Reconcile authorized account statements |
| Market and AI research | Optional providers | Freshness, credentials, data flow and usage rights |
| Live order submission | Not implemented | Out of scope |

See [release and signing runbook](../ai-portfolio-intelligence/docs/RELEASE_AND_SIGNING.md), [product scope](../ai-portfolio-intelligence/docs/PRODUCT_SCOPE.md) and [CI](https://github.com/RyanYang053/ibkr-portfolio-analyzer/actions). A successful build does not constitute a signed production release or investment-performance certification.
