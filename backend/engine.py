import csv,io,datetime as dt,difflib,collections
from pathlib import Path
ROOT=Path(__file__).parent
DATA=ROOT/'private_data'
def read(path):
 p=DATA/path
 return list(csv.DictReader(p.open(encoding='utf-8-sig'))) if p.exists() else []
def date(x): return dt.datetime.fromisoformat(str(x).strip().replace('Z',''))
def num(x):
 try:return float(x or 0)
 except:return 0.
def active_policy(p,when):
 rules=p.get('rules',[])
 return rules

def process(rows,policy,extra_contracts=None):
 cfg=policy['settings']; items=read('master_data/item_master.csv'); suppliers=read('master_data/supplier_master.csv'); hist=read('master_data/po_history.csv'); regs=read('contracts/contract_register.csv')+(extra_contracts or []); lines=read('contracts/contract_lines.csv')
 im={x['item_code']:x for x in items}; sm={x['supplier_id']:x for x in suppliers}; cl=collections.defaultdict(list)
 for x in lines:cl[x['item_code']].append(x)
 def match(r):
  code=(r.get('item_code') or '').strip().upper()
  if code in im:return code
  desc=(r.get('description') or '').lower().strip()
  if not desc:return 'NEW'
  norm=lambda s: ''.join(c for c in s.lower() if c.isalnum())
  for x in items:
   if norm(x['description'])==norm(desc):return x['item_code']
  scores=sorted(((difflib.SequenceMatcher(None,norm(desc),norm(x['description'])).ratio(),x['item_code']) for x in items),reverse=True)
  return scores[0][1] if scores and scores[0][0]>=num(cfg.get('item_match_threshold',0.74)) else 'NEW'
 def preferred(code,when):
  h=[x for x in hist if x['item_code']==code and 0<=(when.date()-date(x['po_date']).date()).days<=num(cfg['preferred_history_days']) and sm.get(x['supplier_id'],{}).get('status')=='Active']
  cs=[x for x in regs if date(x['start_date']).date()<=when.date() and sm.get(x['supplier_id'],{}).get('status')=='Active' and any(l['contract_id']==x['contract_id'] for l in cl[code])]
  ids={x['supplier_id'] for x in h}|{x['supplier_id'] for x in cs}; result=[]
  for sid in ids:
   hh=sorted([x for x in h if x['supplier_id']==sid],key=lambda x:x['po_date'],reverse=True); cc=sorted([x for x in cs if x['supplier_id']==sid],key=lambda x:x['start_date'],reverse=True)
   s=sm[sid]; recent=(when.date()-date(hh[0]['po_date']).date()).days if hh else 548
   score= min(len(hh),15)*3+max(0,548-recent)/548*20+(10 if cc else 0)+num(s['on_time_pct'])*.2+num(s['quality_rating'])*4
   price=num(hh[0]['unit_price']) if hh else next((num(l['rate']) for l in cl[code] if l['contract_id']==cc[0]['contract_id']),0) if cc else 0
   result.append({'supplier_id':sid,'reference_price':price,'score':round(score,2),'reason':f"POs: {len(hh)}, latest: {hh[0]['po_date'] if hh else 'none'}, contract: {'yes' if cc else 'no'}, on-time: {s['on_time_pct']}%, quality: {s['quality_rating']}"})
  return sorted(result,key=lambda x:(-x['score'],x['supplier_id']))
 def suggestions(code,when,n):
  if code=='NEW':return []
  pref=preferred(code,when); ids=[x['supplier_id'] for x in pref]; category=im[code]['category']
  others=sorted((s for s in suppliers if s['status']=='Active' and category.lower() in [v.strip().lower() for v in s['categories'].split(';')] and s['supplier_id'] not in ids),key=lambda s:(-num(s['on_time_pct']),-num(s['quality_rating']),s['supplier_id']))
  return (ids+[s['supplier_id'] for s in others])[:n]
 ordered=sorted(rows,key=lambda x:(x.get('created_at',''),x.get('pr_no',''),num(x.get('pr_line')))); groups=[]
 for r in ordered:
  r=dict(r);r['_code']=match(r)
  if r.get('pr_no') == 'PR-26-00001': print("ENGINE DEBUG:", repr(r.get('created_at')), repr(r.get('need_by_date')), repr(r.get('quantity')), num(r.get('quantity')))
  if not r.get('created_at') or not r.get('need_by_date') or num(r.get('quantity'))<=0:
   groups.append({'rows':[r],'invalid':True});continue
  created=date(r['created_at']); need=date(r['need_by_date']); group=None
  if r['_code']!='NEW':
   for g in groups:
    if g.get('invalid'):continue
    first=g['rows'][0]
    if first['_code']==r['_code'] and first.get('plant')==r.get('plant') and 0<=(created.date()-date(first['created_at']).date()).days<=num(cfg['club_days']) and abs((need.date()-date(first['need_by_date']).date()).days)<=num(cfg['need_by_window_days']):group=g;break
  if group:group['rows'].append(r)
  else:groups.append({'rows':[r]})
 output=[]; openpos=[]; consumed={x['contract_id']:num(x['consumed_value']) for x in regs}; rules=active_policy(policy,None)
 for i,g in enumerate(groups,1):
  rr=g['rows'];first=rr[0]; code=first['_code']; gid=f'REQ-{i:05d}'; when=date(first.get('created_at') or '2026-11-01'); qty=sum(num(x.get('quantity')) for x in rr); emergency=any(str(x.get('urgency','')).lower()=='emergency' for x in rr); pref=preferred(code,when) if code!='NEW' else []
  valid=[]
  if code!='NEW':
   for l in cl[code]:
    for c in regs:
     if c['contract_id']==l['contract_id'] and sm.get(c['supplier_id'],{}).get('status')=='Active' and date(c['start_date']).date()<=when.date()<=date(c['end_date']).date():valid.append((num(l['rate']),c))
  valid.sort(key=lambda x:(x[0],x[1]['contract_id']))
  usable=next(((rate,c) for rate,c in valid if consumed.get(c['contract_id'],0)+rate*qty<=num(c['value_cap'])),None)
  recent=sorted([x for x in hist if x['item_code']==code and 0<=(when.date()-date(x['po_date']).date()).days<=num(cfg['valuation_history_days'])],key=lambda x:(x['po_date'],x['po_number']),reverse=True) if code!='NEW' else []
  rate=usable[0] if usable else valid[0][0] if valid else num(recent[0]['unit_price']) if recent else num(im[code]['standard_price']) if code!='NEW' else num(first.get('estimated_unit_price'))
  value=round(qty*rate,2); ctx={'new_item':code=='NEW','capex':code!='NEW' and im[code]['item_type'].lower()=='capex','contract_available':bool(usable),'emergency':emergency,'value':value,'has_active_recent_po':any(sm.get(x['supplier_id'],{}).get('status')=='Active' for x in recent)}
  decision='SOURCING_REQUEST';route='RFQ';clause='5.5'; count=3
  if g.get('invalid'):route='NOT_PROCESSED';clause='Missing required fields or invalid quantity';decision='NOT_PROCESSED'
  elif code=='NEW':route='NEW_ITEM_SOURCING';clause='1.2';count=0
  else:
   for rule in rules:
    conditions=rule.get('when',{});ok=True
    for key,expected in conditions.items():
     if key=='plant':ok=ok and first.get('plant')==expected
     elif key=='category':ok=ok and im[code]['category']==expected
     elif key=='item_type':ok=ok and im[code]['item_type']==expected
     elif key=='value_lt':ok=ok and value<num(expected)
     elif key=='value_lte':ok=ok and value<=num(expected)
     elif key=='value_gte':ok=ok and value>=num(expected)
     elif key in ctx:ok=ok and ctx[key]==expected
     else:ok=False
    if ok:
     route=rule['route'];decision=rule.get('decision','PO' if route.endswith('_PO') else 'SOURCING_REQUEST');clause=rule.get('clause',rule['id']);count=int(rule.get('suggest_count',3));break
  sid='';unit='';source=''
  if decision=='PO':
   if route=='CONTRACT_PO' and usable:
    unit,c=usable;sid=c['supplier_id'];source=c['contract_id'];consumed[source]=consumed.get(source,0)+qty*unit
   elif pref:sid=pref[0]['supplier_id'];unit=pref[0]['reference_price'];source='preferred supplier history / contract'
   else:decision='SOURCING_REQUEST';route='RFQ';clause+=' (no eligible preferred supplier)';count=3
  po=''
  if decision=='PO':
   for x in openpos:
    if x['supplier']==sid and x['plant']==first.get('plant') and x['route']==route and 0<=(when-x['date']).total_seconds()<=num(cfg['po_consolidation_hours'])*3600:po=x['id'];break
   if not po:
    po=f'PO-{len(openpos)+1:05d}';openpos.append({'id':po,'supplier':sid,'plant':first.get('plant'),'route':route,'date':when})
  sugg=';'.join(suggestions(code,when,count)) if decision=='SOURCING_REQUEST' else ''
  for r in rr:
   output.append({'pr_no':r.get('pr_no',''),'pr_line':r.get('pr_line',''),'resolved_item_code':code,'group_id':gid,'po_id':po,'decision':decision,'route':route,'supplier_id':sid,'unit_price':unit,'group_value_inr':value,'suggested_supplier_ids':sugg,'policy_version':policy['version'],'reason':f"Clause {clause}; valuation {rate:.2f}; source {source or (recent[0]['po_number'] if recent else 'item master / requester estimate')}"})
 return sorted(output,key=lambda x:(x['pr_no'],num(x['pr_line'])))

def preferred_export(policy,as_of):
 items=read('master_data/item_master.csv'); when=date(as_of);result=[]
 # reuse preferred supplier algorithm through a shared function in future revisions
 for item in items:
  code=item['item_code'];hist=read('master_data/po_history.csv');sm={s['supplier_id']:s for s in read('master_data/supplier_master.csv')};regs=read('contracts/contract_register.csv');lines=read('contracts/contract_lines.csv');eligible=[]
  for sid,s in sm.items():
   if s['status']!='Active':continue
   hh=sorted((h for h in hist if h['supplier_id']==sid and h['item_code']==code and 0<=(when.date()-date(h['po_date']).date()).days<=548),key=lambda h:h['po_date'],reverse=True)
   cc=sorted((c for c in regs if c['supplier_id']==sid and date(c['start_date']).date()<=when.date() and any(l['contract_id']==c['contract_id'] and l['item_code']==code for l in lines)),key=lambda c:c['start_date'],reverse=True)
   if not hh and not cc:continue
   recent=(when.date()-date(hh[0]['po_date']).date()).days if hh else 548
   score=min(len(hh),15)*3+max(0,548-recent)/548*20+(10 if cc else 0)+num(s['on_time_pct'])*.2+num(s['quality_rating'])*4
   price=num(hh[0]['unit_price']) if hh else next((num(l['rate']) for l in lines if l['contract_id']==cc[0]['contract_id'] and l['item_code']==code),0)
   eligible.append((score,sid,price))
  eligible.sort(key=lambda x:(-x[0],x[1]));top=';'.join(x[1] for x in eligible[:3])
  for rank,(_,sid,price) in enumerate(eligible,1):result.append({'item_code':code,'rank':rank,'supplier_id':sid,'reference_price':price,'top_3':top})
 return result
