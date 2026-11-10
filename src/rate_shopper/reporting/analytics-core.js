function median(values){const a=values.filter(x=>x!==null&&x!==undefined&&Number.isFinite(Number(x))).map(Number).sort((a,b)=>a-b),n=a.length;return n?(n%2?a[(n-1)/2]:(a[n/2-1]+a[n/2])/2):null}
function statisticRows(report,scope,verified){
  const rows=(report.statistics.scopes?.[scope]||report.statistics).rows;
  if(!verified)return rows;
  const matches=new Map(report.statistics.verified_rows.map(r=>[r.hotel_id+'|'+r.platform,r]));
  return rows.map(r=>matches.get(r.hotel_id+'|'+r.platform)||{...r,reference_offer_id:null,competitor_offer_id:null,reference_total:null,competitor_total:null,reference_access:null,competitor_access:null,percent_gap:null,absolute_gap:null,outcome:'excluded',reason:'unverified'});
}
const countryMapKeys={"ОАЭ":"ARE","Грузия":"GEO","Армения":"ARM","Казахстан":"KAZ","Узбекистан":"UZB","Беларусь":"BLR","Азербайджан":"AZE","Египет":"EGY","Вьетнам":"VNM","Индонезия":"IDN",'Россия':'RUS','Турция':'TUR','Таиланд':'THA','Мальдивы':'MDV'};
const regionMapKeys={"Казань":"RU-TA","Екатеринбург":"RU-SVE","Калининград":"RU-KGD","Владивосток":"RU-PRI","Новосибирск":"RU-NVS","Красноярск":"RU-KYA","Мурманск":"RU-MUR","Иркутск":"RU-IRK","Ярославль":"RU-YAR","Нижний Новгород":"RU-NIZ",'Москва':'RU-MOW','Санкт-Петербург':'RU-SPE','Сочи':'RU-KDA'};
function hotelMapKey(h,kind){return kind==='world'?countryMapKeys[h.country]:(h.country==='Россия'?regionMapKeys[h.geo]:undefined)}
function summarizeRegion(hotels,rows){
  const ids=new Set(hotels.map(h=>h.id)),valid=rows.filter(r=>ids.has(r.hotel_id)&&r.percent_gap!=null&&Number.isFinite(Number(r.percent_gap))),groups=new Map();
  for(const r of valid){if(!groups.has(r.hotel_id))groups.set(r.hotel_id,[]);groups.get(r.hotel_id).push(Number(r.percent_gap))}
  const hotelMedians=[...groups.values()].map(median),gap=median(hotelMedians);
  return {hotels:hotels.length,comparedHotels:groups.size,pairs:valid.length,gap,loss:valid.filter(r=>r.outcome==='loss').length,win:valid.filter(r=>r.outcome==='win').length,tie:valid.filter(r=>r.outcome==='tie').length,status:!hotels.length?'empty':gap===null?'excluded':gap>0?'loss':gap<0?'win':'tie'};
}
// Place nearby country/region labels without hiding their values behind one another.
function placeMapLabels(regions,viewBox){
  const [left,top,width,height]=viewBox.split(' ').map(Number),placed=[];
  return regions.map(region=>{
    const [x,y]=region.anchor,w=Math.max(52,region.name.length*7+12),h=34;
    const candidates=[region.labelOffset||[0,-13],[0,30],[-85,-25],[85,-25],[-90,35],[90,35],[0,65],[0,-65],[-130,75],[130,75],[-130,-75],[130,-75]];
    for(let radius=120;radius<=280;radius+=40){
      for(let angle=0;angle<8;angle++)candidates.push([Math.cos(angle*Math.PI/4)*radius,Math.sin(angle*Math.PI/4)*radius]);
    }
    for(const [dx,dy] of candidates){
      const lx=Math.max(left+w/2+4,Math.min(left+width-w/2-4,x+dx));
      const ly=Math.max(top+18,Math.min(top+height-22,y+dy));
      const box={x:lx-w/2,y:ly-14,w,h};
      if(placed.some(b=>box.x<b.x+b.w+5&&box.x+box.w+5>b.x&&box.y<b.y+b.h+5&&box.y+box.h+5>b.y))continue;
      placed.push(box);return {region,x,y,lx,ly,box};
    }
    return {region,x,y,lx:null,ly:null,box:null};
  });
}
