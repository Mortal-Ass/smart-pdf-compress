// Engine integration test using native canvas and a minimal DOM adapter.
// This does not replace Safari / Chrome browser testing.
const fs=require('node:fs');
const path=require('node:path');
const canvas=require('@napi-rs/canvas');
Object.assign(globalThis,{DOMMatrix:canvas.DOMMatrix,ImageData:canvas.ImageData,Path2D:canvas.Path2D});
globalThis.PDFLib=require('pdf-lib');
const controls=new Map();
function el(id){if(!controls.has(id))controls.set(id,{textContent:'',value:0,hidden:false,disabled:false,addEventListener(){}});return controls.get(id);}
globalThis.document={getElementById:el,createElement(name){
  if(name!=='canvas')throw Error(name);
  const c=canvas.createCanvas(1,1);
  c.toBlob=(cb,type,q)=>cb(new Blob([c.toBuffer('image/jpeg',Math.round(q*100))],{type}));
  return c;
}};
globalThis.HTMLCanvasElement={prototype:{toBlob(){}}};
globalThis.window={PDFLib:globalThis.PDFLib,addEventListener(){},requestAnimationFrame:cb=>setTimeout(cb,0),cancelAnimationFrame:clearTimeout};
let output;
URL.createObjectURL=blob=>{output=blob;return 'blob:local-test';};
URL.revokeObjectURL=()=>{};
(async()=>{
  process.chdir(path.join(__dirname,'../docs'));
  await import('../docs/app.js');
  if(el('start').disabled || el('start').textContent!=='开始本地压缩')throw Error(el('status').textContent);
  const input=path.resolve(process.argv[2]);
  el('file').files=[new File([fs.readFileSync(input)],path.basename(input),{type:'application/pdf'})];
  el('mode').value='target';
  el('focus').value=process.env.FOCUS_PAGES||'';
  await el('start').onclick();
  if(el('result').hidden || !output)throw Error(el('status').textContent);
  const bytes=Buffer.from(await output.arrayBuffer());
  fs.writeFileSync(process.argv[3],bytes);
  console.log(JSON.stringify({size:bytes.length,status:el('status').textContent,details:el('details').textContent}));
})().catch(e=>{console.error(e);process.exitCode=1;});
