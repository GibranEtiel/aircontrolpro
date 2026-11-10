/* Tablero de cotizaciones: arrastra una tarjeta a otra columna (o usa el menú ⋯ en el celular)
   y el estado se guarda al instante. Los totales de cada columna se recalculan solos. */
(function () {
  'use strict';

  var tablero = document.getElementById('tablero');
  if (!tablero) return;
  var csrf = tablero.dataset.csrf;
  var toast = document.getElementById('ktoast'), toastT;
  var ACCION = {pendiente: 'reabrir', aceptada: 'aceptar', rechazada: 'rechazar'};
  var clp = function (v) { return '$' + Math.round(v).toLocaleString('es-CL'); };
  var arrastrada = null;

  function aviso(texto, error) {
    toast.textContent = texto;
    toast.className = 'ktoast on' + (error ? ' error' : '');
    clearTimeout(toastT);
    toastT = setTimeout(function () { toast.classList.remove('on'); }, 3200);
  }

  function totales() {
    Array.prototype.forEach.call(tablero.querySelectorAll('.kcol'), function (col) {
      var tarjetas = col.querySelectorAll('.kcard'), suma = 0;
      Array.prototype.forEach.call(tarjetas, function (t) { suma += parseFloat(t.dataset.neto) || 0; });
      col.querySelector('[data-n]').textContent = tarjetas.length;
      col.querySelector('[data-monto]').textContent = clp(suma);
    });
  }

  function extra(tarjeta, ordenUrl) {
    var caja = tarjeta.querySelector('.kcard-extra');
    caja.innerHTML = '';
    if (ordenUrl) {
      var a = document.createElement('a');
      a.className = 'btn btn-sm btn-info';
      a.href = ordenUrl;
      a.innerHTML = '<i class="bi bi-clipboard2-plus"></i> Generar orden';
      caja.appendChild(a);
    }
  }

  function mover(tarjeta, columna) {
    var destino = columna.dataset.estado, origen = tarjeta.closest('.kcol');
    if (origen === columna) return;
    var siguiente = tarjeta.nextElementSibling;
    columna.querySelector('[data-drop]').insertBefore(tarjeta, columna.querySelector('.kcol-vacio'));
    tarjeta.classList.add('guardando');
    totales();
    var cuerpo = new URLSearchParams({accion: ACCION[destino]});
    fetch(tarjeta.dataset.url, {
      method: 'POST', credentials: 'same-origin', body: cuerpo,
      headers: {'X-CSRFToken': csrf, 'X-Requested-With': 'fetch', 'Accept': 'application/json'}
    }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) {
        tarjeta.dataset.estado = d.estado;
        extra(tarjeta, d.orden_url);
        aviso(d.numero + ' → ' + d.etiqueta.toLowerCase() + (d.orden_url ? ' · ya puedes generar la orden de trabajo' : ''));
      })
      .catch(function () {   // si falla, la tarjeta vuelve a su lugar
        origen.querySelector('[data-drop]').insertBefore(tarjeta, siguiente && siguiente.parentNode ? siguiente : origen.querySelector('.kcol-vacio'));
        aviso('No se pudo guardar el cambio. Revisa tu conexión.', true);
      })
      .finally(function () { tarjeta.classList.remove('guardando'); totales(); });
  }

  tablero.addEventListener('dragstart', function (e) {
    var t = e.target.closest && e.target.closest('.kcard');
    if (!t) return;
    arrastrada = t;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', t.dataset.id);
    setTimeout(function () { t.classList.add('arrastrando'); }, 0);
  });
  tablero.addEventListener('dragend', function () {
    if (arrastrada) arrastrada.classList.remove('arrastrando');
    arrastrada = null;
    Array.prototype.forEach.call(tablero.querySelectorAll('.kcol'), function (c) { c.classList.remove('sobre'); });
  });
  Array.prototype.forEach.call(tablero.querySelectorAll('.kcol'), function (col) {
    col.addEventListener('dragover', function (e) {
      if (!arrastrada) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      col.classList.add('sobre');
    });
    col.addEventListener('dragleave', function (e) {
      if (!col.contains(e.relatedTarget)) col.classList.remove('sobre');
    });
    col.addEventListener('drop', function (e) {
      e.preventDefault();
      col.classList.remove('sobre');
      if (arrastrada) mover(arrastrada, col);
    });
  });

  // Alternativa táctil y de teclado: menú ⋯ de cada tarjeta.
  tablero.addEventListener('click', function (e) {
    var b = e.target.closest('.js-mover');
    if (!b) return;
    var destino = Object.keys(ACCION).filter(function (k) { return ACCION[k] === b.dataset.accion; })[0];
    mover(b.closest('.kcard'), tablero.querySelector('.kcol[data-estado="' + destino + '"]'));
  });
})();
