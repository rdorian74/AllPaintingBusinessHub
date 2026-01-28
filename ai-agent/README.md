# AI Agent Service v2 - All Painting Ltd

## Nuevas Funcionalidades (v2)

### 1. Comparación Word vs PDF
El agente ahora compara el contenido del documento Word original con el PDF generado para asegurar que:
- Todo el contenido del Word está presente en el PDF
- No se omiten secciones, bullets, o información
- Los números y precios son correctos

### 2. Detección de Problemas de Formato
- Páginas en blanco
- Páginas saltadas (1, 2, 4 - falta la 3)
- Contenido cortado
- Problemas de formato

### 3. Auto-Corrección
Si el agente detecta problemas **corregibles** (formato, páginas en blanco), automáticamente:
1. Solicita a Estimate Generator que regenere el PDF
2. Valida el nuevo PDF
3. Repite hasta 3 veces si es necesario
4. Si después de 3 intentos sigue fallando, notifica para revisión manual

### 4. Tracking de Intentos
El dashboard muestra:
- Número de intentos por validación
- Cuáles fueron auto-corregidas
- Estadísticas de éxito

---

## Archivos Incluidos

| Archivo | Descripción |
|---------|-------------|
| `app.py` | Flask API + Dashboard (actualizado) |
| `validator.py` | Lógica de validación mejorada |
| `database.py` | Base de datos con campos nuevos |
| `config.py` | Configuración con auto-corrección |
| `main.py` | Para estimate-automation (REEMPLAZAR) |
| `requirements.txt` | Incluye python-docx |

---

## Instalación

### Paso 1: Reemplazar archivos del AI Agent
Copia estos archivos a `C:\Scripts\ai-agent\`:
- app.py
- validator.py
- database.py
- config.py
- requirements.txt

### Paso 2: Actualizar estimate-automation
Copia `main.py` a `C:\Scripts\estimate-automation\` (reemplaza el existente)

### Paso 3: Instalar nueva dependencia
```bash
cd C:\Scripts\ai-agent
pip install python-docx
```

### Paso 4: Reiniciar servicios
Cierra todas las ventanas y ejecuta `run_ai_system.bat`

---

## Configuración de Auto-Corrección

En `config.py`:

```python
# Habilitar/deshabilitar auto-corrección
AUTO_CORRECTION_ENABLED = True

# Máximo de intentos de regeneración
MAX_REGENERATION_ATTEMPTS = 3

# URL del Estimate Generator (para regenerar PDFs)
ESTIMATE_GENERATOR_URL = "http://localhost:5000/api/generate"
```

---

## Flujo de Validación

```
PDF Generado
     │
     ▼
┌─────────────────────────────────────┐
│ VALIDACIÓN BÁSICA (gratis)         │
│ - ¿Email presente?                 │
│ - ¿Nombre de cliente?              │
│ - ¿Código de estimate?             │
└─────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────┐
│ VALIDACIÓN CON CLAUDE (API)        │
│ - Analiza el PDF completo          │
│ - Compara con Word original        │
│ - Detecta páginas en blanco        │
│ - Verifica formato profesional     │
└─────────────────────────────────────┘
     │
     ├── OK → Continúa (draft o send)
     │
     └── PROBLEMAS DETECTADOS
              │
              ├── Corregibles (formato)?
              │        │
              │        ▼
              │   ┌─────────────────────┐
              │   │ AUTO-CORRECCIÓN     │
              │   │ - Regenera PDF      │
              │   │ - Valida de nuevo   │
              │   │ - Max 3 intentos    │
              │   └─────────────────────┘
              │
              └── No corregibles (contenido)?
                       │
                       ▼
                  Notifica para revisión manual
```

---

## Tipos de Issues

### Corregibles (se intenta auto-corregir):
- `blank_page` - Página en blanco
- `skipped_page` - Página saltada
- `cut_off_content` - Contenido cortado
- `formatting_error` - Error de formato
- `spacing` - Problemas de espaciado

### No Corregibles (requieren revisión manual):
- `missing_content` - Contenido del Word falta en el PDF
- `missing_field` - Campo requerido falta (email, etc.)
- `wrong_data` - Datos incorrectos

---

## API Endpoint Actualizado

### POST /api/validate

```json
{
    "pdf_path": "C:/path/to/estimate.pdf",
    "extracted_data": {...},
    "estimate_code": "25C-319",
    "word_path": "C:/path/to/original.docx"  // NUEVO - opcional
}
```

### Response:

```json
{
    "passed": true,
    "issues": [],
    "confidence_score": 95,
    "cost": 0.08,
    "attempts": 2,
    "auto_corrected": true,
    "action_recommended": "send"
}
```

---

## Costos Estimados

Con auto-corrección habilitada, el costo puede aumentar si hay múltiples intentos:

| Escenario | Costo Aprox |
|-----------|-------------|
| Validación simple (1 intento) | $0.05 - $0.15 |
| Con auto-corrección (2-3 intentos) | $0.15 - $0.45 |

El dashboard muestra el costo acumulado.
