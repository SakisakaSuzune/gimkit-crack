import json, urllib.request, time, os

def _load_env(path):
    cfg = {}
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                cfg[k.strip()] = v.strip()
    except OSError:
        pass
    return cfg

# Look for .env.local next to this script first, then in the current directory
_here = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env.local')
_cfg = _load_env(_here) or _load_env('.env.local')

API   = os.environ.get('BASE_URL') or _cfg.get('BASE_URL', 'https://api.deepseek.com/chat/completions')
KEY   = os.environ.get('API_KEY')  or _cfg.get('API_KEY', '')
MODEL = os.environ.get('MODEL')    or _cfg.get('MODEL', 'deepseek-flash')
SYS   = 'Answer multiple-choice trivia. Reply with ONLY the exact correct option text, copied verbatim. No explanation, no letter prefix.'

def ask(q, opts):
    if not KEY:
        return 'ERR:API_KEY missing (set it in .env.local)', {}
    user = q + '\nOptions: ' + ' | '.join(opts)
    body = json.dumps({'model': MODEL, 'messages': [
        {'role': 'system', 'content': SYS},
        {'role': 'user', 'content': user}
    ], 'max_tokens': 60, 'stream': False}).encode()
    req = urllib.request.Request(API, data=body, headers={
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + KEY
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read())
            msg = d['choices'][0]['message']
            content = (msg.get('content') or '').strip().strip('"').strip()
            if not content:
                rc = (msg.get('reasoning_content') or '')
                for o in sorted(opts, key=len, reverse=True):
                    if o and o.lower() in rc.lower():
                        content = o
                        break
            if not content and attempt < 2:
                time.sleep(0.5)
                continue
            return content, d.get('usage', {})
        except Exception as e:
            if attempt == 2:
                return 'ERR:' + str(e)[:60], {}
            time.sleep(1)
    return '', {}
