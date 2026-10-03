import * as THREE from 'three';
import {OrbitControls} from './vendor/OrbitControls.js';

const vector=p=>new THREE.Vector3(...p);
const connections=[[0,1],[1,2],[2,3],[3,4],[4,5],[4,6],[4,7]];

export class RobotView {
  constructor(host){
    this.host=host;
    this.renderer=new THREE.WebGLRenderer({alpha:true,antialias:true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio,1.6));
    this.renderer.shadowMap.enabled=true;
    this.renderer.shadowMap.type=THREE.PCFSoftShadowMap;
    this.renderer.outputColorSpace=THREE.SRGBColorSpace;
    this.renderer.toneMapping=THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure=1.15;
    Object.assign(this.renderer.domElement.style,{position:'absolute',inset:'0',width:'100%',height:'100%'});
    host.prepend(this.renderer.domElement);
    this.scene=new THREE.Scene();
    this.scene.fog=new THREE.FogExp2(0x152131,.10);
    this.camera=new THREE.PerspectiveCamera(39,1,.01,30);this.camera.up.set(0,0,1);
    this.controls=new OrbitControls(this.camera,this.renderer.domElement);
    this.controls.enableDamping=true;this.controls.minDistance=.8;this.controls.maxDistance=5;
    this.reset();
    this.scene.add(new THREE.HemisphereLight(0xd6ecff,0x253542,2.3));
    const key=new THREE.DirectionalLight(0xe2f8f1,3.1);key.position.set(1,-3,4);key.castShadow=true;
    key.shadow.mapSize.set(1024,1024);key.shadow.camera.left=-2;key.shadow.camera.right=2;key.shadow.camera.top=2;key.shadow.camera.bottom=-2;key.shadow.bias=-.0005;this.scene.add(key);
    const fill=new THREE.DirectionalLight(0x7bb5e2,1.3);fill.position.set(-2,2,2);this.scene.add(fill);
    const floor=new THREE.Mesh(new THREE.CircleGeometry(1.5,80),new THREE.MeshStandardMaterial({color:0x152737,metalness:.15,roughness:.8}));
    floor.position.z=-.002;floor.receiveShadow=true;this.scene.add(floor);
    const grid=new THREE.GridHelper(3,30,0x45627b,0x2b445b);grid.rotation.x=Math.PI/2;grid.material.transparent=true;grid.material.opacity=.35;this.scene.add(grid);
    const body=new THREE.MeshStandardMaterial({color:0x34485c,metalness:.5,roughness:.35});
    this.box([.20,.39,.57],[-.07,0,.73],body);
    this.tube([-.07,0,.05],[-.07,0,.45],.085,body,this.scene);
    this.tube([-.07,0,1.0],[-.07,0,1.30],.048,body,this.scene);
    this.head=new THREE.Group();this.scene.add(this.head);
    const headBox=new THREE.Mesh(new THREE.BoxGeometry(.23,.17,.19),body);headBox.position.z=-.10;headBox.castShadow=true;this.head.add(headBox);
    const lens=new THREE.Mesh(new THREE.BoxGeometry(.105,.038,.014),new THREE.MeshStandardMaterial({color:0x9fdae4,emissive:0x284f64,emissiveIntensity:.4}));this.head.add(lens);
    this.frustum=this.lineObject(0x80bddf,.28);
    this.arms=[this.arm(),this.arm()];
    this.perceived=this.lineObject(0x70e1bd,.8);
    this.residuals=this.lineObject(0xff91aa,.9);
    this.dots=new THREE.Points(new THREE.BufferGeometry(),new THREE.PointsMaterial({color:0x70e1bd,size:.021,sizeAttenuation:true,depthTest:false}));this.dots.renderOrder=3;this.scene.add(this.dots);
    this.highlight=new THREE.Mesh(new THREE.SphereGeometry(.015,16,12),new THREE.MeshBasicMaterial({color:0xe5fff3,wireframe:true,depthTest:false}));this.highlight.renderOrder=4;this.scene.add(this.highlight);
    const axes=new THREE.AxesHelper(.18);axes.position.set(-.1,-.1,.002);this.scene.add(axes);
    this.observer=new ResizeObserver(()=>this.resize());this.observer.observe(host);this.resize();
    this.animate();
  }
  box(size,position,material){const m=new THREE.Mesh(new THREE.BoxGeometry(...size),material);m.position.set(...position);m.castShadow=true;this.scene.add(m);return m;}
  tube(a,b,radius,material,group){const m=new THREE.Mesh(new THREE.CylinderGeometry(radius,radius,1,16),material);m.castShadow=true;group.add(m);this.positionTube(m,a,b);return m;}
  positionTube(m,a,b){const av=vector(a),bv=vector(b),d=bv.clone().sub(av);m.position.copy(av.add(bv).multiplyScalar(.5));m.scale.y=Math.max(d.length(),1e-6);m.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),d.normalize());}
  arm(){
    const group=new THREE.Group();this.scene.add(group);
    const material=new THREE.MeshStandardMaterial({color:0xffbd79,metalness:.4,roughness:.38,transparent:true,opacity:.72});
    const joints=[],links=[];
    for(let i=0;i<7;i++){
      links.push(this.tube([0,0,0],[0,0,1],.018,material,group));
      const sphere=new THREE.Mesh(new THREE.SphereGeometry(.025,16,12),material);group.add(sphere);joints.push(sphere);
    }
    const hand=new THREE.Group();group.add(hand);
    const palm=new THREE.Mesh(new THREE.BoxGeometry(.07,.075,.022),material);palm.position.x=.027;hand.add(palm);
    for(let i=0;i<3;i++){const finger=new THREE.Mesh(new THREE.BoxGeometry(.035,.015,.015),material);finger.position.set(.075,(i-1)*.026,0);hand.add(finger);}
    return {group,links,joints,hand};
  }
  lineObject(color,opacity){const line=new THREE.LineSegments(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color,transparent:true,opacity}));this.scene.add(line);return line;}
  replaceGeometry(object,points){object.geometry.dispose();object.geometry=new THREE.BufferGeometry().setFromPoints(points.map(vector));}
  setRotation(object,r){const m=new THREE.Matrix4().set(r[0][0],r[0][1],r[0][2],0,r[1][0],r[1][1],r[1][2],0,r[2][0],r[2][1],r[2][2],0,0,0,0,1);object.quaternion.setFromRotationMatrix(m);}
  update(sample,iteration,stage,selected,intrinsics){
    const models=sample.snapshots[iteration];
    models.forEach((model,side)=>{
      const arm=this.arms[side];arm.group.visible=stage!==0;
      model.nodes.slice(0,7).forEach((p,j)=>{this.positionTube(arm.links[j],p,model.nodes[j+1]);arm.joints[j].position.set(...p);});
      arm.hand.position.set(...model.points[4]);this.setRotation(arm.hand,model.rotation);
    });
    const dots=[],bones=[],errors=[];
    sample.observed_world.forEach((points,side)=>{
      points.forEach((p,k)=>{if(sample.visible[side][k]){dots.push(p);errors.push(p,models[side].points[k]);}});
      connections.forEach(([a,b])=>{if(sample.visible[side][a]&&sample.visible[side][b])bones.push(points[a],points[b]);});
    });
    this.replaceGeometry(this.dots,dots);this.replaceGeometry(this.perceived,bones);this.replaceGeometry(this.residuals,errors);this.residuals.visible=stage!==0;
    this.perceived.material.opacity=stage===0?.8:.32;
    this.highlight.visible=sample.visible[selected.side][selected.landmark];
    if(this.highlight.visible)this.highlight.position.set(...sample.observed_world[selected.side][selected.landmark]);
    const t=sample.T_base_camera,r=t.slice(0,3).map(row=>row.slice(0,3)),origin=t.slice(0,3).map(row=>row[3]);
    this.head.position.set(...origin);this.setRotation(this.head,r);
    const z=.62,k=intrinsics;
    const corners=[[0,0],[k.width,0],[k.width,k.height],[0,k.height]].map(([u,v])=>{
      const local=[(u-k.cx)/k.fx*z,(v-k.cy)/k.fy*z,z];return r.map((row,i)=>origin[i]+row.reduce((sum,x,j)=>sum+x*local[j],0));
    });
    const rays=[];corners.forEach((p,i)=>rays.push(origin,p,p,corners[(i+1)%4]));this.replaceGeometry(this.frustum,rays);
  }
  reset(){this.camera.position.set(1.9,-2.2,1.82);this.controls.target.set(.25,0,.9);this.controls.update();}
  resize(){const w=this.host.clientWidth,h=this.host.clientHeight;this.renderer.setSize(w,h,false);this.camera.aspect=w/h;this.camera.updateProjectionMatrix();}
  animate(){requestAnimationFrame(()=>this.animate());this.controls.update();this.renderer.render(this.scene,this.camera);}
}
