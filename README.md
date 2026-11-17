# Air Control Pro · Portal de mantenciones

Portal en Django con tres perfiles, con la misma identidad visual que [aircontrolpro.cl](https://aircontrolpro.cl).

| Perfil | Qué hace |
|---|---|
| **Administrador** | Dashboard (ingresos, costos, utilidad, cobranza y **cotizaciones por llamar**); gestiona cotizaciones, clientes, ubicaciones, equipos, usuarios y órdenes de trabajo; revisa y emite los informes. |
| **Técnico** | Ve sus órdenes con los **equipos que debe intervenir** (N° de equipo, ubicación exacta, R-22 fuera de norma), inicia el trabajo, completa el informe por equipo con fotos y lo envía a revisión. |
| **Cliente** | Ve solo lo de su empresa: equipos, próximas mantenciones e informes emitidos ordenados por mes. |

Flujo de una orden: `Pendiente → En proceso (técnico inicia) → En revisión (técnico envía) → Finalizada (admin emite)`.

## Pensado para el celular

Todo el portal está diseñado primero para el teléfono (es donde más se usa) y se revisó a 360 px y 320 px en los tres perfiles: nada se sale de la pantalla, las tablas se muestran como tarjetas, los botones y enlaces tienen tamaño táctil (~40 px), los campos usan 16 px para que iOS no haga zoom al tocarlos y los botones fijos respetan la zona segura de los iPhone. Al agregar una pantalla nueva, usa `class="table ... tabla-movil"` en las tablas para que se vean como tarjetas en el celular.

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

Encabezado con N° de OT, «Dirigido a», emitido por y responsable técnico; por cada equipo: N° de equipo, marca/modelo, ubicación exacta, tipo de mantenimiento, 6 actividades, observaciones (opcionales) y un interruptor **«Equipo fuera de norma»** por equipo en cada informe: parte activado si el refrigerante es R-22, pero el técnico puede apagarlo o encenderlo; si está activo el informe lo dice en rojo, fotos y mediciones. Se exporta a PDF (con fotos) y Excel; el *Informe del mes* reúne todos los equipos intervenidos por cliente.

### Las 6 fotos de cada equipo

En el editor cada equipo muestra 6 casillas numeradas, una por paso del trabajo: **1 Aplicación del líquido · 2 Lavado con hidrolavadora · 3 Secado con soplador · 4 Equipo desarmado · 5 Condensadora (opcional) · 6 Equipo armado y funcionando**. La lista y qué pasos son obligatorios se cambian en `PASOS_FOTO` ([mantenciones/models.py](mantenciones/models.py)).

- Cada casilla guarda **una** foto y se puede llenar con la **cámara** o con **«Galería»** (una foto que ya tengas en el teléfono). *Retomar* o *Galería* la reemplazan y **«Quitar»** la borra por si te equivocaste. Además hay *Otras fotos* libres para detalles o daños.
- **Si el técnico olvida una foto no queda bloqueado:** puede terminar el equipo (la app le avisa qué falta y le pide confirmar) y enviar el informe. Las fotos faltantes aparecen en *Mi jornada → Fotos pendientes*, arriba del editor, y en el detalle de la orden y del informe (para el administrador); con un clic llega a la casilla y la sube. Puede completarlas mientras el informe no esté emitido al cliente; el administrador, en cualquier momento.
- La condensadora no cuenta como pendiente.

### Informe por equipo y general de la orden

- **Informe del equipo (PDF):** disponible apenas el técnico termina ese equipo. Lleva los datos, las actividades, las fotos en el orden del trabajo con el paso al pie, y las mediciones.
- **Informe general de la orden (PDF/Excel):** reúne todos los equipos intervenidos de esa orden de trabajo. Está en el editor, en el detalle del informe y en el detalle de la orden. El Excel incluye la columna de fotos pendientes.

**Numeración de OT:** `456/26` (número/año). Vacío = siguiente del año; para partir desde otro número escribe la primera a mano y las siguientes continúan.

## Eliminar empresas, sucursales, equipos y usuarios

En la pantalla de **editar** de cada uno hay un botón **Eliminar** (solo el administrador). Pide confirmación y muestra qué se eliminaría junto con él (una empresa arrastra sus sucursales y equipos).

- **Lo que tiene historial no se borra:** una empresa, sucursal o equipo con órdenes de trabajo, informes o cotizaciones, o un técnico con trabajos hechos, no se puede eliminar porque ese historial es el respaldo de lo trabajado y cobrado. En su lugar se ofrece **Desactivar**: deja de aparecer para elegir, pero todo lo anterior queda intacto.
- **Protecciones de usuarios:** no puedes eliminarte ni desactivarte a ti mismo, ni dejar el portal sin administrador.

## Datos personales

El portal guarda solo lo necesario: nombre, correo y teléfono de los usuarios y de los contactos de cada empresa, y el nombre de la empresa. **No guarda RUT.** Si quieres reducir aún más lo que se almacena, el teléfono y el contacto de las empresas son opcionales. Esto es una guía técnica, no asesoría legal: si tienes dudas sobre la Ley de protección de datos personales, consúltalo con un abogado.

## Puesta en producción en cPanel

### 1. Base de datos (vacía)
En cPanel → **Bases de datos MySQL**:
1. **Crear la base** (ya hecho si la ves en «Bases de datos actuales»). cPanel le antepone el prefijo de tu cuenta, por ejemplo `aircontr_aircontrol-gi`: ese nombre completo, con el prefijo, es el que va en `DB_NAME`.
2. **Crear un usuario MySQL** (sección «Agregar un nuevo usuario»), con una contraseña larga (usa el generador). También lleva prefijo: `aircontr_app`. Este usuario es solo para que la app hable con la base; no es el de ingreso al portal.
3. **Agregar el usuario a la base** (sección «Agregar usuario a la base de datos»): elige el usuario y la base → **Todos los privilegios** → Realizar cambios. Si en «Usuarios con privilegio» de la base no aparece nadie, falta este paso y la app no podrá conectarse.
4. En **phpMyAdmin → tu base → Operaciones → Cotejamiento**, deja `utf8mb4_unicode_ci` (así se guardan bien tildes y la ñ).

No importes nada: la base se sube **vacía** y Django crea las tablas solo con `migrate` (paso 4). Se recomienda MariaDB 10.6+ / MySQL 8+ (requisito de Django 6.1; si tu servidor es más antiguo usa `Django>=5.2,<5.3` en `requirements.txt`).

### 2. Aplicación Python
En cPanel → **Setup Python App** → *Create Application*: versión de Python 3.12 o superior, *Application root* = carpeta donde subas el proyecto, *Application URL* = p. ej. `portal.aircontrolpro.cl`, *Startup file* `passenger_wsgi.py`, *Entry point* `application`. Sube el código (git o administrador de archivos, **sin** `.env` local ni `db.sqlite3`).

### 3. Variables de entorno
El proyecto trae [`.env.produccion`](.env.produccion) (no se sube a git): ya tiene una clave secreta nueva, el nombre de la base y el subdominio. Solo completa lo que dice **`PEGA_AQUI…`**: el usuario y la contraseña MySQL, la carpeta de fotos, y la cuenta de correo. Mientras quede alguno sin completar, la app **no arranca** y el error dice exactamente cuál falta (si no usarás correo todavía, borra esas líneas).

Súbelo a la carpeta del proyecto en el servidor y **renómbralo a `.env`** (con el punto al inicio; en el Administrador de archivos activa «Mostrar archivos ocultos»). También sirve cargar las mismas variables en *Environment variables* de Setup Python App. Con `DJANGO_DEBUG=0` el sitio exige clave secreta propia y cookies seguras. Nunca reutilices claves ni contraseñas de otro proyecto.

### 4. Instalar, crear las tablas y los dos usuarios iniciales
En el terminal de cPanel (o el botón *Run Pip Install* de la app), dentro del entorno virtual que muestra Setup Python App (Setup Python App te muestra el comando `source .../bin/activate` para entrar):

```bash
pip install -r requirements.txt
python manage.py migrate                   # crea las tablas, todas vacías
python manage.py collectstatic --noinput
python manage.py crear_usuarios_iniciales  # administrador y técnico
```

`crear_usuarios_iniciales` pregunta los datos por pantalla (usuario, nombre, correo, teléfono) y las **contraseñas escondidas**: no quedan guardadas en ningún archivo. Crea solo dos usuarios: el **administrador** (parte con `benjamin`, con acceso total) y el **técnico**. No pisa usuarios que ya existan. Si tu hosting no da un terminal interactivo, pasa los datos como opciones (`--admin-usuario`, `--admin-correo`, `--tecnico-usuario`…) y las contraseñas con las variables `ACP_ADMIN_CLAVE` y `ACP_TECNICO_CLAVE`, que debes borrar del panel apenas termine.

Reinicia la app (*Restart* en Setup Python App) y entra a `/login/`. Todo lo demás (**clientes, ubicaciones, equipos y usuarios** clientes) se crea desde el menú. No se carga ningún dato de ejemplo.

Para comprobar la conexión **antes** de migrar ejecuta `python manage.py probar_conexion`: dice si conecta, la versión de MySQL/MariaDB (avisa si es muy antigua para Django 6.1) y si la base está vacía; si falla, explica qué revisar (usuario, contraseña, privilegios o `DB_HOST`). Después de migrar, `python manage.py showmigrations` debe mostrar todo con `[X]`.

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

### Conectar con la página principal (aircontrolpro.cl)

La página pública (WordPress) **no se reemplaza**: el portal vive en un subdominio, `portal.aircontrolpro.cl`, y la página solo agrega un botón **Iniciar sesión** que lleva ahí. Son dos sitios separados (cookies y sesiones independientes), así que no se estorban.

1. **Crear el subdominio** en cPanel → *Dominios* (o *Subdominios*): `portal.aircontrolpro.cl`. En *Raíz del documento* **no** dejes la que propone cPanel (`public_html/app`): escribe una carpeta **fuera de `public_html`**, por ejemplo `portal.aircontrolpro.cl`. Si queda dentro, las reglas `.htaccess` de WordPress pueden interferir.
2. **Setup Python App** (pasos 2 a 4 de arriba) usando ese subdominio como *Application URL*.
3. **Variables de entorno:** `DJANGO_ALLOWED_HOSTS=portal.aircontrolpro.cl` y `DJANGO_CSRF_TRUSTED_ORIGINS=https://portal.aircontrolpro.cl`.
4. **HTTPS:** en cPanel → *SSL/TLS Status* ejecuta *Run AutoSSL* para que el subdominio tenga certificado (puede tardar unos minutos).
5. **El botón en WordPress.** El tema oculta «Ver disponibilidad» en pantallas menores a 820 px, y en el celular el encabezado no tiene espacio para otro botón con texto: por eso en el celular el botón se muestra como un círculo con el ícono de usuario, al lado del menú.

   En el archivo `header.php` del tema (`wp-content/themes/aircontrolpro-theme/`, **haz una copia antes de editar**), dentro de `<div class="acp-header__actions">` y **antes** del enlace «Ver disponibilidad», pega:

   ```html
   <a class="acp-button acp-button--outline acp-header__login" href="https://portal.aircontrolpro.cl/login/" aria-label="Iniciar sesión (clientes y equipo)">
     <svg class="acp-login-icon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8"/></svg>
     <span class="acp-login-texto">Iniciar sesión</span>
   </a>
   ```

   Y en WordPress → *Apariencia → Personalizar → CSS adicional* (así sobrevive si se actualiza el tema):

   ```css
   .acp-header__login { min-height: 42px; padding-inline: 17px; font-size: .78rem; gap: 8px; background: #fff; }
   .acp-login-icon { flex: none; }
   @media (max-width: 820px) {
     .acp-header__actions { gap: 10px; }
     .acp-header__login { width: 42px; padding: 0; border-radius: 50%; }  /* solo el ícono, junto al menú */
     .acp-login-texto { display: none; }
   }
   ```

   Si el tema se actualiza desde un repositorio o un .zip tuyo, haz el mismo cambio en el original para no perderlo.

### Fotos y respaldos
Las fotos y firmas se guardan en `media/` y **solo se sirven con sesión y permiso** (el cliente ve únicamente las de sus informes emitidos). Incluye `media/` y la base de datos en tus respaldos de cPanel; `DJANGO_MEDIA_ROOT` la mueve fuera de la carpeta del proyecto para que un despliegue nunca la pise; en `.env.produccion` ya viene como `~/aircontrolpro_media` (`~` es tu carpeta personal del hosting, así no necesitas saber tu usuario de cPanel) y la carpeta se crea sola. `python manage.py probar_conexion` te muestra la ruta real y comprueba que se pueda escribir.

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
