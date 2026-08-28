Genera un ticket/reporte de bug o incidencia siguiendo la plantilla estándar del equipo. Usa la conversación actual como contexto para llenar los campos. Si falta información, pregunta antes de generar.

## Plantilla

```
## Reporte: {título descriptivo del problema}

### Problema
{Descripción clara y concisa del problema. Qué pasa vs qué debería pasar.}

### Cuenta afectada
- **Cuenta:** {nombre de la cuenta} (ID: {account_id})
- **Plan/Fecha:** {fecha o plan donde se reproduce}
- **Total registros:** {cantidad total y desglose si aplica}
- **Registros afectados:** {IDs, referencias o rango afectado}

### Pasos para reproducir

1. {Paso 1 — incluir endpoint, método HTTP y payload si aplica}
2. {Paso 2 — verificación via API con el request exacto}
3. {Paso 3 — verificación en plataforma}
4. **Resultado:** {lo que sucede actualmente}

### Causa raíz
{Análisis técnico del origen del problema. Comparar comportamiento entre endpoints si aplica. Mencionar validaciones faltantes o inconsistencias.}

### Comportamiento esperado
{Lo que debería ocurrir en el flujo correcto.}

### Evidencia
- {Screenshots, datos de prueba, visitas/rutas creadas para verificar}
```

## Instrucciones

1. Analiza la conversación para extraer: qué se probó, qué falló, qué endpoints están involucrados, qué cuenta se usó.
2. Si se hicieron pruebas con la API, incluye los endpoints exactos y payloads en los pasos para reproducir.
3. Si se descubrieron diferencias de comportamiento entre endpoints, documéntalas en la causa raíz.
4. Usa lenguaje técnico pero claro — el ticket lo lee tanto el equipo de soporte como desarrollo.
5. No inventes información que no esté en la conversación. Si falta un dato clave, pregunta.
6. Si hay screenshots o datos de prueba disponibles, referenciarlos en Evidencia.
