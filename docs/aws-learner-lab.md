# Infraestructura AWS: AWS-01 a AWS-10

## Alcance y estado

Esta rama aporta infraestructura y herramientas de operación. Conserva sin modificar la implementación de autenticación y seed de `origin/feat/catalog-seed`. Nuestra implementación anterior duplicada de RF-02 se retiró. El servicio de seed de esa rama todavía necesita su handler HTTP/adaptador AWS, a cargo de ese frente.

No se ha desplegado ni consultado una cuenta AWS desde estas herramientas. Los datos comunicados en la conversación (cuenta `992382544030`, `us-east-1`, actor `voclabs`, consulta de CloudFormation permitida) son evidencia aportada por el usuario y deben reconfirmarse en cada sesión. La creación y prueba del bucket de artefactos siguen sin confirmación en este repositorio.

| Tarea | Archivos preparados | Cierre pendiente en AWS |
|---|---|---|
| AWS-01 | `.env.example`, `scripts/smoke_aws.py`, inventario de ejemplo | Identidad, región, bucket, prueba de escritura y permisos reales de despliegue. |
| AWS-02 | Referencias a roles existentes, revisión de trust y simulación opcional de PassRole | Probar las acciones reales de cada integración. |
| AWS-03 | Stack raíz, trece tablas, SQS/DLQ, S3, bus/regla, dos workflows y sus contratos | Integrar handlers de dominio y validar template en la cuenta. |
| AWS-04 | Una HTTP API v2, CORS exacto, REQUEST authorizer simple, caché cero | Firebase real y preflight desde Pages. |
| AWS-05 | CLI/lockfile, ZIP Linux, bloqueo de artefactos incompletos, wrapper de despliegue | Empaquetar código completo, revisar template real e invocar ZIP en Lambda. |
| AWS-06 | Mapping único, timeout 180 s, consumidor 30 s, batching cero, cinco recepciones, DLQ de 14 días frente a origen de 4 días | Lote mixto, respuesta parcial y agotamiento de reintentos. |
| AWS-07 | Identificadores de secretos y lector runtime SSM/Secrets Manager | Crear valores por consola y conceder lectura al rol autorizado. |
| AWS-08 | Alarmas, logs siete días y redrive nativo SQS | Provocar fallo controlado, corregir y comprobar `batch_id` tras redrive. |
| AWS-09 | Outputs, schedules opcionales creados deshabilitados y comando de pausa | Cargar seed, habilitar sólo durante demo y pausar al terminar. |
| AWS-10 | Reutilización explícita de colas/tablas/bucket y guía manual | Registrar recursos preexistentes sin duplicarlos. SNS es P2 y no se activa aquí. |

Los workflows son contratos de orquestación, no implementaciones de negocio. `contracts/workflow-actions.md` define las acciones y respuestas que deben implementar los otros frentes. `npm run validate` enumera los handlers pendientes y bloquea el despliegue; no genera stubs con éxito ficticio.

## Flujo enteramente desde AWS

1. Start Lab, entrar a la consola de esa sesión y abrir CloudShell en una región permitida. No usar otra terminal de instancia con un rol distinto. No es necesario copiar credenciales a un PC.
2. Confirmar `aws sts get-caller-identity` y región. Identificar el actor de despliegue; `voclabs` no es automáticamente el rol de ejecución Lambda.
3. Clonar `https://github.com/Colchado-Cloud-Server/Arquifusion.git` y seleccionar la rama de infraestructura cuando se publique. Para un repo privado, autenticar GitHub en CloudShell mediante el mecanismo autorizado; no guardar tokens GitHub en el repo.
4. Disponer de Node 20–24 y Python 3.12. Crear y activar un entorno virtual. Instalar dependencias y copiar `.env.example` a `.env`.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
npm ci
cp .env.example .env
```

Si CloudShell no incluye Python 3.12 o no permite instalar las herramientas requeridas, registrar esa restricción con el responsable del laboratorio. La ejecución y el despliegue AWS permanecen dentro del entorno autorizado; el runtime Lambda sigue siendo Python 3.12.

Completar `EXPECTED_AWS_ACCOUNT_ID`, `AWS_REGION`, `DEPLOYMENT_BUCKET`, los tres roles obligatorios, `PAGES_ORIGIN` y `FIREBASE_PROJECT_ID`. `.env` es configuración de entorno; no añadir claves AWS, tokens de productores ni llaves privadas GCP. CloudShell ya aporta la sesión. El proyecto usa `.env` mediante dotenv para comandos y Serverless; Lambda recibe sólo las variables declaradas en sus funciones.

Serverless está fijado en 3.40.0 para evitar introducir la autenticación/licencia de v4 en el laboratorio. El plugin local añade Python 3.12 al enum antiguo de esa versión y comprueba la integridad del artefacto; no desactiva la validación del resto del schema. No se usa empaquetado Python nativo de v4. Si el equipo cambia de CLI, debe regenerar el lock y repetir las comprobaciones de template y guardas.

## AWS-01: identidad y artefactos

Crear o identificar un bucket privado de despliegue en la misma cuenta y región. Para la cuenta comunicada, el nombre propuesto es `af-dev-992382544030-us-east-1-artifacts`; verificar que exista antes de configurarlo. Es distinto del bucket de histórico. Bloquear acceso público y usar cifrado S3 AES256, sin crear claves KMS propias.

```bash
python -m scripts.smoke_aws
python -m scripts.smoke_aws --write-test
```

El primer comando es de consulta. El segundo sube un único objeto sintético con clave aleatoria bajo `serverless/arquifusion/<stage>/aws-01/`, verifica lectura y elimina exactamente la versión creada. No enumera cuerpos de mensajes ni imprime secretos. Necesita permisos de escritura/lectura/borrado sobre ese prefijo. Las respuestas no incluyen el nombre personal de la sesión STS.

`READ_CHECKS_PASSED` no equivale a permiso de crear stacks o recursos: el reporte mantiene `effective_deployment_permissions=NOT_VERIFIED`. `ListStacks` y `HeadBucket` sólo comprueban sus respectivas acciones. Registrar denegaciones por código, no asumir que toda la cuenta está bloqueada.

## AWS-02: roles existentes

| Variable | Trust esperado | Acciones runtime mínimas de la integración |
|---|---|---|
| `LAMBDA_ROLE_ARN` | `lambda.amazonaws.com` | Logs y acciones específicas DynamoDB/S3/SQS/EventBridge/secretos/StartExecution que use cada handler. |
| `SFN_ROLE_ARN` | `states.amazonaws.com` | `lambda:InvokeFunction` sobre incident-service, technician-dispatch, parts-service, notification-service, maintenance-analyzer y analytics-sync. |
| `EVENTS_START_SFN_ROLE_ARN` | `events.amazonaws.com` | `states:StartExecution` sobre IncidentWorkflow. |
| `SCHEDULER_ROLE_ARN` | `scheduler.amazonaws.com` | Invocar simulate-telemetry e iniciar MaintenancePlanningWorkflow; obligatorio sólo con `ENABLE_SCHEDULER=true`. |

El actor que despliega necesita `iam:PassRole` sobre los roles utilizados y permisos CloudFormation, S3 de artefactos y gestión de los recursos declarados. No se crean `AWS::IAM::*`, no se adjuntan políticas y no se modifica el trust desde este stack. Si el lab sólo autoriza un rol Lambda, referenciarlo en `provider.iam.role` y registrar su alcance efectivo. `SIMULATOR_ROLE_ARN` e `INGEST_ROLE_ARN` permiten overrides si ya existen roles más acotados.

`smoke_aws` consulta el trust. Condiciones o denies requieren revisión; el nombre del rol no prueba capacidades. `--simulate-passrole` solicita una simulación IAM opcional con `iam:PassedToService`; puede estar denegada y no sustituye pruebas reales ni evalúa todas las restricciones de sesión, SCP y políticas de recursos.

Si `CreateStateMachine`, `PassRole` o el destino EventBridge se bloquean, registrar la acción y consultar al responsable. El disparador alternativo Lambda → Step Functions exige una adaptación explícita y un solo origen activo; esta rama configura el disparador directo del plano.

## AWS-03/04/05: validar y desplegar

```bash
npm run validate:template
npm run lint:template
python -m pytest
npm run validate
```

La primera orden compila el template real sin credenciales ni llamadas de despliegue, con ARNs ficticios sólo en el proceso hijo. Produce `.artifacts/template-only/cloudformation-template-update-stack.json` y un ZIP marcado `template_only=true`, sin dependencias runtime. No es un paquete ejecutable en Lambda. El plugin bloquea su uso con `serverless deploy`, incluso si sigue exportado `AF_TEMPLATE_ONLY=1`.

`cfn-lint` valida el template compilado; `.cfnlintrc` omite únicamente W3005 por dependencias redundantes que genera Serverless. Las advertencias de roles/configuración permanecen activas. Las pruebas inspeccionan ese mismo template para comprobar runtime 3.12, ausencia de roles nuevos y rutas/integraciones únicas.

Para un build real, deben estar integrados todos los handlers de `infra/functions.yml`, las acciones de los workflows y las dependencias de los nuevos módulos. Las dependencias runtime y transitivas actuales están fijadas en `requirements.txt`; las de pruebas y YAML van en `requirements-dev.txt`.

```bash
npm run package
# Revisar .serverless/cloudformation-template-update-stack.json
npm run deploy -- --stage dev --region us-east-1
```

`package_backend` usa wheels Linux x86_64 de Python 3.12 compatibles con Amazon Linux 2023. Incluye `src/`, esquemas/OpenAPI, SQL y sólo los JSON de seed de demo permitidos. No incluye `.venv`, frontend, pruebas, `.env`, mapas locales de UID ni credenciales. El manifiesto registra hash del ZIP y de fuentes/dependencias: cambios posteriores requieren reconstruirlo.

El wrapper comprueba identidad y propietario del bucket antes de publicar y no actúa si falta código/configuración. `npx serverless deploy` también pasa por la guarda local. La revisión del template y las pruebas reales de recursos, roles e invocación del ZIP siguen siendo necesarias; no se han ejecutado desde esta rama.

La API usa un único authorizer REQUEST v2 simple con caché cero. `/telemetry/batch` conserva autenticación del productor en su handler. Todas las rutas `/api/*` requieren el authorizer y validación de alcance en el handler. CORS admite el origen exacto `PAGES_ORIGIN`, métodos GET/POST/PATCH/OPTIONS y headers Authorization, Content-Type e Idempotency-Key. No hay ruta OPTIONS protegida. Agregar cada preview usada de forma explícita en el YAML y en Firebase; no usar comodines.

## AWS-06/10: recursos preexistentes y SQS

Por defecto el stack crea trece tablas, la cola/DLQ y el bucket de histórico. Tablas e histórico llevan `Retain` para preservar estado si se elimina el stack; inventariarlos y gestionar su limpieza autorizada al terminar el laboratorio. El bucket de artefactos siempre es preaprovisionado y se referencia por nombre.

- Para reutilizar **todas las tablas**, definir `USE_EXISTING_TABLES=true` y sus trece variables de nombre.
- Para reutilizar **una tabla**, definir por ejemplo `USE_EXISTING_USERS_TABLE=true` y `USERS_TABLE=<nombre-real>`. Aplicar el mismo patrón a las restantes. Verificar claves e índices antes de usarla.
- Para reutilizar **el histórico**, definir `EXISTING_TELEMETRY_BUCKET=<nombre-real>`; ese bucket/política queda fuera del stack y debe ser privado y cifrado.
- Para reutilizar **las colas**, definir los cuatro valores `EXISTING_TELEMETRY_QUEUE_ARN`, `EXISTING_TELEMETRY_QUEUE_URL`, `EXISTING_TELEMETRY_DLQ_ARN`, `EXISTING_TELEMETRY_DLQ_URL`. Deben corresponder a la misma cuenta/región. No se crean otras colas ni otro mapping.

Si la creación de colas es manual: crear primero la DLQ Standard con retención 14 días, luego la cola Standard con retención 4 días, visibility timeout 180 s y redrive a esa DLQ tras cinco recepciones. Registrar ambos ARNs y URLs. El stack crea el único mapping, batching cero, batch 10 y `ReportBatchItemFailures`. No conectarlo también desde la consola. Un mapping preexistente se debe importar al único propietario o retirar de forma coordinada antes de gestionar éste.

El consumidor comienza deshabilitado (`ENABLE_TELEMETRY_CONSUMER=false`). Después del seed y las pruebas de contrato, habilitarlo con esa variable y actualizar el stack. Un timeout de consumidor distinto de 30 s exige ajustar visibility timeout ≥ seis veces ese valor más ventana de batching. El handler debe devolver los `messageId` fallidos, no repetir ítems correctos.

SNS/fanout de repuestos, analítica y avisos externos pertenece a P2; no se crean sus recursos. Si se habilita luego: topic antes de suscripciones, DLQ antes de cada cola, política restringida al topic, filtros y prueba por tipo, sin duplicar avisos in-app del MVP.

## AWS-07: secretos por consola

Elegir `SECRET_STORE=ssm` o `secretsmanager`, según permisos. Crear `/af/dev/simulator-token` como SecureString en SSM o texto en Secrets Manager; su estructura debe acordarse con RF-03. Si GCP usa llave, crear `/af/dev/gcp-bigquery-credentials` con el JSON de la identidad autorizada, sólo si cabe y el lab lo permite. Con WIF no es necesaria esa llave; configurar el método con el frente BQ.

Conceder `ssm:GetParameter` con descifrado y el acceso KMS correspondiente cuando aplique, o `secretsmanager:GetSecretValue`, únicamente sobre los secretos que cada Lambda consume. Pasar sólo los identificadores al stack. `src/common/secrets.py` aporta lectura runtime para que los handlers la usen; no se usa resolución de valores de secretos durante el despliegue. Revocar/rotar la llave GCP según lo acordado.

## AWS-08: observabilidad y recuperación

Hay alarmas para Errors de las catorce Lambdas, fallo de ambos workflows, mensajes en DLQ y edad de cola. No se crean destinos SNS de alarma. Logs Lambda/API tienen retención siete días y los access logs no contienen headers ni bodies. Si alarmas no están permitidas, configurar `ENABLE_ALARMS=false`, registrar el bloqueo y usar métricas/logs disponibles.

Después de identificar `batch_id`/`trace_id` y corregir la causa:

```bash
python -m scripts.redrive_telemetry --queue-url '<URL_ORIGEN>' --dlq-url '<URL_DLQ>'
python -m scripts.redrive_telemetry --queue-url '<URL_ORIGEN>' --dlq-url '<URL_DLQ>' --execute --rate 1
python -m scripts.redrive_telemetry --queue-url '<URL_ORIGEN>' --dlq-url '<URL_DLQ>' --status
```

La consulta inicial no recibe ni borra mensajes. `--execute` inicia redrive nativo de **todos** los mensajes de esa DLQ, no filtra un batch individual. Comprueba cuenta y asociación DLQ→origen y preserva el payload mediante SQS. Requiere `StartMessageMoveTask` y los permisos SQS de recepción/borrado/atributos en la DLQ y envío al origen; `--status` requiere `ListMessageMoveTasks`. Verificar después que se reprocesó el mismo `batch_id` sin duplicar incidentes. Si el lab deniega redrive, registrar la restricción y coordinar una alternativa autorizada.

## AWS-09: outputs y schedules

Outputs: URL/ID de HTTP API, URLs/ARNs de cola y DLQ, bucket de histórico, ARN de IncidentWorkflow y ARN de MaintenancePlanningWorkflow. Obtenerlos con `aws cloudformation describe-stacks --stack-name af-dev --query 'Stacks[0].Outputs'` y configurar frontend e integraciones.

Con `ENABLE_SCHEDULER=true` y rol válido se crean dos schedules **DISABLED**: telemetría cada minuto y planificación cada hora. Mantenerlos deshabilitados hasta cargar catálogos, verificar roles y completar el recorrido manual. Si Scheduler no está permitido, dejarlo en false y usar invocación Lambda y el endpoint administrativo del plan cuando sus handlers estén integrados.

```bash
# Consultar qué se pausaría; no modifica los targets.
python -m scripts.manage_schedules --state DISABLED
# Habilitar sólo durante la demo verificada.
python -m scripts.manage_schedules --state ENABLED --apply
# Pausar al finalizar.
python -m scripts.manage_schedules --state DISABLED --apply
```

La herramienta verifica cuenta y conserva rol, input, expresión y demás propiedades del schedule al actualizar. Si no se crearon schedules, no ejecutar estos comandos.

## Evidencias

Usar `docs/aws-resources.example.yml` como plantilla de inventario. Registrar nombre/ARN, región, responsable, origen y motivo de cada recurso, comandos ejecutados, códigos de error y dependencias pendientes. No marcar AWS-01–10 completadas sólo porque existan archivos. Las pruebas locales no equivalen a permisos efectivos, despliegue, CORS de navegador ni recuperación real de DLQ.
