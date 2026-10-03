export const C={green:'#70e1bd',amber:'#ffc27f',pink:'#ff91aa',blue:'#8fbfe8',muted:'#94a9c1'};
export const fmt=(x,n=2)=>Number.isFinite(x)?(Math.abs(x)>=10000?x.toExponential(1):x.toFixed(n)):'—';
export const esc=x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
export function cameraPoint(p,t){const d=p.map((v,i)=>v-t[i][3]);return [0,1,2].map(j=>d.reduce((sum,v,i)=>sum+v*t[i][j],0));}
function project(p,k){return [p[0]/Math.max(p[2],.001)*k.fx+k.cx,p[1]/Math.max(p[2],.001)*k.fy+k.cy];}

export function cameraView(sample,iteration,stage,selected,k){
  const w=k.width,h=k.height;
  const factor=w/960;
  let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Perceived landmarks and FK projections in the head-camera image plane"><defs><clipPath id="image-window"><rect width="${w}" height="${h}"/></clipPath><radialGradient id="image-bg"><stop stop-color="#243b50"/><stop offset="1" stop-color="#102031"/></radialGradient></defs><rect width="${w}" height="${h}" fill="url(#image-bg)"/><g clip-path="url(#image-window)">`;
  for(let i=1;i<8;i++)svg+=`<path d="M${w*i/8} 0V${h} M0 ${h*i/8}H${w}" stroke="#3b536c" opacity=".25" stroke-width="${factor}"/>`;
  svg+=`<path d="M${k.cx-12*factor} ${k.cy}h${24*factor} M${k.cx} ${k.cy-12*factor}v${24*factor}" stroke="#728ca7" opacity=".6"/>`;
  const predicted=sample.snapshots[iteration];
  for(let side=0;side<2;side++){
    const observed=sample.observed_camera[side].map(p=>project(p,k));
    const visible=sample.visible[side];
    const model=predicted[side].points.map(p=>project(cameraPoint(p,sample.T_base_camera),k));
    const edges=[[0,1],[1,2],[2,3],[3,4],[4,5],[4,6],[4,7]];
    if(stage!==0){const nodes=predicted[side].nodes.map(p=>project(cameraPoint(p,sample.T_base_camera),k));svg+=`<polyline points="${nodes.map(p=>p.join(',')).join(' ')}" fill="none" stroke="${C.amber}" stroke-width="${12*factor}" stroke-linejoin="round" opacity=".15"/>`;}
    for(const [a,b] of edges)if(visible[a]&&visible[b])svg+=`<line x1="${observed[a][0]}" y1="${observed[a][1]}" x2="${observed[b][0]}" y2="${observed[b][1]}" stroke="${C.green}" stroke-width="${2*factor}" opacity=".45"/>`;
    for(let j=0;j<8;j++){
      if(!visible[j])continue;
      const [u,v]=observed[j],[x,y]=model[j],active=selected.side===side&&selected.landmark===j;
      if(stage!==0)svg+=`<line x1="${u}" y1="${v}" x2="${x}" y2="${y}" stroke="${C.pink}" stroke-width="${(active?2:1)*factor}"/><path d="M${x-6*factor} ${y}h${12*factor} M${x} ${y-6*factor}v${12*factor}" stroke="${C.amber}" stroke-width="${2*factor}"/>`;
      svg+=`<circle cx="${u}" cy="${v}" r="${(active?7:4)*factor}" fill="${C.green}"/>`;
      if(active)svg+=`<circle cx="${u}" cy="${v}" r="${15*factor}" fill="none" stroke="white" opacity=".7"/><text x="${u+18*factor}" y="${v-12*factor}" fill="#e2f6ed" font-family="monospace" font-size="${14*factor}">${side?'RIGHT':'LEFT'} ${j+1}</text>`;
      else if(j<4)svg+=`<text x="${u+7*factor}" y="${v-7*factor}" fill="#a2c0d1" font-family="monospace" font-size="${11*factor}">${side?'R':'L'}${j+1}</text>`;
    }
  }
  svg+=`<text x="${18*factor}" y="${27*factor}" fill="#8da9bf" font-family="monospace" font-size="${12*factor}">CAMERA OPTICAL FRAME · X RIGHT / Y DOWN / Z FORWARD</text>`;
  return svg+'</g></svg>';
}

export function residualView(sample,iteration,stage,selected){
  const s=selected.side,j=selected.landmark;
  if(!sample.visible[s][j])return '<div class="empty-state">This landmark is missing in this frame.<br>It contributes no residual to the fit. Choose another point or observation.</div>';
  const observed=sample.observed_camera[s][j],sigma=sample.sigma_mm[s][j];
  if(stage===0)return `<div class="empty-state"><b>Perceived 3D position [mm]</b><br>X ${fmt(observed[0]*1000,1)} · Y ${fmt(observed[1]*1000,1)} · Z ${fmt(observed[2]*1000,1)}<br>Uncertainty σ [mm]: ${sigma.map(v=>fmt(v,1)).join(' / ')}<br><br>These measurements stay fixed when the kinematic model is calibrated.</div>`;
  const point=cameraPoint(sample.snapshots[iteration][s].points[j],sample.T_base_camera);
  const delta=point.map((v,i)=>(v-observed[i])*1000);
  const initial=cameraPoint(sample.snapshots[0][s].points[j],sample.T_base_camera).map((v,i)=>(v-observed[i])*1000);
  // Fixed across iterations for this selected observation, including nonlinear overshoot.
  const extent=Math.max(10,...sample.snapshots.flatMap(f=>cameraPoint(f[s].points[j],sample.T_base_camera).map((v,i)=>Math.abs((v-observed[i])*1000))));
  const limit=Math.ceil(extent/10)*10,scale=65/limit;
  const x=100+delta[0]*scale,y=88+delta[1]*scale;
  const sx=100+initial[0]*scale,sy=88+initial[1]*scale;
  const svg=`<svg viewBox="0 0 200 180" role="img" aria-label="Magnified camera XY residual, with depth shown separately"><path d="M20 88H180 M100 12V163" stroke="#44617b" stroke-dasharray="3 4"/><circle cx="100" cy="88" r="5" fill="${C.green}"/><path d="M100 88L${sx} ${sy}" stroke="${C.amber}" opacity=".22" stroke-width="2"/><circle cx="${sx}" cy="${sy}" r="4" fill="none" stroke="${C.amber}" opacity=".3"/><path d="M100 88L${x} ${y}" stroke="${C.pink}" stroke-width="2"/><path d="M${x-5} ${y}h10 M${x} ${y-5}v10" stroke="${C.amber}" stroke-width="2"/><g font-family="monospace" font-size="9" fill="#91acc5"><text x="105" y="18">−Y</text><text x="179" y="82">+X</text><text x="22" y="176">XY plane · ±${limit} mm</text></g></svg>`;
  return `<div class="inspector-content"><div><div class="residual-stat">${fmt(Math.hypot(...delta))}<small> mm · 3D</small></div><div class="residual-coords">${['Δ X','Δ Y','Δ Z (depth)'].map((name,i)=>`<span>${name}<b>${fmt(delta[i])} mm</b></span>`).join('')}<span>σ X/Y/Z<b>${sigma.map(v=>fmt(v,1)).join('/')}</b></span></div></div>${svg}</div>`;
}

export function lineChart(series,index){
  const w=620,h=230,left=48,right=16,top=18,bottom=37;
  const n=Math.max(...series.map(s=>s.values.length));
  const max=Math.max(1,...series.flatMap(s=>s.values)) * 1.1;
  const x=i=>left+i/Math.max(n-1,1)*(w-left-right),y=v=>h-bottom-v/max*(h-top-bottom);
  let s=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Observation error on training and validation frames across calibration iterations"><g font-family="monospace" font-size="10" fill="#91abc5">`;
  for(let i=0;i<=4;i++){const v=max*i/4,Y=y(v);s+=`<path d="M${left} ${Y}H${w-right}" stroke="#32465e" stroke-dasharray="3 4"/><text x="${left-7}" y="${Y+3}" text-anchor="end">${fmt(v,1)}</text>`;}
  const ticks=[...new Set([0,Math.round((n-1)/3),Math.round((n-1)*2/3),n-1])];
  for(const i of ticks)s+=`<text x="${x(i)}" y="${h-bottom+17}" text-anchor="middle">${i}</text>`;
  for(const line of series){s+=`<polyline points="${line.values.map((v,i)=>`${x(i)},${y(v)}`).join(' ')}" fill="none" stroke="${line.color}" stroke-width="2"/>`;line.values.forEach((v,i)=>s+=`<circle cx="${x(i)}" cy="${y(v)}" r="2.4" fill="${line.color}"/>`);}
  s+=`<path d="M${x(index)} ${top}V${h-bottom}" stroke="#d5e5f5" opacity=".4" stroke-dasharray="4 4"/><text x="${w/2}" y="${h-3}" text-anchor="middle">Accepted optimizer iteration</text></g></svg>`;
  return s+`<div class="chart-legend">${series.map(line=>`<span><i style="background:${line.color}"></i>${esc(line.label)}</span>`).join('')}</div>`;
}
