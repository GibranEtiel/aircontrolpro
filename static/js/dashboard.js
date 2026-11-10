/* Dashboard del administrador: interactivo y sin recargar la página.
   - Las tarjetas de KPI cambian el gráfico principal (barras o línea, año o 30 días, comparación con el año anterior).
   - Cambiar año o cliente pide los datos nuevos a /dashboard/datos/ y todo se transforma con animación.
   - Tocar un cliente del ranking filtra todo el panel. */
(function () {
  'use strict';

  var cfg = document.getElementById('dash-config').dataset;
  var datos = JSON.parse(document.getElementById('dash-data').textContent);
  var reducido = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var COLORES = {ingresos: '#0881c5', costos: '#f6410f', utilidad: '#12905a', por_cobrar: '#f0a500'};
  var NOMBRES = {ingresos: 'Ingresos netos', costos: 'Costos', utilidad: 'Utilidad', por_cobrar: 'Por cobrar'};
  var ESTADO_COLOR = ['#8aa3b3', '#0881c5', '#f0a500', '#12905a', '#f6410f'];
  var estado = {metrica: 'ingresos', rango: 'anio', tipo: 'bar', comparar: false};

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var clp = function (v) { return '$' + Math.round(v).toLocaleString('es-CL'); };
  var corto = function (v) {
    var a = Math.abs(v);
    if (a >= 1e6) return (v / 1e6).toLocaleString('es-CL', {maximumFractionDigits: 1}) + ' M';
    if (a >= 1e3) return Math.round(v / 1e3) + ' mil';
    return String(Math.round(v));
  };
  var esc = function (t) {
    var d = document.createElement('div');
    d.textContent = t == null ? '' : String(t);
    return d.innerHTML;
  };

  /* ---------- números que "suben" al cargar ---------- */
  function contar(el, hasta, formato) {
    formato = formato || function (v) { return String(Math.round(v)); };
    var desde = el._valor || 0;
    el._valor = hasta;
    if (reducido || desde === hasta) { el.textContent = formato(hasta); return; }
    var t0 = null, dur = 700;
    cancelAnimationFrame(el._raf);
    clearTimeout(el._fin);
    el._fin = setTimeout(function () { cancelAnimationFrame(el._raf); el.textContent = formato(hasta); }, dur + 80);
    (function paso(t) {
      if (t0 === null) t0 = t;
      var p = Math.min((t - t0) / dur, 1), e = 1 - Math.pow(1 - p, 3);
      el.textContent = formato(desde + (hasta - desde) * e);
      if (p < 1) el._raf = requestAnimationFrame(paso);
    })(performance.now());
  }

  /* ---------- gráfico principal ---------- */
  var principal;
  function serieActual() {
    var s = datos[estado.rango === 'anio' ? 'meses' : 'dias'];
    return {labels: s.labels, valores: s[estado.metrica], ordenes: s.ordenes};
  }
  function degradado(c1, c2) {
    return function (ctx) {
      var ch = ctx.chart, a = ch.chartArea;
      if (!a) return c1;
      var g = ch.ctx.createLinearGradient(0, a.top, 0, a.bottom);
      g.addColorStop(0, c1);
      g.addColorStop(1, c2);
      return g;
    };
  }
  function rgba(hex, a) {
    var n = parseInt(hex.slice(1), 16);
    return 'rgba(' + (n >> 16) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
  }
  function datasetsPrincipal() {
    var s = serieActual(), color = COLORES[estado.metrica], linea = estado.tipo === 'line';
    var ds = [{
      type: estado.tipo, label: NOMBRES[estado.metrica], data: s.valores, borderColor: color, borderWidth: linea ? 3 : 0,
      backgroundColor: linea ? degradado(rgba(color, .28), rgba(color, 0)) : degradado(color, rgba(color, .35)),
      fill: linea, tension: .38, borderRadius: 8, borderSkipped: false, maxBarThickness: 38,
      pointRadius: linea ? 3 : 0, pointHoverRadius: 7, pointBackgroundColor: '#fff', pointBorderColor: color,
      pointBorderWidth: 2, order: 1
    }];
    if (estado.comparar && estado.rango === 'anio') {
      ds.push({type: 'line', label: 'Año anterior (' + (datos.anio - 1) + ')', data: datos.meses_previo[estado.metrica],
               borderColor: '#8aa3b3', borderDash: [6, 5], borderWidth: 2, pointRadius: 0, pointHoverRadius: 5,
               fill: false, tension: .38, order: 0});
    }
    return ds;
  }
  function crearPrincipal() {
    var s = serieActual();
    principal = new Chart($('#chPrincipal'), {
      data: {labels: s.labels, datasets: datasetsPrincipal()},
      options: {
        maintainAspectRatio: false, animation: reducido ? false : {duration: 650, easing: 'easeOutQuart'},
        interaction: {mode: 'index', intersect: false},
        plugins: {
          legend: {display: false},
          tooltip: {
            backgroundColor: '#071f33', padding: 12, cornerRadius: 12, titleFont: {weight: '700'}, displayColors: true,
            callbacks: {
              label: function (c) { return ' ' + c.dataset.label + ': ' + clp(c.parsed.y); },
              afterBody: function (items) {
                var n = serieActual().ordenes[items[0].dataIndex];
                return n ? n + ' orden' + (n === 1 ? '' : 'es') + ' finalizada' + (n === 1 ? '' : 's') : '';
              }
            }
          }
        },
        scales: {
          x: {grid: {display: false}, border: {display: false}},
          y: {beginAtZero: true, border: {display: false}, grid: {color: 'rgba(7,31,51,.07)'},
              ticks: {callback: function (v) { return '$' + corto(v); }, maxTicksLimit: 6}}
        }
      }
    });
  }
  function actualizarPrincipal() {
    var s = serieActual();
    principal.data.labels = s.labels;
    principal.data.datasets = datasetsPrincipal();
    principal.update();
    $('#graf-titulo').textContent = NOMBRES[estado.metrica] + (estado.rango === 'anio' ? ' por mes · ' + datos.anio : ' · últimos 30 días');
    var total = s.valores.reduce(function (a, b) { return a + b; }, 0);
    $('#graf-sub').textContent = 'Total del período: ' + clp(total) + (estado.metrica === 'por_cobrar' ? ' (por mes de la orden)' : '');
    $('#btn-comparar').hidden = estado.rango !== 'anio';
  }

  /* ---------- tarjetas de KPI: valor, variación y mini gráfico ---------- */
  function spark(valores, color) {
    var w = 120, h = 34, max = Math.max.apply(null, valores.concat([1])), min = Math.min.apply(null, valores.concat([0]));
    var rango = (max - min) || 1, paso = w / Math.max(valores.length - 1, 1);
    var pts = valores.map(function (v, i) { return [i * paso, h - 3 - ((v - min) / rango) * (h - 8)]; });
    var d = pts.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' ');
    return '<svg viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" aria-hidden="true">' +
      '<path d="' + d + ' L' + w + ' ' + h + ' L0 ' + h + ' Z" fill="' + rgba(color, .13) + '"/>' +
      '<path d="' + d + '" fill="none" stroke="' + color + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  }
  function actualizarKpis() {
    var k = datos.kpis;
    $$('.kpi-tile').forEach(function (t) {
      var m = t.dataset.metrica, v = $('[data-valor]', t);
      contar(v, k[m], clp);
      $('[data-spark]', t).innerHTML = spark(datos.meses[m], COLORES[m]);
      var dl = $('[data-delta]', t);
      if (dl) {
        var c = k.comparacion[m];
        if (c === null || c === undefined) { dl.textContent = ''; dl.className = 'kpi-delta'; dl.removeAttribute('title'); }
        else {
          var bueno = m === 'costos' ? c <= 0 : c >= 0;
          dl.className = 'kpi-delta ' + (bueno ? 'bien' : 'mal');
          dl.innerHTML = '<i class="bi bi-arrow-' + (c >= 0 ? 'up' : 'down') + '-short"></i>' + Math.abs(c) + '%';
          dl.title = 'Respecto a ' + k.comparado_con;
        }
      }
    });
    var margen = $('[data-margen]'); if (margen) margen.textContent = k.margen;
    var n = $('[data-cobrar-n]'); if (n) n.textContent = k.por_cobrar_n;
    var cum = $('[data-cumplimiento]'); if (cum) cum.textContent = k.cumplimiento;
    var hoyMes = datos.hoy ? parseInt(datos.hoy.slice(5, 7), 10) - 1 : null, esActual = datos.hoy && parseInt(datos.hoy.slice(0, 4), 10) === datos.anio;
    ['ingresos', 'utilidad'].forEach(function (m) {
      var sub = $('.kpi-tile[data-metrica="' + m + '"] [data-sub]');
      if (sub) sub.textContent = esActual ? 'Este mes: ' + clp(datos.meses[m][hoyMes]) : '';
    });
    $$('.kpi-tile .kpi-label')[0].textContent = 'Ingresos netos ' + datos.anio;
  }

  /* ---------- órdenes por estado ---------- */
  var dona;
  function actualizarEstados() {
    var total = datos.estados.reduce(function (a, e) { return a + e.n; }, 0);
    contar($('#dona-total'), total);
    var datosDona = {labels: datos.estados.map(function (e) { return e.label; }),
                     datasets: [{data: datos.estados.map(function (e) { return e.n; }), backgroundColor: ESTADO_COLOR,
                                 borderWidth: 3, borderColor: '#fff', hoverOffset: 8}]};
    if (!dona) {
      dona = new Chart($('#chEstados'), {
        type: 'doughnut', data: datosDona,
        options: {
          maintainAspectRatio: false, cutout: '70%', animation: reducido ? false : {duration: 700},
          plugins: {legend: {display: false}, tooltip: {backgroundColor: '#071f33', cornerRadius: 10}},
          onClick: function (e, els) { if (els.length) location.href = datos.estados[els[0].index].url; },
          onHover: function (e, els) { e.native.target.style.cursor = els.length ? 'pointer' : 'default'; }
        }
      });
    } else { dona.data = datosDona; dona.update(); }
    var ul = $('#estados-lista');
    ul.innerHTML = datos.estados.map(function (e, i) {
      return '<li><a href="' + esc(e.url) + '" data-i="' + i + '"><span class="punto" style="background:' + ESTADO_COLOR[i] + '"></span>' +
        '<span class="nombre">' + esc(e.label) + '</span><b>' + e.n + '</b></a></li>';
    }).join('');
    $$('a', ul).forEach(function (a) {   // pasar el mouse por la lista resalta el trozo del gráfico
      a.addEventListener('mouseenter', function () {
        var i = +a.dataset.i;
        dona.setActiveElements([{datasetIndex: 0, index: i}]);
        dona.tooltip.setActiveElements([{datasetIndex: 0, index: i}], {x: 0, y: 0});
        dona.update();
      });
      a.addEventListener('mouseleave', function () {
        dona.setActiveElements([]); dona.tooltip.setActiveElements([], {x: 0, y: 0}); dona.update();
      });
    });
  }

  /* ---------- embudo de cotizaciones ---------- */
  function actualizarEmbudo() {
    var c = datos.cotizaciones, max = Math.max(c.enviadas, 1);
    $('#embudo-sub').textContent = c.enviadas ? 'Cotizaciones de ' + datos.anio : 'Aún no hay cotizaciones en ' + datos.anio;
    $('#embudo').innerHTML = c.embudo.map(function (p, i) {
      var ancho = p.n ? Math.max(p.n / max * 100, 14) : 4;
      var conv = i && c.embudo[i - 1].n ? Math.round(p.n / c.embudo[i - 1].n * 100) + '% del paso anterior' : '';
      return '<a class="embudo-paso" href="' + esc(p.url) + '"><div class="embudo-cab"><span>' + esc(p.label) + '</span>' +
        '<span><b>' + p.n + '</b> · ' + clp(p.monto) + '</span></div>' +
        '<div class="embudo-pista"><div class="embudo-barra" style="background:' + p.color + '" data-ancho="' + ancho + '"></div></div>' +
        (conv ? '<div class="embudo-conv">' + conv + '</div>' : '') + '</a>';
    }).join('');
    requestAnimationFrame(function () {
      $$('#embudo .embudo-barra').forEach(function (b) { b.style.width = b.dataset.ancho + '%'; });
    });
    $('#embudo-pie').innerHTML =
      '<span><i class="bi bi-hourglass-split"></i> <b>' + c.pendientes + '</b> pendientes · ' + clp(c.pendientes_monto) + '</span>' +
      '<span><i class="bi bi-bullseye"></i> Cierre <b>' + (c.cierre === null ? '—' : c.cierre + '%') + '</b></span>';
  }

  /* ---------- agenda ---------- */
  function actualizarAgenda() {
    var ul = $('#agenda');
    if (!datos.agenda.length) {
      ul.innerHTML = '<li class="vacio"><i class="bi bi-calendar-check"></i>No hay órdenes pendientes para los próximos 7 días.</li>';
      return;
    }
    ul.innerHTML = datos.agenda.map(function (o) {
      var clase = o.atrasada ? 'tarde' : o.hoy ? 'hoy' : '';
      return '<li><a href="' + esc(o.url) + '"><span class="fecha ' + clase + '">' + esc(o.cuando) + '</span>' +
        '<span class="cuerpo"><b>' + esc(o.numero) + ' · ' + esc(o.titulo) + '</b>' +
        '<small>' + esc(o.cliente) + ' · ' + esc(o.ubicacion) + '</small></span>' +
        '<span class="meta">' + (o.alta ? '<i class="bi bi-exclamation-triangle-fill text-danger" title="Prioridad alta"></i>' : '') +
        '<span class="chip-mini"><i class="bi bi-fan"></i> ' + o.equipos + '</span>' +
        '<span class="chip-mini ' + (o.tecnico ? '' : 'sin') + '"><i class="bi bi-person"></i> ' + esc(o.tecnico || 'Sin técnico') + '</span></span></a></li>';
    }).join('');
  }

  /* ---------- rankings (clientes y técnicos) ---------- */
  function actualizarRankings() {
    var cl = datos.clientes, maxC = Math.max.apply(null, cl.map(function (c) { return c.ingresos; }).concat([1]));
    $('#clientes-lista').innerHTML = cl.length ? cl.map(function (c) {
      return '<li><button type="button" class="fila-barra" data-cliente="' + c.id + '"><span class="fila-top"><span>' + esc(c.nombre) +
        '</span><b>' + clp(c.ingresos) + '</b></span><span class="pista"><span style="width:0" data-ancho="' + (c.ingresos / maxC * 100) +
        '"></span></span></button></li>';
    }).join('') : '<li class="vacio"><i class="bi bi-buildings"></i>Aún no hay órdenes finalizadas.</li>';
    var tc = datos.tecnicos, maxT = Math.max.apply(null, tc.map(function (t) { return t.ingresos; }).concat([1]));
    $('#tecnicos-lista').innerHTML = tc.length ? tc.map(function (t) {
      return '<li><div class="fila-barra tec"><span class="avatar">' + esc(t.nombre.charAt(0).toUpperCase()) + '</span><span class="tec-cuerpo">' +
        '<span class="fila-top"><span>' + esc(t.nombre) + ' <small>· ' + t.n + ' OT</small></span><b>' + clp(t.ingresos) + '</b></span>' +
        '<span class="pista verde"><span style="width:0" data-ancho="' + (t.ingresos / maxT * 100) + '"></span></span>' +
        '<small class="text-body-secondary">Utilidad ' + clp(t.utilidad) + '</small></span></div></li>';
    }).join('') : '<li class="vacio"><i class="bi bi-person-gear"></i>Aún no hay órdenes finalizadas.</li>';
    requestAnimationFrame(function () {
      $$('.pista > span[data-ancho]').forEach(function (b) { b.style.width = b.dataset.ancho + '%'; });
    });
    $$('#clientes-lista .fila-barra').forEach(function (b) {
      b.addEventListener('click', function () {
        var sel = $('#dash-filtros [name=cliente]');
        sel.value = sel.value === b.dataset.cliente ? '' : b.dataset.cliente;
        sel.dispatchEvent(new Event('change', {bubbles: true}));
      });
    });
  }

  /* ---------- equipos ---------- */
  var donaEquipos;
  function actualizarEquipos() {
    var e = datos.equipos, colores = ['#12905a', '#f0a500', '#f6410f'];
    contar($('#equipos-total'), e.total);
    $('#equipos-sub').textContent = e.total + ' equipos activos';
    var data = {labels: e.condiciones.map(function (c) { return c.label; }),
                datasets: [{data: e.condiciones.map(function (c) { return c.n; }), backgroundColor: colores, borderWidth: 3, borderColor: '#fff', hoverOffset: 6}]};
    if (!donaEquipos) {
      donaEquipos = new Chart($('#chEquipos'), {type: 'doughnut', data: data,
        options: {maintainAspectRatio: false, cutout: '70%', animation: reducido ? false : {duration: 700},
                  plugins: {legend: {position: 'bottom', labels: {usePointStyle: true, boxWidth: 8, padding: 14}},
                            tooltip: {backgroundColor: '#071f33', cornerRadius: 10}}}});
    } else { donaEquipos.data = data; donaEquipos.update(); }
    $('#equipos-alerta').innerHTML = e.fuera_norma ?
      '<div class="alerta-r22"><i class="bi bi-exclamation-triangle-fill"></i><span><b>' + e.fuera_norma + '</b> equipo' + (e.fuera_norma === 1 ? '' : 's') +
      ' con refrigerante R-22 (fuera de norma)</span></div>' : '';
  }

  /* ---------- actividad ---------- */
  function actualizarActividad() {
    var ul = $('#actividad');
    ul.innerHTML = datos.actividad.length ? datos.actividad.map(function (a) {
      return '<li><a href="' + esc(a.url) + '"><span class="ico ' + esc(a.color) + '"><i class="bi ' + esc(a.icono) + '"></i></span>' +
        '<span class="cuerpo">' + esc(a.texto) + '<small>' + esc(a.hace) + '</small></span><i class="bi bi-chevron-right flecha"></i></a></li>';
    }).join('') : '<li class="vacio"><i class="bi bi-activity"></i>Todavía no hay actividad.</li>';
  }

  function renderTodo() {
    actualizarKpis(); actualizarPrincipal(); actualizarEstados(); actualizarEmbudo(); actualizarAgenda();
    actualizarRankings(); actualizarEquipos(); actualizarActividad();
  }

  /* ---------- eventos ---------- */
  $$('.kpi-tile').forEach(function (t) {
    t.addEventListener('click', function () {
      estado.metrica = t.dataset.metrica;
      $$('.kpi-tile').forEach(function (o) {
        o.classList.toggle('activo', o === t);
        o.setAttribute('aria-pressed', o === t ? 'true' : 'false');
      });
      actualizarPrincipal();
    });
  });
  function grupo(sel, atributo, clave) {
    $$(sel + ' button').forEach(function (b) {
      b.addEventListener('click', function () {
        estado[clave] = b.dataset[atributo];
        $$(sel + ' button').forEach(function (o) { o.classList.toggle('on', o === b); });
        actualizarPrincipal();
      });
    });
  }
  grupo('#seg-rango', 'rango', 'rango');
  grupo('#seg-tipo', 'tipo', 'tipo');
  $('#btn-comparar').addEventListener('click', function () {
    estado.comparar = !estado.comparar;
    this.setAttribute('aria-pressed', estado.comparar);
    this.classList.toggle('on', estado.comparar);
    actualizarPrincipal();
  });

  var form = $('#dash-filtros'), pidiendo = 0;
  function recargar() {
    var q = new URLSearchParams(new FormData(form));
    if (!q.get('cliente')) q.delete('cliente');
    var id = ++pidiendo, caja = $('#dash'), msg = $('#dash-estado');
    caja.classList.add('cargando');
    msg.textContent = 'Actualizando…';
    fetch(cfg.urlDatos + '?' + q.toString(), {headers: {'Accept': 'application/json'}, credentials: 'same-origin'})
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) {
        if (id !== pidiendo) return;
        datos = d;
        history.replaceState(null, '', '?' + q.toString());
        renderTodo();
        msg.textContent = '';
      })
      .catch(function () { msg.innerHTML = '<span class="text-danger"><i class="bi bi-wifi-off"></i> No se pudo actualizar</span>'; })
      .finally(function () { if (id === pidiendo) caja.classList.remove('cargando'); });
  }
  form.addEventListener('change', recargar);
  form.addEventListener('submit', function (e) { e.preventDefault(); recargar(); });

  // Los números del encabezado también suben al cargar.
  $$('[data-count]').forEach(function (el) { contar(el, +el.dataset.count); });

  crearPrincipal();
  renderTodo();
})();
