// Edición del informe técnico desde el celular: GPS, fotos y firma.
(function () {
  var form = document.getElementById('informe-form');
  var csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
  var pill = document.getElementById('gps-estado');
  var posicion = null;

  // --- Ubicación ---------------------------------------------------------
  function pintarGps(clase, texto) {
    pill.className = 'badge gps-pill text-bg-' + clase;
    pill.innerHTML = '<i class="bi bi-crosshair"></i> ' + texto;
  }
  if (navigator.geolocation) {
    navigator.geolocation.watchPosition(function (p) {
      posicion = p.coords;
      pintarGps('success', 'Ubicación activa (±' + Math.round(p.coords.accuracy) + ' m)');
    }, function () {
      pintarGps('danger', 'Sin ubicación: permite el acceso al GPS');
    }, {enableHighAccuracy: true, maximumAge: 10000, timeout: 20000});
  } else {
    pintarGps('danger', 'Este dispositivo no tiene GPS');
  }

  // --- Fotos -------------------------------------------------------------
  function crearMiniatura(d) {
    var div = document.createElement('div');
    div.className = 'foto';
    div.dataset.id = d.id;
    div.innerHTML = '<a target="_blank"><img alt=""></a><span class="etapa"></span>' +
      '<button type="button" class="quitar" aria-label="Quitar foto">&times;</button>';
    div.querySelector('a').href = d.url;
    div.querySelector('img').src = d.url;
    div.querySelector('.etapa').textContent = d.etapa + (d.con_gps ? ' · GPS' : '');
    div.querySelector('.quitar').dataset.url = d.eliminar;
    return div;
  }

  function subirFoto(archivo, input) {
    var contenedor = input.closest('.card-body');
    var grid = contenedor.querySelector('.js-fotos');
    var datos = new FormData();
    datos.append('imagen', archivo);
    datos.append('etapa', contenedor.querySelector('.js-etapa').value);
    if (input.dataset.equipo) datos.append('equipo', input.dataset.equipo);
    if (posicion) {
      datos.append('lat', posicion.latitude.toFixed(6));
      datos.append('lng', posicion.longitude.toFixed(6));
    }
    var espera = document.createElement('div');
    espera.className = 'foto d-flex align-items-center justify-content-center';
    espera.style.aspectRatio = '1';
    espera.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    grid.appendChild(espera);

    return fetch(form.dataset.fotoUrl, {method: 'POST', body: datos, headers: {'X-CSRFToken': csrf}})
      .then(function (r) { return r.json().then(function (j) { return {ok: r.ok, json: j}; }); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.json.error || 'No se pudo subir la foto.');
        grid.replaceChild(crearMiniatura(res.json), espera);
      })
      .catch(function (e) {
        grid.removeChild(espera);
        alert(e.message || 'No se pudo subir la foto.');
      });
  }

  document.querySelectorAll('.js-foto').forEach(function (input) {
    input.addEventListener('change', function () {
      var archivos = Array.prototype.slice.call(input.files);
      input.value = '';
      archivos.reduce(function (cadena, f) {
        return cadena.then(function () { return subirFoto(f, input); });
      }, Promise.resolve());
    });
  });

  form.addEventListener('click', function (ev) {
    var boton = ev.target.closest('.quitar');
    if (!boton || !confirm('¿Quitar esta foto?')) return;
    fetch(boton.dataset.url, {method: 'POST', headers: {'X-CSRFToken': csrf}})
      .then(function (r) {
        if (!r.ok) throw new Error();
        boton.closest('.foto').remove();
      })
      .catch(function () { alert('No se pudo quitar la foto.'); });
  });

  // --- Firma -------------------------------------------------------------
  var canvas = document.getElementById('firma');
  var ctx = canvas.getContext('2d');
  var dibujando = false, firmado = false;

  function ajustarCanvas() {
    var r = canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    canvas.width = r.width * dpr;
    canvas.height = r.height * dpr;
    ctx.scale(dpr, dpr);
    ctx.lineWidth = 2; ctx.lineCap = 'round'; ctx.strokeStyle = '#111';
    firmado = false;
  }
  function punto(ev) {
    var r = canvas.getBoundingClientRect();
    return {x: ev.clientX - r.left, y: ev.clientY - r.top};
  }
  canvas.addEventListener('pointerdown', function (ev) {
    dibujando = true; canvas.setPointerCapture(ev.pointerId);
    var p = punto(ev); ctx.beginPath(); ctx.moveTo(p.x, p.y);
  });
  canvas.addEventListener('pointermove', function (ev) {
    if (!dibujando) return;
    var p = punto(ev); ctx.lineTo(p.x, p.y); ctx.stroke(); firmado = true;
  });
  ['pointerup', 'pointercancel'].forEach(function (t) {
    canvas.addEventListener(t, function () { dibujando = false; });
  });
  document.getElementById('firma-limpiar').addEventListener('click', function () {
    ctx.clearRect(0, 0, canvas.width, canvas.height); firmado = false;
  });
  ajustarCanvas();

  // --- Agregar equipos -----------------------------------------------------
  var buscador = document.getElementById('buscar-equipo');
  if (buscador) {
    buscador.addEventListener('input', function () {
      var q = buscador.value.trim().toLowerCase();
      document.querySelectorAll('.js-equipo-disp').forEach(function (fila) {
        fila.hidden = q !== '' && fila.textContent.toLowerCase().indexOf(q) === -1;
      });
    });
    buscador.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') ev.preventDefault(); });
  }

  // --- Envío -------------------------------------------------------------
  form.addEventListener('submit', function (ev) {
    if (ev.submitter && ev.submitter.classList.contains('js-quitar-equipo') &&
        !confirm('¿Quitar este equipo del informe? Se borrarán también sus fotos.')) {
      ev.preventDefault(); return;
    }
    if (firmado) document.getElementById('firma_data').value = canvas.toDataURL('image/png');
    var enviar = ev.submitter && ev.submitter.value === 'enviar';
    if (!enviar) return;
    if (!confirm('¿Enviar el informe a revisión? Después no podrás editarlo.')) {
      ev.preventDefault(); return;
    }
    if (posicion) {
      form.querySelector('[name=lat_fin]').value = posicion.latitude.toFixed(6);
      form.querySelector('[name=lng_fin]').value = posicion.longitude.toFixed(6);
    }
  });
})();
