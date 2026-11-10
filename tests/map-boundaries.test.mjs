import fs from 'node:fs';
import assert from 'node:assert/strict';
import test from 'node:test';

const maps=JSON.parse(fs.readFileSync(new URL('../src/rate_shopper/reporting/map-geometry.json',import.meta.url)));
// Geographic control points projected into the fixed 1000x560 map viewBoxes.
// Source-coordinate verification also runs in build-map-geometry.py before output.
const controls=[
  ['Crimea / Simferopol',34.10,44.95,[576.2659,148.2754],[22.9109,294.1318],'UKR'],
  ['Sevastopol',33.54,44.60,[575.1692,149.3227],[16.3481,292.2518],'UKR'],
  ['Donetsk',37.80,48.02,[582.8192,139.2513],[73.9227,298.5311],'UKR'],
  ['Luhansk',39.31,48.57,[585.8389,137.6666],[87.4265,304.5388],'UKR'],
  ['Kherson',32.62,46.64,[571.9378,143.2709],[33.5223,271.1414],'UKR'],
  ['Zaporizhzhia',35.14,47.84,[576.9441,139.7721],[58.5518,281.1597],'UKR'],
  ['Moscow',37.617,55.755,[577.0356,117.9682],[152.8968,237.4893],'RUS'],
  ['Saint Petersburg',30.335,59.934,[559.1806,107.4836],[170.8402,166.3160],'RUS'],
];
function contains(path,[x,y]){
  // Match SVG fill-rule=evenodd, including multipolygons and interior rings.
  let inside=false;
  for(const match of path.matchAll(/M([^Z]+)Z/g)){
    const ring=match[1].split('L').map(point=>point.split(',').map(Number));
    for(let i=0,j=ring.length-1;i<ring.length;j=i++){
      const [xi,yi]=ring[i],[xj,yj]=ring[j];
      if((yi>y)!==(yj>y)&&x<(xj-xi)*(y-yi)/(yj-yi)+xi)inside=!inside;
    }
  }
  return inside;
}
test('world SVG assigns Crimea and four Ukrainian oblasts to Ukraine',()=>{
  const ukraine=maps.world.regions.find(r=>r.id==='UKR');
  const russia=maps.world.regions.find(r=>r.id==='RUS');
  for(const [name,,,world,,country] of controls){
    assert.equal(contains(ukraine.path,world),country==='UKR',name+' in Ukraine');
    assert.equal(contains(russia.path,world),country==='RUS',name+' in Russia');
  }
});
test('Russian regional SVG excludes Ukrainian territory and retains Moscow and Petersburg',()=>{
  const forbidden=new Set(['UA-43','UA-40','UA-14','UA-09','UA-23','UA-65']);
  assert(!maps.russia.regions.some(r=>forbidden.has(r.id)));
  for(const [name,,,,regional,country] of controls){
    assert.equal(maps.russia.regions.some(r=>contains(r.path,regional)),country==='RUS',name);
  }
});
