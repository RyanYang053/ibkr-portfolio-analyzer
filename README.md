# IBKR Portfolio Analyzer

A read-only portfolio intelligence and decision-support dashboard integrated with the Interactive Brokers (IBKR) Gateway. This tool aggregates multi-account holdings, tracks historical PnL, performs connection diagnostics, and provides AI-powered stock and portfolio analysis.

> **Important**: This application is strictly read-only. It has no order execution capabilities and cannot place, modify, or cancel trades.

---

## Key Features

- **Multi-Account Consolidated Holdings**: Aggregates and converts positions across multiple Interactive Brokers accounts into a single view, supporting both USD and CAD balances.
- **Connection Diagnostics**: Monitor connection health and socket latency to the IBKR Gateway or Trader Workstation (TWS).
- **Historical PnL Snapshots**: A background scheduler automatically records daily portfolio valuations and position changes, storing them locally for trend analysis.
- **AI Research Assistant**: Generate stock analyses and portfolio summary memos using Google Gemini models, with a deterministic local fallback if no API key is provided.
- **Interactive Chatbot**: Ask questions about portfolio allocation, sector concentration, or individual stock metrics with persistent session history.

## Project Structure

This monorepo is split into the frontend, backend, and infrastructure configuration:

* `apps/api/` - FastAPI backend application.
* `apps/web/` - Next.js frontend dashboard built with TypeScript and Tailwind CSS.
* `infra/` - Docker Compose file for Postgres, Redis, and app containers.

---

## Local Setup

### Prerequisites

- **Python**: 3.10 or higher.
- **Node.js**: 18.x or higher.
- **IBKR Gateway or Trader Workstation (TWS)**: Running locally and configured to allow API connections (default ports are `4001`/`4002` or `7496`/`7497`).

### 1. Set Up the Backend API

1. Navigate to the API directory:
   ```bash
   cd ai-portfolio-intelligence/apps/api
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Configure environment variables in a `.env` file (or export them):
   ```ini
   # API Configuration
   JWT_SECRET=your_jwt_secret_here
   DATABASE_URL=postgresql+psycopg://portfolio:portfolio@localhost:5432/portfolio
   
   # IBKR Gateway Configuration
   BROKER_MODE=ibkr_readonly
   IBKR_HOST=127.0.0.1
   IBKR_PORT=4001
   IBKR_CLIENT_ID=10
   
   # AI Configuration (Optional)
   GEMINI_API_KEY=your_gemini_api_key_here
   GEMINI_MODEL=gemini-2.5-flash
   ```

4. Run the development server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

### 2. Set Up the Next.js Frontend

1. Navigate to the web directory:
   ```bash
   cd ai-portfolio-intelligence/apps/web
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start the Next.js development server:
   ```bash
   npm run dev
   ```
   Open [http://localhost:3000](http://localhost:3000) to view the dashboard.

### 3. Run via Docker Compose (Alternative)

To spin up PostgreSQL, Redis, the API, and the Web UI together:

1. Navigate to the infra directory:
   ```bash
   cd ai-portfolio-intelligence/infra
   ```

2. Run the compose services:
   ```bash
   GEMINI_API_KEY="your_api_key_here" docker compose up --build
   ```

---

## Testing & Verification

Run the test suite on the backend:
```bash
cd ai-portfolio-intelligence
npm run api:test
```

Verify the production build of the frontend:
```bash
cd ai-portfolio-intelligence/apps/web
npm run build
```

---

## Mock Demo Mode

If you do not have an active IBKR Gateway connection running, you can run the application with mock data to preview features:

1. Set `BROKER_MODE` to `mock_ibkr_readonly` in your `.env` file.
2. Restart the FastAPI server. The dashboard will show pre-populated positions and history.

---

## Disclaimer

This software is for educational and research purposes only. It is not financial advice. No trading or order execution capability is implemented. The user is responsible for reviewing and confirming all data before making investment decisions.
