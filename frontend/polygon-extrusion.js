/** Validate one simple XY polygon and calculate centroidal area moments. */
export function polygonProfile(vertices) {
  if(!Array.isArray(vertices)||vertices.length<3||vertices.length>64)throw Error('Provide 3 to 64 distinct profile vertices.');
  if(vertices.some(p=>!p||Object.keys(p).sort().join(',')!=='x,y'||!['x','y'].every(k=>typeof p[k]==='number'&&Number.isFinite(p[k])&&Math.abs(p[k])<=1000)))throw Error('Each profile vertex needs finite x and y within ±1000 m.');
  const n=vertices.length,scale=Math.max(...['x','y'].map(k=>Math.max(...vertices.map(p=>p[k]))-Math.min(...vertices.map(p=>p[k]))));
  if(scale<=1e-9)throw Error('Profile must have nonzero size.');
  const eps=1e-12*scale*scale,orient=(a,b,c)=>(b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x),on=(a,b,p)=>p.x>=Math.min(a.x,b.x)-1e-12*scale&&p.x<=Math.max(a.x,b.x)+1e-12*scale&&p.y>=Math.min(a.y,b.y)-1e-12*scale&&p.y<=Math.max(a.y,b.y)+1e-12*scale;
  const intersects=(a,b,c,d)=>{const o=[orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)];if(((o[0]>eps&&o[1]<-eps)||(o[0]<-eps&&o[1]>eps))&&((o[2]>eps&&o[3]<-eps)||(o[2]<-eps&&o[3]>eps)))return true;return [[o[0],a,b,c],[o[1],a,b,d],[o[2],c,d,a],[o[3],c,d,b]].some(([v,x,y,p])=>Math.abs(v)<=eps&&on(x,y,p));};
  for(let i=0;i<n;i++){const a=vertices[i],b=vertices[(i+1)%n],c=vertices[(i+2)%n];if(Math.hypot(b.x-a.x,b.y-a.y)<=1e-9*scale)throw Error('Profile edges must have distinct endpoints.');if(Math.abs(orient(a,b,c))<=eps&&(b.x-a.x)*(c.x-b.x)+(b.y-a.y)*(c.y-b.y)<0)throw Error('Adjacent profile edges must not overlap.');for(let j=i+1;j<n;j++){if(j===i+1||(i===0&&j===n-1))continue;if(intersects(a,b,vertices[j],vertices[(j+1)%n]))throw Error('Profile edges must not intersect or touch.');}}
  const origin=vertices[0],v=vertices.map(p=>({x:p.x-origin.x,y:p.y-origin.y}));let cross=0,cx=0,cy=0,xx=0,yy=0,xy=0;
  for(let i=0;i<n;i++){const a=v[i],b=v[(i+1)%n],c=a.x*b.y-b.x*a.y;cross+=c;cx+=(a.x+b.x)*c;cy+=(a.y+b.y)*c;xx+=(a.x*a.x+a.x*b.x+b.x*b.x)*c;yy+=(a.y*a.y+a.y*b.y+b.y*b.y)*c;xy+=(2*a.x*a.y+a.x*b.y+b.x*a.y+2*b.x*b.y)*c;}
  if(Math.abs(cross)<=2*eps)throw Error('Profile area is too small or degenerate.');
  cx/=3*cross;cy/=3*cross;const sign=Math.sign(cross),area=Math.abs(cross)/2;
  return {area,centroid:{x:origin.x+cx,y:origin.y+cy},ix:sign*yy/12-area*cy*cy,iy:sign*xx/12-area*cx*cx,ixy:sign*xy/24-area*cx*cy};
}
