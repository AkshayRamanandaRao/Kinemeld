import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const base=process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:960}}), errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
try{
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent==='Ready');
 const examples=await (await page.request.get(base+'/api/examples')).json(),model=examples.examples.find(item=>item.id==='mass-spring').model;
 const upload={name:'candidate.mbdyn-studio',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({format:'mbdyn-studio/1',model}))};
 await page.locator('#field-angle').fill('31');await page.locator('#field-angle').press('Tab');
 let dialogCount=0;page.once('dialog',async dialog=>{dialogCount++;assert.match(dialog.message(),/unsaved model, geometry and results/);await dialog.dismiss();});
 await page.locator('#projectFile').setInputFiles(upload);await page.waitForTimeout(200);assert.equal(dialogCount,1);assert.equal(await page.locator('#field-angle').inputValue(),'31');
 let release;const blocked=new Promise(resolve=>release=resolve);let requestSeen;const seen=new Promise(resolve=>requestSeen=resolve);
 await page.route('**/api/validate',async route=>{const data=route.request().postDataJSON();if(data?.model?.kind==='mass-spring'){requestSeen();await blocked;}await route.continue();});
 page.once('dialog',dialog=>dialog.accept());await page.locator('#projectFile').setInputFiles(upload);await seen;
 await page.locator('#field-angle').fill('32');await page.locator('#field-angle').press('Tab');release();
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('your edits were kept'));assert.equal(await page.locator('#field-angle').inputValue(),'32');assert.deepEqual(errors,[]);console.log('Browser import confirmation and in-flight edit protection passed');
}finally{await browser.close();}
