import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
const base=process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:960}}), errors=[];
page.on('pageerror',e=>errors.push(e.message));
const report={checks:[],started:new Date().toISOString()};
try {
 await page.goto(base); await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
 await page.locator('#examplesButton').click();
 await page.locator('.example-card').filter({has:page.getByRole('heading',{name:'Authored rigid pendulum',exact:true})}).getByRole('button',{name:/Open example/}).click();
 await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent==='Ready');
 assert.equal(await page.locator('#previewButton').isDisabled(),true);
 assert(await page.locator('#graph-body-upper_link-mass').isVisible());
 await page.getByRole('button',{name:'Add body + revolute hinge'}).click();
 assert(await page.locator('[data-entity="node-body1"]').isVisible());
 await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent==='Ready');
 await page.locator('#durationInput').fill('1'); await page.locator('#durationInput').dispatchEvent('change');
 const runResponse=page.waitForResponse(r=>r.url().endsWith('/api/run')&&r.request().method()==='POST',{timeout:120000});
 await page.locator('#runButton').click(); const result=await (await runResponse).json();
 assert.equal(result.ok,true,JSON.stringify(result)); assert.equal(result.samples[0].nodes.length,2);
 assert(result.samples.every(s=>Number.isFinite(s.jointError)&&s.jointError<1e-5));
 await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
 assert.equal(await page.locator('#nodeSelect').isHidden(),false); assert.equal(await page.locator('#nodeSelect option').count(),2);
 await page.locator('#nodeSelect').selectOption('body1'); assert.match(await page.locator('#sourceProbe').textContent(),/Node body1/);
 report.checks.push('Authored two-body chain solved in MBDyn, constraints and node postprocessing checked');
 await page.locator('#graph-body-body1-mass').fill('-1'); await page.locator('#graph-body-body1-mass').press('Tab');
 await page.locator('#validateButton').click(); await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent==='Needs attention');
 assert.match(await page.locator('#issuesList').textContent(),/mass/i); await page.locator('#issuesList button').first().click();
 assert.equal(await page.evaluate(()=>document.activeElement.id),'graph-body-body1-mass');
 await page.locator('#undoButton').click(); await page.waitForFunction(()=>document.querySelector('#validationBadge')?.textContent==='Ready');
 report.checks.push('Invalid body mass produces actionable diagnostics and Undo restores the model');
 await page.locator('[data-entity="body"]').click(); await page.getByRole('button',{name:'Remove selected body'}).click();
 assert.match(await page.locator('#notice').textContent(),/child links/i);
 assert.deepEqual(errors,[]); report.ok=true;
} catch(e) { report.ok=false;report.failure=e.stack;process.exitCode=1;console.error(e);await page.screenshot({path:'tests/evidence/assembly-ui-failure.png',fullPage:true}).catch(()=>{}); }
finally { report.errors=errors; report.completed=new Date().toISOString();await mkdir('tests/evidence',{recursive:true});await writeFile('tests/evidence/assembly-ui-verification.json',JSON.stringify(report,null,2));await browser.close();}

