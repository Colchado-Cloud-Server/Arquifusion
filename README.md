# ArquiFusion

Plataforma de monitoreo de maquinaria y gestión de mantenimiento para una hackathon. Recibe telemetría simulada, detecta riesgo persistente, coordina incidentes y recursos, y presenta planificación preventiva y KPIs.

## Estado actual

Repositorio inicial: estructura de directorios, configuración de Git y guía de colaboración. Los servicios, contratos, dependencias y recursos cloud están pendientes de implementación. No hay despliegues ni pruebas automatizadas ejecutables todavía.

La fuente de requisitos es el archivo local `ArquiFusion_requerimientos_y_backlog.md`, excluido de Git. Cada integrante debe obtenerlo por separado. El plano está en [ArquiFusion_arquitectura_v3 (1).drawio](<ArquiFusion_arquitectura_v3 (1).drawio>). El backlog original conserva sus tareas pendientes; este esqueleto no completa BASE-01.

## Arquitectura acordada

- Backend: AWS Lambda con Python 3.12, HTTP API Gateway, SQS, S3, DynamoDB, EventBridge y Step Functions.
- Infraestructura: un futuro `serverless.yml` raíz, fragmentos CloudFormation en `infra/` y dos workflows en `workflows/`, con un stack por stage.
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
├── infra/                 # Recursos CloudFormation por implementar
├── workflows/             # Definiciones ASL por implementar
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

Los archivos `.gitkeep` conservan los directorios vacíos en Git. Los `__init__.py` preparan los paquetes Python; no contienen lógica de negocio.

## Empezar a colaborar

Requisitos iniciales: Git y Python 3.12. Node y la versión de Serverless Framework se fijarán al implementar BASE-01 y WEB-01; todavía no hay archivos de dependencias ni comandos de build disponibles.

1. Clonar el repositorio compartido cuando exista el remoto.
2. Crear una rama desde `main` actualizada, por ejemplo `feat/catalog-seed`.
3. Implementar una tarea acotada del backlog y agregar la validación correspondiente.
4. Abrir un pull request con alcance, resultado y evidencia. Seguir [CONTRIBUTING.md](CONTRIBUTING.md).

Para preparar configuración local en PowerShell:

```powershell
Copy-Item .env.example .env
Copy-Item frontend/.env.example frontend/.env
```

Completar únicamente los valores necesarios. Las plantillas todavía no están conectadas a código. Las credenciales AWS se gestionan mediante el perfil autorizado; los secretos del productor y GCP se almacenarán en el servicio AWS aprobado. Los archivos `.env` se excluyen de Git.

## Reparto inicial

| Frente | Alcance inicial | Rama sugerida |
|---|---|---|
| Compañero: RF-01 | Firebase, authorizer y validación de permisos en `src/auth/` | `feat/auth` |
| Compañero: RF-03 | Simulador, escenarios e ingesta HTTP en `src/telemetry/` | `feat/telemetry-ingest` |
| Nuestro frente: RF-02 | Seed, catálogos y perfiles en `src/admin/` y `seed/` | `feat/catalog-seed` |
| Nuestro siguiente frente: RF-04 | Consumo SQS, histórico S3 y estado DynamoDB en `src/telemetry/` | `feat/telemetry-processing` |

Antes de integrar, acordar el esquema del mensaje SQS, IDs de catálogos, claves de tablas y formato de perfiles por operación. La creación del perfil Admin inicial debe coordinarse entre RF-01 y RF-02. Los UID reales de demo se incorporan desde un mapeo del entorno.

## Secuencia de integración

1. Usuario autorizado → consulta de flota → lote → estado en DynamoDB.
2. Riesgo persistente → incidente → reservas → intervención → cierre.
3. Plan local → carga y SQL BigQuery → KPI visible en la SPA.

## Publicar el repositorio en GitHub

Si todavía no existe el primer commit, revisar los archivos y crearlo desde esta carpeta:

```powershell
git status --short
git add .
git diff --cached --stat
git diff --cached --check
git commit -m "chore: initialize ArquiFusion monorepo"
```

Una persona con sesión válida de GitHub CLI puede crear el repositorio privado y subir `main`:

```powershell
gh auth login --hostname github.com
gh repo create arquifusion --private --source=. --remote=origin --push
```

Si el equipo ya creó un repositorio, configurar su URL como `origin` e integrar el historial existente antes de subir cambios; no crear un segundo repositorio ni forzar el push. Agregar al compañero como colaborador desde GitHub cuando el remoto exista.

## Infraestructura y evidencias

Todavía no se han automatizado ni validado recursos AWS, Firebase, GCP o Cloudflare desde este repositorio. Registrar aquí los recursos preaprovisionados, roles autorizados, región, comandos, URLs y evidencias cuando se realicen las tareas AWS, AUTH, BQ y CF. No guardar tokens ni secretos en documentación o logs.
