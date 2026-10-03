import * as THREE from 'three';
import {OrbitControls} from './vendor/OrbitControls.js';

const vec = a => new THREE.Vector3(...a);
const C = {truth: 0x6de6c5, estimate: 0xffc180};

export class ArmScene {
  constructor(host) {
    this.host = host;
    this.renderer = new THREE.WebGLRenderer({antialias: true, alpha: true, preserveDrawingBuffer: true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.25;
    host.prepend(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0x111b29, .12);
    this.camera = new THREE.PerspectiveCamera(37, 1, .01, 30);
    this.camera.up.set(0, 0, 1);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.minDistance = .65;
    this.controls.maxDistance = 6;
    this.controls.maxPolarAngle = Math.PI * .87;
    this.reset();
    this.scene.add(new THREE.HemisphereLight(0xd2e8ff, 0x243343, 2.0));
    const sun = new THREE.DirectionalLight(0xe3f7ff, 3.5);
    sun.position.set(2, -3, 5); sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.left = -2; sun.shadow.camera.right = 2;
    sun.shadow.camera.top = 2; sun.shadow.camera.bottom = -2;
    sun.shadow.bias = -.0003; this.scene.add(sun);
    const fill = new THREE.DirectionalLight(0x63d7c3, 2);
    fill.position.set(-2, 2, 1); this.scene.add(fill);
    const floor = new THREE.Mesh(new THREE.CircleGeometry(1.6, 100), new THREE.MeshStandardMaterial({color: 0x172231, roughness: .9, metalness: .15, transparent: true, opacity: .8}));
    floor.receiveShadow = true; floor.position.z = -.003; this.scene.add(floor);
    const grid = new THREE.GridHelper(3.2, 32, 0x40556d, 0x253950);
    grid.rotation.x = Math.PI / 2; grid.material.transparent = true; grid.material.opacity = .35; this.scene.add(grid);
    for (const radius of [.4, .8, 1.2]) {
      const ring = new THREE.Mesh(new THREE.RingGeometry(radius-.001, radius+.001, 120), new THREE.MeshBasicMaterial({color: 0x40556d, transparent: true, opacity: .45, side: THREE.DoubleSide}));
      ring.position.z = .001; this.scene.add(ring);
    }
    const standMat = new THREE.MeshStandardMaterial({color: 0x283b50, metalness: .65, roughness: .36});
    this.stand = new THREE.Group();this.scene.add(this.stand);
    this.cylinder([0, 0, 0], [0, 0, .07], .14, standMat, this.stand);
    this.cylinder([0, 0, .06], [0, 0, .37], .052, standMat, this.stand);
    this.scene.add(new THREE.AxesHelper(.23));
    this.arms = {truth: this.makeArm(C.truth, false), estimate: this.makeArm(C.estimate, true)};
    this.rightArms = {truth: this.makeArm(C.truth, false), estimate: this.makeArm(C.estimate, true)};
    Object.values(this.rightArms).forEach(a=>a.group.visible=false);
    this.robot = new THREE.Group();this.scene.add(this.robot);this.robot.visible=false;
    const torsoMat = new THREE.MeshStandardMaterial({color:0x34485f,metalness:.55,roughness:.35});
    const torso = new THREE.Mesh(new THREE.BoxGeometry(.21,.40,.57),torsoMat);
    torso.position.set(-.08,0,.74);torso.castShadow=true;this.robot.add(torso);
    this.cylinder([-.08,0,.08],[-.08,0,.48],.10,torsoMat,this.robot);
    this.cylinder([-.08,0,1.],[-.08,0,1.27],.055,torsoMat,this.robot);
    const head = new THREE.Mesh(new THREE.BoxGeometry(.20,.24,.19),torsoMat);
    head.position.set(-.07,0,1.39);head.castShadow=true;this.robot.add(head);
    const cameraBody=new THREE.Mesh(new THREE.BoxGeometry(.045,.12,.042),new THREE.MeshStandardMaterial({color:0x9ae8df,emissive:0x205a56,emissiveIntensity:.3}));
    cameraBody.position.set(.044,0,1.43);this.robot.add(cameraBody);
    const origin=new THREE.Vector3(.04,0,1.43);
    const z=new THREE.Vector3(1,0,-1).normalize(),x=new THREE.Vector3(0,-1,0),y=new THREE.Vector3().crossVectors(z,x);
    const corners=[[-.64,-.4],[.64,-.4],[.64,.4],[-.64,.4]].map(([u,v])=>origin.clone().addScaledVector(z,.63).addScaledVector(x,u).addScaledVector(y,v));
    const rays=[];corners.forEach((c,i)=>{rays.push(origin,c,c,corners[(i+1)%4]);});
    const frustum=new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(rays),new THREE.LineBasicMaterial({color:0x7bcce0,transparent:true,opacity:.25}));
    this.robot.add(frustum);
    this.cloud = null;
    this.path = null;
    this.errorLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints([vec([0,0,0]),vec([0,0,0])]), new THREE.LineBasicMaterial({color: 0xfca5bd, depthTest: false}));
    this.errorLine.renderOrder = 10; this.scene.add(this.errorLine);
    this.observer = new ResizeObserver(() => this.resize()); this.observer.observe(host); this.resize();
    this.animate();
  }

  cylinder(a, b, radius, material, group) {
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius * 1.04, 1, 20), material);
    mesh.castShadow = !material.transparent;
    group.add(mesh); this.positionLink(mesh, a, b); return mesh;
  }
  positionLink(mesh, a, b) {
    const start = vec(a), end = vec(b), d = end.clone().sub(start);
    mesh.position.copy(start.add(end).multiplyScalar(.5));
    mesh.scale.y = Math.max(d.length(), 1e-6);
    mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0), d.normalize());
  }
  makeArm(color, ghost) {
    const group = new THREE.Group(); this.scene.add(group);
    const material = new THREE.MeshStandardMaterial({color, metalness: ghost ? .1 : .55, roughness: .32, transparent: ghost, opacity: ghost ? .26 : 1, depthWrite: !ghost});
    const jointMaterial = new THREE.MeshStandardMaterial({color: ghost ? color : 0xc7e1dd, metalness: .7, roughness: .3, transparent: ghost, opacity: ghost ? .4 : 1, depthWrite: !ghost});
    const links = [], joints = [];
    for (let i=0;i<7;i++) {
      links.push(this.cylinder([0,0,0], [0,0,1], ghost ? .029 : .019, material, group));
      const joint = new THREE.Mesh(new THREE.SphereGeometry(ghost ? .033 : .027, 20, 14), jointMaterial);
      joint.castShadow = !ghost; group.add(joint); joints.push(joint);
    }
    const hand = new THREE.Group();
    const palm = new THREE.Mesh(new THREE.BoxGeometry(.078, .085, .025), material);
    palm.position.x = .026; palm.castShadow = !ghost; hand.add(palm);
    for (let j=0;j<3;j++) {
      const finger = new THREE.Mesh(new THREE.BoxGeometry(.042,.018,.017), material);
      finger.position.set(.081,(j-1)*.027,0); hand.add(finger);
    }
    const thumb = new THREE.Mesh(new THREE.BoxGeometry(.04,.018,.019), material);
    thumb.position.set(.035,-.061,0); thumb.rotation.z = -.6; hand.add(thumb);
    const axes = new THREE.AxesHelper(ghost ? .16 : .11);
    axes.material.depthTest = false; axes.renderOrder = 12; hand.add(axes); group.add(hand);
    return {group, links, joints, hand};
  }
  updateArm(arm, state) {
    if (!state) {arm.group.visible = false; return;}
    arm.group.visible = true;
    for (let j=0;j<7;j++) {
      this.positionLink(arm.links[j], state.nodes[j], state.nodes[j+1]);
      arm.joints[j].position.copy(vec(state.nodes[j]));
    }
    arm.hand.position.copy(vec(state.position));
    const r = state.rotation;
    const matrix = new THREE.Matrix4().set(r[0][0],r[0][1],r[0][2],0,r[1][0],r[1][1],r[1][2],0,r[2][0],r[2][1],r[2][2],0,0,0,0,1);
    arm.hand.quaternion.setFromRotationMatrix(matrix);
  }
  update(frame, {hideArms=false, exaggeration=1, elastic=false}={}) {
    const estimate = elastic ? frame.elastic : frame.estimate;
    let truth = frame.truth;
    if (exaggeration !== 1 && truth && estimate) {
      truth = {...truth, nodes: truth.nodes.map((p,i)=>p.map((v,k)=>estimate.nodes[i][k]+exaggeration*(v-estimate.nodes[i][k]))), position: truth.position.map((v,k)=>estimate.position[k]+exaggeration*(v-estimate.position[k]))};
    }
    this.updateArm(this.arms.truth, hideArms ? null : truth);
    this.updateArm(this.arms.estimate, hideArms ? null : estimate);
    this.errorLine.visible = !hideArms && !!truth && !!estimate;
    if (truth && estimate) {
      this.errorLine.geometry.dispose();
      this.errorLine.geometry = new THREE.BufferGeometry().setFromPoints([vec(truth.position),vec(estimate.position)]);
    }
  }
  setMode(selfvision) {
    const changed=this.selfvision!==selfvision;this.selfvision=selfvision;
    this.robot.visible=selfvision;this.stand.visible=!selfvision;
    Object.values(this.rightArms).forEach(a=>a.group.visible=false);
    if(this.landmarkResiduals)this.landmarkResiduals.visible=false;
    if(changed)this.reset();
  }
  updateSelfVision(sample, iteration, showTruth=true) {
    const estimates=sample.iterations[iteration];
    this.updateArm(this.arms.truth,showTruth?sample.truth[0]:null);
    this.updateArm(this.arms.estimate,estimates[0]);
    this.updateArm(this.rightArms.truth,showTruth?sample.truth[1]:null);
    this.updateArm(this.rightArms.estimate,estimates[1]);
    const points=[];
    sample.observed_base.forEach((arm,side)=>arm.forEach((p,k)=>{if(sample.used[side][k])points.push(p);}));
    this.setCloud(points);
    // Separate residual segments; one LineSegments object avoids connecting observations.
    if(!this.landmarkResiduals){this.landmarkResiduals=new THREE.LineSegments(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color:0xf594b0,transparent:true,opacity:.85}));this.scene.add(this.landmarkResiduals);}
    const endpoints=[];
    sample.observed_base.forEach((arm,side)=>arm.forEach((p,k)=>{if(sample.used[side][k])endpoints.push(vec(p),vec(estimates[side].landmarks[k]));}));
    this.landmarkResiduals.geometry.dispose();this.landmarkResiduals.geometry=new THREE.BufferGeometry().setFromPoints(endpoints);this.landmarkResiduals.visible=true;
    this.errorLine.visible=false;
  }
  setCloud(points, values=null, maxValue=null, selected=[]) {
    if (this.cloud) {this.scene.remove(this.cloud); this.cloud.geometry.dispose(); this.cloud.material.dispose(); this.cloud=null;}
    if (!points?.length) return;
    const colors = [], chosen = new Set(selected);
    const max = maxValue ?? Math.max(...(values || [1]), 1e-9);
    const low = new THREE.Color(0x52d2b1), high = new THREE.Color(0xfb956d);
    points.forEach((p,i)=>{
      const color = chosen.has(i) ? new THREE.Color(0xf8f6c4) : low.clone().lerp(high, Math.max(0,Math.min(1,(values?.[i]??0)/max)));
      colors.push(color.r,color.g,color.b);
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.Float32BufferAttribute(points.flat(),3));
    geometry.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));
    this.cloud = new THREE.Points(geometry,new THREE.PointsMaterial({size:.014,vertexColors:true,transparent:true,opacity:.8,sizeAttenuation:true}));
    this.scene.add(this.cloud);
  }
  setPath(points) {
    if (this.path) {this.scene.remove(this.path);this.path.geometry.dispose();this.path.material.dispose();this.path=null;}
    if (!points?.length) return;
    this.path=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points.map(vec)),new THREE.LineBasicMaterial({color:0xb0a4fa,transparent:true,opacity:.6}));
    this.scene.add(this.path);
  }
  reset() {if(this.selfvision){this.camera.position.set(2.05,-2.2,1.9);this.controls.target.set(.25,0,.86);}else{this.camera.position.set(1.15,-1.65,1.15);this.controls.target.set(.24,0,.43);}this.controls.update();}
  resize() {const w=this.host.clientWidth,h=this.host.clientHeight;this.renderer.setSize(w,h);this.camera.aspect=w/h;this.camera.updateProjectionMatrix();}
  animate() {requestAnimationFrame(()=>this.animate());this.controls.update();this.renderer.render(this.scene,this.camera);}
  snapshot() {this.renderer.render(this.scene,this.camera);const a=document.createElement('a');a.download='calibration-arm.png';a.href=this.renderer.domElement.toDataURL('image/png');a.click();}
}
