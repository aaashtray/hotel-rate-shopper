function median(values){const a=values.filter(x=>x!==null&&x!==undefined&&Number.isFinite(Number(x))).map(Number).sort((a,b)=>a-b),n=a.length;return n?(n%2?a[(n-1)/2]:(a[n/2-1]+a[n/2])/2):null}
function statisticRows(report,scope,verified){
  const rows=(report.statistics.scopes?.[scope]||report.statistics).rows;
  if(!verified)return rows;
  const matches=new Map(report.statistics.verified_rows.map(r=>[r.hotel_id+'|'+r.platform,r]));
  return rows.map(r=>matches.get(r.hotel_id+'|'+r.platform)||{...r,reference_offer_id:null,competitor_offer_id:null,reference_total:null,competitor_total:null,reference_access:null,competitor_access:null,percent_gap:null,absolute_gap:null,outcome:'excluded',reason:'unverified'});
}
const countryMapKeys={'Россия':'RUS','Турция':'TUR','Таиланд':'THA','Мальдивы':'MDV'};
const regionMapKeys={'Москва':'RU-MOW','Санкт-Петербург':'RU-SPE','Сочи':'RU-KDA'};
function hotelMapKey(h,kind){return kind==='world'?countryMapKeys[h.country]:(h.country==='Россия'?regionMapKeys[h.geo]:undefined)}
function summarizeRegion(hotels,rows){
  const ids=new Set(hotels.map(h=>h.id)),valid=rows.filter(r=>ids.has(r.hotel_id)&&r.percent_gap!=null&&Number.isFinite(Number(r.percent_gap))),groups=new Map();
  for(const r of valid){if(!groups.has(r.hotel_id))groups.set(r.hotel_id,[]);groups.get(r.hotel_id).push(Number(r.percent_gap))}
  const hotelMedians=[...groups.values()].map(median),gap=median(hotelMedians);
  return {hotels:hotels.length,comparedHotels:groups.size,pairs:valid.length,gap,loss:valid.filter(r=>r.outcome==='loss').length,win:valid.filter(r=>r.outcome==='win').length,tie:valid.filter(r=>r.outcome==='tie').length,status:!hotels.length?'empty':gap===null?'excluded':gap>0?'loss':gap<0?'win':'tie'};
}
