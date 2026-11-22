const {chromium}=require('playwright');const fs=require('fs');
(async()=>{const dir=process.cwd();const b=await chromium.launch();const p=await b.newPage({viewport:{width:100,height:100}});p.on('pageerror',e=>console.log('ERR',e.message));
await p.goto('file://'+dir+'/i.html');await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(300);
const names=await p.evaluate(()=>NAMES);
for(const n of names){const out=`${dir}/fi/${n}`;fs.rmSync(out,{recursive:true,force:true});fs.mkdirSync(out,{recursive:true});
 for(let i=0;i<60;i++){await p.evaluate(([n,t])=>render(n,t),[n,i/30]);await p.screenshot({path:`${out}/f${String(i).padStart(3,'0')}.png`,omitBackground:true});}}
console.log(names.join(' '));await b.close()})();
