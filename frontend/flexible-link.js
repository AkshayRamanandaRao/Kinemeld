import * as THREE from 'three';

/** Native FE nodes are connected directly; tube thickness is a display aid, not section CAD. */
export function buildFlexibleLink(view) {
  const p=view.model.parameters,L=p.length,parts={segments:[],nodes:[]};view.scale=L;view.flexibleParts=parts;
  view.mesh(new THREE.BoxGeometry(.07*L,.14*L,.16*L),0x687d94,new THREE.Vector3(-.035*L,0,0),'ground');
  for(let i=0;i<p.nodes;i++) {
    const node=view.mesh(new THREE.SphereGeometry(.012*L,16,12),i===0?0xe08a1e:0x147dcc,new THREE.Vector3(),i===0?'joint':`node-flex${i+1}`);
    parts.nodes.push(node);
    if(i)parts.segments.push(view.mesh(new THREE.CylinderGeometry(.009*L,.009*L,1,16),0x25a5a5,new THREE.Vector3(),'body'));
  }
  sampleFlexibleLink(view,{nodes:Array.from({length:p.nodes},(_,i)=>({id:`flex${i+1}`,x:L*i/(p.nodes-1),y:0,z:0}))});
}

/** Every displayed point comes from the current native node frame without a deformation multiplier. */
export function sampleFlexibleLink(view,sample) {
  const parts=view.flexibleParts;if(!parts)return;
  const nodes=new Map((sample?.nodes||[]).map(node=>[String(node.id),node]));
  for(let i=0;i<parts.nodes.length;i++) {
    const node=nodes.get(`flex${i+1}`);if(!node)continue;
    parts.nodes[i].position.set(node.x,node.y,node.z);
    if(i) {
      const a=parts.nodes[i-1].position,b=parts.nodes[i].position,delta=b.clone().sub(a),segment=parts.segments[i-1];
      segment.position.copy(a).add(b).multiplyScalar(.5);segment.scale.y=delta.length();
      if(delta.lengthSq()>1e-18)segment.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),delta.normalize());
    }
  }
}
