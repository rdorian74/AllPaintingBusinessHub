# Estimate Automation - AI Agent Integration

## Archivos Modificados

Esta carpeta contiene los archivos modificados para integrar el AI Agent con estimate-automation.

### Archivos incluidos:

| Archivo | Cambios |
|---------|---------|
| `config.py` | Nueva sección AI_AGENT_SETTINGS con configuración del agente |
| `outlook_client.py` | Nuevas funciones `send_email()` y `send_email_with_attachment()` |
| `main.py` | Nuevo Step 2.5 con llamada al AI Agent + lógica auto/review |
| `notifications.py` | Soporte para notificaciones de auto-send |

---

## Instrucciones de Instalación

### Paso 1: Backup
```bash
# Haz backup de tus archivos actuales
cd C:\path\to\estimate-automation
copy config.py config.py.backup
copy outlook_client.py outlook_client.py.backup
copy main.py main.py.backup
copy notifications.py notifications.py.backup
```

### Paso 2: Copiar archivos nuevos
Copia los 4 archivos de esta carpeta a tu carpeta `estimate-automation`, reemplazando los existentes.

### Paso 3: Verificar configuración
Abre `config.py` y verifica:
```python
# Por defecto está en modo revisión (crea drafts)
AI_AGENT_ENABLED = True
AI_AGENT_MODE = "review"  # Cambiar a "auto" cuando tengas confianza
```

---

## Cómo Funciona

### Modo Review (Default)
```
Email de Ian → PDF generado → AI Agent valida → 
  └── Si OK → Crea draft (como antes)
  └── Si problemas → Notifica a Rodrigo
```

### Modo Auto (Futuro)
```
Email de Ian → PDF generado → AI Agent valida → 
  └── Si OK → ENVÍA email automáticamente
  └── Si problemas → Notifica a Rodrigo
```

---

## Configuración

### Variables en config.py:

```python
# Habilitar/deshabilitar el agente
AI_AGENT_ENABLED = True  # False = flujo original sin agente

# Modo de operación
AI_AGENT_MODE = "review"  # "review" o "auto"

# URL del AI Agent
AI_AGENT_API_URL = "http://localhost:5010/api/validate"

# Timeout (segundos)
AI_AGENT_TIMEOUT = 60

# Si el agente no está disponible, ¿continuar con draft?
AI_AGENT_FALLBACK_TO_DRAFT = True
```

---

## Comportamiento cuando AI Agent no está disponible

Si `AI_AGENT_FALLBACK_TO_DRAFT = True`:
- El sistema continúa funcionando
- Crea drafts como antes
- Muestra warning en consola

Si `AI_AGENT_FALLBACK_TO_DRAFT = False`:
- El procesamiento se detiene
- Notifica error a Rodrigo

---

## Nuevas Funciones en outlook_client.py

### send_email(to_email, subject, body_html)
Envía un email simple sin attachment.

### send_email_with_attachment(to_email, subject, body_html, attachment_path)
Envía un email con PDF adjunto. Usado por el AI Agent en modo "auto".

---

## Nuevos Status en la Base de Datos

| Status | Descripción |
|--------|-------------|
| `sent` | Email enviado automáticamente (modo auto) |
| `needs_review` | AI Agent encontró problemas |
| `completed` | Draft creado exitosamente (modo review) |
| `error` | Error en el procesamiento |
| `partial` | PDF generado pero draft/envío falló |

---

## Próximo Paso

Ahora necesitas crear el **AI Agent Service** (puerto 5010) que provee el endpoint `/api/validate`.

Este servicio:
1. Recibe el PDF path y datos extraídos
2. Usa Claude API para validar el PDF
3. Retorna: `{passed, issues, confidence_score, cost}`

¿Listo para crear el AI Agent Service?
