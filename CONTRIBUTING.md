# Colaborar en ArquiFusion

## Ramas y cambios

Usar `main` como rama de integración y ramas cortas por tarea: `feat/auth`, `feat/telemetry-ingest`, `feat/catalog-seed` y `feat/telemetry-processing` son los primeros ejemplos.

Actualizar la rama local desde `main` antes de iniciar trabajo. Subir cambios mediante pull request y coordinar una revisión del compañero. Esta es una convención de trabajo; la protección de ramas en GitHub todavía no está configurada.

Los commits deben describir un cambio concreto, por ejemplo `feat(admin): add idempotent demo seed`.

## Contratos y archivos compartidos

- Acordar cambios en `contracts/` antes de modificar el formato que consume otro servicio.
- Coordinar modificaciones en `src/common/`, `serverless.yml`, `infra/` y archivos de dependencias. Designar a quien integra infraestructura antes de empezar el despliegue.
- En RF-03 se implementan simulación e ingesta; en RF-04 se implementan consumo y persistencia. Compartir `src/telemetry/` no implica editar los mismos handlers.
- Los handlers públicos validan identidad y alcance; el body del cliente no selecciona acciones internas del workflow.
- Mantener IDs estables para que los fixtures y el seed coincidan con el contrato de ingesta.

## Pull requests

Incluir IDs del backlog y RF relacionados, comportamiento resultante, validación realizada y dependencias pendientes. Si cambian contratos o configuración, señalar los consumidores afectados.

Ejecutar las comprobaciones disponibles para el cambio. Mientras no existan suites o builds, describir la revisión manual sin afirmar que se ejecutaron pruebas inexistentes. Marcar una tarea del backlog como completada solamente cuando cumpla sus criterios y tenga evidencia.

## Configuración y datos

Usar datos sintéticos de demo. Versionar plantillas `.env.example` y leer la configuración local desde archivos excluidos de Git o el entorno. No subir credenciales AWS, llaves GCP, tokens Firebase ni secretos del productor.

El seed debe preservar estado operativo, reservas e inventario al repetirse. Los cambios de esquema o de reglas deben coordinarse con los servicios que los consumen.
