let mapSelection=null;
document.querySelectorAll('.mapcanvas').forEach(canvas=>{
  const button=document.createElement('button');button.className='mapzoom';button.textContent='Увеличить карту';button.setAttribute('aria-pressed','false');
  canvas.before(button);button.onclick=()=>{const zoomed=canvas.classList.toggle('zoomed');button.setAttribute('aria-pressed',String(zoomed));button.textContent=zoomed?'Уместить карту':'Увеличить карту'};
});
const MAPS=JSON.parse(document.getElementById('map-data').textContent||'{}');
const mapColors={empty:'#d5d9d8',excluded:null,loss:'#de4949',win:'#168047',tie:'#fff1c4'};
function renderMaps(hotels,rows,verified){
  const choices=[];
  for(const kind of ['russia','world']){
    const map=MAPS[kind],summaries=new Map();
    for(const region of map.regions){
      const sample=hotels.filter(h=>hotelMapKey(h,kind)===region.id),s=summarizeRegion(sample,rows);
      const full=R.hotels.filter(h=>hotelMapKey(h,kind)===region.id);s.inSample=full.length;
      summaries.set(region.id,s);
      if(full.length)choices.push({kind,region,s});
    }
    const description=(r,s)=>`${r.name}: ${s.gap===null?(s.hotels?'нет сравнения':s.inSample?'нет отелей по фильтрам':'данные ещё не собраны'):(s.gap>0?'Отелло дороже на ':s.gap<0?'Отелло дешевле на ':'Цены равны ')+pct(Math.abs(s.gap)).replace('+','')}. Отелей в расчёте: ${s.comparedHotels}, пар: ${s.pairs}.`;
    const regionAttrs=(r,s)=>`data-map-kind="${kind}" data-region-id="${esc(r.id)}" role="button" tabindex="${s.inSample?0:-1}" aria-label="${esc(description(r,s))}"`;
    const fill=s=>s.status==='excluded'?`url(#hatch-${kind})`:mapColors[s.status];
    const paths=map.regions.map(r=>{const s=summaries.get(r.id);return `<path class="region ${mapSelection===kind+'|'+r.id?'selected':''}" d="${r.path}" fill="${fill(s)}" fill-rule="evenodd" ${r.tiny?'':regionAttrs(r,s)}><title>${esc(description(r,s))}</title></path>`}).join('');
    const labelRegions=map.regions.filter(r=>summaries.get(r.id).inSample).sort((a,b)=>summaries.get(b.id).inSample-summaries.get(a.id).inSample);
    const labels=placeMapLabels(labelRegions,map.viewBox).map(({region:r,x,y,lx,ly})=>{
      const s=summaries.get(r.id);
      const marker=r.tiny?`<circle class="map-marker" cx="${x}" cy="${y}" r="6" fill="${fill(s)}" ${regionAttrs(r,s)}><title>${esc(description(r,s))}</title></circle>`:'';
      if(lx===null)return marker;
      const displaced=Math.abs(lx-x)>10||Math.abs(ly-y)>20;
      return `${marker}${displaced?`<path class="map-label-line" d="M${x},${y} L${lx},${ly}"/>`:''}<text class="map-label" x="${lx}" y="${ly}" text-anchor="middle">${esc(r.name)}<tspan class="map-label-value" x="${lx}" dy="16">${s.gap===null?'—':pct(s.gap)}</tspan></text>`;
    }).join('');
    $('map-'+kind).innerHTML=`<svg viewBox="${map.viewBox}" aria-label="${kind==='russia'?'Карта регионов России':'Карта мира'}"><defs><pattern id="hatch-${kind}" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="7" height="7" fill="#e9eceb"/><rect width="2" height="7" fill="#a8b3ad"/></pattern></defs>${paths}${labels}</svg>`;
  }
  const select=(kind,id)=>{mapSelection=kind+'|'+id;selection=null;render();$('map-selection').scrollIntoView({behavior:'smooth',block:'start'})};
  document.querySelectorAll('[data-region-id]').forEach(el=>{el.onclick=()=>select(el.dataset.mapKind,el.dataset.regionId);el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(el.dataset.mapKind,el.dataset.regionId)}}});
  $('region-list').innerHTML=choices.map(({kind,region,s})=>`<button data-region-choice="${kind}|${region.id}" aria-pressed="${mapSelection===kind+'|'+region.id}">${esc(region.name)} <b>${pct(s.gap)}</b><small>${kind==='russia'?'Регион РФ':'Страна'} · ${s.comparedHotels} отелей · ${s.pairs} пар</small></button>`).join('');
  document.querySelectorAll('[data-region-choice]').forEach(el=>el.onclick=()=>select(...el.dataset.regionChoice.split('|')));
  $('clear-region').hidden=!mapSelection;
  $('clear-region').onclick=()=>{mapSelection=null;selectedRegionHotelIds=null;render()};
  selectedRegionHotelIds=null;
  if(mapSelection){
    const [kind,id]=mapSelection.split('|'),region=MAPS[kind].regions.find(r=>r.id===id),sample=hotels.filter(h=>hotelMapKey(h,kind)===id),s=summarizeRegion(sample,rows);
    selectedRegionHotelIds=new Set(sample.map(h=>h.id));
    $('map-selection-title').textContent=region.name;
    $('map-selection-info').innerHTML=`<span class="region-gap" style="color:${s.status==='loss'?'#ba3333':s.status==='win'?'#168047':'#526452'}">${pct(s.gap)}</span><span>${s.gap===null?'Нет сравнения':s.gap>0?'Отелло дороже':s.gap<0?'Отелло дешевле':'Одинаковые цены'}</span><div class="region-meta"><p>${s.hotels} отелей по фильтрам · ${s.comparedHotels} вошли в медиану · ${s.pairs} пар с конкурентами.</p>${s.hotels?`<p>По парам: дороже — ${s.loss}, дешевле — ${s.win}, равны — ${s.tie}. ${verified?'Подтверждённый режим.':'Предварительные минимумы; условия могут отличаться.'}</p><p>Отели и источники показаны в таблице ниже.</p>`:'<p>Нет отелей по текущим фильтрам. Если территория ещё не представлена в выборке, она остаётся серой.</p>'}</div>`;
  }else{$('map-selection-title').textContent='Выберите регион или страну';$('map-selection-info').textContent='Нажмите карту или территорию в списке. Таблица ниже показывает все отели по фильтрам.'}
  $('map-attribution').innerHTML=`Геоданные: <a href="https://www.naturalearthdata.com/" target="_blank" rel="noopener">Natural Earth ${esc(MAPS.attribution.version)}</a>, public domain. ${esc(MAPS.attribution.boundaryNote)} Выводы относятся к нашей выборке отелей.`;
}
