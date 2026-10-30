import asyncio,csv,io,re,sqlite3,threading,time,statistics
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
import serial, serial.tools.list_ports
from fastapi import FastAPI,HTTPException,WebSocket,WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

DB=Path(__file__).with_name("phasebreathe.db")
ser=None; serial_lock=threading.Lock(); stop_reader=threading.Event(); data_lock=threading.Lock()
state={"connected":False,"port":None,"distance_cm":None,"rate_bpm":None,"quality":"waiting","status":"Choose a COM port and connect","samples":0,"epoch":0,"recording":False,"invalid":0,"valid_pct":None,"apnea_s":None,"apnea_events":0,"rate_spread":None,"threshold_cm":.25,"calibrating":None}
# sized for ~25 Hz firmware: 30 s of history, 5 s motion window
history=deque(maxlen=750); raw_window=deque(maxlen=5); motion=deque(maxlen=125); rates=deque(maxlen=3); outcomes=deque(maxlen=125)
smooth=None; last_distance=None; last_change=time.time(); last_peak=None; ext=None; rising=True; in_apnea=False
thr=.25; calib_until=None; calib_vals=[]
recording=False; session_id=None; session_base=None; pending=[]; db_lock=threading.Lock()

def dbinit():
 with sqlite3.connect(DB) as c:
  c.execute("CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY AUTOINCREMENT,started TEXT NOT NULL,ended TEXT,samples INTEGER DEFAULT 0)")
  c.execute("CREATE TABLE IF NOT EXISTS readings(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id INTEGER,timestamp REAL,distance REAL,rate REAL,status TEXT)")
  c.execute("CREATE INDEX IF NOT EXISTS readings_session ON readings(session_id)")
  # added later; older databases need the columns
  for col in ("apnea_events INTEGER","valid_pct INTEGER"):
   try:c.execute(f"ALTER TABLE sessions ADD COLUMN {col}")
   except sqlite3.OperationalError:pass
@asynccontextmanager
async def lifespan(app):
 dbinit(); yield; close_serial(); flush()
app=FastAPI(title="PhaseBreathe API",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:5173","http://127.0.0.1:5173"],allow_methods=["*"],allow_headers=["*"])
class ConnectRequest(BaseModel):
 port:str
 baudrate:int=115200
def close_serial():
 global ser
 stop_reader.set()
 with serial_lock: old,ser=ser,None
 if old:
  try: old.close()
  except Exception: pass
 with data_lock: state["connected"]=False
def reset():
 global smooth,last_distance,last_change,last_peak,ext,rising,in_apnea,thr,calib_until
 raw_window.clear();motion.clear();rates.clear();outcomes.clear()
 smooth=last_distance=last_peak=ext=calib_until=None;rising=True;in_apnea=False;last_change=time.time();thr=.25
 with data_lock:
  history.clear()
  state.update(distance_cm=None,rate_bpm=None,quality="waiting",status="Waiting for serial readings",samples=0,epoch=state["epoch"]+1,invalid=0,valid_pct=None,apnea_s=None,apnea_events=0,rate_spread=None,threshold_cm=.25,calibrating=None)
def flush():
 with db_lock: rows=pending[:];pending.clear()
 if not rows:return
 with sqlite3.connect(DB) as c:
  c.executemany("INSERT INTO readings(session_id,timestamp,distance,rate,status) VALUES(?,?,?,?,?)",rows)
  for sid in {r[0] for r in rows}:c.execute("UPDATE sessions SET samples=samples+? WHERE id=?",(sum(r[0]==sid for r in rows),sid))
def parse_distance(line):
 if line.startswith("DIST,"):
  try:return float(line.split(",",1)[1])
  except ValueError:return None
 m=re.search(r"Distance:\s*(-?\d+(?:\.\d+)?)\s*cm",line,re.I)
 return float(m.group(1)) if m else None
def process_distance(raw):
 global smooth,last_distance,last_change,last_peak,ext,rising,in_apnea,thr,calib_until
 now=time.time()
 if not 2<=raw<=250:
  with data_lock:state.update(status="Invalid distance reading",quality="poor")
  return
 # Algorithm 1: median filter; Algorithm 2: exponential moving average.
 raw_window.append(float(raw)); med=statistics.median(raw_window)
 # alpha .2 at 25 Hz (~0.2 s lag): heavier smoothing flattened fast breaths below the 0.25 cm peak threshold
 smooth=med if smooth is None else .2*med+.8*smooth
 d=smooth
 # measured from the last moved-to point, not the previous sample, so it holds at any sample rate
 if last_distance is None or abs(d-last_distance)>=.15:last_change=now;last_distance=d
 motion.append(d)
 # calibration: 10 s of normal breathing sets the peak threshold to 40% of this person's breath depth
 if calib_until:
  calib_vals.append(d)
  if now>=calib_until:
   thr=round(min(max(.4*(max(calib_vals)-min(calib_vals)),.1),1),2);calib_until=None
 peak=None
 span=max(motion)-min(motion) if len(motion)>=10 else 0
 quality="low motion" if span<.25 else "fair" if span<1 else "variable"
 # Algorithm 3: hysteresis peak detection (thr prominence, 0.25 cm until calibrated), independent of sample rate;
 # peak-to-peak is a candidate cycle.
 if ext is None:ext=(now,d)
 elif rising:
  if d>ext[1]:ext=(now,d)
  elif ext[1]-d>=thr:
   # 1.5–10 s cycles = 6–40 br/min; the old 2.5 s floor silently dropped anything above 24
   if last_peak is not None and 1.5<=ext[0]-last_peak<=10:rates.append(60/(ext[0]-last_peak))
   last_peak=ext[0];peak=[ext[0],round(ext[1],2)];rising=False;ext=(now,d)
 elif d<ext[1]:ext=(now,d)
 elif d-ext[1]>=thr:rising=True;ext=(now,d)
 # 10 s without movement is the usual apnea-event length; only meaningful once breathing was seen
 still=now-last_change;apnea=still>=10 and last_peak is not None
 if apnea:
  rates.clear()  # don't keep showing a pre-pause rate
  status=f"Possible apnea event — no chest movement for {still:.0f} s. Check on the person; this prototype cannot diagnose sleep apnea";quality="no movement"
 elif still>5:status="Little distance variation — check sensor positioning";quality="low motion"
 elif not rates:status="Collecting candidate cycles — rate not ready"
 else:status="Candidate rate estimate — not clinically validated"
 with data_lock:
  if apnea and not in_apnea:state["apnea_events"]+=1
  in_apnea=apnea
  state.update(apnea_s=round(still) if apnea else None,distance_cm=round(d,2),rate_bpm=round(sum(rates)/len(rates),1) if rates else None,quality=quality,status=status,samples=state["samples"]+1,
   rate_spread=round((max(rates)-min(rates))/2,1) if len(rates)>1 else None,threshold_cm=thr,calibrating=max(0,round(calib_until-now)) if calib_until else None)
  history.append({"n":state["samples"],"timestamp":now,"distance_cm":round(d,2),"rate_bpm":state["rate_bpm"],"peak":peak})
  rate=state["rate_bpm"]
 if recording and session_id:
  # batched: one commit per sample blocked the serial reader
  with db_lock:pending.append((session_id,now,d,rate,status));full=len(pending)>=25
  if full:flush()
def reader():
 with data_lock:state["status"]="Serial connected; waiting for sensor readings"
 while not stop_reader.is_set():
  with serial_lock:s=ser
  if s is None:break
  try:
   line=s.readline().decode("utf-8",errors="ignore").strip()
   d=parse_distance(line)
   if d is not None:process_distance(d)
   elif line and line not in ("INVALID","PHASEBREATHE_READY"):
    with data_lock:state["status"]="Serial text received; waiting for distance format"
   # INVALID = no echo within range; track the share of good lines over the last ~5 s
   if d is not None or line=="INVALID":
    ok=d is not None and 2<=d<=250;outcomes.append(ok)
    with data_lock:
     state["valid_pct"]=round(100*sum(outcomes)/len(outcomes))
     if not ok:state["invalid"]+=1
     if len(outcomes)>=25 and state["valid_pct"]<70:state.update(quality="poor",apnea_s=None,status=f"Only {state['valid_pct']}% of readings have an echo — aim the sensor squarely at the chest and check the ECHO wiring")
  except (serial.SerialException,OSError,ValueError) as e:
   with data_lock:state.update(connected=False,status=f"Serial read error: {e}")
   break
 with data_lock:state["connected"]=False
@app.get("/api/health")
def health():return {"ok":True}
@app.get("/api/ports")
def ports():return {"ports":[{"device":p.device,"description":p.description} for p in serial.tools.list_ports.comports()]}
@app.get("/api/state")
def get_state():
 with data_lock:return dict(state,history=list(history))
@app.post("/api/connect")
def connect(req:ConnectRequest):
 global ser
 if not req.port.strip():raise HTTPException(400,"Select a COM port first")
 close_serial();stop_reader.clear();reset()
 try:
  new=serial.Serial(req.port,req.baudrate,timeout=1);time.sleep(2)
  with serial_lock:ser=new
  with data_lock:state.update(connected=True,port=req.port,status=f"Connected to {req.port}; waiting for readings")
  threading.Thread(target=reader,daemon=True).start()
  return {"ok":True,"port":req.port}
 except (serial.SerialException,OSError) as e:
  with data_lock:state.update(connected=False,status=f"Could not open {req.port}")
  raise HTTPException(400,f"Could not open port '{req.port}': {e}")
@app.post("/api/disconnect")
def disconnect():
 close_serial()
 with data_lock:state.update(status="Disconnected",port=None)
 return {"ok":True}
@app.post("/api/calibrate")
def calibrate():
 global calib_until
 with data_lock:
  if not state["connected"]:raise HTTPException(400,"Connect the sensor before calibrating")
  state["calibrating"]=10
 calib_vals.clear();calib_until=time.time()+10
 return {"ok":True}
@app.post("/api/session/start")
def start_session():
 global recording,session_id,session_base
 with sqlite3.connect(DB) as c:
  cur=c.execute("INSERT INTO sessions(started) VALUES(?)",(time.strftime("%Y-%m-%d %H:%M:%S"),));session_id=cur.lastrowid
 recording=True
 with data_lock:state["recording"]=True;session_base=(state["apnea_events"],state["samples"],state["invalid"])
 return {"ok":True,"id":session_id}
@app.post("/api/session/stop")
def stop_session():
 global recording,session_id
 flush()
 with data_lock:state["recording"]=False
 if recording and session_id:
  # shortcut: deltas of per-connection counters, so a reconnect mid-session undercounts; store per reading if that matters
  with data_lock:ev,ok,bad=[max(0,a-b) for a,b in zip((state["apnea_events"],state["samples"],state["invalid"]),session_base)]
  with sqlite3.connect(DB) as c:c.execute("UPDATE sessions SET ended=?,apnea_events=?,valid_pct=? WHERE id=?",(time.strftime("%Y-%m-%d %H:%M:%S"),ev,round(100*ok/(ok+bad)) if ok+bad else None,session_id))
 recording=False;session_id=None;return {"ok":True}
@app.get("/api/sessions")
def sessions():
 with sqlite3.connect(DB) as c:
  c.row_factory=sqlite3.Row
  return {"sessions":[dict(r) for r in c.execute("SELECT s.*,ROUND(AVG(r.rate),1) avg_rate,ROUND(MIN(r.rate),1) min_rate,ROUND(MAX(r.rate),1) max_rate FROM sessions s LEFT JOIN readings r ON r.session_id=s.id GROUP BY s.id ORDER BY s.id DESC LIMIT 20")]}
@app.get("/api/export.csv")
def export_csv():
 out=io.StringIO();w=csv.writer(out);w.writerow(["session_id","timestamp_unix","distance_cm","estimated_rate_bpm","status"])
 with sqlite3.connect(DB) as c:w.writerows(c.execute("SELECT session_id,timestamp,distance,rate,status FROM readings ORDER BY id"))
 return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=phasebreathe.csv"})
@app.websocket("/ws")
async def ws(sock:WebSocket):
 # sends only samples the client hasn't seen; reset=True means drop the client buffer
 await sock.accept();epoch=None;last=-1
 try:
  while True:
   with data_lock:
    snapshot=dict(state);reset=snapshot["epoch"]!=epoch
    if reset:epoch=snapshot["epoch"];last=-1
    new=[h for h in history if h["n"]>last] if snapshot["samples"]!=last else []
   if new:last=new[-1]["n"]
   await sock.send_json({"state":snapshot,"new":new,"reset":reset});await asyncio.sleep(.1)
 except (WebSocketDisconnect,RuntimeError):pass
