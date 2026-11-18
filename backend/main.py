
import csv,io,json,os,sqlite3,datetime as dt
from pathlib import Path
from fastapi import FastAPI,UploadFile,File,HTTPException,Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from engine import process,preferred_export,read

BASE=Path(__file__).parent; DB=BASE/'app.db'; POLICY=BASE/'policy.json'
app=FastAPI(title='Corvo Procurement API')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])

def conn():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c

def init():
 with conn() as c:
  c.execute('create table if not exists policies(id integer primary key, version text, effective_date text, body text, active integer, approved_at text)')
  c.execute('create table if not exists decisions(id integer primary key, batch_id text, pr_no text, pr_line text, payload text, status text default "PENDING")')
  c.execute('create table if not exists audit(id integer primary key, decision_id integer, actor text, action text, comment text, at text)')
  c.execute('create table if not exists contracts(id integer primary key, contract_id text, supplier_id text, start_date text,end_date text,value_cap real,consumed_value real)')
  if not c.execute('select count(*) from policies').fetchone()[0]:
   p=json.loads(POLICY.read_text());c.execute('insert into policies(version,effective_date,body,active,approved_at) values(?,?,?,?,?)',(p['version'],p['effective_date'],json.dumps(p),1,dt.datetime.now().isoformat()))

init()

def policy():
 with conn() as c:
  r=c.execute('select * from policies where active=1 order by id desc limit 1').fetchone()
  return json.loads(r['body'])

def contracts():
 with conn() as c:return [dict(x) for x in c.execute('select contract_id,supplier_id,start_date,end_date,value_cap,consumed_value from contracts')]

def csv_response(rows,name):
 b=io.StringIO();fields=list(rows[0]) if rows else ['no_results'];w=csv.DictWriter(b,fieldnames=fields);w.writeheader();w.writerows(rows);b.seek(0)
 return StreamingResponse(iter([b.getvalue()]),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{name}"'})

@app.get('/api/health')
def health():return {'status':'ok','policy':policy()['version']}

@app.get('/api/items')
def items():return read('master_data/item_master.csv')

@app.get('/api/policy')
def get_policy():return policy()

@app.get('/api/policies')
def policies():
 with conn() as c:return [dict(x) for x in c.execute('select id,version,effective_date,active,approved_at from policies order by id desc')]

class PolicyBody(BaseModel):
 version:str;effective_date:str;settings:dict;rules:list

@app.post('/api/policies/preview')
def preview(p:PolicyBody):
 old=policy();new=p.model_dump();changes=[]
 for k,v in new['settings'].items():
  if old['settings'].get(k)!=v:changes.append(f'{k}: {old["settings"].get(k)} → {v}')
 if old['rules']!=new['rules']:changes.append('Decision rules / rule order changed')
 return {'changes':changes,'new_version':new['version'],'effective_date':new['effective_date']}

@app.post('/api/policies')
def add_policy(p:PolicyBody):
 with conn() as c:
  cur=c.execute('insert into policies(version,effective_date,body,active) values(?,?,?,0)',(p.version,p.effective_date,p.model_dump_json()))
  return {'id':cur.lastrowid,'status':'PENDING_APPROVAL'}

@app.post('/api/policies/{id}/approve')
def approve_policy(id:int):
 with conn() as c:
  r=c.execute('select id from policies where id=?',(id,)).fetchone()
  if not r:raise HTTPException(404,'Policy not found')
  c.execute('update policies set active=0')
  c.execute('update policies set active=1,approved_at=? where id=?',(dt.datetime.now().isoformat(),id))
 return {'status':'approved','id':id}

@app.post('/api/process-batch')
async def process_batch(file:UploadFile=File(...)):
 try:
  reader=csv.DictReader(io.StringIO((await file.read()).decode('utf-8-sig')))
  required={'pr_no','pr_line','created_at','requester','department','plant','item_code','description','quantity','uom','estimated_unit_price','need_by_date','urgency'}
  missing=required-set(reader.fieldnames or [])
  if missing:raise HTTPException(400,'Wrong CSV file. Missing: '+', '.join(sorted(missing)))
  rows=list(reader)
 except HTTPException:raise
 except Exception as e:raise HTTPException(400,str(e))
 if not rows:raise HTTPException(400,'CSV is empty')
 result=process(rows,policy(),contracts());batch=dt.datetime.now().strftime('%Y%m%d%H%M%S%f')
 with conn() as c:
  for r in result:c.execute('insert into decisions(batch_id,pr_no,pr_line,payload) values(?,?,?,?)',(batch,r['pr_no'],r['pr_line'],json.dumps(r)))
 return {'batch_id':batch,'count':len(result),'decisions':result}


@app.get('/api/decisions')
def decisions():
 with conn() as c:
  latest=c.execute('select batch_id from decisions order by id desc limit 1').fetchone()
  if not latest:return []
  rows=c.execute('select * from decisions where batch_id=? order by id desc',(latest['batch_id'],))
  return [dict(id=r['id'],batch_id=r['batch_id'],status=r['status'],**json.loads(r['payload'])) for r in rows]

class Action(BaseModel):
 actor:str='Buyer';comment:str='';action:str='APPROVE'

@app.post('/api/decisions/{id}/action')
def action(id:int,a:Action):
 if a.action not in ('APPROVE','OVERRIDE'):raise HTTPException(400,'Invalid action')
 if a.action=='OVERRIDE' and not a.comment.strip():raise HTTPException(400,'Override requires a written comment')
 with conn() as c:
  if not c.execute('select id from decisions where id=?',(id,)).fetchone():raise HTTPException(404,'Decision not found')
  c.execute('update decisions set status=? where id=?',(a.action+'D' if a.action=='APPROVE' else 'OVERRIDDEN',id))
  c.execute('insert into audit(decision_id,actor,action,comment,at) values(?,?,?,?,?)',(id,a.actor,a.action,a.comment,dt.datetime.now().isoformat()))
 return {'status':'saved'}

@app.get('/api/audit')
def audit():
 with conn() as c:return [dict(r) for r in c.execute('select * from audit order by id desc')]

@app.get('/api/export/{batch_id}')
def export(batch_id:str):
 with conn() as c:rows=[json.loads(r['payload']) for r in c.execute('select payload from decisions where batch_id=? order by id',(batch_id,))]
 return csv_response(rows,f'decisions_{batch_id}.csv')

@app.get('/api/preferred-export')
def preferred(as_of:str='2026-11-19'):return csv_response(preferred_export(policy(),as_of),f'preferred_{as_of}.csv')

class Contract(BaseModel):
 contract_id:str;supplier_id:str;start_date:str;end_date:str;value_cap:float;consumed_value:float=0

@app.post('/api/contracts')
def add_contract(x:Contract):
 with conn() as c:c.execute('insert into contracts(contract_id,supplier_id,start_date,end_date,value_cap,consumed_value) values(?,?,?,?,?,?)',tuple(x.model_dump().values()))
 return {'status':'added','note':'Add matching contract lines to private_data/contracts/contract_lines.csv for item-level applicability'}

class Chat(BaseModel):
 message:str;draft:dict={}

@app.post('/api/chat')
def chat(c:Chat):
 import re,difflib
 d=dict(c.draft);msg=c.message.strip();lower=msg.lower();items=read('master_data/item_master.csv')
 for plant in ['PUN1','CHK1']:
  if plant.lower() in lower:d['plant']=plant
 if 'chakan' in lower:d['plant']='CHK1'
 if 'bhosari' in lower or 'pune' in lower:d['plant']='PUN1'
 if 'emergency' in lower or 'urgent' in lower:d['urgency']='Emergency'
 if 'normal' in lower:d['urgency']='Normal'
 match=re.search(r'\b(\d+(?:\.\d+)?)\s*(?:pcs|nos|kg|pairs|ltr|units|pieces)?\b',lower)
 if match and not d.get('quantity'):d['quantity']=float(match.group(1))
 for item in items:
  if item['item_code'].lower() in lower or item['description'].lower() in lower:d['item_code']=item['item_code'];d['description']=item['description'];break
 if not d.get('item_code'):
  candidates=difflib.get_close_matches(lower,[i['description'].lower() for i in items],n=1,cutoff=.45)
  if candidates:
   item=next(i for i in items if i['description'].lower()==candidates[0])
   return {'reply':f'Did you mean {item["description"]} ({item["item_code"]})? Please type the item code to confirm.','draft':d}
 if not d.get('item_code'):return {'reply':'Which item do you need? Please provide its item code or exact description. Unknown items can be sent to new-item sourcing.','draft':d}
 if not d.get('quantity'):return {'reply':'How many units do you need?','draft':d}
 if not d.get('plant'):return {'reply':'Which plant: PUN1 (Bhosari) or CHK1 (Chakan)?','draft':d}
 if not d.get('need_by_date'):
  iso=re.search(r'\d{4}-\d{2}-\d{2}',msg)
  if iso:d['need_by_date']=iso.group()
  else:return {'reply':'What is the need-by date? Please type YYYY-MM-DD.','draft':d}
 return {'reply':f'Confirm request: {d["quantity"]} × {d["item_code"]}, plant {d["plant"]}, needed {d["need_by_date"]}. Click Create PR to save.','draft':d,'ready':True}

@app.post('/api/chat/create')
def create_chat_pr(d:dict):
 now=dt.datetime.now()
 r={'pr_no':'CHAT-'+now.strftime('%Y%m%d%H%M%S%f'),'pr_line':'1','created_at':now.strftime('%Y-%m-%d %H:%M'),'requester':d.get('requester','Employee'),'department':'General','plant':d['plant'],'item_code':d['item_code'],'description':d.get('description',''),'quantity':d['quantity'],'uom':'NOS','estimated_unit_price':'','need_by_date':d['need_by_date'],'urgency':d.get('urgency','Normal')}
 result=process([r],policy(),contracts());batch=r['pr_no']
 with conn() as c:c.execute('insert into decisions(batch_id,pr_no,pr_line,payload) values(?,?,?,?)',(batch,r['pr_no'],'1',json.dumps(result[0])))
 return {'batch_id':batch,'decisions':result}
