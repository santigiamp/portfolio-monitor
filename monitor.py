"""
Portfolio Monitor — NVDA, TSM, PLTR
Corre diario (alertas de precio) y semanal (informe completo con análisis IA).
"""

import yfinance as yf
import feedparser
import smtplib
import json
import traceback
import anthropic
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, date, timedelta
import os


class config:
    NVDA_PRECIO_ENTRADA = float(os.environ.get("NVDA_PRECIO_ENTRADA", 174.39))
    TSM_PRECIO_ENTRADA  = float(os.environ.get("TSM_PRECIO_ENTRADA", 183.00))
    PLTR_PRECIO_ENTRADA = float(os.environ.get("PLTR_PRECIO_ENTRADA", 148.82))
    EMAIL_FROM          = os.environ.get("EMAIL_FROM", "")
    EMAIL_TO            = os.environ.get("EMAIL_TO", "")
    GMAIL_APP_PASSWORD  = os.environ.get("GMAIL_APP_PASSWORD", "")
    ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")


TICKERS = {
    "NVDA": {
        "nombre": "NVIDIA",
        "precio_entrada": config.NVDA_PRECIO_ENTRADA,
        "stop_loss_pct": -0.25,
        "take_profit_pct": 0.60,
        "gross_margin_min": 65.0,
        "data_center_growth_min": 20,
        "pe_referencia": "35x = razonable, >60x = caro, <20x = oportunidad",
    },
    "TSM": {
        "nombre": "TSMC",
        "precio_entrada": config.TSM_PRECIO_ENTRADA,
        "stop_loss_pct": -0.20,
        "take_profit_pct": 0.40,
        "utilization_min": 80,
        "pe_referencia": "23x = histórico, >35x = caro",
    },
    "PLTR": {
        "nombre": "Palantir",
        "precio_entrada": config.PLTR_PRECIO_ENTRADA,
        "stop_loss_pct": -0.30,
        "take_profit_pct": 1.00,
        "revenue_growth_min": 30,
        "pe_referencia": "PE extremo por naturaleza — evaluar tendencia histórica",
    },
}

# Actualizar cada trimestre
EARNINGS_CALENDAR = {
    "NVDA": "2026-05-28",
    "TSM": "2026-04-17",
    "PLTR": "2026-05-05",
    "MSFT": "2026-04-30",
    "GOOG": "2026-04-29",
    "AMZN": "2026-05-01",
    "META": "2026-04-30",
}

NEWS_TICKERS = ["NVDA", "TSM", "PLTR", "MSFT", "GOOG", "AMZN", "META"]


# ── Datos de mercado ─────────────────────────────────────────────────────────

def get_market_data():
    data = {}
    symbols = list(TICKERS.keys())
    tickers_obj = yf.Tickers(" ".join(symbols))

    for symbol in symbols:
        t = tickers_obj.tickers[symbol]
        hist = t.history(period="10d")
        info = t.info

        precio_actual = float(hist["Close"].iloc[-1])
        precio_ayer = float(hist["Close"].iloc[-2]) if len(hist) > 1 else precio_actual
        cambio_1d = (precio_actual - precio_ayer) / precio_ayer * 100

        # Cambio semanal: ~5 ruedas atrás
        precio_semana = float(hist["Close"].iloc[-min(6, len(hist))]) if len(hist) > 1 else precio_actual
        cambio_semanal = (precio_actual - precio_semana) / precio_semana * 100

        precio_entrada = TICKERS[symbol]["precio_entrada"]
        retorno = (precio_actual - precio_entrada) / precio_entrada * 100

        high_52w = info.get("fiftyTwoWeekHigh", 0) or 0
        dist_52w_high = ((precio_actual - high_52w) / high_52w * 100) if high_52w > 0 else None

        data[symbol] = {
            "precio": round(precio_actual, 2),
            "cambio_1d": round(cambio_1d, 2),
            "cambio_semanal": round(cambio_semanal, 2),
            "retorno_entrada": round(retorno, 2),
            "pe_ratio": info.get("trailingPE") or None,
            "market_cap": info.get("marketCap", 0),
            "volumen": info.get("volume", 0),
            "52w_high": high_52w,
            "52w_low": info.get("fiftyTwoWeekLow", 0) or 0,
            "distancia_52w_high": round(dist_52w_high, 1) if dist_52w_high is not None else None,
        }

    return data


# ── Noticias ─────────────────────────────────────────────────────────────────

def get_news(tickers=None):
    """Trae noticias de los últimos 7 días vía RSS de Yahoo Finance."""
    if tickers is None:
        tickers = NEWS_TICKERS

    noticias = []
    cutoff = datetime.now() - timedelta(days=7)

    for symbol in tickers:
        try:
            url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                # feedparser devuelve published_parsed como time.struct_time UTC
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_dt = datetime(*entry.published_parsed[:6])
                else:
                    pub_dt = datetime.now()

                if pub_dt >= cutoff:
                    noticias.append({
                        "ticker": symbol,
                        "titulo": entry.get("title", ""),
                        "fecha": pub_dt.strftime("%Y-%m-%d"),
                        "url": entry.get("link", ""),
                    })
            print(f"  {symbol}: {len([n for n in noticias if n['ticker']==symbol])} noticias")
        except Exception as e:
            print(f"  Warning: noticias para {symbol}: {e}")

    return noticias


# ── Motor de alertas ─────────────────────────────────────────────────────────

def evaluar_alertas(data):
    alertas = []

    for symbol, cfg in TICKERS.items():
        d = data[symbol]
        precio = d["precio"]

        if d["retorno_entrada"] <= cfg["stop_loss_pct"] * 100:
            alertas.append({
                "nivel": "CRITICA",
                "symbol": symbol,
                "mensaje": f"⚠️ STOP LOSS alcanzado: {d['retorno_entrada']:.1f}% desde entrada. "
                           f"Revisar posición inmediatamente.",
            })
        elif d["retorno_entrada"] >= cfg["take_profit_pct"] * 100:
            alertas.append({
                "nivel": "ALTA",
                "symbol": symbol,
                "mensaje": f"🎯 Take profit alcanzado: +{d['retorno_entrada']:.1f}%. "
                           f"Considerar tomar parcial o revisar stop.",
            })

        dist_max = d.get("distancia_52w_high")
        cambio_sem = d.get("cambio_semanal", 0)
        condicion_a = dist_max is not None and dist_max < -20 and cambio_sem < -8
        retorno = d["retorno_entrada"]
        sl_pct = cfg["stop_loss_pct"] * 100
        margen_sl = retorno - sl_pct
        condicion_b = retorno < 0 and margen_sl < 15
        if condicion_a or condicion_b:
            alertas.append({
                "nivel": "ALTA",
                "symbol": symbol,
                "mensaje": f"⚠️ Condición REVISAR activa: tesis necesita revalidación. "
                           f"Dist. máx 52s: {dist_max:.1f}%, cambio semanal: {cambio_sem:.1f}%, "
                           f"retorno entrada: {retorno:.1f}%.",
            })

        if d["cambio_1d"] <= -5.0:
            alertas.append({
                "nivel": "ALTA",
                "symbol": symbol,
                "mensaje": f"📉 Caída fuerte: {d['cambio_1d']:.1f}% en 1 día. "
                           f"Verificar si hay noticias de fundamentals.",
            })

        if d["52w_low"] > 0:
            distancia_min = (precio - d["52w_low"]) / d["52w_low"] * 100
            if distancia_min < 10:
                alertas.append({
                    "nivel": "MEDIA",
                    "symbol": symbol,
                    "mensaje": f"📊 Precio a {distancia_min:.1f}% del mínimo de 52 semanas. "
                               f"Revisar fundamentals antes de promediar.",
                })

    hoy = date.today()
    for symbol, fecha_str in EARNINGS_CALENDAR.items():
        if symbol not in TICKERS:
            continue
        fecha_earnings = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        dias_restantes = (fecha_earnings - hoy).days
        if 0 <= dias_restantes <= 7:
            alertas.append({
                "nivel": "INFO",
                "symbol": symbol,
                "mensaje": f"📅 Earnings en {dias_restantes} días ({fecha_str}). "
                           f"Alta volatilidad esperada. Revisar posición.",
            })

    return alertas


# ── Análisis con Claude ───────────────────────────────────────────────────────

def generar_analisis_claude(data_mercado, noticias):
    """Llama a la Claude API y devuelve el análisis estructurado como dict."""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # Contexto por empresa
    empresas_ctx = []
    for symbol, cfg in TICKERS.items():
        d = data_mercado[symbol]
        entrada = cfg["precio_entrada"]
        sl_precio = round(entrada * (1 + cfg["stop_loss_pct"]), 2)
        tp_precio = round(entrada * (1 + cfg["take_profit_pct"]), 2)
        empresas_ctx.append({
            "symbol": symbol,
            "nombre": cfg["nombre"],
            "precio_actual": d["precio"],
            "cambio_1d_pct": d["cambio_1d"],
            "cambio_semanal_pct": d["cambio_semanal"],
            "retorno_desde_entrada_pct": d["retorno_entrada"],
            "precio_entrada": entrada,
            "stop_loss_precio": sl_precio,
            "take_profit_precio": tp_precio,
            "pe_ratio": d["pe_ratio"],
            "pe_referencia": cfg["pe_referencia"],
            "distancia_52w_high_pct": d["distancia_52w_high"],
        })

    # Earnings próximos (30 días)
    hoy = date.today()
    earnings_ctx = []
    hyperscalers_proximos = []
    HYPERSCALERS = {"MSFT", "GOOG", "AMZN", "META"}
    for symbol, fecha_str in EARNINGS_CALENDAR.items():
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        dias = (fecha - hoy).days
        if 0 <= dias <= 30:
            earnings_ctx.append({"empresa": symbol, "fecha": fecha_str, "dias_restantes": dias})
        if symbol in HYPERSCALERS and 0 <= dias <= 14:
            hyperscalers_proximos.append({"empresa": symbol, "fecha": fecha_str, "dias_restantes": dias})

    # Noticias agrupadas por ticker
    noticias_por_ticker = {}
    for n in noticias:
        t = n["ticker"]
        noticias_por_ticker.setdefault(t, []).append({
            "titulo": n["titulo"],
            "fecha": n["fecha"],
        })

    prompt = f"""Eres un analista financiero especializado en tecnología y semiconductores.
Analiza el estado de este portafolio y genera un informe semanal estructurado.

CONTEXTO DEL PORTAFOLIO:
- Concentración: 100% en NVDA, TSM, PLTR (sin diversificación externa)
- Horizonte: 1-3 años
- Tolerancia: media
- Objetivo: crecimiento de capital

DATOS DE MERCADO:
{json.dumps(empresas_ctx, ensure_ascii=False, indent=2)}

NOTICIAS ÚLTIMOS 7 DÍAS:
{json.dumps(noticias_por_ticker, ensure_ascii=False, indent=2)}

EARNINGS PRÓXIMOS 30 DÍAS:
{json.dumps(earnings_ctx, ensure_ascii=False, indent=2)}

HYPERSCALERS CON EARNINGS EN LOS PRÓXIMOS 14 DÍAS:
{json.dumps(hyperscalers_proximos, ensure_ascii=False, indent=2)}

INSTRUCCIONES:
- Señal: MANTENER (tesis intacta), VIGILAR (zona de alerta), REVISAR (umbral roto o tesis en
  riesgo). Usar REVISAR automáticamente si se cumplen DOS o más de estas condiciones
  simultáneas: distancia al máximo de 52 semanas > 20% Y cambio semanal < -8%, o retorno
  desde entrada negativo Y precio dentro del 15% del stop loss.
- Análisis: interpretá los números, no los describas. Qué significan para la tesis de largo plazo.
  Si hay earnings en los próximos 14 días para esa empresa, agregá al final del análisis
  un bloque con este formato exacto:

  EARNINGS CHECK — [FECHA]:
  • Métrica 1: [qué número, qué umbral, qué significa si lo supera o no lo alcanza]
  • Métrica 2: [ídem]
  • Métrica 3: [ídem]
  • Si supera consenso: [1 línea]
  • Si decepciona: [1 línea]

  Umbrales por empresa:
  NVDA: gross margin (mínimo 65%), Data Center growth YoY (mínimo 20%),
  guidance de CapEx de hyperscalers en sus propios earnings.
  TSM: utilización de fábricas (mínimo 80%), revenue de nodos avanzados <5nm
  (mínimo 25% YoY), guidance de demanda para H2 del año.
  PLTR: revenue growth comercial US (mínimo 40% YoY), net revenue retention
  (mínimo 115%), SBC como % de revenue (debe seguir bajando del 15%).

  Si no hay earnings próximos para esa empresa, omitir el bloque completamente.

- Bloque HYPERSCALERS para NVDA: si la lista "HYPERSCALERS CON EARNINGS EN LOS PRÓXIMOS
  14 DÍAS" tiene al menos una empresa, agregá al final del análisis de NVDA (después del
  EARNINGS CHECK propio si lo hay) un bloque con este formato exacto:

  EARNINGS CHECK — HYPERSCALERS ([lista de empresas y fechas]):
  • CapEx guidance agregado: [qué número vigilar, qué crecimiento YoY mínimo sostiene la
    demanda de GPUs, qué implicaría una reducción o pausa]
  • Lenguaje sobre AI infrastructure: [señales positivas vs. señales de alerta en el
    commentary de management]
  • Data center revenue mix: [qué porcentaje del revenue total representa el segmento
    cloud/AI, qué dirección indica para la demanda de aceleradores]
  • Mención explícita de NVDA o GPUs: [presencia o ausencia, tono]
  • Si el CapEx guidance supera expectativas: [1 línea de impacto en la tesis de NVDA]
  • Si el CapEx guidance decepciona o hay lenguaje cauteloso: [1 línea de riesgo]

  Si la lista de hyperscalers próximos está vacía, omitir este bloque completamente.

- Noticias: seleccioná solo las relevantes para la tesis (IA, semis, crecimiento cloud,
  contratos gobierno). Ignorá productos consumer y drama de management sin impacto estratégico.
- Tono: analista directo hablando a otro inversor sofisticado. Sin disclaimers dentro del análisis.
- Resumen ejecutivo: ¿qué pasó esta semana?, ¿algo urgente?, ¿estado general?

Respondé ÚNICAMENTE con JSON válido, sin texto adicional:
{{
  "resumen_ejecutivo": "3-4 oraciones",
  "empresas": {{
    "NVDA": {{
      "senal": "MANTENER|VIGILAR|REVISAR",
      "razon_senal": "una oración",
      "analisis": "2-3 párrafos separados por doble salto de línea. Si hay earnings próximos, incluir bloque EARNINGS CHECK al final.",
      "noticias_relevantes": [
        {{"titular": "...", "contexto": "1 línea: por qué importa para el portafolio"}}
      ]
    }},
    "TSM": {{...}},
    "PLTR": {{...}}
  }},
  "calendario_eventos": ["descripción del evento relevante próximo"]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    return json.loads(text)


# ── Generadores de HTML ──────────────────────────────────────────────────────

def generar_html_alerta(alertas, data):
    items_html = ""
    for a in alertas:
        color = {"CRITICA": "#dc2626", "ALTA": "#d97706", "MEDIA": "#2563eb", "INFO": "#6b7280"}
        bg    = {"CRITICA": "#fef2f2", "ALTA": "#fffbeb", "MEDIA": "#eff6ff", "INFO": "#f9fafb"}
        c = color.get(a["nivel"], "#6b7280")
        b = bg.get(a["nivel"], "#f9fafb")
        items_html += f"""
        <div style="background:{b};border-left:4px solid {c};padding:12px 16px;margin:8px 0;border-radius:4px">
            <strong style="color:{c}">[{a['nivel']}] {a['symbol']}</strong><br>
            <span style="color:#374151">{a['mensaje']}</span>
        </div>"""

    precios_html = ""
    for symbol, d in data.items():
        color_ret = "#16a34a" if d["retorno_entrada"] >= 0 else "#dc2626"
        color_1d  = "#16a34a" if d["cambio_1d"] >= 0 else "#dc2626"
        signo     = "+" if d["retorno_entrada"] >= 0 else ""
        signo_1d  = "+" if d["cambio_1d"] >= 0 else ""
        pe_str    = f"{d['pe_ratio']:.0f}x" if d.get("pe_ratio") else "—"
        precios_html += f"""
        <tr>
            <td style="padding:8px 12px;font-weight:600">{symbol}</td>
            <td style="padding:8px 12px">${d['precio']}</td>
            <td style="padding:8px 12px;color:{color_1d}">{signo_1d}{d['cambio_1d']:.1f}%</td>
            <td style="padding:8px 12px;color:{color_ret}">{signo}{d['retorno_entrada']:.1f}%</td>
            <td style="padding:8px 12px">{pe_str}</td>
        </tr>"""

    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#111">
    <h2 style="color:#1e3a5f;border-bottom:2px solid #e5e7eb;padding-bottom:8px">
        🚨 Alertas de Portafolio — {datetime.now().strftime('%d/%m/%Y %H:%M')}
    </h2>
    {items_html}
    <h3 style="color:#374151;margin-top:24px">Resumen de precios</h3>
    <table style="width:100%;border-collapse:collapse;font-size:14px">
        <tr style="background:#f3f4f6;text-align:left">
            <th style="padding:8px 12px">Ticker</th>
            <th style="padding:8px 12px">Precio</th>
            <th style="padding:8px 12px">1D</th>
            <th style="padding:8px 12px">vs Entrada</th>
            <th style="padding:8px 12px">P/E</th>
        </tr>
        {precios_html}
    </table>
    <p style="color:#9ca3af;font-size:11px;margin-top:24px">
        Este informe es automático y no constituye asesoramiento financiero.
    </p>
    </body></html>"""


def generar_html_informe_semanal(data, alertas):
    """Informe semanal con análisis generado por Claude."""
    api_key = config.ANTHROPIC_API_KEY
    print(f"ANTHROPIC_API_KEY configurada: {'sí' if api_key else 'NO — FALTA EL SECRET'} (len={len(api_key)})")

    print("Obteniendo noticias...")
    try:
        noticias = get_news()
        print(f"Noticias obtenidas: {len(noticias)}")
    except Exception as e:
        print(f"Error obteniendo noticias: {e}")
        noticias = []

    print("Generando análisis con Claude...")
    try:
        analisis = generar_analisis_claude(data, noticias)
        print("Análisis Claude generado correctamente.")
    except Exception as e:
        print(f"ERROR en análisis Claude: {e}")
        traceback.print_exc()
        return _generar_html_basico(data, alertas)

    hoy  = datetime.now().strftime("%d/%m/%Y")
    hora = datetime.now().strftime("%H:%M")

    SENAL_CFG = {
        "MANTENER": {"color": "#16a34a", "bg": "#f0fdf4", "icono": "🟢"},
        "VIGILAR":  {"color": "#d97706", "bg": "#fffbeb", "icono": "🟡"},
        "REVISAR":  {"color": "#dc2626", "bg": "#fef2f2", "icono": "🔴"},
    }

    # Bloque 1 — Resumen ejecutivo
    resumen_html = f"""
    <div style="background:#eff6ff;border-left:4px solid #2563eb;border-radius:4px;padding:16px 20px;margin:16px 0">
        <p style="margin:0;font-size:14px;line-height:1.7;color:#1e3a5f">
            {analisis.get('resumen_ejecutivo', '')}
        </p>
    </div>"""

    # Bloques 2+3 — Señal + análisis por empresa
    bloques_empresas = ""
    for symbol in TICKERS:
        d    = data[symbol]
        cfg  = TICKERS[symbol]
        nombre  = cfg["nombre"]
        entrada = cfg["precio_entrada"]
        sl = round(entrada * (1 + cfg["stop_loss_pct"]), 2)
        tp = round(entrada * (1 + cfg["take_profit_pct"]), 2)

        ea     = analisis.get("empresas", {}).get(symbol, {})
        senal  = ea.get("senal", "VIGILAR")
        razon  = ea.get("razon_senal", "")
        texto  = ea.get("analisis", "")
        nots   = ea.get("noticias_relevantes", [])

        sc = SENAL_CFG.get(senal, SENAL_CFG["VIGILAR"])

        color_ret = "#16a34a" if d["retorno_entrada"] >= 0 else "#dc2626"
        signo     = "+" if d["retorno_entrada"] >= 0 else ""
        color_sem = "#16a34a" if d.get("cambio_semanal", 0) >= 0 else "#dc2626"
        signo_sem = "+" if d.get("cambio_semanal", 0) >= 0 else ""
        pe_str    = f"{d['pe_ratio']:.0f}x" if d.get("pe_ratio") else "—"
        dist_str  = f"{d['distancia_52w_high']:.1f}%" if d.get("distancia_52w_high") is not None else "—"

        parrafos = "".join(
            f'<p style="margin:0 0 10px;font-size:13px;line-height:1.7;color:#374151">{p.strip()}</p>'
            for p in texto.split("\n\n") if p.strip()
        )

        noticias_items = ""
        for n in nots[:3]:
            noticias_items += f"""
            <li style="margin:6px 0">
                <strong style="font-size:12px;color:#111">{n.get('titular','')}</strong><br>
                <span style="font-size:11px;color:#6b7280">{n.get('contexto','')}</span>
            </li>"""

        noticias_section = ""
        if noticias_items:
            noticias_section = f"""
            <div style="margin-top:14px;border-top:1px solid #e5e7eb;padding-top:12px">
                <p style="margin:0 0 6px;font-size:11px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:0.5px">Noticias relevantes</p>
                <ul style="margin:0;padding-left:16px">{noticias_items}</ul>
            </div>"""

        bloques_empresas += f"""
        <div style="background:{sc['bg']};border-left:4px solid {sc['color']};border-radius:6px;padding:16px 20px;margin:12px 0">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:4px">
                <div>
                    <h3 style="margin:0;color:#111;font-size:16px">{sc['icono']} {nombre} ({symbol})</h3>
                    <p style="margin:4px 0 0;font-size:12px;color:{sc['color']};font-weight:600">{senal} — {razon}</p>
                </div>
                <div style="text-align:right">
                    <span style="font-size:22px;font-weight:700;color:#111">${d['precio']}</span>
                    <span style="margin-left:8px;font-size:13px;color:{color_sem}">{signo_sem}{d.get('cambio_semanal', 0):.1f}% sem</span>
                </div>
            </div>

            <div style="display:flex;gap:20px;flex-wrap:wrap;padding:10px 0;margin:10px 0;border-top:1px solid {sc['color']}33;border-bottom:1px solid {sc['color']}33">
                <div style="font-size:12px"><span style="color:#9ca3af">vs Entrada</span><br><strong style="color:{color_ret}">{signo}{d['retorno_entrada']:.1f}%</strong></div>
                <div style="font-size:12px"><span style="color:#9ca3af">Stop Loss</span><br><strong>${sl:.2f}</strong></div>
                <div style="font-size:12px"><span style="color:#9ca3af">Take Profit</span><br><strong>${tp:.2f}</strong></div>
                <div style="font-size:12px"><span style="color:#9ca3af">P/E</span><br><strong>{pe_str}</strong></div>
                <div style="font-size:12px"><span style="color:#9ca3af">vs Máx 52s</span><br><strong>{dist_str}</strong></div>
            </div>

            {parrafos}
            {noticias_section}
        </div>"""

    # Bloque 5 — Calendario próximos 30 días
    hoy_dt = date.today()
    cal_rows = ""
    for symbol, fecha_str in EARNINGS_CALENDAR.items():
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        dias  = (fecha - hoy_dt).days
        if 0 <= dias <= 30:
            urgente   = dias <= 7
            color_d   = "#dc2626" if dias <= 7 else "#d97706" if dias <= 14 else "#6b7280"
            prefix    = "⚠️ " if urgente else ""
            bold      = "font-weight:600" if urgente else ""
            cal_rows += f"""
            <tr>
                <td style="padding:6px 12px;font-size:13px;font-weight:600">{prefix}{symbol}</td>
                <td style="padding:6px 12px;font-size:13px">Earnings</td>
                <td style="padding:6px 12px;font-size:13px">{fecha_str}</td>
                <td style="padding:6px 12px;font-size:13px;color:{color_d};{bold}">{dias} días</td>
            </tr>"""

    for evento in analisis.get("calendario_eventos", []):
        cal_rows += f"""
        <tr>
            <td colspan="4" style="padding:6px 12px;font-size:13px;color:#6b7280">📌 {evento}</td>
        </tr>"""

    calendario_html = ""
    if cal_rows:
        calendario_html = f"""
        <h3 style="color:#374151;margin:28px 0 8px;font-size:15px">📅 Próximos 30 días</h3>
        <table style="width:100%;border-collapse:collapse">
            <tr style="background:#f3f4f6">
                <th style="padding:6px 12px;text-align:left;font-size:12px">Empresa</th>
                <th style="padding:6px 12px;text-align:left;font-size:12px">Evento</th>
                <th style="padding:6px 12px;text-align:left;font-size:12px">Fecha</th>
                <th style="padding:6px 12px;text-align:left;font-size:12px">Días</th>
            </tr>
            {cal_rows}
        </table>"""

    return f"""
    <html>
    <body style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;padding:20px;color:#111;background:#fff">

    <h2 style="color:#1e3a5f;border-bottom:2px solid #e5e7eb;padding-bottom:10px;margin-bottom:8px">
        📊 Informe Semanal — {hoy}
    </h2>

    {resumen_html}

    <h3 style="color:#374151;margin:24px 0 8px;font-size:15px">Posiciones</h3>
    {bloques_empresas}

    {calendario_html}

    <p style="color:#9ca3af;font-size:11px;margin-top:28px;border-top:1px solid #e5e7eb;padding-top:12px">
        Generado automáticamente · {hoy} {hora} UTC · Análisis: claude-sonnet-4-20250514 · No constituye asesoramiento financiero.
    </p>
    </body></html>"""


def _generar_html_basico(data, alertas):
    """Fallback si falla la Claude API."""
    hoy = datetime.now().strftime("%d/%m/%Y")
    alertas_count = len(alertas)
    resumen = f"{alertas_count} alerta(s) activa(s)." if alertas_count else "Sin alertas activas."

    bloques = ""
    for symbol in TICKERS:
        d = data[symbol]
        cfg = TICKERS[symbol]
        entrada = cfg["precio_entrada"]
        sl = round(entrada * (1 + cfg["stop_loss_pct"]), 2)
        tp = round(entrada * (1 + cfg["take_profit_pct"]), 2)
        ret = d["retorno_entrada"]
        color_ret = "#16a34a" if ret >= 0 else "#dc2626"
        signo = "+" if ret >= 0 else ""
        pe_str = f"{d['pe_ratio']:.0f}x" if d.get("pe_ratio") else "—"

        bloques += f"""
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;padding:16px;margin:10px 0">
            <h3 style="margin:0 0 8px;color:#1e3a5f">{cfg['nombre']} ({symbol})</h3>
            <div style="display:flex;gap:20px;flex-wrap:wrap;font-size:13px">
                <div><span style="color:#9ca3af">Precio</span><br><strong>${d['precio']}</strong></div>
                <div><span style="color:#9ca3af">vs Entrada</span><br><strong style="color:{color_ret}">{signo}{ret:.1f}%</strong></div>
                <div><span style="color:#9ca3af">Stop Loss</span><br><strong>${sl:.2f}</strong></div>
                <div><span style="color:#9ca3af">Take Profit</span><br><strong>${tp:.2f}</strong></div>
                <div><span style="color:#9ca3af">P/E</span><br><strong>{pe_str}</strong></div>
            </div>
        </div>"""

    hoy_dt = date.today()
    earnings_rows = ""
    for symbol, fecha_str in EARNINGS_CALENDAR.items():
        if symbol not in TICKERS:
            continue
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        dias = (fecha - hoy_dt).days
        if dias >= 0:
            color = "#dc2626" if dias <= 7 else "#d97706" if dias <= 30 else "#6b7280"
            earnings_rows += f"""
            <tr>
                <td style="padding:6px 12px;font-weight:600">{symbol}</td>
                <td style="padding:6px 12px">{fecha_str}</td>
                <td style="padding:6px 12px;color:{color}">{'⚠️ ' if dias<=7 else ''}{dias} días</td>
            </tr>"""

    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;padding:20px;color:#111">
    <h2 style="color:#1e3a5f;border-bottom:2px solid #e5e7eb;padding-bottom:8px">📊 Informe Semanal — {hoy}</h2>
    <p style="background:#eff6ff;border-left:4px solid #2563eb;padding:10px 14px;border-radius:4px">{resumen} Horizonte: 1-3 años · Tolerancia: media.</p>
    <h3 style="color:#374151;margin-top:24px">Posiciones</h3>
    {bloques}
    <h3 style="color:#374151;margin-top:24px">📅 Earnings</h3>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
        <tr style="background:#f3f4f6">
            <th style="padding:6px 12px;text-align:left">Empresa</th>
            <th style="padding:6px 12px;text-align:left">Fecha</th>
            <th style="padding:6px 12px;text-align:left">Días</th>
        </tr>
        {earnings_rows}
    </table>
    <p style="color:#9ca3af;font-size:11px;margin-top:24px">Informe automático · No asesoramiento financiero.</p>
    </body></html>"""


# ── Envío de email ───────────────────────────────────────────────────────────

def enviar_email(asunto, html):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"]    = config.EMAIL_FROM
    msg["To"]      = config.EMAIL_TO
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(config.EMAIL_FROM, config.GMAIL_APP_PASSWORD)
        server.sendmail(config.EMAIL_FROM, config.EMAIL_TO, msg.as_string())
    print(f"✅ Email enviado: {asunto}")


# ── Entry points ─────────────────────────────────────────────────────────────

def run_alertas_diarias():
    """Corre diariamente. Solo envía email si hay alertas CRITICA o ALTA."""
    print(f"[{datetime.now()}] Ejecutando chequeo diario...")
    data    = get_market_data()
    alertas = evaluar_alertas(data)

    importantes = [a for a in alertas if a["nivel"] in ("CRITICA", "ALTA")]
    if importantes:
        html   = generar_html_alerta(importantes, data)
        asunto = f"🚨 [{len(importantes)} alerta(s)] Portafolio NVDA/TSM/PLTR"
        enviar_email(asunto, html)
    else:
        print("Sin alertas importantes. No se envía email.")


def run_informe_semanal():
    """Corre los lunes. Siempre envía el informe completo."""
    print(f"[{datetime.now()}] Generando informe semanal...")
    data    = get_market_data()
    alertas = evaluar_alertas(data)
    html    = generar_html_informe_semanal(data, alertas)
    asunto  = f"📊 Informe Semanal — Portafolio IA ({datetime.now().strftime('%d/%m/%Y')})"
    enviar_email(asunto, html)


if __name__ == "__main__":
    import sys
    modo = sys.argv[1] if len(sys.argv) > 1 else "diario"
    if modo == "semanal":
        run_informe_semanal()
    else:
        run_alertas_diarias()
