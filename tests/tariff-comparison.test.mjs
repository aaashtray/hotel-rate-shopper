import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import test from 'node:test';
const source=fs.readFileSync(new URL('../src/rate_shopper/reporting/tariff-comparison.js',import.meta.url),'utf8');
const {compareTariffs,candidateRank}=vm.runInNewContext(source+';({compareTariffs,candidateRank})');
// Synthetic cases for the UI classification, independent of strict matching.
const a={room_category_normalized:'classic',room_area_m2:'24',meal_plan:'none',
  cancellation_type:'free',payment_timing:'now',bed_type:'allocation_not_guaranteed',
  taxes_included:null,cancellation_deadline:null,access_type:'public'};
test('missing bed, taxes and deadline mean unconfirmed, not a different tariff',()=>{
  const c=compareTariffs(a,{...a,bed_type:null});
  assert.equal(c.kind,'similar');assert.equal(c.differences.length,0);
  assert(c.unknown.includes('тип кровати'));assert(c.unknown.includes('точный срок отмены'));
});
test('different room wording alone is not proof of different conditions',()=>{
  const c=compareTariffs(a,{...a,room_category_normalized:'классический номер'});
  assert.equal(c.kind,'similar');assert(c.unknown.includes('соответствие названий категории'));
});
test('known meal and payment differences are explained',()=>{
  const c=compareTariffs(a,{...a,meal_plan:'breakfast',payment_timing:'at_hotel'});
  assert.equal(c.kind,'different');assert(c.differences.includes('питание'));
  assert(c.differences.includes('оплата'));
});
test('unknown meal on both sides cannot establish similarity',()=>{
  assert.equal(compareTariffs({...a,meal_plan:null},{...a,meal_plan:null}).kind,'unknown');
});
test('prefer matching room name within candidates with similar conditions',()=>{
  const exact=candidateRank(a,a),other=candidateRank(a,{...a,room_category_normalized:'suite'});
  assert.equal(exact[0],other[0]);assert(exact[1]<other[1]);
});
test('bank and corporate access remain explicit differences',()=>{
  for(const access_type of ['bank','corporate']){
    const c=compareTariffs(a,{...a,access_type});
    assert(c.differences.includes('доступ к цене'));
  }
});
