// Habitos - logica del cliente. Sin frameworks.

var $ = function (sel) { return document.querySelector(sel); };
var $$ = function (sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); };

var MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
var MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun",
                    "jul", "ago", "sep", "oct", "nov", "dic"];
var DIAS_CORTOS = ["dom", "lun", "mar", "mie", "jue", "vie", "sab"];

var estado = {
  tareas: [],
  filtro: "por_hacer",
  busqueda: "",
  vista: "hoy",
  calAnio: 0,
  calMes: 0,
  calSeleccion: null,
  periodo: "semana",
  resumen: null
};

// ------------------------------------------------------------ utilidades

function api(ruta, metodo, cuerpo) {
  var opciones = { method: metodo || "GET", headers: { "Content-Type": "application/json" } };
  if (cuerpo !== undefined && cuerpo !== null) {
    opciones.body = JSON.stringify(cuerpo);
  }
  return fetch(ruta, opciones).then(function (respuesta) {
    return respuesta.json().then(function (datos) {
      if (!respuesta.ok) {
        throw new Error(datos.error || "Error del servidor");
      }
      return datos;
    });
  });
}

function escapar(texto) {
  if (texto === null || texto === undefined) { return ""; }
  return String(texto)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

var temporizadorAviso = null;

function avisar(mensaje) {
  var caja = $("#aviso");
  caja.textContent = mensaje;
  caja.classList.add("visible");
  if (temporizadorAviso) { clearTimeout(temporizadorAviso); }
  temporizadorAviso = setTimeout(function () {
    caja.classList.remove("visible");
  }, 2300);
}

function dosDigitos(n) {
  return n < 10 ? "0" + n : "" + n;
}

function hoyISO() {
  var ahora = new Date();
  return ahora.getFullYear() + "-" + dosDigitos(ahora.getMonth() + 1) + "-" + dosDigitos(ahora.getDate());
}

function fechaLegible(iso) {
  if (!iso) { return ""; }
  var partes = iso.split("-");
  if (partes.length < 3) { return iso; }
  return parseInt(partes[2], 10) + " " + MESES_CORTOS[parseInt(partes[1], 10) - 1];
}

function fechaLarga(iso) {
  if (!iso) { return ""; }
  var partes = iso.split("-");
  var d = new Date(parseInt(partes[0], 10), parseInt(partes[1], 10) - 1, parseInt(partes[2], 10));
  return DIAS_CORTOS[d.getDay()] + " " + parseInt(partes[2], 10) + " de " +
         MESES[parseInt(partes[1], 10) - 1];
}

function minutosATexto(minutos) {
  if (!minutos) { return "0 min"; }
  if (minutos < 60) { return minutos + " min"; }
  var horas = Math.floor(minutos / 60);
  var resto = minutos % 60;
  if (resto === 0) { return horas + " h"; }
  return horas + " h " + resto + " min";
}

function prioridadTexto(valor) {
  if (valor === 1) { return "Alta"; }
  if (valor === 3) { return "Baja"; }
  return "Media";
}

// ------------------------------------------------------------ navegacion

function cambiarVista(nombre) {
  estado.vista = nombre;
  $$(".menu-item").forEach(function (boton) {
    boton.classList.toggle("activo", boton.getAttribute("data-vista") === nombre);
  });
  $$(".vista").forEach(function (seccion) {
    seccion.classList.remove("activa");
  });
  var vista = $("#vista-" + nombre);
  if (vista) { vista.classList.add("activa"); }

  if (nombre === "hoy") { cargarHoy(); }
  if (nombre === "tareas") { cargarTareas(); }
  if (nombre === "pomodoro") { cargarPomodoro(); }
  if (nombre === "calendario") { cargarCalendario(); }
  if (nombre === "memoria") { cargarMemoria(); }
  if (nombre === "notas") { cargarNotas(); }
  if (nombre === "metricas") { cargarMetricas(); }
}

// --------------------------------------------------------------- tarjetas

function htmlTarea(tarea, opciones) {
  opciones = opciones || {};
  var clases = "tarea";
  if (tarea.estado === "hecha") { clases += " hecha"; }

  var meta = [];
  meta.push('<span><span class="pri pri-' + tarea.prioridad + '"></span>' + prioridadTexto(tarea.prioridad) + "</span>");
  if (tarea.area) { meta.push('<span class="etiqueta">' + escapar(tarea.area) + "</span>"); }
  if (tarea.origen === "moodle") {
    meta.push('<span class="etiqueta nube">Nube</span>');
  }
  if (tarea.perdida) {
    meta.push('<span class="etiqueta perdida">sin entrega</span>');
  }
  if (tarea.estado !== "hecha" && tarea.fecha && tarea.fecha < hoyISO()) {
    meta.push('<span class="etiqueta atrasada">atrasada</span>');
  }
  if (tarea.url) {
    meta.push('<a class="enlace-moodle" href="' + escapar(tarea.url) +
              '" target="_blank" rel="noopener"><i class="bi bi-box-arrow-up-right"></i> abrir</a>');
  }
  if (tarea.fecha && !opciones.ocultarFecha) {
    var textoFecha = fechaLegible(tarea.fecha);
    if (tarea.fecha === hoyISO()) { textoFecha = "hoy"; }
    meta.push('<span><i class="bi bi-calendar3"></i> ' + textoFecha + "</span>");
  }
  if (tarea.hora) { meta.push('<span><i class="bi bi-clock"></i> ' + escapar(tarea.hora) + "</span>"); }
  meta.push('<span><i class="bi bi-hourglass-split"></i> ' + minutosATexto(tarea.estimado_min) + "</span>");
  if (tarea.estado === "hecha" && tarea.completada) {
    meta.push('<span><i class="bi bi-check2"></i> ' + fechaLegible(tarea.completada.substring(0, 10)) + "</span>");
  }

  var botonFoco = "";
  if (tarea.estado === "pendiente") {
    botonFoco = '<button class="icono-btn" data-accion="foco" data-id="' + tarea.id + '" title="Enfocar esta tarea"><i class="bi bi-play-circle"></i></button>';
  }

  return '' +
    '<div class="' + clases + '" data-id="' + tarea.id + '">' +
      '<button class="marca-check" data-accion="estado" data-id="' + tarea.id + '" title="Marcar hecha"><i class="bi bi-check-lg"></i></button>' +
      '<div class="tarea-cuerpo">' +
        '<div class="tarea-titulo">' + escapar(tarea.titulo) + "</div>" +
        '<div class="tarea-meta">' + meta.join("") + "</div>" +
      "</div>" +
      '<div class="tarea-acciones">' +
        botonFoco +
        '<button class="icono-btn" data-accion="editar" data-id="' + tarea.id + '" title="Editar"><i class="bi bi-pencil"></i></button>' +
        '<button class="icono-btn peligro" data-accion="borrar" data-id="' + tarea.id + '" title="Borrar"><i class="bi bi-trash3"></i></button>' +
      "</div>" +
    "</div>";
}

function pintarTareas(contenedor, tareas, opciones) {
  if (!tareas || tareas.length === 0) {
    contenedor.innerHTML = '<div class="vacio"><i class="bi bi-clipboard-check"></i><p>Nada por aqui.</p></div>';
    return;
  }
  var html = "";
  for (var i = 0; i < tareas.length; i++) {
    html += htmlTarea(tareas[i], opciones);
  }
  contenedor.innerHTML = html;
}

function manejarAccionTarea(evento) {
  var boton = evento.target.closest("[data-accion]");
  if (!boton) { return; }
  var accion = boton.getAttribute("data-accion");
  var id = parseInt(boton.getAttribute("data-id"), 10);

  if (accion === "estado") {
    alternarEstado(id);
  } else if (accion === "editar") {
    abrirModal(id);
  } else if (accion === "borrar") {
    borrarTarea(id);
  } else if (accion === "foco") {
    irAFoco(id);
  }
}

function alternarEstado(id) {
  var tarea = buscarTarea(id);
  if (!tarea) { return; }
  var nuevo = tarea.estado === "hecha" ? "pendiente" : "hecha";
  api("/api/tareas/" + id + "/estado", "POST", { estado: nuevo }).then(function (actualizada) {
    avisar(nuevo === "hecha" ? "Hecha: " + actualizada.titulo : "Devuelta a pendientes");
    refrescarVista();
  }).catch(function (error) { avisar(error.message); });
}

function borrarTarea(id) {
  var tarea = buscarTarea(id);
  if (!tarea) { return; }
  if (!confirm('Borrar "' + tarea.titulo + '"?')) { return; }
  api("/api/tareas/" + id, "DELETE").then(function () {
    avisar("Tarea borrada");
    refrescarVista();
  }).catch(function (error) { avisar(error.message); });
}

function buscarTarea(id) {
  for (var i = 0; i < estado.tareas.length; i++) {
    if (estado.tareas[i].id === id) { return estado.tareas[i]; }
  }
  return null;
}

function fusionarTareas(lista) {
  for (var i = 0; i < lista.length; i++) {
    var tarea = lista[i];
    var encontrada = false;
    for (var j = 0; j < estado.tareas.length; j++) {
      if (estado.tareas[j].id === tarea.id) {
        estado.tareas[j] = tarea;
        encontrada = true;
        break;
      }
    }
    if (!encontrada) { estado.tareas.push(tarea); }
  }
}

// --------------------------------------------------------------- refresco

function refrescarVista() {
  cargarResumen();
  cargarRacha();
  if (estado.vista === "hoy") { cargarHoy(); }
  if (estado.vista === "tareas") { cargarTareas(); }
  if (estado.vista === "pomodoro") { cargarPomodoro(); }
  if (estado.vista === "calendario") { cargarCalendario(); }
  if (estado.vista === "memoria") { cargarMemoria(); }
  if (estado.vista === "notas") { cargarNotas(); }
  if (estado.vista === "metricas") { cargarMetricas(); }
}

function cargarResumen() {
  return api("/api/resumen").then(function (datos) {
    estado.resumen = datos;
    $("#kpi-hoy").textContent = datos.de_hoy;
    $("#kpi-hechas-hoy").textContent = datos.hechas_hoy;
    $("#kpi-min-hoy").textContent = datos.minutos_hoy;
    $("#kpi-vencidas").textContent = datos.vencidas;
    $("#lateral-racha").textContent = datos.racha;
    $("#lateral-horas").textContent = minutosATexto(datos.semana_minutos);
    $("#lateral-pendientes").textContent = datos.por_hacer;
    $("#badge-sin-fecha").textContent = datos.sin_fecha;
    $("#fecha-hoy").textContent = fechaLarga(datos.hoy);

    var hora = new Date().getHours();
    var saludo = "Hola, jefe";
    if (hora < 12) { saludo = "Buenos dias, jefe"; }
    else if (hora < 19) { saludo = "Buenas tardes, jefe"; }
    else { saludo = "Buenas noches, jefe"; }
    $("#saludo").textContent = saludo;
  });
}

// ------------------------------------------------------------------- hoy

function cargarHoy() {
  return Promise.all([
    api("/api/tareas?filtro=hoy"),
    api("/api/tareas?filtro=atrasadas")
  ]).then(function (resultados) {
    var deHoy = resultados[0].tareas;
    var atrasadas = resultados[1].tareas;

    var todas = [];
    for (var i = 0; i < atrasadas.length; i++) { todas.push(atrasadas[i]); }
    for (var j = 0; j < deHoy.length; j++) { todas.push(deHoy[j]); }
    estado.tareas = todas;

    pintarTareas($("#lista-hoy"), todas);
    $("#plan-sugerido").classList.add("oculto");

    return api("/api/tareas?filtro=pendientes").then(function (datos) {
      var sinFecha = [];
      for (var k = 0; k < datos.tareas.length; k++) {
        if (!datos.tareas[k].fecha) { sinFecha.push(datos.tareas[k]); }
      }
      fusionarTareas(datos.tareas);
      pintarTareas($("#lista-sin-fecha"), sinFecha, { ocultarFecha: true });
    });
  }).catch(function (error) { avisar(error.message); });
}

function armarPlan(minutosDisponibles) {
  api("/api/tareas?filtro=pendientes").then(function (datos) {
    var pendientes = datos.tareas;

    // orden: atrasadas primero, luego prioridad, luego estimado corto
    pendientes.sort(function (a, b) {
      var aAtrasada = a.fecha && a.fecha < hoyISO() ? 0 : 1;
      var bAtrasada = b.fecha && b.fecha < hoyISO() ? 0 : 1;
      if (aAtrasada !== bAtrasada) { return aAtrasada - bAtrasada; }
      if (a.prioridad !== b.prioridad) { return a.prioridad - b.prioridad; }
      return a.estimado_min - b.estimado_min;
    });

    var elegidas = [];
    var acumulado = 0;
    for (var i = 0; i < pendientes.length; i++) {
      if (acumulado + pendientes[i].estimado_min <= minutosDisponibles) {
        elegidas.push(pendientes[i]);
        acumulado += pendientes[i].estimado_min;
      }
      if (elegidas.length >= 7) { break; }
    }

    var caja = $("#plan-sugerido");
    caja.classList.remove("oculto");

    if (elegidas.length === 0) {
      caja.innerHTML = "<strong>No alcanza el tiempo</strong> para ninguna tarea pendiente con la estimacion actual. Recorta una tarea en partes mas pequenas.";
      return;
    }

    var html = "<strong>Plan para " + minutosATexto(minutosDisponibles) + "</strong><ul>";
    for (var j = 0; j < elegidas.length; j++) {
      var t = elegidas[j];
      var marca = t.fecha && t.fecha < hoyISO() ? " (atrasada)" : "";
      html += "<li>" + escapar(t.titulo) + marca + ' <span style="color:#8b97ad">- ' +
              minutosATexto(t.estimado_min) + "</span></li>";
    }
    html += "</ul>";
    html += '<div class="total">Total ' + minutosATexto(acumulado) + " de " +
            minutosATexto(minutosDisponibles) + " disponibles. Empieza por la primera y dale un bloque de 25.</div>";
    caja.innerHTML = html;

    var modal = bootstrap.Modal.getInstance($("#modalPlan"));
    if (modal) { modal.hide(); }
  }).catch(function (error) { avisar(error.message); });
}

// ---------------------------------------------------------------- tareas

function cargarTareas() {
  var ruta = "/api/tareas?filtro=" + estado.filtro;
  if (estado.busqueda) {
    ruta += "&q=" + encodeURIComponent(estado.busqueda);
  }
  return api(ruta).then(function (datos) {
    estado.tareas = datos.tareas;
    pintarTareas($("#lista-tareas"), datos.tareas);
    $("#vacio-tareas").classList.toggle("oculto", datos.tareas.length > 0);
  }).catch(function (error) { avisar(error.message); });
}

// -------------------------------------------------------------- pomodoro

var pomo = {
  total: 25 * 60,
  restante: 25 * 60,
  corriendo: false,
  intervalo: null,
  tipo: "foco",
  tareaId: null,
  transcurridos: 0
};

function cargarPomodoro() {
  var seleccionPrevia = pomo.tareaId;

  return api("/api/tareas?filtro=pendientes").then(function (datos) {
    var select = $("#pomo-tarea");
    var html = '<option value="">Sin tarea (tiempo suelto)</option>';
    for (var i = 0; i < datos.tareas.length; i++) {
      var t = datos.tareas[i];
      html += '<option value="' + t.id + '">' + escapar(t.titulo) + " (" + minutosATexto(t.estimado_min) + ")</option>";
    }
    select.innerHTML = html;
    if (seleccionPrevia) { select.value = String(seleccionPrevia); }
    pomo.tareaId = select.value ? parseInt(select.value, 10) : null;

    return api("/api/sesiones?desde=" + hoyISO() + "&hasta=" + hoyISO());
  }).then(function (datos) {
    var caja = $("#pomo-registro");
    if (datos.sesiones.length === 0) {
      caja.innerHTML = '<div class="vacio"><i class="bi bi-stopwatch"></i><p>Todavia no hay bloques hoy.</p></div>';
      return;
    }
    var html = "";
    var total = 0;
    for (var i = 0; i < datos.sesiones.length; i++) {
      var s = datos.sesiones[i];
      var titulo = s.tarea_titulo ? s.tarea_titulo : "Sin tarea";
      var etiqueta = s.tipo === "descanso" ? "descanso" : "";
      html += '<div class="pomo-fila">' +
                '<span class="hora">' + s.inicio.substring(11, 16) + "</span>" +
                '<span class="titulo">' + escapar(titulo) + (etiqueta ? ' <span class="etiqueta">' + etiqueta + "</span>" : "") + "</span>" +
                '<span class="min">' + s.minutos + " min</span>" +
              "</div>";
      if (s.tipo === "foco") { total += s.minutos; }
    }
    html += '<div class="total" style="margin-top:10px;font-size:12px;color:#8b97ad">Total de foco hoy: ' + minutosATexto(total) + "</div>";
    caja.innerHTML = html;
  }).catch(function (error) { avisar(error.message); });
}

function pintarReloj() {
  var minutos = Math.floor(pomo.restante / 60);
  var segundos = pomo.restante % 60;
  $("#pomo-tiempo").textContent = dosDigitos(minutos) + ":" + dosDigitos(segundos);

  var circunferencia = 2 * Math.PI * 98;
  var avance = 1 - (pomo.restante / pomo.total);
  var circulo = $("#aro-progreso");
  circulo.style.strokeDashoffset = String(circunferencia * (1 - avance));
  circulo.classList.toggle("descanso", pomo.tipo === "descanso");
}

function iniciarPomodoro() {
  if (pomo.corriendo) {
    detenerPomodoro();
    return;
  }
  if (pomo.restante <= 0) {
    pomo.restante = pomo.total;
  }
  pomo.corriendo = true;
  $("#pomo-iniciar").innerHTML = '<i class="bi bi-pause-fill"></i> Pausar';
  $("#pomo-estado").textContent = pomo.tipo === "descanso" ? "descansando" : "en foco";

  var seleccion = $("#pomo-tarea").value;
  pomo.tareaId = seleccion ? parseInt(seleccion, 10) : null;

  pomo.intervalo = setInterval(function () {
    pomo.restante = pomo.restante - 1;
    pomo.transcurridos = pomo.transcurridos + 1;
    pintarReloj();
    if (pomo.restante <= 0) {
      terminarPomodoro(true);
    }
  }, 1000);
}

function detenerPomodoro() {
  pomo.corriendo = false;
  if (pomo.intervalo) { clearInterval(pomo.intervalo); pomo.intervalo = null; }
  $("#pomo-iniciar").innerHTML = '<i class="bi bi-play-fill"></i> Continuar';
  $("#pomo-estado").textContent = "en pausa";
}

function reiniciarPomodoro() {
  detenerPomodoro();
  pomo.restante = pomo.total;
  pomo.transcurridos = 0;
  $("#pomo-iniciar").innerHTML = '<i class="bi bi-play-fill"></i> Iniciar';
  $("#pomo-estado").textContent = "listo para empezar";
  pintarReloj();
}

function sonar() {
  try {
    var contexto = new (window.AudioContext || window.webkitAudioContext)();
    var oscilador = contexto.createOscillator();
    var ganancia = contexto.createGain();
    oscilador.connect(ganancia);
    ganancia.connect(contexto.destination);
    oscilador.frequency.value = 880;
    oscilador.type = "sine";
    ganancia.gain.setValueAtTime(0.16, contexto.currentTime);
    ganancia.gain.exponentialRampToValueAtTime(0.001, contexto.currentTime + 0.5);
    oscilador.start();
    oscilador.stop(contexto.currentTime + 0.5);
  } catch (e) {}
}

function terminarPomodoro(completado) {
  var minutosHechos = Math.round(pomo.transcurridos / 60);
  detenerPomodoro();

  if (minutosHechos < 1) {
    avisar("Menos de un minuto, no se guarda el bloque");
    reiniciarPomodoro();
    return;
  }

  var datos = {
    tarea_id: pomo.tareaId,
    minutos: minutosHechos,
    tipo: pomo.tipo,
    completa: completado === true
  };

  api("/api/sesiones", "POST", datos).then(function () {
    if (completado) { sonar(); }
    avisar("Guardado: " + minutosHechos + " min de " + pomo.tipo);
    reiniciarPomodoro();
    cargarResumen();
    if (pomo.tipo === "foco") { cargarPomodoro(); }
  }).catch(function (error) { avisar(error.message); });
}

function irAFoco(id) {
  cambiarVista("pomodoro");
  setTimeout(function () {
    var select = $("#pomo-tarea");
    select.value = String(id);
    pomo.tareaId = id;
    avisar("Tarea cargada en el pomodoro");
  }, 250);
}

// ------------------------------------------------------------ calendario

function cargarCalendario() {
  if (!estado.calAnio) {
    var hoy = new Date();
    estado.calAnio = hoy.getFullYear();
    estado.calMes = hoy.getMonth();
    estado.calSeleccion = hoyISO();
  }

  var primerDia = new Date(estado.calAnio, estado.calMes, 1);
  var ultimoDia = new Date(estado.calAnio, estado.calMes + 1, 0);
  var desde = estado.calAnio + "-" + dosDigitos(estado.calMes + 1) + "-01";
  var hasta = estado.calAnio + "-" + dosDigitos(estado.calMes + 1) + "-" + dosDigitos(ultimoDia.getDate());

  $("#cal-titulo").textContent = MESES[estado.calMes] + " " + estado.calAnio;

  return api("/api/tareas?filtro=todas&desde=" + desde + "&hasta=" + hasta).then(function (datos) {
    var porDia = {};
    for (var i = 0; i < datos.tareas.length; i++) {
      var t = datos.tareas[i];
      if (!t.fecha) { continue; }
      if (!porDia[t.fecha]) { porDia[t.fecha] = []; }
      porDia[t.fecha].push(t);
    }

    var desplazamiento = (primerDia.getDay() + 6) % 7;
    var inicioCuadricula = new Date(estado.calAnio, estado.calMes, 1 - desplazamiento);
    var celdas = [];
    var hoy = hoyISO();

    for (var c = 0; c < 42; c++) {
      var fecha = new Date(inicioCuadricula.getFullYear(), inicioCuadricula.getMonth(), inicioCuadricula.getDate() + c);
      var iso = fecha.getFullYear() + "-" + dosDigitos(fecha.getMonth() + 1) + "-" + dosDigitos(fecha.getDate());
      var clases = "cal-celda";
      if (fecha.getMonth() !== estado.calMes) { clases += " fuera"; }
      if (iso === hoy) { clases += " hoy"; }
      if (iso === estado.calSeleccion) { clases += " sel"; }

      var tareasDia = porDia[iso] || [];
      var contenido = '<div class="cal-num">' + fecha.getDate() + "</div>";
      var mostradas = 0;
      for (var k = 0; k < tareasDia.length && mostradas < 2; k++) {
        var claseTarea = tareasDia[k].estado === "hecha" ? "cal-tarea hecha" : "cal-tarea";
        contenido += '<div class="' + claseTarea + '" title="' + escapar(tareasDia[k].titulo) + '">' + escapar(tareasDia[k].titulo) + "</div>";
        mostradas++;
      }
      if (tareasDia.length > 2) {
        contenido += '<div class="cal-mas">+' + (tareasDia.length - 2) + " mas</div>";
      }

      celdas.push('<div class="' + clases + '" data-fecha="' + iso + '">' + contenido + "</div>");
      if (fecha.getMonth() > estado.calMes && c > 34) { break; }
    }

    $("#cal-grid").innerHTML = celdas.join("");
    pintarDiaSeleccionado(porDia);
  }).catch(function (error) { avisar(error.message); });
}

function pintarDiaSeleccionado(porDia) {
  var iso = estado.calSeleccion;
  $("#dia-titulo").textContent = fechaLarga(iso);
  $("#btn-nueva-dia-sel").classList.remove("oculto");

  var lista = (porDia && porDia[iso]) ? porDia[iso] : [];
  if (lista.length === 0) {
    $("#lista-dia").innerHTML = '<div class="vacio"><i class="bi bi-calendar-plus"></i><p>Dia libre. Puedes agendar algo.</p></div>';
    return;
  }
  pintarTareas($("#lista-dia"), lista, { ocultarFecha: true });
}

function seleccionarDia(iso) {
  estado.calSeleccion = iso;
  api("/api/tareas?filtro=todas&desde=" + iso + "&hasta=" + iso).then(function (datos) {
    fusionarTareas(datos.tareas);
    var mapa = {};
    mapa[iso] = datos.tareas;
    pintarDiaSeleccionado(mapa);
    cargarCalendario();
  });
}

// --------------------------------------------------------------- memoria

function cargarMemoria() {
  return Promise.all([
    api("/api/tareas?filtro=hechas"),
    api("/api/tareas?filtro=pendientes"),
    api("/api/sesiones")
  ]).then(function (resultados) {
    var hechas = resultados[0].tareas;
    var pendientes = resultados[1].tareas;
    var sesiones = resultados[2].sesiones;

    $("#badge-hechas").textContent = hechas.length;
    $("#badge-pendientes").textContent = pendientes.length;

    fusionarTareas(hechas);
    fusionarTareas(pendientes);
    pintarTareas($("#lista-hechas"), hechas);
    pintarTareas($("#lista-pendientes"), pendientes);

    var caja = $("#bitacora");
    if (sesiones.length === 0) {
      caja.innerHTML = '<div class="vacio"><i class="bi bi-journal"></i><p>Sin bloques registrados todavia.</p></div>';
      return;
    }

    var html = "";
    var diaActual = "";
    for (var i = 0; i < sesiones.length; i++) {
      var s = sesiones[i];
      var dia = s.inicio.substring(0, 10);
      if (dia !== diaActual) {
        diaActual = dia;
        html += '<div class="bitacora-dia">' + fechaLarga(dia) + "</div>";
      }
      var titulo = s.tarea_titulo ? s.tarea_titulo : "Sin tarea";
      var sufijo = s.tipo === "descanso" ? " (descanso)" : "";
      html += '<div class="bitacora-fila">' +
                '<span class="h">' + s.inicio.substring(11, 16) + "</span>" +
                '<span class="t">' + escapar(titulo) + sufijo + "</span>" +
                '<span class="m">' + s.minutos + " min</span>" +
              "</div>";
    }
    caja.innerHTML = html;
  }).catch(function (error) { avisar(error.message); });
}

// ------------------------------------------------------------ seguimiento

function cargarMetricas() {
  return api("/api/metricas?periodo=" + estado.periodo).then(function (datos) {
    $("#met-horas").textContent = datos.horas_foco + " h";
    $("#met-bloques").textContent = datos.bloques;
    $("#met-cumplimiento").textContent = datos.cumplimiento + " %";
    $("#met-racha").textContent = datos.racha;
    $("#met-rango").textContent = fechaLegible(datos.desde) + " - " + fechaLegible(datos.hasta);

    pintarGraficoDias(datos);
    pintarAreas(datos);
    pintarDestacadas(datos);
    pintarLectura(datos);
  }).catch(function (error) { avisar(error.message); });
}

function pintarGraficoDias(datos) {
  var mapa = {};
  for (var i = 0; i < datos.por_dia.length; i++) {
    mapa[datos.por_dia[i].dia] = datos.por_dia[i].minutos;
  }

  var dias = [];
  var cursor = new Date(parseInt(datos.desde.substring(0, 4), 10),
                        parseInt(datos.desde.substring(5, 7), 10) - 1,
                        parseInt(datos.desde.substring(8, 10), 10));
  var fin = new Date(parseInt(datos.hasta.substring(0, 4), 10),
                     parseInt(datos.hasta.substring(5, 7), 10) - 1,
                     parseInt(datos.hasta.substring(8, 10), 10));

  while (cursor <= fin && dias.length < 40) {
    var iso = cursor.getFullYear() + "-" + dosDigitos(cursor.getMonth() + 1) + "-" + dosDigitos(cursor.getDate());
    dias.push({ iso: iso, minutos: mapa[iso] || 0, dia: cursor.getDate() });
    cursor = new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate() + 1);
  }

  var maximo = 1;
  for (var j = 0; j < dias.length; j++) {
    if (dias[j].minutos > maximo) { maximo = dias[j].minutos; }
  }

  var html = "";
  for (var k = 0; k < dias.length; k++) {
    var alto = dias[k].minutos > 0 ? Math.max(4, Math.round(dias[k].minutos * 100 / maximo)) : 2;
    var clase = dias[k].minutos > 0 ? "barra" : "barra cero";
    html += '<div class="barra-col">' +
              '<div class="barra-valor">' + (dias[k].minutos > 0 ? dias[k].minutos : "") + "</div>" +
              '<div class="' + clase + '" style="height:' + alto + '%"></div>' +
              '<div class="barra-dia">' + dias[k].dia + "</div>" +
            "</div>";
  }
  $("#grafico-dias").innerHTML = html;
}

function pintarAreas(datos) {
  if (datos.por_area.length === 0) {
    $("#tabla-areas").innerHTML = '<div class="vacio"><i class="bi bi-pie-chart"></i><p>Sin datos en este periodo.</p></div>';
    return;
  }
  var maximo = datos.por_area[0].minutos || 1;
  var html = "";
  for (var i = 0; i < datos.por_area.length; i++) {
    var fila = datos.por_area[i];
    var ancho = Math.round(fila.minutos * 100 / maximo);
    html += '<div class="fila-area">' +
              '<div class="texto"><span>' + escapar(fila.area) + "</span><span>" + minutosATexto(fila.minutos) + "</span></div>" +
              '<div class="pista"><div style="width:' + ancho + '%"></div></div>' +
            "</div>";
  }
  $("#tabla-areas").innerHTML = html;
}

function pintarDestacadas(datos) {
  if (datos.destacadas.length === 0) {
    $("#tabla-destacadas").innerHTML = '<div class="vacio"><i class="bi bi-hourglass"></i><p>Sin bloqueos registrados.</p></div>';
    return;
  }
  var maximo = datos.destacadas[0].minutos || 1;
  var html = "";
  for (var i = 0; i < datos.destacadas.length; i++) {
    var fila = datos.destacadas[i];
    var ancho = Math.round(fila.minutos * 100 / maximo);
    html += '<div class="fila-area">' +
              '<div class="texto"><span>' + escapar(fila.titulo) + "</span><span>" + minutosATexto(fila.minutos) + "</span></div>" +
              '<div class="pista"><div class="verde" style="width:' + ancho + '%"></div></div>' +
            "</div>";
  }
  $("#tabla-destacadas").innerHTML = html;
}

function pintarLectura(datos) {
  var texto = "";
  var nombrePeriodo = datos.periodo === "mes" ? "este mes" : "esta semana";

  if (datos.minutos_foco === 0) {
    texto = "<strong>Sin foco registrado " + nombrePeriodo + ".</strong> Arranca con un bloque de 25 minutos en la tarea mas urgente. Lo importante ahora es la constancia, no el volumen.";
  } else {
    var diasPeriodo = datos.periodo === "mes" ? 30 : 7;
    var promedio = Math.round(datos.minutos_foco / diasPeriodo);
    texto = "<strong>" + minutosATexto(datos.minutos_foco) + " de foco " + nombrePeriodo +
            "</strong> en " + datos.bloques + " bloques (promedio " + minutosATexto(datos.promedio_bloque) + " por bloque). ";
    texto += "Eso da " + minutosATexto(promedio) + " al dia. ";

    if (datos.por_area.length > 0) {
      texto += "El area que mas te ocupo fue <strong>" + escapar(datos.por_area[0].area) + "</strong>. ";
    }

    if (datos.programadas > 0) {
      texto += "Cumpliste " + datos.completadas + " de " + datos.programadas + " tareas agendadas (" + datos.cumplimiento + " %). ";
      if (datos.cumplimiento < 50) {
        texto += "Estas agendando mas de lo que el dia aguanta: baja la carga a 3 tareas diarias. ";
      } else if (datos.cumplimiento >= 80) {
        texto += "Buen cumplimiento, podes subir un poco la carga. ";
      }
    }

    if (datos.vencidas > 0) {
      texto += "<strong>Tenes " + datos.vencidas + " tareas atrasadas.</strong> Reagendalas o borralas: lo vencido sin fecha definida solo genera ruido. ";
    }

    if (datos.racha >= 3) {
      texto += "Racha de " + datos.racha + " dias: no la cortes hoy.";
    }
  }

  $("#resumen-ia").innerHTML = texto + '<div class="total" style="margin-top:10px;font-size:11.5px;color:#8b97ad">Analisis local sobre tus propios datos. La version con IA real llega en la etapa final.</div>';
}

// ----------------------------------------------------------------- modal

var modalTarea = null;

function abrirModal(id, fechaPorDefecto) {
  if (!modalTarea) { modalTarea = new bootstrap.Modal($("#modalTarea")); }

  $("#err-titulo").classList.add("oculto");
  $("#estimador-resultado").classList.add("oculto");
  $("#estimador-resultado").innerHTML = "";

  if (id) {
    var tarea = buscarTarea(id);
    if (!tarea) {
      api("/api/tareas/" + id).then(function (datos) { llenarModal(datos); modalTarea.show(); });
      return;
    }
    $("#modal-titulo").textContent = "Editar tarea";
    $("#f-id").value = tarea.id;
    $("#f-titulo").value = tarea.titulo;
    $("#f-area").value = tarea.area;
    $("#f-prioridad").value = String(tarea.prioridad);
    $("#f-fecha").value = tarea.fecha || "";
    $("#f-hora").value = tarea.hora || "";
    $("#f-notas").value = tarea.notas || "";
    $("#f-estimado").value = String(tarea.estimado_min);
  } else {
    $("#modal-titulo").textContent = "Nueva tarea";
    $("#f-id").value = "";
    $("#f-titulo").value = "";
    $("#f-area").value = "";
    $("#f-prioridad").value = "2";
    $("#f-fecha").value = fechaPorDefecto || "";
    $("#f-hora").value = "";
    $("#f-notas").value = "";
    $("#f-estimado").value = "30";
  }
  modalTarea.show();
  setTimeout(function () { $("#f-titulo").focus(); }, 350);
}

function llenarModal(tarea) {
  $("#modal-titulo").textContent = "Editar tarea";
  $("#f-id").value = tarea.id;
  $("#f-titulo").value = tarea.titulo;
  $("#f-area").value = tarea.area;
  $("#f-prioridad").value = String(tarea.prioridad);
  $("#f-fecha").value = tarea.fecha || "";
  $("#f-hora").value = tarea.hora || "";
  $("#f-notas").value = tarea.notas || "";
  $("#f-estimado").value = String(tarea.estimado_min);
}

function guardarTarea() {
  var titulo = $("#f-titulo").value.trim();
  if (!titulo) {
    $("#err-titulo").classList.remove("oculto");
    $("#f-titulo").focus();
    return;
  }
  $("#err-titulo").classList.add("oculto");

  var datos = {
    titulo: titulo,
    area: $("#f-area").value.trim() || "General",
    prioridad: parseInt($("#f-prioridad").value, 10),
    fecha: $("#f-fecha").value,
    hora: $("#f-hora").value,
    notas: $("#f-notas").value,
    estimado_min: parseInt($("#f-estimado").value, 10) || 30
  };

  var id = $("#f-id").value;

  if (id) {
    api("/api/tareas/" + id, "PUT", datos).then(function () {
      avisar("Tarea actualizada");
      modalTarea.hide();
      refrescarVista();
    }).catch(function (error) { avisar(error.message); });
  } else {
    api("/api/tareas", "POST", datos).then(function (resultado) {
      if (resultado && resultado.duplicado) {
        modalTarea.hide();
        avisar("Ya existe: #" + resultado.tarea.id + " " + resultado.tarea.titulo);
        return;
      }
      avisar("Tarea creada");
      modalTarea.hide();
      refrescarVista();
    }).catch(function (error) { avisar(error.message); });
  }
}

function estimarDesdeModal() {
  var datos = {
    titulo: $("#f-titulo").value,
    notas: $("#f-notas").value,
    area: $("#f-area").value
  };
  if (!datos.titulo.trim()) {
    $("#err-titulo").classList.remove("oculto");
    return;
  }

  api("/api/estimar", "POST", datos).then(function (resultado) {
    $("#f-estimado").value = String(resultado.minutos);

    var html = "<strong>Estimado: " + minutosATexto(resultado.minutos) + "</strong> (" +
               resultado.bloques + " bloques de 25 min).<br>" + escapar(resultado.razon);

    if (resultado.subtareas.length > 0) {
      html += "<ul>";
      for (var i = 0; i < resultado.subtareas.length; i++) {
        html += "<li>" + escapar(resultado.subtareas[i].titulo) + " - " +
                resultado.subtareas[i].minutos + " min</li>";
      }
      html += "</ul>";
    }

    var caja = $("#estimador-resultado");
    caja.innerHTML = html;
    caja.classList.remove("oculto");
  }).catch(function (error) { avisar(error.message); });
}

// ---------------------------------------------------------------- racha

function letraDia(iso) {
  var partes = iso.split("-");
  var dia = new Date(parseInt(partes[0], 10), parseInt(partes[1], 10) - 1,
                     parseInt(partes[2], 10));
  return DIAS_CORTOS[dia.getDay()].substring(0, 1).toUpperCase();
}

function cargarRacha() {
  return api("/api/racha").then(function (datos) {
    if (!$("#racha-numero")) { return; }
    $("#racha-numero").textContent = datos.actual;
    $("#racha-insignia").textContent = datos.insignia;
    $("#racha-mejor").textContent = "Mejor: " + datos.mejor;
    $("#racha-meta").textContent = datos.activos_semana + "/" + datos.meta_semana +
                                   " esta semana";
    $("#racha-mensaje").textContent = datos.mensaje;

    var html = "";
    for (var i = 0; i < datos.dias.length; i++) {
      var dia = datos.dias[i];
      var clases = "racha-dia";
      if (dia.activo) { clases += " activo"; }
      if (i === datos.dias.length - 1) { clases += " hoy"; }
      var detalle = fechaLarga(dia.fecha);
      if (dia.activo) {
        detalle += " - " + dia.minutos + " min, " + dia.hechas + " hechas";
      } else {
        detalle += " - sin actividad";
      }
      html += '<div class="' + clases + '" title="' + escapar(detalle) + '">' +
              letraDia(dia.fecha) + "</div>";
    }
    $("#racha-dias").innerHTML = html;
  }).catch(function () {});
}

// ------------------------------------------------------------- nube UTSA

var modalNube = null;
var estadoNube = { configurado: false };

function cargarNube() {
  return api("/api/moodle").then(function (datos) {
    estadoNube = datos;
    var caja = document.querySelector(".barra-nube");
    var texto = $("#nube-texto");
    if (!caja) { return; }
    caja.classList.remove("error", "activa");

    if (!datos.configurado) {
      texto.textContent = "Nube UTSA: sin configurar. Pon tus credenciales y las tareas entran solas.";
      return;
    }

    var ultimo = datos.ultimo || {};
    if (ultimo.ok === false) {
      caja.classList.add("error");
      texto.textContent = "Nube UTSA: " + (ultimo.error || "fallo la ultima sincronizacion");
      return;
    }

    if (datos.ultima) {
      caja.classList.add("activa");
      texto.textContent = "Nube UTSA (" + (datos.campus_nombre || "") + "): sincronizada el " +
        fechaLegible(datos.ultima.substring(0, 10)) + " a las " + datos.ultima.substring(11, 16) +
        " - " + (ultimo.nuevas || 0) + " nuevas de " + (ultimo.revisadas || 0) + " actividades";
      return;
    }

    texto.textContent = "Nube UTSA (" + (datos.campus_nombre || "") + "): conectada, sin sincronizar todavia.";
  }).catch(function () {});
}

function abrirModalNube() {
  if (!modalNube) { modalNube = new bootstrap.Modal($("#modalNube")); }
  $("#err-nube").classList.add("oculto");
  if (estadoNube.configurado) {
    $("#n-campus").value = estadoNube.campus || "utsan";
    $("#n-usuario").value = estadoNube.usuario || "";
  }
  $("#n-clave").value = "";
  modalNube.show();
}

function guardarNube() {
  var usuario = $("#n-usuario").value.trim();
  var clave = $("#n-clave").value.trim();
  var error = $("#err-nube");

  if (!usuario || !clave) {
    error.textContent = "Necesito la matricula y la contrasena.";
    error.classList.remove("oculto");
    return;
  }
  error.classList.add("oculto");

  var boton = $("#btn-guardar-nube");
  boton.disabled = true;
  boton.textContent = "Conectando...";

  api("/api/moodle/config", "POST", {
    campus: $("#n-campus").value,
    usuario: usuario,
    clave: clave
  }).then(function (resultado) {
    boton.disabled = false;
    boton.textContent = "Guardar y sincronizar";
    if (!resultado.ok) {
      error.textContent = resultado.error || "No se pudo conectar con la nube.";
      error.classList.remove("oculto");
      return;
    }
    modalNube.hide();
    avisar("Conectado: " + resultado.nuevas + " tareas nuevas de la nube");
    cargarNube();
    refrescarVista();
  }).catch(function (e) {
    boton.disabled = false;
    boton.textContent = "Guardar y sincronizar";
    error.textContent = e.message;
    error.classList.remove("oculto");
  });
}

var ultimaSyncVista = null;

function notificar(titulo, cuerpo) {
  try {
    if (window.Notification && Notification.permission === "granted") {
      new Notification(titulo, { body: cuerpo });
    }
  } catch (e) {}
}

function activarAvisos() {
  if (!window.Notification) {
    avisar("Este navegador no soporta avisos");
    return;
  }
  Notification.requestPermission().then(function (permiso) {
    if (permiso === "granted") {
      avisar("Avisos activados");
      notificar("Habitos", "Te aviso cuando entren tareas nuevas de la nube");
    } else {
      avisar("El navegador bloqueo los avisos");
    }
  });
}

function vigilarNube() {
  setInterval(function () {
    api("/api/moodle").then(function (datos) {
      if (!datos.configurado) { return; }
      var momento = datos.ultima || "";
      var ultimo = datos.ultimo || {};
      if (ultimaSyncVista === null) {
        ultimaSyncVista = momento;
        return;
      }
      if (momento === ultimaSyncVista) { return; }
      ultimaSyncVista = momento;
      cargarNube();
      if (ultimo.ok && ultimo.nuevas > 0) {
        notificar("Tareas nuevas de la universidad",
                  ultimo.nuevas + " actividad(es) agregadas a tus pendientes");
        avisar(ultimo.nuevas + " tareas nuevas de la nube");
        refrescarVista();
      }
    }).catch(function () {});
  }, 180000);
}

function sincronizarNube() {
  var boton = $("#btn-nube-sync");
  boton.disabled = true;
  $("#nube-texto").textContent = "Sincronizando con la nube...";
  api("/api/moodle/sync", "POST", {}).then(function (resultado) {
    boton.disabled = false;
    if (!resultado.ok) {
      avisar(resultado.error || "No se pudo sincronizar");
      cargarNube();
      return;
    }
    avisar("Nube: " + resultado.nuevas + " nuevas, " + resultado.actualizadas + " actualizadas");
    cargarNube();
    refrescarVista();
  }).catch(function (e) {
    boton.disabled = false;
    avisar(e.message);
    cargarNube();
  });
}

// ---------------------------------------------------------------- apuntes

estado.apuntes = [];

function cargarNotas() {
  var ruta = "/api/apuntes";
  var buscador = $("#buscador-notas");
  if (buscador && buscador.value.trim()) {
    ruta += "?q=" + encodeURIComponent(buscador.value.trim());
  }
  return api(ruta).then(function (datos) {
    estado.apuntes = datos.apuntes;
    pintarApuntes(datos.apuntes);
    llenarSelectorNota();
  }).catch(function (error) { avisar(error.message); });
}

function llenarSelectorNota() {
  var select = $("#ap-tarea");
  if (!select) { return; }
  var elegido = select.value;
  api("/api/tareas?filtro=pendientes").then(function (datos) {
    var html = '<option value="">Sin tarea ligada</option>';
    for (var i = 0; i < datos.tareas.length; i++) {
      var tarea = datos.tareas[i];
      html += '<option value="' + tarea.id + '">#' + tarea.id + " " +
              escapar(tarea.titulo).substring(0, 55) + "</option>";
    }
    select.innerHTML = html;
    if (elegido) { select.value = elegido; }
  }).catch(function () {});
}

function pintarApuntes(apuntes) {
  var caja = $("#lista-apuntes");
  if (!apuntes || apuntes.length === 0) {
    caja.innerHTML = '<div class="vacio"><i class="bi bi-journal-text"></i><p>Sin notas todavia.</p></div>';
    return;
  }
  var html = "";
  for (var i = 0; i < apuntes.length; i++) {
    var apunte = apuntes[i];
    var cuerpo = escapar(apunte.cuerpo).replace(/\n/g, "<br>");
    var ligada = apunte.tarea_id ? ' <span class="etiqueta">tarea #' + apunte.tarea_id + "</span>" : "";
    html += '<div class="apunte" data-id="' + apunte.id + '">' +
              '<div class="apunte-cabecera">' +
                "<strong>" + escapar(apunte.titulo) + "</strong>" + ligada +
                '<span class="apunte-fecha">' +
                  fechaLegible((apunte.creada || "").substring(0, 10)) + "</span>" +
              "</div>" +
              '<div class="apunte-cuerpo">' + cuerpo + "</div>" +
              '<div class="apunte-acciones">' +
                '<button class="icono-btn" data-apunte="editar" data-id="' + apunte.id + '">' +
                  '<i class="bi bi-pencil"></i></button>' +
                '<button class="icono-btn peligro" data-apunte="borrar" data-id="' + apunte.id + '">' +
                  '<i class="bi bi-trash3"></i></button>' +
              "</div>" +
            "</div>";
  }
  caja.innerHTML = html;
}

function guardarApunte() {
  var cuerpo = $("#ap-cuerpo").value.trim();
  var titulo = $("#ap-titulo").value.trim();
  if (!cuerpo && !titulo) {
    avisar("Escribe algo primero");
    return;
  }
  var tareaId = $("#ap-tarea").value;
  api("/api/apuntes", "POST", {
    titulo: titulo,
    cuerpo: cuerpo,
    tarea_id: tareaId ? parseInt(tareaId, 10) : null
  }).then(function () {
    $("#ap-titulo").value = "";
    $("#ap-cuerpo").value = "";
    avisar("Nota guardada");
    cargarNotas();
  }).catch(function (error) { avisar(error.message); });
}

function accionApunte(evento) {
  var boton = evento.target.closest("[data-apunte]");
  if (!boton) { return; }
  var accion = boton.getAttribute("data-apunte");
  var identificador = parseInt(boton.getAttribute("data-id"), 10);
  var apunte = null;
  for (var i = 0; i < estado.apuntes.length; i++) {
    if (estado.apuntes[i].id === identificador) { apunte = estado.apuntes[i]; }
  }
  if (!apunte) { return; }

  if (accion === "borrar") {
    if (!confirm('Borrar la nota "' + apunte.titulo + '"?')) { return; }
    api("/api/apuntes/" + identificador, "DELETE").then(function () {
      avisar("Nota borrada");
      cargarNotas();
    }).catch(function (error) { avisar(error.message); });
    return;
  }

  if (accion === "editar") {
    var nuevo = prompt("Editar nota:", apunte.cuerpo);
    if (nuevo === null) { return; }
    api("/api/apuntes/" + identificador, "PUT", { cuerpo: nuevo }).then(function () {
      avisar("Nota actualizada");
      cargarNotas();
    }).catch(function (error) { avisar(error.message); });
  }
}

// --------------------------------------------------------------- telegram

var modalTelegram = null;

function cargarTelegram() {
  return api("/api/telegram").then(function (datos) {
    var caja = $("#tg-estado");
    if (!caja) { return; }
    var html = "";
    if (!datos.configurado) {
      html = "<strong>Sin bot configurado.</strong> Sigue los tres pasos de abajo.";
    } else if (!datos.chat_id) {
      html = "<strong>Bot @" + escapar(datos.bot || "") + " registrado.</strong> " +
             "Falta mandarle /start desde tu Telegram.";
    } else {
      html = "<strong>Conectado</strong> con @" + escapar(datos.bot || "") +
             " - chat " + datos.chat_id + ".";
    }
    caja.innerHTML = html;
  }).catch(function () {});
}

function abrirModalTelegram() {
  if (!modalTelegram) { modalTelegram = new bootstrap.Modal($("#modalTelegram")); }
  $("#err-tg").classList.add("oculto");
  $("#tg-token").value = "";
  cargarTelegram();
  cargarRecordatorios();
  modalTelegram.show();
}

function guardarTokenTelegram() {
  var token = $("#tg-token").value.trim();
  var error = $("#err-tg");
  if (!token) {
    error.textContent = "Pega el token que te dio BotFather.";
    error.classList.remove("oculto");
    return;
  }
  error.classList.add("oculto");

  var boton = $("#btn-tg-guardar");
  boton.disabled = true;
  boton.textContent = "Probando...";

  api("/api/telegram/config", "POST", { token: token }).then(function (datos) {
    boton.disabled = false;
    boton.textContent = "Guardar token";
    $("#tg-token").value = "";
    cargarTelegram();
    avisar("Bot @" + (datos.bot || "") + " conectado. Mandale /start");
  }).catch(function (e) {
    boton.disabled = false;
    boton.textContent = "Guardar token";
    error.textContent = e.message;
    error.classList.remove("oculto");
  });
}

function desvincularTelegram() {
  api("/api/telegram/desvincular", "POST", {}).then(function () {
    avisar("Chat desvinculado");
    cargarTelegram();
  }).catch(function (error) { avisar(error.message); });
}

function cargarRecordatorios() {
  return api("/api/recordatorios").then(function (datos) {
    if (!$("#rec-activo")) { return; }
    $("#rec-activo").checked = !!datos.activo;
    $("#rec-minutos").value = datos.minutos;
    $("#rec-desde").value = datos.desde;
    $("#rec-hasta").value = datos.hasta;
    var aviso = $("#rec-aviso");
    if (!datos.telegram) {
      aviso.textContent = "Primero vincula tu chat con /start, si no no tengo a donde avisarte.";
    } else if (datos.ultimo) {
      aviso.textContent = "Ultimo aviso enviado: " + datos.ultimo +
                          ". Te aviso cada " + datos.minutos + " minutos de " +
                          datos.desde + ":00 a " + datos.hasta + ":00.";
    }
  }).catch(function () {});
}

function guardarRecordatorios() {
  var datos = {
    activo: $("#rec-activo").checked,
    minutos: parseInt($("#rec-minutos").value, 10) || 90,
    desde: parseInt($("#rec-desde").value, 10) || 0,
    hasta: parseInt($("#rec-hasta").value, 10) || 24
  };
  api("/api/recordatorios", "POST", datos).then(function (config) {
    avisar("Recordatorios: cada " + config.minutos + " min de " +
           config.desde + ":00 a " + config.hasta + ":00");
    cargarRecordatorios();
  }).catch(function (error) { avisar(error.message); });
}

// ---------------------------------------------------------------- google

var modalGoogle = null;

function cargarGoogle() {
  return api("/api/google").then(function (datos) {
    var caja = $("#g-estado");
    if (!caja) { return; }
    var html = "";
    if (!datos.cliente) {
      html = "<strong>Falta el paso 1.</strong> Todavia no hay acceso de Google cargado.";
    } else if (!datos.conectado) {
      html = "<strong>Acceso cargado.</strong> Falta autorizar tu cuenta (paso 2).";
    } else {
      html = "<strong>Conectado</strong> con " + escapar(datos.email || "tu cuenta") + ".";
      var ultimo = datos.ultimo;
      if (ultimo && ultimo.momento) {
        html += "<br>Ultima sincronizacion: " + escapar(ultimo.momento) + " - " +
                (ultimo.eventos_nuevos || 0) + " eventos nuevos, " +
                (ultimo.tareas_nuevas || 0) + " tareas nuevas.";
      }
    }
    caja.innerHTML = html;
  }).catch(function () {});
}

function abrirModalGoogle() {
  if (!modalGoogle) { modalGoogle = new bootstrap.Modal($("#modalGoogle")); }
  $("#err-g-cliente").classList.add("oculto");
  $("#err-g-autorizar").classList.add("oculto");
  $("#err-g-sync").classList.add("oculto");
  cargarGoogle();
  modalGoogle.show();
}

function cargarClienteGoogle() {
  var ruta = $("#g-ruta").value.trim();
  var error = $("#err-g-cliente");
  if (!ruta) {
    error.textContent = "Pega la ruta del JSON que bajaste.";
    error.classList.remove("oculto");
    return;
  }
  error.classList.add("oculto");
  api("/api/google/cliente", "POST", { ruta: ruta }).then(function () {
    avisar("Acceso cargado. Ahora autoriza tu cuenta.");
    cargarGoogle();
  }).catch(function (e) {
    error.textContent = e.message;
    error.classList.remove("oculto");
  });
}

function autorizarGoogle() {
  var error = $("#err-g-autorizar");
  error.classList.add("oculto");
  api("/api/google/autorizar").then(function (datos) {
    window.open(datos.url, "_blank");
    avisar("Se abrio Google. Aprueba y vuelve a esta pestaña.");
  }).catch(function (e) {
    error.textContent = e.message;
    error.classList.remove("oculto");
  });
}

function sincronizarGoogle() {
  var boton = $("#btn-g-sync");
  boton.disabled = true;
  boton.textContent = "Sincronizando...";
  api("/api/google/sync", "POST", {}).then(function (resultado) {
    boton.disabled = false;
    boton.textContent = "Sincronizar ahora";
    if (!resultado.ok && resultado.error) {
      avisar(resultado.error);
      cargarGoogle();
      return;
    }
    avisar("Google: " + resultado.eventos_nuevos + " eventos y " +
           resultado.tareas_nuevas + " tareas nuevas");
    cargarGoogle();
  }).catch(function (e) {
    boton.disabled = false;
    boton.textContent = "Sincronizar ahora";
    avisar(e.message);
  });
}

function desconectarGoogle() {
  api("/api/google/desconectar", "POST", {}).then(function () {
    avisar("Google desconectado");
    cargarGoogle();
  }).catch(function (error) { avisar(error.message); });
}

// -------------------------------------------------------------- servidor

var modalServidor = null;

function cargarServidor() {
  return api("/api/ajustes").then(function (datos) {
    var caja = $("#s-estado");
    if (!caja) { return; }
    var html = "<strong>Clave:</strong> " +
               (datos.clave ? "activada" : "sin clave (solo esta computadora)");
    html += "<br><strong>Escucha en:</strong> " +
            (datos.red_abierta ? "toda la red local" : "solo esta computadora");
    if (datos.red_abierta && datos.url_red) {
      html += "<br><strong>Desde el telefono:</strong> " + escapar(datos.url_red);
    }
    html += "<br><strong>Puerto:</strong> " + datos.puerto;
    caja.innerHTML = html;
    $("#s-red").checked = !!datos.red_abierta;
    $("#s-puerto").value = datos.puerto;
    $("#s-clave").value = "";
  }).catch(function () {});
}

function abrirModalServidor() {
  if (!modalServidor) { modalServidor = new bootstrap.Modal($("#modalServidor")); }
  $("#err-servidor").classList.add("oculto");
  cargarServidor();
  modalServidor.show();
}

function guardarServidor() {
  var error = $("#err-servidor");
  var datos = {
    host: $("#s-red").checked ? "0.0.0.0" : "127.0.0.1",
    puerto: parseInt($("#s-puerto").value, 10) || 8630
  };
  var clave = $("#s-clave").value.trim();
  if (clave) { datos.clave = clave; }

  error.classList.add("oculto");
  api("/api/ajustes", "POST", datos).then(function () {
    avisar("Guardado. Reinicia la app para aplicar red y puerto.");
    cargarServidor();
  }).catch(function (e) {
    error.textContent = e.message;
    error.classList.remove("oculto");
  });
}

function cerrarSesion() {
  api("/api/logout", "POST", {}).then(function () {
    window.location.href = "/login";
  }).catch(function () {
    window.location.href = "/login";
  });
}

// ------------------------------------------------------------------ init

function conectarEventos() {
  $$(".menu-item").forEach(function (boton) {
    boton.addEventListener("click", function () {
      cambiarVista(boton.getAttribute("data-vista"));
    });
  });

  $("#btn-nueva").addEventListener("click", function () { abrirModal(null); });
  $("#btn-nueva-hoy").addEventListener("click", function () { abrirModal(null, hoyISO()); });
  $("#btn-nueva-dia").addEventListener("click", function () { abrirModal(null, estado.calSeleccion); });
  $("#btn-nueva-dia-sel").addEventListener("click", function () { abrirModal(null, estado.calSeleccion); });
  $("#btn-guardar").addEventListener("click", guardarTarea);
  $("#btn-estimar").addEventListener("click", estimarDesdeModal);

  $("#btn-nube-config").addEventListener("click", abrirModalNube);
  $("#btn-telegram").addEventListener("click", abrirModalTelegram);
  $("#btn-tg-guardar").addEventListener("click", guardarTokenTelegram);
  $("#btn-tg-desvincular").addEventListener("click", desvincularTelegram);
  $("#btn-guardar-rec").addEventListener("click", guardarRecordatorios);

  $("#btn-google").addEventListener("click", abrirModalGoogle);
  $("#btn-servidor").addEventListener("click", abrirModalServidor);
  $("#btn-guardar-servidor").addEventListener("click", guardarServidor);
  $("#btn-salir").addEventListener("click", cerrarSesion);
  $("#btn-g-cliente").addEventListener("click", cargarClienteGoogle);
  $("#btn-g-autorizar").addEventListener("click", autorizarGoogle);
  $("#btn-g-sync").addEventListener("click", sincronizarGoogle);
  $("#btn-g-desconectar").addEventListener("click", desconectarGoogle);

  window.addEventListener("focus", function () {
    var modal = document.querySelector("#modalGoogle");
    if (modal && modal.classList.contains("show")) { cargarGoogle(); }
  });

  $("#btn-guardar-apunte").addEventListener("click", guardarApunte);
  document.addEventListener("click", accionApunte);

  var temporizadorNotas = null;
  $("#buscador-notas").addEventListener("input", function () {
    if (temporizadorNotas) { clearTimeout(temporizadorNotas); }
    temporizadorNotas = setTimeout(cargarNotas, 260);
  });

  $("#btn-nube-avisos").addEventListener("click", activarAvisos);
  $("#btn-nube-sync").addEventListener("click", sincronizarNube);
  $("#btn-guardar-nube").addEventListener("click", guardarNube);

  $("#f-titulo").addEventListener("keydown", function (evento) {
    if (evento.key === "Enter") {
      evento.preventDefault();
      guardarTarea();
    }
  });

  document.addEventListener("click", manejarAccionTarea);

  $$("#filtros-tareas .chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      $$("#filtros-tareas .chip").forEach(function (c) { c.classList.remove("activo"); });
      chip.classList.add("activo");
      estado.filtro = chip.getAttribute("data-filtro");
      cargarTareas();
    });
  });

  var temporizadorBusqueda = null;
  $("#buscador").addEventListener("input", function () {
    var valor = $("#buscador").value;
    if (temporizadorBusqueda) { clearTimeout(temporizadorBusqueda); }
    temporizadorBusqueda = setTimeout(function () {
      estado.busqueda = valor;
      cargarTareas();
    }, 260);
  });

  $$("#filtros-periodo .chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      $$("#filtros-periodo .chip").forEach(function (c) { c.classList.remove("activo"); });
      chip.classList.add("activo");
      estado.periodo = chip.getAttribute("data-periodo");
      cargarMetricas();
    });
  });

  // pomodoro
  $("#pomo-iniciar").addEventListener("click", iniciarPomodoro);
  $("#pomo-reiniciar").addEventListener("click", reiniciarPomodoro);
  $("#pomo-terminar").addEventListener("click", function () { terminarPomodoro(false); });
  $("#pomo-tarea").addEventListener("change", function () {
    var valor = $("#pomo-tarea").value;
    pomo.tareaId = valor ? parseInt(valor, 10) : null;
  });

  $$("#pomo-modos .chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      $$("#pomo-modos .chip").forEach(function (c) { c.classList.remove("activo"); });
      chip.classList.add("activo");
      var minutos = parseInt(chip.getAttribute("data-min"), 10);
      pomo.tipo = chip.getAttribute("data-tipo") === "descanso" ? "descanso" : "foco";
      pomo.total = minutos * 60;
      reiniciarPomodoro();
    });
  });

  // plan
  $("#btn-plan-ia").addEventListener("click", function () {
    var modal = new bootstrap.Modal($("#modalPlan"));
    modal.show();
  });
  $("#btn-generar-plan").addEventListener("click", function () {
    var activo = $("#plan-minutos .chip.activo");
    var minutos = activo ? parseInt(activo.getAttribute("data-min"), 10) : 120;
    armarPlan(minutos);
  });
  $$("#plan-minutos .chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      $$("#plan-minutos .chip").forEach(function (c) { c.classList.remove("activo"); });
      chip.classList.add("activo");
    });
  });

  // calendario
  $("#cal-anterior").addEventListener("click", function () {
    estado.calMes = estado.calMes - 1;
    if (estado.calMes < 0) { estado.calMes = 11; estado.calAnio = estado.calAnio - 1; }
    cargarCalendario();
  });
  $("#cal-siguiente").addEventListener("click", function () {
    estado.calMes = estado.calMes + 1;
    if (estado.calMes > 11) { estado.calMes = 0; estado.calAnio = estado.calAnio + 1; }
    cargarCalendario();
  });
  $("#cal-hoy").addEventListener("click", function () {
    var hoy = new Date();
    estado.calAnio = hoy.getFullYear();
    estado.calMes = hoy.getMonth();
    estado.calSeleccion = hoyISO();
    cargarCalendario();
  });

  $("#cal-grid").addEventListener("click", function (evento) {
    var celda = evento.target.closest(".cal-celda");
    if (!celda) { return; }
    seleccionarDia(celda.getAttribute("data-fecha"));
  });
}

document.addEventListener("DOMContentLoaded", function () {
  conectarEventos();
  cargarResumen();
  cargarHoy();
  cargarRacha();
  cargarNube();
  vigilarNube();
  pintarReloj();
});
