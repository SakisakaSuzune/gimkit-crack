import json, time, sys
import auto_answer as A
import ds_model
import qbank

N=int(sys.argv[1]) if len(sys.argv)>1 else 100
print('start qbank entries',len(qbank.QB),'target',N,flush=True)

def body(): return A.read_question().get('body','')
def close_dialog():
    if not A.click_text('Continue'): A.click_rel(0.5,0.78)
    time.sleep(0.35)
def get_q():
    d=A.read_question(); q=d.get('q'); opts=d.get('spans',[])[1:]
    if q and len(opts)>=2 and len(q)>8 and 'Correct Answer' not in d.get('body',''):
        return q.strip(),opts
    return None
def ensure_q():
    for _ in range(30):
        b=body()
        if 'reconnect' in b.lower() or 'lost connection' in b.lower():
            time.sleep(1.0); continue
        if 'Questions Answered' in b: return None,'OVER'
        qq=get_q()
        if qq: return qq,'OK'
        if ('Correct Answer' in b) or ('Incorrect' in b) or ('Energy' in b) or ('Continue' in b):
            close_dialog(); continue
        if 'Answer Questions' in b:
            A.ev("[...document.querySelectorAll('button')].find(x=>x.innerText.includes('Answer Questions'))?.click()")
            time.sleep(0.7); continue
        time.sleep(0.25)
    return None,'STUCK'

stats={'total':0,'hit':0,'api':0,'correct':0,'wrong':0,'stored':0}
lat=[]; lat_api=[]; issues=[]
T0=time.time()
for i in range(N):
    qq,st=ensure_q()
    if st!='OK':
        issues.append('iter%d %s %s'%(i,st,body()[-120:])); print('STOP',st,flush=True); break
    q,opts=qq
    t0=time.time()
    entry,k=qbank.lookup(q,opts)
    if entry:
        ans=entry['a']; stats['hit']+=1; src='BANK'
    else:
        ans,u=ds_model.ask(q,opts); stats['api']+=1; src='API'
        if ans.startswith('ERR:'):
            issues.append('iter%d APIERR %s'%(i,ans)); print('APIERR',ans,flush=True); break
    dt=(time.time()-t0)*1000; lat.append(dt)
    if src=='API': lat_api.append(dt)
    chosen=next((o for o in opts if ans and (ans.lower()==o.lower() or o.lower() in ans.lower() or ans.lower() in o.lower())),None)
    if chosen: A.click_option(chosen)
    else: issues.append('iter%d NOMATCH %s'%(i,str(ans)[:40]))
    # poll for result
    rb=''; revealed=None; decided=False
    # Gimkit feedback can take 5-8s; wait up to 15s for a definitive result
    for _ in range(60):
        time.sleep(0.25); rb=body()
        if 'Correct Answer' in rb:
            sp=A.read_question().get('spans',[])
            if sp and sp[0].strip():
                cand=sp[0].strip()
                revealed=next((o for o in opts if o.lower()==cand.lower() or o.lower() in cand.lower() or cand.lower() in o.lower()), cand)
            decided=True; break
        if 'Incorrect!' in rb:
            # wait a bit more for the Correct Answer line to appear
            continue
        if 'Energy' in rb and 'Incorrect' not in rb:
            decided=True; break
    is_ok = decided and ('Correct Answer' not in rb) and ('Incorrect' not in rb) and ('Energy' in rb)
    stats['total']+=1
    if is_ok: stats['correct']+=1
    else: stats['wrong']+=1
    if not entry:
        truth = chosen if is_ok else revealed
        if truth:
            qbank.store(q,opts,truth); stats['stored']+=1
    if (i+1)%10==0 or not is_ok:
        print('Q%03d %5.0fms %-4s %-5s bank=%d chosen=%-28s | %s'%(i+1,dt,src,'OK' if is_ok else 'WRONG',len(qbank.QB),str(chosen)[:28],q[:28]),flush=True)
        if not is_ok and not entry:
            print('    revealed=',revealed,'opts=',opts,flush=True)
    close_dialog()

el=time.time()-T0
print('=== FINAL',json.dumps(stats),flush=True)
print('=== elapsed %.1fs avg_all %.0fms avg_api %s min %.0f max %.0f'%(el,sum(lat)/len(lat) if lat else 0,('%.0fms'%(sum(lat_api)/len(lat_api))) if lat_api else 'n/a',min(lat) if lat else 0,max(lat) if lat else 0),flush=True)
print('=== issues(%d)'%len(issues),issues[:20],flush=True)
