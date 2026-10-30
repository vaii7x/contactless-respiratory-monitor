import React,{useEffect,useRef,useState} from 'react';import{createRoot}from'react-dom/client';import'./style.css';
const API='http://127.0.0.1:8000',WS='ws://127.0.0.1:8000/ws',WINDOW=30,KEEP=1500;

function draw(cv,pts){
 const dpr=window.devicePixelRatio||1,w=cv.clientWidth,h=cv.clientHeight;
 if(cv.width!==w*dpr||cv.height!==h*dpr){cv.width=w*dpr;cv.height=h*dpr}
 const g=cv.getContext('2d'),css=getComputedStyle(cv);g.setTransform(dpr,0,0,dpr,0,0);g.clearRect(0,0,w,h);
 g.strokeStyle=css.getPropertyValue('--grid');g.lineWidth=1;g.beginPath();
 for(let i=1;i<6;i++){const x=Math.round(w*i/6)+.5;g.moveTo(x,0);g.lineTo(x,h)}
 for(let i=1;i<4;i++){const y=Math.round(h*i/4)+.5;g.moveTo(0,y);g.lineTo(w,y)}
 g.stroke();
 if(pts.length<2)return;
 const t1=pts[pts.length-1].timestamp,t0=t1-WINDOW,vis=pts.filter(p=>p.timestamp>=t0),vals=vis.map(p=>p.distance_cm);
 let lo=Math.min(...vals),hi=Math.max(...vals);const pad=Math.max((hi-lo)*.15,.5);lo-=pad;hi+=pad;
 const X=t=>(t-t0)/WINDOW*w,Y=v=>h-(v-lo)/(hi-lo)*h;
 g.strokeStyle=css.getPropertyValue('--trace');g.lineWidth=1.75;g.lineJoin='round';g.beginPath();
 vis.forEach((p,i)=>i?g.lineTo(X(p.timestamp),Y(p.distance_cm)):g.moveTo(X(p.timestamp),Y(p.distance_cm)));g.stroke();
 // each detected breath peak, drawn where it happened (detection itself comes a moment later)
 g.fillStyle=css.getPropertyValue('--ink');
 vis.forEach(p=>{if(p.peak&&p.peak[0]>=t0){g.beginPath();g.arc(X(p.peak[0]),Y(p.peak[1]),3.5,0,2*Math.PI);g.fill()}});
 g.fillStyle=css.getPropertyValue('--muted');g.font='11px "IBM Plex Mono",monospace';
 g.fillText(hi.toFixed(1)+' cm',6,14);g.fillText(lo.toFixed(1)+' cm',6,h-6);
 for(let i=1;i<6;i++)g.fillText(`-${WINDOW-WINDOW*i/6}s`,w*i/6+4,h-6);
}

function Readout({label,value,unit,note,warn}){return <div className="readout"><span className="label">{label}</span><span className="value">{value??'—'}{value!=null&&unit&&<small> {unit}</small>}</span><span className={warn?'note warn':'note'}>{note}</span></div>}

const band=r=>r==null?null:r<12?'slow':r<=20?'normal':'fast';
// short beep; the AudioContext is created on a click because browsers block sound before user interaction
function beep(ctx){const o=ctx.createOscillator(),g=ctx.createGain();o.frequency.value=880;g.gain.value=.2;o.connect(g).connect(ctx.destination);o.start();o.stop(ctx.currentTime+.25)}

function App(){const [s,S]=useState({}),[,T]=useState(0),[ports,P]=useState([]),[port,C]=useState(''),[err,E]=useState(''),[online,O]=useState(false),[sessions,H]=useState([]);
const buf=useRef([]),cv=useRef(null),audio=useRef(null);
function unlockAudio(){try{audio.current??=new AudioContext()}catch{}}
async function req(path,opts={}){let r=await fetch(API+path,{headers:{'Content-Type':'application/json'},...opts});let d=await r.json();if(!r.ok)throw Error(d.detail||'Request failed');return d}
// ports scan is slow on Windows, so it stays off the live path
async function refresh(){try{P((await req('/api/ports')).ports);H((await req('/api/sessions')).sessions)}catch{}}
useEffect(()=>{refresh();let t=setInterval(refresh,3000);return()=>clearInterval(t)},[]);
useEffect(()=>{let ws,timer,dead=false;
 function open(){ws=new WebSocket(WS);ws.onopen=()=>O(true);
  ws.onclose=()=>{O(false);if(!dead)timer=setTimeout(open,1000)};
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.reset)buf.current=[];if(m.new.length)buf.current=buf.current.concat(m.new).slice(-KEEP);S(m.state);T(t=>t+1)}}
 open();return()=>{dead=true;clearTimeout(timer);ws.close()}},[]);
useEffect(()=>{if(cv.current)draw(cv.current,buf.current)});
useEffect(()=>{if(s.apnea_s!=null&&audio.current)beep(audio.current)},[s.apnea_s]);
useEffect(()=>{const o=new ResizeObserver(()=>T(t=>t+1));o.observe(cv.current);return()=>o.disconnect()},[]);
async function act(path){unlockAudio();try{await req(path,{method:'POST'});E('')}catch(e){E(e.message)}refresh()}
async function connect(){unlockAudio();try{await req('/api/connect',{method:'POST',body:JSON.stringify({port,baudrate:115200})});E('')}catch(e){E(e.message)}}
const b=buf.current,recent=b.length?b.filter(p=>p.timestamp>b[b.length-1].timestamp-2):[];
const hz=s.connected&&recent.length>2?((recent.length-1)/(recent[recent.length-1].timestamp-recent[0].timestamp)).toFixed(1):null;
return <div className="page">
<header className="top"><div className="brand"><h1>PhaseBreathe</h1><span>contactless respiration monitor</span></div>
 <div className="device"><span className={'led'+(s.connected?' on':'')} title={s.connected?'Device connected':'No device'}/>
  <select value={s.connected?s.port:port} onChange={e=>C(e.target.value)} disabled={s.connected} aria-label="Serial port"><option value="">Serial port…</option>{ports.map(p=><option key={p.device} value={p.device}>{p.device} — {p.description}</option>)}</select>
  {s.connected&&<button onClick={()=>act('/api/calibrate')} disabled={s.calibrating!=null} title="Breathe normally for 10 s to tune breath detection to this person">{s.calibrating!=null?`Calibrating… ${s.calibrating} s`:'Calibrate'}</button>}
  {s.connected?<button onClick={()=>act('/api/disconnect')}>Disconnect</button>:<button className="primary" onClick={connect} disabled={!port||!online}>Connect</button>}
 </div></header>
{!online&&<p className="alert">Backend not reachable on 127.0.0.1:8000. Start it with start_backend.bat; this page reconnects on its own.</p>}
{s.apnea_s!=null&&<div className="apnea" role="alert"><b>No chest movement for {s.apnea_s} s — possible apnea event.</b><span>Check on the person and the sensor position. This prototype is not validated and cannot diagnose sleep apnea.</span></div>}
{err&&<p className="alert">{err} <button className="link" onClick={()=>E('')}>Dismiss</button></p>}
<section className="readouts">
 <Readout label="Respiratory rate" value={s.rate_bpm} unit="br/min" note={s.rate_bpm==null?'candidate estimate':`${band(s.rate_bpm)} (adult 12–20)${s.rate_spread!=null?` · ±${s.rate_spread}`:''}`} warn={s.rate_spread>3}/>
 <Readout label="Distance" value={s.distance_cm?.toFixed(2)} unit="cm" note={`smoothed · breath threshold ${s.threshold_cm??.25} cm`}/>
 <Readout label="Signal" value={s.quality} note={s.apnea_events?`${s.apnea_events} pause${s.apnea_events>1?'s':''} ≥10 s this connection`:'from last 5 s of motion'} warn={s.apnea_s!=null}/>
 <Readout label="Sample rate" value={hz} unit="Hz" note={s.valid_pct==null?`${s.samples||0} samples this connection`:`${s.valid_pct}% valid · ${s.invalid} no-echo`} warn={s.valid_pct!=null&&s.valid_pct<70}/>
</section>
<section className="scope"><div className="head"><h2>Chest distance</h2><span>{s.connected?'live · ':''}last {WINDOW} s</span></div>
 <div className="screen"><canvas ref={cv}/>{b.length<2&&<p className="idle">{s.connected?'Waiting for readings from the sensor.':'No signal. Pick the ESP32 port above and connect.'}</p>}</div>
 <p className="statusline">{s.status||'—'}</p></section>
<section className="lower">
 <div className="block"><h2>Recording</h2><p>{s.recording?'Every reading is being saved to phasebreathe.db.':'Readings are shown live but not saved until you start a session.'}</p>
  {s.recording?<button onClick={()=>act('/api/session/stop')}>Stop session</button>:<button className="primary" onClick={()=>act('/api/session/start')} disabled={!online}>Start session</button>}</div>
 <div className="block"><div className="head"><h2>Recent sessions</h2><a href={API+'/api/export.csv'}>Export CSV</a></div>
  {sessions.length?<div className="tablewrap"><table><thead><tr><th>#</th><th>Started</th><th>Ended</th><th className="num">Samples</th><th className="num">Rate avg (min–max)</th><th className="num">Pauses</th><th className="num">Valid</th></tr></thead><tbody>{sessions.map(x=><tr key={x.id}><td>{x.id}</td><td>{x.started}</td><td>{x.ended||'recording'}</td><td className="num">{x.samples}</td><td className="num">{x.avg_rate??'—'}{x.avg_rate!=null&&` (${x.min_rate}–${x.max_rate})`}</td><td className="num">{x.apnea_events??'—'}</td><td className="num">{x.valid_pct!=null?x.valid_pct+'%':'—'}</td></tr>)}</tbody></table></div>:<p className="muted">No sessions saved yet.</p>}</div>
</section>
<footer>Experimental prototype. Not validated for medical use — low movement does not mean breathing has stopped. Data stays on this computer.</footer>
</div>}
createRoot(document.getElementById('root')).render(<App/>);
