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

function tvDecodedFourccClass(fourcc) {
  const f = (fourcc || '').toLowerCase();
  if (f.startsWith('dv')) return 'good';
  if (f === 'qdh1') return 'warn';
  if (f === 'hvc1') return 'bad';
  return 'neutral';
}

function audioLabel(audio) {
  if (!audio) return '—';
  const format = (audio.format || '').toLowerCase();
  const displayFormat = format === 'qc+3'
    ? 'qc+3 (Apple Dolby-like)'
    : ['ec+3', 'ec-3', 'ec3'].includes(format)
      ? `${audio.format} (E-AC-3)`
      : ['qaac', 'aacp', 'aac'].includes(format) && (audio.channels || 0) <= 2
        ? `${audio.format} (AAC fallback)`
        : audio.format;
  const parts = [
    displayFormat,
    audio.channels ? `ch=${audio.channels}` : null,
    audio.sample_rate ? `${audio.sample_rate} Hz` : null,
    audio.spatialization ? `spat=${audio.spatialization}` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(' ') : '—';
}

function audioPillClass(audio) {
  const format = (audio?.format || '').toLowerCase();
  const channels = audio?.channels || 0;
  if (['ec+3', 'ec-3', 'ec3'].includes(format) && channels >= 16) return 'good';
  if (format === 'qc+3' && channels >= 16) return 'good';
  if (channels > 2) return 'good';
  if (['qaac', 'aacp', 'aac'].includes(format) && channels <= 2) return 'neutral';
  return 'neutral';
}

function boolText(v) {
  if (v === true) return 'yes';
  if (v === false) return 'no';
  return null;
}

function capturedText(v) {
  const text = boolText(v);
  return text == null ? 'not captured' : text;
}

function activeText(v) {
  const text = boolText(v);
  return text == null ? 'not captured' : (v ? 'active' : 'inactive');
}

function rendererVerdictLabel(r) {
  if (!r) return null;
  if (r.verdict === 'app_spatial_rendering_active') return {
    text: 'App-level spatial rendering active',
    className: 'good',
  };
  if (r.verdict === 'lower_level_active_app_spatial_false') return {
    text: 'Atmos/spatial machinery active, but app-level spatial rendering flag is false',
    className: 'warn',
  };
  if (r.verdict === 'lower_level_spatialization_active') return {
    text: 'Lower-level Atmos/spatial machinery active',
    className: 'good',
  };
  return {
    text: 'No spatial renderer activity captured',
    className: 'neutral',
  };
}

function rendererMediaLabel(item) {
  if (!item) return '—';
  const parts = [
    item.format,
    item.label,
    item.channels ? `ch=${item.channels}` : null,
    item.sample_rate ? `${item.sample_rate} Hz` : null,
    item.rendering_spatial_audio == null ? null : `rendering=${boolText(item.rendering_spatial_audio)}`,
  ].filter(Boolean);
  return parts.join(' ');
}

function rendererPowerLabel(item) {
  if (!item) return '—';
  return [
    `spatialization=${boolText(item.spatialization)}`,
    `stereo upmix=${boolText(item.stereo_upmix)}`,
    `head tracking=${boolText(item.head_tracking)}`,
  ].filter(Boolean).join(', ');
}

function rendererMixerLabel(item) {
  if (!item) return '—';
  return [
    item.format,
    item.channels ? `ch=${item.channels}` : null,
    item.content_spatializable == null ? null : `spatializable=${boolText(item.content_spatializable)}`,
    item.spatialization_status != null ? `status=${item.spatialization_status}` : null,
  ].filter(Boolean).join(' ');
}

function rendererAtmosLabel(item) {
  if (!item) return '—';
  return [
    item.decoder_is_atmos == null ? null : `Atmos=${boolText(item.decoder_is_atmos)}`,
    item.decoder_oar_mode == null ? null : `OAR=${boolText(item.decoder_oar_mode)}`,
  ].filter(Boolean).join(', ');
}

// Last directory successfully resolved — passed as hint to /api/find so the
// find(1) fallback searches there first (useful for external volumes Spotlight skips).
let _lastResolvedDir = '';

function _recordDir(p) {
  if (p) _lastResolvedDir = p.includes('/') ? p.substring(0, p.lastIndexOf('/')) : '';
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

function _disambiguate(name, paths) {
  // Inline disambiguation dialog rendered into a temporary overlay
  return new Promise((resolve) => {
    const overlay = el('div', { class: 'disambig-overlay' });
    const box = el('div', { class: 'disambig-box' });
    box.appendChild(el('p', {}, `Multiple files named "${name}" found — pick one:`));
    paths.forEach((p, i) => {
      const btn = el('button', { class: 'disambig-btn', onclick: () => { overlay.remove(); resolve(p); } },
        el('span', { class: 'disambig-idx' }, String(i + 1)),
        el('span', { class: 'disambig-path' }, p),
      );
      box.appendChild(btn);
    });
    box.appendChild(el('button', { class: 'disambig-cancel', onclick: () => { overlay.remove(); resolve(null); } }, 'Cancel'));
    overlay.appendChild(box);
    document.body.appendChild(overlay);
  });
}

async function pathsFromDataTransfer(dt, multi) {
  // Try URI list first (Safari — exposes file:// URIs directly)
  const uriList = (dt.getData('text/uri-list') || dt.getData('text/plain'))
    .split('\n').map((l) => l.trim()).filter((l) => l && !l.startsWith('#'));
  if (uriList.length) {
    const paths = uriList.map((u) => u.startsWith('file://') ? decodeURIComponent(u.slice(7)) : u);
    paths.forEach(_recordDir);
    return paths;
  }
  // Fallback: File objects (Chrome on macOS) — resolve via Spotlight + find(1)
  const files = Array.from(dt.files || []);
  if (!files.length) return [];
  const resolved = await Promise.all(files.map(async (f) => {
    const url = '/api/find?name=' + encodeURIComponent(f.name) +
      (_lastResolvedDir ? '&hint=' + encodeURIComponent(_lastResolvedDir) : '');
    const res = await fetch(url).then((r) => r.json());
    if (res.paths.length === 1) { _recordDir(res.paths[0]); return res.paths[0]; }
    if (res.paths.length > 1) {
      const chosen = await _disambiguate(f.name, res.paths);
      if (chosen) _recordDir(chosen);
      return chosen;
    }
    alert(`Could not locate "${f.name}". Use Browse… or paste the full path instead.`);
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



async function loadCapabilities() {
  try {
    const caps = await get('/api/capabilities');
    const missing = [];
    for (const [k, ok] of Object.entries(caps.tools || {})) {
      if (!ok) missing.push(k);
    }
    const banner = $('#capabilities-banner');
    if (missing.length) {
      banner.hidden = false;
      banner.textContent = `Limited environment detected (${caps.platform}): missing tools: ${missing.join(', ')}.`;
    }
  } catch (_e) { }
}

loadCapabilities();

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

function compareWeightsFromUi() {
  return {
    dv_present: Number($('#w-dv-present').value || 0),
    dv_fourcc_ok: Number($('#w-dv-fourcc').value || 0),
    hdr10_plus: Number($('#w-hdr10plus').value || 0),
    atmos: Number($('#w-atmos').value || 0),
    bit_rate_mbps: Number($('#w-bitrate').value || 0),
    resolution: Number($('#w-resolution').value || 0),
    subtitles: Number($('#w-subtitles').value || 0),
  };
}

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
    const res = await api('/api/compare', { paths: Array.from(comparePaths), weights: compareWeightsFromUi() });
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
let lastEventKey = null;
let lastEventNode = null;

function setCaptureStatus(state, label) {
  const s = $('#capture-status');
  s.className = 'status ' + state;
  s.textContent = label;
}

$('#capture-start').addEventListener('click', () => {
  $('#capture-events').innerHTML = '';
  $('#capture-summary').innerHTML = '';
  captureCount = 0;
  lastEventKey = null;
  lastEventNode = null;
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
  const key = `${ev.kind}:${summary}`;
  if (lastEventNode && lastEventKey === key) {
    const count = Number(lastEventNode.dataset.count || '1') + 1;
    lastEventNode.dataset.count = String(count);
    const countNode = lastEventNode.querySelector('.event-count');
    countNode.hidden = false;
    countNode.textContent = `${count}x`;
    return;
  }
  const node = el('div', { class: 'event' },
    el('span', { class: 'kind ' + ev.kind }, ev.kind),
    summary,
    el('span', { class: 'event-count', hidden: true }, '1x'),
  );
  node.dataset.count = '1';
  const wrap = $('#capture-events');
  // Insert at top because flex-direction: column-reverse renders bottom-up
  wrap.insertBefore(node, wrap.firstChild);
  lastEventKey = key;
  lastEventNode = node;
  while (wrap.children.length > 500) wrap.removeChild(wrap.lastChild);
}

function formatEventSummary(ev) {
  switch (ev.kind) {
    case 'hls_variant':
      return [
        `${ev.width ?? 'null'}x${ev.height ?? 'null'}`,
        ev.codecs,
        ev.video_range,
        ev.peak_bps ? `peak ${(ev.peak_bps/1_000_000).toFixed(1)}Mbps` : null,
      ].filter(Boolean).join(' ');
    case 'codec_type':
      return [ev.fourcc, `(${ev.decoder || 'decoder'})`, ev.width ? `${ev.width}x${ev.height}` : null]
        .filter(Boolean).join(' ');
    case 'audio_format':
      return [
        ev.format,
        ev.decodable === true ? 'is decodable' : ev.decodable === false ? 'is not decodable' : null,
        ev.channels ? `ch=${ev.channels}` : null,
        ev.spatialization ? `spat=${ev.spatialization}` : null,
      ].filter(Boolean).join(' ');
    case 'file_player':
      return [ev.codec, ev.encryption_scheme != null ? `enc=${ev.encryption_scheme}` : null, ev.width ? `${ev.width}x${ev.height}` : null]
        .filter(Boolean).join(' ');
    case 'luma_chroma':
      return `luma=${ev.luma_depth} chroma=${ev.chroma_format}`;
    case 'renderer_hint':
      if (ev.hint === 'media_formatinfo') return rendererMediaLabel(ev);
      if (ev.hint === 'spatial_power') return rendererPowerLabel(ev);
      if (ev.hint === 'route') return ev.route;
      if (ev.hint === 'atmos_decoder_state') return rendererAtmosLabel(ev);
      if (ev.hint === 'atmos_decoder_subtype') return `decoder subtype=${ev.decoder_subtype}`;
      if (ev.hint === 'mixer_spatial_status') return rendererMixerLabel(ev);
      return ev.hint || ev.raw || '';
    default:
      return ev.raw || '';
  }
}

function _copyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).catch(() => {});
  } else {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.left = '-9999px'; ta.style.position = 'fixed';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }
}

function _flashCopied(wrap) {
  wrap.classList.add('copied');
  setTimeout(() => wrap.classList.remove('copied'), 1200);
}

function renderCaptureSummary(summary) {
  const card = el('div', { class: 'card capt-summary' });

  // header row: title + copy icon
  const hdr = el('div', { class: 'capt-summary-hdr' });
  hdr.appendChild(el('h2', {}, 'Playback summary'));

  const copyWrap = el('div', { class: 'copy-wrap' });
  const copyToast = el('span', { class: 'copy-toast' }, 'Copied');

  // icon click → copy UI-only summary
  copyWrap.appendChild(el('button', {
    class: 'copy-icon-btn',
    title: 'Copy summary',
    onclick: () => {
      _copyText(JSON.stringify({
        event_count: summary.event_count,
        duration_s: summary.duration_s,
        playback: summary.playback,
      }, null, 2));
      _flashCopied(copyWrap);
    },
    html: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7.5 3H14.6C16.84 3 17.96 3 18.816 3.436C19.569 3.819 20.181 4.431 20.564 5.184C21 6.04 21 7.16 21 9.4V16.5M6.2 21H14.3C15.42 21 15.98 21 16.408 20.782C16.784 20.59 17.09 20.284 17.282 19.908C17.5 19.48 17.5 18.92 17.5 17.8V9.7C17.5 8.58 17.5 8.02 17.282 7.592C17.09 7.216 16.784 6.91 16.408 6.718C15.98 6.5 15.42 6.5 14.3 6.5H6.2C5.08 6.5 4.52 6.5 4.092 6.718C3.716 6.91 3.41 7.216 3.218 7.592C3 8.02 3 8.58 3 9.7V17.8C3 18.92 3 19.48 3.218 19.908C3.41 20.284 3.716 20.59 4.092 20.782C4.52 21 5.08 21 6.2 21Z"/></svg>',
  }));

  // hover dropdown → copy full raw JSON
  copyWrap.appendChild(el('div', { class: 'copy-menu' },
    el('button', {
      class: 'copy-menu-item',
      onclick: () => {
        _copyText(JSON.stringify(summary, null, 2));
        _flashCopied(copyWrap);
      },
    }, 'Copy full JSON'),
  ));

  copyWrap.appendChild(copyToast);
  hdr.appendChild(copyWrap);
  card.appendChild(hdr);
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
  else if (p.dv_label) pills.appendChild(el('span', { class: 'pill warn' }, p.dv_label));
  if (p.audio && p.audio.is_atmos) pills.appendChild(el('span', { class: 'pill good' }, 'Atmos'));
  if (p.best_audio && audioLabel(p.best_audio) !== audioLabel(p.audio)) {
    pills.appendChild(el('span', { class: `pill ${audioPillClass(p.best_audio)}` }, `Best audio: ${audioLabel(p.best_audio)}`));
  }
  card.appendChild(pills);

  if (p.dv_diagnosis) {
    card.appendChild(el('div', { class: 'warning' }, p.dv_diagnosis));
  }
  if (p.capture_quality?.likely_missed_audio_init) {
    card.appendChild(el('div', { class: 'warning' }, p.capture_quality.note));
  }

  // Grid
  const g = el('div', { class: 'grid' });
  if (p.decoded_fourcc) g.appendChild(kv('Decoded FourCC', p.decoded_fourcc, tvDecodedFourccClass(p.decoded_fourcc)));
  if (p.decoder) g.appendChild(kv('Decoder', p.decoder));
  if (p.decoded_resolution) g.appendChild(kv('Resolution', p.decoded_resolution));
  if (p.peak_mbps) g.appendChild(kv('HLS peak', `${p.peak_mbps} Mbps`));
  if (p.avg_mbps) g.appendChild(kv('HLS average', `${p.avg_mbps} Mbps`));
  if (p.video_fourcc) g.appendChild(kv('HLS video', p.video_fourcc));
  if (p.audio_codec) g.appendChild(kv('HLS audio', p.audio_codec));
  if (p.audio) {
    g.appendChild(kv('Current audio', audioLabel(p.audio), audioPillClass(p.audio)));
    g.appendChild(kv('Current channels', p.audio.channels));
    g.appendChild(kv('Current sample rate', p.audio.sample_rate ? `${p.audio.sample_rate} Hz` : null));
    g.appendChild(kv('Current spatialization', p.audio.spatialization));
    g.appendChild(kv('Current Atmos eligible', p.audio.spatialization_eligible));
    if (p.audio.decodable != null) g.appendChild(kv('Decodable', p.audio.decodable ? 'yes' : 'no', p.audio.decodable ? 'good' : 'bad'));
    if (p.audio.diagnosis) g.appendChild(kv('Audio diagnosis', p.audio.diagnosis, 'warn'));
  }
  if (p.best_audio) {
    g.appendChild(kv('Best observed audio', audioLabel(p.best_audio), audioPillClass(p.best_audio)));
    if (p.audio && audioLabel(p.best_audio) !== audioLabel(p.audio)) {
      g.appendChild(kv('Audio event note', 'Current audio is the latest event; best observed audio is the strongest path seen during capture.'));
    }
  }
  if (p.file_player) {
    g.appendChild(kv('File codec', p.file_player.codec));
    g.appendChild(kv('Encryption scheme', p.file_player.encryption_scheme));
  }
  if (p.capture_quality) {
    g.appendChild(kv('Capture quality', p.capture_quality.label, p.capture_quality.likely_missed_audio_init ? 'warn' : 'neutral'));
  }
  card.appendChild(g);

  if (p.observed_audio && p.observed_audio.length) {
    card.appendChild(el('h3', {}, 'Observed audio formats'));
    const list = el('div', { class: 'audio-observed' });
    p.observed_audio.forEach((audio) => {
      list.appendChild(el('div', { class: 'audio-observed-item' },
        el('span', { class: `pill ${audioPillClass(audio)}` }, audioLabel(audio)),
        audio.count > 1 ? el('span', { class: 'event-count' }, `${audio.count}x`) : null,
      ));
    });
    card.appendChild(list);
  }

  if (p.renderer_evidence) {
    card.appendChild(el('h3', {}, 'Spatial renderer evidence'));
    const r = p.renderer_evidence;
    const verdict = rendererVerdictLabel(r);
    if (verdict) {
      card.appendChild(el('div', { class: `renderer-verdict ${verdict.className}` }, verdict.text));
    }
    const rg = el('div', { class: 'grid' });
    if (r.routes?.length) rg.appendChild(kv('Output route', r.routes.join(', ')));
    rg.appendChild(kv('Route capability', r.route_capability_label || 'not captured'));
    rg.appendChild(kv('App spatial rendering ever true', capturedText(r.app_spatial_rendering_ever_true), r.app_spatial_rendering_ever_true ? 'good' : 'neutral'));
    rg.appendChild(kv('App spatial rendering last state', capturedText(r.app_spatial_rendering_last_state), r.app_spatial_rendering_last_state ? 'good' : 'neutral'));
    rg.appendChild(kv('Lower-level spatialization', activeText(r.lower_level_spatialization_active), r.lower_level_spatialization_active ? 'good' : 'neutral'));
    rg.appendChild(kv('Spatial power', activeText(r.spatial_power_active), r.spatial_power_active ? 'good' : 'neutral'));
    rg.appendChild(kv('Head tracking', activeText(r.head_tracking_active), r.head_tracking_active ? 'good' : 'neutral'));
    rg.appendChild(kv('Atmos decoder', activeText(r.atmos_decoder_active), r.atmos_decoder_active ? 'good' : 'neutral'));
    rg.appendChild(kv('OAR mode', activeText(r.oar_mode_active), r.oar_mode_active ? 'good' : 'neutral'));
    rg.appendChild(kv('Mixer spatializable', capturedText(r.mixer_content_spatializable), r.mixer_content_spatializable ? 'good' : 'neutral'));
    if (r.mixer_spatialization_statuses?.length) rg.appendChild(kv('Mixer spatialization statuses', r.mixer_spatialization_statuses.join(', ')));
    if (r.media_formatinfo?.length) {
      r.media_formatinfo.forEach((item, index) => {
        rg.appendChild(kv(index ? 'App spatial flag' : 'App spatial flag', rendererMediaLabel(item), item.rendering_spatial_audio ? 'good' : 'neutral'));
      });
    }
    if (r.spatial_power?.length) {
      r.spatial_power.forEach((item) => {
        rg.appendChild(kv('Spatial power state', rendererPowerLabel(item), item.spatialization ? 'good' : 'neutral'));
      });
    }
    if (r.prefers_head_tracked_spatialization?.length) {
      rg.appendChild(kv('Prefers head tracking', r.prefers_head_tracked_spatialization.map(boolText).join(', ')));
    }
    if (r.atmos_decoder_states?.length) {
      r.atmos_decoder_states.forEach((item) => {
        rg.appendChild(kv('Atmos decoder', rendererAtmosLabel(item), item.decoder_is_atmos ? 'good' : 'neutral'));
      });
    }
    if (r.decoder_subtypes?.length) rg.appendChild(kv('Decoder subtype', r.decoder_subtypes.join(', ')));
    if (r.mixer_spatial_status?.length) {
      r.mixer_spatial_status.forEach((item) => {
        rg.appendChild(kv('Mixer spatial status', rendererMixerLabel(item), item.content_spatializable ? 'good' : 'neutral'));
      });
    }
    if (r.spatial_rendering_changed_count) rg.appendChild(kv('Spatial rendering changes', r.spatial_rendering_changed_count));
    if (r.observed_hints?.length) rg.appendChild(kv('Renderer hint types', r.observed_hints.join(', ')));
    card.appendChild(rg);
  }

  // Raw event log
  card.appendChild(el('details', {}, el('summary', {}, `All ${summary.event_count} events`), el('pre', {}, JSON.stringify(summary.events, null, 2))));

  return card;
}
