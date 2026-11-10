"""Rendered desktop table adapter. Each column is one tariff, never a whole row."""

ROOM_SELECTOR = 'table[class*="Rates_table__"]'

DOM_CARDS = r"""() => Array.from(document.querySelectorAll('table[class*="Rates_table__"]'))
.flatMap(t => {
 let box=t.parentElement;
 while(box && !box.querySelector('[class*="RoomGroup_name__"]')) box=box.parentElement;
 const name=box?.querySelector('[class*="RoomGroup_name__"]')?.innerText;
 const header=box?.querySelector('[class*="RoomGroup_header__"]')?.innerText || '';
 // GURU's rowspan banner is advertising, not a bookable tariff column.
 const rows=Array.from(t.rows).map(r=>Array.from(r.cells)
   .filter(c=>!c.className.includes('Rates_cell_banner__')));
 if(!name || !rows.length || rows.some(r=>r.length!==rows[0].length ||
   r.some(c=>c.colSpan!==1 || c.rowSpan!==1))) return [];
 return rows[0].flatMap((_,i)=>{
   const cells=rows.map(r=>r[i]);
   const price=cells.find(c=>c.className.includes('Rates_cell_price__'));
   const book=cells.find(c=>c.className.includes('Rates_cell_book__'));
   if(!price || !book) return [];
   return [{text:name+'\n'+header+'\n'+cells[0].innerText,
     rates:[{text:cells.map(c=>c.innerText).join('\n'),price:price.innerText,
       meal:null,cancellation:null}]}];
 });
})"""
