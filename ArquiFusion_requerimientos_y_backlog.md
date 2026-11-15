# ArquiFusion | Requerimientos y backlog de implementación

Base técnica: plano serverless de nueve pestañas de `ArquiFusion_arquitectura_v3.drawio` y especificación de flujos v3. Este documento define el alcance, los archivos por crear y las pruebas para cerrar cada tarea.

**P0** permite demostrar la operación de punta a punta. **P1** completa el producto según el plano. **P2** corresponde a extensiones que se habilitan si el entorno y el tiempo lo permiten. Todas las tareas figuran pendientes.

## 1. Decisiones de implementación

| Tema | Base de trabajo |
|---|---|
| Backend | AWS Lambda en Python 3.12. ZIP con dependencias fijadas y compatibles con Amazon Linux 2023. |
| Infraestructura AWS | Un `serverless.yml` en la raíz, un stack CloudFormation por stage, archivos YAML por recurso y dos definiciones ASL. Los microservicios se separan por dominio en código, permisos y contratos. |
| Stage y región | Empezar con `dev` en una región permitida por AWS Academy Learner Lab. Pasar región, stage y roles como configuración. |
| API | Una HTTP API Gateway con payload v2.0. `/telemetry/batch` valida la credencial del productor en `ingest-api`; las rutas `/api/*` usan Lambda authorizer con Firebase y validación de permisos en el handler. |
| Datos | DynamoDB on-demand para estado operativo, incidentes, reservas, avisos y snapshots. S3 privado para histórico y exportes. |
| Web | React + TypeScript + Vite en Cloudflare Pages. Firebase Authentication con correo y contraseña. Los usuarios de demo se dan de alta por invitación/configuración. |
| Analítica multinube | `analytics-sync` envía agregados por HTTPS a BigQuery Sandbox, ejecuta SQL e importa resultados a DynamoDB. |
| Alcance inicial | La apertura y asignación de incidentes es automatizada. El técnico registra la intervención y el supervisor confirma el cierre. SNS, Streams/Pipes, réplica regional, GCS, BigQuery ML y Workers AI corresponden a P2. |

La HTTP API, Python 3.12, `t-event-dedup` en el MVP y `GET /api/me` son decisiones de implementación para concretar el plano. Firebase es el proveedor de identidad. La aplicación completa corre sobre servicios administrados, incluido el simulador invocado por Scheduler.

## 2. Requerimientos funcionales

| ID | Requerimiento | Resultado verificable |
|---|---|---|
| RF-01 | Autenticar al personal y autorizar por operación y rol. | Firebase entrega un ID token. Un perfil habilitado ve sus operaciones. Un token ausente o inválido se rechaza y una operación ajena no devuelve datos. |
| RF-02 | Cargar catálogos iniciales y asignar accesos. | El seed crea operaciones, modelos, máquinas, técnicos, stock y perfiles de demo; repetirlo conserva reservas y estado operativo. |
| RF-03 | Simular lecturas y recibir lotes autenticados. | `simulate-telemetry` genera lecturas deterministas de demo. La API devuelve `202 QUEUED` sólo si el lote quedó en SQS. |
| RF-04 | Conservar histórico y publicar estado actual. | S3 conserva el lote; DynamoDB mantiene la lectura más nueva y la última ubicación válida. Reintentos y lecturas atrasadas no corrompen el estado. |
| RF-05 | Detectar riesgo persistente y abrir incidentes. | El detector publica `risk.detected` según reglas versionadas. Un riesgo repetido actualiza el mismo incidente activo. |
| RF-06 | Priorizar y asignar técnico y repuestos. | Se obtiene `ASSIGNED`, `TRIAGED`, `PENDING_TECH` o `PENDING_PARTS` con motivo. Dos incidentes concurrentes no reservan el mismo técnico ni dejan stock negativo. |
| RF-07 | Gestionar la intervención y el cierre. | El técnico asignado inicia y resuelve. El supervisor cierra. Quedan historial, consumo real, auditoría y liberación de recursos que corresponde. |
| RF-08 | Entregar avisos por rol y destinatario. | El usuario ve y marca sus avisos. Los reintentos no duplican avisos originados por el mismo evento. |
| RF-09 | Consultar flota, incidentes, técnicos e inventario. | La SPA ofrece mapa, estado, histórico y vistas por rol con filtros, paginación y acciones permitidas. |
| RF-10 | Ejecutar la planificación preventiva. | El workflow genera prioridades, motivo y demanda sugerida con un corte temporal. Una recomendación no modifica el stock. |
| RF-11 | Calcular y consultar KPIs desde BigQuery. | Un load job y un query job reales producen un snapshot visible con fecha y fuente. Si GCP falla, se conserva el último snapshot válido y se muestra su estado de frescura. |
| RF-12 | Operar y recuperar el pipeline. | Una traza permite seguir un lote hasta su incidente. Los mensajes fallidos terminan en DLQ y pueden reprocesarse después de corregir la causa. |

## 3. Repositorio, contratos y secuencia de entrega

Los siguientes nombres son rutas de trabajo. Este backlog es el único archivo entregado en esta etapa.

```text
arquifusion/
  serverless.yml
  package.json
  package-lock.json
  requirements.txt
  requirements-dev.txt
  .env.example
  .gitignore
  README.md
  infra/             # fragmentos CloudFormation en YAML
  workflows/         # definiciones ASL en YAML
  src/               # handlers Python agrupados por dominio
  contracts/         # OpenAPI y JSON Schema
  sql/               # consultas BigQuery
  seed/              # catálogos y escenarios sintéticos
  tests/             # pruebas unitarias, de contrato y de integración
  scripts/           # smoke tests y operaciones de demo
  frontend/          # SPA React/Vite y configuración de Cloudflare Pages
```

- [ ] **BASE-01 · P0** Crear el repositorio y fijar en el `package-lock.json` la versión de la CLI de Serverless Framework acordada por el equipo. Para v4, comprobar autenticación y elegibilidad antes de depender de la CLI. Fijar dependencias Python verificadas en `requirements.txt`; usar `requirements-dev.txt` para `pytest` y validación de esquemas. Hacer una invocación de prueba al ZIP empaquetado.
- [ ] **BASE-02 · P0** Crear `src/common/http.py`, `src/common/identity.py`, `src/common/dynamo.py`, `src/common/logging.py` y `src/common/config.py`. Unificar respuesta, paginación por cursor, validación de alcance, tiempos UTC, lectura de configuración y `trace_id`. Los handlers HTTP extraen identidad del contexto de API Gateway, y la lógica de dominio se prueba fuera del handler.
- [ ] **BASE-03 · P0** Crear `contracts/openapi.yml`, `contracts/telemetry-batch.schema.json`, `contracts/telemetry-queued.schema.json`, `contracts/risk-detected.schema.json` y `contracts/domain-event.schema.json`. Versionar `schema_version` y agregar fixtures válidos e inválidos en `tests/fixtures/`. Frontend y backend usan el mismo contrato de error `{code, message, trace_id}`.
- [ ] **BASE-04 · P0** Definir en OpenAPI `400` para payload inválido, `401/403` según punto de rechazo y `409` para conflicto de estado o idempotencia. Usar `Idempotency-Key` en mutaciones de incidentes y preservar el mismo identificador al reintentar. Validar que cursores y filtros siguen acotados a la operación del solicitante.
- [ ] **BASE-05 · P0** Crear `scripts/smoke_aws.py`, `scripts/smoke_auth.py` y `scripts/smoke_bigquery.py`. Correr pruebas reducidas de despliegue, identidad y salida a GCP antes de conectar todos los módulos. Registrar comandos, recursos externos del entorno y evidencias en `README.md`.
- [ ] **BASE-06 · P1** Crear `contracts/analytics-snapshot.schema.json` y `contracts/maintenance-plan.schema.json`. Fijar convención de `period`, estado de frescura y métricas con unidad, cobertura y fuente.

### Orden y reparto de trabajo

| Frente sugerido | Implementa | Dependencias para integrar |
|---|---|---|
| Infraestructura | `BASE`, `AWS`, permisos, empaquetado, observabilidad | Primera prueba real de los roles, HTTP API, SQS y Step Functions |
| Flota e ingesta | `TEL` y `FLEET` | Catálogo base, contratos, cola, tablas y bucket |
| Operación de incidentes | `INC`, `TECH`, `PARTS` y `NOTIF` | Evento `risk.detected`, catálogos y perfiles |
| Datos y GCP | `PLAN`, `BQ` y `DASH` | Contrato de histórico, dataset, identidad de servicio y resultados de incidencias |
| Identidad y frontend | `AUTH`, `ADMIN`, `WEB` y `CF` | Proyecto Firebase, contrato OpenAPI, `/api/me`, URL API y origen de Pages |

Primer corte de integración: usuario autorizado → consulta de flota → lote → estado en DynamoDB. Segundo corte: escenario de riesgo → incidente → reserva → resolución y cierre. Tercer corte: planificación → carga y SQL en BigQuery → KPI visible en la web. Los tres cortes se comprueban en el stage de demo.

## 4. Despliegue AWS y recursos

Convención propuesta: `af-<stage>-<recurso>` para recursos nombrados y `af-<stage>-<cuenta>-<región>-telemetry-lake` para el bucket privado. `af-dev-telemetry-queue`, `af-dev-telemetry-dlq` y `af-dev-arquifusion` son ejemplos de los nombres que usarían las guías manuales. Parámetros no secretos en `.env.example` o configuración por stage. Mantener separados los nombres lógicos CloudFormation y los nombres físicos.

### Qué va en YAML

| Recurso y nombre físico propuesto | Archivo y tipo | Criterio si el entorno restringe la creación |
|---|---|---|
| Stack `af-<stage>`, Lambdas `af-<stage>-<handler>`, HTTP API `af-<stage>-api` | `serverless.yml`; `functions`, `httpApi`, rutas, authorizer. | Validar CloudFormation, bucket de artefactos y rol Lambda. Referenciar un bucket de despliegue autorizado, por ejemplo `af-<stage>-<cuenta>-<región>-artifacts` si el equipo lo preaprovisiona. La app mantiene un único dueño del Gateway y de las rutas. |
| `af-<stage>-telemetry-queue` y `af-<stage>-telemetry-dlq` | `infra/queues.yml`; `AWS::SQS::Queue`; mapping de la cola en `serverless.yml`. | Si las colas ya existen y pueden usarse, referenciar URL y ARN. El propietario define la política redrive y la Lambda se conecta por un único mapping. |
| `af-<stage>-t-*` | `infra/tables.yml`; `AWS::DynamoDB::Table` con `BillingMode: PAY_PER_REQUEST`. | Usar tablas existentes sólo si coinciden claves, GSIs, stage y acceso. Cada tabla tiene un solo dueño de despliegue. |
| Bucket `af-<stage>-<cuenta>-<región>-telemetry-lake` | `infra/storage.yml`; `AWS::S3::Bucket`; bloqueo público, cifrado y política de retención según entorno. | Si se usa un bucket preexistente, registrar propietario, nombre, región y prefijos concedidos. PITR y versionado se habilitan tras confirmar permisos y costos. |
| Bus `af-<stage>-arquifusion`, regla `af-<stage>-risk-detected` | `infra/events.yml`; `AWS::Events::EventBus` y `AWS::Events::Rule`. | Probar `PutEvents` y regla → Step Functions con el rol autorizado. Si ese destino se bloquea y el lab permite Lambda → Step Functions, documentar el cambio y usar un único disparador para cada riesgo. |
| State machines `af-<stage>-incident-workflow` y `af-<stage>-maintenance-planning` | `infra/workflows.yml`; `AWS::StepFunctions::StateMachine`, tipo `STANDARD`; ASL en `workflows/incident.asl.yml` y `workflows/maintenance.asl.yml`. | Referenciar ARN de un rol de Step Functions autorizado. Si se deniega `states:CreateStateMachine` o `iam:PassRole`, registrar el bloqueo y consultar al responsable del laboratorio. |
| `af-<stage>-simulate-telemetry` y `af-<stage>-maintenance-planning` como nombres de schedules | `infra/schedules.yml`; `AWS::Scheduler::Schedule` para Lambda y Step Functions. | Si Scheduler o su rol no están habilitados, modo demo por invocación Lambda autorizada y `POST /api/admin/analytics/run`. Una regla programada es otra opción si el lab la permite. |
| Alarmas por fallos Lambda, ejecución fallida, edad de cola y mensajes en DLQ | `infra/observability.yml`; `AWS::CloudWatch::Alarm`; log retention por stage. | Si una alarma no puede crearse, recolectar las métricas y logs disponibles y registrar el bloqueo. |
| P2 · `af-<stage>-arquifusion-events`, colas `af-<stage>-sqs-{repuestos,analitica,notificaciones}` y sus `-dlq` | `infra/fanout.yml`; `AWS::SNS::Topic`, `AWS::SNS::Subscription`, `AWS::SNS::TopicPolicy`, `AWS::SQS::Queue`, `AWS::SQS::QueuePolicy`, regla y mappings. | Si luego se usa un topic o cola existente, registrar ARN, alcance del filtro y permiso de publicación/entrega. La bandeja in-app del MVP opera con DynamoDB. |

CloudFormation permite declarar estos recursos en YAML. Su creación efectiva depende de las políticas del lab. La consola y la CLI también están sujetas a IAM. [Serverless Framework — AWS resources](https://www.serverless.com/framework/docs/providers/aws/guide/resources) · [AWS — EventBridge Scheduler en CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-scheduler-schedule.html)

### Configuración previa y tareas de despliegue

- [ ] **AWS-01 · P0** Abrir sesión de Learner Lab, cargar credenciales temporales mediante el perfil asignado y comprobar cuenta y región con `aws sts get-caller-identity`. Verificar `cloudformation`, autorización sobre S3 de artefactos y permisos del actor que despliega. No subir credenciales temporales a Git ni a Cloudflare.
- [ ] **AWS-02 · P0** Inventariar `LAMBDA_ROLE_ARN`, `SFN_ROLE_ARN`, `EVENTS_START_SFN_ROLE_ARN` y `SCHEDULER_ROLE_ARN`. Verificar `iam:PassRole` y que cada rol confíe en el principal que lo asume. Probar las acciones efectivas: Lambda accede a recursos, Step Functions invoca Lambdas, EventBridge inicia la máquina y Scheduler invoca su destino. El nombre `LabRole` por sí solo no verifica esas capacidades. Si sólo hay un rol Lambda aprobado, configurar ese ARN en `provider.iam.role` y registrar el alcance efectivo.
- [ ] **AWS-03 · P0** Crear todos los YAML base de la matriz y añadirlos a `resources` mediante imports `${file(./infra/<archivo>.yml)}`. En ASL, importar la definición en `Definition`, referenciar ARNs con intrínsecos CloudFormation y revisar los logical IDs de funciones en el template de `serverless package`. Pasar URLs para `SendMessage` y ARNs para mappings/policies. Definir nombres de tablas, bus, bucket y ARNs de workflows en el entorno de sus consumidores.
- [ ] **AWS-04 · P0** Configurar CORS con orígenes exactos, `Authorization` y `Content-Type`; agregar `Idempotency-Key` donde lo usa la SPA. Excluir el authorizer del preflight. Definir authorizer REQUEST para HTTP API v2.0 con respuestas simples y caché de decisiones desactivada inicialmente. Verificar desde `pages.dev` en navegador. [API Gateway — Lambda authorizer para HTTP API](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-lambda-authorizer.html)
- [ ] **AWS-05 · P0** Ejecutar `npm ci`, `npx serverless package --stage dev --region <región>` y, tras revisar el template resultante, `npx serverless deploy --stage dev --region <región>`. Confirmar que `package` incluye `src/`, SQL y los datos de seed limitados a demo. Excluir fixtures grandes, `.env`, credenciales, frontend y archivos locales innecesarios. Si la versión fijada incluye soporte Python nativo, activar `custom.pythonRequirements`; verificar el empaquetado Linux de las dependencias de criptografía. [Serverless Framework — Python support](https://www.serverless.com/framework/docs/providers/aws/guide/python)
- [ ] **AWS-06 · P0** Configurar cola Standard, `ReportBatchItemFailures`, visibility timeout de al menos seis veces el timeout de Lambda más la ventana de batching, y DLQ con retención mayor que la cola de origen. Probar un lote mixto y un mensaje agotando los reintentos. [AWS — Lambda y SQS](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html)
- [ ] **AWS-07 · P0** Elegir un almacén de secretos permitido. Crear por consola/CLI autorizada `/af/dev/simulator-token` y, si se eligió llave GCP, `/af/dev/gcp-bigquery-credentials` en Secrets Manager o Parameter Store SecureString si el tamaño y permisos lo permiten. Configurar los handlers con el identificador del secreto y permisos de lectura. Declarar referencias en YAML y cargar los valores en runtime. [AWS — SecureString y CloudFormation](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_PutParameter.html)
- [ ] **AWS-08 · P1** Configurar alarmas, retención de logs y `scripts/redrive_telemetry.py`. Identificar el mensaje, corregir la causa, reprocesar de forma autorizada y verificar el `batch_id`. Registrar creación manual o previa bajo nombre, ID/ARN, región, responsable y motivo; cargar esas referencias al stack sin duplicar los recursos.
- [ ] **AWS-09 · P0** Publicar como outputs `HttpApiUrl`, `TelemetryQueueUrl`, `IncidentWorkflowArn` y `MaintenancePlanningWorkflowArn`. Configurar los schedules inicialmente deshabilitados hasta cargar catálogos y verificar el recorrido. Como punto de partida para dev, usar rate de un minuto durante la demo de telemetría y una hora para el plan, ajustados a las cuotas. Registrar cómo pausarlos antes de terminar la demo.

- [ ] **AWS-10 · P0 si se requiere intervención manual** Si el laboratorio suministra colas o permite crearlas por consola, crear primero `af-<stage>-telemetry-dlq` y luego `af-<stage>-telemetry-queue` como Standard. En la segunda, fijar redrive a la primera, cinco recepciones y los tiempos del ejemplo. Registrar URL y ambos ARNs. Crear el mapping en exactamente un lugar y verificar la respuesta parcial. Para SNS P2, crear el topic antes de suscripciones; crear cada DLQ antes de su cola, aplicar política de cola restringida al topic, agregar suscripción con filtro y probar un mensaje por tipo. Los nombres y filtros están en la sección 7.

### Variables que pasan entre módulos

| Consumidor | Configuración a pasar desde el stack o el entorno |
|---|---|
| `simulate-telemetry`, `ingest-api` | `TELEMETRY_POST_URL` en el simulador, `SIMULATOR_SECRET_ID` en ambos y `TELEMETRY_QUEUE_URL` en ingesta. Configurar `producer_id` y los ámbitos permitidos al productor. |
| `process-telemetry`, `fleet-api` | `TELEMETRY_BUCKET`, `MACHINES_TABLE`, `MACHINE_MODELS_TABLE`, `EVENT_DEDUP_TABLE` en el procesador y `EVENT_BUS_NAME` en el publicador. |
| Auth, APIs y admin | `FIREBASE_PROJECT_ID` para el authorizer; `USERS_TABLE` en la autorización; `OPERATIONS_TABLE` para catálogos y alcance; `MAINTENANCE_WORKFLOW_ARN` en `catalog-admin`. |
| Incidentes, técnicos y partes | `INCIDENTS_TABLE`, `ACTIVE_INCIDENTS_TABLE`, `MAINTENANCE_EVENTS_TABLE`, `TECHNICIANS_TABLE`, `PARTS_TABLE`, `PART_RESERVATIONS_TABLE` para las funciones que las consumen. |
| Avisos y analítica | `NOTIFICATIONS_TABLE`, `ANALYTICS_TABLE`, `GCP_PROJECT_ID`, `BQ_DATASET`, `BQ_LOCATION` y referencia `GCP_CREDENTIALS_SECRET_ID` sólo si el método es llave. Mantener separados los ID de proyecto Firebase y BigQuery. |

El despliegue obtiene los roles por stage. En una cuenta con roles diferentes para el simulador y ingesta, limitar a ambos a la lectura del secreto compartido y otorgar a ingesta únicamente el permiso de encolar en la cola de telemetría, además de sus lecturas de catálogo.

### Tablas de DynamoDB y claves

Cada nombre lógico de la primera columna se prefija con `af-<stage>-`. Usar claves materializadas para valores compuestos. Tiempo ordenable en UTC con formato fijo o epoch, según se especifique en cada índice.

| Tabla | PK · SK | Consultas e índices previstos |
|---|---|---|
| `t-operations` | `operation_id` | Operación, zonas, almacenes y política de planificación. |
| `t-machine-models` | `model_id` | Umbrales, perfiles de mantenimiento y compatibilidad. |
| `t-machines` | `machine_id` | GSI `by-operation`: `operation_id` · `machine_id`. Última lectura, GPS, estado, ventana resumida y versión. |
| `t-event-dedup` | `event_id` | TTL `expires_at` en epoch-segundos. Marcador de procesamiento y riesgo pendiente de publicar. |
| `t-incidents` | `incident_id` | GSI `by-machine`: `machine_id` · `opened_key`. GSI `by-operation`: `operation_id` · `opened_key`. GSI `by-operation-status`: `operation_status` · `opened_key`. |
| `t-active-incidents` | `active_key` | Valor `machine_id#anomaly_family`, asociado a `incident_id`. |
| `t-maintenance-events` | `machine_id` · `event_key` | `event_key = performed_at#maintenance_id`. Guarda intervención/auditoría. GSI opcional `by-incident`. |
| `t-technicians` | `technician_id` | GSI `by-operation-availability`: `operation_availability` · `zone_technician`; incluye turno, skills y asignación. |
| `t-parts` | `warehouse_id` · `part_id` | Consulta por almacén. `on_hand`, `reserved`, `available` y punto de reposición. |
| `t-part-reservations` | `incident_id` · `stock_key` | `stock_key = warehouse_id#part_id`. Cantidad y estado de la reserva. |
| `t-users` | `firebase_uid` | `enabled` y mapa de roles por `operation_id`; se usa para autorización. Alias `t-user-access` en el plano. Para la demo, acotar la enumeración de destinatarios; incluir un índice de membresías si la escala lo exige. |
| `t-notifications` | `user_id` · `notification_key` | `notification_key = created_at#notification_id`. Bandeja por destinatario. |
| `t-analytics` | `operation_id` · `snapshot_key` | `snapshot_key = period#metric_id`; usar prefijos separados para plan, KPI BigQuery, puntero activo y extensiones. |

`opened_key = opened_at#incident_id`, `operation_status = operation_id#status`, `operation_availability = operation_id#availability` y `zone_technician = zone_id#technician_id`. Los índices sirven para consultas; las transiciones y reservas se validan con escrituras condicionadas sobre los ítems base.

## 5. Backlog por microservicio

Cada función en `serverless.yml` referencia `src.<dominio>.<módulo>.handler`. Los handlers usados por Step Functions exponen acciones internas con payload versionado. Cuando una función atiende además una ruta pública, el handler usa el contrato HTTP y reduce las operaciones disponibles según la ruta; el body del cliente no selecciona acciones internas.

### MS-01 · Identidad y catálogos — RF-01 y RF-02

**Lambdas:** `firebase-authorizer`, `catalog-admin`. **Datos:** `t-users`, `t-operations`, `t-machine-models`, `t-machines`, `t-technicians`, `t-parts`.

- [ ] **AUTH-01 · P0** Crear `src/auth/firebase_authorizer.py` y `src/auth/firebase_tokens.py`. Validar ID token con RS256, `kid`, certificado público vigente, `aud` del proyecto, `iss=https://securetoken.google.com/<proyecto>`, `exp`, `iat`, `auth_time` y `sub` válido. Usar biblioteca JWT con criptografía. Cachear certificados según `Cache-Control`, con consulta acotada cuando rote la clave. La verificación de firma usa claves públicas y el ID del proyecto. [Firebase — Verificar ID tokens](https://firebase.google.com/docs/auth/admin/verify-id-tokens)
- [ ] **AUTH-02 · P0** Validar perfil habilitado y mapa de roles por operación en `t-users`. El authorizer entrega un `uid` verificado en el contexto. Cada Lambda revalida el alcance de la operación y del recurso. Implementar `GET /api/me` en `dashboard-api` para que la SPA obtenga roles y operaciones permitidas.
- [ ] **AUTH-03 · P0** En Firebase Console crear o asociar un proyecto y registrar la app web `arquifusion-web-dev`. Habilitar Email/Password, crear usuarios de demo para Operador, Técnico, Supervisor, Gerencia y Admin, vincular el UID de prueba del técnico a su `technician_id`, y registrar los dominios de Pages utilizados y `localhost` sólo en desarrollo si se necesita. Probar un token emitido por otro proyecto, token vencido, usuario deshabilitado y operación ajena. El identificador de proyecto/UID nunca se toma de un campo libre enviado por el cliente. [Firebase — Authorized domains](https://firebase.google.com/docs/auth/faq-and-troubleshooting)
- [ ] **ADMIN-01 · P0** Crear `src/admin/catalog_admin.py`, `src/admin/seed_service.py` y `seed/demo_catalog.json`. `POST /api/admin/seed` sólo es Admin en el stage de demo. Cargar una operación de ejemplo, zonas, modelos, flota, técnicos, stock y perfiles con IDs estables. Crear ítems ausentes y reportar conflictos. Preservar estado, inventario y reservas al repetir la carga. Obtener los UID del entorno desde un mapeo de demo provisto al seed.
- [ ] **ADMIN-02 · P0** `POST /api/admin/analytics/run` permite Admin o Supervisor de esa operación. Validar el corte y el rango permitido, crear `run_id`, invocar `StartExecution` sobre `MaintenancePlanningWorkflow` y devolver `202` con `run_id`. Configurar idempotencia del inicio y registrar UID.
- [ ] **AUTH-04 · P0** Crear `tests/unit/test_firebase_tokens.py`, `tests/unit/test_catalog_seed.py` y `tests/integration/test_auth_scope.py`. Verificar 200 con perfil autorizado, rechazo de solicitudes inválidas y 403 transversal entre operaciones.

**Permisos mínimos de demo.** Operador consulta flota y resumen de incidentes. Técnico consulta su operación y ejecuta acciones sobre sus incidentes asignados. Supervisor gestiona cierre, reasignación, técnicos, inventario y planificación de su operación. Gerencia consulta KPIs y vistas de resumen. Admin gestiona seed y soporte auditado. Cada usuario accede a su propia bandeja.

### MS-02 · Telemetría y flota — RF-03, RF-04, RF-05 y RF-09

**Lambdas:** `simulate-telemetry`, `ingest-api`, `process-telemetry`, `fleet-api`. **Recursos:** `telemetry-queue`, `telemetry-dlq`, S3 `telemetry-lake`, `t-machines`, `t-event-dedup` y bus EventBridge.

- [ ] **TEL-01 · P0** Crear `src/telemetry/simulate_telemetry.py`, `src/telemetry/scenarios.py` y `seed/telemetry_scenarios.json`. Generar escenarios normal, pico aislado, anomalía persistente y llegada fuera de orden. Usar `source=SIMULATED`, fecha UTC y `batch_id`/eventos estables por ejecución y posición. Enviar lotes por `POST /telemetry/batch` con token de equipo. Usar timestamp programado o run ID explícito como semilla; repetir fallos transitorios con los mismos IDs y payload.
- [ ] **TEL-02 · P0** Crear `src/telemetry/ingest_api.py` y `src/telemetry/validation.py`. Validar token de productor y su alcance, `schema_version`, timestamps y tamaño efectivo del mensaje SQS. Propuesta inicial: hasta 20 lecturas y 128 KiB para mensaje serializado. Validar cada máquina contra `operation_id` y las reglas del modelo. Usar `SendMessage` y devolver `202` con `batch_id`, estado y `trace_id` tras confirmación; `503` para fallo de encolado. Documentar `400/401/403/413/429` en OpenAPI.
- [ ] **TEL-03 · P0** Crear `src/telemetry/process_telemetry.py`, `src/telemetry/store.py` y `src/telemetry/risk_detector.py`. Consumir SQS con respuesta parcial `batchItemFailures`, identificando el `messageId`. Escribir primero cada lote en `raw/operation_id=<id>/date=<UTC>/hour=<UTC>/<batch_id>.jsonl` con clave derivada de los datos originales. Un replay idéntico reutiliza el objeto; un payload distinto con la misma clave genera conflicto trazable.
- [ ] **TEL-04 · P0** Procesar secuencialmente por máquina y tiempo dentro del lote. Actualizar `t-machines` sólo si la lectura es nueva, con condición sobre tiempo/versión, y conservar la última coordenada válida. Mantener una ventana acotada por modelo. Las lecturas tardías quedan en S3; la demo no recalcula retrospectivamente el score.
- [ ] **TEL-05 · P0** Combinar temperatura, vibración, presión u otras señales configuradas. Requerir umbral y persistencia. Publicar `risk.detected` en el bus con `source=arquifusion.telemetry`, `risk_event_id` estable, familia, severidad, señales y `history_ref`. Confirmar resultado de cada entrada de `PutEvents`. Actualizar estado de máquina y marcador por evento en transacción; guardar en el marcador el riesgo pendiente de publicar y marcarlo enviado tras confirmación. Un fallo entre publicación y confirmación puede duplicar la entrega, y se absorbe en incidentes.
- [ ] **FLEET-01 · P0** Crear `src/fleet/fleet_api.py` y `src/fleet/repository.py`. Implementar `GET /api/fleet?operation_id=&cursor=` y `GET /api/machines/{id}`. Consultar GSI por operación, aplicar proyección por rol y exponer estado, posición válida, riesgo, horas y última lectura con tiempo. Un perfil nunca lista todo el almacén de datos.
- [ ] **FLEET-02 · P1** Crear `src/fleet/history.py`. Implementar `GET /api/machines/{id}/history?from=&to=&cursor=` con rango acotado, prefijos S3 por operación, paginación y agregación según cobertura. Entregar series o resúmenes y trazabilidad; los objetos permanecen privados.
- [ ] **TEL-06 · P0** Crear `tests/unit/test_telemetry.py` y `tests/integration/test_ingestion.py`. Probar token inválido, productor de otra operación, SQS caído, lote repetido, mensaje parcial, atraso y reintento tras falla de publicación. Fixture normal no genera incidente; el persistente sí.

### MS-03 · Incidentes e historial — RF-05, RF-06 y RF-07

**Lambdas:** `incident-api`, `incident-service`. **Workflow:** `IncidentWorkflow`. **Datos:** `t-incidents`, `t-active-incidents`, `t-maintenance-events`.

- [ ] **INC-01 · P0** Crear `workflows/incident.asl.yml`, `src/incidents/incident_service.py`, `src/incidents/repository.py` y `src/incidents/state_machine.py`. La regla de EventBridge filtra `source` y `detail-type=risk.detected`; el workflow normaliza `detail`. Validar máquina, familia y operación. Crear incidente y `active_key` en una transacción. Una carrera recupera el incidente ganador. Registrar `RISK#<risk_event_id>` en `t-event-dedup` junto con la escritura del incidente o de su evidencia, para absorber replays incluso después de cerrar. Alinear TTL con la ventana admitida de reenvío. Una medición antigua no reemplaza evidencia reciente.
- [ ] **INC-02 · P0** En ASL, hacer explícitos `ValidateRiskEvent → GetOrCreateIncident → RankTechnicians → CheckParts → TryReserveResources → SetOutcome → CreateNotifications`, con ramas para riesgo existente, técnico ausente, stock insuficiente e inspección. `TRIAGED` identifica revisión o inspección; confirmar `ASSIGNED` antes de iniciar el trabajo. Una inspección asignada puede avanzar con técnico y cero repuestos. Incorporar `Retry` acotado y `Catch` a revisión técnica. Ante un fallo de avisos, conservar la asignación confirmada y permitir reintento idempotente del aviso.
- [ ] **INC-03 · P0** Crear `src/incidents/incident_api.py`. Implementar `GET /api/incidents?operation_id=&status=&cursor=` y `GET /api/incidents/{id}`. Las listas requieren operación autorizada, y el detalle aplica permisos por rol y asignación. Consultar el índice adecuado para listado con/sin estado.
- [ ] **INC-04 · P0** Implementar `POST /api/incidents/{id}/start`, `/resolve` y `/close`. Reglas: `ASSIGNED → IN_PROGRESS`; `IN_PROGRESS → RESOLVED`; `RESOLVED → CLOSED`. El técnico asignado registra inicio y resolución; el supervisor autorizado valida cierre. En resolución guardar intervención y consumo real en transacción con su estado. En cierre, liberar técnico y lock de familia sólo si pertenecen a ese incidente. Mantener actor, hora, motivo, notas y claves de idempotencia. Para la misma clave y el mismo payload, devolver el resultado previo; si cambia el payload, devolver 409.
- [ ] **INC-05 · P1** Implementar `POST /api/incidents/{id}/reassign` para Supervisor. Validar disponibilidad del nuevo técnico y hacer el cambio y la liberación del anterior en una transacción. Guardar auditoría y notificar al destinatario correcto. Para recuperar pendientes, reevaluar elegibilidad de técnico y repuestos mediante el servicio de dominio.
- [ ] **INC-06 · P0** Crear `tests/unit/test_incident_state.py` y `tests/integration/test_incident_workflow.py`. Probar dos alertas iguales, dos ejecuciones concurrentes, transiciones prohibidas, resolución repetida, cierre auditado y apertura posterior de un nuevo incidente tras liberar el lock. Propagar `trace_id` y `executionArn`.

### MS-04 · Técnicos — RF-06 y RF-09

**Lambda:** `technician-dispatch`. **Datos:** `t-technicians`.

- [ ] **TECH-01 · P0** Crear `src/technicians/technician_dispatch.py`, `src/technicians/ranking.py` y `src/technicians/repository.py`. Buscar técnicos por operación y disponibilidad. Filtrar skills, turno y zona. Ordenar por cercanía y carga con desempate estable; devolver candidatos acotados para el workflow.
- [ ] **TECH-02 · P0** Usar asignación condicionada por disponibilidad y turno vigentes. Incluir identidad del incidente asignado y comprobarla al liberar. `incident-service` coordina transacción con stock y estado; el ranking por GSI orienta la selección y la transacción decide.
- [ ] **TECH-03 · P1** Implementar `GET /api/technicians?operation_id=&zone_id=&cursor=` para Supervisor autorizado. Exponer disponibilidad, habilidades y turno, con datos de ubicación limitados según rol. Crear `tests/unit/test_technician_ranking.py` y una prueba de competencia por el mismo técnico.

### MS-05 · Repuestos e inventario — RF-06, RF-07 y RF-10

**Lambda:** `parts-service`. **Datos:** `t-parts`, `t-part-reservations`, `t-machine-models`.

- [ ] **PARTS-01 · P0** Crear `src/parts/parts_service.py`, `src/parts/reservations.py` y `src/parts/repository.py`. Consultar BOM/reglas y stock del almacén autorizado. Retornar disponibilidad y causa de bloqueo. Cuando falta diagnóstico, ofrecer inspección sin asociar una pieza por inferencia.
- [ ] **PARTS-02 · P0** Construir operaciones transaccionales de reserva, consumo y liberación. Mantener `available = on_hand - reserved` como invariante con contadores actualizados juntos, y condición `available >= cantidad` al reservar. Hacer estable la clave de reserva por incidente y stock. Resolver repuestos usados y sobrantes con condiciones sobre el estado de la reserva. Reintentos, escasez y concurrencia no deben descontar dos veces.
- [ ] **PARTS-03 · P1** Implementar `GET /api/parts?warehouse_id=&cursor=` para Supervisor o perfil autorizado. Verificar que el almacén corresponde a una operación permitida. Para planificación, devolver demanda sugerida por almacén y pieza como proyección separada del inventario. Crear `tests/integration/test_stock_reservation.py`.

### MS-06 · Notificaciones — RF-08

**Lambda:** `notification-service`. **Datos:** `t-notifications`, perfiles de `t-users`.

- [ ] **NOTIF-01 · P0** Crear `src/notifications/notification_service.py`, `src/notifications/recipients.py` y `src/notifications/repository.py`. Resolver destinatarios habilitados de la operación. Generar aviso para técnico asignado, supervisor en pendientes/escalamiento y perfiles autorizados según prioridad. La clave se deriva de evento, destinatario y tipo de aviso, con timestamp estable.
- [ ] **NOTIF-02 · P0** Implementar `GET /api/notifications?cursor=` y `PATCH /api/notifications/{id}`. Leer por UID autenticado y marcar como leído con condición de propiedad. Definir un identificador de API que permita reconstruir el SK y verificar el destinatario de forma directa.
- [ ] **NOTIF-03 · P0** Crear `tests/unit/test_notification_rules.py` y probar aviso duplicado, destinatario deshabilitado y acceso a aviso de otra cuenta. `incident-service` y el workflow de mantenimiento deben poder reintentar crear avisos tras persistir la decisión.

### MS-07 · Planificación preventiva y analítica local — RF-10

**Lambdas:** `maintenance-analyzer`, `parts-service`, `notification-service`. **Workflow:** `MaintenancePlanningWorkflow`.

- [ ] **PLAN-01 · P0** Crear `workflows/maintenance.asl.yml`, `src/maintenance/maintenance_analyzer.py` y `src/maintenance/recommendations.py`. Recibir `run_id`, `operation_id` y corte explícitos; si Scheduler envía un timestamp, inicializar una ventana UTC determinista. Leer flota acotada o paginada y mantenimiento previo. Estimar horas restantes, tendencia y criticidad. Persistir las recomendaciones mínimas y el corte en una proyección `PLAN#…` antes de iniciar la fase externa. Cada recomendación indica motivo, prioridad y fecha de corte; si falta información, marcar `INSUFFICIENT_DATA`.
- [ ] **PLAN-02 · P1** Crear `src/maintenance/common_patterns.py`. Agrupar anomalías por zona, ventana y familia. Formular una hipótesis para revisión. Usar `parts-service` para demanda sugerida y publicar resultados `PLAN#…` en `t-analytics`, con avisos de supervisor por `notification-service`.
- [ ] **PLAN-03 · P0** Definir en ASL la ruta local antes de la fase externa. Si BigQuery falla, conservar plan local y registrar `STALE` o `UNAVAILABLE` según exista snapshot previo. Usar `Wait` y límite de sondeos; evitar mantener Lambda esperando un job. Probar inicio manual y plan sin conectividad a GCP en `tests/integration/test_maintenance_workflow.py`.

### MS-08 · BigQuery y API de KPIs — RF-11

**Lambdas:** `analytics-sync`, `dashboard-api`. **Datos:** S3 `raw/`, `curated/` o `analytics-export/`, BigQuery Sandbox y `t-analytics`.

- [ ] **BQ-01 · P0** En Google Cloud crear o identificar el proyecto, habilitar BigQuery API, confirmar que Sandbox y los permisos sirven para load/query jobs y crear el dataset `arquifusion_dev` con una ubicación elegida y documentada, por ejemplo `US`. La misma ubicación se usa al crear, consultar y recuperar jobs. Preparar un staging acotado con vencimiento. Verificar cuotas, caducidad y restricciones de Sandbox antes de automatizar. [BigQuery Sandbox](https://docs.cloud.google.com/bigquery/docs/sandbox)
- [ ] **BQ-02 · P0** Crear o autorizar `af-bigquery-dev` como identidad de servicio para jobs. Conceder `roles/bigquery.jobUser` en el proyecto que crea los jobs y permiso de datos sobre el dataset, por ejemplo `roles/bigquery.dataEditor` limitado a `arquifusion_dev`. Probar Workload Identity Federation si el equipo puede limitar el proveedor al rol AWS autorizado y la Lambda puede intercambiar credenciales. Si no es viable y GCP autoriza una llave, guardarla en el almacén AWS aprobado de `AWS-07` y planificar su revocación/rotación. Esta identidad se usa en backend; Firebase autentica personas. [BigQuery — Jobs programáticos](https://docs.cloud.google.com/bigquery/docs/running-jobs) · [Google Cloud — Workload Identity Federation](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-other-clouds)
- [ ] **BQ-03 · P0** Crear `src/analytics/analytics_sync.py`, `src/analytics/export.py`, `src/analytics/bigquery_client.py` y `src/analytics/snapshots.py`. Leer sólo la partición/rango de operación. Preparar JSONL agregado con `operation_id`, fecha, modelo, máquina, tiempo activo/observado y combustible integrado sobre intervalos válidos. Excluir brechas y datos insuficientes del denominador; anotar cobertura. Guardar el export en una clave por `run_id`, y devolver un puntero al workflow.
- [ ] **BQ-04 · P0** Crear `sql/utilization_by_model.sql` y `sql/fuel_by_machine.sql`. Enviar el archivo como load job mediante la API/SDK de BigQuery a un staging por ejecución con ID seguro y estable. No depender de GCS ni de streaming. Sondear load job hasta éxito real antes de iniciar query job. Parametrizar operación y fechas, acotar bytes consultados y recuperar resultados sólo tras éxito del query. Usar IDs deterministas por fase para recuperar el mismo job después de un reintento. [BigQuery — Cargas por lotes](https://docs.cloud.google.com/bigquery/docs/batch-loading-data)
- [ ] **BQ-05 · P0** Importar métricas con `computed_at`, `source=BIGQUERY`, cobertura y `run_id`. Escribir filas por ejecución y publicar el puntero activo sólo al finalizar el lote, con condición de frescura. Mantener separadas las claves `BIGQUERY#…` y `PLAN#…`. Un fallo registra frescura sin pisar valores previos; un run atrasado no invalida el snapshot más nuevo.
- [ ] **DASH-01 · P0** Crear `src/analytics/dashboard_api.py` y `src/analytics/dashboard_queries.py`. Implementar `GET /api/analytics?operation_id=&period=` y el perfil `GET /api/me` de AUTH-02. Entregar KPIs autorizados con unidad, fuente, corte, `computed_at` y estado `FRESH/STALE/UNAVAILABLE`. Mostrar el plan local desde su proyección aunque haya degradación en GCP.
- [ ] **BQ-06 · P0** Desde una Lambda desplegada cargar un fixture pequeño, consultar y guardar un resultado real. Registrar `load_job_id`, `query_job_id`, ubicación, `run_id` y lectura de DynamoDB con valores sintéticos. Probar error de credenciales o timeout controlado; conservar el snapshot anterior. Crear `tests/unit/test_analytics_aggregates.py` y `tests/integration/test_bigquery_roundtrip.py`.

## 6. Frontend y verificación de Cloudflare Pages

**Proyecto:** `frontend/` · **Hosting de dev:** `arquifusion-web-dev` · **Flujo:** navegador → Firebase → HTTP API Gateway. La SPA usa la API de AWS para consultar KPIs, flota, historial y avisos.

- [ ] **WEB-01 · P0** Crear `frontend/package.json`, `frontend/package-lock.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx` y `frontend/.env.example`. Configurar router, layout, tema y validación de build con `npm ci && npm run build`.
- [ ] **WEB-02 · P0** Crear `frontend/src/auth/firebase.ts`, `frontend/src/auth/AuthProvider.tsx`, `frontend/src/auth/ProtectedRoute.tsx`, `frontend/src/api/client.ts` y `frontend/src/api/types.ts`. Leer la sesión con el SDK de Firebase, obtener ID token actualizado, enviarlo en `Authorization: Bearer …` y consultar `/api/me`. Manejar inicio/cierre de sesión, un reintento de refresh ante token expirado, 403 persistente, tiempo de espera y abortos. Delegar la persistencia y renovación de sesión al SDK de Firebase.
- [ ] **WEB-03 · P0** Implementar el flujo de login, selección de operación, flota, incidentes y avisos. Mostrar acciones según el alcance retornado por `/api/me`; el backend conserva la validación de cada acción. En mutaciones mostrar 409, refrescar el detalle y preservar la clave en reintentos de la misma operación.
- [ ] **WEB-04 · P1** Agregar vistas técnicas, inventario, histórico y planeamiento según la matriz. Usar polling moderado para flota/avisos y refresco manual para KPIs, con cancelación al cambiar de operación o salir de la pantalla. Incluir carga, estados vacíos, errores y fecha visible de actualización. Mantener coordenadas sin ubicación como estado explícito.
- [ ] **WEB-05 · P0** Mostrar estado de BigQuery en la vista de KPIs. Si está obsoleto, mostrar el último `computed_at` y el estado. Si todavía no hay un snapshot, mostrar ese estado y conservar el acceso al plan preventivo local.
- [ ] **WEB-06 · P1** Crear `frontend/tests/auth.spec.ts`, `frontend/tests/incident-lifecycle.spec.ts` y `frontend/playwright.config.ts`. Probar login, rutas privadas, cambios de operación, intervención/cierre y KPI obsoleto desde el navegador en Pages.

| Vista y archivo en `frontend/src/pages/` | API y acciones | Prioridad |
|---|---|---|
| `LoginPage.tsx` y `OperationSelectPage.tsx` | Firebase sign-in/sign-out; `GET /api/me`; seleccionar sólo la operación disponible para el usuario. | P0 |
| `FleetPage.tsx` y `MachineDetailPage.tsx` | `GET /api/fleet` y `/api/machines/{id}`; tarjetas de estado, filtros y mapa. Agregar histórico vía `/history` en P1. | P0/P1 |
| `IncidentsPage.tsx` y `IncidentDetailPage.tsx` | Lista por estado, detalle, iniciar, resolver y cerrar según permiso. Reasignación en P1. | P0/P1 |
| `TechniciansPage.tsx` | Disponibilidad, turno, habilidades y zona. | P1 |
| `InventoryPage.tsx` | Stock por almacén, unidades libres/reservadas y demanda sugerida desde analítica. | P1 |
| `AnalyticsPage.tsx` | KPIs, unidad, origen y frescura. Plan preventivo y causas comunes cuando hay evidencia. | P0/P1 |
| `NotificationsPage.tsx` | Bandeja propia, marcas de lectura y enlaces a incidencias permitidas. | P0 |
| `DemoAdminPage.tsx` | Panel de demo para seed y arranque manual del plan si se habilita. La API y los scripts bastan para ejecutar ambas operaciones en P0. | P1 |

- [ ] **CF-01 · P0** Crear el proyecto Pages `arquifusion-web-dev` en Cloudflare y conectar el repositorio. Configurar directorio raíz `frontend`, comando `npm run build` y salida `dist`; fijar la versión Node compatible con el proyecto. Como alternativa autorizada, usar un proyecto Direct Upload para publicar `dist/`. Documentar qué método se escogió y quién administra el proyecto. [Cloudflare — React](https://developers.cloudflare.com/pages/framework-guides/deploy-a-react-site/) · [Cloudflare — Build configuration](https://developers.cloudflare.com/pages/configuration/build-configuration/)
- [ ] **CF-02 · P0** Configurar `VITE_API_BASE_URL`, `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID` y `VITE_FIREBASE_APP_ID` para el entorno de build. Son valores de configuración pública de la SPA. Mantener credenciales de AWS/GCP, tokens de equipos y secretos de Workers sólo en backend. Registrar la URL exacta resultante de Pages en CORS y dominios autorizados de Firebase; configurar previews sólo para los orígenes que realmente se usan.
- [ ] **CF-03 · P0** Verificar HTTPS, login, logout, refresh de una ruta interna, llamadas con token, preflight CORS desde Pages y bloqueo de un origen fuera de la lista. Usar el comportamiento SPA de Pages o definir fallback de rutas si se introduce una página 404 propia. Guardar la URL y evidencia de navegador. [Cloudflare — Serving Pages](https://developers.cloudflare.com/pages/configuration/serving-pages/)
- [ ] **CF-04 · P1** Verificar mapa y atribución del proveedor de tiles que use el equipo. Mostrar la lista de equipos aunque no haya tiles o coordenadas. Revisar configuración por entorno para que previews no apunten por error a una API o proyecto Firebase distinto.

## 7. Extensiones del diagrama — P2

### SNS y SQS por consumidor

- [ ] **EVT-01** Crear `infra/fanout.yml` e importarlo sólo en el perfil de extensión. Crear topic `af-<stage>-arquifusion-events`, permisos EventBridge → SNS → SQS y filtros `MessageBody` con entrega cruda. La regla publica tipos de evento explícitos. Cada cola tiene `RedrivePolicy`, DLQ y mapping con la Lambda indicada. [AWS — SNS, filtros de suscripción](https://docs.aws.amazon.com/sns/latest/dg/sns-subscription-filter-policies.html)
- [ ] **EVT-02** Crear `src/events/update_parts_demand.py`, `src/events/update_indicators.py` y `src/events/process_notification.py`. Fijar `event_id` y `operation_id` en el contrato. Los consumidores actualizan proyecciones o entregan avisos; si incrementan métricas, registrar el evento y hacer la escritura del KPI en una operación atómica. Crear `tests/integration/test_sns_fanout.py` para filtro, duplicado y DLQ.

| SQS física · DLQ | Filtro `detail-type` | Consumidor y destino |
|---|---|---|
| `af-<stage>-sqs-repuestos` · mismo nombre con `-dlq` | `maintenance.recommended` | `update-parts-demand` → `t-analytics` con prefijo `PART_DEMAND#`. |
| `af-<stage>-sqs-analitica` · `-dlq` | `incident.resolved`, `incident.closed` | `update-indicators` → `t-analytics` con prefijo `INCIDENT_KPI#`. Distinguir la contribución de cada transición. |
| `af-<stage>-sqs-notificaciones` · `-dlq` | `incident.assigned`, `incident.pending`, `incident.escalated` | `process-notification` → avisos externos por audiencia autorizada. Si se usa email/SMS, confirmar suscripciones y cuotas. |

Los productores de dominio publican estos eventos después de confirmar el cambio. Definir el contrato y la reanudación de eventos pendientes antes de activar consumidores. La bandeja base sigue persistiendo con `notification-service`.

### Otras integraciones opcionales

- [ ] **EXT-01** Para el disparador alternativo, crear `infra/risk-pipe.yml`, tabla inmutable `af-<stage>-t-risk-events`, Streams y Pipe. Configurar filtro y normalización del payload, rol y destino `IncidentWorkflow` asíncrono. Validar el contrato de entrada con el lote real del Pipe y utilizar un solo origen activo para el inicio por cada riesgo.
- [ ] **EXT-02** Para Workers AI, crear `src/ai/explain_incident.py`, `infra/workers-ai.yml` y `workers/explain-incident/wrangler.toml` con `workers/explain-incident/src/index.ts`. Verificar en Cloudflare el binding AI, las cuotas y el secreto del endpoint. Invocar por regla sobre `incident.opened` elegible, enviar sólo contexto operativo mínimo, validar la salida y guardar una sugerencia claramente rotulada. Probar timeout y continuidad del incidente.
- [ ] **EXT-03** Para GCS o BigQuery ML, crear la infraestructura GCP en su consola/CLI autorizada y documentar bucket de staging, identidad, permisos, presupuesto y expiración. Cargar desde `gs://` sólo con la extensión habilitada. Para réplica AWS, crear `infra/replication.yml` tras validar segunda región, versionado en S3, IAM y el modelo de escritura para tablas replicadas. Probar recuperación antes de declarar disponibilidad regional.
- [ ] **EXT-04** Si se habilita Amplify Hosting como alternativa, crear el hosting de la SPA y repetir las comprobaciones de dominio autorizado, CORS y rutas. Mantener Firebase como identidad del personal.

## 8. Aceptación de entrega y tareas de demo

| Check | Cuándo se cierra | Evidencia |
|---|---|---|
| A-01 · Auth/Pages | Un usuario entra desde Pages, obtiene su perfil, consulta su operación y recibe rechazo al intentar otra. | URL, roles de demo, requests con datos sintéticos y códigos depurados. |
| A-02 · Ingesta | Lote normal devuelve 202, se archiva en S3 y cambia estado de flota. Repetir y enviar un lote antiguo conserva la última lectura correcta. | `batch_id`, TTL/marcador, objeto S3 y estado antes/después. |
| A-03 · Riesgo e idempotencia | Pico aislado no abre el incidente de prueba. Riesgo persistente abre uno. Duplicado y carreras mantienen un incidente activo por familia. | `risk_event_id`, ARN de ejecución y fila de lock. |
| A-04 · Reservas | Con recursos asigna; sin técnico o repuesto queda pendiente con motivo. Dos intentos concurrentes no toman el mismo técnico ni sobregiran stock. | Estado, reservas y prueba de concurrencia. |
| A-05 · Intervención | Técnico asignado inicia y resuelve; Supervisor cierra. Consumo y liberación ocurren una vez pese a repetir el request. | Historial, stock final, identidad y auditoría. |
| A-06 · GCP | Plan local más carga/SQL real en BigQuery. KPI visible desde la SPA. Un fallo externo conserva plan y último KPI válido. | IDs de jobs, resultado, snapshot y `computed_at`. |
| A-07 · DLQ y observabilidad | Un mensaje falla de forma controlada, es enviado a DLQ y se reprocesa tras corregir el problema. | `trace_id`, logs, métrica y evidencia de redrive. |
| A-08 · P1 | Histórico, reasignación, inventario, técnicos y avisos funcionan desde la SPA según el rol. | Suite de navegador y pruebas HTTP. |
| A-09 · P2 | Cada extensión activada tiene permisos y prueba propia de entrega, conflicto o degradación. | Evidencia de la extensión utilizada y su configuración. |

- [ ] **QA-01 · P0** Crear y ejecutar `scripts/run_demo.py` con casos sintéticos reproducibles. Correr pruebas unitarias, de contrato y de integración antes del recorrido en AWS. Los datos y usuarios de prueba son del entorno de demo.
- [ ] **QA-02 · P0** Seguir un mismo `trace_id` por Lambda, SQS, EventBridge y Step Functions. Correlacionar con `batch_id`, `incident_id`, `run_id` e IDs BigQuery. Excluir tokens, secretos y datos personales de logs y evidencias.
- [ ] **QA-03 · P0** Registrar recursos por nombre y versión, URL, cómo ejecutar semilla, escenarios y controles de pausa. Pausar schedules al acabar las pruebas. Antes de otra sesión de lab confirmar cuenta, rol, región, stack y vigencia de credenciales.
- [ ] **QA-04 · P0** Marcar cada tarea terminada con evidencia y dependencia resuelta. Mostrar explícitamente en el README qué recursos están automatizados, cuáles vienen preaprovisionados y qué permisos o servicios siguen pendientes de validar.

### Ejemplo de fragmento YAML que se debe crear

Fragmento para `infra/queues.yml`, con un visibility timeout inicial de 180 s, válido como punto de partida para Lambda con timeout de 30 s y ventana de batching cero. Importar el fragmento bajo `resources` en `serverless.yml`. En la función consumidora, configurar el mapping al ARN de `TelemetryQueue` y `ReportBatchItemFailures`. `ingest-api` recibe la URL de la cola mediante `Ref`.

```yaml
Resources:
  TelemetryDlq:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: af-${sls:stage}-telemetry-dlq
      MessageRetentionPeriod: 1209600
      SqsManagedSseEnabled: true
  TelemetryQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: af-${sls:stage}-telemetry-queue
      VisibilityTimeout: 180
      MessageRetentionPeriod: 345600
      SqsManagedSseEnabled: true
      RedrivePolicy:
        deadLetterTargetArn:
          Fn::GetAtt: [TelemetryDlq, Arn]
        maxReceiveCount: 5
```
