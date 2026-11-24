const {chromium}=require('playwright');const fs=require('fs');
(async()=>{const dir=process.cwd();const b=await chromium.launch();const p=await b.newPage({viewport:{width:512,height:512}});p.on('pageerror',e=>console.log('ERR',e.message));
await p.goto('file://'+dir+'/st.html');await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(400);
for(const n of process.argv.slice(2)){const out=`${dir}/fs/${n}`;fs.rmSync(out,{recursive:true,force:true});fs.mkdirSync(out,{recursive:true});
 for(let i=0;i<60;i++){await p.evaluate(([n,t])=>sticker(n,t),[n,i/30]);await p.screenshot({path:`${out}/f${String(i).padStart(3,'0')}.png`,omitBackground:true});}}
await b.close()})();
