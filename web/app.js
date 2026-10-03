import {RobotView} from './scene.js';
import {C,fmt,esc,cameraPoint,cameraView,residualView,lineChart} from './plots.js';

const $=id=>document.getElementById(id);
const steps=[
  {title:'Start with positions, not a perfect hand pose.',text:'The head camera predicts labeled 3D points on the arms and hands. Each observation includes uncertainty, synchronized encoder readings, and the known camera-to-torso transform. Missing detections are left out.',action:'Compare with FK →'},
  {title:'Same landmarks. Same frame. Different positions.',text:'Forward kinematics predicts each landmark from the encoders. Transform those predictions into the camera frame, then compare orange model points with green perceived points. Pink lines show the disagreement.',action:'Calibrate model →'},
  {title:'Keep the observations fixed. Change the model.',text:'Fit one set of joint offsets and link lengths across all training observations. Playback follows actual accepted optimizer iterations. The observation slider and model-iteration slider change different things.',action:'Validate on unseen frames →'},
  {title:'A better fit must work on observations it never used.',text:'Only held-out validation frames are shown here. Compare the nominal model at iteration 0 with the calibrated model at the last iteration. Noise and outliers can leave residuals even after a good calibration.',action:'Return to observations ↺'}
];
let result=null,renderer=null,stage=0,iteration=0,sampleIndex=0,playing=false,timer=0,busy=false,imported=null;
const selected={side:0,landmark:3};
const titleCase=s=>s.replaceAll('_',' ');
const metric=(label,value,unit,note,highlight=false)=>`<div class="metric ${highlight?'highlight':''}"><div class="metric-label">${label}</div><div class="metric-value">${value}<em>${unit}</em></div><div class="metric-note">${note}</div></div>`;
const eligible=()=>result.samples.map((s,i)=>({s,i})).filter(({s})=>s.split===(stage===3?'validation':'train')).map(({i})=>i);

function stop(){playing=false;clearInterval(timer);$('play').textContent='▶ Play fit';$('play').setAttribute('aria-label','Play actual optimizer iterations');}
function play(){
  if(playing){stop();return;}
  if(stage<2||busy)return;
  if(iteration===result.iterations.length-1)iteration=0;
  playing=true;$('play').textContent='Ⅱ Pause';$('play').setAttribute('aria-label','Pause optimizer playback');update();
  timer=setInterval(()=>{if(iteration>=result.iterations.length-1){stop();return;}iteration++;update();},650);
}
function chooseStage(next){
  stop();stage=next;
  if(stage<2)iteration=0;
  if(stage===3)iteration=result.iterations.length-1;
  const allowed=eligible();if(!allowed.includes(sampleIndex))sampleIndex=allowed.find(i=>result.samples[i].visible[0][3]&&result.samples[i].visible[1][4])??allowed[0];
  update();
}
function setBusy(value,message=''){
  busy=value;$('status').textContent=message;
  ['import-button','run-demo','next-stage','export-button'].forEach(id=>$(id).disabled=value||!result);
  document.querySelectorAll('.step').forEach(el=>el.disabled=value||!result);
  if(result){$('play').disabled=value||stage<2;$('iteration').disabled=value||stage<2;}
}
function accept(data){
  result=data;iteration=0;stage=0;
  sampleIndex=eligible().find(i=>result.samples[i].visible[0][3]&&result.samples[i].visible[0][4]&&result.samples[i].visible[1][4])??eligible()[0];
  $('source').textContent=data.source==='synthetic'?'SIMULATED PERCEPTION':'IMPORTED OBSERVATIONS';
  $('landmark-select').innerHTML=data.landmark_names.map((name,i)=>`<option value="${i}" ${i===selected.landmark?'selected':''}>${i+1}. ${esc(titleCase(name))}</option>`).join('');
  if(data.settings){$('frame-count').value=data.settings.count;$('noise').value=data.settings.noise_mm;$('missing').value=data.settings.missing;$('outliers').value=data.settings.outliers;}
  setBusy(false);update();
  if(data.rank<18||data.at_bound)$('status').textContent=data.rank<18?'Some model parameters cannot be independently identified from these observations. Review the rank and dataset before using the exported model.':'A parameter reached its fitting bound. Inspect perception bias, excitation, and model assumptions.';
}
async function fitRequest(path,payload,replaceDataset=false){
  stop();setBusy(true,'Fitting a shared model to the training frames. Validation frames are excluded…');
  try{
    const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data=await response.json();if(!response.ok)throw new Error(data.error||'Calibration failed');
    if(replaceDataset)imported=path==='/api/calibrate'?payload:null;
    accept(data);chooseStage(2);play();
  }catch(error){setBusy(false,`Could not calibrate: ${error.message}`);}
}

function update(){
  if(!result)return;
  const description=steps[stage],sample=result.samples[sampleIndex],frame=result.iterations[iteration],allowed=eligible();
  document.querySelectorAll('.step').forEach(el=>{const active=Number(el.dataset.stage)===stage;el.classList.toggle('active',active);el.setAttribute('aria-current',active?'step':'false');});
  $('stage-label').textContent=`0${stage+1} / ${['OBSERVE','COMPARE','CALIBRATE','VALIDATE'][stage]}`;
  $('stage-title').textContent=description.title;$('stage-description').textContent=description.text;$('next-stage').textContent=description.action;
  $('observation').max=allowed.length-1;$('observation').value=allowed.indexOf(sampleIndex);
  $('observation-value').textContent=`${allowed.indexOf(sampleIndex)+1} / ${allowed.length}`;
  $('split-badge').textContent=sample.split==='train'?`TRAIN · FRAME ${sampleIndex+1}`:`HELD OUT · FRAME ${sampleIndex+1}`;
  $('iteration').max=result.iterations.length-1;$('iteration').value=iteration;$('iteration').disabled=stage<2||busy;
  $('iteration-value').textContent=`${iteration} / ${result.iterations.length-1}`;$('play').disabled=stage<2||busy;
  $('iteration-hint').textContent=stage<2?'The nominal model is fixed at iteration 0 in this stage. Continue to Calibrate to change it.':'Changes the FK model. Perceived positions and encoder readings stay fixed.';
  const count=sample.visible.flat().filter(Boolean).length;
  if(stage===0){
    $('metrics').innerHTML=metric('Visible in this frame',count,'/ 16','Missing landmarks are omitted',true)+metric('Training observations',result.train_frames,'frames',`${result.training_points} visible 3D landmarks`)+metric('Held-out observations',result.validation_frames,'frames','Never used to fit parameters')+metric('Perception provides','3D','positions','No hand orientation is required');
  }else{
    const m=frame.metrics,change=100*(1-m.validation_rms_mm/result.initial.validation_rms_mm);
    const last=result.source==='synthetic'?metric('Simulation geometry RMS',fmt(m.truth_rms_mm,3),'mm','Against exact truth · validation poses'):metric('Validation median',fmt(m.validation_median_mm),'mm','Agreement with noisy perception');
    $('metrics').innerHTML=metric('Nominal validation RMS',fmt(result.initial.validation_rms_mm),'mm','Position discrepancy vs perception')+metric('Current validation RMS',fmt(m.validation_rms_mm),'mm',`${fmt(Math.abs(change),1)}% ${change>=0?'lower':'higher'} observation error`,true)+last+metric('Model parameters','18','','14 joint offsets + 4 length corrections');
  }
  $('scene-state').textContent=['PERCEIVED 3D LANDMARKS','NOMINAL FK + PERCEPTION',`MODEL UPDATE ${iteration} · FIXED OBSERVATIONS`,'HELD-OUT FRAME · BEFORE / AFTER'][stage];
  $('fk-legend').hidden=stage===0;
  renderer?.update(sample,iteration,stage,selected,result.intrinsics);
  $('camera-view').innerHTML=cameraView(sample,iteration,stage,selected,result.intrinsics);
  $('projection-label').textContent=result.source==='synthetic'?'SYNTHETIC PROJECTION':result.projection_is_illustrative?'ILLUSTRATIVE INTRINSICS':'IMPORTED 3D PROJECTION';
  $('camera-count').textContent=`${count} visible landmarks`;
  document.querySelector('.camera-disclaimer').textContent=result.source==='synthetic'?'A projection of simulated 3D predictions—not a real camera image. No image-inference model is running.':result.projection_is_illustrative?'Your imported 3D observations. Image projection uses illustrative intrinsics; the fit uses camera-frame 3D positions directly.':'Your imported 3D observations projected with the supplied camera intrinsics. No RGB image is displayed.';
  $('residual-inspector').innerHTML=residualView(sample,iteration,stage,selected);
  if(stage<2){$('error-chart').innerHTML='<div class="empty-state"><b>The test comes after fitting.</b><br><br>The model is currently uncalibrated. Continue to Calibrate to see how observation errors evolve.<br><br>Training frames update the parameters. Held-out frames only evaluate them.</div>';}
  else{$('error-chart').innerHTML=lineChart([{label:'Training observations',color:C.amber,values:result.iterations.map(f=>f.metrics.train_rms_mm)},{label:'Held-out observations',color:C.green,values:result.iterations.map(f=>f.metrics.validation_rms_mm)}],iteration);}
  $('error-caption').textContent='Residuals include perception noise and outliers. A nonzero final error does not necessarily mean the geometry is wrong. Absolute geometry error is available only for the synthetic demo.';
  const p=frame.parameters;
  const names=['Joint 1 [°]','Joint 2 [°]','Joint 3 [°]','Joint 4 [°]','Joint 5 [°]','Joint 6 [°]','Joint 7 [°]','Upper arm Δ [mm]','Forearm Δ [mm]'];
  $('parameters').innerHTML=`<table class="parameter-table"><thead><tr><th>Parameter</th><th>Nominal</th><th>Left · current</th><th>Right · current</th></tr></thead><tbody>${names.map((name,j)=>`<tr><td>${name}</td><td>0.00</td><td class="fit">${fmt(p[0][j])}</td><td class="fit">${fmt(p[1][j])}</td></tr>`).join('')}</tbody></table>`;
  $('fit-diagnostics').innerHTML=stage<2?'<div class="diagnostic-row"><span>Shared calibration parameters</span><strong>18</strong></div><div class="diagnostic-row"><span>Camera calibration</span><strong>Known / fixed input</strong></div>':`<div class="diagnostic-row"><span>Final local parameter rank</span><strong>${result.rank} / 18</strong></div><div class="diagnostic-row"><span>Scaled sensitivity condition</span><strong>${fmt(result.condition,1)}</strong></div><div class="diagnostic-row"><span>Training / validation landmarks</span><strong>${result.training_points} / ${result.validation_points}</strong></div><div class="diagnostic-row"><span>Parameter at bound</span><strong>${result.at_bound?'Yes — inspect the fit':'No'}</strong></div>`;
}

document.querySelectorAll('.step').forEach(el=>el.onclick=()=>result&&!busy&&chooseStage(Number(el.dataset.stage)));
$('next-stage').onclick=()=>{if(stage===1){if(imported)fitRequest('/api/calibrate',imported);else fitRequest('/api/demo',result.settings);}else chooseStage((stage+1)%4);};
$('observation').oninput=e=>{sampleIndex=eligible()[Number(e.target.value)];update();};
$('iteration').oninput=e=>{stop();iteration=Number(e.target.value);update();};
$('play').onclick=play;$('reset-view').onclick=()=>renderer?.reset();
$('arm-select').onchange=e=>{selected.side=Number(e.target.value);update();};
$('landmark-select').onchange=e=>{selected.landmark=Number(e.target.value);update();};
$('run-demo').onclick=()=>fitRequest('/api/demo',{count:Number($('frame-count').value),noise_mm:Number($('noise').value),missing:Number($('missing').value),outliers:Number($('outliers').value)},true);
$('import-button').onclick=()=>$('file-input').click();
$('file-input').onchange=async e=>{
  const file=e.target.files[0];if(!file)return;
  try{if(file.size>2_000_000)throw new Error('Use a JSON dataset under 2 MB');const raw=JSON.parse(await file.text());await fitRequest('/api/calibrate',raw,true);}catch(error){setBusy(false,`Could not import: ${error.message}`);}e.target.value='';
};
$('export-button').onclick=()=>{
  const output={schema_version:1,source:result.source,model:result.model,rank:result.rank,at_bound:result.at_bound,
    validation_metrics:result.final,parameter_units:'radians for joint offsets; meters for link corrections'};
  const url=URL.createObjectURL(new Blob([JSON.stringify(output,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download='calibrated-arm-model.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
setBusy(true,'Loading the calibration experiment…');
try{
  const response=await fetch('/api/demo');if(!response.ok)throw new Error('Start the app with python server.py');
  const data=await response.json();
  try{renderer=new RobotView($('robot-view'));}catch(error){$('webgl-error').hidden=false;$('webgl-error').textContent='WebGL could not start. The camera projection, residual inspector, calibration controls, and metrics still work.';}
  accept(data);
  window.calibrationApp={get result(){return result;},get stage(){return stage;},get iteration(){return iteration;},get sampleIndex(){return sampleIndex;},get hasWebGL(){return !!renderer;},get busy(){return busy;}};
}catch(error){setBusy(false,error.message);}
