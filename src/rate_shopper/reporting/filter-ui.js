function setupFilterPanel(ids,onChange,defaults={}){
  const box=document.querySelector('.filterbox'),toggle=document.getElementById('filter-toggle'),apply=document.getElementById('filter-apply');
  const close=()=>{box.classList.remove('expanded');toggle.setAttribute('aria-expanded','false')};
  const small=window.matchMedia('(max-width:760px)');
  const sync=()=>{toggle.disabled=!small.matches;toggle.setAttribute('aria-expanded',String(!small.matches||box.classList.contains('expanded')))};small.addEventListener('change',sync);sync();
  toggle.onclick=()=>{const open=box.classList.toggle('expanded');toggle.setAttribute('aria-expanded',String(open))};
  apply.onclick=()=>{close();document.querySelector('.resultarea').scrollIntoView({behavior:'smooth',block:'start'})};
  const params=new URLSearchParams(location.search);
  for(const id of ids){const el=document.getElementById(id);const value=params.get(id);if(value!==null&&(el.tagName!=='SELECT'||[...el.options].some(o=>o.value===value)))el.value=value}
  function updateFilterUI(){
    const active=ids.filter(id=>!document.getElementById(id).disabled&&document.getElementById(id).value!==(defaults[id]??''));
    document.getElementById('filter-count').textContent=active.length?`Выбрано: ${active.length}`:'Все отели';
    document.getElementById('active-filters').innerHTML=active.length?active.map(id=>{const el=document.getElementById(id),name=el.tagName==='SELECT'?el.selectedOptions[0].textContent:el.value;return `<button class="filterchip" data-clear="${id}" aria-label="Убрать фильтр ${esc(name)}">${esc(name)} ×</button>`}).join(''):'<span>Все отели по выбранному режиму</span>';
    document.querySelectorAll('[data-clear]').forEach(b=>b.onclick=()=>{document.getElementById(b.dataset.clear).value=defaults[b.dataset.clear]??'';onChange()});
    const query=new URLSearchParams();for(const id of ids){const value=document.getElementById(id).value;if(value)query.set(id,value)}
    if(location.protocol!=='file:')history.replaceState(null,'',location.pathname+(query.size?'?'+query:'')+location.hash);
    document.querySelectorAll('[data-report-link]').forEach(a=>{const q=new URLSearchParams();for(const id of ['country','geo','stars','search'])if(query.has(id))q.set(id,query.get(id));const platform=query.get('platform')||query.get('competitor');if(platform&&platform!=='otello')q.set(a.dataset.reportLink==='rates'?'platform':'competitor',platform);if(a.dataset.reportLink!=='rates'){if(query.has('scope'))q.set('scope',query.get('scope'));if(query.has('mode'))q.set('mode',query.get('mode'))}a.href=a.dataset.base+(q.size?'?'+q:'')});
  }
  return updateFilterUI;
}
