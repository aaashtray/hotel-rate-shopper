// Display guidance only. Never grants a verified match or authorizes a price gap.
function compareTariffs(a,b){
  const matching=[],unknown=[],differences=[];
  if(!a||!b)return {kind:'unknown',label:'Недостаточно данных',matching,unknown,differences};
  const known=v=>v!==null&&v!==undefined&&v!==''&&!['unknown','allocation_not_guaranteed'].includes(v);
  const fields=[['room_category_normalized','название категории'],['room_area_m2','площадь'],
    ['meal_plan','питание'],['cancellation_type','тип отмены'],['payment_timing','оплата'],
    ['bed_type','тип кровати'],['taxes_included','сборы'],['access_type','доступ к цене']];
  if(a.cancellation_type==='free'||b.cancellation_type==='free')fields.push(['cancellation_deadline','точный срок отмены']);
  let nameDiff=false;
  for(const [key,label] of fields){
    if(!known(a[key])||!known(b[key])){unknown.push(label);continue}
    const equal=key==='room_area_m2'?Number(a[key])===Number(b[key]):String(a[key]).trim().toLocaleLowerCase('ru')===String(b[key]).trim().toLocaleLowerCase('ru');
    if(equal)matching.push(label);
    else if(key==='room_category_normalized')nameDiff=true;
    else differences.push(label);
  }
  // Different wording is not evidence of a different room category.
  if(nameDiff)unknown.push('соответствие названий категории');
  if(differences.length)return {kind:'different',label:'Есть различия в условиях',matching,unknown,differences};
  const sameCore=['meal_plan','cancellation_type'].every(k=>known(a[k])&&known(b[k])&&a[k]===b[k]);
  if(sameCore)return {kind:'similar',label:'Похожий тариф',matching,unknown,differences};
  return {kind:'unknown',label:'Недостаточно данных',matching,unknown,differences};
}
function candidateRank(a,b){
  const c=compareTariffs(a,b);
  return [c.kind==='similar'?0:c.kind==='unknown'?1:2,
    a.room_category_normalized&&a.room_category_normalized===b.room_category_normalized?0:1,
    c.differences.length,-c.matching.length];
}
