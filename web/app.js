import {ArmScene} from './scene.js';
import {lineChart,barChart,colors as C,number as fmt} from './charts.js';

const $=id=>document.getElementById(id);
const META={
  ghost:{n:'01',topic:'PARAMETER ESTIMATION',title:'Fix the ghost arm',subtitle:'Use measured hand poses to teach the model where its joints really are.',scene:'ARM / MODEL ALIGNMENT',timeline:'ITERATION'},
  redundancy:{n:'02',topic:'SEVEN-JOINT REDUNDANCY',title:'Hold the hand. Move the elbow',subtitle:'A stationary hand can reveal a moving model error.',scene:'NULL-SPACE / SELF-MOTION',timeline:'PROGRESS'},
  active:{n:'03',topic:'EXPERIMENTAL DESIGN',title:'Choose the next pose',subtitle:'Every measurement has a cost. Make the next one count.',scene:'WORKSPACE / INFORMATION GAIN',timeline:'POSE BUDGET'},
  observability:{n:'04',topic:'PARAMETER OBSERVABILITY',title:'See the invisible',subtitle:'Some model changes leave no trace in the measurements.',scene:'MEASUREMENTS / WEAK DIRECTIONS',timeline:'PERTURBATION'},
  compliance:{n:'05',topic:'LOAD-DEPENDENT ERRORS',title:'Geometry or arm flex?',subtitle:'A model calibrated without a payload can bend under new evidence.',scene:'PAYLOAD / JOINT DEFLECTION',timeline:'PAYLOAD'}
};
let data,view,module='ghost',index=0,playing=false,lastTick=0;
let ghostView='arm',sweepMode='before',measurement='point',coverage='broad',prediction='rigid',exaggeration=5;
let pointView='gain';
const metric=(label,value,unit,detail,accent=false)=>`<div class="metric ${accent?'accent':''}"><div class="label">${label}</div><div class="value">${value}<em>${unit}</em></div><div class="detail">${detail}</div></div>`;
const select=(id,label,options,value)=>`<div class="field"><label for="${id}">${label}</label><select id="${id}">${options.map(([v,t])=>`<option value="${v}" ${String(value)===String(v)?'selected':''}>${t}</option>`).join('')}</select></div>`;
const readout=(rows)=>rows.map(([k,v])=>`<div class="readout-row"><span>${k}</span><strong>${v}</strong></div>`).join('');

function frames(){const d=data[module];return module==='redundancy'?d[`${sweepMode}_frames`]:module==='observability'?d.cases[`${measurement}_${coverage}`].frames:d.frames;}
function setPlaying(value){playing=value;$('play').textContent=value?'Ⅱ':'▶';$('play').setAttribute('aria-label',value?'Pause experiment animation':'Play experiment animation');lastTick=performance.now();}
function switchModule(key){setPlaying(false);module=key;index=key==='observability'?32:key==='compliance'?40:0;render();history.replaceState(null,'',`#${key}`);}
function chart(which,title,unit,html,caption){$(`chart-${which}-title`).textContent=title;$(`chart-${which}-unit`).textContent=unit;$(`chart-${which}`).innerHTML=html;$(`chart-${which}-caption`).textContent=caption;}

function render(){
  const m=META[module],d=data[module];
  document.querySelectorAll('.nav-item').forEach(el=>{const selected=el.dataset.module===module;el.classList.toggle('active',selected);el.setAttribute('aria-current',selected?'page':'false');});
  $('eyebrow').textContent=`EXPERIMENT ${m.n} / ${m.topic}`;
  $('title').innerHTML=m.title+'<span>.</span>';$('subtitle').textContent=m.subtitle;
  $('scene-title').textContent=m.scene;$('timeline-label').textContent=m.timeline;
  $('status').textContent='';
  view?.setCloud(null);view?.setPath(null);
  $('truth-label').textContent='Physical arm';$('estimate-label').textContent='Predicted arm';
  if(module==='ghost')renderGhost(d);
  if(module==='redundancy')renderRedundancy(d);
  if(module==='active')renderActive(d);
  if(module==='observability')renderObservability(d);
  if(module==='compliance')renderCompliance(d);
  $('timeline').max=frames().length-1;
  $('timeline').setAttribute('aria-label',`${m.timeline.toLowerCase()} playback`);
  update();
}

function renderGhost(d){
  const improvement=100*(1-d.final.position_mm/d.initial.position_mm);
  $('metrics').innerHTML=metric('Before calibration',fmt(d.initial.position_mm),'mm','Held-out position RMS')+metric('After calibration',fmt(d.final.position_mm,3),'mm',`${fmt(Math.abs(improvement),1)}% ${improvement>=0?'less':'more'} position error`,true)+metric('Orientation after fit',fmt(d.final.orientation_deg,3),'°','Held-out orientation RMS')+metric('Training observations',d.count,'poses',`${d.spread} · ${d.noise_mm} mm noise`);
  $('controls').innerHTML=`<div class="field"><label for="sample-count">Training samples <output id="sample-value">${d.count}</output></label><input id="sample-count" type="range" min="4" max="128" step="4" value="${d.count}"><div class="range-ends"><span>4 POSES</span><span>128 POSES</span></div></div><div class="field"><label for="noise">Observation noise <output id="noise-value">${d.noise_mm} mm</output></label><input id="noise" type="range" min="0" max="3" step=".25" value="${d.noise_mm}"></div>`+select('coverage','Pose coverage',[['diverse','Diverse configurations'],['clustered','Clustered around one pose']],d.spread)+select('ghost-view','Visualization',[['arm','Physical arm + model'],['workspace','Held-out error map']],ghostView)+`<button class="primary" id="run-calibration">Run calibration ↗</button><p class="control-note">Fit seven encoder offsets from noisy full hand poses. Replay accepted optimizer iterations.</p>`;
  $('sample-count').oninput=e=>$('sample-value').textContent=e.target.value;
  $('noise').oninput=e=>$('noise-value').textContent=`${e.target.value} mm`;
  $('ghost-view').onchange=e=>{ghostView=e.target.value;update();};
  $('run-calibration').onclick=runGhost;
  $('takeaway').textContent='Calibration learns one set of offsets that explains many measured hand poses. Diverse configurations help separate the effects of different joints; the real test is accuracy at configurations the fit never saw.';
  $('method').innerHTML=`<p><code>T(q; θ) = FK(q + θ)</code>. We fit seven bounded encoder zero offsets with nonlinear least squares, using translation residuals and the SO(3) rotation logarithm. Residual weights are 1 mm and 0.15°. The noise control scales measurement standard deviations together: 1 mm corresponds to 0.15° per rotational component. Camera, base and palm transforms are known.</p><p>The error map evaluates 160 fixed, unseen configurations against noise-free synthetic truth. Its color scale is fixed to the initial maximum error (${fmt(Math.max(...d.initial.per_pose_mm),1)} mm) throughout playback, so improvement is visually comparable. Optimizer history contains accepted iterates, not an invented interpolation. Configuration and noise samples use a fixed seed; different sample counts are separate deterministic datasets.</p>`;
}

async function runGhost(){
  const button=$('run-calibration');button.disabled=true;button.textContent='Fitting offsets…';setPlaying(false);
  const options={count:Number($('sample-count').value),noise_mm:Number($('noise').value),spread:$('coverage').value};
  try{
    const response=await fetch('/api/ghost',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(options)});
    const result=await response.json();if(!response.ok)throw new Error(result.error||'Calibration failed');
    data.ghost=result;
    if(module==='ghost'){index=0;render();setPlaying(true);}
  }catch(error){$('status').textContent=`Could not run calibration: ${error.message}. Start the dashboard with python server.py.`;button.disabled=false;button.textContent='Run calibration ↗';}
}

function renderRedundancy(d){
  $('metrics').innerHTML=metric('Physical drift before',fmt(d.before.max_position_mm),'mm','Maximum from starting hand pose')+metric('Physical drift after',fmt(d.after.max_position_mm,3),'mm','Motion replanned after calibration',true)+metric('Orientation drift after',fmt(d.after.max_orientation_deg,3),'°','Maximum from starting orientation')+metric('Nominal position drift','< 0.0001','mm','Full-pose constraint verified');
  $('controls').innerHTML=select('sweep-mode','Motion planning model',[['before','Before calibration'],['after','After calibration · replanned']],sweepMode)+`<button class="primary" id="replay">Replay elbow sweep ↗</button><p class="control-note">Seven joints, six pose constraints. Follow the remaining local direction, then correct the complete hand pose after every finite step.</p><p class="control-note">The after-calibration motion uses new joint commands. Hand drift is measured relative to each trajectory’s own starting pose.</p>`;
  $('sweep-mode').onchange=e=>{sweepMode=e.target.value;index=0;render();};
  $('replay').onclick=()=>{index=0;setPlaying(true);};
  const comparison=`<table class="comparison"><thead><tr><th>24 observations</th><th>RMS mm</th><th>Rank</th><th>Cond.</th></tr></thead><tbody>${d.comparison.map(r=>`<tr><td>${r.label}</td><td>${fmt(r.position_mm,3)}</td><td>${r.rank}/7</td><td>${fmt(r.condition,1)}</td></tr>`).join('')}</tbody></table>`;
  chart('two','Which dataset calibrates better?','HELD-OUT',comparison,'One seeded noisy comparison at an equal pose budget. Rank belongs to the calibration Jacobian, not the motion Jacobian.');
  $('takeaway').textContent='Seven DOF makes inverse motion redundant, not forward kinematics ambiguous. Internal arm motion can expose model errors even when the planned hand pose is fixed. Here a single sweep identifies all seven offsets, but that depends on the model and parameters.';
  $('method').innerHTML=`<p><code>q̇ = J†v + (I − J†J)z</code>. This demo extracts the null vector using SVD, takes a small joint-space step, and retracts to the target pose with a Newton correction. Both orientation and position are constrained. Motion stops at a joint limit, near a singularity, or if pose correction fails.</p><p>Calibration for the before/after replay uses 32 independent workspace poses with 0.5 mm / 0.075° observation noise. The separate table compares three 24-pose datasets on the same 160 unseen configurations. The plotted drift uses meters converted to mm without rescaling time or normalizing each error curve. There is no collision checking or actuator model.</p><p><a href="https://modernrobotics.northwestern.edu/nu-gm-book-resource/5-3-singularities/" target="_blank" rel="noopener">Background: Modern Robotics, Jacobians and redundancy ↗</a></p>`;
}

function renderActive(d){
  const final=d.curve.at(-1);
  $('metrics').innerHTML=metric('Information-based fit',fmt(final.greedy_mm,3),'mm','Held-out RMS · 32 observations',true)+metric('Random-selection fit',fmt(final.random_median_mm,3),'mm',`Median of ${d.random_repeats} selections · 32 poses`)+metric('Orientation · selected fit',fmt(final.greedy_deg,3),'°','Held-out RMS · 32 observations')+metric('Candidate pool',d.pool_size,'poses','120 clustered + 60 diverse');
  $('controls').innerHTML=select('budget','Inspect measurement budget',[[2,'2 observations'],[4,'4 observations'],[8,'8 observations'],[12,'12 observations'],[20,'20 observations'],[32,'32 observations']],32)+select('point-view','Candidate display',[['gain','All candidates · information gain'],['selected','Selected candidates only']],pointView)+`<button class="primary" id="replay">Watch pose selection ↗</button><p class="control-note">Select the pose that most increases log det(I + Σ AᵀA). Warm points have larger marginal information gain; selected points are pale.</p><p class="control-note">The pool intentionally contains repeated-looking poses. Both policies use the same observations and measurement budgets.</p>`;
  $('budget').onchange=e=>{setPlaying(false);index=Number(e.target.value)-1;update();};
  $('point-view').onchange=e=>{pointView=e.target.value;update();};
  $('replay').onclick=()=>{index=0;setPlaying(true);};
  $('takeaway').textContent='Pose quality matters as well as pose count. The information criterion rewards measurements that add new parameter constraints. Its score is a local prediction, so held-out accuracy still has to be measured—and need not improve at every step.';
  $('method').innerHTML=`<p><code>next = argmax log det(F + AᵀA) − log det(F)</code>. A is the full-pose parameter Jacobian at the nominal model, whitened by 1 mm and 0.15° measurement standard deviations, then scaled by a 3° parameter prior. F starts at the identity. The prior regularizes early, underconstrained selections; it is not counted as measured information.</p><p>${d.note}</p><p>Models are actually refitted at budgets 2, 4, 8, 12, 20 and 32. The random baseline uses ten nested random selections, with median and interquartile band. These trials vary selection, not the noise realization. No assertion requires the greedy method to win.</p>`;
}

function renderObservability(d){
  const c=d.cases[`${measurement}_${coverage}`];
  $('metrics').innerHTML=metric('Observable local rank',`${c.rank} / 10`,'','Relative SVD threshold 10⁻⁷',true)+metric('Exact null dimensions',10-c.rank,'',measurement==='point'?'Terminal orientation is invisible':'For this model and dataset')+metric('Condition number',c.condition===null?'∞':fmt(c.condition,1),'','Scaled parameter sensitivity')+metric('Measurements per pose',measurement==='point'?3:6,'',measurement==='point'?'Position of the palm-frame origin':'Position + orientation');
  $('controls').innerHTML=select('measurement','What does perception measure?',[['point','One 3D hand point'],['pose','Full 6D hand pose']],measurement)+select('obs-coverage','Joint excitation',[['broad','Broad · workspace coverage'],['narrow','Narrow · ±0.002 rad per joint']],coverage)+`<button class="primary" id="replay">Animate weakest direction ↗</button><p class="control-note">Change a combination of model parameters along the weakest right singular vector. Watch how little—or how much—the measurements change.</p><p class="control-note">The colored hand axes show orientation. Point-only perception cannot see them.</p>`;
  $('measurement').onchange=e=>{measurement=e.target.value;index=32;render();};
  $('obs-coverage').onchange=e=>{coverage=e.target.value;index=32;render();};
  $('replay').onclick=()=>{index=0;setPlaying(true);};
  $('truth-label').textContent='Reference model';$('estimate-label').textContent='Perturbed model';
  $('takeaway').textContent=measurement==='point'?'An orientation change of the terminal coordinate frame cannot move its origin. Those three parameters are exactly invisible to point-only observations, however many points you collect.':'Adding orientation measurements makes this ten-parameter model locally identifiable with diverse poses. Narrow excitation still produces a badly conditioned fit: local full rank is not the same as reliable estimation.';
  $('method').innerHTML=`<p>${d.note}</p><p><code>A = ∂r / ∂θ = UΣVᵀ</code>. The final column of V gives the parameter combination with the weakest local effect on observations. The slider applies an actual finite perturbation of up to 8° in that direction and recomputes nonlinear FK; it does not assume the linearized prediction stays exact. In the point-only cases, the tool-frame ambiguity is exact even for finite rotations.</p><p>Changing the terminal frame rotates the drawn hand and axes but leaves its origin unchanged. This demonstrates uncertainty in the frame transform, not an additional physical actuator. Tiny singular values are floored at 10⁻⁹ only for logarithmic plotting.</p>`;
}

function renderCompliance(d){
  const held=d.curve.find(x=>x.payload===2);
  $('metrics').innerHTML=metric('Rigid fit · unseen 2 kg',fmt(held.geometry_mm,3),'mm','Held-out position RMS')+metric('Elastic fit · unseen 2 kg',fmt(held.elastic_mm,3),'mm','Held-out position RMS',true)+metric('Fitted elbow compliance',fmt(d.estimated_compliance*1000,3),'mrad/Nm',`Injected value ${fmt(d.true_compliance*1000,3)}`)+metric('Orientation · unseen 2 kg',fmt(held.elastic_deg,3),'°','Held-out orientation RMS');
  $('controls').innerHTML=select('prediction','Compare the physical arm against',[['rigid','Unloaded geometric fit'],['elastic','Offsets + compliance fit']],prediction)+select('exaggeration','Displacement exaggeration',[[1,'1× · physical scale'],[5,'5× · displacement only'],[10,'10× · displacement only']],exaggeration)+select('payload','Inspect payload',[[0,'0 kg · training load'],[.5,'0.5 kg · unseen load'],[1,'1 kg · training load'],[2,'2 kg · unseen load'],[3,'3 kg · training load']],2)+`<button class="primary" id="replay">Sweep the payload ↗</button><p class="control-note">Gravity creates elbow torque. A small angular deflection changes the hand pose. Reported errors always use physical scale.</p>`;
  $('prediction').onchange=e=>{prediction=e.target.value;update();};
  $('exaggeration').onchange=e=>{exaggeration=Number(e.target.value);update();};
  $('payload').onchange=e=>{setPlaying(false);index=Math.round(Number(e.target.value)*20);update();};
  $('replay').onclick=()=>{index=0;setPlaying(true);};
  chart('two','Residual versus elbow torque','UNSEEN 2 KG',lineChart([{label:'Unloaded rigid fit',color:C.amber,points:d.scatter.torque_nm.map((t,i)=>[t,d.scatter.geometry_mm[i]])},{label:'Compliance fit',color:C.teal,points:d.scatter.torque_nm.map((t,i)=>[t,d.scatter.elastic_mm[i]])}],{xlabel:'Absolute gravity torque [Nm]',ylabel:'Position error [mm]',scatter:true}),'Each point is an unseen configuration. Residual magnitudes use the true synthetic torque for this diagnostic.');
  $('takeaway').textContent='A constant offset cannot explain a deflection that changes with load and configuration. Even a rigid fit trained on mixed payloads leaves systematic error. A small compliance model explains the missing effect and generalizes to unseen configurations and loads.';
  $('method').innerHTML=`<p><code>τ = Jᵀ[0, 0, −mg, 0, 0, 0]ᵀ</code> and <code>Δq₄ = c τ₄</code>. The synthetic arm has compliance only at elbow joint 4. Fitting uses seven offsets plus one nonnegative compliance parameter. A separate mixed-load rigid fit receives exactly the same observations as the compliance fit, so the chart can distinguish extra data from a better model.</p><p>${d.note}</p><p>Position exaggeration displaces rendered nodes relative to the selected predicted model. It does not rescale reported errors or hand orientation. The scene is illustrative when exaggeration is enabled; use 1× for actual geometry.</p>`;
}

function update(){
  const all=frames();index=Math.max(0,Math.min(index,all.length-1));const f=all[index],d=data[module];
  $('timeline').max=all.length-1;$('timeline').value=index;
  $('frame-label').textContent=`${index} / ${all.length-1}`;
  $('scene-detail').innerHTML='';
  if(module==='ghost'){
    view?.update(f,{hideArms:ghostView==='workspace'});
    view?.setCloud(ghostView==='workspace'?d.test_positions:null,f.metrics.per_pose_mm,Math.max(...d.initial.per_pose_mm));
    $('scene-badge').textContent=ghostView==='workspace'?'ERROR MAP · FIXED COLOR SCALE':`OPTIMIZER ITERATE ${index}`;
    if(ghostView==='workspace')$('scene-detail').innerHTML=`<div class="color-scale">POSITION ERROR / MM<div></div><span>0</span><span>${fmt(Math.max(...d.initial.per_pose_mm),1)}</span></div>`;
    $('frame-readout').innerHTML=readout([['Current test RMS',`${fmt(f.metrics.position_mm,3)} mm`],['Orientation RMS',`${fmt(f.metrics.orientation_deg,3)}°`],['Data condition',fmt(d.condition,1)]]);
    const offsetLimit=Math.max(3.2,...d.frames.flatMap(frame=>frame.offsets_deg.map(v=>Math.abs(v)*1.15)));
    chart('one','Recovered encoder offsets','DEGREES',barChart(['J1','J2','J3','J4','J5','J6','J7'],[{label:'Injected truth',color:C.teal,values:d.true_offsets_deg},{label:'Current estimate',color:C.amber,values:f.offsets_deg}],{limit:offsetLimit}),'Seven shared offsets explain the entire dataset. Zero is the uncalibrated starting model.');
    chart('two','Accuracy beyond the training poses','POSITION RMS / MM',lineChart([{label:'Held-out error',color:C.teal,points:d.frames.map((x,i)=>[i,x.metrics.position_mm])}],{xlabel:'Accepted optimizer iteration',ylabel:'Held-out position RMS [mm]',marker:index}),'160 unseen configurations, evaluated against noise-free truth. The full completed fit is shown; playback follows actual iterations.');
  }
  if(module==='redundancy'){
    view?.update(f);view?.setPath(d[sweepMode].positions);
    const trace=d[sweepMode].trace_mm[index];
    $('scene-badge').textContent=sweepMode==='before'?'UNCALIBRATED PLANNER':'CALIBRATED PLANNER · NEW MOTION';
    $('frame-label').textContent=`${Math.round(index/(all.length-1)*100)}%`;
    $('frame-readout').innerHTML=readout([['Current hand drift',`${fmt(Math.hypot(...trace),3)} mm`],['Elbow angle',`${fmt(f.q_deg[3],1)}°`],['Trajectory frames',all.length]]);
    const maxDrift=d.before.max_position_mm;
    const project=p=>[75+p[0]*48/maxDrift,72-p[2]*48/maxDrift];
    const path=points=>points.map(p=>project(p).join(',')).join(' ');
    const marker=project(trace);
    $('scene-detail').innerHTML=`<div class="drift-inset"><span>HAND DRIFT · XZ PLANE</span><svg viewBox="0 0 150 125" role="img" aria-label="Hand drift trajectory in the world XZ plane"><path d="M18 72H135 M75 12V110" stroke="#3a5167" stroke-width="1"/><circle cx="75" cy="72" r="3" fill="#cadce8"/><polyline points="${path(d.before.trace_mm)}" fill="none" stroke="${C.amber}" stroke-width="2"/><polyline points="${path(d.after.trace_mm)}" fill="none" stroke="${C.teal}" stroke-width="2"/><circle cx="${marker[0]}" cy="${marker[1]}" r="3" fill="white"/><text x="136" y="69" fill="#91a2b9" font-size="9">X</text><text x="79" y="15" fill="#91a2b9" font-size="9">Z</text><path d="M15 116H${15+10*48/maxDrift}" stroke="#cadce8"/><text x="${20+10*48/maxDrift}" y="119" fill="#91a2b9" font-size="8">10 mm</text></svg></div>`;
    chart('one','Physical hand drift during self-motion','DISPLACEMENT / MM',lineChart([{label:'Before calibration',color:C.amber,points:d.before.trace_mm.map((p,i)=>[100*i/(d.before.trace_mm.length-1),Math.hypot(...p)])},{label:'Replanned after fit',color:C.teal,points:d.after.trace_mm.map((p,i)=>[100*i/(d.after.trace_mm.length-1),Math.hypot(...p)])}],{xlabel:'Trajectory progress [%]',ylabel:'Hand drift [mm]',marker:index/(all.length-1)*100}),'A magnified measurement view: vertical values are actual millimeters. Both curves share the same scale.');
  }
  if(module==='active'){
    view?.update(f);
    const selected=d.selection.slice(0,index+1);
    if(pointView==='gain')view?.setCloud(d.candidate_positions,d.gain_frames[index],Math.max(...d.gain_frames[0]),selected);
    else view?.setCloud(selected.map(i=>d.candidate_positions[i]));
    view?.setPath(selected.map(i=>d.candidate_positions[i]));
    $('scene-badge').textContent=`POSE ${index+1} / ${d.selection.length} · GREEDY INFORMATION`;
    $('scene-detail').innerHTML=`<div class="color-scale">MARGINAL INFORMATION GAIN<div></div><span>0</span><span>${fmt(Math.max(...d.gain_frames[0]),1)}</span></div>`;
    $('frame-label').textContent=`${index+1} / ${all.length}`;
    $('frame-readout').innerHTML=readout([['Selected candidate',`#${d.selection[index]+1}`],['Marginal log-det gain',fmt(d.gain_frames[index][d.selection[index]],3)],['Accumulated log det',fmt(d.logdet[index],2)]]);
    $('budget').value=d.curve.some(r=>r.count===index+1)?String(index+1):'';
    chart('one','Same budget. Different measurements.','POSITION RMS / MM · LOG',lineChart([{label:'Information gain',color:C.teal,points:d.curve.map(r=>[r.count,r.greedy_mm])},{label:'Random median',color:C.amber,points:d.curve.map(r=>[r.count,r.random_median_mm])}],{xlabel:'Number of observed poses',ylabel:'Held-out position RMS [mm]',log:true,band:d.curve.map(r=>[r.count,r.random_q25_mm,r.random_q75_mm]),marker:Math.max(2,index+1)}),'Band: 25th–75th percentile across ten random selections. These are actual refits, not predicted errors.');
    chart('two','Diminishing returns on new poses','LOG-DET GAIN',lineChart([{label:'Selected pose information gain',color:C.purple,points:d.selection.map((j,i)=>[i+1,d.gain_frames[i][j]])}],{xlabel:'Selection step',ylabel:'Marginal log-det information gain',marker:index+1}),'Whitened sensitivities and a 3° parameter prior make the score dimensionless. Colors use the initial gain scale.');
  }
  if(module==='observability'){
    const c=d.cases[`${measurement}_${coverage}`];view?.update(f);
    $('scene-badge').textContent=measurement==='point'?'POSITION ONLY · ORIENTATION UNMEASURED':'FULL POSE · POSITION + ORIENTATION';
    $('frame-label').textContent=`${fmt(f.amplitude_deg,2)}°`;
    $('frame-readout').innerHTML=readout([['Position change',`${fmt(f.metrics.position_mm,4)} mm`],[measurement==='point'?'Unmeasured rotation':'Orientation change',`${fmt(f.metrics.orientation_deg,3)}°`],['Parameter-vector norm',`${fmt(Math.abs(f.amplitude_deg),2)}°`]]);
    chart('one','Which parameter directions are visible?','SINGULAR VALUES · LOG',lineChart([{label:`${measurement==='point'?'Point':'Full pose'} · ${coverage}`,color:C.teal,points:c.singular_values.map((s,i)=>[i+1,Math.max(s,1e-9)])},{label:'Full pose · broad reference',color:C.purple,points:d.cases.pose_broad.singular_values.map((s,i)=>[i+1,Math.max(s,1e-9)])}],{xlabel:'Singular value index',ylabel:'Whitened sensitivity per degree',log:true}),'Zero singular values are displayed at the 10⁻⁹ plotting floor. Weak is different from exactly unobservable.');
    chart('two','Move along the weakest direction','PARAMETER CHANGE / DEG',barChart(d.parameter_names,[{label:'Applied finite perturbation',color:C.amber,values:f.parameter_delta_deg}],{limit:8.5}),'J1–J7 are encoder offsets. Tool x/y/z rotate the terminal coordinate frame without translating its origin.');
  }
  if(module==='compliance'){
    view?.update(f,{elastic:prediction==='elastic',exaggeration});
    const predicted=prediction==='elastic'?f.elastic:f.estimate;
    const residual=Math.hypot(...f.truth.position.map((p,i)=>(p-predicted.position[i])*1000));
    $('truth-label').textContent=`Physical arm · displacement ×${exaggeration}`;$('estimate-label').textContent=prediction==='elastic'?'Compliance model':'Rigid model';
    $('scene-badge').textContent=`${fmt(f.payload,2)} KG · DISPLACEMENT ×${exaggeration}`;
    $('frame-label').textContent=`${fmt(f.payload,2)} kg`;
    $('payload').value=[0,.5,1,2,3].includes(f.payload)?String(f.payload):'';
    $('frame-readout').innerHTML=readout([['Physical-scale residual',`${fmt(residual,3)} mm`],['Signed elbow torque',`${fmt(f.torque_nm,2)} Nm`],['Rendered displacement',`×${exaggeration}`]]);
    chart('one','Error that grows with the payload','POSITION RMS / MM',lineChart([{label:'Unloaded rigid fit',color:C.amber,points:d.curve.map(r=>[r.payload,r.geometry_mm])},{label:'Mixed-load rigid fit',color:C.purple,points:d.curve.map(r=>[r.payload,r.mixed_geometry_mm])},{label:'Compliance fit',color:C.teal,points:d.curve.map(r=>[r.payload,r.elastic_mm])}],{xlabel:'Payload [kg] · 0.5 and 2 kg unseen in training',ylabel:'Held-out position RMS [mm]',marker:f.payload}),'All curves use unseen configurations. Mixed-load rigid and compliance fits use the same 96 observations.');
  }
}

function animation(now){
  if(data&&playing){const delay=module==='ghost'?700:module==='active'?220:65;if(now-lastTick>=delay){lastTick=now;if(index>=frames().length-1)setPlaying(false);else{index++;update();}}}
  requestAnimationFrame(animation);
}

$('timeline').oninput=e=>{setPlaying(false);index=Number(e.target.value);update();};
$('play').onclick=()=>{if(!playing&&index===frames().length-1)index=0;setPlaying(!playing);update();};
$('reset-view').onclick=()=>view?.reset();$('snapshot').onclick=()=>view?.snapshot();
$('export-data').onclick=()=>{const blob=new Blob([JSON.stringify(data[module],null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`calibration-${module}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
document.querySelectorAll('.nav-item').forEach(el=>el.onclick=()=>data&&switchModule(el.dataset.module));
try{
  const response=await fetch('../results/data.json');if(!response.ok)throw new Error('Experiment results are missing. Run python run_experiments.py.');
  data=await response.json();
  try{view=new ArmScene($('viewport'));}catch(error){$('render-error').hidden=false;$('render-error').textContent=`The 3D view needs WebGL. Numerical results and controls are still available. ${error.message}`;}
  const initial=location.hash.slice(1);switchModule(META[initial]?initial:'ghost');
  window.calibrationLab={get module(){return module;},get data(){return data;},get index(){return index;},get hasWebGL(){return !!view;}};
  requestAnimationFrame(animation);
}catch(error){$('status').textContent=error.message;$('play').disabled=true;$('export-data').disabled=true;}
