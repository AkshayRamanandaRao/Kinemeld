import test from 'node:test';
import assert from 'node:assert/strict';
import {stepPartLabel,hasMultiPartBindings} from '../frontend/step-asset.js';

test('product labels retain the occurrence name to distinguish repeated instances',()=>{
 assert.equal(stepPartLabel({name:'NAUO10',productName:'Wheel'}),'Wheel · NAUO10');
 assert.equal(stepPartLabel({name:'NAUO11',productName:'Wheel'}),'Wheel · NAUO11');
 assert.equal(stepPartLabel({name:'gear.step · NAUO1',occurrenceName:'NAUO1',productName:'Piston'}),'Piston · gear.step · NAUO1');
});
test('missing or identical product names preserve the existing label',()=>{
 assert.equal(stepPartLabel({name:'Part 1',productName:null}),'Part 1');
 assert.equal(stepPartLabel({name:'one.step · Housing',occurrenceName:'Housing',productName:'Housing'}),'one.step · Housing');
});
test('warn only when a binding belongs to a source with multiple occurrences',()=>{
 const asset={parts:[{id:'0:part-1'},{id:'0:part-2'},{id:'1:part-1'}],metadata:{bindings:{'1:part-1':{}}}};
 assert.equal(hasMultiPartBindings(asset),false);asset.metadata.bindings['0:part-2']={};assert.equal(hasMultiPartBindings(asset),true);assert.equal(hasMultiPartBindings(null),false);
});
