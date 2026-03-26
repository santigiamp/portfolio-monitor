# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Serverless portfolio monitor for a concentrated AI infrastructure thesis (NVDA, TSM, PLTR).
Runs entirely on GitHub Actions (zero cost). Two modes:
- **Daily** (weekdays 19:00 ARG): fetches market data via `yfinance`, evaluates price alerts, sends email only if CRÍTICA or ALTA alerts exist.
- **Weekly** (Mondays 09:00 ARG): always sends a full HTML report with Claude-generated analysis, thesis evaluation, paradigm shift monitoring, and earnings calendar.

## Running locally

```bash
pip install -r requirements.txt

# Daily alerts mode
python monitor.py diario

# Weekly report mode
python monitor.py semanal
```

Required environment variables (or set defaults in the `config` class):
- `NVDA_PRECIO_ENTRADA`, `TSM_PRECIO_ENTRADA`, `PLTR_PRECIO_ENTRADA` — entry prices in USD
- `EMAIL_FROM`, `EMAIL_TO`, `GMAIL_APP_PASSWORD` — Gmail credentials
- `ANTHROPIC_API_KEY` — for Claude analysis in weekly mode

## Architecture

All logic lives in a single file: `monitor.py`. Fundamental data in `tesis.json`.

**Data flow:**
1. `get_market_data()` — fetches price history + fundamentals via `yf.Tickers`
2. `evaluar_alertas(data)` — price alerts: stop loss, take profit, 1-day drop, 52w proximity, earnings proximity
3. `evaluar_tesis(tesis_data)` — compares `tesis.json` metrics against `TESIS_UMBRALES` thresholds → TESIS_OK / TESIS_EN_RIESGO / TESIS_ROTA
4. `analizar_cambio_paradigma(noticias)` — Claude (Sonnet): evaluates paradigm shift signals from news headlines → VERDE / AMARILLO / ROJO
5. `generar_analisis_claude(data, noticias, tesis_resultados)` — Claude (Sonnet): full weekly analysis, per-company signal (MANTENER / VIGILAR / REVISAR)
6. `generar_html_alerta()` / `generar_html_informe_semanal()` — builds HTML email bodies
7. `enviar_email()` — sends via Gmail SMTP SSL (port 465)

**Alert levels:** `CRITICA` → `ALTA` → `MEDIA` → `INFO`

**Ticker config** (`TICKERS` dict): each entry holds `precio_entrada`, `stop_loss_pct`, `take_profit_pct`, and ticker-specific fundamental thresholds.

**`EARNINGS_CALENDAR`**: hardcoded dates — update each quarter.

**`TESIS_UMBRALES`**: per-company fundamental thresholds. Evaluated against `tesis.json`.

**`PARADIGMA_SEÑALES`**: five structural risks monitored weekly (neuromorphic, optical computing, alternative architectures, hyperscaler CapEx reversal, energy constraints).

## Rate limit handling

The weekly mode makes two sequential Claude API calls:
1. `analizar_cambio_paradigma()` — ~1k tokens in/out
2. `generar_analisis_claude()` — larger prompt with market data + news

A 62-second sleep is inserted between calls to respect the 30k input tokens/minute rate limit.
Both calls have retry logic: if RateLimitError on first attempt, wait 62s and retry once.
`analizar_cambio_paradigma` does NOT use web_search — it uses already-fetched news to avoid variable token injection from search results.

## tesis.json

Updated manually after each earnings report. Structure:
```json
{
  "TICKER": {
    "ultima_actualizacion": "YYYY-MM-DD",
    "periodo": "FY20XX-QX",
    "metricas": { ... },
    "notas": "..."
  }
}
```
The system alerts when `tesis.json` is stale (>120 days since last update, or not updated within 14 days of earnings).

## GitHub Actions deployment

The workflow (`.github/workflows/monitor.yml`) uses three cron schedules:
- `0 22 * * 2-5` — daily alerts Tue–Fri
- `0 12 * * 1` — weekly report Monday
- `0 23 * * 1` — daily alerts Monday (after weekly report)

Supports manual `workflow_dispatch` with mode selection (diario / semanal / ambos).
All secrets injected as env vars.

## Quarterly maintenance

1. Update `EARNINGS_CALENDAR` dates in `monitor.py`
2. Update `tesis.json` with actual reported metrics after earnings
3. Update entry prices in GitHub Secrets if position was averaged
4. Adjust `stop_loss_pct` / `take_profit_pct` / `TESIS_UMBRALES` per ticker as thesis evolves
