# Portfolio Monitor — NVDA / TSM / PLTR

Automated portfolio monitor for a concentrated AI infrastructure thesis.
Zero cost. No server. Runs entirely on GitHub Actions.

---

## The Investment Thesis

This portfolio is a concentrated bet on **AI infrastructure dominance for the next 1–3 years**.

The core belief: the current AI stack — GPU clusters (NVDA), advanced semiconductor foundry (TSM), and AI-native software platforms (PLTR) — will remain the dominant paradigm through at least 2027. The market is still in the early innings of a multi-year CapEx supercycle driven by hyperscaler demand for compute.

**Portfolio construction:** 100% concentrated in three positions. No diversification. The rationale is that diversification into unrelated assets would dilute the thesis, not reduce risk in any meaningful way given the time horizon.

**Exit rule:** Price alone is never a reason to sell. Exit is triggered when the thesis breaks — specific fundamental thresholds are breached, or a genuine paradigm shift in computing architecture becomes evident.

---

## Per-Company Thesis

### NVIDIA (NVDA)
**Why own it:** NVDA is the only company with a full-stack AI platform — silicon (H100/B200), software (CUDA ecosystem), networking (InfiniBand), and enterprise frameworks. The CUDA moat is 15+ years deep and represents a switching cost that neither AMD, Intel, nor custom silicon (TPUs, Trainium) has meaningfully eroded. Data Center revenue is the single most important line item.

**Thesis confirmed by:**
| Metric | Minimum threshold |
|--------|-------------------|
| Gross Margin | ≥ 65% |
| Data Center Revenue Growth YoY | ≥ 20% |
| Operating Margin | ≥ 50% |

**Thesis breaks if:**
- Gross margin collapses to <65% (signals Blackwell yields or competition issues)
- Data Center growth decelerates below 20% YoY for two consecutive quarters
- Any hyperscaler meaningfully reduces GPU orders YoY while maintaining compute capacity

**Key indicator to watch:** Hyperscaler CapEx guidance (MSFT, GOOG, AMZN, META earnings all matter more than NVDA's own earnings for forward signal).

---

### TSMC (TSM)
**Why own it:** TSMC is a structural monopoly. No other foundry on earth can manufacture sub-3nm chips at scale. Without TSMC there is no NVDA Blackwell, no Apple Silicon, no advanced AI chip from any hyperscaler. The geopolitical risk is real but binary — and the global dependency on Taiwanese production makes it a deterrent, not just a risk.

**Thesis confirmed by:**
| Metric | Minimum threshold |
|--------|-------------------|
| Gross Margin | ≥ 53% |
| Factory Utilization | ≥ 80% |
| Advanced Nodes (<5nm) Revenue Growth YoY | ≥ 25% |

**Thesis breaks if:**
- Factory utilization falls below 80% (signals demand destruction, not just inventory correction)
- Advanced node revenue growth falls below 25% YoY for two quarters
- Intel Foundry, Samsung, or a new entrant demonstrates credible advanced node yield at scale

**Key risk:** Taiwan Strait geopolitics. This is a binary risk — unhedgeable at the retail level. Position sizing reflects this.

---

### Palantir (PLTR)
**Why own it:** PLTR is the only enterprise AI software company with (1) real government contracts at mission-critical scale, (2) a commercial business growing >50% YoY, and (3) a platform (AIP) built specifically for AI-native workflows rather than bolted on. It is the software layer on top of the AI hardware buildout that NVDA and TSM enable.

**Thesis confirmed by:**
| Metric | Threshold |
|--------|-----------|
| US Commercial Revenue Growth YoY | ≥ 35% |
| Net Revenue Retention | ≥ 115% |
| SBC as % of Revenue | ≤ 20% (declining trend) |
| Operating Margin | ≥ 20% |

**Thesis breaks if:**
- US commercial growth decelerates below 35% YoY (signals AIP is not penetrating enterprise)
- NRR falls below 115% (signals customers are not expanding usage)
- SBC trend reverses upward (signals return to pre-profitability culture)

---

## Paradigm Shift Monitoring

Beyond per-company fundamentals, the system actively monitors **five structural risks** that could invalidate the entire thesis regardless of individual company metrics:

| Signal | What would break the thesis |
|--------|----------------------------|
| **Neuromorphic Computing** | Benchmark showing >10x energy efficiency vs GPU at scale |
| **Optical / Photonic Computing** | Photonic chip running LLM inference at real cost advantage vs GPU |
| **Alternative Architectures** | Non-transformer model matching GPT-4 class quality at <10% of compute |
| **Hyperscaler CapEx Reversal** | Any hyperscaler cuts GPU orders YoY while compute capacity grows |
| **Energy Constraints** | Regulation limiting AI data center power consumption in major markets |

The weekly report includes a **paradigm status** section (VERDE / AMARILLO / ROJO) based on Claude's analysis of recent news against these signals.

---

## How It Works

```
GitHub Actions (cron)
       │
       ▼
get_market_data()          ← yfinance: prices, P/E, 52w high/low
       │
       ▼
evaluar_alertas()          ← price alerts: stop loss, take profit, 1d drop, earnings proximity
       │
       ▼
evaluar_tesis()            ← fundamental check: tesis.json vs TESIS_UMBRALES thresholds
       │
       ▼
analizar_cambio_paradigma()  ← Claude (Sonnet): paradigm shift signals from news headlines
       │
       ▼
generar_analisis_claude()  ← Claude (Sonnet): weekly analysis, signal (MANTENER/VIGILAR/REVISAR)
       │
       ▼
enviar_email()             ← Gmail SMTP SSL: HTML report to inbox
```

**All logic lives in a single file: `monitor.py`**
**Fundamental data lives in: `tesis.json`** — updated manually after each earnings

### Run modes

| Mode | When | What it sends |
|------|------|---------------|
| `diario` | Weekdays 19:00 ARG | Email only if CRÍTICA or ALTA alerts exist |
| `semanal` | Mondays 09:00 ARG | Full HTML report always sent |

### Alert levels

| Level | Trigger |
|-------|---------|
| 🔴 CRÍTICA | Stop loss hit (NVDA: -25%, TSM: -20%, PLTR: -30%) |
| 🟠 ALTA | Take profit hit · Single day drop >5% |
| 🔵 MEDIA | Price within 10% of 52-week low |
| ⚪ INFO | Earnings in <7 days |

### Weekly report contents

- Executive summary (Claude-generated)
- Per-company signal: **MANTENER** / **VIGILAR** / **REVISAR**
- Fundamental thesis status per company (TESIS_OK / TESIS_EN_RIESGO / TESIS_ROTA)
- Relevant news analysis
- Earnings calendar (next 30 days)
- Paradigm shift monitoring status

---

## Stack

- **Python 3.11** — single file, minimal dependencies
- **yfinance** — market data (free)
- **feedparser** — Yahoo Finance RSS for news (free)
- **anthropic** — Claude Sonnet for weekly AI analysis
- **Gmail SMTP** — email delivery (free with App Password)
- **GitHub Actions** — scheduling and execution (free tier)

**Total running cost: ~$0.02/week** (Claude API calls for weekly report only)

---

## Setup

### 1. Fork or clone this repo

```bash
git clone https://github.com/santigiamp/portfolio-monitor.git
cd portfolio-monitor
pip install -r requirements.txt
```

### 2. Gmail App Password

1. Go to [myaccount.google.com](https://myaccount.google.com)
2. Security → 2-Step Verification (must be active)
3. Security → App passwords
4. Create one named "Portfolio Monitor"
5. Save the 16-character password

### 3. Configure GitHub Secrets

In your repo: **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Value |
|--------|-------|
| `NVDA_PRECIO_ENTRADA` | Your NVDA entry price in USD |
| `TSM_PRECIO_ENTRADA` | Your TSM entry price in USD |
| `PLTR_PRECIO_ENTRADA` | Your PLTR entry price in USD |
| `EMAIL_FROM` | your_account@gmail.com |
| `EMAIL_TO` | where_you_want_alerts@gmail.com |
| `GMAIL_APP_PASSWORD` | The 16-char app password |
| `ANTHROPIC_API_KEY` | Your Anthropic API key (for weekly Claude analysis) |

### 4. Adapt to your own portfolio

1. Edit `TICKERS` in `monitor.py` — change symbols, entry prices, stop/take-profit percentages
2. Edit `TESIS_UMBRALES` — adjust fundamental thresholds to match your thesis
3. Edit `EARNINGS_CALENDAR` — update with actual earnings dates each quarter
4. Edit `tesis.json` — enter actual fundamental metrics after each earnings report
5. Edit `PARADIGMA_SEÑALES` — customize which paradigm shifts you're watching

### 5. Run locally

```bash
# Daily alerts mode
python monitor.py diario

# Weekly report mode
python monitor.py semanal
```

---

## Quarterly Maintenance

After each earnings cycle:

1. **Update `tesis.json`** with actual reported metrics (gross margin, growth rates, etc.)
2. **Update `EARNINGS_CALENDAR`** in `monitor.py` with next quarter dates
3. **Update entry prices** in GitHub Secrets if you averaged down/up
4. **Review thresholds** in `TESIS_UMBRALES` — adjust if thesis has evolved

The system will flag when `tesis.json` is stale (>14 days after earnings without update).

---

## Why this exists

I wanted a system that distinguishes between two very different types of risk:

1. **Price risk** — the stock goes down. Managed with stop loss levels. Not necessarily a reason to sell if the thesis is intact.
2. **Thesis risk** — the fundamental reason for owning the stock breaks. This is the actual reason to sell.

Most retail portfolio tools alert on price. This one alerts on both — and treats them differently. Price alerts are tactical. Thesis alerts are strategic.

The weekly AI-generated report forces a structured review of whether the original investment rationale still holds, using current data and news.

---

*Automated report. Not financial advice.*
