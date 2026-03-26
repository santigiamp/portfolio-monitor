# Portfolio Monitor — NVDA / TSM / PLTR

Sistema automático de alertas y seguimiento para portafolio de acciones de IA.  
Costo: **$0**. Sin servidor. Corre en GitHub Actions.

---

## Qué hace

| Cuándo | Qué envía |
|--------|-----------|
| Lunes a viernes, 19:00 ARG | Email solo si hay alertas críticas o importantes |
| Todos los lunes, 09:00 ARG | Informe semanal completo con estado de todas las posiciones |

---

## Setup en 10 minutos

### 1. Crear el repo en GitHub

```bash
git init portfolio-monitor
cd portfolio-monitor
# Copiar los archivos monitor.py y config.py acá
# Crear la carpeta .github/workflows/ y copiar monitor.yml
```

### 2. Crear `.gitignore`

```
config.py        # Nunca subir credenciales al repo
__pycache__/
*.pyc
```

### 3. Habilitar Gmail App Password

1. Ir a [myaccount.google.com](https://myaccount.google.com)
2. Seguridad → Verificación en 2 pasos (debe estar activa)
3. Seguridad → Contraseñas de aplicaciones
4. Crear una nueva: "Portfolio Monitor"
5. Guardar los 16 caracteres que aparecen

### 4. Configurar Secrets en GitHub

En tu repo: **Settings → Secrets and variables → Actions → New repository secret**

Crear estos 6 secrets:

| Nombre | Valor |
|--------|-------|
| `NVDA_PRECIO_ENTRADA` | Tu precio de compra en USD |
| `TSM_PRECIO_ENTRADA` | Tu precio de compra en USD |
| `PLTR_PRECIO_ENTRADA` | Tu precio de compra en USD |
| `EMAIL_FROM` | tu_cuenta@gmail.com |
| `EMAIL_TO` | donde_recibes@gmail.com |
| `GMAIL_APP_PASSWORD` | Los 16 caracteres del paso anterior |

### 5. Adaptar monitor.py para leer secrets como variables de entorno

Reemplazar el import de config al inicio de monitor.py por esto:

```python
import os

class config:
    NVDA_PRECIO_ENTRADA = float(os.environ.get("NVDA_PRECIO_ENTRADA", 174.39))
    TSM_PRECIO_ENTRADA  = float(os.environ.get("TSM_PRECIO_ENTRADA", 183.00))
    PLTR_PRECIO_ENTRADA = float(os.environ.get("PLTR_PRECIO_ENTRADA", 148.82))
    EMAIL_FROM          = os.environ.get("EMAIL_FROM", "")
    EMAIL_TO            = os.environ.get("EMAIL_TO", "")
    GMAIL_APP_PASSWORD  = os.environ.get("GMAIL_APP_PASSWORD", "")
```

### 6. Subir y activar

```bash
git add .
git commit -m "Portfolio monitor inicial"
git push origin main
```

Ir a **Actions** en GitHub y verificar que el workflow está activo.  
Para probar: **Actions → Portfolio Monitor → Run workflow**.

---

## Alertas que genera

| Nivel | Cuándo |
|-------|--------|
| 🔴 CRÍTICA | Stop loss alcanzado (NVDA: -25%, TSM: -20%, PLTR: -30%) |
| 🟠 ALTA | Take profit alcanzado · Caída >5% en un día |
| 🔵 MEDIA | Precio a <10% del mínimo de 52 semanas |
| ⚪ INFO | Earnings en menos de 7 días |

---

## Actualizar cada trimestre

1. **Earnings calendar**: actualizar las fechas en `EARNINGS_CALENDAR` dentro de monitor.py
2. **Precios de entrada**: si promediás posición, actualizar en los Secrets de GitHub
3. **Umbrales**: ajustar `stop_loss_pct` y `take_profit_pct` según evolucione tu tesis

---

## Dependencias

```
yfinance    # pip install yfinance
```
Solo una dependencia. No requiere API keys de pago.

---

## Indicadores fundamentales a monitorear (por empresa)

### NVDA
- Gross margin: alerta si cae por debajo del 65%
- Data Center growth: alerta si crece menos del 20% YoY
- CapEx guidance de Microsoft, Google, Amazon, Meta (sus earnings impactan NVDA antes que los propios)

### TSM
- Utilización de fábricas: alerta si cae por debajo del 80%
- Revenue de nodos avanzados (<5nm): alerta si crece menos del 25% YoY
- Noticias geopolíticas del estrecho de Taiwan (riesgo binario)

### PLTR
- Crecimiento comercial US: alerta si cae por debajo del 40% YoY
- SBC como % del revenue: debe seguir bajando del 15% actual
- Net Revenue Retention: alerta si cae por debajo del 115%
