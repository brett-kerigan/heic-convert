const state = { items: [], format: "png", quality: 95, resize: 0 };

const IMAGE_RE = /\.(heic|heif|jpe?g|png|webp)$/i;
const ZIP_RE = /\.zip$/i;
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));

const dz = $("#dropzone"), input = $("#file-input"), gallery = $("#gallery");
const controls = $("#controls"), actions = $("#actions"), statusEl = $("#status"), ioHint = $("#io-hint");
const qWrap = $("#quality-wrap"), qInput = $("#quality"), qVal = $("#quality-val");
const convertBtn = $("#convert-btn"), scrubBtn = $("#scrub-btn"), countEl = $("#count"), openFolderBtn = $("#open-folder-btn");
const selectToggleBtn = $("#select-toggle");

let _idc = 0; const uid = () => `f${++_idc}`;
function setStatus(m, working){ statusEl.textContent = m || ""; statusEl.classList.toggle("working", !!(m && working)); }

async function extractZip(zipFile){
  const zip = await JSZip.loadAsync(zipFile); const files = []; let skipped = 0;
  for (const entry of Object.values(zip.files)){
    if (entry.dir) continue;
    const base = entry.name.split(/[\\/]/).pop();
    if (!base || base.startsWith(".")) continue;
    if (IMAGE_RE.test(base)){
      const blob = await entry.async("blob");
      files.push(new File([blob], base, { type: blob.type || "application/octet-stream" }));
    } else skipped++;
  }
  return { files, skipped };
}

dz.addEventListener("click", () => input.click());
dz.addEventListener("keydown", (e) => { if (e.key==="Enter"||e.key===" ") input.click(); });
input.addEventListener("change", () => addFiles(input.files));
["dragenter","dragover"].forEach((ev)=>dz.addEventListener(ev,(e)=>{e.preventDefault();dz.classList.add("drag");}));
["dragleave","drop"].forEach((ev)=>dz.addEventListener(ev,(e)=>{e.preventDefault();dz.classList.remove("drag");}));
dz.addEventListener("drop",(e)=>addFiles(e.dataTransfer.files));

async function addFiles(fileList){
  const all = [...fileList];
  let images = all.filter((f)=>IMAGE_RE.test(f.name));
  const zips = all.filter((f)=>ZIP_RE.test(f.name));
  let skipped = 0;
  for (const z of zips){
    setStatus(`Reading ${z.name}`, true);
    try { const r = await extractZip(z); images = images.concat(r.files); skipped += r.skipped; }
    catch(e){ setStatus(`Could not read ${z.name}: ${e.message}`); }
  }
  if (!images.length){ setStatus("No HEIC/JPG/PNG/WEBP images found." + (skipped?` (skipped ${skipped})`:"")); return; }
  const fd = new FormData();
  images.forEach((f)=>fd.append("files", f));
  setStatus(`Generating previews for ${images.length} image(s)`, true);
  const res = await fetch("/preview", { method:"POST", body:fd });
  if (!res.ok){ setStatus("Preview failed: server error " + res.status); return; }
  const { previews } = await res.json();
  previews.forEach((p,i)=>{
    state.items.push({
      id: uid(), file: images[i], name: p.name, ok: p.ok, preview: p.preview,
      error: p.error, edit: { crop:null, rotate:0, flipH:false }, thumb:null, dims:null,
      selected: true,
    });
  });
  render();
  setStatus(skipped ? `Added ${previews.length}; skipped ${skipped} non-image file(s).` : "");
}

function dimsFor(it, cb){
  if (!it.ok || !it.preview || it.dims){ cb(); return; }
  const im = new Image();
  im.onload = () => { it.dims = `${im.naturalWidth}×${im.naturalHeight}`; cb(); };
  im.onerror = cb; im.src = it.preview;
}

function render(){
  const has = state.items.length > 0;
  controls.hidden = !has; actions.hidden = !has; if (ioHint) ioHint.hidden = !has;
  const okCount = state.items.filter(x=>x.ok).length;
  const okSelected = state.items.filter(x=>x.ok && x.selected).length;
  countEl.textContent = has ? `${okSelected} of ${okCount} selected` : "";
  if (selectToggleBtn){
    selectToggleBtn.hidden = !okCount;
    selectToggleBtn.textContent = (okCount>0 && okSelected===okCount) ? "Select none" : "Select all";
  }
  gallery.innerHTML = "";
  for (const it of state.items){
    const card = document.createElement("div");
    if (it.ok){
      card.className = "card ok" + (it.selected ? " selected" : "");
      const tags = [];
      if (it.edit.crop) tags.push('<span class="badge">▣ cropped</span>');
      if (it.edit.rotate) tags.push(`<span class="badge">⟳${it.edit.rotate}°</span>`);
      if (it.edit.flipH) tags.push('<span class="badge">⇋ flip</span>');
      // A cropped thumb already has rotation/flip baked in (Task 10); only the raw
      // preview needs the CSS transform, else it double-rotates.
      const tf = it.thumb ? "" : `transform:scaleX(${it.edit.flipH?-1:1}) rotate(${it.edit.rotate}deg)`;
      card.innerHTML =
        `<button class="sel" type="button" aria-pressed="${it.selected?"true":"false"}" aria-label="Toggle selection">${it.selected?"✓":"○"}</button>
         <div class="ph"><img src="${it.thumb||it.preview}" alt="" style="${tf}"></div>
         <div class="nm">${esc(it.name)}</div>
         <div class="dim">${it.dims||""} ${tags.join(" ")}</div>`;
      card.querySelector(".sel").onclick = (e) => {
        e.stopPropagation(); it.selected = !it.selected; render();
      };
      card.querySelector(".ph").onclick = () => openPreview(it.id);
      dimsFor(it, ()=>{ const d = card.querySelector(".dim"); if (d) d.innerHTML = `${it.dims||""} ${tags.join(" ")}`; });
    } else {
      card.className = "card";
      card.innerHTML = `<div class="ph"></div><div class="nm">${esc(it.name)}</div>
        <div class="err">${esc(it.error||"failed")}</div>
        <div class="acts"><button data-act="rm">✕ remove</button></div>`;
      card.querySelector('[data-act="rm"]').onclick = () => { state.items = state.items.filter(x=>x.id!==it.id); render(); };
    }
    gallery.appendChild(card);
  }
  const anySelected = state.items.some(x=>x.ok && x.selected);
  if (convertBtn) convertBtn.disabled = !anySelected;
  if (scrubBtn) scrubBtn.disabled = !anySelected;
}

// format / quality / resize controls
document.querySelectorAll(".seg-btn").forEach((b)=>b.addEventListener("click",()=>{
  document.querySelectorAll(".seg-btn").forEach(x=>x.classList.remove("is-active"));
  b.classList.add("is-active"); state.format = b.dataset.fmt;
  qWrap.hidden = !(state.format==="jpg"||state.format==="webp");
}));
qInput.addEventListener("input",()=>{ state.quality=+qInput.value; qVal.textContent=qInput.value; });
document.querySelectorAll("#resize-group .chip").forEach((b)=>b.addEventListener("click",()=>{
  document.querySelectorAll("#resize-group .chip").forEach(x=>x.classList.remove("on"));
  b.classList.add("on"); state.resize = +b.dataset.resize;
}));

// per-file convert loop + block progress bar + client-side zip
const progress = $("#progress"), progressBar = $("#progress-bar"), progressLabel = $("#progress-label");

function renderBar(done, total, label){
  const width = 28, filled = total ? Math.round((done/total)*width) : 0;
  progressBar.innerHTML =
    `[<span class="bar-fill">${"█".repeat(filled)}</span><span class="bar-empty">${"░".repeat(width-filled)}</span>] ` +
    `${Math.round((done/total)*100)}%`;
  progressLabel.textContent = `${label}  ${String(done).padStart(2,"0")} / ${total}`;
}

async function convertOne(it, mode){
  const fd = new FormData();
  fd.append("files", it.file, it.name);
  fd.append("format", mode === "scrub" ? "scrub" : state.format);
  fd.append("quality", String(state.quality));
  fd.append("resize", String(mode === "scrub" ? 0 : state.resize));
  fd.append("edits", JSON.stringify({ [it.name]: it.edit }));
  const res = await fetch("/convert", { method:"POST", body:fd });
  if (!res.ok) throw new Error("server error " + res.status);
  const blob = await res.blob();
  if (blob.type === "application/zip") {
    // We send exactly one file per request, so a zip response is only ever the
    // server's "0 results" failure case (a zip of just errors.txt) — treat as failure.
    throw new Error("conversion failed");
  }
  const cd = res.headers.get("Content-Disposition") || "";
  const m = cd.match(/filename="([^"]+)"/);
  return { name: m ? m[1] : it.name, blob };
}

function downloadBlob(blob, filename){
  const url = URL.createObjectURL(blob); const a = document.createElement("a");
  a.href = url; a.download = filename; document.body.appendChild(a); a.click();
  a.remove(); URL.revokeObjectURL(url);
}

// Native desktop app exposes a save bridge; a plain browser (self-host) does not.
const nativeApi = () => (window.pywebview && window.pywebview.api) || null;
function blobToB64(blob){
  return new Promise((resolve, reject)=>{
    const r = new FileReader();
    r.onload = ()=> resolve(String(r.result).split(",", 2)[1] || "");
    r.onerror = ()=> reject(new Error("read failed"));
    r.readAsDataURL(blob);
  });
}
let lastSavedPath = null;
function showSaved(path){ lastSavedPath = path; if (openFolderBtn) openFolderBtn.hidden = false; }
function hideSaved(){ lastSavedPath = null; if (openFolderBtn) openFolderBtn.hidden = true; }
if (openFolderBtn) openFolderBtn.addEventListener("click", ()=>{
  const api = nativeApi();
  if (api && api.open_path && lastSavedPath) api.open_path(lastSavedPath);
});

function uniqueName(name, used){
  if (!used.has(name)){ used.add(name); return name; }
  const i = name.lastIndexOf(".");
  const stem = i < 0 ? name : name.slice(0, i);
  const ext  = i < 0 ? "" : name.slice(i);
  let n = 1, candidate;
  do { candidate = `${stem}_${n}${ext}`; n++; } while (used.has(candidate));
  used.add(candidate);
  return candidate;
}

async function convertAll(mode){
  const good = state.items.filter(x=>x.ok && x.selected);
  if (!good.length) return;
  const label = mode === "scrub" ? "SCRUBBING" : "CONVERTING";
  const donePrefix = mode === "scrub" ? "Metadata scrubbed" : "Done";
  const doneVerb = mode === "scrub" ? "scrubbed" : "converted";
  const zipName = mode === "scrub" ? "scrubbed.zip" : "converted.zip";
  convertBtn.disabled = true; progress.hidden = false; hideSaved();
  const outs = [], errors = []; let done = 0; renderBar(0, good.length, label);
  for (const it of good){
    try { outs.push(await convertOne(it, mode)); }
    catch(e){ errors.push(`${it.name}: ${e.message}`); }
    renderBar(++done, good.length, label);
  }
  try {
    const api = nativeApi();
    if (api && api.save_file){
      // Native desktop app: save through OS dialogs, no zip.
      if (outs.length === 1){
        const r = await api.save_file(outs[0].name, await blobToB64(outs[0].blob));
        if (r && r.ok){ setStatus(`${donePrefix} — saved → ${r.path}`); showSaved(r.path); }
        else if (r && r.cancelled){ setStatus("Save cancelled."); }
        else { setStatus("Save failed" + (r && r.error ? `: ${r.error}` : "") + "."); }
      } else if (outs.length){
        const folder = await api.choose_folder();
        if (!folder){ setStatus("Save cancelled."); }
        else {
          let saved = 0;
          for (const o of outs){
            await api.save_into(folder, o.name, await blobToB64(o.blob));
            setStatus(`Saving ${++saved} / ${outs.length}`, true);
          }
          setStatus(`${donePrefix} — ${saved} ${doneVerb} → ${folder}${errors.length?`, ${errors.length} failed`:""}.`);
          showSaved(folder);
        }
      } else {
        setStatus(`All ${errors.length} failed.`);
      }
    } else if (outs.length === 1 && !errors.length){
      downloadBlob(outs[0].blob, outs[0].name);
      setStatus(donePrefix + " — downloaded " + outs[0].name);
    } else if (outs.length || errors.length){
      const zip = new JSZip(); const used = new Set();
      for (const o of outs) zip.file(uniqueName(o.name, used), o.blob);
      if (errors.length) zip.file("errors.txt", errors.join("\n") + "\n");
      const zblob = await zip.generateAsync({ type:"blob" });
      downloadBlob(zblob, zipName);
      setStatus(`${donePrefix} — ${outs.length} ${doneVerb}${errors.length?`, ${errors.length} failed`:""}.`);
    }
  } finally {
    convertBtn.disabled = false;
    setTimeout(()=>{ progress.hidden = true; }, 1200);
  }
}

convertBtn.addEventListener("click", () => convertAll("format"));

const modal = $("#crop-modal"), cropImg = $("#crop-img"), cropName = $("#crop-name");
let cropper = null, activeCropId = null, lastCropTrigger = null;
let cropBusy = false;

const previewModal = $("#preview-modal"), previewImg = $("#preview-img"), previewName = $("#preview-name");
let activePreviewId = null;

window.rotateItem = function(id){
  const it = state.items.find(x=>x.id===id); if (!it) return;
  it.edit.rotate = (it.edit.rotate + 90) % 360;
  it.edit.crop = null; it.thumb = null;   // crop coords no longer valid after re-orient
  render();
};
window.flipItem = function(id){
  const it = state.items.find(x=>x.id===id); if (!it) return;
  it.edit.flipH = !it.edit.flipH; it.edit.crop = null; it.thumb = null; render();
};

// Bake the current rotate+flip into a canvas so the crop UI operates in the SAME
// frame the server crops in (server order: rotate → flipH → crop). Transforms are
// applied so geometry is rotated first, then flipped (canvas applies the last-listed
// transform first), matching the server exactly.
function orientedPreview(it){
  return new Promise((resolve)=>{
    const rot = ((it.edit.rotate % 360) + 360) % 360;
    if (!rot && !it.edit.flipH){ resolve(it.preview); return; }
    const im = new Image();
    im.onload = () => {
      const swap = (rot===90||rot===270);
      const cw = swap ? im.naturalHeight : im.naturalWidth;
      const ch = swap ? im.naturalWidth : im.naturalHeight;
      const cv = document.createElement("canvas"); cv.width = cw; cv.height = ch;
      const cx = cv.getContext("2d");
      cx.translate(cw/2, ch/2);
      if (it.edit.flipH) cx.scale(-1, 1);          // outer op → applied after rotate
      cx.rotate(rot * Math.PI/180);                 // inner op → applied first
      cx.drawImage(im, -im.naturalWidth/2, -im.naturalHeight/2);
      resolve(cv.toDataURL("image/jpeg", 0.9));
    };
    im.onerror = () => resolve(it.preview);
    im.src = it.preview;
  });
}

window.openCropper = async function(id){
  if (cropBusy) return;                              // ignore re-entrant opens during the async bake
  const it = state.items.find(x=>x.id===id); if (!it || !it.ok) return;
  cropBusy = true;
  activeCropId = id; lastCropTrigger = document.activeElement;
  cropName.textContent = it.name;
  cropImg.src = await orientedPreview(it);           // rotation/flip baked in; Cropper stays upright
  if (cropper){ cropper.destroy(); cropper = null; } // safety: never double-init
  modal.hidden = false;
  cropper = new Cropper(cropImg, { viewMode:1, autoCropArea:1, background:false, aspectRatio:NaN });
  document.querySelectorAll('[data-aspect]').forEach(x=>x.classList.remove("on"));
  const free = document.querySelector('[data-aspect="free"]'); if (free) free.classList.add("on");
};
function closeCropper(){
  if (cropper){ cropper.destroy(); cropper = null; }
  modal.hidden = true; activeCropId = null; cropBusy = false;
  if (lastCropTrigger && lastCropTrigger.focus) lastCropTrigger.focus();
}
$("#crop-cancel").onclick = closeCropper;
$("#crop-clear").onclick = () => {
  const it = state.items.find(x=>x.id===activeCropId);
  if (it){ it.edit.crop = null; it.thumb = null; } closeCropper(); render();
};
$("#crop-apply").onclick = () => {
  const it = state.items.find(x=>x.id===activeCropId);
  const d = cropper.getData(true), im = cropper.getImageData();
  const W = im.naturalWidth, H = im.naturalHeight;
  let x = d.x/W, y = d.y/H, w = d.width/W, h = d.height/H;
  x = Math.max(0,Math.min(1,x)); y = Math.max(0,Math.min(1,y));
  w = Math.max(0,Math.min(1-x,w)); h = Math.max(0,Math.min(1-y,h));
  it.edit.crop = [x,y,w,h];
  try { const c = cropper.getCroppedCanvas({maxWidth:1024,maxHeight:1024});
        it.thumb = c ? c.toDataURL("image/jpeg",0.85) : null; } catch(e){ it.thumb = null; }
  closeCropper(); render();
};
document.querySelectorAll('[data-aspect]').forEach((b)=>b.addEventListener("click",()=>{
  document.querySelectorAll('[data-aspect]').forEach(x=>x.classList.remove("on"));
  b.classList.add("on"); const a = b.dataset.aspect; if (!cropper) return;
  if (a==="free") cropper.setAspectRatio(NaN);
  else if (a==="orig"){ const g = cropper.getImageData(); cropper.setAspectRatio(g.naturalWidth/g.naturalHeight); }
  else cropper.setAspectRatio(parseFloat(a));
}));

// preview modal — click a thumbnail to open a big view; all editing happens from here
function showPreviewImage(it){
  previewImg.src = it.thumb || it.preview;
  // Same transform logic as the card thumbnail: a baked thumb already has rotate/flip
  // applied, but the raw preview needs the CSS transform or it won't reflect edits.
  previewImg.style.transform = it.thumb ? "" : `scaleX(${it.edit.flipH?-1:1}) rotate(${it.edit.rotate}deg)`;
  previewName.textContent = it.name;
}
window.openPreview = function(id){
  const it = state.items.find(x=>x.id===id); if (!it || !it.ok) return;
  activePreviewId = id;
  showPreviewImage(it);
  previewModal.hidden = false;
};
function closePreview(){
  previewModal.hidden = true; activePreviewId = null;
}
$("#preview-rotate").addEventListener("click", () => {
  rotateItem(activePreviewId);
  const it = state.items.find(x=>x.id===activePreviewId); if (it) showPreviewImage(it);
});
$("#preview-flip").addEventListener("click", () => {
  flipItem(activePreviewId);
  const it = state.items.find(x=>x.id===activePreviewId); if (it) showPreviewImage(it);
});
$("#preview-crop").addEventListener("click", () => {
  const id = activePreviewId; closePreview(); openCropper(id);
});
$("#preview-close").addEventListener("click", closePreview);

// action buttons
$("#scrub-btn").addEventListener("click", () => convertAll("scrub"));
$("#clear-btn").addEventListener("click", () => { state.items = []; render(); setStatus(""); hideSaved(); });
$("#rotate-all-btn").addEventListener("click", () => {
  state.items.forEach(it => { if (it.ok && it.selected){ it.edit.rotate = (it.edit.rotate+90)%360; it.edit.crop=null; it.thumb=null; } });
  render();
});
if (selectToggleBtn) selectToggleBtn.addEventListener("click", () => {
  const okItems = state.items.filter(x=>x.ok);
  const allSelected = okItems.length>0 && okItems.every(x=>x.selected);
  okItems.forEach(x=>{ x.selected = !allSelected; });
  render();
});

// remember settings
const LS = "heic-convert.settings";
function saveSettings(){ try { localStorage.setItem(LS, JSON.stringify(
  { format: state.format, quality: state.quality, resize: state.resize })); } catch(e){} }
function applySavedSettings(){
  let s; try { s = JSON.parse(localStorage.getItem(LS) || "null"); } catch(e){ s = null; }
  if (!s) return;
  const fbtn = document.querySelector(`.seg-btn[data-fmt="${s.format}"]`);
  if (fbtn){ document.querySelectorAll(".seg-btn").forEach(x=>x.classList.remove("is-active"));
    fbtn.classList.add("is-active"); state.format = s.format;
    qWrap.hidden = !(s.format==="jpg"||s.format==="webp"); }
  if (typeof s.quality === "number"){ state.quality = s.quality; qInput.value = s.quality; qVal.textContent = s.quality; }
  const rbtn = document.querySelector(`#resize-group .chip[data-resize="${s.resize}"]`);
  if (rbtn){ document.querySelectorAll("#resize-group .chip").forEach(x=>x.classList.remove("on"));
    rbtn.classList.add("on"); state.resize = s.resize; }
}
["click","input"].forEach(ev=>document.addEventListener(ev, saveSettings));
applySavedSettings();

window.addEventListener("pywebviewready", () => document.body.classList.add("in-app"));

// keyboard shortcuts
document.addEventListener("keydown", (e) => {
  if (!previewModal.hidden){ if (e.key === "Escape") closePreview(); return; }
  if (!modal.hidden){ if (e.key === "Escape") closeCropper(); return; }
  if (e.target.tagName === "INPUT" || e.target.tagName === "OUTPUT" || e.target.tagName === "BUTTON") return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.key === "o" || e.key === "O") input.click();
  else if (e.key === "Enter" && state.items.some(x=>x.ok && x.selected)) convertAll("format");
  else if ((e.key === "c" || e.key === "C")){
    const first = state.items.find(x=>x.ok); if (first) openCropper(first.id);
  }
});
