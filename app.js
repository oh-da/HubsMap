/* ───────────────────────────────────────────────
   מפת המתח״מים — dashboard logic
─────────────────────────────────────────────── */
const HUBS = window.HUBS || [];

/* classification config (ordered, top tier first) */
const CLASSES = [
  { key:"ארצי",        label:"ארצי",       color:"#B0432B" },
  { key:"מטרופוליני",  label:"מטרופוליני", color:"#DD9326" },
  { key:"עירוני",      label:"עירוני",     color:"#3E769E" },
  { key:"Not Hub",     label:"לא מסווג",   color:"#A9A192" },
];
const CLS_MAP = Object.fromEntries(CLASSES.map(c=>[c.key,c]));
/* Canonical display order for the well-known metros / modes; any extra value
   that shows up in the data (e.g. a new "מחוז דרום" metro) is appended so it
   stays visible and filterable instead of being silently dropped. */
const METRO_ORDER = ["תל אביב","חיפה","ירושלים","באר שבע","צפון"];
const MODE_ORDER  = ['רק"ל','BRT','מטרו','רכבת פרברית','רכבת בינעירונית','רכבת מהירה','Cable Line','פוניקולר'];
/* Display-only aliases for transport modes. The raw value (kept in the data and
   used for filtering) stays the same; only the label shown to the user changes. */
const MODE_LABELS = { 'Cable Line':'רכבלית', 'פוניקולר':'כרמלית' };
const modeLabel = m => MODE_LABELS[m] || m;
function withExtras(order, values){
  const extra = [...new Set(values)].filter(v => v && !order.includes(v));
  return [...order, ...extra];
}
const METROS = withExtras(METRO_ORDER, HUBS.map(h=>h.metro));
const MODES  = withExtras(MODE_ORDER, HUBS.flatMap(h=>(h.modes||"").split(',').map(s=>s.trim())));
/* Display-only labels for modes whose source value differs from the Hebrew
   term shown to users. The underlying value is kept for filtering/matching. */
const MODE_LABELS = { 'Cable Line':'רכבלית', 'פוניקולר':'כרמלית' };
const modeLabel = m => MODE_LABELS[m] || m;

/* ── helpers ── */
const nf = new Intl.NumberFormat('he-IL');
const fmt = n => (n==null||isNaN(n)) ? "—" : nf.format(Math.round(n));
const fmtc = n => { if(n==null||isNaN(n))return"—"; const a=Math.abs(n);
  if(a>=1e6)return (n/1e6).toFixed(1).replace(/\.0$/,'')+"M";
  if(a>=1e3)return (n/1e3).toFixed(a>=1e4?0:1).replace(/\.0$/,'')+"K"; return ""+Math.round(n); };
function splitLines(str){
  if(!str) return [];
  return str.split(/\)\s*,\s*/).map(s=>s.trim()).filter(Boolean).map(s=>s.endsWith(')')?s:s+')');
}
const esc = s => String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
const escA = esc; // back-compat alias; both content and attribute contexts use full escaping
function textOn(hex){ const n=parseInt(hex.slice(1),16),r=(n>>16)&255,g=(n>>8)&255,b=n&255; return (0.299*r+0.587*g+0.114*b)/255>0.6?'#231b0e':'#fff'; }
function hubModes(h){
  const out=[]; (h.modes||"").split(',').map(s=>s.trim()).filter(Boolean).forEach(m=>{ if(!out.includes(m)) out.push(m); });
  return out;
}

/* ── radius scale (by log demand) ── */
const lds = HUBS.map(h=>h.logDemand).filter(v=>typeof v==='number');
const LD_MIN=Math.min(...lds), LD_MAX=Math.max(...lds);
const radiusFor = h => { const t=(h.logDemand-LD_MIN)/(LD_MAX-LD_MIN||1); return 5 + Math.pow(t,0.85)*15; };

/* ── contextual ranking ──
   ארצי → national rank (among national hubs);
   מטרופוליני / עירוני → rank within their type AND their area (metro). ── */
(function computeRanks(){
  const groups={};
  HUBS.forEach(h=>{
    let key;
    if(h.type==='ארצי') key='__national__';
    else if(h.type==='מטרופוליני'||h.type==='עירוני') key=h.type+'||'+h.metro;
    else key='__nothub__';
    (groups[key]=groups[key]||[]).push(h);
  });
  Object.values(groups).forEach(arr=>{
    arr.sort((a,b)=>(a.rank||9999)-(b.rank||9999));
    arr.forEach((h,i)=>{ h.gRank=i+1; h.gTotal=arr.length; });
  });
})();
function rankInfo(h){
  const ring=h.ring||'—';
  if(h.type==='ארצי')
    return {pill:`דירוג ארצי #${h.gRank}`, sub:`מתוך ${h.gTotal} מתח״מים ארציים · אזור ${ring}`};
  if(h.type==='מטרופוליני'||h.type==='עירוני'){
    const w=h.type==='מטרופוליני'?'מטרופוליניים':'עירוניים';
    return {pill:`דירוג ב${h.metro} #${h.gRank}`, sub:`מתוך ${h.gTotal} מתח״מים ${w} ב${h.metro} · אזור ${ring}`};
  }
  return {pill:`דירוג כללי #${h.rank??'—'}`, sub:`לא מסווג כמתח״ם · אזור ${ring}`};
}

/* ── state ── */
const state = {
  classes:new Set(["ארצי","מטרופוליני","עירוני"]),  // Not Hub off by default
  metros:new Set(METROS),
  modes:new Set(MODES),
  demandMin:0,
  rankMax:130,
  topN:null,        // quick contextual top-N filter (null | 10 | 20)
  selected:null,
  network:false,
};
const DEMAND_MAX = Math.max(...HUBS.map(h=>h.demand||0));
const RANK_MAX   = Math.max(...HUBS.map(h=>h.rank||0));
state.rankMax = RANK_MAX;

/* ── map ── */
const map = L.map('map',{zoomControl:false,attributionControl:true,minZoom:7,maxZoom:16}).setView([32.05,34.95],9);
const BASES = {
  light:L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{subdomains:'abcd',maxZoom:19,attribution:'© OpenStreetMap © CARTO'}),
  gray :L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png',{subdomains:'abcd',maxZoom:19,attribution:'© OpenStreetMap © CARTO'}),
  dark :L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{subdomains:'abcd',maxZoom:19,attribution:'© OpenStreetMap © CARTO'}),
};
let curBase='light'; BASES.light.addTo(map);

const overlayPane = map.createPane('hubs'); overlayPane.style.zIndex=620;
const netPane = map.createPane('net'); netPane.style.zIndex=560;
const uploadPane = map.createPane('uploads'); uploadPane.style.zIndex=540;

/* ── markers ── */
const markers = HUBS.map(h=>{
  const c = CLS_MAP[h.type]||CLS_MAP["Not Hub"];
  const m = L.circleMarker([h.lat,h.lng],{
    pane:'hubs', radius:radiusFor(h), fillColor:c.color, color:'#fff',
    weight:1.4, opacity:1, fillOpacity:.82
  });
  m.hub=h;
  m.bindTooltip(`<div>${esc(h.name)}</div><div class="tt-sub">${esc(rankInfo(h).pill)} · ${esc(c.label)} · ביקוש ${fmtc(h.demand)}</div>`,
    {className:'hub-tip',direction:'top',offset:[0,-4],opacity:1});
  m.on('click',()=>openDetail(h));
  m.on('mouseover',function(){ if(state.selected!==h) this.setStyle({weight:2.4,fillOpacity:.95}); });
  m.on('mouseout', function(){ if(state.selected!==h) this.setStyle({weight:1.4,fillOpacity:.82}); });
  return m;
});

const ALL_BOUNDS = L.latLngBounds(HUBS.map(h=>[h.lat,h.lng])).pad(0.08);
map.fitBounds(ALL_BOUNDS);

/* ── derived line network ── */
const netLayer = L.layerGroup([],{pane:'net'});
(function buildNetwork(){
  const byLine={};
  HUBS.forEach(h=>{ splitLines(h.lines).forEach(ln=>{ (byLine[ln]=byLine[ln]||[]).push(h); }); });
  Object.values(byLine).forEach(group=>{
    if(group.length<2) return;
    // greedy nearest-neighbour path from westernmost
    const pts=[...group].sort((a,b)=>a.lng-b.lng);
    const path=[pts.shift()];
    while(pts.length){
      const last=path[path.length-1]; let bi=0,bd=Infinity;
      pts.forEach((p,i)=>{ const d=(p.lat-last.lat)**2+(p.lng-last.lng)**2; if(d<bd){bd=d;bi=i;} });
      path.push(pts.splice(bi,1)[0]);
    }
    L.polyline(path.map(p=>[p.lat,p.lng]),{pane:'net',color:'#5a6b7a',weight:2,opacity:.32,lineCap:'round'}).addTo(netLayer);
  });
})();

/* ── uploaded layers (persisted) ── */
const LS_KEY='hubDash.layers.v1';
let userLayers=[]; // {id,name,geojson,visible,leaf}
function loadUserLayers(){
  try{ const raw=JSON.parse(localStorage.getItem(LS_KEY)||'[]');
    raw.forEach(r=>addUserLayer(r.name,r.geojson,r.visible!==false,r.id,false)); }catch(e){}
}
function persistUserLayers(){
  localStorage.setItem(LS_KEY, JSON.stringify(userLayers.map(l=>({id:l.id,name:l.name,geojson:l.geojson,visible:l.visible}))));
}
function styleUpload(){ return {pane:'uploads',color:'#7A3FB0',weight:2.4,opacity:.85,fillColor:'#7A3FB0',fillOpacity:.12}; }
function addUserLayer(name,geojson,visible,id,persist=true){
  id=id||('L'+Date.now()+Math.random().toString(36).slice(2,6));
  const leaf=L.geoJSON(geojson,{
    pane:'uploads', style:styleUpload(),
    pointToLayer:(f,ll)=>L.circleMarker(ll,{pane:'uploads',radius:4,color:'#7A3FB0',weight:2,fillColor:'#fff',fillOpacity:1})
  });
  const layer={id,name,geojson,visible:visible!==false,leaf};
  userLayers.push(layer);
  if(layer.visible) leaf.addTo(map);
  if(persist) persistUserLayers();
  renderRail();
}
function removeUserLayer(id){
  const i=userLayers.findIndex(l=>l.id===id); if(i<0)return;
  map.removeLayer(userLayers[i].leaf); userLayers.splice(i,1); persistUserLayers(); renderRail();
}

/* ── built-in shared layers ──
   Defined in layers/layers.json and committed to the repo, so every viewer
   sees the same layers (unlike uploads, which stay in one browser).
   Manifest entry: { "id", "name", "file", "color", "visible" }. ── */
let builtinLayers=[]; // {id,name,color,visible,leaf}
const hasFill = f => !!(f && f.geometry && /Polygon/.test(f.geometry.type));
function styleBuiltin(color){
  return f => ({pane:'uploads',color,weight:2.4,opacity:.9,fillColor:color,fillOpacity:hasFill(f)?.14:0});
}
async function loadBuiltinLayers(){
  let manifest=[];
  try{ const r=await fetch('layers/layers.json',{cache:'no-cache'}); if(r.ok) manifest=await r.json(); }
  catch(e){ return; }
  if(!Array.isArray(manifest)) return;
  for(const m of manifest){
    if(!m||!m.file) continue;
    try{
      const r=await fetch('layers/'+m.file,{cache:'no-cache'}); if(!r.ok) continue;
      const gj=await r.json();
      const color=m.color||'#2E7D6B';
      const leaf=L.geoJSON(gj,{
        pane:'uploads', style:styleBuiltin(color),
        pointToLayer:(f,ll)=>L.circleMarker(ll,{pane:'uploads',radius:4,color,weight:2,fillColor:'#fff',fillOpacity:1})
      });
      const visible=m.visible!==false;
      const layer={id:m.id||('B'+Math.random().toString(36).slice(2,8)), name:m.name||m.file, color, visible, leaf};
      builtinLayers.push(layer);
      if(visible) leaf.addTo(map);
    }catch(e){ /* skip a bad layer, keep the rest */ }
  }
  renderRail();
}

/* ── filtering ── */
function passes(h){
  if(!state.classes.has(h.type)) return false;
  if(!state.metros.has(h.metro)) return false;
  const hm=hubModes(h);
  if(![...hm].some(m=>state.modes.has(m))) return false;
  if((h.demand||0) < state.demandMin) return false;
  if((h.rank||999) > state.rankMax) return false;
  // contextual quick filter: top-N within the hub's own ranking group
  // (national among national, metro/urban within their metro), so e.g. with
  // only "ארצי" selected, Top 10 shows the 10 highest-ranked national hubs.
  if(state.topN!=null && (h.gRank||9999) > state.topN) return false;
  return true;
}
function applyFilters(){
  let shown=0, demSum=0;
  markers.forEach((m,i)=>{
    const h=HUBS[i];
    if(passes(h)){ if(!map.hasLayer(m)) m.addTo(map); shown++; demSum+=h.demand||0; }
    else { if(map.hasLayer(m)) map.removeLayer(m); if(state.selected===h) closeDetail(); }
  });
  document.getElementById('mapCount').innerHTML = `מציג <b>${shown}</b> מתוך ${HUBS.length} מתח״מים`;
  document.getElementById('mastMeta').innerHTML = `
    <div class="mast-stat"><span class="num">${shown}</span><span class="lab">מתח״מים מוצגים</span></div>
    <div class="mast-div"></div>
    <div class="mast-stat"><span class="num">${fmtc(demSum)}</span><span class="lab">ביקוש יומי כולל</span></div>`;
}

/* ── detail drawer ── */
const detailEl=document.getElementById('detail');
/* Bars for a single metric (key 'pop' or 'emp') across the three radius rings,
   scaled to that metric's own max so each graph reads on its own. */
function radiusBarsMetric(h,key,color){
  const rings=[
    {l:'0–500 מ׳',     v:h[key+'_0_500']},
    {l:'500–1,000 מ׳',  v:h[key+'_500_1000']},
    {l:'1,000–1,500 מ׳', v:h[key+'_1000_1500']},
  ];
  const maxV=Math.max(...rings.map(r=>r.v||0),1);
  return rings.map(r=>{
    const v=r.v||0; const w=(v/maxV)*100;
    return `<div class="radius-row">
      <div class="rl"><span>${r.l}</span><b>${fmt(v)}</b></div>
      <div class="bar" style="width:${Math.max(w,8)}%"><i style="width:100%;background:${color}"></i></div>
    </div>`;
}
function openDetail(h){
  state.selected=h;
  markers.forEach(m=>m.setStyle(m.hub===h?{weight:3,fillOpacity:1,color:'#1B1915'}:{weight:1.4,fillOpacity:.82,color:'#fff'}));
  const c=CLS_MAP[h.type]||CLS_MAP["Not Hub"];
  const ri=rankInfo(h);
  const modes=hubModes(h);
  const lines=splitLines(h.lines);
  detailEl.innerHTML=`
    <div class="dt-head">
      <button class="dt-close" onclick="closeDetail()" aria-label="סגור">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>
      </button>
      <div class="rk">
        <span class="dt-rank" style="background:${c.color};color:${textOn(c.color)}">${esc(ri.pill)}</span>
        <span class="dt-cls"><span class="dot" style="background:${c.color}"></span>${esc(c.label)}</span>
      </div>
      <h3>${esc(h.name)}</h3>
      <div class="loc">${esc(ri.sub)}</div>
    </div>
    <div class="dt-body">
      <div class="kpi-grid">
        <div class="kpi"><div class="v">${fmt(h.demand)}</div><div class="l">ביקוש יומי (נוסעים)</div></div>
        <div class="kpi"><div class="v">${h.numModes}</div><div class="l">מס׳ אמצעים</div></div>
        <div class="kpi"><div class="v">${fmt(h.pop)}</div><div class="l">אוכלוסייה · רדיוס 1.5 ק״מ</div></div>
        <div class="kpi"><div class="v">${fmt(h.emp)}</div><div class="l">תעסוקה · רדיוס 1.5 ק״מ</div></div>
      </div>

      <div class="dt-sec">
        <div class="h">אמצעים מתוכננים</div>
        <div class="mode-chips">${modes.map(m=>`<span class="mode-chip">${esc(modeLabel(m))}</span>`).join('')}</div>
      </div>

      <div class="dt-sec">
        <div class="h">אוכלוסייה ומועסקים בסביבת המתח״מ - 2050</div>
        <div class="radii-sub"><i style="background:#3E769E"></i>אוכלוסייה</div>
        <div class="radii">${radiusBarsMetric(h,'pop','#3E769E')}</div>
        <div class="radii-sub" style="margin-top:16px"><i style="background:#DD9326"></i>מועסקים</div>
        <div class="radii">${radiusBarsMetric(h,'emp','#DD9326')}</div>
      </div>

      <div class="dt-sec">
        <div class="h">קווים (${lines.length})</div>
        <div class="lines-list">${lines.map(l=>`<div class="line-item">${esc(l)}</div>`).join('')||'<div class="line-item">—</div>'}</div>
      </div>

      <button class="dt-focus" onclick="focusHub()">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
        התמקד במפה
      </button>
    </div>`;
  detailEl.classList.add('open');
}
function closeDetail(){
  detailEl.classList.remove('open');
  if(state.selected){ markers.forEach(m=>m.setStyle({weight:1.4,fillOpacity:.82,color:'#fff'})); state.selected=null; }
}
function focusHub(){ if(state.selected) map.flyTo([state.selected.lat,state.selected.lng],13,{duration:.8}); }
window.closeDetail=closeDetail; window.focusHub=focusHub;

/* ── rail (filters / legend / layers) ── */
const rail=document.getElementById('rail');
function clsCounts(){ const m={}; HUBS.forEach(h=>m[h.type]=(m[h.type]||0)+1); return m; }
function metroCounts(){ const m={}; HUBS.forEach(h=>m[h.metro]=(m[h.metro]||0)+1); return m; }
function renderRail(){
  const cc=clsCounts(), mc=metroCounts();
  rail.innerHTML=`
    <div class="sec">
      <div class="sec-h"><span class="t">סיווג מתח״ם</span><span class="ln"></span><span class="h">סינון</span></div>
      <div class="chips" id="clsChips">
        ${CLASSES.map(c=>`<button class="chip cls ${state.classes.has(c.key)?'on':'off'}" data-cls="${c.key}" style="${state.classes.has(c.key)?`color:${c.color}`:''}">
          <span class="dot" style="background:${c.color}"></span>${c.label}<span class="cnt">${cc[c.key]||0}</span></button>`).join('')}
      </div>
    </div>

    <div class="sec">
      <div class="sec-h"><span class="t">מטרופולין</span><span class="ln"></span></div>
      <div class="chips" id="metChips">
        ${METROS.map(m=>`<button class="chip ${state.metros.has(m)?'on':'off'}" data-met="${m}">${m}<span class="cnt">${mc[m]||0}</span></button>`).join('')}
      </div>
    </div>

    <div class="sec">
      <div class="sec-h"><span class="t">אמצעי תחבורה</span><span class="ln"></span></div>
      <div class="chips" id="modeChips">
        ${MODES.map(m=>`<button class="chip ${state.modes.has(m)?'on':'off'}" data-mode="${escA(m)}">${esc(modeLabel(m))}</button>`).join('')}
      </div>
    </div>

    <div class="sec">
      <div class="sec-h"><span class="t">סף ביקוש ודירוג</span><span class="ln"></span></div>
      <div class="slider-row">
        <div class="slider-lab"><span>ביקוש יומי מינימלי</span><b>${fmt(state.demandMin)}</b></div>
        <input type="range" id="demSlider" min="0" max="${Math.ceil(DEMAND_MAX/1000)*1000}" step="1000" value="${state.demandMin}">
      </div>
      <div class="slider-row">
        <div class="slider-lab"><span>הצג מתח״מים עד דירוג</span><b>${state.rankMax}</b></div>
        <input type="range" id="rankSlider" min="1" max="${RANK_MAX}" step="1" value="${state.rankMax}">
      </div>
      <div class="slider-row">
        <div class="slider-lab"><span>סינון מהיר לפי דירוג</span></div>
        <div class="chips" id="topChips">
          <button class="chip ${state.topN===10?'on':'off'}" data-top="10">Top 10</button>
          <button class="chip ${state.topN===20?'on':'off'}" data-top="20">Top 20</button>
        </div>
      </div>
    </div>

    <div class="sec">
      <div class="sec-h"><span class="t">מקרא</span><span class="ln"></span></div>
      <div class="legend">
        ${CLASSES.map(c=>`<div class="lg-row"><span class="dot" style="background:${c.color}"></span>${c.label}</div>`).join('')}
        <div class="lg-sub">גודל העיגול = ביקוש יומי</div>
        <div class="lg-sizes">
          <div class="lg-size"><i style="width:11px;height:11px"></i><span>נמוך</span></div>
          <div class="lg-size"><i style="width:24px;height:24px"></i><span>בינוני</span></div>
          <div class="lg-size"><i style="width:40px;height:40px"></i><span>גבוה</span></div>
        </div>
      </div>
    </div>

    <div class="sec">
      <div class="sec-h"><span class="t">שכבות רקע</span><span class="ln"></span></div>
      <div class="seg" id="baseSeg">
        <button data-base="light" class="${curBase==='light'?'on':''}">בהיר</button>
        <button data-base="gray" class="${curBase==='gray'?'on':''}">אפור</button>
        <button data-base="dark" class="${curBase==='dark'?'on':''}">כהה</button>
      </div>
      <div style="margin-top:14px">
        <div class="layer-row">
          <div class="layer-swatch" style="background:#eef0f1"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="#5a6b7a" stroke-width="2"><path d="M3 17 L9 7 L15 15 L21 6"/></svg></div>
          <div class="ll"><div class="nm">רשת הקווים (משוער)</div><div class="ds">חיבור מתח״מים על קו משותף</div></div>
          <button class="toggle ${state.network?'on':''}" id="netToggle"></button>
        </div>
        ${builtinLayers.map(l=>`<div class="layer-row">
          <div class="layer-swatch" style="background:${esc(l.color)}1f"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="${esc(l.color)}" stroke-width="2"><path d="M4 18 L10 9 L14 14 L20 5"/></svg></div>
          <div class="ll"><div class="nm">${esc(l.name)}</div><div class="ds">שכבה משותפת</div></div>
          <button class="toggle ${l.visible?'on':''}" data-blayer="${esc(l.id)}"></button>
        </div>`).join('')}
        ${userLayers.map(l=>`<div class="layer-row">
          <div class="layer-swatch" style="background:#f1ecf6"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="#7A3FB0" stroke-width="2"><path d="M4 18 L10 9 L14 14 L20 5"/></svg></div>
          <div class="ll"><div class="nm">${esc(l.name)}</div><div class="ds">שכבה שהועלתה</div></div>
          <button class="toggle ${l.visible?'on':''}" data-ulayer="${esc(l.id)}"></button>
          <button class="dt-close" style="position:static;width:24px;height:24px;background:#f3efe6;color:#938b7d" data-rm="${esc(l.id)}" title="הסר">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg></button>
        </div>`).join('')}
        <button class="upload-btn" id="uploadBtn">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16V4M7 9l5-5 5 5M5 20h14"/></svg>
          טען שכבת GeoJSON
        </button>
        <div class="upload-hint">קווי רכבת, מטרו, גבולות תכנון ועוד · ‎.geojson</div>
      </div>
    </div>`;
  wireRail();
}

function wireRail(){
  rail.querySelectorAll('[data-cls]').forEach(b=>b.onclick=()=>{ toggleSet(state.classes,b.dataset.cls); renderRail(); applyFilters(); });
  rail.querySelectorAll('[data-met]').forEach(b=>b.onclick=()=>{ toggleSet(state.metros,b.dataset.met); renderRail(); applyFilters(); });
  rail.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{ toggleSet(state.modes,b.dataset.mode); renderRail(); applyFilters(); });
  const ds=rail.querySelector('#demSlider'); ds.oninput=()=>{ state.demandMin=+ds.value; ds.previousElementSibling.querySelector('b').textContent=fmt(state.demandMin); applyFilters(); };
  const rs=rail.querySelector('#rankSlider'); rs.oninput=()=>{
    state.rankMax=+rs.value;
    // moving the slider supersedes a quick top-N selection
    if(state.topN!=null){ state.topN=null; rail.querySelectorAll('[data-top]').forEach(x=>{x.classList.remove('on');x.classList.add('off');}); }
    rs.previousElementSibling.querySelector('b').textContent=state.rankMax; applyFilters();
  };
  rail.querySelectorAll('[data-top]').forEach(b=>b.onclick=()=>{
    const n=+b.dataset.top;
    state.topN = (state.topN===n) ? null : n;
    state.rankMax = RANK_MAX;   // top-N supersedes the manual rank slider
    renderRail(); applyFilters();
  });
  rail.querySelectorAll('[data-base]').forEach(b=>b.onclick=()=>setBase(b.dataset.base));
  rail.querySelector('#netToggle').onclick=()=>{ state.network=!state.network; if(state.network) netLayer.addTo(map); else map.removeLayer(netLayer); renderRail(); };
  rail.querySelectorAll('[data-blayer]').forEach(b=>b.onclick=()=>{ const l=builtinLayers.find(x=>x.id===b.dataset.blayer); if(!l)return; l.visible=!l.visible; if(l.visible)l.leaf.addTo(map); else map.removeLayer(l.leaf); renderRail(); });
  rail.querySelectorAll('[data-ulayer]').forEach(b=>b.onclick=()=>{ const l=userLayers.find(x=>x.id===b.dataset.ulayer); l.visible=!l.visible; if(l.visible)l.leaf.addTo(map); else map.removeLayer(l.leaf); persistUserLayers(); renderRail(); });
  rail.querySelectorAll('[data-rm]').forEach(b=>b.onclick=()=>removeUserLayer(b.dataset.rm));
  rail.querySelector('#uploadBtn').onclick=()=>document.getElementById('geojsonInput').click();
}
function toggleSet(set,v){ set.has(v)?set.delete(v):set.add(v); }
function setBase(b){ if(b===curBase)return; map.removeLayer(BASES[curBase]); curBase=b; BASES[b].addTo(map); renderRail(); }

/* ── geojson upload ── */
document.getElementById('geojsonInput').addEventListener('change',e=>{
  const f=e.target.files[0]; if(!f)return;
  const rd=new FileReader();
  rd.onload=()=>{ try{ const gj=JSON.parse(rd.result); addUserLayer(f.name.replace(/\.(geo)?json$/i,''),gj,true);
    const lyr=userLayers[userLayers.length-1]; try{ map.fitBounds(lyr.leaf.getBounds().pad(0.1)); }catch(_){}}
    catch(err){ alert('קובץ GeoJSON לא תקין'); } };
  rd.readAsText(f); e.target.value='';
});

/* ── map tools ── */
document.getElementById('btnFit').onclick=()=>map.fitBounds(ALL_BOUNDS);
document.getElementById('btnZin').onclick=()=>map.zoomIn();
document.getElementById('btnZout').onclick=()=>map.zoomOut();
map.on('click',e=>{ if(!e.originalEvent.target.closest('.leaflet-interactive')) closeDetail(); });

/* ── init ── */
loadUserLayers();
renderRail();
applyFilters();
loadBuiltinLayers();
