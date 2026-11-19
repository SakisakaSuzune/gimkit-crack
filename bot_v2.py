import json, os, time, sys
import page
import qbank
import resolve
import verdict

PAGE = page.Page.connect()
BANK = qbank.QuestionBank()
RESOLVER = resolve.default_resolver(BANK)
N=int(sys.argv[1]) if len(sys.argv)>1 else 100
print('start qbank entries',len(BANK),'target',N,flush=True)

def body(): return PAGE.read_state().get('body','')
def spans(): return PAGE.read_state().get('spans',[])
JUDGE = verdict.Verdict(body, spans, BANK.store)
DEBUG_LOG = os.environ.get('GIMKIT_DEBUG_LOG')

def debug_record(record):
    if DEBUG_LOG:
        with open(DEBUG_LOG, 'a', encoding='utf-8') as out:
            out.write('[DEBUG-a4f2] ' + json.dumps(record, ensure_ascii=False) + '\n')

def close_dialog():
    closed = PAGE.click_text('Continue')
    if DEBUG_LOG:
        debug_record({'event': 'close_dialog', 'closed': closed, 'body': body()[-200:]})
    if not closed:
        w, h = PAGE.viewport()
        PAGE.click_xy(int(w * 0.5), int(h * 0.78))
    time.sleep(0.25)

DIALOG_MARKERS = ('Correct Answer', 'Incorrect', 'Energy', 'Continue')

def clean_page(body_text):
    return not any(marker in body_text for marker in DIALOG_MARKERS)

def get_q():
    d = PAGE.read_state()
    q = d.get('q')
    opts = d.get('spans', [])[1:]
    if not (q and len(opts) >= 2 and len(q) > 8):
        return None
    if not clean_page(d.get('body', '')):
        return None
    return q.strip(), opts

def ensure_q():
    for _ in range(40):
        b = body()
        if 'reconnect' in b.lower() or 'lost connection' in b.lower():
            time.sleep(1.0); continue
        if 'Questions Answered' in b: return None, 'OVER'
        qq = get_q()
        if qq:
            return qq, 'OK'
        if any(marker in b for marker in DIALOG_MARKERS):
            close_dialog(); continue
        if 'Answer Questions' in b:
            PAGE.click_text_containing('Answer Questions')
            time.sleep(0.7); continue
        time.sleep(0.25)
    return None, 'STUCK'

def click_current(q, opts, chosen):
    for _ in range(4):
        d = PAGE.read_state()
        if d.get('q') == q and d.get('spans', [])[1:] == opts:
            if PAGE.click_option(chosen):
                return True
        time.sleep(0.2)
    return False

stats={'total':0,'hit':0,'api':0,'correct':0,'wrong':0,'stored':0}
lat=[]; lat_api=[]; issues=[]
T0=time.time()
for i in range(N):
    qq,st=ensure_q()
    if st!='OK':
        issues.append('iter%d %s %s'%(i,st,body()[-120:])); print('STOP',st,flush=True); break
    q,opts=qq
    t0=time.time()
    found=RESOLVER.resolve(q,opts)
    if not found.ok:
        issues.append('iter%d APIERR %s'%(i,found.error)); print('APIERR',found.error,flush=True); break
    ans=found.text; src=found.source; chosen=found.chosen
    if src=='BANK': stats['hit']+=1
    else: stats['api']+=1
    dt=(time.time()-t0)*1000; lat.append(dt)
    if src=='API': lat_api.append(dt)
    if chosen and not click_current(q,opts,chosen):
        issues.append('iter%d CLICK_MISMATCH %s'%(i,q[:60])); print('CLICK_MISMATCH',flush=True); continue
    elif not chosen:
        issues.append('iter%d NOMATCH %s'%(i,str(ans)[:40]))
    if DEBUG_LOG:
        def on_poll(text, _q=q, _chosen=chosen):
            debug_record({'q': _q, 'chosen': _chosen, 'poll': text[-600:]})
    else:
        on_poll = None
    outcome=JUDGE.observe(q,opts,chosen,should_store=resolve.should_learn(src),on_poll=on_poll)
    if DEBUG_LOG:
        debug_record({'q': q, 'chosen': chosen, 'ok': outcome.ok, 'revealed': outcome.revealed, 'error': outcome.error})
    revealed=outcome.revealed
    is_ok=outcome.ok
    if outcome.error: issues.append('iter%d VERDICT %s'%(i,outcome.error))
    if outcome.stored: stats['stored']+=1
    stats['total']+=1
    if is_ok: stats['correct']+=1
    else: stats['wrong']+=1
    if (i+1)%10==0 or not is_ok:
        print('Q%03d %5.0fms %-4s %-5s bank=%d chosen=%-28s | %s'%(i+1,dt,src,'OK' if is_ok else 'WRONG',len(BANK),str(chosen)[:28],q[:28]),flush=True)
        if not is_ok and src=='API':
            print('    revealed=',revealed,'opts=',opts,flush=True)
    close_dialog()
    time.sleep(0.15)

el=time.time()-T0
print('=== FINAL',json.dumps(stats),flush=True)
print('=== elapsed %.1fs avg_all %.0fms avg_api %s min %.0f max %.0f'%(el,sum(lat)/len(lat) if lat else 0,('%.0fms'%(sum(lat_api)/len(lat_api))) if lat_api else 'n/a',min(lat) if lat else 0,max(lat) if lat else 0),flush=True)
print('=== issues(%d)'%len(issues),issues[:20],flush=True)
PAGE.close()
