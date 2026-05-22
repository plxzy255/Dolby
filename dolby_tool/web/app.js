// dolby-tool frontend

// ---------------------------------------------------------------------------
// utilities

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function api(path, body) {
  return fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(async (r) => {
    const text = await r.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { detail: text }; }
    if (!r.ok) throw new Error(data.detail || `${r.status} ${r.statusText}`);
    return data;
  });
}

function get(path) {
  return fetch(path).then(async (r) => {
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  });
}

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const c of children) {
    if (c == null || c === false) continue;
    if (Array.isArray(c)) c.forEach((cc) => cc && e.appendChild(cc));
    else if (typeof c === 'string' || typeof c === 'number') e.appendChild(document.createTextNode(String(c)));
    else e.appendChild(c);
  }
  return e;
}

function kv(k, v, pillClass) {
  if (v === null || v === undefined || v === '') v = '—';
  const valueEl = pillClass
    ? el('span', { class: `pill ${pillClass}` }, String(v))
    : el('span', { class: 'v' }, String(v));
  return el('div', { class: 'kv' }, el('span', { class: 'k' }, k), valueEl);
}

function pathFromDataTransfer(dt) {
  // Safari passes file:// URIs; Chrome/Firefox only expose File objects — no .path
  const uri = dt.getData('text/uri-list') || dt.getData('text/plain');
  if (uri) {
    const first = uri.split('\n').find((l) => l.trim() && !l.startsWith('#'));
    if (first) return first.startsWith('file://') ? decodeURIComponent(first.slice('file://'.length)) : first;
  }
  return null;
}

async function pathsFromDataTransfer(dt, multi) {
  // Try URI list first (Safari)
  const uriList = (dt.getData('text/uri-list') || dt.getData('text/plain'))
    .split('\n').map((l) => l.trim()).filter((l) => l && !l.startsWith('#'));
  if (uriList.length) {
    const paths = uriList.map((u) => u.startsWith('file://') ? decodeURIComponent(u.slice(7)) : u);
    return paths;
  }
  // Fallback: File objects (Chrome on macOS) — resolve via Spotlight
  const files = Array.from(dt.files || []);
  if (!files.length) return [];
  const resolved = await Promise.all(files.map(async (f) => {
    const res = await fetch('/api/find?name=' + encodeURIComponent(f.name)).then((r) => r.json());
    if (res.paths.length === 1) return res.paths[0];
    if (res.paths.length > 1) {
      // Multiple hits — show a disambiguation prompt
      const choice = window.prompt(
        `Found ${res.paths.length} files named "${f.name}":\n\n` +
        res.paths.map((p, i) => `${i + 1}. ${p}`).join('\n') +
        '\n\nEnter number to select (or Cancel to skip):',
        '1',
      );
      const idx = parseInt(choice, 10) - 1;
      return (idx >= 0 && idx < res.paths.length) ? res.paths[idx] : null;
    }
    // Not indexed by Spotlight — ask user to use Browse
    alert(`Could not locate "${f.name}" via Spotlight. Use Browse… or paste the full path instead.`);
    return null;
  }));
  return resolved.filter(Boolean);
}

function bindDropzone(zone, onPath, { multi = false } = {}) {
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag'));
  zone.addEventListener('drop', async (e) => {
    e.preventDefault();
    zone.classList.remove('drag');
    const paths = await pathsFromDataTransfer(e.dataTransfer, multi);
    if (!paths.length) return;
    if (multi) onPath(paths);
    else onPath(paths[0]);
  });
}

// ---------------------------------------------------------------------------
// tabs

$$('.tab').forEach((t) => {
  t.addEventListener('click', () => {
    $$('.tab').forEach((x) => x.classList.remove('active'));
    $$('.panel').forEach((x) => x.classList.remove('active'));
    t.classList.add('active');
    $(`#tab-${t.dataset.tab}`).classList.add('active');
  });
});

// ---------------------------------------------------------------------------
// Inspect tab

bindDropzone($('#inspect-drop'), (p) => {
  $('#inspect-path').value = p;
  runInspect(p);
});

$('#inspect-browse').addEventListener('click', async () => {
  const { paths } = await get('/api/pick');
  if (paths.length) {
    $('#inspect-path').value = paths[0];
    runInspect(paths[0]);
  }
});

$('#inspect-go').addEventListener('click', () => runInspect($('#inspect-path').value.trim()));

$('#inspect-path').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') runInspect(e.target.value.trim());
});

async function runInspect(path) {
  if (!path) return;
  const out = $('#inspect-result');
  out.innerHTML = '<div class="card"><h2>Inspecting…</h2></div>';
  try {
    const spec = await api('/api/inspect', { path });
    out.innerHTML = '';
    out.appendChild(renderSpec(spec));
  } catch (e) {
    out.innerHTML = '';
    out.appendChild(el('div', { class: 'error' }, e.message));
  }
}

function renderSpec(spec) {
  const v = spec.video;
  const dv = v.dolby_vision;
  const card = el('div', { class: 'card' });
  card.appendChild(el('h2', {}, spec.filename));
  card.appendChild(el('div', { class: 'filename' }, spec.path));

  if (v.fourcc_warning) {
    card.appendChild(el('div', { class: 'warning', html: `<strong>⚠︎ TV.app DV breakage:</strong> ${v.fourcc_warning}` }));
  }

  // Verdict pills
  const pills = el('div', { class: 'row', style: 'justify-content: flex-start; margin-bottom: 12px' });
  pills.appendChild(el('span', { class: 'pill ' + (dv.present ? (v.fourcc_warning ? 'warn' : 'good') : 'neutral') },
    dv.present ? `Dolby Vision ${dv.profile || dv.profile_raw} (${dv.compatibility_name})` : 'No Dolby Vision'));
  pills.appendChild(el('span', { class: 'pill ' + (v.hdr10_plus ? 'good' : 'neutral') }, v.hdr10_plus ? 'HDR10+' : 'No HDR10+'));
  pills.appendChild(el('span', { class: 'pill ' + ((v.hdr10.mdcv || v.hdr10.cll) ? 'good' : 'neutral') }, (v.hdr10.mdcv || v.hdr10.cll) ? 'HDR10' : 'No HDR10'));
  pills.appendChild(el('span', { class: 'pill ' + (v.fourcc && (v.fourcc.startsWith('dv') ? 'good' : (dv.present ? 'bad' : 'neutral'))) }, `FourCC: ${v.fourcc || 'n/a'}`));
  const anyAtmos = spec.audio.some((a) => a.atmos === true);
  pills.appendChild(el('span', { class: 'pill ' + (anyAtmos ? 'good' : 'neutral') }, anyAtmos ? 'Atmos' : 'No Atmos'));
  card.appendChild(pills);

  // Container
  card.appendChild(el('h3', {}, 'Container'));
  const cont = spec.container;
  const cgrid = el('div', { class: 'grid' });
  cgrid.appendChild(kv('Format', cont.format_name));
  cgrid.appendChild(kv('Duration', cont.duration_pretty));
  cgrid.appendChild(kv('Size', cont.size_pretty));
  cgrid.appendChild(kv('Overall bitrate', cont.overall_bit_rate_bps ? `${(cont.overall_bit_rate_bps/1_000_000).toFixed(2)} Mbps` : null));
  card.appendChild(cgrid);

  // Video
  card.appendChild(el('h3', {}, 'Video'));
  const vgrid = el('div', { class: 'grid' });
  vgrid.appendChild(kv('Codec', v.codec));
  vgrid.appendChild(kv('Profile', v.profile));
  vgrid.appendChild(kv('FourCC', v.fourcc, v.fourcc && v.fourcc.startsWith('dv') ? 'good' : (dv.present ? 'bad' : 'neutral')));
  vgrid.appendChild(kv('Resolution', v.resolution));
  vgrid.appendChild(kv('FPS', v.fps));
  vgrid.appendChild(kv('Pixel fmt', v.pix_fmt));
  vgrid.appendChild(kv('Bitrate', v.bit_rate_mbps ? `${v.bit_rate_mbps} Mbps` : null));
  vgrid.appendChild(kv('Transfer', v.color_transfer));
  vgrid.appendChild(kv('Primaries', v.color_primaries));
  vgrid.appendChild(kv('Color space', v.color_space));
  card.appendChild(vgrid);

  // Dolby Vision
  if (dv.present) {
    card.appendChild(el('h3', {}, 'Dolby Vision'));
    const dgrid = el('div', { class: 'grid' });
    dgrid.appendChild(kv('Profile', dv.profile, 'good'));
    dgrid.appendChild(kv('Raw profile', dv.profile_raw));
    dgrid.appendChild(kv('Compatibility', `${dv.compatibility_id} (${dv.compatibility_name})`));
    dgrid.appendChild(kv('Level', dv.level));
    dgrid.appendChild(kv('RPU present', dv.rpu_present ? 'yes' : 'no'));
    dgrid.appendChild(kv('BL present', dv.bl_present ? 'yes' : 'no'));
    dgrid.appendChild(kv('EL present', dv.el_present ? 'yes' : 'no'));
    card.appendChild(dgrid);
  }

  // HDR
  card.appendChild(el('h3', {}, 'HDR metadata'));
  const hgrid = el('div', { class: 'grid' });
  hgrid.appendChild(kv('Mastering display', v.hdr10.mdcv ? 'present' : '—', v.hdr10.mdcv ? 'good' : 'neutral'));
  hgrid.appendChild(kv('Content light level', v.hdr10.cll ? 'present' : '—', v.hdr10.cll ? 'good' : 'neutral'));
  hgrid.appendChild(kv('HDR10+', v.hdr10_plus ? 'present' : '—', v.hdr10_plus ? 'good' : 'neutral'));
  card.appendChild(hgrid);

  // Audio
  if (spec.audio.length) {
    card.appendChild(el('h3', {}, `Audio (${spec.audio.length} track${spec.audio.length === 1 ? '' : 's'})`));
    const at = el('table');
    at.appendChild(el('thead', {}, el('tr', {},
      el('th', {}, '#'),
      el('th', {}, 'Codec'),
      el('th', {}, 'Profile'),
      el('th', {}, 'Channels'),
      el('th', {}, 'Layout'),
      el('th', {}, 'Bitrate'),
      el('th', {}, 'Sample'),
      el('th', {}, 'Lang'),
      el('th', {}, 'Atmos'),
    )));
    const ab = el('tbody');
    spec.audio.forEach((a, i) => {
      ab.appendChild(el('tr', {},
        el('td', { class: 'num' }, i),
        el('td', { class: 'mono' }, a.codec || '—'),
        el('td', {}, a.profile || '—'),
        el('td', { class: 'num' }, a.channels ?? '—'),
        el('td', { class: 'mono' }, a.channel_layout || '—'),
        el('td', { class: 'num' }, a.bit_rate_kbps ? `${a.bit_rate_kbps} kbps` : '—'),
        el('td', { class: 'num' }, a.sample_rate_hz ? `${a.sample_rate_hz} Hz` : '—'),
        el('td', {}, a.language || '—'),
        el('td', {}, a.atmos === true ? '✓' : (a.atmos === false ? '✗' : '?')),
      ));
    });
    at.appendChild(ab);
    card.appendChild(at);
  }

  // Subtitles
  if (spec.subtitles.length) {
    card.appendChild(el('h3', {}, `Subtitles (${spec.subtitles.length} track${spec.subtitles.length === 1 ? '' : 's'})`));
    const st = el('table');
    st.appendChild(el('thead', {}, el('tr', {},
      el('th', {}, '#'),
      el('th', {}, 'Codec'),
      el('th', {}, 'Lang'),
      el('th', {}, 'Title'),
      el('th', {}, 'Default'),
      el('th', {}, 'Forced'),
      el('th', {}, 'SDH'),
    )));
    const sb = el('tbody');
    spec.subtitles.forEach((s, i) => {
      sb.appendChild(el('tr', {},
        el('td', { class: 'num' }, i),
        el('td', { class: 'mono' }, s.codec || '—'),
        el('td', {}, s.language || '—'),
        el('td', {}, s.title || '—'),
        el('td', {}, s.default ? '✓' : ''),
        el('td', {}, s.forced ? '✓' : ''),
        el('td', {}, s.hearing_impaired ? '✓' : ''),
      ));
    });
    st.appendChild(sb);
    card.appendChild(st);
  }

  // Raw JSON drill-down
  const det = el('details', {}, el('summary', {}, 'Raw JSON'), el('pre', {}, JSON.stringify(spec, null, 2)));
  card.appendChild(det);

  return card;
}

// ---------------------------------------------------------------------------
// Compare tab

const comparePaths = new Set();

function renderCompareList() {
  const ul = $('#compare-list');
  ul.innerHTML = '';
  Array.from(comparePaths).forEach((p) => {
    const li = el('li', {},
      el('span', { class: 'name' }, p),
      el('button', { class: 'remove', title: 'Remove', onclick: () => { comparePaths.delete(p); renderCompareList(); } }, '×'),
    );
    ul.appendChild(li);
  });
}

bindDropzone($('#compare-drop'), (paths) => {
  paths.forEach((p) => comparePaths.add(p));
  renderCompareList();
}, { multi: true });

$('#compare-add').addEventListener('click', async () => {
  const { paths } = await get('/api/pick?multi=true');
  paths.forEach((p) => comparePaths.add(p));
  renderCompareList();
});

$('#compare-add-folder').addEventListener('click', async () => {
  const dir = $('#compare-folder-path').value.trim();
  if (!dir) {
    alert('Paste a folder path first.');
    return;
  }
  try {
    const { files } = await get('/api/list?path=' + encodeURIComponent(dir));
    files.forEach((f) => comparePaths.add(f.path));
    renderCompareList();
  } catch (e) {
    alert(e.message);
  }
});

$('#compare-clear').addEventListener('click', () => {
  comparePaths.clear();
  renderCompareList();
  $('#compare-result').innerHTML = '';
});

$('#compare-go').addEventListener('click', async () => {
  const out = $('#compare-result');
  if (comparePaths.size < 1) { alert('Add at least one file.'); return; }
  out.innerHTML = '<div class="card"><h2>Comparing…</h2></div>';
  try {
    const res = await api('/api/compare', { paths: Array.from(comparePaths) });
    out.innerHTML = '';
    out.appendChild(renderCompare(res));
  } catch (e) {
    out.innerHTML = '';
    out.appendChild(el('div', { class: 'error' }, e.message));
  }
});

function renderCompare(res) {
  const card = el('div', { class: 'card' });
  card.appendChild(el('h2', {}, 'Comparison'));

  if (res.errors.length) {
    res.errors.forEach((er) => {
      card.appendChild(el('div', { class: 'warning' }, `${er.path}: ${er.error}`));
    });
  }

  // Score row
  const scoreGrid = el('div', { class: 'grid', style: 'margin-bottom: 16px' });
  res.rows.forEach((r, i) => {
    const s = res.scores[i];
    const pillClass = s.is_best ? 'good' : 'neutral';
    scoreGrid.appendChild(kv(r.filename, `${s.total} / ${s.max}` + (s.is_best ? ' ★ best' : ''), pillClass));
  });
  card.appendChild(scoreGrid);

  // Big table
  const t = el('table');
  const headers = [
    'File', 'Size', 'Res', 'FPS', 'V codec', 'FourCC', 'V bitrate',
    'DV profile', 'DV compat', 'HDR10', 'HDR10+',
    'Audio', 'Ch', 'A bitrate', 'Atmos', 'Subs'
  ];
  t.appendChild(el('thead', {}, el('tr', {}, ...headers.map((h) => el('th', {}, h)))));
  const tb = el('tbody');
  res.rows.forEach((r, i) => {
    const isBest = res.scores[i].is_best;
    const w = res.winners;
    const winCell = (key, val, mono = false) => {
      const isWinner = w[key] && w[key].includes(i) && w[key].length < res.rows.length;
      const cls = (mono ? 'mono ' : '') + (isWinner ? 'winner' : '');
      return el('td', { class: cls.trim() }, val ?? '—');
    };
    const tr = el('tr', { class: isBest ? 'best-row' : '' },
      el('td', { class: 'mono', title: r.path }, r.filename),
      el('td', { class: 'num' }, r.size || '—'),
      el('td', { class: 'mono' }, r.resolution || '—'),
      el('td', { class: 'num' }, r.fps || '—'),
      el('td', { class: 'mono' }, r.video_codec || '—'),
      winCell('fourcc_ok', r.fourcc || '—', true),
      winCell('video_bitrate_mbps', r.video_bitrate_mbps ? `${r.video_bitrate_mbps} Mbps` : '—', false),
      winCell('dv_profile', r.dv_profile || '—', true),
      el('td', { class: 'mono' }, r.dv_compat || '—'),
      el('td', {}, r.hdr10 ? '✓' : '—'),
      winCell('hdr10_plus', r.hdr10_plus ? '✓' : '—'),
      el('td', { class: 'mono' }, r.audio_codec || '—'),
      winCell('audio_channels', r.audio_channels || '—'),
      winCell('audio_bitrate_kbps', r.audio_bitrate_kbps ? `${r.audio_bitrate_kbps} kbps` : '—'),
      winCell('audio_atmos', r.audio_atmos === true ? '✓' : '—'),
      winCell('subtitle_count', r.subtitle_count),
    );
    tb.appendChild(tr);
  });
  t.appendChild(tb);
  card.appendChild(t);

  // Per-file warnings
  res.rows.forEach((r) => {
    r.warnings.forEach((w) => {
      card.appendChild(el('div', { class: 'warning' }, `${r.filename}: ${w}`));
    });
  });

  // Score component breakdown
  card.appendChild(el('h3', {}, 'Score breakdown'));
  const sb = el('table');
  sb.appendChild(el('thead', {}, el('tr', {},
    el('th', {}, 'File'),
    el('th', {}, 'DV present'),
    el('th', {}, 'DV fourcc'),
    el('th', {}, 'HDR10+'),
    el('th', {}, 'Atmos'),
    el('th', {}, 'V bitrate'),
    el('th', {}, 'Resolution'),
    el('th', {}, 'Subs'),
    el('th', {}, 'Total'),
  )));
  const sbody = el('tbody');
  res.scores.forEach((s, i) => {
    const c = s.components;
    sbody.appendChild(el('tr', { class: s.is_best ? 'best-row' : '' },
      el('td', { class: 'mono' }, res.rows[i].filename),
      el('td', { class: 'num' }, c.dv_present),
      el('td', { class: 'num' }, c.dv_fourcc_ok),
      el('td', { class: 'num' }, c.hdr10_plus),
      el('td', { class: 'num' }, c.atmos),
      el('td', { class: 'num' }, c.bit_rate_mbps),
      el('td', { class: 'num' }, c.resolution),
      el('td', { class: 'num' }, c.subtitles),
      el('td', { class: 'num' }, `${s.total} / ${s.max}`),
    ));
  });
  sb.appendChild(sbody);
  card.appendChild(sb);

  return card;
}

// ---------------------------------------------------------------------------
// TV Capture tab

let captureWs = null;
let captureCount = 0;

function setCaptureStatus(state, label) {
  const s = $('#capture-status');
  s.className = 'status ' + state;
  s.textContent = label;
}

$('#capture-start').addEventListener('click', () => {
  $('#capture-events').innerHTML = '';
  $('#capture-summary').innerHTML = '';
  captureCount = 0;
  $('#capture-counter').textContent = '0 events';

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  captureWs = new WebSocket(`${proto}://${location.host}/ws/tvlog`);
  captureWs.onopen = () => {
    captureWs.send(JSON.stringify({ cmd: 'start' }));
  };
  captureWs.onmessage = (msg) => {
    const data = JSON.parse(msg.data);
    if (data.type === 'started') {
      setCaptureStatus('running', 'Capturing… play in TV.app now');
      $('#capture-start').disabled = true;
      $('#capture-stop').disabled = false;
    } else if (data.type === 'event') {
      addEvent(data.event);
    } else if (data.type === 'summary') {
      setCaptureStatus('done', `Done — ${data.summary.event_count} events`);
      $('#capture-summary').appendChild(renderCaptureSummary(data.summary));
      $('#capture-start').disabled = false;
      $('#capture-stop').disabled = true;
    } else if (data.type === 'error') {
      setCaptureStatus('error', data.message);
    }
  };
  captureWs.onerror = () => setCaptureStatus('error', 'WebSocket error');
  captureWs.onclose = () => {
    $('#capture-start').disabled = false;
    $('#capture-stop').disabled = true;
  };
});

$('#capture-stop').addEventListener('click', () => {
  if (captureWs && captureWs.readyState === WebSocket.OPEN) {
    captureWs.send(JSON.stringify({ cmd: 'stop' }));
  }
});

function addEvent(ev) {
  captureCount++;
  $('#capture-counter').textContent = `${captureCount} event${captureCount === 1 ? '' : 's'}`;
  const summary = formatEventSummary(ev);
  const node = el('div', { class: 'event' },
    el('span', { class: 'kind ' + ev.kind }, ev.kind),
    summary,
  );
  const wrap = $('#capture-events');
  // Insert at top because flex-direction: column-reverse renders bottom-up
  wrap.insertBefore(node, wrap.firstChild);
  while (wrap.children.length > 500) wrap.removeChild(wrap.lastChild);
}

function formatEventSummary(ev) {
  switch (ev.kind) {
    case 'hls_variant':
      return `${ev.width}x${ev.height} ${ev.codecs || ''} ${ev.video_range || ''}` +
        (ev.peak_bps ? ` peak ${(ev.peak_bps/1_000_000).toFixed(1)}Mbps` : '');
    case 'codec_type':
      return `${ev.fourcc} (${ev.decoder || 'decoder'}) ${ev.width ? `${ev.width}x${ev.height}` : ''}`;
    case 'audio_format':
      return `${ev.format} ch=${ev.channels} ` +
        (ev.spatialization ? `spat=${ev.spatialization}` : '');
    case 'file_player':
      return `${ev.codec} enc=${ev.encryption_scheme} ${ev.width ? `${ev.width}x${ev.height}` : ''}`;
    case 'luma_chroma':
      return `luma=${ev.luma_depth} chroma=${ev.chroma_format}`;
    default:
      return ev.raw || '';
  }
}

function renderCaptureSummary(summary) {
  const card = el('div', { class: 'card' });
  card.appendChild(el('h2', {}, 'Playback summary'));
  card.appendChild(el('div', { class: 'filename' }, `${summary.event_count} events in ${summary.duration_s.toFixed(1)}s`));

  const p = summary.playback || {};
  if (!p || Object.keys(p).length === 0) {
    card.appendChild(el('div', { class: 'warning' }, 'No playback events captured. Did TV.app play anything during the capture window?'));
    return card;
  }

  // Verdict pill
  const pills = el('div', { class: 'row', style: 'justify-content: flex-start; margin-bottom: 12px' });
  pills.appendChild(el('span', { class: 'pill ' + (p.source === 'hls' ? 'good' : p.source === 'local_file' ? 'warn' : 'neutral') },
    p.source === 'hls' ? 'Source: HLS (Apple TV+ / streaming)' : p.source === 'local_file' ? 'Source: Local file' : 'Source: unknown'));
  if (p.dolby_vision_active === true) pills.appendChild(el('span', { class: 'pill good' }, 'Dolby Vision active'));
  else if (p.dolby_vision_active === false) pills.appendChild(el('span', { class: 'pill bad' }, 'Dolby Vision NOT active'));
  if (p.audio && p.audio.is_atmos) pills.appendChild(el('span', { class: 'pill good' }, 'Atmos'));
  card.appendChild(pills);

  if (p.dv_diagnosis) {
    card.appendChild(el('div', { class: 'warning' }, p.dv_diagnosis));
  }

  // Grid
  const g = el('div', { class: 'grid' });
  if (p.decoded_fourcc) g.appendChild(kv('Decoded FourCC', p.decoded_fourcc, p.decoded_fourcc.startsWith('dv') ? 'good' : 'bad'));
  if (p.decoder) g.appendChild(kv('Decoder', p.decoder));
  if (p.decoded_resolution) g.appendChild(kv('Resolution', p.decoded_resolution));
  if (p.peak_mbps) g.appendChild(kv('HLS peak', `${p.peak_mbps} Mbps`));
  if (p.avg_mbps) g.appendChild(kv('HLS average', `${p.avg_mbps} Mbps`));
  if (p.video_fourcc) g.appendChild(kv('HLS video', p.video_fourcc));
  if (p.audio_codec) g.appendChild(kv('HLS audio', p.audio_codec));
  if (p.audio) {
    g.appendChild(kv('Audio format', p.audio.format));
    g.appendChild(kv('Audio channels', p.audio.channels));
    g.appendChild(kv('Sample rate', p.audio.sample_rate ? `${p.audio.sample_rate} Hz` : null));
    g.appendChild(kv('Spatialization', p.audio.spatialization));
    g.appendChild(kv('Atmos eligible', p.audio.spatialization_eligible));
  }
  if (p.file_player) {
    g.appendChild(kv('File codec', p.file_player.codec));
    g.appendChild(kv('Encryption scheme', p.file_player.encryption_scheme));
  }
  card.appendChild(g);

  // Raw event log
  card.appendChild(el('details', {}, el('summary', {}, `All ${summary.event_count} events`), el('pre', {}, JSON.stringify(summary.events, null, 2))));

  return card;
}
