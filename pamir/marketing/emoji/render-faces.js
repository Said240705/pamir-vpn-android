const {chromium}=require('playwright');const fs=require('fs');
(async()=>{const [dir,...items]=process.argv.slice(2);const b=await chromium.launch();
const p=await b.newPage({viewport:{width:100,height:100}});p.on('pageerror',e=>console.log('ERR',e.message));
await p.goto('file://'+dir+'/e.html');await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(300);
for(const it of items){const [name,arg]=it.split(':');const out=`${dir}/fr/${it.replace(':','')}`;fs.rmSync(out,{recursive:true,force:true});fs.mkdirSync(out,{recursive:true});
 for(let i=0;i<60;i++){await p.evaluate(([n,t,a])=>render(n,t,a),[name,i/30,arg]);await p.screenshot({path:`${out}/f${String(i).padStart(3,'0')}.png`,omitBackground:true});}}
await b.close()})();
