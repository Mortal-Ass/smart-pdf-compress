import {test} from 'node:test';
import assert from 'node:assert/strict';
import {saveFile,supportsFileShare} from '../docs/file-save.mjs';
const file=new File(['%PDF-1.7\n'],'证书.pdf',{type:'application/pdf'});
test('picker writes original bytes then closes',async()=>{
  const calls=[];
  const env={showSaveFilePicker:async opts=>{assert.equal(opts.suggestedName,file.name);return {createWritable:async()=>({write:async data=>calls.push(data),close:async()=>calls.push('close')})};}};
  assert.equal(await saveFile(file,env,{}),'saved');assert.deepEqual(calls,[file,'close']);
});
test('file sharing receives a File, not a blob URL',async()=>{
  let sent;const nav={canShare:data=>data.files[0]===file,share:async data=>{sent=data;}};
  assert.equal(await saveFile(file,{},nav),'shared');assert.equal(sent.files[0],file);assert.equal(sent.url,undefined);
});
test('unsupported file APIs choose explicit download',async()=>{
  assert.equal(await saveFile(file,{},{}),'download');
  assert.equal(supportsFileShare(file,{canShare(){throw Error('unsupported');},share(){}}),false);
});
test('picker cancellation does not unexpectedly trigger sharing',async()=>{
  let shares=0;const error=new DOMException('cancel','AbortError');
  await assert.rejects(saveFile(file,{showSaveFilePicker:()=>Promise.reject(error)},{share(){shares++;},canShare:()=>true}),{name:'AbortError'});
  assert.equal(shares,0);
});
test('failed write aborts the file',async()=>{
  let aborted=false;
  await assert.rejects(saveFile(file,{showSaveFilePicker:async()=>({createWritable:async()=>({write:async()=>{throw Error('disk full');},abort:async()=>{aborted=true;}})})},{}),/disk full/);
  assert.equal(aborted,true);
});
