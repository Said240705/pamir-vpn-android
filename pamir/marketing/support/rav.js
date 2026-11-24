const {chromium}=require('playwright');const fs=require('fs');
(async()=>{const dir=process.cwd();const b=await chromium.launch();const p=await b.newPage({viewport:{width:512,height:512},deviceScaleFactor:2});
await p.goto('file://'+dir+'/st.html');await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(300);
fs.rmSync(dir+'/fa',{recursive:true,force:true});fs.mkdirSync(dir+'/fa');
await p.evaluate(()=>avatar(0.5));await p.screenshot({path:dir+'/avatar.png'});
for(let i=0;i<180;i++){await p.evaluate(t=>avatar(t),i/30);await p.screenshot({path:`${dir}/fa/f${String(i).padStart(3,'0')}.png`});}
await b.close()})();
