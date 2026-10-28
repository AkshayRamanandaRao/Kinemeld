import { polygonProfile } from './polygon-extrusion.js';
import { revolutionProfile } from './revolution-profile.js';

/** Homogeneous solids centered at their centroid, with extrusion along local Z. */
export function massProperties(shape, density, dimensions) {
  if (typeof density !== 'number' || !Number.isFinite(density) || density <= 0 || density > 1e9) throw Error('Density must be a positive finite value up to 1e9 kg/m³.');
  if(shape==='revolution'){
    const p=revolutionProfile(dimensions?.vertices),mass=p.volume*density,iz=2*Math.PI*density*p.radial3,ix=iz/2+2*Math.PI*density*p.axial;
    if(!Number.isFinite(mass)||mass<.0001||mass>1e6||![ix,iz].every(v=>Number.isFinite(v)&&v>=1e-9&&v<=1e9))throw Error('Calculated mass or inertia is outside the supported simulation range.');
    return {mass,inertia:{xx:ix,yy:ix,zz:iz},volume:p.volume};
  }
  if(shape==='polygon-extrusion'){
    if(!dimensions || typeof dimensions.length!=='number' || !Number.isFinite(dimensions.length) || dimensions.length<=0 || dimensions.length>1000)throw Error('Enter a positive finite extrusion length up to 1,000 m.');
    const p=polygonProfile(dimensions.vertices),volume=p.area*dimensions.length,mass=volume*density,scale=density*dimensions.length,z=mass*dimensions.length**2/12;
    const inertia={xx:scale*p.ix+z,yy:scale*p.iy+z,zz:scale*(p.ix+p.iy),xy:-scale*p.ixy,xz:0,yz:0};
    if(!Number.isFinite(mass)||mass<.0001||mass>1e6||Object.values(inertia).some(v=>!Number.isFinite(v)||Math.abs(v)>1e9)||['xx','yy','zz'].some(k=>inertia[k]<1e-9))throw Error('Calculated mass or inertia is outside the supported simulation range.');
    return {mass,inertia,volume};
  }
  const required = {brick:['x','y','z'],cylinder:['radius','length'],sphere:['radius'],ellipsoid:['x','y','z'],'regular-extrusion':['radius','length','sides']}[shape];
  if (!required || !dimensions || typeof dimensions !== 'object' || required.some(key=>typeof dimensions[key] !== 'number' || !Number.isFinite(dimensions[key]) || dimensions[key] <= 0 || dimensions[key] > 1000)) throw Error('Enter positive finite dimensions up to 1,000 m.');
  if(shape==='regular-extrusion' && (!Number.isInteger(dimensions.sides) || dimensions.sides<3 || dimensions.sides>64))throw Error('A regular extrusion requires an integer from 3 to 64 sides.');
  const {x,y,z,radius:r,length:l}=dimensions;
  let volume, factors;
  if(shape==='brick') {volume=x*y*z;factors=[(y*y+z*z)/12,(x*x+z*z)/12,(x*x+y*y)/12];}
  else if(shape==='cylinder') {volume=Math.PI*r*r*l;factors=[(3*r*r+l*l)/12,(3*r*r+l*l)/12,r*r/2];}
  else if(shape==='sphere') {volume=4*Math.PI*r*r*r/3;factors=[2*r*r/5,2*r*r/5,2*r*r/5];}
  else if(shape==='regular-extrusion') {const angle=2*Math.PI/dimensions.sides;volume=dimensions.sides*r*r*Math.sin(angle)*l/2;const iz=r*r*(2+Math.cos(angle))/6;factors=[iz/2+l*l/12,iz/2+l*l/12,iz];}
  else {volume=4*Math.PI*x*y*z/3;factors=[(y*y+z*z)/5,(x*x+z*z)/5,(x*x+y*y)/5];}
  const mass=volume*density, moments=factors.map(value=>value*mass);
  if (!Number.isFinite(mass) || mass<0.0001 || mass>1e6 || moments.some(value=>!Number.isFinite(value)||value<1e-9||value>1e9)) throw Error('Calculated mass or inertia is outside the supported simulation range.');
  return {mass,inertia:{xx:moments[0],yy:moments[1],zz:moments[2]},volume};
}
