# Contrato de integración de workflows AWS

Las definiciones ASL describen orquestación; las acciones de dominio las implementan los frentes INC, TECH, PARTS, NOTIF, PLAN y BQ. Su código aún no está integrado. No se incluyen respuestas simuladas para permitir un despliegue incompleto.

Cada tarea invoca directamente el ARN de su Lambda con:

```json
{"schema_version":"1.0","action":"nombre_de_accion","context":{}}
```

`context` es el documento acumulado del workflow. La respuesta es el objeto de dominio directamente, sin wrapper HTTP ni `Payload`. Las funciones que también reciben HTTP deben distinguir `version=2.0`/`requestContext` y autorizar por ruta; el body HTTP nunca selecciona una acción interna. Los errores de validación deben lanzarse como errores Lambda, sin devolver una respuesta HTTP que el workflow interpretaría como éxito.

## Incidentes

La regla recibe `source=arquifusion.telemetry`, `detail-type=risk.detected` y entrega el evento completo. El primer estado extrae `detail` a `context.risk` y registra `execution_arn`. El evento de riesgo debe incluir su versión, operación, máquina, familia, `risk_event_id`, tiempo original, `trace_id`, señales y referencia de histórico según el contrato TEL.

| Lambda / acción | Respuesta mínima y comportamiento |
|---|---|
| incident-service / `validate_risk_event` | Evidencia validada; lanzar error si es inválida. |
| incident-service / `get_or_create_incident` | `{incident_id, created, ...}`. Dedupe y creación/actualización atómica pertenecen al dominio. `created=false` conserva el incidente y salta reservas. |
| technician-dispatch / `rank_technicians` | `{available: boolean, candidates: [...]}`. |
| parts-service / `check_parts` | `{available: boolean, inspection_required: boolean, ...}`. Inspección puede continuar con cero piezas. |
| incident-service / `try_reserve_resources` | `{status, reason, ...}`; estado entre `ASSIGNED`, `TRIAGED`, `PENDING_TECH`, `PENDING_PARTS`. Reserva coordinada y atómica de técnico, piezas e incidente. Puede lanzar `ResourceConflict` para reintento acotado. |
| incident-service / `set_outcome` | Decisión persistida desde `context.outcome`; en revisión técnica sólo cambia un incidente ya creado. |
| notification-service / `create_incident_notifications` | Resultado idempotente por evento/destinatario. Usar `context.decision` o el incidente existente. |

Las tareas mantienen resultados separados (`validation`, `incident`, `technicians`, `parts`, `reservation`, `decision`, `notifications`). `trace_id` original permanece en `context.risk`. Los errores previos a crear un incidente fallan la ejecución. Tras crearlo, los fallos de asignación intentan persistir `TRIAGED`. Si no se puede persistir una decisión, la ejecución falla y se observa en CloudWatch. Un fallo de avisos conserva la decisión y retorna `notifications.status=PENDING_RETRY`; el servicio debe permitir recuperar ese aviso con la misma clave idempotente.

## Planificación y BigQuery

Entradas manuales: `run_id`, `operation_id` y corte UTC. Scheduler aporta `scheduled_at` y un `run_id` derivado de ese tiempo; un reintento conserva la misma ventana. No usar la hora de recepción como semilla de una repetición.

| Lambda / acción | Respuesta mínima y comportamiento |
|---|---|
| maintenance-analyzer / `initialize_run` | Contexto completo normalizado con `run_id`, `operation_id`, corte, `trace_id` y `execution_arn`. Esta acción recibe también `execution_arn` del contexto de Step Functions en el nivel superior del payload. La respuesta se convierte en la raíz del workflow. |
| maintenance-analyzer / `analyze_local` | Plan persistido en `PLAN#...`, con corte, prioridad y motivos. No devolver éxito antes de persistirlo. |
| parts-service / `project_demand` | Proyección de demanda; no reserva ni consume stock. |
| notification-service / `create_plan_notifications` | Avisos idempotentes del plan a supervisores. |
| analytics-sync / `export_aggregates` | Puntero S3 del export agregado por operación/run, con cobertura. |
| analytics-sync / `start_load` y `get_load_status` | `{job_id, status, ...}`; estado `PENDING`, `SUCCEEDED` o `FAILED`. Recuperar el mismo job por ID determinista. |
| analytics-sync / `start_query` y `get_query_status` | Igual contrato, usando ubicación y parámetros consistentes. Sólo se invoca `start_query` tras carga `SUCCEEDED`. |
| analytics-sync / `publish_snapshot` | Snapshot completo y puntero activo confirmado; comprobar frescura frente a runs atrasados. |
| analytics-sync / `record_degradation` | Conservar plan y último snapshot; persistir `STALE` si hay snapshot previo o `UNAVAILABLE` si no existe. |

El workflow espera cinco segundos entre sondeos, con máximo veinte por fase. Cada invocación inicia o consulta un job; ninguna Lambda permanece esperando a BigQuery. Si falla la persistencia de frescura, el resultado indica `freshness_persisted=false`; el plan local sigue almacenado. Los fallos locales previos a confirmar el plan terminan como ejecución fallida.

Los handlers deben usar punteros a S3 y candidatos acotados para respetar el límite de payload de Step Functions. Mantener `run_id`, IDs de job y corte; no incluir credenciales ni lotes completos.
