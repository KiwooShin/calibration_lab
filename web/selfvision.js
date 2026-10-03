import {lineChart,colors as C,number as fmt} from './charts.js';
const $=id=>document.getElementById(id);
export const perceptionState={sample:4,showTruth:true};

export function perceptionOptions(){
  return {count:Number($('vision-count').value),noise_mm:Number($('vision-noise').value),
    dropout:Number($('vision-dropout').value),outliers:Number($('vision-outliers').value),group:$('vision-group').value};
}

export function renderPerception(d,{metric,select,update,run}){
  perceptionState.sample=Math.min(perceptionState.sample,d.samples.length-1);
  $('metrics').innerHTML=metric('Landmarks · before',fmt(d.initial.landmark_mm,2),'mm','Both arms · held-out 3D RMS')+metric('Landmarks · calibrated',fmt(d.final.landmark_mm,3),'mm','160 unseen two-arm configurations',true)+metric('Hand position · calibrated',fmt(d.final.palm_mm,3),'mm','Palm center RMS · no orientation input')+metric('Identifiable parameters',`${d.rank} / 18`,'',`${d.used_observations} visible 3D observations`);
  $('controls').innerHTML=select('vision-group','Positions used for calibration',[['all','Arm + hand landmarks'],['hand','Hand landmarks only'],['palm','Palm center only']],d.group)+select('vision-count','Synchronized observation frames',[[24,'24 frames'],[40,'40 frames'],[64,'64 frames'],[96,'96 frames']],d.count)+`<div class="field"><label for="vision-noise">Lateral perception noise <output id="vision-noise-value">${d.noise_mm} mm</output></label><input id="vision-noise" type="range" min="0" max="8" step=".5" value="${d.noise_mm}"></div>`+select('vision-dropout','Missing detections',[[0,'0%'],[.15,'15%'],[.3,'30%'],[.4,'40%']],d.dropout)+select('vision-outliers','Unflagged outliers',[[0,'0%'],[.04,'4%'],[.1,'10%'],[.15,'15%']],d.outliers)+`<button class="primary" id="run-perception">Calibrate from perception ↗</button><p class="control-note">3D positions + uncertainty + visibility. Camera-to-torso calibration is known. Depth noise is 2× lateral noise.</p>`;
  $('vision-noise').oninput=e=>$('vision-noise-value').textContent=`${e.target.value} mm`;
  $('run-perception').onclick=run;
  $('perception-panel').hidden=false;
  $('observation-frame').max=d.count-1;$('observation-frame').value=perceptionState.sample;
  $('observation-frame').oninput=e=>{perceptionState.sample=Number(e.target.value);update();};
  $('show-truth').checked=perceptionState.showTruth;
  $('show-truth').onchange=e=>{perceptionState.showTruth=e.target.checked;update();};
  $('takeaway').textContent='Each visible arm or hand landmark constrains the part of the kinematic chain that places it. Fit one shared model across synchronized camera observations and encoder readings. More arm landmarks help distinguish proximal joint and link errors from wrist errors.';
  $('method').innerHTML=`<p><code>rᵢⱼ = Σᵢⱼ⁻½ [ T_camera←torso(i) · FK_landmarkⱼ(qᵢ; θ) − p̂_camera,ᵢⱼ ]</code>. Minimize a robust soft-L1 loss over visible, labeled 3D points. No measured or ground-truth hand orientation is used. Each arm has seven encoder offsets and two upper/forearm length corrections: 18 unknowns in total. Their scales are degrees and millimeters.</p><p>${d.note}</p><p>The model assumes the selected landmarks have known, repeatable attachments to rigid links. Learned landmarks must be inferred independently of the FK parameters being calibrated. The camera-view panel is a synthetic projection of 3D predictions, not real RGB or a trained perception network. Green points include noise and outliers; translucent ground truth is available only for simulation inspection.</p><p>Every frame accepts its own known camera-to-torso transform, so head motion is supported by the solver. The demo uses a fixed head pose. The comparison fits use the same frames and available observations, with different landmark subsets; adding arm points adds measurements. Calibration-Jacobian rank and held-out errors are reported separately.</p><p>Use <code>python self_observation.py --input predictions.json --output results/landmark_fit.json</code> for actual perception outputs. The schema and landmark attachments are documented in <a href="../PERCEPTION_INPUT.md" target="_blank" rel="noopener">PERCEPTION_INPUT.md</a>. This generic geometry must be replaced with your robot’s kinematic chain for hardware data.</p>`;
  if(d.at_bound)$('status').textContent='A fitted parameter reached its bound. Inspect perception bias, excitation, and model assumptions before trusting the result.';
}

function projected(p,camera){
  const t=camera.T_base_camera,delta=p.map((v,i)=>v-t[i][3]);
  const c=[0,1,2].map(j=>delta.reduce((sum,v,k)=>sum+v*t[k][j],0));
  return [camera.K[0][0]*c[0]/Math.max(c[2],.001)+camera.K[0][2],camera.K[1][1]*c[1]/Math.max(c[2],.001)+camera.K[1][2]];
}

export function cameraOverlay(d,sample,iteration){
  let s='<svg viewBox="0 0 960 600" role="img" aria-label="Synthetic head-camera projection of perceived 3D landmarks and forward-kinematics predictions"><defs><clipPath id="camera-clip"><rect width="960" height="600" rx="8"/></clipPath><radialGradient id="camera-bg"><stop stop-color="#22374a"/><stop offset="1" stop-color="#101c2a"/></radialGradient></defs><rect width="960" height="600" rx="8" fill="url(#camera-bg)"/><g clip-path="url(#camera-clip)">';
  for(let x=0;x<=960;x+=80)s+=`<path d="M${x} 0V600" stroke="#345065" opacity=".25"/>`;
  for(let y=0;y<=600;y+=75)s+=`<path d="M0 ${y}H960" stroke="#345065" opacity=".25"/>`;
  s+='<path d="M466 300H494 M480 286V314" stroke="#71899e" opacity=".55"/><text x="20" y="32" font-family="monospace" font-size="13" fill="#97b0c6">HEAD CAMERA / SYNTHETIC PROJECTION</text><text x="770" y="32" font-family="monospace" font-size="13" fill="#97b0c6">960 × 600</text>';
  for(let side=0;side<2;side++){
    const predicted=sample.iterations[iteration][side];
    const nodes=predicted.nodes.map(p=>projected(p,d.camera));
    s+=`<polyline points="${nodes.map(p=>p.join(',')).join(' ')}" stroke="${C.amber}" stroke-width="14" stroke-linecap="round" stroke-linejoin="round" fill="none" opacity=".18"/>`;
    const observed=sample.observed_uv[side],visible=sample.visible[side],used=sample.used[side];
    for(const [a,b] of [[0,1],[1,2],[2,3],[3,4],[4,5],[4,6],[4,7]]){
      if(visible[a]&&visible[b])s+=`<line x1="${observed[a][0]}" y1="${observed[a][1]}" x2="${observed[b][0]}" y2="${observed[b][1]}" stroke="${C.teal}" opacity=".35" stroke-width="2"/>`;
    }
    predicted.landmarks.forEach((p,k)=>{
      const xy=projected(p,d.camera),color=used[k]?C.amber:'#71849a';
      s+=`<path d="M${xy[0]-5} ${xy[1]}h10 M${xy[0]} ${xy[1]-5}v10" stroke="${color}" stroke-width="2"/>`;
      if(visible[k]){
        const uv=observed[k];
        if(used[k])s+=`<line x1="${xy[0]}" y1="${xy[1]}" x2="${uv[0]}" y2="${uv[1]}" stroke="${C.red}" opacity=".8"/>`;
        s+=`<circle cx="${uv[0]}" cy="${uv[1]}" r="${used[k]?5:3}" fill="${used[k]?C.teal:'#71849a'}" opacity="${sample.confidence[side][k]}"/>`;
        if(k<4||k===7)s+=`<text x="${uv[0]+8}" y="${uv[1]-7}" fill="#b8cbdb" font-family="monospace" font-size="11">${side?'R':'L'} ${k+1}</text>`;
      }
    });
  }
  return s+'</g></svg><div class="chart-legend"><span><i style="background:#6de6c5"></i>Perceived 3D positions (projected)</span><span><i style="background:#ffc180"></i>FK projection +</span><span><i style="background:#f594b0"></i>Discrepancy</span></div>';
}

export function updatePerception(d,index,{view,readout,chart}){
  const sample=d.samples[perceptionState.sample],f=d.frames[index];
  view?.updateSelfVision(sample,index,perceptionState.showTruth);
  $('scene-badge').textContent=`HEAD CAMERA → 3D LANDMARKS → FK FIT`;
  $('truth-label').textContent='Simulation truth (optional)';$('estimate-label').textContent='FK model + perceived points';
  $('observation-value').textContent=`${perceptionState.sample+1} / ${d.count}`;
  $('camera-overlay').innerHTML=cameraOverlay(d,sample,index);
  const names=['J1 [°]','J2 [°]','J3 [°]','J4 [°]','J5 [°]','J6 [°]','J7 [°]','Upper Δ [mm]','Forearm Δ [mm]'];
  $('parameter-table').innerHTML=`<table class="comparison parameter-table"><thead><tr><th>Parameter</th><th>L true</th><th>L fit</th><th>R true</th><th>R fit</th></tr></thead><tbody>${names.map((name,k)=>`<tr><td>${name}</td><td>${fmt(d.true_parameters[0][k])}</td><td class="fit-value">${fmt(f.parameters[0][k])}</td><td>${fmt(d.true_parameters[1][k])}</td><td class="fit-value">${fmt(f.parameters[1][k])}</td></tr>`).join('')}</tbody></table>`;
  $('frame-readout').innerHTML=readout([['Current holdout RMS',`${fmt(f.metrics.landmark_mm,3)} mm`],['Current palm RMS',`${fmt(f.metrics.palm_mm,3)} mm`],['3D point residuals',d.used_observations],['Sensitivity condition',fmt(d.condition,1)]]);
  const comparison=`<table class="comparison"><thead><tr><th>Perception inputs</th><th>Points</th><th>Arm RMS</th><th>Palm RMS</th></tr></thead><tbody>${d.comparison.map(r=>`<tr><td>${r.label}</td><td>${r.used_observations}</td><td>${fmt(r.landmark_mm,3)} mm</td><td>${fmt(r.palm_mm,3)} mm</td></tr>`).join('')}</tbody></table>`;
  chart('one','Why observe the arm as well as the hand?','SAME FRAMES / MM',comparison,'Each fit uses a subset of the same perception outputs. More landmarks add constraints; this is not an equal-point-budget comparison. Unfit subsets are omitted.');
  chart('two','Fit positions. Test on new configurations.','HELD-OUT 3D RMS / MM',lineChart([{label:'Arm + hand landmark error',color:C.teal,points:d.frames.map((f,i)=>[i,f.metrics.landmark_mm])},{label:'Palm position error',color:C.amber,points:d.frames.map((f,i)=>[i,f.metrics.palm_mm])}],{xlabel:'Accepted optimizer iteration',ylabel:'3D position RMS [mm]',marker:index}),'Synthetic ground truth is used only for these evaluation metrics. The optimizer receives perception positions, uncertainties, and visibility—not truth.');
}
