# Air Control Pro · Portal de mantenciones

Portal en Django con tres perfiles, con la misma identidad visual que [aircontrolpro.cl](https://aircontrolpro.cl).

| Perfil | Qué hace |
|---|---|
| **Administrador** | Dashboard (ingresos, costos, utilidad, cobranza y **cotizaciones por llamar**); gestiona cotizaciones, clientes, ubicaciones, equipos, usuarios y órdenes de trabajo; revisa y emite los informes. |
| **Técnico** | Ve sus órdenes con los **equipos que debe intervenir** (N° de equipo, ubicación exacta, R-22 fuera de norma), inicia el trabajo, completa el informe por equipo con fotos y lo envía a revisión. |
| **Cliente** | Ve solo lo de su empresa: equipos, próximas mantenciones e informes emitidos ordenados por mes. |

Flujo de una orden: `Pendiente → En proceso (técnico inicia) → En revisión (técnico envía) → Finalizada (admin emite)`.

## Dashboard interactivo (administrador)

- **KPIs que mandan sobre el gráfico:** toca *Ingresos*, *Costos*, *Utilidad* o *Por cobrar* y el gráfico principal se transforma. Cada tarjeta muestra su mini gráfico y la variación contra el período equivalente del año anterior.
- **Gráfico:** alterna entre *Año* (por mes) y *30 días*, entre barras y línea, y superpone el *Año anterior*. El tooltip muestra el monto y cuántas órdenes se finalizaron.
- **Sin recargar:** cambiar el año o el cliente actualiza todo el panel (`/dashboard/datos/` entrega el JSON). Tocar un cliente del ranking *Ingresos por cliente* filtra todo el panel; la URL queda con el filtro.
- **Órdenes por estado** (dona; al pasar el mouse por la leyenda se resalta el trozo, al tocarlo abre las órdenes de ese estado), **embudo de cotizaciones** (enviadas → aceptadas → con orden), **agenda de 7 días** (atrasadas primero), **rendimiento por técnico**, **estado de los equipos** (con alerta de R-22) y **actividad reciente**.
- Los dashboards del técnico y del cliente comparten el encabezado y los números animados. Se respeta `prefers-reduced-motion`.

## Tablero de cotizaciones

En *Cotizaciones → Tablero* las cotizaciones están en tres columnas (Pendiente, Aceptada, Rechazada). **Arrastra una tarjeta** a otra columna y el estado se guarda al instante; los totales de cada columna se recalculan. En el celular se usa el menú ⋯ de la tarjeta. Al pasar a *Aceptada* aparece **Generar orden**.

## Cotizaciones y alerta de seguimiento

- **Cotizaciones** (menú del administrador): cliente, sucursal, ítems con cantidad y precio neto (IVA 19 % automático), validez, y PDF listo para enviar al cliente.
- Estados: **Pendiente → Aceptada / Rechazada**. Una cotización aceptada tiene el botón **Generar orden de trabajo**, que abre la orden con los datos y el monto precargados y queda enlazada a la cotización.
- **Alerta «por llamar»:** una cotización *pendiente* con **más de 3 días** desde su envío (`COTIZACION_DIAS_ALERTA`) sin gestión aparece:
  - en el Dashboard, con nombre del contacto, teléfono (clic para llamar), WhatsApp y días sin respuesta;
  - como contador naranja en el menú *Cotizaciones*;
  - en un **correo diario** (ver más abajo).
- Cada llamada/WhatsApp se anota en **Seguimiento al cliente**; eso saca la cotización de la alerta hasta que pasen otros 3 días. Los datos de contacto salen del cliente, o de la propia cotización si quien decide es otra persona.

## Técnico: órdenes de trabajo y equipos

El administrador crea la orden (*Órdenes de trabajo → Nueva orden*), elige la sucursal, **marca los equipos a intervenir** y asigna el técnico. El técnico los ve en *Mi jornada* (atrasadas en rojo, prioridad alta destacada) y en el detalle de la orden. El técnico también puede abrir un informe directamente en terreno (*Nuevo informe*) y agregar equipos que no estaban en el catálogo.

## Informe técnico (formato Air Control Pro)

Encabezado con N° de OT, A.t, quién generó y responsable técnico; por cada equipo: N° de equipo, marca/modelo, ubicación exacta, tipo de mantenimiento, 6 actividades, observaciones (opcionales) y un interruptor **«Equipo fuera de norma»** por equipo en cada informe: parte activado si el refrigerante es R-22, pero el técnico puede apagarlo o encenderlo; si está activo el informe lo dice en rojo, fotos y mediciones. Se exporta a PDF (con fotos) y Excel; el *Informe del mes* reúne todos los equipos intervenidos por cliente.

### Las 6 fotos de cada equipo

En el editor cada equipo muestra 6 casillas numeradas, una por paso del trabajo: **1 Aplicación del líquido · 2 Lavado con hidrolavadora · 3 Secado con soplador · 4 Equipo desarmado · 5 Condensadora (opcional) · 6 Equipo armado y funcionando**. La lista y qué pasos son obligatorios se cambian en `PASOS_FOTO` ([mantenciones/models.py](mantenciones/models.py)).

- Cada casilla guarda **una** foto: *Retomar* la reemplaza. Además hay *Otras fotos* libres para detalles o daños.
- **Si el técnico olvida una foto no queda bloqueado:** puede terminar el equipo (la app le avisa qué falta y le pide confirmar) y enviar el informe. Las fotos faltantes aparecen en *Mi jornada → Fotos pendientes*, arriba del editor, y en el detalle de la orden y del informe (para el administrador); con un clic llega a la casilla y la sube. Puede completarlas mientras el informe no esté emitido al cliente; el administrador, en cualquier momento.
- La condensadora no cuenta como pendiente.

### Informe por equipo y general de la orden

- **Informe del equipo (PDF):** disponible apenas el técnico termina ese equipo. Lleva los datos, las actividades, las fotos en el orden del trabajo con el paso al pie, y las mediciones.
- **Informe general de la orden (PDF/Excel):** reúne todos los equipos intervenidos de esa orden de trabajo. Está en el editor, en el detalle del informe y en el detalle de la orden. El Excel incluye la columna de fotos pendientes.

**Numeración de OT:** `456/26` (número/año). Vacío = siguiente del año; para partir desde otro número escribe la primera a mano y las siguientes continúan.

## Puesta en producción en cPanel

### 1. Base de datos
En cPanel → **Bases de datos MySQL**: crea la base, crea un usuario y asígnalo a la base con *todos los privilegios*. cPanel antepone tu usuario (`usuario_aircontrol`). Se recomienda MariaDB 10.6+ / MySQL 8+ (requisito de Django 6.1; si tu servidor es más antiguo usa `Django>=5.2,<5.3` en `requirements.txt`).

### 2. Aplicación Python
En cPanel → **Setup Python App** → *Create Application*: versión de Python 3.12 o superior, *Application root* = carpeta donde subas el proyecto, *Application URL* = p. ej. `app.aircontrolpro.cl`, *Startup file* `passenger_wsgi.py`, *Entry point* `application`. Sube el código (git o administrador de archivos, **sin** `.env` local ni `db.sqlite3`).

### 3. Variables de entorno
Define las de [`.env.example`](.env.example) en *Environment variables* de la app, o crea un `.env` en la raíz del proyecto en el servidor. Obligatorias: `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`. Con `DJANGO_DEBUG` apagado (por defecto) el sitio exige clave secreta propia y cookies seguras.

### 4. Instalar y migrar
En el terminal de cPanel (o el botón *Run Pip Install* de la app), dentro del entorno virtual que muestra Setup Python App:

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser      # tu usuario administrador real
```

Reinicia la app. Luego entra a `/`, crea tus **clientes, ubicaciones, equipos y usuarios** (técnicos y clientes) desde el menú. No se carga ningún dato de ejemplo.

### 5. HTTPS
Activa AutoSSL para el subdominio (el sitio usa cookies seguras). Si cPanel no redirige solo a HTTPS, define `DJANGO_SSL_REDIRECT=1`; cuando HTTPS esté estable puedes subir `DJANGO_HSTS_SECONDS` (p. ej. `31536000`).

### 6. Correo: recuperar contraseña y avisos
**Sin esta configuración la recuperación de contraseña no puede enviar correos** (en desarrollo el correo se imprime en la terminal). Crea una cuenta de correo en cPanel (p. ej. `avisos@aircontrolpro.cl`) y completa `EMAIL_*` y `DEFAULT_FROM_EMAIL` con esa misma cuenta; si el remitente no coincide con la cuenta SMTP, muchos servidores rechazan o mandan a spam.

**Recuperar contraseña:** en el ingreso, *¿Olvidaste tu contraseña?* → la persona escribe su correo → recibe un enlace que vale 2 horas y sirve una sola vez. La respuesta es la misma exista o no el correo (no revela qué cuentas hay). Por eso **cada usuario debe tener correo** (es obligatorio y no puede repetirse al crear o editar usuarios). Si tú, administrador, pierdes el acceso y tu correo no funciona, se cambia desde el servidor: `python manage.py changepassword TU_USUARIO`.

**Aviso diario de cotizaciones por llamar:**
Con la cuenta ya creada, completa `EMAIL_*`, `DEFAULT_FROM_EMAIL` y `AVISOS_EMAIL` y agrega un **Cron Job** diario (p. ej. 09:00):

```bash
cd /home/USUARIO/ruta-del-proyecto && /home/USUARIO/virtualenv/ruta/3.12/bin/python manage.py avisar_cotizaciones
```

`python manage.py avisar_cotizaciones --dry-run` muestra el correo sin enviarlo. Sin `AVISOS_EMAIL` se usa el correo de los usuarios administradores.

### Fotos y respaldos
Las fotos y firmas se guardan en `media/` y **solo se sirven con sesión y permiso** (el cliente ve únicamente las de sus informes emitidos). Incluye `media/` y la base de datos en tus respaldos de cPanel; `DJANGO_MEDIA_ROOT` permite moverla fuera de la carpeta del proyecto para que un despliegue nunca la pise.

## Desarrollo local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
echo DJANGO_DEBUG=1 > .env            # sin DB_NAME usa SQLite (db.sqlite3)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
python manage.py test
```
