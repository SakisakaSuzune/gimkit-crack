import socket, base64, os, json, struct, urllib.request, time, subprocess, sys
from urllib.parse import urlparse

def cdp_connect():
    ts=json.load(urllib.request.urlopen('http://127.0.0.1:9222/json/list'))
    t=[x for x in ts if 'gimkit.com/join' in x.get('url','') and x['type']=='page'][0]
    u=urlparse(t['webSocketDebuggerUrl']); s=socket.create_connection((u.hostname,u.port))
    k=base64.b64encode(os.urandom(16)).decode()
    s.sendall((f'GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {k}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
    b=b''
    while b'\r\n\r\n' not in b: b+=s.recv(4096)
    return s

S=cdp_connect(); MID=[1000]
def send(method,params={}):
    MID[0]+=1; mid=MID[0]
    d=json.dumps({'id':mid,'method':method,'params':params}).encode(); m=os.urandom(4); n=len(d)
    h=bytes([0x81,0x80|n]) if n<126 else (bytes([0x81,0xfe])+struct.pack('!H',n) if n<65536 else bytes([0x81,0xff])+struct.pack('!Q',n))
    S.sendall(h+m+bytes(x^m[i%4] for i,x in enumerate(d)))
    return mid
def recv():
    h=S.recv(2)
    if len(h)<2: return None
    op=h[0]&15; ln=h[1]&127
    if ln==126: ln=struct.unpack('!H',S.recv(2))[0]
    elif ln==127: ln=struct.unpack('!Q',S.recv(8))[0]
    p=b''
    while len(p)<ln:
        c=S.recv(ln-len(p))
        if not c: return None
        p+=c
    return op,p
def call(method,params={},timeout=10):
    mid=send(method,params); S.settimeout(timeout); end=time.time()+timeout
    while time.time()<end:
        try: f=recv()
        except socket.timeout: return {'error':'timeout'}
        if not f or f[0]!=1: continue
        try: m=json.loads(f[1])
        except: continue
        if m.get('id')==mid: return m.get('result',m.get('error'))
    return {'error':'timeout'}
def ev(expr):
    r=call('Runtime.evaluate',{'expression':expr,'returnByValue':True,'awaitPromise':True})
    inner=r.get('result',r) if isinstance(r,dict) else r
    if isinstance(inner,dict) and 'value' in inner: return inner['value']
    return None

READ_JS = ("(function(){"
  "var spans=[...document.querySelectorAll('span.notranslate')].map(e=>e.textContent.trim()).filter(Boolean);"
  "var q=spans.find(t=>t.length>20);"
  "var hasAns=document.body.innerText.indexOf('Answer Questions')>=0;"
  "return {spans:spans,q:q||null,inQuiz:!hasAns,body:document.body.innerText.slice(-600)};"
  "})()")

def read_question():
    return ev(READ_JS)

def click_option(text):
    ev("window.__target=" + json.dumps(text))
    js=("(function(){"
      "var sp=[...document.querySelectorAll('span.notranslate')].find(e=>e.textContent.trim()===window.__target);"
      "if(!sp) return false;"
      "var r=sp.getBoundingClientRect();"
      "window.__cx=r.left+r.width/2; window.__cy=r.top+r.height/2; return true;})()")
    ok=ev(js)
    if not ok: return False
    x=ev('window.__cx'); y=ev('window.__cy')
    for typ in ('mousePressed','mouseReleased'):
        call('Input.dispatchMouseEvent',{'type':typ,'x':x,'y':y,'button':'left','clickCount':1})
    return True



def click_text(txt):
    """Click an element whose visible text equals/contains txt, using its center."""
    ev("window.__t="+__import__('json').dumps(txt))
    js=("(function(){"
      "var els=[...document.querySelectorAll('*')].filter(e=>e.children.length===0 && (e.textContent||'').trim()===window.__t);"
      "if(!els.length) return false;"
      "var r=els[0].getBoundingClientRect();"
      "window.__tx=r.left+r.width/2; window.__ty=r.top+r.height/2; return true;})()")
    if not ev(js): return False
    x=ev('window.__tx'); y=ev('window.__ty')
    for typ in ('mousePressed','mouseReleased'):
        call('Input.dispatchMouseEvent',{'type':typ,'x':x,'y':y,'button':'left','clickCount':1})
    return True

def viewport():
    r=ev("(function(){var c=document.querySelector('canvas');var b=c.getBoundingClientRect();return {w:b.width,h:b.height};})()")
    if not r: return (944,1546)
    return (r.get('w',944), r.get('h',1546))

def click_rel(fx,fy):
    w,h=viewport()
    x=int(w*fx); y=int(h*fy)
    for typ in ('mousePressed','mouseReleased'):
        call('Input.dispatchMouseEvent',{'type':typ,'x':x,'y':y,'button':'left','clickCount':1})
    return (x,y)

if __name__=='__main__':
    print('QUESTION_STATE', json.dumps(read_question(),ensure_ascii=False))
