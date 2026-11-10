import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import test from 'node:test';
const source=fs.readFileSync(new URL('../src/rate_shopper/reporting/analytics-core.js',import.meta.url),'utf8');
const {median,summarizeRegion,hotelMapKey,statisticRows,placeMapLabels}=vm.runInNewContext(source+';({median,summarizeRegion,hotelMapKey,statisticRows,placeMapLabels})');
// Synthetic cases: coverage gaps must never become a zero-price advantage.
test('missing comparisons stay missing; an observed zero is a tie',()=>{
  assert.equal(median([null,undefined,NaN,Infinity]),null);
  assert.equal(median([null,0]),0);
  assert.equal(summarizeRegion([],[]).status,'empty');
  assert.equal(summarizeRegion([{id:'a'}],[{hotel_id:'a',percent_gap:null}]).status,'excluded');
  assert.equal(summarizeRegion([{id:'a'}],[{hotel_id:'a',percent_gap:'0',outcome:'tie'}]).status,'tie');
});
test('each hotel has equal weight regardless of competitor coverage',()=>{
  const rows=[1,2,3].map(()=>({hotel_id:'a',percent_gap:'10',outcome:'loss'}));
  rows.push({hotel_id:'b',percent_gap:'-30',outcome:'win'});
  const s=summarizeRegion([{id:'a'},{id:'b'}],rows);
  assert.equal(s.gap,-10);assert.equal(s.comparedHotels,2);assert.equal(s.pairs,4);
  assert.equal(s.status,'win');
  assert.equal(summarizeRegion([{id:'a'}],rows).gap,10);
});
test('Russian cities are separate from oblasts and Sochi maps to Krasnodar',()=>{
  assert.equal(hotelMapKey({country:'Россия',geo:'Москва'},'russia'),'RU-MOW');
  assert.equal(hotelMapKey({country:'Россия',geo:'Санкт-Петербург'},'russia'),'RU-SPE');
  assert.equal(hotelMapKey({country:'Россия',geo:'Сочи'},'russia'),'RU-KDA');
  assert.equal(hotelMapKey({country:'Турция'},'russia'),undefined);
  assert.equal(hotelMapKey({country:'Мальдивы'},'world'),'MDV');
  const maps=JSON.parse(fs.readFileSync(new URL('../src/rate_shopper/reporting/map-geometry.json',import.meta.url)));
  assert.equal(maps.russia.regions.find(r=>r.id==='RU-MOW').name,'Москва');
  assert.equal(maps.russia.regions.find(r=>r.id==='RU-SPE').name,'Санкт-Петербург');
});
test('switching price scopes uses the matching minima; strict mode clears unverified prices',()=>{
  const base={hotel_id:'a',platform:'yandex_travel',reference_total:'100',competitor_total:'80',percent_gap:'25',outcome:'loss'};
  const publicRow={...base,competitor_total:null,percent_gap:null,outcome:'excluded'};
  const report={statistics:{rows:[publicRow],scopes:{all:{rows:[base]},public:{rows:[publicRow]}},verified_rows:[]}};
  assert.equal(statisticRows(report,'all',false)[0].competitor_total,'80');
  assert.equal(statisticRows(report,'public',false)[0].percent_gap,null);
  const strict=statisticRows(report,'all',true)[0];
  assert.equal(strict.reference_total,null);assert.equal(strict.competitor_total,null);
  assert.equal(strict.outcome,'excluded');assert.equal(strict.reason,'unverified');
});
test('every configured hotel has a map region and populated labels do not overlap',()=>{
  const {hotels}=JSON.parse(fs.readFileSync(new URL('../config/hotels.json',import.meta.url)));
  const maps=JSON.parse(fs.readFileSync(new URL('../src/rate_shopper/reporting/map-geometry.json',import.meta.url)));
  for(const kind of ['russia','world']){
    const relevant=hotels.filter(h=>kind==='world'||h.country==='Россия');
    for(const h of relevant)assert.ok(maps[kind].regions.some(r=>r.id===hotelMapKey(h,kind)),h.name);
    const regions=maps[kind].regions.filter(r=>relevant.some(h=>hotelMapKey(h,kind)===r.id));
    const labels=placeMapLabels(regions,maps[kind].viewBox);
    for(let i=0;i<labels.length;i++){
      const a=labels[i].box;if(!a)continue;
      for(const b of labels.slice(i+1).map(x=>x.box).filter(Boolean))assert.ok(a.x+a.w<=b.x||b.x+b.w<=a.x||a.y+a.h<=b.y||b.y+b.h<=a.y);
    }
  }
});

test('dense labels stay nearby and selected region can take first priority',()=>{
  const regions=Array.from({length:30},(_,i)=>({id:String(i),name:'Dense region '+i,anchor:[300,200]}));
  const labels=placeMapLabels(regions,'0 0 600 400');
  assert.ok(labels[0].box);
  assert.ok(labels.some(l=>l.box===null));
  assert.equal(labels.length,regions.length);
  for(const l of labels.filter(l=>l.box))assert.ok(Math.hypot(l.lx-l.x,l.ly-l.y)<=90);
  const selected=placeMapLabels([regions[29],...regions.slice(0,29)],'0 0 600 400');
  assert.equal(selected[0].region.id,'29');assert.ok(selected[0].box);
});
