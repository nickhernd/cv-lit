/* ═══════════════════════════════════════════════════════
   Calibración — lógica de frontend (vanilla JS)
   Llama a /api/calib/* (ver backend/calibration_api.py)
   ═══════════════════════════════════════════════════════ */

const API_BASE = '/api/calib';

/* ---- Estado del wizard en memoria ---- */
const wizardState = {
  cameraId: null,
  gcps: [],            // [{id, x, y, z}]
  photos: [],          // [{id, file, url, gx, gy, dx, dy, residual}]
  marks: {},           // { stakeId: [{photoId, u, v}] }
  homography: null,    // {H, rmse, inliers}
  profileName: null,
};

const STEP_LABELS = ['Varillas', 'Fotos', 'Marcar', 'Validar', 'Guardar'];

function renderStepper(current) {
  const el = document.getElementById('stepper');
  if (!el) return;
  el.innerHTML = STEP_LABELS.map((label, i) => {
    const cls = i < current ? 'done' : i === current ? 'active' : '';
    const connector = i < STEP_LABELS.length - 1 ? '<div class="connector"></div>' : '';
    return `<div class="step ${cls}"><div class="dot">${i < current ? '✓' : i + 1}</div><span>${label}</span></div>${connector}`;
  }).join('');
}

/* ═════════ API calls (fetch wrappers) ═════════ */

async function apiImportGcps(cameraId, file) {
  // TODO: POST multipart/form-data to /api/calib/{cameraId}/gcps/import
  // Returns: [{id, x, y, z}]
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch(`${API_BASE}/${cameraId}/gcps/import`, { method: 'POST', body: fd });
  return res.json();
}

async function apiUploadPhotos(cameraId, files) {
  // TODO: POST photos, backend registers each against cameras/{id}/reference.jpg
  // Returns: [{id, url, gx, gy, dx, dy, residual}]
  const fd = new FormData();
  files.forEach(f => fd.append('photos', f));
  const res = await fetch(`${API_BASE}/${cameraId}/photos`, { method: 'POST', body: fd });
  return res.json();
}

async function apiUploadMetadata(cameraId, file) {
  // TODO: POST Gx/Gy/temp CSV, backend joins by timestamp with uploaded photos
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch(`${API_BASE}/${cameraId}/photos/metadata`, { method: 'POST', body: fd });
  return res.json();
}

async function apiSaveMark(cameraId, stakeId, photoId, u, v) {
  // TODO: POST a single pixel<->GCP correspondence
  const res = await fetch(`${API_BASE}/${cameraId}/marks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stake_id: stakeId, photo_id: photoId, u, v }),
  });
  return res.json();
}

async function apiDeleteMark(cameraId, stakeId, photoId) {
  // TODO: DELETE a correspondence
  return fetch(`${API_BASE}/${cameraId}/marks/${stakeId}/${photoId}`, { method: 'DELETE' });
}

async function apiComputeHomography(cameraId, excludedPairs = []) {
  // TODO: POST -> backend runs cv2.findHomography with RANSAC over all marks
  // Returns: {H: [[...]], rmse, inliers, residuals: [{stake_id, photo_id, residual}]}
  const res = await fetch(`${API_BASE}/${cameraId}/homography/compute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ excluded: excludedPairs }),
  });
  return res.json();
}

async function apiSaveProfile(cameraId, meta) {
  // TODO: POST -> persists profiles/{cameraId}/<date>/ (profile.json, H_matrix.npy, gcps.csv, report.pdf)
  const res = await fetch(`${API_BASE}/${cameraId}/profile/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(meta),
  });
  return res.json();
}

async function apiGetReferenceFrame(cameraId) {
  // TODO: GET cameras/{id}/reference.jpg metadata + URL
  const res = await fetch(`${API_BASE.replace('/calib', '/cameras')}/${cameraId}/reference`);
  return res.json();
}

/* ═════════ Step renderers ═════════ */

function renderStep1() {
  const tpl = document.getElementById('tpl-step-1').content.cloneNode(true);
  document.getElementById('screen-root').replaceChildren(tpl);
  renderStepper(0);
  document.getElementById('gcp-file-input').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    wizardState.gcps = await apiImportGcps(wizardState.cameraId, file);
    renderGcpPreview(wizardState.gcps);
  });
}

function renderGcpPreview(gcps) {
  const tbody = document.querySelector('#gcp-preview-table tbody');
  tbody.innerHTML = gcps.map(g => `<tr><td>${g.id}</td><td>${g.x.toFixed(2)}</td><td>${g.y.toFixed(2)}</td><td>${(g.z ?? 0).toFixed(1)}</td></tr>`).join('');
}

function renderStep2() {
  const tpl = document.getElementById('tpl-step-2').content.cloneNode(true);
  document.getElementById('screen-root').replaceChildren(tpl);
  renderStepper(1);

  apiGetReferenceFrame(wizardState.cameraId).then(ref => {
    document.getElementById('reference-frame-preview').innerHTML =
      `<img src="${ref.url}" style="max-width:200px;border-radius:4px"><div class="label" style="margin-top:6px">${ref.path}</div>`;
  });

  document.getElementById('photos-input').addEventListener('change', async (e) => {
    wizardState.photos = await apiUploadPhotos(wizardState.cameraId, Array.from(e.target.files));
    renderPhotoGrid(wizardState.photos);
  });
  document.getElementById('metadata-input').addEventListener('change', async (e) => {
    wizardState.photos = await apiUploadMetadata(wizardState.cameraId, e.target.files[0]);
    renderPhotoGrid(wizardState.photos);
  });
}

function renderPhotoGrid(photos) {
  const grid = document.getElementById('photo-grid');
  grid.innerHTML = photos.map(p => `
    <div class="card" data-photo-id="${p.id}">
      <img src="${p.url}" style="width:100%;border-radius:4px">
      <div style="display:flex;justify-content:space-between;margin-top:6px;font-size:11px">
        <span>${p.id}</span>
        <span class="badge ${Math.hypot(p.dx, p.dy) > 18 ? 'badge-warn' : 'badge-ok'}">
          Δ ${Math.hypot(p.dx, p.dy).toFixed(0)} px
        </span>
      </div>
    </div>`).join('');
}

function renderStep3() {
  const tpl = document.getElementById('tpl-step-3').content.cloneNode(true);
  document.getElementById('screen-root').replaceChildren(tpl);
  renderStepper(2);
  initMarkerCanvas();
}

/* Canvas-based point marking: click image -> capture (u,v) -> POST mark */
function initMarkerCanvas() {
  const img = document.getElementById('marker-image');
  const canvas = document.getElementById('marker-overlay');
  let currentStakeId = null; // TODO: set from stake-list selection
  let currentPhotoId = null; // TODO: set from photo-list selection

  canvas.addEventListener('click', async (e) => {
    if (!currentStakeId || !currentPhotoId) return;
    const rect = canvas.getBoundingClientRect();
    // Convert click position to native image pixel coords (u, v)
    const scaleX = img.naturalWidth / rect.width;
    const scaleY = img.naturalHeight / rect.height;
    const u = Math.round((e.clientX - rect.left) * scaleX);
    const v = Math.round((e.clientY - rect.top) * scaleY);
    await apiSaveMark(wizardState.cameraId, currentStakeId, currentPhotoId, u, v);
    drawMarkers(); // TODO: re-render markers from wizardState.marks
  });
}

function drawMarkers() {
  // TODO: draw all current photo's marks as .gcp-marker positioned divs, or canvas 2d drawing
}

function renderStep4() {
  const tpl = document.getElementById('tpl-step-4').content.cloneNode(true);
  document.getElementById('screen-root').replaceChildren(tpl);
  renderStepper(3);
  computeAndRenderHomography([]);
}

async function computeAndRenderHomography(excluded) {
  const result = await apiComputeHomography(wizardState.cameraId, excluded);
  wizardState.homography = result;
  document.getElementById('homography-stats').innerHTML = `
    <div class="card"><div class="stat-val">${result.rmse.toFixed(2)} px</div><div class="stat-label">RMSE total</div></div>
    <div class="card"><div class="stat-val">${result.inliers}/${result.residuals.length}</div><div class="stat-label">Inliers RANSAC</div></div>
    <div class="card"><div class="stat-val">${result.det_h?.toFixed(3) ?? '—'}</div><div class="stat-label">det(H)</div></div>`;
  const tbody = document.querySelector('#correspondence-table tbody');
  tbody.innerHTML = result.residuals.map(r => `
    <tr><td><input type="checkbox" data-stake="${r.stake_id}" data-photo="${r.photo_id}"></td>
    <td>${r.stake_id}</td><td>${r.photo_id}</td><td>${r.u}</td><td>${r.v}</td>
    <td>${r.x.toFixed(2)}</td><td>${r.y.toFixed(2)}</td>
    <td style="color:${r.residual > 0.4 ? 'var(--warn)' : 'inherit'}">${r.residual.toFixed(2)}</td></tr>`).join('');
}

function renderStep5() {
  const tpl = document.getElementById('tpl-step-5').content.cloneNode(true);
  document.getElementById('screen-root').replaceChildren(tpl);
  renderStepper(4);
  document.getElementById('btn-save-profile').addEventListener('click', async () => {
    const name = document.getElementById('profile-name').value;
    const notes = document.getElementById('profile-notes').value;
    const saved = await apiSaveProfile(wizardState.cameraId, { name, notes, homography: wizardState.homography });
    // TODO: navigate to overview / show confirmation with saved.profile_path
  });
}

/* ═════════ Cámaras: overview, detalle, bloqueo, lente ═════════
   Estas viven bajo el nav "Cámaras" salvo overview/blocked que son
   la entrada al flujo de "Calibración" (homografía). */

async function apiGetCameraOverview() {
  // TODO: GET lista de cámaras con estado {id, name, calibrated, rmse, gcps, lens_ok}
  const res = await fetch(`${API_BASE}/overview`);
  return res.json();
}

async function apiGetCameraDetail(cameraId) {
  // TODO: GET info general + ROI + lens + reference + lista de perfiles
  const res = await fetch(`${API_BASE.replace('/calib', '/cameras')}/${cameraId}`);
  return res.json();
}

function setScreenTitle(title, sub) {
  document.getElementById('screen-title').textContent = title;
  document.getElementById('screen-sub').textContent = sub;
}

function setTopbarActions(buttonsHtml) {
  document.getElementById('topbar-actions').innerHTML = buttonsHtml;
}

async function renderOverview() {
  setScreenTitle('Calibración geométrica', 'Estado por cámara · Módulo offline');
  setTopbarActions('<button class="btn btn-primary" id="btn-new-calib">+ Nueva calibración</button>');
  const tpl = document.getElementById('tpl-overview').content.cloneNode(true);
  document.getElementById('screen-root').replaceChildren(tpl);

  let cameras = [];
  try {
    cameras = await apiGetCameraOverview();
  } catch (err) {
    console.warn('Backend no disponible (overview):', err);
    document.getElementById('overview-table-body').innerHTML =
      '<tr><td colspan="6" style="text-align:center;color:var(--text3)">Backend no disponible — datos de ejemplo no cargados</td></tr>';
    return;
  }

  document.getElementById('ov-calibrated').textContent = `${cameras.filter(c => c.calibrated).length} / ${cameras.length}`;
  const rmses = cameras.filter(c => c.rmse != null).map(c => c.rmse);
  document.getElementById('ov-rmse').textContent = rmses.length ? `${(rmses.reduce((a, b) => a + b, 0) / rmses.length).toFixed(2)} px` : '—';
  document.getElementById('ov-gcps').textContent = cameras.reduce((sum, c) => sum + (c.gcps || 0), 0);

  document.getElementById('overview-table-body').innerHTML = cameras.map(c => `
    <tr>
      <td>${c.id}</td>
      <td><span class="badge ${c.calibrated ? 'badge-ok' : 'badge-warn'}">${c.calibrated ? 'Calibrada' : 'Sin calibrar'}</span></td>
      <td>${c.last_calibration || '—'}</td>
      <td>${c.rmse != null ? c.rmse.toFixed(2) + ' px' : '—'}</td>
      <td>${c.gcps ?? '—'}</td>
      <td><button class="btn btn-secondary" data-start-calib="${c.id}">${c.calibrated ? 'Editar' : 'Iniciar'}</button></td>
    </tr>`).join('');

  document.getElementById('overview-table-body').addEventListener('click', (e) => {
    const camId = e.target.dataset.startCalib;
    if (!camId) return;
    startCalibrationFlow(camId);
  });
}

async function startCalibrationFlow(cameraId) {
  wizardState.cameraId = cameraId;
  let lens = false;
  try {
    lens = await pipelineHasLens(cameraId);
  } catch (err) {
    console.warn('Backend no disponible (lens check):', err);
  }
  if (!lens) {
    renderBlocked(cameraId);
    return;
  }
  renderStep1();
}

async function pipelineHasLens(cameraId) {
  // TODO: GET /api/cameras/{id} y comprobar lens != null
  const detail = await apiGetCameraDetail(cameraId);
  return !!detail.lens;
}

function renderBlocked(cameraId) {
  setScreenTitle(`Calibrar · Cámara ${cameraId}`, 'Requisito previo no cumplido');
  setTopbarActions('<button class="btn btn-secondary" id="btn-cancel-blocked">Cancelar</button>');
  const tpl = document.getElementById('tpl-blocked').content.cloneNode(true);
  document.getElementById('screen-root').replaceChildren(tpl);
  document.getElementById('btn-goto-lens').addEventListener('click', () => renderLensCalibration(cameraId));
  document.getElementById('btn-import-lens').addEventListener('click', () => {
    // TODO: abrir selector de perfiles de lente compartidos (shared/lens_models/)
  });
}

/* ─ Cámaras > Detalle (hardware: info, ROI, lente, referencia, perfiles) ─ */

async function renderCameraDetail(cameraId) {
  setScreenTitle(`Cámara ${cameraId}`, 'Configuración hardware · Lente, ROI, ubicación');
  setTopbarActions('<button class="btn btn-primary" id="btn-save-camera">Guardar cambios</button>');
  const tpl = document.getElementById('tpl-camera-detail').content.cloneNode(true);
  document.getElementById('screen-root').replaceChildren(tpl);

  let detail;
  try {
    detail = await apiGetCameraDetail(cameraId);
  } catch (err) {
    console.warn('Backend no disponible (camera detail):', err);
    document.getElementById('screen-root').innerHTML =
      '<div class="card" style="text-align:center;color:var(--text3)">Backend no disponible — no se pudo cargar el detalle de la cámara</div>';
    return;
  }

  document.getElementById('camera-info-fields').innerHTML = Object.entries(detail.info || {})
    .map(([k, v]) => `<div><div class="label">${k}</div><input class="input" value="${v}" readonly></div>`).join('');

  document.getElementById('roi-preview').innerHTML = detail.roi
    ? `<div class="label">${detail.roi.vertices?.length ?? 0} vértices</div>`
    : '<div class="label">Sin ROI definida</div>';

  if (detail.lens) {
    document.getElementById('lens-params').innerHTML = Object.entries(detail.lens)
      .filter(([k]) => k !== 'method')
      .map(([k, v]) => `<div><div class="label">${k}</div><div style="font-family:var(--mono)">${v}</div></div>`).join('');
    document.getElementById('lens-path').textContent = `cameras/${cameraId}/lens.json`;
  } else {
    document.getElementById('lens-params').innerHTML = '<div class="badge badge-warn">Sin calibrar</div>';
  }

  document.getElementById('reference-frame-detail').innerHTML = detail.reference
    ? `<img src="${detail.reference.url}" style="max-width:180px;border-radius:4px"><div class="label" style="margin-top:6px">cameras/${cameraId}/reference.jpg</div>`
    : '<div class="label">Sin fijar</div>';

  document.getElementById('camera-profiles-body').innerHTML = (detail.profiles || []).map(p => `
    <tr><td>${p.date}</td><td>${p.rmse.toFixed(2)} px</td><td>${p.gcps}</td>
    <td>${p.active ? '<span class="badge badge-ok">activo</span>' : `<button class="btn btn-ghost" data-activate="${p.date}">Activar</button>`}</td></tr>`).join('');

  document.getElementById('btn-recalibrate-lens').addEventListener('click', () => renderLensCalibration(cameraId));
  document.getElementById('btn-change-reference').addEventListener('click', () => {
    // TODO: abrir selector de fotos recientes para fijar nueva referencia -> apiSetReferenceFrame
  });
}

/* ─ Cámaras > Calibrar lente (líneas rectas, tarea única por cámara) ─ */

const LENS_METHODS = [
  { id: 'plumb', title: 'Líneas rectas', recommended: true },
  { id: 'gcp', title: 'Auto desde varillas' },
  { id: 'manual', title: 'Manual' },
  { id: 'import', title: 'Importar perfil' },
  { id: 'none', title: 'Sin corrección' },
];

function renderLensCalibration(cameraId) {
  setScreenTitle(`Calibrar lente · Cámara ${cameraId}`, 'Estimación de parámetros intrínsecos · tarea única por cámara');
  setTopbarActions('<button class="btn btn-secondary" id="btn-cancel-lens">Cancelar</button> <button class="btn btn-primary" id="btn-save-lens-top">Guardar lens.json</button>');
  const tpl = document.getElementById('tpl-lens-calib').content.cloneNode(true);
  document.getElementById('screen-root').replaceChildren(tpl);

  document.getElementById('lens-method-list').innerHTML = LENS_METHODS.map(m => `
    <div class="card" data-method="${m.id}" style="cursor:pointer;margin-bottom:6px">
      ${m.title}${m.recommended ? ' <span class="badge badge-ok">Recomendado</span>' : ''}
    </div>`).join('');

  initLensLineCanvas(cameraId);

  document.getElementById('btn-add-line').addEventListener('click', () => {
    // TODO: activar modo "dibujar línea" en el canvas; al soltar, POST a lines locales
  });
  document.getElementById('btn-reestimate-lens').addEventListener('click', async () => {
    // TODO: llamar apiEstimateLens(cameraId, lines) y refrescar lens-estimated-params
  });
  document.getElementById('btn-save-lens').addEventListener('click', () => saveLensProfile(cameraId));
}

function initLensLineCanvas(cameraId) {
  // TODO: cargar cameras/{cameraId}/reference.jpg en #lens-image,
  // permitir click-drag para trazar líneas sobre #lens-overlay, acumular en un array local.
}

async function apiEstimateLens(cameraId, lines) {
  // TODO: POST /api/cameras/{cameraId}/lens/estimate {lines} -> {k1,k2,p1,p2,fx,fy,cx,cy, residual}
  const res = await fetch(`${API_BASE.replace('/calib', '/cameras')}/${cameraId}/lens/estimate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lines }),
  });
  return res.json();
}

async function saveLensProfile(cameraId) {
  // TODO: POST /api/cameras/{cameraId}/lens (persist lens.json) y volver a renderCameraDetail
}

/* ═════════ Init / navegación del sidebar ═════════ */

function wireSidebarNav() {
  document.querySelectorAll('.sidebar-item[data-nav]').forEach(item => {
    item.addEventListener('click', () => {
      document.querySelectorAll('.sidebar-item').forEach(i => i.classList.remove('active'));
      item.classList.add('active');
      const nav = item.dataset.nav;
      if (nav === 'calibracion') renderOverview();
      if (nav === 'camaras') renderCameraDetail(wizardState.cameraId || 'C4');
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  wireSidebarNav();
  renderOverview(); // entry point
});
