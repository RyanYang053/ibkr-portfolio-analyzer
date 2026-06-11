# Security

Security requirements implemented or scaffolded in the MVP:

- Password hashing through Passlib
- JWT issuance for login
- Pydantic request validation
- CORS restricted to local frontend origin by default
- SQLAlchemy models for ORM-based data access
- No IBKR username, password, 2FA code, or raw account number storage
- Mock account number exists only in explicit demo mode and tests
- Audit log model and mock audit endpoint
- Broker permissions module with explicit read-only action allowlist

Future live IBKR work must not automate unsafe login scraping, bypass 2FA, or persist plaintext session cookies.
