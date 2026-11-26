import {saveFile, supportsFileShare} from './file-save.mjs';
const $ = id => document.getElementById(id);
const LIMIT = 1024 * 1024;
let pdfjs, running = false, cancelled = false, activeRender, resultURL, resultBlob, resultName, resultFile;
const status = message => { $('status').textContent = message; };
const yieldUI = () => new Promise(resolve => setTimeout(resolve, 0));
const kb = bytes => `${(bytes / 1024).toFixed(1)} KB`;
function ensureRunning() { if (cancelled) throw new Error('已停止，原文件未修改。'); }
async function jpeg(canvas, quality) {
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', quality));
  if (!blob) throw new Error('手机未能编码页面图片，可能内存不足。');
  return new Uint8Array(await blob.arrayBuffer());
}
function detailRegions(text, pages) {
  const regions = new Map();
  for (const item of text.split(';').filter(s => s.trim())) {
    const [pageText, box, extra] = item.split(':');
    const page = Number(pageText), coords = (box || '').split(',').map(Number);
    const [left, top, right, bottom] = coords;
    if (extra !== undefined || !Number.isInteger(page) || page < 1 || page > pages ||
        coords.length !== 4 || !(0 <= left && left < right && right <= 100 && 0 <= top && top < bottom && bottom <= 100))
      throw new Error('局部区域请按 页码:左,上,右,下 填写，坐标为 0 到 100 的百分比');
    if (!regions.has(page)) regions.set(page, []);
    regions.get(page).push(coords);
  }
  return regions;
}
async function budgetJpeg(canvas, budget) {
  let low = .16, high = .92, best = await jpeg(canvas, low);
  for (let i = 0; i < 5; i++) {
    ensureRunning();
    const mid = (low + high) / 2;
    const data = await jpeg(canvas, mid);
    if (data.length <= budget) { best = data; low = mid; }
    else high = mid;
  }
  return best;
}
async function verify(bytes, source, label) {
  const task = pdfjs.getDocument({ data: bytes.slice(), isEvalSupported: false });
  const doc = await task.promise;
  try {
    if (doc.numPages !== source.numPages) throw new Error('输出页数不一致，已停止。');
    for (let n = 1; n <= doc.numPages; n++) {
      ensureRunning(); status(`${label}：检查页面 ${n}/${doc.numPages}`);
      const a = await source.getPage(n), b = await doc.getPage(n);
      const av = a.getViewport({scale: 1}), bv = b.getViewport({scale: 1});
      if (Math.abs(av.width - bv.width) > .1 || Math.abs(av.height - bv.height) > .1 || a.rotate !== b.rotate || a.view.some((v,i)=>Math.abs(v-b.view[i])>.1)) throw new Error(`第 ${n} 页尺寸或方向检查失败。`);
      const c = document.createElement('canvas'), viewport = b.getViewport({scale: Math.min(.3, 600 / Math.max(bv.width,bv.height))});
      c.width = Math.ceil(viewport.width); c.height = Math.ceil(viewport.height);
      try { activeRender = b.render({canvasContext:c.getContext('2d'), viewport}); await activeRender.promise; }
      finally { activeRender=null; c.width=c.height=1; b.cleanup(); }
      await yieldUI();
    }
  } finally { await task.destroy(); }
}
async function compress(file, mode, focusPages = new Set()) {
  const sourceBytes = new Uint8Array(await file.arrayBuffer());
  // Already small files need no lossy conversion; still validate all pages.
  const task = pdfjs.getDocument({ data:sourceBytes.slice(), isEvalSupported:false, cMapUrl:'./vendor/cmaps/', cMapPacked:true, standardFontDataUrl:'./vendor/standard_fonts/', wasmUrl:'./vendor/wasm/' });
  task.onPassword = () => { task.destroy(); };
  const source = await task.promise;
  try {
    if (source.numPages > 100) throw new Error('手机模式最多处理 100 页，请使用电脑版本。');
    if([...focusPages].some(n=>!Number.isInteger(n)||n<1||n>source.numPages))throw new Error('重点页码超出范围或格式不正确，请填写如 3,11');
    const regions = detailRegions(String($('regions').value || ''), source.numPages);
    if (regions.size && mode !== 'target') throw new Error('局部区域需要选择大小优先模式');
    const weights = source.numPages + focusPages.size * 1.8;
    const profiles = mode === 'target' ? [[140,.7],[110,.5],[100,.4],[90,.32],[85,.2],[80,.2]] : [[160,.75],[130,.65],[110,.55],[100,.5]];
    if (sourceBytes.length <= LIMIT) {
      await verify(sourceBytes, source, '原文件已达标');
      return {bytes:sourceBytes,pages:source.numPages,original:true};
    }
    let best;
    for (let attempt=0; attempt<profiles.length; attempt++) {
      ensureRunning();
      const [dpi,quality] = profiles[attempt];
      const output = await PDFLib.PDFDocument.create();
      for (let n=1; n<=source.numPages; n++) {
        ensureRunning(); status(`方案 ${attempt+1}/${profiles.length} · 压缩第 ${n}/${source.numPages} 页`);
        $('progress').value = ((attempt+(n-1)/source.numPages)/profiles.length)*90;
        const page = await source.getPage(n);
        const base = page.getViewport({scale:1,rotation:0});
        const focused=focusPages.has(n);
        const pageDpi=focused?Math.max(180,dpi*1.8):dpi;
        const scale = Math.min(pageDpi/72, Math.sqrt(3000000/(base.width*base.height)), 2400/Math.max(base.width,base.height));
        const viewport=page.getViewport({scale,rotation:0});
        const canvas=document.createElement('canvas');
        canvas.width=Math.ceil(viewport.width); canvas.height=Math.ceil(viewport.height);
        try {
          activeRender=page.render({canvasContext:canvas.getContext('2d',{alpha:false}),viewport,background:'rgb(255,255,255)'});
          await activeRender.promise; activeRender=null; ensureRunning();
          const parts = [];
          for (const [l,t,r,b] of regions.get(n) || []) {
            const patch = document.createElement('canvas');
            const factor = Math.min(200/72, 2400/base.width, 2400/base.height);
            const pv = page.getViewport({scale:factor,rotation:0});
            patch.width = Math.max(1,Math.ceil(pv.width*(r-l)/100));
            patch.height = Math.max(1,Math.ceil(pv.height*(b-t)/100));
            try {
              activeRender = page.render({canvasContext:patch.getContext('2d'), viewport:pv,
                transform:[1,0,0,1,-pv.width*l/100,-pv.height*t/100],background:'white'});
              await activeRender.promise;
              parts.push({l,t,r,b,data:await jpeg(patch,.85)});
            } finally { activeRender=null; patch.width=patch.height=1; }
          }
          const budget = (LIMIT-1800-source.numPages*650)*(focused?2.8:1)/weights
            - parts.reduce((sum,p)=>sum+p.data.length+350,0);
          const data = mode === 'target' ? await budgetJpeg(canvas,budget) : await jpeg(canvas,focused?Math.max(.75,quality):quality);
          const image=await output.embedJpg(data);
          const [x0,y0,x1,y1]=page.view;
          const dest=output.addPage([x1-x0,y1-y0]);
          dest.setMediaBox(x0,y0,x1-x0,y1-y0);
          dest.setCropBox(x0,y0,x1-x0,y1-y0);
          dest.drawImage(image,{x:x0,y:y0,width:x1-x0,height:y1-y0});
          for (const {l,t,r,b,data} of parts) {
            dest.drawImage(await output.embedJpg(data),{x:x0+(x1-x0)*l/100,y:y0+(y1-y0)*(100-b)/100,
              width:(x1-x0)*(r-l)/100,height:(y1-y0)*(b-t)/100});
          }
          dest.setRotation(PDFLib.degrees(page.rotate));
        } finally { activeRender=null; canvas.width=canvas.height=1; page.cleanup(); }
        await yieldUI();
      }
      ensureRunning(); status(`方案 ${attempt+1} · 正在生成 PDF`);
      const bytes=await output.save({useObjectStreams:true});
      if (!best || bytes.length<best.bytes.length) best={bytes,pages:source.numPages,dpi,quality};
      if (best.bytes.length<=LIMIT) break;
      await yieldUI();
    }
    // Never replace a smaller original with a larger recompression.
    if (best.bytes.length>=sourceBytes.length) best={bytes:sourceBytes,pages:source.numPages,original:true};
    await verify(best.bytes,source,'重新打开并渲染验证');
    return best;
  } finally { await task.destroy(); }
}
$('file').addEventListener('change',()=>{
  const file=$('file').files[0];
  $('info').textContent=file?`${file.name} · ${kb(file.size)}`:'建议单个文件不超过 30MB、100 页。';
  $('result').hidden=true;
  if(resultURL) URL.revokeObjectURL(resultURL);
  resultURL=resultBlob=null;
  resultFile=null;
  $('previewCanvas').hidden=true;
});
$('cancel').onclick=()=>{cancelled=true; activeRender?.cancel(); status('正在停止，请稍候…');};
$('start').onclick=async()=>{
  const file=$('file').files[0];
  if(!file) {status('请先选择一个 PDF 文件。');return;}
  if(!file.name.toLowerCase().endsWith('.pdf')) {status('请选择 PDF 文件。');return;}
  if(file.size>30*1024*1024) {status('文件超过 30MB，建议使用电脑版本，避免手机内存不足。');return;}
  const focusPages=new Set(String($('focus').value||'').replaceAll('，',',').split(',').map(s=>s.trim()).filter(Boolean).map(Number));
  running=true;cancelled=false; $('file').disabled=$('mode').disabled=$('start').disabled=$('focus').disabled=true;
  $('cancel').hidden=false;$('result').hidden=true;$('progress').value=0;
  try {
    const result=await compress(file,$('mode').value,focusPages);ensureRunning();
    if(resultURL) URL.revokeObjectURL(resultURL);
    resultBlob=new Blob([result.bytes],{type:'application/pdf'});
    // Generic binary MIME discourages browsers from navigating into a PDF viewer.
    resultURL=URL.createObjectURL(new Blob([result.bytes],{type:'application/octet-stream'}));
    const ok=result.bytes.length<=LIMIT;
    resultName=file.name.replace(/\.pdf$/i,'')+(ok?'_compressed':'_OVER_LIMIT')+'.pdf';
    resultFile=new File([resultBlob],resultName,{type:'application/pdf'});
    $('compat').href=resultURL;$('compat').download=resultName;
    $('saveStatus').textContent='请点击保存按钮，选择系统提供的保存位置；结果仍在当前页面内存中。';
    $('previewCanvas').hidden=true;
    $('tag').textContent=ok?'已达到 1024KB 目标':'处理完成，仍超过 1024KB';
    $('size').textContent=kb(result.bytes.length);
    $('details').textContent=`共 ${result.pages} 页，已逐页重新打开并渲染检查。${result.original?'保留原文件，未进行有损转换。':'已转为整页图片，文字不可复制，链接和交互功能丢失；小字及二维码需人工复核。'}${ok?'':'已到预设方案下限，不再降低画质。'}`;
    $('result').hidden=false;$('progress').value=100;status('处理完成，原文件未修改。');
    $('share').hidden=!supportsFileShare(resultFile);
  } catch(e) { status(cancelled?'已停止，原文件未修改。':`未能完成：${e.name==='PasswordException'?'暂不支持加密 PDF':e.message}。可尝试较小文件或电脑版本。`); }
  finally {running=false; $('file').disabled=$('mode').disabled=$('start').disabled=$('focus').disabled=false;$('cancel').hidden=true;}
};
function saveError(e) {
  $('saveStatus').textContent=e.name==='AbortError'?'已取消保存，结果仍在，可再次点击保存。':'当前浏览器未能保存。请尝试下方系统分享或备用下载；若仍跳到 blob 空白页，请用 Chrome / Edge / Safari 重新打开工具。';
}
$('download').onclick=async()=>{
  if(!resultFile)return;
  try {
    const mode=await saveFile(resultFile);
    if(mode==='download') {
      $('compat').click();
      $('saveStatus').textContent='已请求浏览器下载，请检查下载列表。若未保存，请换用支持文件分享或下载的浏览器重试。';
    } else $('saveStatus').textContent=mode==='saved'?'文件已写入所选位置。':'系统分享已结束，请确认文件已存储到文件管理器。';
  } catch(e){saveError(e);}
};
$('share').onclick=async()=>{if(!resultFile)return;try{await navigator.share({files:[resultFile]});$('saveStatus').textContent='系统分享已结束，请检查保存位置。';}catch(e){saveError(e);}};
$('preview').onclick=async()=>{
  if(!resultBlob)return;
  $('preview').disabled=true;
  let task;
  try {
    task=pdfjs.getDocument({data:new Uint8Array(await resultBlob.arrayBuffer()),isEvalSupported:false});
    const doc=await task.promise, page=await doc.getPage(1);
    const base=page.getViewport({scale:1}), viewport=page.getViewport({scale:Math.min(1.5,1400/Math.max(base.width,base.height))});
    const canvas=$('previewCanvas');canvas.width=Math.ceil(viewport.width);canvas.height=Math.ceil(viewport.height);
    await page.render({canvasContext:canvas.getContext('2d'),viewport}).promise;
    canvas.hidden=false;
  } catch(e){$('saveStatus').textContent='首页预览失败，请先保存后使用 PDF 阅读器检查。';}
  finally {await task?.destroy();$('preview').disabled=false;}
};
window.addEventListener('beforeunload',e=>{if(running){e.preventDefault();e.returnValue='';}});
try {
  pdfjs=await import('./vendor/pdf.mjs');
  pdfjs.GlobalWorkerOptions.workerSrc=new URL('./vendor/pdf.worker.mjs',import.meta.url).href;
  if(!window.PDFLib || !HTMLCanvasElement.prototype.toBlob)throw new Error('浏览器缺少所需能力');
  $('start').disabled=false;$('start').textContent='开始本地压缩';status('已就绪。请选择 PDF；处理期间请保持此页面在前台。');
} catch(e){status('组件加载失败，请联网刷新，或换用较新的 Safari / Chrome。');$('start').textContent='暂时无法启动';}
