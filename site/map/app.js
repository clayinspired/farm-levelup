/* VM0047 land screening — map + timeline */
(function () {
  'use strict';

  // suppress focus rings for pointer-driven focus (iOS :focus-visible trap)
  addEventListener('keydown', function (e) {
    if (e.key === 'Tab') document.body.classList.add('kbd');
  });
  addEventListener('pointerdown', function () { document.body.classList.remove('kbd'); });

  var map = L.map('map', { zoomControl: false, attributionControl: true });
  L.control.zoom({ position: 'bottomleft' }).addTo(map);
  var base = L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    { maxZoom: 18, attribution: 'Esri World Imagery · Landsat C2 L2 · Hansen GFC v1.13' }
  ).addTo(map);

  var S = {
    aois: [], cur: null, year: null, layer: 'ndfi', filter: 'all',
    overlay: null, pending: null, rect: null, markers: {}, playing: false,
    timer: null, preloaded: {}
  };

  var $ = function (s) { return document.querySelector(s); };
  var fmt = function (v, d) { return v === null || v === undefined || isNaN(v) ? '—' : Number(v).toFixed(d === undefined ? 3 : d); };

  function cls(t) { return /^PASS/.test(t) ? 'pass' : /^FAIL/.test(t) ? 'fail' : 'cond'; }
  function short(t) { return t.split(' ')[0]; }

  /* ---------- sidebar ---------- */
  function buildFilters() {
    var counts = { all: S.aois.length, pass: 0, cond: 0, fail: 0 };
    S.aois.forEach(function (a) { counts[cls(a.triage)]++; });
    var defs = [['all', 'All'], ['pass', 'Eligible'], ['cond', 'Conditional'], ['fail', 'Fail']];
    var el = $('#filters'); el.innerHTML = '';
    defs.forEach(function (d) {
      if (!counts[d[0]]) return;
      var b = document.createElement('button');
      b.className = 'fchip'; b.dataset.f = d[0];
      b.setAttribute('aria-pressed', String(S.filter === d[0]));
      b.innerHTML = d[1] + '<span class="n">' + counts[d[0]] + '</span>';
      b.onclick = function () {
        S.filter = d[0];
        document.querySelectorAll('.fchip').forEach(function (x) {
          x.setAttribute('aria-pressed', String(x.dataset.f === d[0]));
        });
        buildList();
      };
      el.appendChild(b);
    });
  }

  function buildList() {
    var el = $('#list'); el.innerHTML = '';
    ['Southeast Asia', 'Africa'].forEach(function (region) {
      var group = S.aois.filter(function (a) {
        return a.region === region && (S.filter === 'all' || cls(a.triage) === S.filter);
      });
      if (!group.length) return;
      var h = document.createElement('div');
      h.className = 'sect';
      h.innerHTML = '<span class="dot" style="background:' +
        (region === 'Africa' ? 'var(--afr)' : 'var(--sea)') + '"></span>' + region;
      el.appendChild(h);
      group.forEach(function (a) {
        var b = document.createElement('button');
        b.className = 'aoi'; b.dataset.key = a.key;
        b.setAttribute('aria-current', 'false');
        b.innerHTML =
          '<span class="nm">' + a.country +
          '<span class="pill p-' + cls(a.triage) + '">' + short(a.triage) + '</span></span>' +
          '<span class="sb">' + a.note + '</span>';
        b.onclick = function () { select(a.key, true); };
        el.appendChild(b);
      });
    });
  }

  /* ---------- sparkline ---------- */
  function spark(series, years, opts) {
    opts = opts || {};
    var w = 238, h = 46, pad = 3;
    var vals = years.map(function (y) { var v = series[y]; return v === null || v === undefined ? NaN : v; });
    var fin = vals.filter(function (v) { return !isNaN(v); });
    if (!fin.length) return '<div class="cap">no data</div>';
    var lo = opts.lo !== undefined ? opts.lo : Math.min.apply(null, fin);
    var hi = opts.hi !== undefined ? opts.hi : Math.max.apply(null, fin);
    if (opts.pad) {                       // breathing room so a real trend is visible
      var sp = (hi - lo) || 0.02;
      lo -= sp * 0.25; hi += sp * 0.25;
    }
    if (hi - lo < 1e-6) { hi = lo + 1e-6; }
    opts.outLo = lo; opts.outHi = hi;
    var X = function (i) { return pad + i * (w - 2 * pad) / Math.max(1, years.length - 1); };
    var Y = function (v) { return h - pad - (v - lo) / (hi - lo) * (h - 2 * pad); };

    var d = '', started = false;
    vals.forEach(function (v, i) {
      if (isNaN(v)) { started = false; return; }
      d += (started ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1) + ' ';
      started = true;
    });
    var dots = years.map(function (y, i) {
      if (isNaN(vals[i])) return '';
      var on = y === S.year;
      return '<circle cx="' + X(i).toFixed(1) + '" cy="' + Y(vals[i]).toFixed(1) + '" r="' +
        (on ? 3.4 : 1.7) + '" fill="' + (on ? '#58a6ff' : (opts.color || '#3fb950')) + '"/>';
    }).join('');
    var band = '';
    if (opts.hline !== undefined && opts.hline >= lo && opts.hline <= hi) {
      band = '<line x1="0" y1="' + Y(opts.hline).toFixed(1) + '" x2="' + w + '" y2="' +
        Y(opts.hline).toFixed(1) + '" stroke="#f85149" stroke-width="1" stroke-dasharray="3 3" opacity=".75"/>';
    }
    var loss = (opts.lossYears || []).map(function (ly) {
      var i = years.indexOf(ly); if (i < 0) return '';
      return '<line x1="' + X(i).toFixed(1) + '" y1="0" x2="' + X(i).toFixed(1) + '" y2="' + h +
        '" stroke="#f85149" stroke-width="1" opacity=".3"/>';
    }).join('');
    return '<svg class="spark" width="100%" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" aria-hidden="true">' +
      loss + band + '<path d="' + d + '" fill="none" stroke="' + (opts.color || '#3fb950') +
      '" stroke-width="1.6" stroke-linejoin="round"/>' + dots + '</svg>';
  }

  /* ---------- detail ---------- */
  function icon(p) {
    return p === true ? '<span class="ic i-pass">✓</span>'
      : p === false ? '<span class="ic i-fail">✕</span>'
      : '<span class="ic i-man">?</span>';
  }

  function renderDetail() {
    var a = S.cur; if (!a) return '';
    var t = a.trend || {};
    var html =
      '<h2>' + a.country + '</h2>' +
      '<div class="loc">' + a.note + '</div>' +
      '<div class="verdict v-' + cls(a.triage) + '">' + a.triage + '</div>' +

      '<div class="mrow"><span>Stocking index ' + S.year + '</span><b>' + fmt(a.si[S.year]) + '</b></div>' +
      '<div class="mrow"><span>Forest fraction ' + S.year + '</span><b>' +
        (a.forest[S.year] === null || a.forest[S.year] === undefined ? '—' : (a.forest[S.year] * 100).toFixed(1) + '%') + '</b></div>' +
      '<div class="mrow"><span>SI trend t−10→t0</span><b style="color:' +
        (t.significant_negative ? 'var(--fail)' : 'var(--ink)') + '">' +
        (t.slope === null || t.slope === undefined ? '—' : (t.slope > 0 ? '+' : '') + fmt(t.slope, 4) + '/yr') + '</b></div>' +
      '<div class="mrow"><span>p-value</span><b>' + fmt(t.p, 3) + '</b></div>' +
      '<div class="mrow"><span>Cleared in window</span><b style="color:' +
        (a.cum_loss >= 0.01 ? 'var(--cond)' : 'var(--ink)') + '">' +
        (a.cum_loss === null || a.cum_loss === undefined ? '—' : (a.cum_loss * 100).toFixed(2) + '%') + '</b></div>' +
      '<div class="mrow"><span>Season window</span><b>m' + a.season[0] + '–m' + a.season[1] + '</b></div>' +
      '<div class="mrow"><span>Scenes ' + S.year + '</span><b>' + (a.scenes[S.year] || '—') + '</b></div>' +

      '<h3>Stocking index (NDFI)</h3>' +
      (function () {
        var o = { color: '#3fb950', lossYears: a.loss_years, pad: true };
        var svg = spark(a.si, a.years, o);
        var t = a.trend || {};
        var trendTxt = (t.slope === null || t.slope === undefined) ? ''
          : (t.significant_negative
              ? ' <b style="color:var(--fail)">Declining (p&lt;0.05) — §8 justification required.</b>'
              : (t.slope > 0 && t.p !== null && t.p < 0.05
                  ? ' <b style="color:var(--pass)">Significant greening (p=' + fmt(t.p, 3) + ').</b>'
                  : ''));
        return svg + '<div class="cap">Axis ' + fmt(o.outLo, 2) + ' to ' + fmt(o.outHi, 2) +
          '. Red verticals mark years losing &ge;0.5% of the AOI to clearing.' + trendTxt + '</div>';
      })() +

      '<h3>Forest fraction</h3>' +
      spark(a.forest, a.years, { lo: 0, hi: Math.max(0.15, Math.max.apply(null,
        a.years.map(function (y) { return a.forest[y] || 0; })) * 1.1),
        color: '#8b949e', hline: 0.10 }) +
      '<div class="cap">Dashed line = 10% woody-cover limit (§4 #11a, census route).</div>' +

      '<h3>Eligibility checks</h3>';

    Object.keys(a.findings).forEach(function (k) {
      var f = a.findings[k];
      html += '<div class="chk">' + icon(f.passes) + '<span>' +
        f.test.replace(/ - /, ' — ').replace('>=', '\u2265')
              .replace(/t-10\.\.t0/g, 't\u221210\u2026t0')
              .replace(/\[t-10,t-8\]/g, '[t\u221210, t\u22128]') + '</span></div>';
    });
    html += '<div class="cap" style="margin-top:10px">Screening only — not a validation-grade determination. See README for what this does not check.</div>';
    return html;
  }

  function paintDetail() {
    var h = renderDetail();
    $('#detail').innerHTML = h;
    $('#detail-m').innerHTML = '<div class="dpanel dpanel-m">' + h + '</div>';
  }

  /* ---------- map overlay ---------- */
  // Frames are swapped load-then-remove: the incoming overlay is added transparent and
  // only becomes visible once its PNG has decoded, at which point the outgoing one is
  // removed. Removing first (the naive approach) leaves a gap showing bare basemap,
  // which reads as a flicker on every tick of the timeline.
  function preload(a) {
    ['ndfi', 'forest'].forEach(function (layer) {
      var m = a.layers[layer] || {};
      Object.keys(m).forEach(function (y) {
        var src = m[y];
        if (S.preloaded[src]) return;
        var img = new Image();
        img.decoding = 'async';
        img.src = src;
        S.preloaded[src] = img;
      });
    });
  }

  function clearOverlays() {
    if (S.pending) { map.removeLayer(S.pending); S.pending = null; }
    if (S.overlay) { map.removeLayer(S.overlay); S.overlay = null; }
  }

  function showOverlay() {
    var a = S.cur; if (!a) return;
    if (S.layer === 'none') { clearOverlays(); return; }
    var src = (a.layers[S.layer] || {})[S.year];
    if (!src) { clearOverlays(); return; }

    // already showing this exact frame
    if (S.overlay && S.overlay._vmSrc === src && !S.pending) return;

    var b = a.bbox;
    var bounds = [[b[1], b[0]], [b[3], b[2]]];
    var target = S.layer === 'forest' ? 0.72 : 0.78;

    if (S.pending) { map.removeLayer(S.pending); S.pending = null; }

    var next = L.imageOverlay(src, bounds, { opacity: 0, interactive: false });
    next._vmSrc = src;

    function reveal() {
      if (S.pending !== next) return;            // a newer frame superseded this one
      next.setOpacity(target);
      if (S.overlay && S.overlay !== next) map.removeLayer(S.overlay);
      S.overlay = next;
      S.pending = null;
    }
    next.on('load', reveal);
    next.on('error', function () {
      if (S.pending === next) { map.removeLayer(next); S.pending = null; }
    });

    S.pending = next;
    next.addTo(map);
    // A cached image can finish before Leaflet wires its load handler.
    var el = next.getElement();
    if (el && el.complete && el.naturalWidth) reveal();
  }

  function select(key, fly) {
    var a = S.aois.filter(function (x) { return x.key === key; })[0];
    if (!a) return;
    S.cur = a;
    // start at the beginning of the look-back window so Play moves forward in time
    if (S.year === null || a.years.indexOf(S.year) < 0) S.year = a.years[0];
    document.querySelectorAll('.aoi').forEach(function (el) {
      el.setAttribute('aria-current', String(el.dataset.key === key));
    });
    if (S.rect) map.removeLayer(S.rect);
    var b = a.bbox;
    S.rect = L.rectangle([[b[1], b[0]], [b[3], b[2]]],
      { color: '#58a6ff', weight: 1.6, fill: false, dashArray: '4 3' }).addTo(map);
    if (fly) map.flyToBounds(S.rect.getBounds(), { padding: [90, 90], duration: 0.8, maxZoom: 14 });
    preload(a);
    if (S.layer === 'forest') $('#legthr').textContent = a.canopy_threshold;
    buildTicks(); syncYear(true);
  }

  /* ---------- timeline ---------- */
  function buildTicks() {
    var a = S.cur; if (!a) return;
    var el = $('#ticks'); el.innerHTML = '';
    $('#scrub').max = String(a.years.length - 1);
    a.years.forEach(function (y) {
      var s = document.createElement('span');
      s.textContent = "'" + String(y).slice(2);
      if (a.loss_years.indexOf(y) >= 0) s.className = 'tick-loss';
      s.dataset.year = y;
      el.appendChild(s);
    });
  }

  var heavyTimer = null;
  function scheduleHeavy(delay) {
    if (heavyTimer) clearTimeout(heavyTimer);
    heavyTimer = setTimeout(function () {
      heavyTimer = null;
      showOverlay();
      paintDetail();
    }, delay);
  }

  function syncYear(immediate) {
    var a = S.cur; if (!a) return;
    var i = a.years.indexOf(S.year); if (i < 0) { i = a.years.length - 1; S.year = a.years[i]; }
    $('#scrub').value = String(i);
    $('#yr').textContent = S.year;
    var off = S.year - a.t0;
    $('#yrsub').textContent = off === 0 ? 't = 0' : 't = ' + off;
    document.querySelectorAll('#ticks span').forEach(function (s) {
      s.classList.toggle('on', Number(s.dataset.year) === S.year);
    });
    // Swapping the raster and re-rendering the panel on every intermediate value
    // of a drag is what made scrubbing flash; coalesce it instead.
    scheduleHeavy(immediate ? 0 : 90);
  }

  function play() {
    S.playing = !S.playing;
    $('#pi').setAttribute('d', S.playing ? 'M2.5 1.5h2.6v9H2.5zM6.9 1.5h2.6v9H6.9z' : 'M3 1.5v9l7-4.5z');
    $('#play').setAttribute('aria-label', S.playing ? 'Pause timeline' : 'Play timeline');
    if (S.timer) { clearInterval(S.timer); S.timer = null; }
    if (S.playing) {
      S.timer = setInterval(function () {
        var a = S.cur; if (!a) return;
        var i = a.years.indexOf(S.year);
        S.year = a.years[(i + 1) % a.years.length];
        syncYear(true);
      }, 900);
    }
  }

  /* ---------- wiring ---------- */
  // The timeline sits over the map. Dragging the map often started on its
  // background and moved the slider instead of panning, so the panel itself is
  // transparent to pointers and only its actual controls accept them.
  ['#time', '#ctrl', '#legend'].forEach(function (sel) {
    var el = $(sel); if (!el) return;
    el.style.pointerEvents = 'none';
    el.querySelectorAll('button, input, a, select').forEach(function (c) {
      c.style.pointerEvents = 'auto';
      L.DomEvent.disableClickPropagation(c);
      L.DomEvent.on(c, 'pointerdown mousedown touchstart', L.DomEvent.stopPropagation);
    });
  });

  $('#play').onclick = play;
  $('#scrub').oninput = function (e) {
    var a = S.cur; if (!a) return;
    S.year = a.years[Number(e.target.value)]; syncYear(false);
  };
  $('#scrub').onchange = function () { syncYear(true); };   // settle on release
  document.querySelectorAll('.seg').forEach(function (b) {
    b.onclick = function () {
      S.layer = b.dataset.layer;
      document.querySelectorAll('.seg').forEach(function (x) {
        x.setAttribute('aria-pressed', String(x === b));
      });
      $('#legtitle').textContent = S.layer === 'forest'
        ? 'Hansen forest cover' : S.layer === 'none' ? 'Basemap only' : 'NDFI stocking index';
      $('#legbody').style.display = S.layer === 'ndfi' ? '' : 'none';
      $('#legforest').style.display = S.layer === 'forest' ? '' : 'none';
      if (S.cur) $('#legthr').textContent = S.cur.canopy_threshold;
      showOverlay();
    };
  });
  document.querySelectorAll('.mtab').forEach(function (b) {
    b.onclick = function () {
      document.querySelectorAll('.mtab').forEach(function (x) {
        x.setAttribute('aria-pressed', String(x === b));
      });
      var showList = b.dataset.mtab === 'list';
      $('#list').style.display = showList ? '' : 'none';
      $('#detail-m').style.display = showList ? 'none' : 'block';
    };
  });
  addEventListener('keydown', function (e) {
    var a = S.cur; if (!a) return;
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      var i = a.years.indexOf(S.year) + (e.key === 'ArrowRight' ? 1 : -1);
      if (i >= 0 && i < a.years.length) { S.year = a.years[i]; syncYear(true); }
    }
  });

  /* ---------- a field drawn in the bot, opened here via ?plot=<token> ---------- */
  function loadSharedPlot() {
    var tok = new URLSearchParams(location.search).get('plot');
    if (!tok) return;
    var store = (window.FARM && window.FARM.store) || '';
    if (!store) return;
    fetch(store + '/share/' + encodeURIComponent(tok))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !d.coordinates || d.coordinates.length < 3) return;
        var latlngs = d.coordinates.map(function (c) { return [c[1], c[0]]; });
        var poly = L.polygon(latlngs, {
          color: '#f0b400', weight: 2.5, fillColor: '#f0b400', fillOpacity: .25
        }).addTo(map);
        // Label rides with the field itself; a corner badge collided with the legend.
        poly.bindTooltip(
          'Your field · ' + (d.area_ha || 0).toFixed(2) + ' ha (' +
          ((d.area_ha || 0) / 0.40468564224).toFixed(2) + ' acres)',
          { permanent: true, direction: 'top', className: 'mine-label' });
        map.fitBounds(poly.getBounds().pad(3));
      })
      .catch(function () {});
  }

  /* ---------- boot ---------- */
  fetch('data/index.json?v=' + Date.now()).then(function (r) { return r.json(); }).then(function (d) {
    S.aois = d.aois;
    if (!S.aois.length) { $('#list').innerHTML = '<div class="sect">no data yet</div>'; return; }
    buildFilters(); buildList();
    S.aois.forEach(function (a) {
      var color = a.triage.charAt(0) === 'P' ? '#3fb950' : a.triage.charAt(0) === 'F' ? '#f85149' : '#d29922';
      var m = L.circleMarker(a.centre, {
        radius: 7, color: '#0d1117', weight: 2, fillColor: color, fillOpacity: 1
      }).addTo(map).bindTooltip(a.country + ' — ' + a.note, { direction: 'top' });
      m.on('click', function () { select(a.key, true); });
      S.markers[a.key] = m;
    });
    map.fitBounds(L.latLngBounds(S.aois.map(function (a) { return a.centre; })).pad(0.35));
    var shared = new URLSearchParams(location.search).get('plot');
    // Arriving from the bot, the subject is the user's own field - do not open
    // an unrelated sample site's panel over it.
    select(S.aois[0].key, !shared);
    if (shared) { $('#detail').style.display = 'none'; loadSharedPlot(); }
    if (innerWidth <= 860) $('#detail-m').style.display = 'none';
  }).catch(function (e) {
    $('#list').innerHTML = '<div class="sect">failed to load data</div>';
    console.error(e);
  });
})();
