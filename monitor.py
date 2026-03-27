"""
Portfolio Monitor — NVDA, TSM, PLTR
Corre diario (alertas de precio) y semanal (informe completo con análisis IA).
Incluye evaluación de tesis fundamental por empresa (actualizar tesis.json cada trimestre).
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
import time


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
        "pe_referencia": "23x = historico, >35x = caro",
    },
    "PLTR": {
        "nombre": "Palantir",
        "precio_entrada": config.PLTR_PRECIO_ENTRADA,
        "stop_loss_pct": -0.30,
        "take_profit_pct": 1.00,
        "revenue_growth_min": 30,
        "pe_referencia": "PE extremo por naturaleza - evaluar tendencia historica",
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

# Umbrales de tesis por empresa
# "min" = alerta si el valor cae por debajo
# "max" = alerta si el valor sube por encima
TESIS_UMBRALES = {
    "NVDA": {
        "gross_margin_pct":           {"min": 65.0, "label": "Gross Margin",           "unidad": "%"},
        "data_center_growth_yoy_pct": {"min": 20.0, "label": "Data Center Growth YoY", "unidad": "%"},
        "operating_margin_pct":       {"min": 50.0, "label": "Operating Margin",        "unidad": "%"},
    },
    "TSM": {
        "gross_margin_pct":                        {"min": 53.0, "label": "Gross Margin",             "unidad": "%"},
        "utilizacion_fabricas_pct":                {"min": 80.0, "label": "Utilizacion de Fabricas",  "unidad": "%"},
        "revenue_nodos_avanzados_growth_yoy_pct":  {"min": 25.0, "label": "Revenue Nodos <5nm YoY",   "unidad": "%"},
    },
    "PLTR": {
        "revenue_comercial_us_growth_yoy_pct": {"min": 35.0,  "label": "Revenue Comercial US YoY", "unidad": "%"},
        "net_revenue_retention_pct":           {"min": 115.0, "label": "Net Revenue Retention",     "unidad": "%"},
        "sbc_pct_revenue":                     {"max": 20.0,  "label": "SBC % Revenue",             "unidad": "%"},
        "operating_margin_pct":                {"min": 20.0,  "label": "Operating Margin",           "unidad": "%"},
    },
}


# ── Evaluacion de tesis ──────────────────────────────────────────────────────

def cargar_tesis():
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tesis.json")
    if not os.path.exists(ruta):
        print(f"Warning: tesis.json no encontrado en {ruta}")
        return {}
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluar_tesis(tesis_data):
    """
    Evalua cada empresa contra sus umbrales fundamentales.
    Retorna dict con estado: TESIS_OK | TESIS_EN_RIESGO | TESIS_ROTA
    """
    resultados = {}

    for symbol, umbrales in TESIS_UMBRALES.items():
        empresa_data = tesis_data.get(symbol, {})
        metricas = empresa_data.get("metricas", {})
        ultima_act = empresa_data.get("ultima_actualizacion", "desconocida")
        periodo = empresa_data.get("periodo", "desconocido")
        notas = empresa_data.get("notas", "")

        checks = []
        rotas = 0
        en_riesgo = 0

        for metrica_key, cfg in umbrales.items():
            valor_raw = metricas.get(metrica_key)
            if valor_raw is None:
                valor = None
            else:
                try:
                    valor = float(valor_raw)
                except (TypeError, ValueError):
                    print(f"Warning: valor no numerico en tesis.json para {symbol}.{metrica_key}: {valor_raw!r}")
                    valor = None
            if valor is None:
                checks.append({
                    "label": cfg["label"],
                    "valor": None,
                    "estado": "SIN_DATO",
                    "mensaje": "Sin dato cargado",
                })
                continue

            label = cfg["label"]
            unidad = cfg["unidad"]

            if "min" in cfg:
                umbral = cfg["min"]
                ok = valor >= umbral
                diferencia = valor - umbral
                estado_check = "OK" if ok else ("EN_RIESGO" if diferencia > -5 else "ROTO")
                checks.append({
                    "label": label,
                    "valor": valor,
                    "umbral": umbral,
                    "unidad": unidad,
                    "ok": ok,
                    "estado": estado_check,
                    "mensaje": f"{valor}{unidad} {'OK' if ok else ('cerca del minimo ' + str(umbral) + unidad if estado_check == 'EN_RIESGO' else 'ROTO - minimo ' + str(umbral) + unidad)}",
                })
                if not ok:
                    if estado_check == "EN_RIESGO":
                        en_riesgo += 1
                    else:
                        rotas += 1

            elif "max" in cfg:
                umbral = cfg["max"]
                ok = valor <= umbral
                diferencia = umbral - valor
                estado_check = "OK" if ok else ("EN_RIESGO" if diferencia > -3 else "ROTO")
                checks.append({
                    "label": label,
                    "valor": valor,
                    "umbral": umbral,
                    "unidad": unidad,
                    "ok": ok,
                    "estado": estado_check,
                    "mensaje": f"{valor}{unidad} {'OK' if ok else ('cerca del maximo ' + str(umbral) + unidad if estado_check == 'EN_RIESGO' else 'ROTO - maximo ' + str(umbral) + unidad)}",
                })
                if not ok:
                    if estado_check == "EN_RIESGO":
                        en_riesgo += 1
                    else:
                        rotas += 1

        if rotas >= 2:
            estado_global = "TESIS_ROTA"
        elif rotas == 1 or en_riesgo >= 2:
            estado_global = "TESIS_EN_RIESGO"
        else:
            estado_global = "TESIS_OK"

        datos_viejos = False
        try:
            fecha_act = datetime.strptime(ultima_act, "%Y-%m-%d").date()
            dias_desde_act = (date.today() - fecha_act).days
            datos_viejos = dias_desde_act > 120
        except Exception:
            datos_viejos = True

        resultados[symbol] = {
            "estado": estado_global,
            "checks": checks,
            "rotas": rotas,
            "en_riesgo": en_riesgo,
            "ultima_actualizacion": ultima_act,
            "periodo": periodo,
            "notas": notas,
            "datos_viejos": datos_viejos,
        }

    return resultados


def necesita_actualizar_tesis():
    """
    Retorna empresas cuyos earnings pasaron hace 0-14 dias
    pero tesis.json no fue actualizado despues de esa fecha.
    """
    tesis_data = cargar_tesis()
    hoy = date.today()
    alertas = []

    for symbol in TICKERS:
        fecha_earnings_str = EARNINGS_CALENDAR.get(symbol)
        if not fecha_earnings_str:
            continue
        fecha_earnings = datetime.strptime(fecha_earnings_str, "%Y-%m-%d").date()
        dias_desde_earnings = (hoy - fecha_earnings).days

        if 0 <= dias_desde_earnings <= 14:
            empresa_data = tesis_data.get(symbol, {})
            ultima_act_str = empresa_data.get("ultima_actualizacion", "2000-01-01")
            try:
                ultima_act = datetime.strptime(ultima_act_str, "%Y-%m-%d").date()
            except Exception:
                ultima_act = date(2000, 1, 1)

            if ultima_act < fecha_earnings:
                alertas.append({
                    "symbol": symbol,
                    "fecha_earnings": fecha_earnings_str,
                    "dias_desde_earnings": dias_desde_earnings,
                    "ultima_actualizacion": ultima_act_str,
                })

    return alertas


def verificar_proximos_earnings_aviso():
    """
    Retorna empresas con earnings en 7-14 dias como aviso de preparacion.
    """
    hoy = date.today()
    proximos = []
    for symbol in TICKERS:
        fecha_earnings_str = EARNINGS_CALENDAR.get(symbol)
        if not fecha_earnings_str:
            continue
        fecha_earnings = datetime.strptime(fecha_earnings_str, "%Y-%m-%d").date()
        dias = (fecha_earnings - hoy).days
        if 7 <= dias <= 14:
            proximos.append({
                "symbol": symbol,
                "fecha_earnings": fecha_earnings_str,
                "dias_restantes": dias,
            })
    return proximos


# ── Vigilancia de cambio de paradigma ────────────────────────────────────────

# Señales que vigilamos. Cada una tiene un peso y una descripcion de por que importa.
PARADIGMA_SEÑALES = {
    "neuromorphic": {
        "label": "Neuromorphic Computing",
        "descripcion": "Chips que emulan neuronas biologicas. Consumen 100-1000x menos energia que GPUs. Si escalan, el modelo de GPU cluster deja de ser necesario.",
        "ejemplos": ["Intel Loihi", "Ami Labs", "Cortical Labs", "IBM NorthPole", "SpiNNaker"],
        "umbral_alerta": "Benchmark en tarea de IA que supere GPU en eficiencia energetica por factor >10x a escala",
    },
    "optical_computing": {
        "label": "Optical / Photonic Computing",
        "descripcion": "Computo con fotones en lugar de electrones. Velocidad de luz, consumo minimo. Lightmatter y Luminous ya tienen chips en produccion limitada.",
        "ejemplos": ["Lightmatter", "Luminous Computing", "Nvidia Photonics research"],
        "umbral_alerta": "Chip fotonico que corra inferencia de LLM a escala con ventaja de costo real vs GPU",
    },
    "alternative_arch": {
        "label": "Arquitecturas alternativas a Transformers",
        "descripcion": "SSMs (Mamba), RWKV, arquitecturas hibridas que logren calidad similar a transformers con menos cómputo. Si se adoptan masivamente, la demanda de GPU cae.",
        "ejemplos": ["Mamba / SSM", "RWKV", "Hyena", "xLSTM", "TTT"],
        "umbral_alerta": "Arquitectura no-transformer que iguale o supere GPT-4 class en benchmarks estandar con <10% del computo",
    },
    "hyperscaler_capex": {
        "label": "Reduccion de CapEx en hyperscalers",
        "descripcion": "Si Microsoft, Google, Amazon o Meta reducen guidance de CapEx mientras mantienen capacidad de computo, significa que estan encontrando alternativas a GPUs NVIDIA.",
        "ejemplos": ["Google TPU v5", "Amazon Trainium2", "Microsoft Maia", "Meta MTIA"],
        "umbral_alerta": "Cualquier hyperscaler reduce pedidos de GPU YoY mientras su capacidad de computo crece",
    },
    "energy_constraint": {
        "label": "Restriccion energetica estructural",
        "descripcion": "Los data centers de IA ya consumen tanto como paises medianos. Si hay restricciones regulatorias o de grid electrico, el modelo de escalar con mas GPUs se frena.",
        "ejemplos": ["Regulacion EU de consumo AI", "Restricciones de grid en Virginia/Texas", "Nuclear para AI"],
        "umbral_alerta": "Regulacion que limite consumo energetico de data centers de IA en mercados mayores",
    },
}

# Nivel de alerta del paradigma
# VERDE: sin señales relevantes
# AMARILLO: señales tempranas, monitorear
# ROJO: señal concreta de cambio — considerar salida
PARADIGMA_NIVELES = {
    0: "VERDE",
    1: "AMARILLO",
    2: "ROJO",
}


def analizar_cambio_paradigma(noticias, client=None):
    """
    Analiza señales de cambio de paradigma en computacion de IA
    usando las noticias ya obtenidas (sin web search para respetar rate limits).
    """
    if client is None:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    señales_ctx = json.dumps(
        {k: {"label": v["label"], "umbral_alerta": v["umbral_alerta"]}
         for k, v in PARADIGMA_SEÑALES.items()},
        ensure_ascii=False, indent=2
    )

    # Solo titulos de noticias para minimizar tokens
    titulos = [n["titulo"][:200] for n in noticias[:30]]
    noticias_ctx = json.dumps(titulos, ensure_ascii=False)

    prompt = f"""Eres un analista vigilando señales de cambio de paradigma en computacion de IA.

Tesis del portafolio (NVDA/TSM/PLTR): la infraestructura actual de IA (GPU clusters + transformers + foundry avanzado) domina los proximos 3 anios.
Regla de salida: si aparece evidencia concreta de un paradigma superador, se sale de las posiciones.

Areas vigiladas (key: label | umbral_alerta):
{señales_ctx}

Noticias de los ultimos 7 dias:
{noticias_ctx}

Evalua si alguna noticia constituye evidencia de avance en estas areas. Se estricto: ALERTA solo si es resultado empirico demostrado con path a escala, no especulacion.

Responde UNICAMENTE con JSON valido:
{{
  "nivel_global": "VERDE|AMARILLO|ROJO",
  "resumen": "2 oraciones sobre el estado del paradigma",
  "señales_detectadas": [
    {{
      "area": "key del area",
      "nivel": "RUIDO|SEÑAL|ALERTA",
      "titulo": "noticia relevante",
      "detalle": "por que importa o no para la tesis"
    }}
  ],
  "recomendacion": "una oracion"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        return _parse_json_from_claude(_extract_text_from_claude(message))
    except Exception:
        # Fallback si el JSON no parsea
        return {
            "nivel_global": "VERDE",
            "resumen": "No se pudo obtener analisis de paradigma esta semana.",
            "señales_detectadas": [],
            "recomendacion": "Reintentar la proxima semana.",
        }


def _html_bloque_paradigma(analisis_paradigma):
    """Genera el bloque HTML del analisis de cambio de paradigma."""
    if not analisis_paradigma:
        return ""

    nivel = analisis_paradigma.get("nivel_global", "VERDE")
    resumen = analisis_paradigma.get("resumen", "")
    señales = analisis_paradigma.get("señales_detectadas", [])
    recomendacion = analisis_paradigma.get("recomendacion", "")

    NIVEL_CFG = {
        "VERDE":    {"color": "#16a34a", "bg": "#f0fdf4", "borde": "#86efac", "label": "SIN SEÑALES DE CAMBIO"},
        "AMARILLO": {"color": "#d97706", "bg": "#fffbeb", "borde": "#fcd34d", "label": "SEÑALES TEMPRANAS — MONITOREAR"},
        "ROJO":     {"color": "#dc2626", "bg": "#fef2f2", "borde": "#fca5a5", "label": "ALERTA DE PARADIGMA — REVISAR TESIS"},
    }
    nc = NIVEL_CFG.get(nivel, NIVEL_CFG["VERDE"])

    SEÑAL_CFG = {
        "RUIDO":  {"color": "#9ca3af", "label": "RUIDO"},
        "SEÑAL":  {"color": "#d97706", "label": "SEÑAL"},
        "ALERTA": {"color": "#dc2626", "label": "ALERTA"},
    }

    señales_html = ""
    for s in señales:
        sc = SEÑAL_CFG.get(s.get("nivel", "RUIDO"), SEÑAL_CFG["RUIDO"])
        area_key = s.get("area", "")
        area_label = PARADIGMA_SEÑALES.get(area_key, {}).get("label", area_key)
        señales_html += f"""
        <div style="padding:8px 0;border-bottom:1px solid {nc['borde']}44">
            <div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px">
                <span style="font-size:12px;font-weight:600;color:#374151">{s.get('titulo','')}</span>
                <span style="font-size:10px;font-weight:700;color:{sc['color']};white-space:nowrap">[{sc['label']}]</span>
            </div>
            <div style="font-size:11px;color:#6b7280;margin-top:2px">
                {area_label} &middot; {s.get('fuente','')}
            </div>
            <div style="font-size:12px;color:#374151;margin-top:4px;line-height:1.5">
                {s.get('detalle','')}
            </div>
        </div>"""

    if not señales_html:
        señales_html = '<p style="font-size:12px;color:#9ca3af;margin:8px 0">Sin señales relevantes detectadas esta semana.</p>'

    recomendacion_html = ""
    if recomendacion:
        recomendacion_html = f"""
        <div style="margin-top:10px;padding:8px 12px;background:{'#fef2f2' if nivel=='ROJO' else '#f9fafb'};border-radius:4px">
            <span style="font-size:12px;font-weight:600;color:{nc['color']}">Recomendacion: </span>
            <span style="font-size:12px;color:#374151">{recomendacion}</span>
        </div>"""

    return f"""
    <div style="margin:24px 0">
        <h3 style="color:#374151;font-size:15px;margin:0 0 10px">Vigilancia de Cambio de Paradigma</h3>
        <div style="background:{nc['bg']};border:2px solid {nc['borde']};border-radius:8px;padding:16px 20px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
                <span style="font-size:13px;font-weight:700;color:{nc['color']}">{nivel} &mdash; {nc['label']}</span>
            </div>
            <p style="margin:0 0 12px;font-size:13px;line-height:1.6;color:#374151">{resumen}</p>
            {señales_html}
            {recomendacion_html}
        </div>
        <p style="font-size:10px;color:#9ca3af;margin:6px 0 0">
            Areas vigiladas: neuromorphic computing &middot; optical computing &middot; arquitecturas alternativas a transformers &middot; CapEx hyperscalers &middot; restricciones energeticas
        </p>
    </div>"""


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

        precio_semana = float(hist["Close"].iloc[-min(5, len(hist))]) if len(hist) > 1 else precio_actual
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
    if tickers is None:
        tickers = NEWS_TICKERS

    noticias = []
    cutoff = datetime.now() - timedelta(days=7)

    for symbol in tickers:
        try:
            url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
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


# ── Motor de alertas de precio ───────────────────────────────────────────────

def evaluar_alertas(data):
    alertas = []

    for symbol, cfg in TICKERS.items():
        d = data[symbol]
        precio = d["precio"]

        if d["retorno_entrada"] <= cfg["stop_loss_pct"] * 100:
            alertas.append({
                "nivel": "CRITICA",
                "symbol": symbol,
                "mensaje": f"STOP LOSS DE PRECIO alcanzado: {d['retorno_entrada']:.1f}% desde entrada. "
                           f"Revisar tesis antes de decidir. Precio: ${precio}.",
            })
        elif d["retorno_entrada"] >= cfg["take_profit_pct"] * 100:
            alertas.append({
                "nivel": "ALTA",
                "symbol": symbol,
                "mensaje": f"Take profit alcanzado: +{d['retorno_entrada']:.1f}%. "
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
                "mensaje": f"Condicion REVISAR activa. "
                           f"Dist. max 52s: {dist_max:.1f}%, cambio semanal: {cambio_sem:.1f}%, "
                           f"retorno entrada: {retorno:.1f}%.",
            })

        if d["cambio_1d"] <= -5.0:
            alertas.append({
                "nivel": "ALTA",
                "symbol": symbol,
                "mensaje": f"Caida fuerte: {d['cambio_1d']:.1f}% en 1 dia. "
                           f"Verificar si hay noticias de fundamentals.",
            })

        if d["52w_low"] > 0:
            distancia_min = (precio - d["52w_low"]) / d["52w_low"] * 100
            if distancia_min < 10:
                alertas.append({
                    "nivel": "MEDIA",
                    "symbol": symbol,
                    "mensaje": f"Precio a {distancia_min:.1f}% del minimo de 52 semanas. "
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
                "mensaje": f"Earnings en {dias_restantes} dias ({fecha_str}). "
                           f"Alta volatilidad esperada.",
            })

    return alertas


# ── Analisis con Claude ───────────────────────────────────────────────────────

def _extract_text_from_claude(message):
    """Extrae y concatena todos los bloques de texto de una respuesta Claude."""
    return "".join(block.text for block in message.content if hasattr(block, "text"))

def _parse_json_from_claude(text):
    """Limpia fences de markdown y parsea JSON."""
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    return json.loads(text)


def generar_analisis_claude(data_mercado, noticias, tesis_resultados=None):
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    empresas_ctx = []
    for symbol, cfg in TICKERS.items():
        d = data_mercado[symbol]
        entrada = cfg["precio_entrada"]
        sl_precio = round(entrada * (1 + cfg["stop_loss_pct"]), 2)
        tp_precio = round(entrada * (1 + cfg["take_profit_pct"]), 2)

        tesis_ctx = {}
        if tesis_resultados and symbol in tesis_resultados:
            tr = tesis_resultados[symbol]
            tesis_ctx = {
                "estado_tesis": tr["estado"],
                "metricas_rotas": tr["rotas"],
                "metricas_en_riesgo": tr["en_riesgo"],
                "periodo_datos": tr["periodo"],
            }

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
            "tesis": tesis_ctx,
        })

    hoy = date.today()
    earnings_ctx = []
    for symbol, fecha_str in EARNINGS_CALENDAR.items():
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        dias = (fecha - hoy).days
        if 0 <= dias <= 30:
            earnings_ctx.append({"empresa": symbol, "fecha": fecha_str, "dias_restantes": dias})

    noticias_por_ticker = {}
    for n in noticias:
        t = n["ticker"]
        noticias_por_ticker.setdefault(t, [])
        if len(noticias_por_ticker[t]) < 4:  # max 4 noticias por ticker para no exceder rate limit
            noticias_por_ticker[t].append({
                "titulo": n["titulo"][:200],
                "fecha": n["fecha"],
            })

    prompt = f"""Eres un analista financiero especializado en tecnologia y semiconductores.
Analiza el estado de este portafolio y genera un informe semanal estructurado.

CONTEXTO DEL PORTAFOLIO:
- Concentracion: 100% en NVDA, TSM, PLTR (sin diversificacion externa)
- Horizonte: 1-3 anios
- Tolerancia: media
- Objetivo: crecimiento de capital
- IMPORTANTE: El inversor distingue entre stop loss de PRECIO (alerta tactica) y stop loss de TESIS
  (decision estrategica). Solo sale de una posicion si la tesis se rompe, no por precio solo.

DATOS DE MERCADO:
{json.dumps(empresas_ctx, ensure_ascii=False, indent=2)}

NOTICIAS ULTIMOS 7 DIAS:
{json.dumps(noticias_por_ticker, ensure_ascii=False, indent=2)}

EARNINGS PROXIMOS 30 DIAS:
{json.dumps(earnings_ctx, ensure_ascii=False, indent=2)}

INSTRUCCIONES:
- Senal: MANTENER (tesis intacta), VIGILAR (zona de alerta), REVISAR (umbral roto o tesis en
  riesgo). Si el campo tesis.estado_tesis es TESIS_ROTA -> senal REVISAR automaticamente.
  Si es TESIS_EN_RIESGO -> senal VIGILAR como minimo.
- Analisis: interpreta los numeros, no los describas. Si hay earnings en los proximos 14 dias,
  incluir bloque EARNINGS CHECK con metricas clave y umbrales especificos.
- Noticias: solo las relevantes para la tesis de IA/semis/crecimiento cloud/gobierno.
- Tono: analista directo hablando a otro inversor sofisticado. Sin disclaimers.

Responde UNICAMENTE con JSON valido, sin texto adicional:
{{
  "resumen_ejecutivo": "3-4 oraciones",
  "empresas": {{
    "NVDA": {{
      "senal": "MANTENER|VIGILAR|REVISAR",
      "razon_senal": "una oracion",
      "analisis": "2-3 parrafos. Si hay earnings proximos, incluir bloque EARNINGS CHECK al final.",
      "noticias_relevantes": [
        {{"titular": "...", "contexto": "1 linea: por que importa para el portafolio"}}
      ]
    }},
    "TSM": {{}},
    "PLTR": {{}}
  }},
  "calendario_eventos": ["descripcion del evento relevante proximo"]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_json_from_claude(_extract_text_from_claude(message))


# ── HTML helpers ─────────────────────────────────────────────────────────────

def _html_bloque_tesis(symbol, tesis_resultado):
    if not tesis_resultado:
        return ""

    estado = tesis_resultado["estado"]
    checks = tesis_resultado["checks"]
    ultima_act = tesis_resultado["ultima_actualizacion"]
    periodo = tesis_resultado["periodo"]
    notas = tesis_resultado.get("notas", "")
    datos_viejos = tesis_resultado.get("datos_viejos", False)

    ESTADO_CFG = {
        "TESIS_OK":        {"color": "#16a34a", "bg": "#f0fdf4", "icono": "OK",      "label": "TESIS OK"},
        "TESIS_EN_RIESGO": {"color": "#d97706", "bg": "#fffbeb", "icono": "RIESGO",  "label": "TESIS EN RIESGO"},
        "TESIS_ROTA":      {"color": "#dc2626", "bg": "#fef2f2", "icono": "ROTA",    "label": "TESIS ROTA"},
    }
    sc = ESTADO_CFG.get(estado, ESTADO_CFG["TESIS_EN_RIESGO"])

    checks_html = ""
    for c in checks:
        if c["estado"] == "SIN_DATO":
            dot_color = "#9ca3af"
        elif c["estado"] == "OK":
            dot_color = "#16a34a"
        elif c["estado"] == "EN_RIESGO":
            dot_color = "#d97706"
        else:
            dot_color = "#dc2626"

        checks_html += f"""
        <div style="display:flex;align-items:center;gap:8px;padding:3px 0;font-size:12px">
            <span style="color:{dot_color};font-size:16px">&#9679;</span>
            <span style="color:#374151;flex:1">{c['label']}</span>
            <span style="color:#111;font-weight:600">{c['mensaje']}</span>
        </div>"""

    aviso_datos_viejos = ""
    if datos_viejos:
        aviso_datos_viejos = f"""
        <div style="background:#fef9c3;border:1px solid #fde68a;border-radius:4px;padding:6px 10px;margin-top:8px;font-size:11px;color:#92400e">
            Datos de {ultima_act} ({periodo}). Actualizar tesis.json con los ultimos earnings.
        </div>"""

    notas_html = f'<p style="margin:8px 0 0;font-size:11px;color:#6b7280;font-style:italic">{notas}</p>' if notas else ""

    return f"""
    <div style="background:{sc['bg']};border:1px solid {sc['color']}55;border-radius:6px;padding:12px 16px;margin-top:12px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <span style="font-size:12px;font-weight:700;color:{sc['color']}">[{sc['icono']}] {sc['label']}</span>
            <span style="font-size:11px;color:#9ca3af">{periodo} &middot; {ultima_act}</span>
        </div>
        {checks_html}
        {notas_html}
        {aviso_datos_viejos}
    </div>"""


def _html_recordatorio(pendientes, proximos):
    if not pendientes and not proximos:
        return ""

    items = ""
    for p in pendientes:
        items += f"""
        <div style="background:#fef2f2;border-left:4px solid #dc2626;padding:10px 14px;margin:6px 0;border-radius:4px">
            <strong style="color:#dc2626">ACTUALIZAR TESIS.JSON — {p['symbol']}</strong><br>
            <span style="font-size:13px;color:#374151">
                Earnings del {p['fecha_earnings']} pasaron hace {p['dias_desde_earnings']} dias.
                Cargar datos del nuevo trimestre en tesis.json.
                Ultimo dato registrado: {p['ultima_actualizacion']}.
            </span>
        </div>"""

    for p in proximos:
        items += f"""
        <div style="background:#fffbeb;border-left:4px solid #d97706;padding:10px 14px;margin:6px 0;border-radius:4px">
            <strong style="color:#d97706">PREPARAR ACTUALIZACION — {p['symbol']}</strong><br>
            <span style="font-size:13px;color:#374151">
                Earnings en {p['dias_restantes']} dias ({p['fecha_earnings']}).
                Preparate para actualizar tesis.json despues del reporte.
            </span>
        </div>"""

    return f"""
    <div style="margin:20px 0">
        <h3 style="color:#374151;font-size:15px;margin:0 0 8px">Actualizacion de Tesis Pendiente</h3>
        {items}
        <p style="font-size:11px;color:#9ca3af;margin:8px 0 0">
            Editar tesis.json en el repositorio y hacer commit para actualizar la evaluacion fundamental.
        </p>
    </div>"""


# ── Generadores de HTML ──────────────────────────────────────────────────────

def generar_html_alerta(alertas, data, tesis_resultados=None, analisis_paradigma=None):
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

    if tesis_resultados:
        for symbol, tr in tesis_resultados.items():
            if tr["estado"] == "TESIS_ROTA":
                items_html += f"""
                <div style="background:#fef2f2;border-left:4px solid #dc2626;padding:12px 16px;margin:8px 0;border-radius:4px">
                    <strong style="color:#dc2626">[TESIS ROTA] {symbol}</strong><br>
                    <span style="color:#374151">
                        {tr['rotas']} metrica(s) fundamental(es) por debajo del umbral.
                        Datos de: {tr['periodo']}. Criterio de salida: tesis, no precio.
                    </span>
                </div>"""
            elif tr["estado"] == "TESIS_EN_RIESGO":
                items_html += f"""
                <div style="background:#fffbeb;border-left:4px solid #d97706;padding:12px 16px;margin:8px 0;border-radius:4px">
                    <strong style="color:#d97706">[TESIS EN RIESGO] {symbol}</strong><br>
                    <span style="color:#374151">
                        {tr['en_riesgo']} metrica(s) cerca del umbral minimo.
                        Monitorear proximos earnings con atencion.
                    </span>
                </div>"""

    # Bloque de paradigma en email de alerta (solo si ROJO)
    paradigma_alerta_html = ""
    if analisis_paradigma and analisis_paradigma.get("nivel_global") == "ROJO":
        paradigma_alerta_html = _html_bloque_paradigma(analisis_paradigma)

    precios_html = ""
    for symbol, d in data.items():
        color_ret = "#16a34a" if d["retorno_entrada"] >= 0 else "#dc2626"
        color_1d  = "#16a34a" if d["cambio_1d"] >= 0 else "#dc2626"
        signo     = "+" if d["retorno_entrada"] >= 0 else ""
        signo_1d  = "+" if d["cambio_1d"] >= 0 else ""
        pe_str    = f"{d['pe_ratio']:.0f}x" if d.get("pe_ratio") else "-"
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
        Alertas de Portafolio &mdash; {datetime.now().strftime('%d/%m/%Y %H:%M')}
    </h2>
    {items_html}
    {paradigma_alerta_html}
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
        Este informe es automatico y no constituye asesoramiento financiero.
    </p>
    </body></html>"""


def generar_html_informe_semanal(data, alertas):
    api_key = config.ANTHROPIC_API_KEY
    print(f"ANTHROPIC_API_KEY configurada: {'si' if api_key else 'NO - FALTA EL SECRET'} (len={len(api_key)})")

    print("Evaluando tesis fundamental...")
    tesis_data = cargar_tesis()
    tesis_resultados = evaluar_tesis(tesis_data)
    pendientes_actualizacion = necesita_actualizar_tesis()
    proximos_earnings_aviso = verificar_proximos_earnings_aviso()

    print("Obteniendo noticias...")
    try:
        noticias = get_news()
        print(f"Noticias obtenidas: {len(noticias)}")
    except Exception as e:
        print(f"Error obteniendo noticias: {e}")
        noticias = []

    print("Analizando señales de cambio de paradigma...")
    analisis_paradigma = None
    nivel_paradigma = "VERDE"
    paradigma_ok = False
    for intento in range(2):
        try:
            analisis_paradigma = analizar_cambio_paradigma(noticias)
            nivel_paradigma = analisis_paradigma.get("nivel_global", "VERDE")
            print(f"Paradigma: {nivel_paradigma}")
            paradigma_ok = True
            break
        except anthropic.RateLimitError:
            if intento == 0:
                print("Rate limit en paradigma, esperando 62s y reintentando...")
                time.sleep(62)
            else:
                print("Rate limit persistente en paradigma, continuando sin analisis.")
        except Exception as e:
            print(f"Error en analisis de paradigma: {e}")
            break

    if paradigma_ok:
        print("Esperando 62s antes de segunda llamada a Claude (rate limit)...")
        time.sleep(62)
    else:
        print("Primera llamada Claude fallida, omitiendo sleep de rate limit.")

    print("Generando analisis con Claude...")
    for intento in range(2):
        try:
            analisis = generar_analisis_claude(data, noticias, tesis_resultados)
            print("Analisis Claude generado correctamente.")
            break
        except anthropic.RateLimitError:
            if intento == 0:
                print("Rate limit en analisis principal, esperando 62s y reintentando...")
                time.sleep(62)
            else:
                print("Rate limit persistente en analisis principal.")
                return _generar_html_basico(data, alertas)
        except Exception as e:
            print(f"ERROR en analisis Claude: {e}")
            traceback.print_exc()
            return _generar_html_basico(data, alertas)

    hoy  = datetime.now().strftime("%d/%m/%Y")
    hora = datetime.now().strftime("%H:%M")

    SENAL_CFG = {
        "MANTENER": {"color": "#16a34a", "bg": "#f0fdf4", "icono": "MANTENER"},
        "VIGILAR":  {"color": "#d97706", "bg": "#fffbeb", "icono": "VIGILAR"},
        "REVISAR":  {"color": "#dc2626", "bg": "#fef2f2", "icono": "REVISAR"},
    }

    resumen_html = f"""
    <div style="background:#eff6ff;border-left:4px solid #2563eb;border-radius:4px;padding:16px 20px;margin:16px 0">
        <p style="margin:0;font-size:14px;line-height:1.7;color:#1e3a5f">
            {analisis.get('resumen_ejecutivo', '')}
        </p>
    </div>"""

    recordatorio_html = _html_recordatorio(pendientes_actualizacion, proximos_earnings_aviso)

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
        pe_str    = f"{d['pe_ratio']:.0f}x" if d.get("pe_ratio") else "-"
        dist_str  = f"{d['distancia_52w_high']:.1f}%" if d.get("distancia_52w_high") is not None else "-"

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
                <p style="margin:0 0 6px;font-size:11px;font-weight:600;color:#9ca3af;text-transform:uppercase">Noticias relevantes</p>
                <ul style="margin:0;padding-left:16px">{noticias_items}</ul>
            </div>"""

        tesis_html = _html_bloque_tesis(symbol, tesis_resultados.get(symbol))

        bloques_empresas += f"""
        <div style="background:{sc['bg']};border-left:4px solid {sc['color']};border-radius:6px;padding:16px 20px;margin:12px 0">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:4px">
                <div>
                    <h3 style="margin:0;color:#111;font-size:16px">[{sc['icono']}] {nombre} ({symbol})</h3>
                    <p style="margin:4px 0 0;font-size:12px;color:{sc['color']};font-weight:600">{senal} &mdash; {razon}</p>
                </div>
                <div style="text-align:right">
                    <span style="font-size:22px;font-weight:700;color:#111">${d['precio']}</span>
                    <span style="margin-left:8px;font-size:13px;color:{color_sem}">{signo_sem}{d.get('cambio_semanal', 0):.1f}% sem</span>
                </div>
            </div>

            <div style="display:flex;gap:20px;flex-wrap:wrap;padding:10px 0;margin:10px 0;border-top:1px solid {sc['color']}33;border-bottom:1px solid {sc['color']}33">
                <div style="font-size:12px"><span style="color:#9ca3af">vs Entrada</span><br><strong style="color:{color_ret}">{signo}{d['retorno_entrada']:.1f}%</strong></div>
                <div style="font-size:12px"><span style="color:#9ca3af">Stop Precio</span><br><strong>${sl:.2f}</strong></div>
                <div style="font-size:12px"><span style="color:#9ca3af">Take Profit</span><br><strong>${tp:.2f}</strong></div>
                <div style="font-size:12px"><span style="color:#9ca3af">P/E</span><br><strong>{pe_str}</strong></div>
                <div style="font-size:12px"><span style="color:#9ca3af">vs Max 52s</span><br><strong>{dist_str}</strong></div>
            </div>

            {parrafos}
            {tesis_html}
            {noticias_section}
        </div>"""

    hoy_dt = date.today()
    cal_rows = ""
    for symbol, fecha_str in EARNINGS_CALENDAR.items():
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        dias  = (fecha - hoy_dt).days
        if 0 <= dias <= 30:
            urgente = dias <= 7
            color_d = "#dc2626" if dias <= 7 else "#d97706" if dias <= 14 else "#6b7280"
            bold    = "font-weight:600" if urgente else ""
            cal_rows += f"""
            <tr>
                <td style="padding:6px 12px;font-size:13px;font-weight:600">{symbol}</td>
                <td style="padding:6px 12px;font-size:13px">Earnings</td>
                <td style="padding:6px 12px;font-size:13px">{fecha_str}</td>
                <td style="padding:6px 12px;font-size:13px;color:{color_d};{bold}">{dias} dias</td>
            </tr>"""

    for evento in analisis.get("calendario_eventos", []):
        cal_rows += f"""
        <tr>
            <td colspan="4" style="padding:6px 12px;font-size:13px;color:#6b7280">{evento}</td>
        </tr>"""

    calendario_html = ""
    if cal_rows:
        calendario_html = f"""
        <h3 style="color:#374151;margin:28px 0 8px;font-size:15px">Proximos 30 dias</h3>
        <table style="width:100%;border-collapse:collapse">
            <tr style="background:#f3f4f6">
                <th style="padding:6px 12px;text-align:left;font-size:12px">Empresa</th>
                <th style="padding:6px 12px;text-align:left;font-size:12px">Evento</th>
                <th style="padding:6px 12px;text-align:left;font-size:12px">Fecha</th>
                <th style="padding:6px 12px;text-align:left;font-size:12px">Dias</th>
            </tr>
            {cal_rows}
        </table>"""

    paradigma_html = _html_bloque_paradigma(analisis_paradigma)

    return f"""
    <html>
    <body style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;padding:20px;color:#111;background:#fff">

    <h2 style="color:#1e3a5f;border-bottom:2px solid #e5e7eb;padding-bottom:10px;margin-bottom:8px">
        Informe Semanal &mdash; {hoy}
    </h2>

    {resumen_html}
    {recordatorio_html}

    <h3 style="color:#374151;margin:24px 0 8px;font-size:15px">Posiciones</h3>
    {bloques_empresas}

    {calendario_html}
    {paradigma_html}

    <p style="color:#9ca3af;font-size:11px;margin-top:28px;border-top:1px solid #e5e7eb;padding-top:12px">
        Generado automaticamente &middot; {hoy} {hora} UTC &middot; claude-sonnet-4-20250514 &middot; No constituye asesoramiento financiero.
    </p>
    </body></html>"""


def _generar_html_basico(data, alertas):
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
        pe_str = f"{d['pe_ratio']:.0f}x" if d.get("pe_ratio") else "-"

        bloques += f"""
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;padding:16px;margin:10px 0">
            <h3 style="margin:0 0 8px;color:#1e3a5f">{cfg['nombre']} ({symbol})</h3>
            <div style="display:flex;gap:20px;flex-wrap:wrap;font-size:13px">
                <div><span style="color:#9ca3af">Precio</span><br><strong>${d['precio']}</strong></div>
                <div><span style="color:#9ca3af">vs Entrada</span><br><strong style="color:{color_ret}">{signo}{ret:.1f}%</strong></div>
                <div><span style="color:#9ca3af">Stop Precio</span><br><strong>${sl:.2f}</strong></div>
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
                <td style="padding:6px 12px;color:{color}">{dias} dias</td>
            </tr>"""

    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;padding:20px;color:#111">
    <h2 style="color:#1e3a5f;border-bottom:2px solid #e5e7eb;padding-bottom:8px">Informe Semanal &mdash; {hoy}</h2>
    <p style="background:#eff6ff;border-left:4px solid #2563eb;padding:10px 14px;border-radius:4px">{resumen} Horizonte: 1-3 anios.</p>
    <h3 style="color:#374151;margin-top:24px">Posiciones</h3>
    {bloques}
    <h3 style="color:#374151;margin-top:24px">Earnings</h3>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
        <tr style="background:#f3f4f6">
            <th style="padding:6px 12px;text-align:left">Empresa</th>
            <th style="padding:6px 12px;text-align:left">Fecha</th>
            <th style="padding:6px 12px;text-align:left">Dias</th>
        </tr>
        {earnings_rows}
    </table>
    <p style="color:#9ca3af;font-size:11px;margin-top:24px">Informe automatico. No asesoramiento financiero.</p>
    </body></html>"""


# ── Envio de email ───────────────────────────────────────────────────────────

def enviar_email(asunto, html):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"]    = config.EMAIL_FROM
    msg["To"]      = config.EMAIL_TO
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(config.EMAIL_FROM, config.GMAIL_APP_PASSWORD)
        server.sendmail(config.EMAIL_FROM, config.EMAIL_TO, msg.as_string())
    print(f"Email enviado: {asunto}")


# ── Entry points ─────────────────────────────────────────────────────────────

def run_alertas_diarias():
    """Corre diariamente. Envia email si hay alertas de precio, tesis rota, o actualizacion pendiente."""
    print(f"[{datetime.now()}] Ejecutando chequeo diario...")
    data    = get_market_data()
    alertas = evaluar_alertas(data)

    tesis_data = cargar_tesis()
    tesis_resultados = evaluar_tesis(tesis_data)
    pendientes = necesita_actualizar_tesis()

    # Verificar paradigma solo si es lunes o hay señales previas en cache
    analisis_paradigma = None
    nivel_paradigma = "VERDE"
    if date.today().weekday() == 0:  # lunes: chequeo semanal de paradigma
        try:
            noticias_paradigma = get_news()
            analisis_paradigma = analizar_cambio_paradigma(noticias_paradigma)
            nivel_paradigma = analisis_paradigma.get("nivel_global", "VERDE")
            print(f"Paradigma (chequeo lunes): {nivel_paradigma}")
        except Exception as e:
            print(f"Error en paradigma diario: {e}")

    importantes    = [a for a in alertas if a["nivel"] in ("CRITICA", "ALTA")]
    tesis_criticas = [s for s, tr in tesis_resultados.items() if tr["estado"] == "TESIS_ROTA"]
    paradigma_critico = nivel_paradigma == "ROJO"

    if importantes or tesis_criticas or pendientes or paradigma_critico:
        html = generar_html_alerta(importantes, data, tesis_resultados, analisis_paradigma)
        n = len(importantes) + len(tesis_criticas)
        if paradigma_critico:
            asunto = f"ALERTA DE PARADIGMA — Revisar tesis de portafolio"
        elif pendientes and not importantes and not tesis_criticas:
            asunto = f"Actualizar tesis.json — {', '.join(p['symbol'] for p in pendientes)}"
        else:
            asunto = f"[{n} alerta(s)] Portafolio NVDA/TSM/PLTR"
        enviar_email(asunto, html)
    else:
        print("Sin alertas importantes. No se envia email.")


def run_informe_semanal():
    """Corre los lunes. Siempre envia el informe completo."""
    print(f"[{datetime.now()}] Generando informe semanal...")
    data    = get_market_data()
    alertas = evaluar_alertas(data)
    html    = generar_html_informe_semanal(data, alertas)
    asunto  = f"Informe Semanal - Portafolio IA ({datetime.now().strftime('%d/%m/%Y')})"
    enviar_email(asunto, html)


if __name__ == "__main__":
    import sys
    modo = sys.argv[1] if len(sys.argv) > 1 else "diario"
    if modo == "semanal":
        run_informe_semanal()
    else:
        run_alertas_diarias()
