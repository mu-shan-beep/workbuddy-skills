import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';

const root=path.resolve(import.meta.dirname,'..');
const input=path.resolve(process.argv[2]||path.join(root,'.audit/hra'));
const output=path.join(root,'assets/hra');
const revision='b036a91aaf7234f462b1249d4a5f4fb0e982f412';
const expectedHashes={skin:'8cab299d04323e6364938a271647df5671138a2177f412e741a0d6bd4536ee1c',lung:'e64351b72b0bc5289a4dc32ba2b402b9c974f9ec0b1972bf06b436864f917913',heart:'b1237e7e765178e9357fd2ea7ccf19d55d0bf9ca55e187886635febe28244c70'};
const sources=[];
const meshes=[];
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
function accessor(json,bin,id){
  const a=json.accessors[id],v=json.bufferViews[a.bufferView];
  assert(!a.sparse,'Sparse accessors need explicit handling');
  const Type={5123:Uint16Array,5125:Uint32Array,5126:Float32Array}[a.componentType];
  assert(Type,'Unsupported accessor component');
  const count=a.count*({SCALAR:1,VEC3:3,VEC4:4}[a.type]);
  const width=({SCALAR:1,VEC3:3,VEC4:4}[a.type]);
  const offset=bin.byteOffset+(v.byteOffset||0)+(a.byteOffset||0);
  if(!v.byteStride||v.byteStride===width*Type.BYTES_PER_ELEMENT)return new Type(bin.buffer,offset,count);
  const result=new Type(count);
  for(let i=0;i<a.count;i++)result.set(new Type(bin.buffer,offset+i*v.byteStride,width),i*width);
  return result;
}
for(const source of ['skin','lung','heart']){
  const bytes=fs.readFileSync(path.join(input,source+'.glb'));
  assert.equal(hash(bytes),expectedHashes[source],'Source mesh differs from the pinned release');
  assert.equal(bytes.readUInt32LE(0),0x46546c67);assert.equal(bytes.readUInt32LE(4),2);
  const length=bytes.readUInt32LE(12),json=JSON.parse(bytes.subarray(20,20+length)),bin=bytes.subarray(28+length);
  assert(json.nodes.every(n=>!n.matrix&&!n.translation&&!n.rotation&&!n.scale),'Source transforms need explicit handling');
  sources.push({name:source,url:`https://github.com/hubmapconsortium/ccf-releases/blob/${revision}/v1.2/models/VH_M_${{skin:'Skin',lung:'Lung',heart:'Heart'}[source]}.glb`,sha256:hash(bytes)});
  for(const node of json.nodes.filter(n=>n.mesh!==undefined)){
    const name=node.name;
    const lungSurface=/bronchopulmonary_segment/.test(name);
    const id=source==='skin'?'skin':source==='heart'?'heart':lungSurface?(name.includes('_left_')?'left':'right'):'trachea';
    if(source==='heart'&&!/cardiac_atrium|ventricle|septum/.test(name))continue;
    if(source==='lung'&&/hilum/.test(name))continue;
    for(const primitive of json.meshes[node.mesh].primitives){
      let p=accessor(json,bin,primitive.attributes.POSITION),n=accessor(json,bin,primitive.attributes.NORMAL),indices=accessor(json,bin,primitive.indices);
      if(source==='skin'){
        const positions=[],normals=[],faces=[];
        for(let t=0;t<indices.length;t+=3){
          let polygon=Array.from(indices.subarray(t,t+3),i=>({p:Array.from(p.subarray(i*3,i*3+3)),n:Array.from(n.subarray(i*3,i*3+3))}));
          for(const [axis,limit,sign] of [[1,.31,1],[1,.685,-1],[0,-.205,1],[0,.205,-1]]){
            const clipped=[];
            for(let i=0;i<polygon.length;i++){const a=polygon[i],b=polygon[(i+1)%polygon.length],da=sign*(a.p[axis]-limit),db=sign*(b.p[axis]-limit);if(da>=0)clipped.push(a);if((da>=0)!==(db>=0)){const u=da/(da-db);clipped.push({p:a.p.map((v,k)=>v+(b.p[k]-v)*u),n:a.n.map((v,k)=>v+(b.n[k]-v)*u)});}}
            polygon=clipped;
          }
          for(let i=1;i+1<polygon.length;i++)for(const v of [polygon[0],polygon[i],polygon[i+1]]){faces.push(positions.length/3);positions.push(...v.p);normals.push(...v.n);}
        }
        p=Float32Array.from(positions);n=Float32Array.from(normals);indices=Uint32Array.from(faces);
      }
      const cell=source==='skin'?.0018:source==='heart'?.00065:.00085;
      const points=[],normals=[],remap=new Map(),lookup=new Map(),triangles=[];
      function vertex(i){
        if(remap.has(i))return remap.get(i);
        const v=Array.from(p.subarray(i*3,i*3+3)),key=v.map(x=>Math.round(x/cell)).join(',');
        let out=lookup.get(key);
        if(out===undefined){out=points.length;lookup.set(key,out);points.push(v);normals.push(Array.from(n.subarray(i*3,i*3+3)));}
        remap.set(i,out);return out;
      }
      for(let i=0;i<indices.length;i+=3){
        const t=[indices[i],indices[i+1],indices[i+2]];
        const mapped=t.map(vertex);if(new Set(mapped).size===3)triangles.push(...mapped);
      }
      assert(points.length<65536,'Mesh exceeds unsigned short indices');
      if(!triangles.length)continue;
      const packedPositions=Int16Array.from(points.flat().map(x=>Math.round(x*30000)));
      const packedNormals=Int8Array.from(normals.flat().map(x=>Math.round(x*127)));
      const packedIndices=Uint16Array.from(triangles);
      const base64=a=>Buffer.from(a.buffer).toString('base64');
      const bounds=[0,1,2].map(k=>[Math.min(...points.map(p=>p[k])),Math.max(...points.map(p=>p[k]))]);
      meshes.push({id,name,vertices:points.length,triangles:triangles.length/3,bounds,p:base64(packedPositions),n:base64(packedNormals),i:base64(packedIndices)});
    }
  }
}
const data={positionScale:30000,meshes};
fs.mkdirSync(output,{recursive:true});
const packed=JSON.stringify(data);
fs.writeFileSync(path.join(output,'chest-meshes.json'),packed+'\n');
const provenance={title:'Human Reference Atlas Visible Human male chest derivative',license:'CC BY 4.0',license_url:'https://creativecommons.org/licenses/by/4.0/',attribution:'Human Reference Atlas / HuBMAP consortium; Visible Human male reference objects',reference_library:'https://humanatlas.io/3d-reference-library',revision,sources,changes:['Skin triangles clipped at y 0.31–0.685 m and x ±0.205 m, with interpolated source normals; open crop boundaries remain visible.','Vertex clustering uses 1.8 mm cells for skin, 0.85 mm for lungs and airways, 0.65 mm for heart. Degenerate triangles removed.','Positions quantized to 1/30000 m, normals to signed 8-bit; source coordinates and relative scale preserved.','Skin and organ colors replaced for teaching; cutaway window is a rendering aid. Diaphragm is separately authored schematic geometry.'],derived_sha256:hash(Buffer.from(packed+'\n')),meshes:meshes.map(({p,n,i,...m})=>m)};
fs.writeFileSync(path.join(output,'provenance.json'),JSON.stringify(provenance,null,2)+'\n');
const file=path.join(root,'examples/human-anatomy.html');
let html=fs.readFileSync(file,'utf8');
assert(/<script id="atlas-data" type="application\/json">[\s\S]*?<\/script>/.test(html),'Missing atlas data insertion marker');
html=html.replace(/<script id="atlas-data" type="application\/json">[\s\S]*?<\/script>/,`<script id="atlas-data" type="application/json">${packed}</script>`);
fs.writeFileSync(file,html);
console.log(JSON.stringify({bytes:Buffer.byteLength(packed),vertices:meshes.reduce((s,m)=>s+m.vertices,0),triangles:meshes.reduce((s,m)=>s+m.triangles,0),meshes:meshes.length}));
