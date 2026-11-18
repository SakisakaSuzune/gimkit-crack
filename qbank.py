import json, hashlib

DB='qbank.json'
try:
    QB=json.load(open(DB))
except:
    QB={}

def make_key(q, opts):
    """Stable key from question text + sorted option set (order-independent)."""
    qn=' '.join(q.strip().lower().split())
    on=sorted(' '.join(o.strip().lower().split()) for o in opts)
    raw=qn+'||'+'|'.join(on)
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]

def lookup(q, opts):
    k=make_key(q,opts)
    return QB.get(k), k

def store(q, opts, answer):
    k=make_key(q,opts)
    QB[k]={'q':q.strip(), 'opts':sorted(o.strip() for o in opts), 'a':answer.strip()}
    save()
    return k

def save():
    json.dump(QB, open(DB,'w'), ensure_ascii=False, indent=1)

if __name__=='__main__':
    print('entries', len(QB))
