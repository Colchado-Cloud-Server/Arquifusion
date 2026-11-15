# ArquiFusion

Plataforma de monitoreo de maquinaria y gestión de mantenimiento para una hackathon. Recibe telemetría simulada, detecta riesgo persistente, coordina incidentes y recursos, y presenta planificación preventiva y KPIs.

## Estado actual

La rama de infraestructura incluye los archivos de AWS-01 a AWS-10: stack Serverless/CloudFormation, recursos, dos workflows, empaquetado Linux, validaciones y comandos de operación desde CloudShell. Se conserva el código de autenticación y seed de la rama del compañero. Los handlers de los demás dominios y el despliegue real siguen pendientes; las validaciones bloquean la publicación de un backend incompleto.

La fuente de requisitos es el archivo local `ArquiFusion_requerimientos_y_backlog.md`, excluido de Git. Cada integrante debe obtenerlo por separado. El plano está en [ArquiFusion_arquitectura_v3 (1).drawio](<ArquiFusion_arquitectura_v3 (1).drawio>). Tener archivos preparados y pruebas locales no cierra las tareas que requieren evidencia de AWS.

## Arquitectura acordada

- Backend: AWS Lambda con Python 3.12, HTTP API Gateway, SQS, S3, DynamoDB, EventBridge y Step Functions.
- Infraestructura: `serverless.yml` raíz, fragmentos CloudFormation en `infra/` y dos workflows en `workflows/`, con un stack por stage y roles existentes del Learner Lab.
- Frontend: React, TypeScript y Vite, publicado en Cloudflare Pages.
- Identidad: Firebase Authentication para personas y credencial de productor separada para telemetría.
- Analítica: cargas y consultas reales en BigQuery Sandbox, con snapshots en DynamoDB.

Los servicios comparten repositorio y despliegue inicial. Sus responsabilidades, handlers, contratos y permisos se separan por dominio.

## Estructura

```text
.
├── ArquiFusion_requerimientos_y_backlog.md  # Local, excluido de Git
├── ArquiFusion_arquitectura_v3 (1).drawio
├── CONTRIBUTING.md
├── .env.example
├── serverless.yml         # Stack único por stage, API y roles existentes
├── infra/                 # Tablas, colas, storage, eventos, funciones y alarmas
├── workflows/             # IncidentWorkflow y MaintenancePlanningWorkflow
├── docs/                  # Guía de Learner Lab e inventario de recursos
├── contracts/             # OpenAPI, JSON Schema y contratos compartidos
├── src/
│   ├── common/
│   ├── auth/
│   ├── admin/
│   ├── telemetry/
│   ├── fleet/
│   ├── incidents/
│   ├── technicians/
│   ├── parts/
│   ├── notifications/
│   ├── maintenance/
│   └── analytics/
├── seed/                  # Catálogos y escenarios sintéticos
├── sql/                   # Consultas BigQuery
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── scripts/               # Smoke tests, demo y operaciones
└── frontend/
    ├── .env.example
    └── src/
```

Los archivos `.gitkeep` conservan los directorios todavía vacíos. Los servicios de dominio se integran según los handlers declarados en `infra/functions.yml`. Los contratos de acciones internas están en [workflow-actions.md](contracts/workflow-actions.md).

## Empezar a colaborar

Requisitos: Git, Python 3.12 y Node 20–24. Serverless está fijado en 3.40.0 con lockfile y empaquetado Python independiente. La [guía AWS para Learner Lab](docs/aws-learner-lab.md) explica las comprobaciones y configuración desde CloudShell, sin credenciales en equipos locales.

```bash
python -m pip install -r requirements-dev.txt
npm ci
npm run validate:template
npm run lint:template
python -m pytest
```

`validate:template` genera un template de prueba con referencias ficticias y un ZIP marcado como no desplegable. `npm run validate` comprueba configuración real y lista handlers pendientes. Cuando estén integrados, `npm run package` genera el ZIP Linux completo y `npm run deploy -- --stage dev --region us-east-1` verifica la cuenta y publica el stack. Revisar antes el template generado. No se despliega nada durante las pruebas locales.

1. Clonar el repositorio compartido del equipo.
2. Crear una rama desde `main` actualizada, por ejemplo `feat/catalog-seed`.
3. Implementar una tarea acotada del backlog y agregar la validación correspondiente.
4. Abrir un pull request con alcance, resultado y evidencia. Seguir [CONTRIBUTING.md](CONTRIBUTING.md).

Para preparar configuración local en PowerShell:

```powershell
Copy-Item .env.example .env
Copy-Item frontend/.env.example frontend/.env
```

Completar `.env` con cuenta esperada, región, bucket de artefactos, roles autorizados, proyecto Firebase y origen exacto de Pages. CloudShell aporta las credenciales de la sesión. Los valores de secretos del productor y GCP se cargan en el almacén AWS aprobado; el stack pasa sólo sus identificadores y `src/common/secrets.py` permite leerlos en runtime. `.env`, `.artifacts/`, `.local/` y los mapas locales de UID están excluidos de Git.

## Reparto inicial

| Frente | Alcance inicial | Rama sugerida |
|---|---|---|
| Compañero: RF-01 | Firebase, authorizer y validación de permisos en `src/auth/` | `feat/auth` |
| Compañero: RF-03 | Simulador, escenarios e ingesta HTTP en `src/telemetry/` | `feat/telemetry-ingest` |
| Compañero: RF-02 | Seed, catálogos y perfiles en `src/admin/` y `seed/` | `feat/catalog-seed` |
| Nuestro frente: AWS-01 a AWS-10 | Infraestructura, configuración, empaquetado, smoke tests y operación | `feat/aws-infrastructure` |

Antes de integrar, acordar el esquema del mensaje SQS, IDs de catálogos, claves de tablas y formato de perfiles por operación. La creación del perfil Admin inicial debe coordinarse entre RF-01 y RF-02. Los UID reales de demo se incorporan desde un mapeo del entorno.

## Secuencia de integración

1. Usuario autorizado → consulta de flota → lote → estado en DynamoDB.
2. Riesgo persistente → incidente → reservas → intervención → cierre.
3. Plan local → carga y SQL BigQuery → KPI visible en la SPA.

## Repositorio compartido

Usar [Colchado-Cloud-Server/Arquifusion](https://github.com/Colchado-Cloud-Server/Arquifusion), ramas por tarea y pull requests. Esta rama AWS se creó sobre `origin/feat/catalog-seed` para reutilizar el trabajo existente; coordinar su integración con `main`.

## Infraestructura y evidencias

El template configura trece tablas on-demand, dos colas, histórico privado, catorce Lambdas, una HTTP API, EventBridge, dos workflows y alarmas. Scheduler es opcional; los schedules y el consumidor SQS comienzan deshabilitados. Referencia roles existentes y permite reutilizar recursos preaprovisionados sin duplicarlos.

Usar [aws-resources.example.yml](docs/aws-resources.example.yml) para registrar nombres/ARNs, región, responsable, origen, denegaciones y evidencias reales. Las comprobaciones locales de CloudFormation, CORS, colas, workflows y scripts no sustituyen la validación en Learner Lab. El presupuesto y los permisos de la cuenta se comprueban antes de desplegar; los schedules se pausan al terminar la demo.
