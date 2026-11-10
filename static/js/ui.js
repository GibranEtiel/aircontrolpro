/* Detalles de interacción compartidos: los números con data-count "suben" al cargar la página. */
(function () {
  'use strict';
  if (document.getElementById('dash-data')) return;  // el dashboard del administrador tiene su propia versión
  var reducido = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.querySelectorAll('[data-count]').forEach(function (el) {
    var hasta = parseFloat(el.dataset.count);
    if (isNaN(hasta) || reducido) return;
    var t0 = null, dur = 700;
    (function paso(t) {
      if (t0 === null) t0 = t;
      var p = Math.min((t - t0) / dur, 1);
      el.textContent = Math.round(hasta * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(paso);
    })(performance.now());
    setTimeout(function () { el.textContent = Math.round(hasta); }, dur + 80);
  });
})();
