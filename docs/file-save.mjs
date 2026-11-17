export function supportsFileShare(file, nav = navigator) {
  try { return typeof nav.share === 'function' && typeof nav.canShare === 'function' && nav.canShare({files:[file]}); }
  catch { return false; }
}

// Called directly from a user click, before any unrelated asynchronous work.
export async function saveFile(file, env = window, nav = navigator) {
  if (typeof env.showSaveFilePicker === 'function') {
    const handle = await env.showSaveFilePicker({suggestedName:file.name, types:[{description:'PDF 文件',accept:{'application/pdf':['.pdf']}}]});
    const writable = await handle.createWritable();
    try { await writable.write(file); await writable.close(); }
    catch(error) { try { await writable.abort(); } catch {} throw error; }
    return 'saved';
  }
  if (supportsFileShare(file, nav)) {
    await nav.share({files:[file]});
    return 'shared';
  }
  return 'download';
}
