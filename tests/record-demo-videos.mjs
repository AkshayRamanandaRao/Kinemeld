import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdtemp, mkdir, realpath, rm, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { execFileSync } from 'node:child_process';

// Recording scrubs actual MBDyn result samples slowly enough to inspect each study.
const base=process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:18996';
const ffmpeg=process.env.FFMPEG || execFileSync('python',['-c','import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'],{encoding:'utf8'}).trim();
const output=resolve('docs/demos'), frames=72, fps=12;
const examples=[
  {name:'aircraft-nose-gear',project:'examples/open-aircraft-nose-kinematics/nose-gear-kinematics.mbdyn-studio',attached:11,entity:'joint-oleo',signal:'Slider position (reconstructed)',field:'jointSelect',value:'oleo'},
  {name:'double-wishbone',project:'examples/open-suspension/suspension.mbdyn-studio',attached:5,field:'nodeSelect',value:'wheel'},
  {name:'wheel-end',project:'examples/open-wheel-end/wheel-end.mbdyn-studio',attached:3,entity:'torque-drive',signal:'Node angular velocity · X / Y / Z',field:'nodeSelect',value:'wheel'},
  {name:'oleo-strut',project:'examples/oleo-strut/wheel-oleo.mbdyn-studio',attached:3,entity:'force-oleo',signal:'Oleo gas pressure (native)',field:'forceSelect',value:'oleo'}
];
const target=process.argv[2];
if(target && !examples.some(item=>item.name===target))throw Error(`Unknown demo: ${target}`);
await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
try {
  for(const item of examples.filter(value=>!target || value.name===target)) {
    const folder=await mkdtemp(join(tmpdir(),'kinemeld-demo-'));
    const page=await browser.newPage({viewport:{width:1440,height:1200}}),errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    page.on('dialog',dialog=>dialog.accept());
    await page.route('**/api/tour-preference',route=>route.fulfill({json:{enabled:false}}));
    try {
      await page.goto(base);await page.waitForFunction(()=>document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
      await page.locator('#projectFile').setInputFiles(item.project);
      await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('Project imported and validated'),null,{timeout:240000});
      assert.match(await page.locator('#stepStatus').textContent(),new RegExp(`${item.attached} attached`));
      const response=page.waitForResponse(result=>result.url().endsWith('/api/run') && result.request().method()==='POST',{timeout:180000});
      await page.locator('#runButton').click();const result=await (await response).json();assert(result.ok,JSON.stringify(result));
      await page.waitForFunction(()=>document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
      assert(result.samples.length>=frames,'Too few actual solver samples for this recording.');
      const initial=new Map(result.samples[0].nodes.map(node=>[node.id,node]));
      assert(result.samples.some(sample=>sample.nodes.some(node=>['x','y','z','rx','ry','rz'].some(key=>Math.abs(node[key]-initial.get(node.id)[key])>1e-7))),'Solver response does not contain visible body motion.');
      if(item.entity)await page.locator(`[data-entity="${item.entity}"]`).click();
      if(item.signal)await page.locator('#signalSelect').selectOption({label:item.signal});
      if(item.field)await page.locator(`#${item.field}`).selectOption(item.value);
      if(item.name==='double-wishbone') {
        const box=await page.locator('canvas').first().boundingBox();
        if(box){await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.5+220,box.y+box.height*.5,{steps:15});await page.mouse.up();await page.waitForTimeout(2000);}
      }
      const slider=page.locator('#timeSlider');
      for(let i=0;i<frames;i++) {
        await slider.fill(String(Math.round(i*(result.samples.length-1)/(frames-1))));await slider.dispatchEvent('input');
        await page.screenshot({path:join(folder,`frame-${String(i).padStart(3,'0')}.png`)});
      }
      assert.deepEqual(errors,[]);
      const mp4=join(output,`${item.name}.mp4`),gif=join(output,`${item.name}.gif`);
      const label="drawtext=fontfile=frontend/fonts/IBMPlexSans-Variable.ttf:text='SLOW PLAYBACK - MBDyn result':fontcolor=white:fontsize=18:box=1:boxcolor=black@0.75:boxborderw=8:x=w-tw-16:y=92";
      execFileSync(ffmpeg,['-hide_banner','-loglevel','error','-y','-framerate',String(fps),'-i',join(folder,'frame-%03d.png'),'-vf',`scale=1280:-2:flags=lanczos,${label}`,'-c:v','libx264','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',mp4],{stdio:'inherit'});
      execFileSync(ffmpeg,['-hide_banner','-loglevel','error','-y','-i',mp4,'-filter_complex','fps=6,scale=864:-2:flags=lanczos,split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle','-loop','0',gif],{stdio:'inherit'});
      for(const file of [mp4,gif]) {assert((await stat(file)).size>1000,`Empty recording: ${file}`);execFileSync(ffmpeg,['-hide_banner','-loglevel','error','-i',file,'-f','null','-'],{stdio:'inherit'});}
      console.log(`${item.name}: ${frames} solver frames, ${result.samples.at(-1).time} s simulation; MP4 ${(await stat(mp4)).size} bytes; GIF ${(await stat(gif)).size} bytes`);
    } finally {
      await page.close();
      const baseTemp=await realpath(tmpdir()), targetTemp=await realpath(folder);
      if(!targetTemp.startsWith(join(baseTemp,'kinemeld-demo-')))throw Error('Refusing to remove a recording directory outside the configured temporary folder.');
      await rm(targetTemp,{recursive:true,force:true});
    }
  }
} finally {await browser.close();}
