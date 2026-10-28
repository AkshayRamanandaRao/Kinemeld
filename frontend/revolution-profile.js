import { polygonProfile } from './polygon-extrusion.js';

/** Integrate a simple radial/axial polygon for a complete body of revolution. */
export function revolutionProfile(vertices) {
  polygonProfile(vertices);
  if(vertices.some(p=>p.x<0))throw Error('Revolution radii must be nonnegative.');
  const zeros=vertices.map((p,i)=>p.x===0?i:-1).filter(i=>i>=0),n=vertices.length;
  if(zeros.length&&zeros.filter(i=>!zeros.includes((i-1+n)%n)).length>1)throw Error('The profile may touch the rotation axis in only one continuous boundary section.');
  const origin=vertices[0].y,points=vertices.map(p=>({x:p.x,y:p.y-origin})),fac=[1,1,2,6,24,120];
  const choose=(p,i)=>fac[p]/(fac[i]*fac[p-i]);
  function moment(p,q){let total=0;for(let k=0;k<n;k++){const a=points[k],b=points[(k+1)%n],cross=a.x*b.y-b.x*a.y;for(let i=0;i<=p;i++)for(let j=0;j<=q;j++)total+=cross*choose(p,i)*choose(q,j)*a.x**i*b.x**(p-i)*a.y**j*b.y**(q-j)*fac[i+j]*fac[p+q-i-j]/fac[p+q+2];}return total;}
  const sign=Math.sign(moment(0,0)),radial=sign*moment(1,0),radialZ=sign*moment(1,1),radialZ2=sign*moment(1,2),radial3=sign*moment(3,0);
  if(!Number.isFinite(radial)||radial<=0||!Number.isFinite(radial3)||radial3<=0)throw Error('Revolution profile must enclose positive volume.');
  const axial=radialZ2-radialZ**2/radial;if(!Number.isFinite(axial)||axial<=0)throw Error('Revolution inertia is invalid.');
  return {volume:2*Math.PI*radial,centerZ:origin+radialZ/radial,axial,radial3};
}
