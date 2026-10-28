/** STEP-only selection and safe restoration of older STL-reference projects. */
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const evidence=fileURLToPath(new URL('./evidence/',import.meta.url));
await mkdir(evidence,{recursive:true});
const report={started:new Date().toISOString(),checks:[],errors:[]};
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:960},acceptDownloads:true});
page.on('pageerror',error=>report.errors.push(error.message));
await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
const source=await readFile(new URL('../examples/step-pendulum/pendulum.step',import.meta.url));
const sourceHash=createHash('sha256').update(source).digest('hex');
const mesh=Buffer.from('solid sample\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 10 0 0\nvertex 0 10 0\nendloop\nendfacet\nendsolid sample\n');
const legacyReference={schemaVersion:1,format:'stl',name:'saved-reference.stl',unit:'mm',data:mesh.toString('base64'),sha256:createHash('sha256').update(mesh).digest('hex'),byteLength:mesh.length,triangleCount:1};
let conversions=0;
page.on('request',request=>{if(request.url().endsWith('/api/step/convert')) conversions++;});
async function save(name) {
 const event=page.waitForEvent('download');await page.locator('#saveButton').click();
 const download=await event, location=path.join(evidence,name);await download.saveAs(location);
 return {location,project:JSON.parse(await readFile(location,'utf8'))};
}
async function open(project) {
 page.on('dialog', dialog=>dialog.accept());await page.locator('#projectFile').setInputFiles({name:'saved-project.mbdyn-studio',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(project))});
}
try {
 await page.goto(process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768');
 await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent==='Ready');
 for(const id of ['referenceImportButton','referenceUnit','referenceFile']) assert.equal(await page.locator(`#${id}`).count(),0);
 assert.equal(await page.locator('#stepFile').getAttribute('accept'),'.step,.stp');
 await page.locator('#examplesButton').click();
 assert.equal(await page.getByRole('heading',{name:'NASA Mars 2020 wheel',exact:true}).count(),0);
 await page.locator('#examplesDialog [data-close]').first().click();
 const before=(await save('step-only-before.mbdyn-studio')).project;
 await page.locator('#stepButton').click();
 assert.match(await page.locator('#stepDetail').textContent(),/mass, inertia and joints separately/);
 await page.locator('#stepFile').setInputFiles([{name:'pendulum.step',mimeType:'application/step',buffer:source},{name:'new-reference.stl',mimeType:'model/stl',buffer:mesh}]);
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Choose STEP geometry files'));
 assert.equal(conversions,0,'Reject a mixed non-STEP selection before converting any file');
 assert(await page.locator('#stepStatus').isHidden());assert(await page.locator('#referenceStatus').isHidden());
 report.checks.push({name:'STEP-only new selection: old STL controls and NASA card absent; mixed selection rejected atomically',ok:true});
 await page.locator('#stepFile').setInputFiles({name:'pendulum.STP',mimeType:'application/step',buffer:source});
 await page.waitForFunction(()=>document.querySelector('#stepDetail')?.textContent.includes('1 STEP files'),null,{timeout:120000});
 assert.match(await page.locator('#stepDetail').textContent(),/Define mass, inertia and joints in the physical model/);
 assert.match(await page.locator('#stepStatus').textContent(),/visual geometry/);
 await page.locator('#stepClose').click();
 const stepSaved=await save('step-only-source.mbdyn-studio');
 assert.deepEqual(stepSaved.project.model,before.model,'STEP import must not silently change solver properties');
 assert.equal(stepSaved.project.assets.step.files[0].name,'pendulum.STP');
 assert.equal(stepSaved.project.assets.step.files[0].sha256,sourceHash);
 assert.deepEqual(Buffer.from(stepSaved.project.assets.step.files[0].data,'base64'),source);
 assert.equal(stepSaved.project.assets.reference,undefined);
 report.checks.push({name:'Real uppercase .STP import converts locally, preserves exact bytes/digest and leaves physics unchanged',ok:true});
 const legacy=structuredClone(stepSaved.project);legacy.assets.reference=legacyReference;
 await open(legacy);
 await page.waitForFunction(()=>document.querySelector('#referenceStatus')?.textContent.includes('saved-reference.stl (mm)'),null,{timeout:120000});
 assert.match(await page.locator('#referenceStatus').textContent(),/Saved STL reference.*visual only/);
 assert.match(await page.locator('#stepStatus').textContent(),/STEP solids/);
 await page.locator('#referenceIsolateButton').click();assert.equal(await page.locator('#referenceIsolateButton').textContent(),'Show model');
 await page.locator('#referenceIsolateButton').click();
 const combined=await save('legacy-reference-and-step.mbdyn-studio');
 assert.deepEqual(combined.project.model,before.model);assert.deepEqual(combined.project.assets.reference,legacyReference);
 assert.deepEqual(combined.project.assets.step,stepSaved.project.assets.step);
 await page.locator('#referenceRemoveButton').click();assert(await page.locator('#referenceStatus').isHidden());
 await page.locator('#projectFile').setInputFiles(combined.location);
 await page.waitForFunction(()=>document.querySelector('#referenceStatus')?.textContent.includes('saved-reference.stl'),null,{timeout:120000});
 report.checks.push({name:'Saved STL references restore, isolate, remove and round-trip alongside exact STEP sources',ok:true});
 const tampered=structuredClone(legacy);tampered.model.parameters.length=2;tampered.assets.reference.sha256='0'.repeat(64);
 await open(tampered);await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project was not opened'));
 assert.equal(await page.locator('#field-length').inputValue(),'1');assert.match(await page.locator('#referenceStatus').textContent(),/saved-reference.stl/);
 const afterFailure=await save('step-only-after-rejected-project.mbdyn-studio');
 assert.deepEqual(afterFailure.project.model,before.model);assert.deepEqual(afterFailure.project.assets,combined.project.assets);
 report.checks.push({name:'Corrupt legacy reference rejected before model or geometry replacement',ok:true});
 await page.screenshot({path:path.join(evidence,'step-only-legacy-compatibility.png')});
 assert.deepEqual(report.errors,[]);report.ok=true;console.log(JSON.stringify({ok:true,checks:report.checks.length,conversions}));
} catch(error) {report.ok=false;report.failure=error.stack;process.exitCode=1;console.error(error);await page.screenshot({path:path.join(evidence,'reference-ui-failure.png'),fullPage:true}).catch(()=>{});}
finally {report.completed=new Date().toISOString();await writeFile(path.join(evidence,'reference-ui-verification.json'),JSON.stringify(report,null,2));await browser.close();}
