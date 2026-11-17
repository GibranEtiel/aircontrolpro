/* Formularios de equipo y de ubicación: la empresa se elige de la lista o se crea ahí mismo, y la sucursal
   (solo en el formulario de equipo) se elige entre las de esa empresa o también se crea ahí mismo. */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var emp = $('id_cliente'), empN = $('id_empresa_nueva'), suc = $('id_ubicacion'), sucN = $('id_ubicacion_nueva');
  if (!emp || !empN) return;
  var caja = function (el) { return el.closest('[class*="col-"]'); };
  var enlaceNuevo = function (padre) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn btn-link btn-sm p-0 mt-1 fw-bold';
    padre.appendChild(b);
    return b;
  };
  var hayError = function (el) { return caja(el).querySelector('.text-danger') !== null; };

  var cajaEmp = caja(emp), cajaEmpN = caja(empN), enlaceEmp = enlaceNuevo(cajaEmp);
  var modoEmpresa = empN.value.trim() !== '' || hayError(empN);
  var cajaSuc, cajaSucN, enlaceSuc, modoSucursal = false;
  if (suc && sucN) {
    cajaSuc = caja(suc); cajaSucN = caja(sucN); enlaceSuc = enlaceNuevo(cajaSuc);
    modoSucursal = sucN.value.trim() !== '' || hayError(sucN);
  }

  function sucursalesDeLaEmpresa() {
    var n = 0;
    Array.prototype.forEach.call(suc.options, function (o) {
      if (!o.value) return;
      var propia = o.dataset.cliente === emp.value;
      o.hidden = o.disabled = !propia;
      if (propia) n++; else if (o.selected) suc.value = '';
    });
    return n;
  }

  function pintar() {
    // Empresa: lista o nueva
    emp.disabled = modoEmpresa;
    if (modoEmpresa) emp.value = '';
    cajaEmpN.hidden = !modoEmpresa;
    if (!modoEmpresa) empN.value = '';
    enlaceEmp.textContent = modoEmpresa ? 'Elegir una empresa que ya existe' : '¿La empresa es nueva? Créala aquí';

    // Sucursal (solo en el formulario de equipo)
    if (!suc || !sucN) return;
    var hay = (emp.value && !modoEmpresa) ? sucursalesDeLaEmpresa() : 0;
    var sinSucursales = modoEmpresa || (emp.value !== '' && hay === 0);   // empresa nueva o sin sucursales: se crea una
    var creando = modoSucursal || sinSucursales;
    cajaSuc.hidden = sinSucursales;
    suc.disabled = (emp.value === '' && !modoEmpresa) || creando;
    if (creando) suc.value = '';
    cajaSucN.hidden = !creando;
    sucN.placeholder = 'Sucursal principal';
    enlaceSuc.hidden = (emp.value === '' && !modoEmpresa) || sinSucursales;
    enlaceSuc.textContent = modoSucursal ? 'Elegir una sucursal que ya existe' : '¿La sucursal es nueva? Créala aquí';
    if (!creando) sucN.value = '';
  }

  enlaceEmp.addEventListener('click', function () {
    modoEmpresa = !modoEmpresa;
    modoSucursal = false;
    pintar();
    (modoEmpresa ? empN : emp).focus();
  });
  if (enlaceSuc) {
    enlaceSuc.addEventListener('click', function () {
      modoSucursal = !modoSucursal;
      pintar();
      (modoSucursal ? sucN : suc).focus();
    });
  }
  emp.addEventListener('change', function () { modoSucursal = false; pintar(); });
  pintar();
})();
