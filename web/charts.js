export const colors={teal:'#6de6c5',amber:'#ffc180',purple:'#b0a4fa',red:'#f594b0',muted:'#91a2b9'};
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
export const number=(v,d=2)=>!Number.isFinite(v)?'—':Math.abs(v)>9999?v.toExponential(1):v.toFixed(d);
const tick=v=>Math.abs(v)>=100?number(v,0):Math.abs(v)>=1?number(v,1):v===0?'0':Math.abs(v)<.01?v.toExponential(0):number(v,2);

export function lineChart(series,{xlabel='',ylabel='',log=false,band=null,scatter=false,marker=null,height=210}={}) {
  const w=560,h=height,p={l:53,r:17,t:14,b:36};
  const all=series.flatMap(s=>s.points);
  if(!all.length)return '';
  let xmin=Math.min(...all.map(p=>p[0])),xmax=Math.max(...all.map(p=>p[0]));
  if(xmin===xmax)xmax=xmin+1;
  let ys=all.map(p=>p[1]);if(band)ys.push(...band.flatMap(p=>[p[1],p[2]]));
  let ymin=log?Math.log10(Math.max(Math.min(...ys),1e-9)):Math.min(0,...ys);
  let ymax=log?Math.log10(Math.max(Math.max(...ys),1e-8)):Math.max(...ys);
  if(ymin===ymax)ymax=ymin+1;
  ymax+=(ymax-ymin)*.08;
  const x=v=>p.l+(v-xmin)/(xmax-xmin)*(w-p.l-p.r);
  const y=v=>h-p.b-((log?Math.log10(Math.max(v,1e-9)):v)-ymin)/(ymax-ymin)*(h-p.t-p.b);
  let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(ylabel)} versus ${esc(xlabel)}"><g font-family="monospace" font-size="9" fill="#91a2b9">`;
  for(let i=0;i<=4;i++) {
    const v=ymin+(ymax-ymin)*i/4,Y=h-p.b-(h-p.t-p.b)*i/4;
    svg+=`<line x1="${p.l}" x2="${w-p.r}" y1="${Y}" y2="${Y}" stroke="#28364a" stroke-dasharray="3 4"/><text x="${p.l-9}" y="${Y+3}" text-anchor="end">${tick(log?10**v:v)}</text>`;
    const xv=xmin+(xmax-xmin)*i/4;
    svg+=`<text x="${x(xv)}" y="${h-p.b+16}" text-anchor="middle">${tick(xv)}</text>`;
  }
  svg+=`<text x="${(w+p.l)/2}" y="${h-3}" text-anchor="middle" fill="#7890aa">${esc(xlabel)}</text>`;
  if(band){const upper=band.map(v=>`${x(v[0])},${y(v[2])}`).join(' '),lower=[...band].reverse().map(v=>`${x(v[0])},${y(v[1])}`).join(' ');svg+=`<polygon points="${upper} ${lower}" fill="${colors.amber}" opacity=".12"/>`;}
  for(const s of series) {
    if(!scatter)svg+=`<polyline points="${s.points.map(v=>`${x(v[0])},${y(v[1])}`).join(' ')}" fill="none" stroke="${s.color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`;
    if(scatter||s.points.length<40)for(const v of s.points)svg+=`<circle cx="${x(v[0])}" cy="${y(v[1])}" r="${scatter?2.1:2.8}" fill="${s.color}" opacity="${scatter?.6:1}"/>`;
  }
  if(marker!==null)svg+=`<line x1="${x(marker)}" x2="${x(marker)}" y1="${p.t}" y2="${h-p.b}" stroke="#d7e6f8" stroke-dasharray="4 4" opacity=".4"/>`;
  svg+='</g></svg>';
  return svg+`<div class="chart-legend">${series.map(s=>`<span><i style="background:${s.color}"></i>${esc(s.label)}</span>`).join('')}</div>`;
}

export function barChart(labels,series,{unit='deg',limit=null}={}) {
  const w=560,h=210,p={l:35,r:12,t:12,b:30};
  const max=limit??Math.max(1,...series.flatMap(s=>s.values.map(Math.abs)))*1.18;
  const center=p.t+(h-p.t-p.b)/2,scale=(h-p.t-p.b)/2/max;
  const slot=(w-p.l-p.r)/labels.length,bw=Math.min(17,slot/(series.length+1));
  let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Parameter values in ${esc(unit)}"><g font-family="monospace" font-size="9" fill="#91a2b9">`;
  for(const sign of [-1,0,1]){const y=center-sign*max*.8*scale;svg+=`<line x1="${p.l}" x2="${w-p.r}" y1="${y}" y2="${y}" stroke="#314155" stroke-dasharray="${sign===0?'0':'3 4'}"/><text x="${p.l-5}" y="${y+3}" text-anchor="end">${number(sign*max*.8,1)}</text>`;}
  labels.forEach((label,i)=>{
    const cx=p.l+(i+.5)*slot;
    svg+=`<text x="${cx}" y="${h-10}" text-anchor="middle">${esc(label)}</text>`;
    series.forEach((s,k)=>{const v=s.values[i],bh=Math.abs(v)*scale;svg+=`<rect x="${cx+(k-series.length/2)*bw}" y="${v>0?center-bh:center}" width="${bw-3}" height="${Math.max(bh,.5)}" rx="2" fill="${s.color}" opacity=".85"/>`;});
  });
  return svg+'</g></svg>'+`<div class="chart-legend">${series.map(s=>`<span><i style="background:${s.color}"></i>${esc(s.label)}</span>`).join('')}</div>`;
}
