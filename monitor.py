"""
Portfolio Monitor — NVDA, TSM, PLTR
Corre diario (alertas de precio) y semanal (informe completo).
Configura tus datos en config.py antes de usar.
"""

import yfinance as yf
import smtplib
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, date
import os

class config:
    NVDA_PRECIO_ENTRADA = float(os.environ.get("NVDA_PRECIO_ENTRADA", 174.39))
    TSM_PRECIO_ENTRADA  = float(os.environ.get("TSM_PRECIO_ENTRADA", 183.00))
    PLTR_PRECIO_ENTRADA = float(os.environ.get("PLTR_PRECIO_ENTRADA", 148.82))
    EMAIL_FROM          = os.environ.get("EMAIL_FROM", "")
    EMAIL_TO            = os.environ.get("EMAIL_TO", "")
    GMAIL_APP_PASSWORD  = os.environ.get("GMAIL_APP_PASSWORD", "")

TICKERS = {
    "NVDA": {
        "nombre": "NVIDIA",
        "precio_entrada": config.NVDA_PRECIO_ENTRADA,
        "stop_loss_pct": -0.25,       # Alerta si cae >25% desde entrada
        "take_profit_pct": 0.60,      # Alerta si sube >60% (target analistas)
        "gross_margin_min": 65.0,     # Señal de salida si baja de este nivel
        "data_center_growth_min": 20, # % crecimiento mínimo aceptable (YoY)
    },
    "TSM": {
        "nombre": "TSMC",
        "precio_entrada": config.TSM_PRECIO_ENTRADA,
        "stop_loss_pct": -0.20,
        "take_profit_pct": 0.40,
        "utilization_min": 80,        # % utilización fábricas
    },
    "PLTR": {
        "nombre": "Palantir",
        "precio_entrada": config.PLTR_PRECIO_ENTRADA,
        "stop_loss_pct": -0.30,       # Mayor tolerancia = mayor volatilidad
        "take_profit_pct": 1.00,      # Upside potencial alto
        "revenue_growth_min": 30,     # % crecimiento mínimo (YoY)
    },
}

# Fechas de earnings próximas (actualizar cada trimestre)
EARNINGS_CALENDAR = {
    "NVDA": "2026-05-28",
    "TSM": "2026-04-17",
    "PLTR": "2026-05-05",
}

# ── Datos de mercado ────────────────────────────────────────────────────────

def get_market_data():
    data = {}
    symbols = list(TICKERS.keys())
    tickers = yf.Tickers(" ".join(symbols))
    
    for symbol in symbols:
        t = tickers.tickers[symbol]
        hist = t.history(period="5d")
        info = t.info
        
        precio_actual = hist["Close"].iloc[-1]
        precio_ayer = hist["Close"].iloc[-2] if len(hist) > 1 else precio_actual
        cambio_1d = (precio_actual - precio_ayer) / precio_ayer * 100
        
        precio_entrada = TICKERS[symbol]["precio_entrada"]
        retorno = (precio_actual - precio_entrada) / precio_entrada * 100
        
        data[symbol] = {
            "precio": round(precio_actual, 2),
            "cambio_1d": round(cambio_1d, 2),
            "retorno_entrada": round(retorno, 2),
            "pe_ratio": info.get("trailingPE", "N/A"),
            "market_cap": info.get("marketCap", 0),
            "volumen": info.get("volume", 0),
            "52w_high": info.get("fiftyTwoWeekHigh", 0),
            "52w_low": info.get("fiftyTwoWeekLow", 0),
        }
    
    return data


# ── Motor de alertas ────────────────────────────────────────────────────────

def evaluar_alertas(data):
    alertas = []
    
    for symbol, cfg in TICKERS.items():
        d = data[symbol]
        precio = d["precio"]
        entrada = cfg["precio_entrada"]
        
        # Stop loss
        if d["retorno_entrada"] <= cfg["stop_loss_pct"] * 100:
            alertas.append({
                "nivel": "CRITICA",
                "symbol": symbol,
                "mensaje": f"⚠️ STOP LOSS alcanzado: {d['retorno_entrada']:.1f}% desde entrada. "
                           f"Revisar posición inmediatamente.",
            })
        
        # Take profit
        elif d["retorno_entrada"] >= cfg["take_profit_pct"] * 100:
            alertas.append({
                "nivel": "ALTA",
                "symbol": symbol,
                "mensaje": f"🎯 Take profit alcanzado: +{d['retorno_entrada']:.1f}%. "
                           f"Considerar tomar parcial o revisar stop.",
            })
        
        # Caída fuerte en 1 día
        if d["cambio_1d"] <= -5.0:
            alertas.append({
                "nivel": "ALTA",
                "symbol": symbol,
                "mensaje": f"📉 Caída fuerte: {d['cambio_1d']:.1f}% en 1 día. "
                           f"Verificar si hay noticias de fundamentals.",
            })
        
        # Cerca de mínimo 52 semanas (posible oportunidad o deterioro)
        if d["52w_low"] > 0:
            distancia_min = (precio - d["52w_low"]) / d["52w_low"] * 100
            if distancia_min < 10:
                alertas.append({
                    "nivel": "MEDIA",
                    "symbol": symbol,
                    "mensaje": f"📊 Precio a {distancia_min:.1f}% del mínimo de 52 semanas. "
                               f"Revisar fundamentals antes de promediar.",
                })
    
    # Alerta de earnings próximos
    hoy = date.today()
    for symbol, fecha_str in EARNINGS_CALENDAR.items():
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


# ── Generador de email HTML ─────────────────────────────────────────────────

def generar_html_alerta(alertas, data):
    items_html = ""
    for a in alertas:
        color = {"CRITICA": "#dc2626", "ALTA": "#d97706", "MEDIA": "#2563eb", "INFO": "#6b7280"}
        bg = {"CRITICA": "#fef2f2", "ALTA": "#fffbeb", "MEDIA": "#eff6ff", "INFO": "#f9fafb"}
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
        color_1d = "#16a34a" if d["cambio_1d"] >= 0 else "#dc2626"
        signo = "+" if d["retorno_entrada"] >= 0 else ""
        signo_1d = "+" if d["cambio_1d"] >= 0 else ""
        precios_html += f"""
        <tr>
            <td style="padding:8px 12px;font-weight:600">{symbol}</td>
            <td style="padding:8px 12px">${d['precio']}</td>
            <td style="padding:8px 12px;color:{color_1d}">{signo_1d}{d['cambio_1d']:.1f}%</td>
            <td style="padding:8px 12px;color:{color_ret}">{signo}{d['retorno_entrada']:.1f}%</td>
            <td style="padding:8px 12px">{d['pe_ratio'] if d['pe_ratio'] != 'N/A' else '—'}x</td>
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
    hoy = datetime.now().strftime('%d/%m/%Y')
    
    # Semáforos por empresa
    def semaforo(symbol, d):
        ret = d["retorno_entrada"]
        cambio = d["cambio_1d"]
        if ret > 15 and cambio > -3:
            return "🟢", "En tendencia positiva"
        elif ret < -15:
            return "🔴", "Revisar posición"
        else:
            return "🟡", "Monitorear"
    
    bloques = ""
    for symbol in TICKERS:
        d = data[symbol]
        nombre = TICKERS[symbol]["nombre"]
        entrada = TICKERS[symbol]["precio_entrada"]
        sl = entrada * (1 + TICKERS[symbol]["stop_loss_pct"])
        tp = entrada * (1 + TICKERS[symbol]["take_profit_pct"])
        icono, estado = semaforo(symbol, d)
        color_ret = "#16a34a" if d["retorno_entrada"] >= 0 else "#dc2626"
        signo = "+" if d["retorno_entrada"] >= 0 else ""
        
        bloques += f"""
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin:12px 0">
            <h3 style="margin:0 0 8px;color:#1e3a5f">{icono} {nombre} ({symbol})</h3>
            <p style="margin:0 0 4px;font-size:13px;color:#6b7280">{estado}</p>
            <div style="display:flex;gap:24px;flex-wrap:wrap;margin-top:12px">
                <div><span style="font-size:11px;color:#9ca3af">Precio actual</span><br>
                    <strong>${d['precio']}</strong></div>
                <div><span style="font-size:11px;color:#9ca3af">Retorno desde entrada</span><br>
                    <strong style="color:{color_ret}">{signo}{d['retorno_entrada']:.1f}%</strong></div>
                <div><span style="font-size:11px;color:#9ca3af">Stop loss</span><br>
                    <strong>${sl:.2f}</strong></div>
                <div><span style="font-size:11px;color:#9ca3af">Take profit</span><br>
                    <strong>${tp:.2f}</strong></div>
                <div><span style="font-size:11px;color:#9ca3af">P/E ratio</span><br>
                    <strong>{d['pe_ratio'] if d['pe_ratio'] != 'N/A' else '—'}x</strong></div>
            </div>
        </div>"""
    
    # Próximos earnings
    hoy_dt = date.today()
    earnings_html = ""
    for symbol, fecha_str in EARNINGS_CALENDAR.items():
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        dias = (fecha - hoy_dt).days
        color = "#dc2626" if dias <= 7 else "#d97706" if dias <= 30 else "#6b7280"
        earnings_html += f"""
        <tr>
            <td style="padding:6px 12px;font-weight:600">{symbol}</td>
            <td style="padding:6px 12px">{fecha_str}</td>
            <td style="padding:6px 12px;color:{color}">
                {'⚠️ ' if dias <= 7 else ''}{dias} días
            </td>
        </tr>"""
    
    alertas_count = len(alertas)
    alertas_resumen = f"{alertas_count} alerta(s) activa(s)" if alertas_count > 0 else "Sin alertas activas"
    
    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;padding:20px;color:#111">
    <h2 style="color:#1e3a5f;border-bottom:2px solid #e5e7eb;padding-bottom:8px">
        📊 Informe Semanal de Portafolio — {hoy}
    </h2>
    <p style="background:#eff6ff;border-left:4px solid #2563eb;padding:10px 14px;border-radius:4px">
        {alertas_resumen}. Horizonte: 1-3 años · Tolerancia: media.
    </p>
    
    <h3 style="color:#374151;margin-top:24px">Posiciones</h3>
    {bloques}
    
    <h3 style="color:#374151;margin-top:24px">📅 Calendario de earnings</h3>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
        <tr style="background:#f3f4f6">
            <th style="padding:6px 12px;text-align:left">Empresa</th>
            <th style="padding:6px 12px;text-align:left">Fecha estimada</th>
            <th style="padding:6px 12px;text-align:left">Días restantes</th>
        </tr>
        {earnings_html}
    </table>
    
    <h3 style="color:#374151;margin-top:24px">🔍 Indicadores clave a monitorear</h3>
    <ul style="font-size:13px;color:#374151;line-height:1.8">
        <li><strong>NVDA</strong>: Gross margin (alerta si &lt;65%) · Data Center growth (alerta si &lt;20% YoY) · CapEx guidance de hyperscalers</li>
        <li><strong>TSM</strong>: Utilización fábricas (alerta si &lt;80%) · Revenue nodos avanzados · Noticias geopolíticas Taiwan</li>
        <li><strong>PLTR</strong>: Crecimiento comercial US (alerta si &lt;40% YoY) · SBC como % revenue (debe bajar del 15%)</li>
    </ul>
    
    <p style="color:#9ca3af;font-size:11px;margin-top:24px;border-top:1px solid #e5e7eb;padding-top:12px">
        Informe automático generado por portfolio_monitor.py · No es asesoramiento financiero.
    </p>
    </body></html>"""


# ── Envío de email ──────────────────────────────────────────────────────────

def enviar_email(asunto, html):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = config.EMAIL_FROM
    msg["To"] = config.EMAIL_TO
    msg.attach(MIMEText(html, "html"))
    
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(config.EMAIL_FROM, config.GMAIL_APP_PASSWORD)
        server.sendmail(config.EMAIL_FROM, config.EMAIL_TO, msg.as_string())
    print(f"✅ Email enviado: {asunto}")


# ── Entry points ────────────────────────────────────────────────────────────

def run_alertas_diarias():
    """Correr diariamente. Solo envía email si hay alertas."""
    print(f"[{datetime.now()}] Ejecutando chequeo diario...")
    data = get_market_data()
    alertas = evaluar_alertas(data)
    
    alertas_importantes = [a for a in alertas if a["nivel"] in ("CRITICA", "ALTA")]
    
    if alertas_importantes:
        html = generar_html_alerta(alertas_importantes, data)
        asunto = f"🚨 [{len(alertas_importantes)} alerta(s)] Portafolio NVDA/TSM/PLTR"
        enviar_email(asunto, html)
    else:
        print("Sin alertas importantes. No se envía email.")


def run_informe_semanal():
    """Correr los lunes. Siempre envía el informe completo."""
    print(f"[{datetime.now()}] Generando informe semanal...")
    data = get_market_data()
    alertas = evaluar_alertas(data)
    html = generar_html_informe_semanal(data, alertas)
    asunto = f"📊 Informe Semanal — Portafolio IA ({datetime.now().strftime('%d/%m/%Y')})"
    enviar_email(asunto, html)


if __name__ == "__main__":
    import sys
    modo = sys.argv[1] if len(sys.argv) > 1 else "diario"
    if modo == "semanal":
        run_informe_semanal()
    else:
        run_alertas_diarias()
