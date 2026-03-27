# Portfolio Monitor — NVDA / TSM / PLTR

Monitor automático de portafolio para una tesis concentrada en infraestructura de IA.
Costo: **$0**. Sin servidor. Corre en GitHub Actions.

---

## La tesis de inversión

Este portafolio es una apuesta concentrada en la **dominancia de la infraestructura de IA durante los próximos 1–3 años**.

La hipótesis central: el stack actual de IA — GPU clusters (NVDA), foundry de semiconductores avanzados (TSM), y plataformas de software nativas de IA (PLTR) — va a seguir siendo el paradigma dominante al menos hasta 2027. El mercado está en las primeras etapas de un superciclo de CapEx de varios años impulsado por la demanda de los hyperscalers.

**Construcción del portafolio:** 100% concentrado en tres posiciones. Sin diversificación. El argumento es que diversificar en activos no relacionados diluiría la tesis sin reducir el riesgo real dado el horizonte temporal.

**Regla de salida:** El precio solo nunca es razón para vender. La salida se activa cuando la tesis se rompe — umbrales fundamentales específicos son violados, o un cambio genuino de paradigma en arquitectura de cómputo se vuelve evidente.

---

## Tesis por empresa

### NVIDIA (NVDA)
**Por qué tenerla:** NVDA es la única empresa con una plataforma de IA full-stack — silicon (H100/B200), software (ecosistema CUDA), networking (InfiniBand) y frameworks empresariales. El moat de CUDA tiene más de 15 años de profundidad y representa un costo de switching que AMD, Intel, ni silicon propio (TPUs, Trainium) ha erosionado significativamente. El revenue de Data Center es la línea más importante a seguir.

**La tesis se confirma con:**
| Métrica | Umbral mínimo |
|---------|--------------|
| Gross Margin | ≥ 65% |
| Crecimiento Data Center YoY | ≥ 20% |
| Operating Margin | ≥ 50% |

**La tesis se rompe si:**
- El gross margin cae por debajo del 65% (señala problemas de yields en Blackwell o presión competitiva)
- El crecimiento de Data Center desacelera por debajo del 20% YoY dos trimestres consecutivos
- Algún hyperscaler reduce órdenes de GPU YoY manteniendo su capacidad de cómputo

**Indicador clave:** El CapEx guidance de los hyperscalers (los earnings de MSFT, GOOG, AMZN y META importan más que los propios de NVDA como señal adelantada).

---

### TSMC (TSM)
**Por qué tenerla:** TSMC es un monopolio estructural. No existe otra foundry en el mundo que pueda fabricar chips sub-3nm a escala. Sin TSMC no hay Blackwell, no hay Apple Silicon, no hay chip de IA avanzado de ningún hyperscaler. El riesgo geopolítico es real pero binario — y la dependencia global de la producción taiwanesa actúa como disuasivo, no solo como riesgo.

**La tesis se confirma con:**
| Métrica | Umbral mínimo |
|---------|--------------|
| Gross Margin | ≥ 53% |
| Utilización de fábricas | ≥ 80% |
| Crecimiento Revenue Nodos <5nm YoY | ≥ 25% |

**La tesis se rompe si:**
- La utilización de fábricas cae por debajo del 80% (señala destrucción de demanda, no solo corrección de inventario)
- El crecimiento de nodos avanzados cae por debajo del 25% YoY dos trimestres seguidos
- Intel Foundry, Samsung, o un nuevo competidor demuestra yield creíble en nodos avanzados a escala

**Riesgo clave:** Geopolítica del Estrecho de Taiwán. Es un riesgo binario, no hedgeable a nivel retail. El sizing de la posición refleja esto.

---

### Palantir (PLTR)
**Por qué tenerla:** PLTR es la única empresa de software empresarial de IA con (1) contratos gubernamentales reales a escala mission-critical, (2) un negocio comercial creciendo >50% YoY, y (3) una plataforma (AIP) construida específicamente para workflows nativos de IA en lugar de bolted-on. Es la capa de software encima del buildout de hardware de IA que NVDA y TSM habilitan.

**La tesis se confirma con:**
| Métrica | Umbral |
|---------|--------|
| Crecimiento Revenue Comercial US YoY | ≥ 35% |
| Net Revenue Retention | ≥ 115% |
| SBC como % del Revenue | ≤ 20% (tendencia bajista) |
| Operating Margin | ≥ 20% |

**La tesis se rompe si:**
- El crecimiento comercial US desacelera por debajo del 35% YoY (señala que AIP no penetra el enterprise)
- El NRR cae por debajo del 115% (señala que los clientes no expanden el uso)
- El SBC revierte su tendencia hacia arriba (señala regresión a cultura pre-rentabilidad)

---

## Monitoreo de cambio de paradigma

Más allá de los fundamentales por empresa, el sistema vigila activamente **cinco riesgos estructurales** que podrían invalidar la tesis completa sin importar las métricas individuales:

| Señal | Qué rompería la tesis |
|-------|----------------------|
| **Neuromorphic Computing** | Benchmark con >10x eficiencia energética vs GPU a escala |
| **Cómputo Óptico / Fotónico** | Chip fotónico corriendo inferencia de LLM con ventaja de costo real vs GPU |
| **Arquitecturas Alternativas a Transformers** | Modelo no-transformer igualando GPT-4 class con <10% del cómputo |
| **Reversión de CapEx en Hyperscalers** | Algún hyperscaler reduce órdenes de GPU YoY mientras su capacidad de cómputo crece |
| **Restricción Energética Estructural** | Regulación que limite consumo de data centers de IA en mercados relevantes |

El informe semanal incluye una sección de **estado de paradigma** (VERDE / AMARILLO / ROJO) basada en el análisis de Claude sobre las noticias recientes contra estas señales.

---

## Cómo funciona

```
GitHub Actions (cron)
       │
       ▼
get_market_data()              ← yfinance: precios, P/E, máximo/mínimo 52 semanas
       │
       ▼
evaluar_alertas()              ← alertas de precio: stop loss, take profit, caída diaria, earnings
       │
       ▼
evaluar_tesis()                ← tesis.json vs TESIS_UMBRALES → TESIS_OK / EN_RIESGO / ROTA
       │
       ▼
analizar_cambio_paradigma()    ← Claude Sonnet: señales de paradigma desde titulares → VERDE/AMARILLO/ROJO
       │
       ▼
generar_analisis_claude()      ← Claude Sonnet: análisis semanal, señal MANTENER/VIGILAR/REVISAR
       │
       ▼
enviar_email()                 ← Gmail SMTP SSL: informe HTML al inbox
```

**Toda la lógica vive en un solo archivo: `monitor.py`**
**Los datos fundamentales viven en: `tesis.json`** — se actualizan manualmente después de cada earnings

### Modos de ejecución

| Modo | Cuándo | Qué envía |
|------|--------|-----------|
| `diario` | Lunes a viernes 19:00 ARG | Email solo si hay alertas CRÍTICA o ALTA |
| `semanal` | Todos los lunes 09:00 ARG | Informe HTML completo, siempre |

### Niveles de alerta

| Nivel | Cuándo |
|-------|--------|
| 🔴 CRÍTICA | Stop loss alcanzado (NVDA: -25%, TSM: -20%, PLTR: -30%) |
| 🟠 ALTA | Take profit alcanzado · Caída >5% en un día |
| 🔵 MEDIA | Precio a menos del 10% del mínimo de 52 semanas |
| ⚪ INFO | Earnings en menos de 7 días |

### Contenido del informe semanal

- Resumen ejecutivo (generado por Claude)
- Señal por empresa: **MANTENER** / **VIGILAR** / **REVISAR**
- Estado de tesis fundamental por empresa (TESIS_OK / TESIS_EN_RIESGO / TESIS_ROTA)
- Análisis de noticias relevantes
- Calendario de earnings (próximos 30 días)
- Estado de monitoreo de cambio de paradigma

---

## Stack técnico

- **Python 3.11** — archivo único, dependencias mínimas
- **yfinance** — datos de mercado (gratis)
- **feedparser** — RSS de Yahoo Finance para noticias (gratis)
- **anthropic** — Claude Sonnet para análisis semanal
- **Gmail SMTP** — envío de emails (gratis con App Password)
- **GitHub Actions** — scheduling y ejecución (tier gratuito)

**Costo operativo total: ~$0.02/semana** (solo las llamadas a Claude API del informe semanal)

---

## Setup

### 1. Clonar el repo

```bash
git clone https://github.com/santigiamp/portfolio-monitor.git
cd portfolio-monitor
pip install -r requirements.txt
```

### 2. Crear Gmail App Password

1. Ir a [myaccount.google.com](https://myaccount.google.com)
2. Seguridad → Verificación en 2 pasos (debe estar activa)
3. Seguridad → Contraseñas de aplicaciones
4. Crear una nueva: "Portfolio Monitor"
5. Guardar los 16 caracteres que aparecen

### 3. Configurar Secrets en GitHub

En tu repo: **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Valor |
|--------|-------|
| `NVDA_PRECIO_ENTRADA` | Tu precio de entrada en NVDA (USD) |
| `TSM_PRECIO_ENTRADA` | Tu precio de entrada en TSM (USD) |
| `PLTR_PRECIO_ENTRADA` | Tu precio de entrada en PLTR (USD) |
| `EMAIL_FROM` | tu_cuenta@gmail.com |
| `EMAIL_TO` | donde_recibes@gmail.com |
| `GMAIL_APP_PASSWORD` | Los 16 caracteres del paso anterior |
| `ANTHROPIC_API_KEY` | Tu API key de Anthropic (para el análisis semanal) |

### 4. Adaptar a tu propio portafolio

1. Editar `TICKERS` en `monitor.py` — cambiar symbols, precios de entrada, porcentajes de stop/take-profit
2. Editar `TESIS_UMBRALES` — ajustar los umbrales fundamentales a tu tesis
3. Editar `EARNINGS_CALENDAR` — actualizar con fechas reales de earnings cada trimestre
4. Editar `tesis.json` — cargar las métricas reales después de cada earnings
5. Editar `PARADIGMA_SEÑALES` — personalizar qué cambios de paradigma vigilás

### 5. Probar localmente

```bash
# Modo alertas diarias
python monitor.py diario

# Modo informe semanal
python monitor.py semanal
```

---

## Mantenimiento trimestral

Después de cada ciclo de earnings:

1. **Actualizar `tesis.json`** con las métricas reales reportadas (gross margin, tasas de crecimiento, etc.)
2. **Actualizar `EARNINGS_CALENDAR`** en `monitor.py` con las fechas del próximo trimestre
3. **Actualizar precios de entrada** en los Secrets de GitHub si promediaste la posición
4. **Revisar umbrales** en `TESIS_UMBRALES` — ajustar si la tesis evolucionó

El sistema avisa cuando `tesis.json` está desactualizado (más de 120 días desde la última actualización, o no actualizado dentro de los 14 días posteriores a un earnings).

---

## Por qué existe este proyecto

Quería un sistema que distinguiera entre dos tipos de riesgo muy distintos:

1. **Riesgo de precio** — la acción baja. Se maneja con niveles de stop loss. No es necesariamente razón para vender si la tesis está intacta.
2. **Riesgo de tesis** — la razón fundamental para tener la acción se rompe. Esta es la razón real para salir.

La mayoría de las herramientas de portafolio retail alertan sobre precio. Esta alerta sobre ambos — y los trata de forma diferente. Las alertas de precio son tácticas. Las alertas de tesis son estratégicas.

El informe semanal generado por IA fuerza una revisión estructurada de si la tesis de inversión original sigue vigente, usando datos actuales y noticias recientes.

---

*Informe automático. No constituye asesoramiento financiero.*
