// Edición del informe técnico desde el celular: fotos y firma.
(function () {
  var form = document.getElementById('informe-form');
  var csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
  // --- Fotos -------------------------------------------------------------
  function crearMiniatura(d) {
    var div = document.createElement('div');
    div.className = 'foto';
    div.dataset.id = d.id;
    div.innerHTML = '<a target="_blank"><img alt=""></a><span class="etapa"></span>' +
      '<button type="button" class="quitar" aria-label="Quitar foto">&times;</button>';
    div.querySelector('a').href = d.url;
    div.querySelector('img').src = d.url;
    div.querySelector('.etapa').textContent = (d.titulo || d.etapa);
    div.querySelector('.quitar').dataset.url = d.eliminar;
    return div;
  }

  function subirFoto(archivo, input) {
    var contenedor = input.closest('.js-bloque-fotos');
    var grid = contenedor.querySelector('.js-fotos');
    var datos = new FormData();
    datos.append('imagen', archivo);
    var etapa = contenedor.querySelector('.js-etapa');
    datos.append('etapa', etapa ? etapa.value : 'otro');
    if (input.dataset.equipo) datos.append('equipo', input.dataset.equipo);
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

  // --- Fotos del procedimiento (6 pasos por equipo) ----------------------------
  function progreso(tarjeta) {
    var obligatorias = tarjeta.querySelectorAll('.slot[data-obligatoria="1"]');
    var faltan = Array.prototype.filter.call(obligatorias, function (sl) { return !sl.classList.contains('lleno'); });
    tarjeta.dataset.faltan = faltan.map(function (sl) { return sl.dataset.nombre; }).join(', ');
    var badge = tarjeta.querySelector('[data-progreso]');
    var hechas = obligatorias.length - faltan.length;
    badge.className = 'badge fotos-progreso ' + (faltan.length ? 'text-bg-warning' : 'text-bg-success');
    badge.innerHTML = faltan.length
      ? '<i class="bi bi-camera"></i> ' + hechas + ' de ' + obligatorias.length + ' obligatorias · faltan ' + faltan.length
      : '<i class="bi bi-check-circle"></i> Fotos completas';
  }
  function pintarSlot(slot, d) {
    var img = slot.querySelector('.slot-img'), boton = slot.querySelector('.slot-btn');
    var quitar = slot.querySelector('.slot-quitar');
    if (d) {
      img.href = d.url; img.target = '_blank';
      img.innerHTML = '<img alt="">';
      img.querySelector('img').src = d.url + (d.url.indexOf('?') < 0 ? '?t=' + Date.now() : '');
      slot.classList.add('lleno');
      boton.classList.replace('btn-info', 'btn-outline-secondary');
      boton.querySelector('span').textContent = 'Retomar';
      quitar.dataset.url = d.eliminar; quitar.hidden = false;
    } else {
      img.removeAttribute('href'); img.removeAttribute('target');
      img.innerHTML = '<i class="bi bi-camera"></i>';
      slot.classList.remove('lleno');
      boton.classList.replace('btn-outline-secondary', 'btn-info');
      boton.querySelector('span').textContent = 'Tomar foto';
      quitar.hidden = true; delete quitar.dataset.url;
    }
    progreso(slot.closest('.equipo-card'));
  }
  document.querySelectorAll('.equipo-card').forEach(progreso);

  document.querySelectorAll('.js-slot').forEach(function (input) {
    input.addEventListener('change', function () {
      var archivo = input.files[0], slot = input.closest('.slot');
      input.value = '';
      if (!archivo) return;
      var datos = new FormData();
      datos.append('imagen', archivo);
      datos.append('equipo', input.dataset.equipo);
      datos.append('paso', input.dataset.paso);
      slot.classList.add('subiendo');
      fetch(form.dataset.fotoUrl, {method: 'POST', body: datos, headers: {'X-CSRFToken': csrf}})
        .then(function (r) { return r.json().then(function (j) { return {ok: r.ok, json: j}; }); })
        .then(function (res) {
          if (!res.ok) throw new Error(res.json.error || 'No se pudo subir la foto.');
          pintarSlot(slot, res.json);
        })
        .catch(function (e) { alert(e.message || 'No se pudo subir la foto.'); })
        .then(function () { slot.classList.remove('subiendo'); });
    });
  });
  form.addEventListener('click', function (ev) {
    var boton = ev.target.closest('.slot-quitar');
    if (!boton || !boton.dataset.url || !confirm('¿Quitar esta foto?')) return;
    var slot = boton.closest('.slot');
    fetch(boton.dataset.url, {method: 'POST', headers: {'X-CSRFToken': csrf}})
      .then(function (r) { if (!r.ok) throw new Error(); pintarSlot(slot, null); })
      .catch(function () { alert('No se pudo quitar la foto.'); });
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
  // Un lienzo para firmar con el dedo; se usa dos veces: firma del cliente y firma del técnico.
  function lienzoFirma(idCanvas, idLimpiar, idCampo) {
    var canvas = document.getElementById(idCanvas);
    if (!canvas) return {guardar: function () {}};
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
    document.getElementById(idLimpiar).addEventListener('click', function () {
      ctx.clearRect(0, 0, canvas.width, canvas.height); firmado = false;
    });
    ajustarCanvas();
    return {guardar: function () { if (firmado) document.getElementById(idCampo).value = canvas.toDataURL('image/png'); }};
  }
  var firmaCliente = lienzoFirma('firma', 'firma-limpiar', 'firma_data');
  var firmaTecnico = lienzoFirma('firma-tecnico', 'firma-tecnico-limpiar', 'firma_tecnico_data');

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
    firmaCliente.guardar();
    firmaTecnico.guardar();
    var accion = ev.submitter ? ev.submitter.value : '';
    if (accion.indexOf('terminar_') === 0) {
      var tarjeta = ev.submitter.closest('.equipo-card');
      if (tarjeta && tarjeta.dataset.faltan &&
          !confirm('Faltan estas fotos: ' + tarjeta.dataset.faltan + '.' + String.fromCharCode(10, 10) + '¿Terminar el equipo de todas formas? Podrás agregarlas después.')) {
        ev.preventDefault();
      }
      return;
    }
    var enviar = accion === 'enviar';
    if (!enviar) return;
    var conFaltas = Array.prototype.filter.call(document.querySelectorAll('.equipo-card'), function (t) { return t.dataset.faltan; });
    var aviso = conFaltas.length ? 'Aún faltan fotos en ' + conFaltas.length + ' equipo(s). Puedes completarlas mientras el informe esté en revisión.' + String.fromCharCode(10, 10) : '';
    if (!confirm(aviso + '¿Enviar el informe a revisión?')) {
      ev.preventDefault(); return;
    }
  });
})();
