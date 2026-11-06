# Air Control Pro

Portal de mantenciones en Django con tres perfiles:

| Perfil | Qué hace |
|---|---|
| **Administrador** | Dashboard de ingresos, costos, utilidad y cobranza; crea clientes, ubicaciones, equipos, usuarios y órdenes de trabajo; revisa y emite los informes. |
| **Técnico** | Ve solo sus órdenes, inicia el trabajo (se pide su ubicación GPS), completa el informe por equipo con fotos (cada foto guarda su GPS) y lo envía a revisión. |
| **Cliente** | Ve solo lo de su empresa: equipos, próximas mantenciones e informes emitidos ordenados por mes. |

Flujo: `Pendiente → En proceso (técnico inicia) → En revisión (técnico envía) → Finalizada (admin emite)`.

## Informe técnico (formato Air Control Pro)

El informe replica el Word actual: encabezado con N° de OTs, A.t, quién generó y responsable técnico, y
por cada equipo: N° de equipo, marca/modelo, ubicación exacta, tipo de mantenimiento, las 6 actividades,
observaciones (los equipos con refrigerante R-22 salen solos como «FUERA DE NORMA» en rojo), fotos y las
mediciones (presión, consumo total, consumo ventilador y temperatura de inyección frío/calor).

- El técnico puede **crear el informe directamente en terreno** (botón *Nuevo informe*): elige cliente y
  sucursal, se crea la orden a su nombre con su GPS, y va agregando equipos, fotos y mediciones. El
  administrador completa después lo que falte (N° de OT, montos) y puede editar el informe.
- El técnico **termina cada equipo** apenas lo interviene → su ficha PDF queda disponible al instante.
- Para enviar el informe a revisión todos los equipos de la orden deben estar terminados.
- Dentro del informe se pueden **agregar equipos** de la misma empresa (o crear uno nuevo si no está en el
  catálogo) y quitarlos. Un informe puede llevar tantos equipos como se hayan intervenido.
- El informe se puede **editar después de enviado**: el técnico mientras está en revisión y el administrador
  en cualquier momento, incluso ya emitido (el cliente ve los cambios al instante).
- **Informe del mes** (admin y cliente): reúne todos los equipos intervenidos en el mes para un cliente
  (opcionalmente una ubicación) en un solo PDF o Excel. El cliente solo ve lo ya emitido.
- **Numeración de OT:** formato `456/26` (número/año). Si dejas el campo vacío se asigna el siguiente del
  año; para partir desde otro número escribe la primera a mano (ej. `456/26`) y las siguientes serán
  `457/26`, `458/26`… Cada año vuelve a empezar en 1.
- Para cada equipo completa en *Equipos* su N° de equipo, ubicación exacta y refrigerante.

## Puesta en marcha

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo        # datos de ejemplo; usuarios: admin, tecnico, cliente
python manage.py runserver
```

Para un usuario administrador real: `python manage.py createsuperuser`.

## Exportar a PDF y Excel

Cada listado (órdenes, informes por mes, equipos, ubicaciones, clientes, usuarios), Finanzas y el
dashboard del administrador tienen un botón **Exportar** que respeta los filtros activos. Cada
informe técnico se exporta en **PDF con fotos** y en Excel. El cliente solo exporta lo de su
empresa y sin columnas financieras. Se puede pedir también por URL con `?export=pdf` o `?export=xlsx`.

## Base de datos

SQLite por defecto (`db.sqlite3`). Para PostgreSQL instala `psycopg[binary]` y define
`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`.

## Notas

- La geolocalización del navegador solo funciona en HTTPS (o `localhost`): en producción el sitio debe servirse con HTTPS.
- Las fotos se guardan en `media/` (se reducen a 1600 px al subirlas).
- Pruebas: `python manage.py test`.
