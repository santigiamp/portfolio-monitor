# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Serverless portfolio monitor for NVDA, TSM, and PLTR. Runs entirely on GitHub Actions (zero cost). Two modes:
- **Daily** (weekdays 19:00 ARG): fetches market data via `yfinance`, evaluates alerts, sends email only if CRÍTICA or ALTA alerts exist.
- **Weekly** (Mondays 09:00 ARG): always sends a full HTML report with position status, earnings calendar, and key indicators.

## Running locally

```bash
pip install yfinance

# Daily alerts mode
python monitor.py diario

# Weekly report mode
python monitor.py semanal
```

Required environment variables (or set defaults in the `config` class):
- `NVDA_PRECIO_ENTRADA`, `TSM_PRECIO_ENTRADA`, `PLTR_PRECIO_ENTRADA` — entry prices in USD
- `EMAIL_FROM`, `EMAIL_TO`, `GMAIL_APP_PASSWORD` — Gmail credentials

## Architecture

All logic lives in a single file: `monitor.py`.

**Data flow:**
1. `get_market_data()` — fetches price history + fundamentals via `yf.Tickers`
2. `evaluar_alertas(data)` — applies per-ticker thresholds (stop loss, take profit, 1-day drop, 52-week proximity, earnings proximity)
3. `generar_html_alerta()` / `generar_html_informe_semanal()` — builds HTML email bodies
4. `enviar_email()` — sends via Gmail SMTP SSL (port 465)

**Alert levels:** `CRITICA` → `ALTA` → `MEDIA` → `INFO`

**Ticker config** (`TICKERS` dict): each entry holds `precio_entrada`, `stop_loss_pct`, `take_profit_pct`, and ticker-specific fundamental thresholds.

**`EARNINGS_CALENDAR`**: hardcoded dates — update each quarter.

## GitHub Actions deployment

The workflow (`.github/workflows/monitor.yml`) uses two cron schedules and supports manual `workflow_dispatch`. All secrets are injected as env vars. On manual trigger, both `diario` and `semanal` modes run.

## Quarterly maintenance

1. Update `EARNINGS_CALENDAR` dates in `monitor.py`
2. Update entry prices in GitHub Secrets if position was averaged
3. Adjust `stop_loss_pct` / `take_profit_pct` per ticker as thesis evolves
