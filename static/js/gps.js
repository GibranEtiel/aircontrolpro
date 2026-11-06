// Pide la ubicación al técnico antes de iniciar un trabajo (formularios .js-iniciar).
(function () {
  function obtenerPosicion() {
    return new Promise(function (resolve, reject) {
      if (!navigator.geolocation) return reject(new Error('Este dispositivo no tiene geolocalización.'));
      navigator.geolocation.getCurrentPosition(resolve, reject,
        {enableHighAccuracy: true, timeout: 15000, maximumAge: 30000});
    });
  }

  document.querySelectorAll('form.js-iniciar').forEach(function (form) {
    form.addEventListener('submit', function (ev) {
      if (form.dataset.listo) return;
      ev.preventDefault();
      var boton = form.querySelector('button');
      var texto = boton.innerHTML;
      boton.disabled = true;
      boton.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Obteniendo ubicación…';

      function enviar() { form.dataset.listo = '1'; form.submit(); }

      obtenerPosicion().then(function (pos) {
        form.querySelector('[name=lat]').value = pos.coords.latitude.toFixed(6);
        form.querySelector('[name=lng]').value = pos.coords.longitude.toFixed(6);
        form.querySelector('[name=precision]').value = Math.round(pos.coords.accuracy);
        enviar();
      }).catch(function () {
        boton.disabled = false;
        boton.innerHTML = texto;
        if (confirm('No se pudo obtener tu ubicación. Activa el GPS y permite el acceso en el navegador.\n\n¿Iniciar el trabajo sin ubicación?')) enviar();
      });
    });
  });
})();
