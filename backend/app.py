#!/usr/bin/env python3
import base64, hashlib, hmac, json, os, secrets, sqlite3, sys, time
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1]
def load_env():
    env = ROOT / '.env'
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('\"').strip("'"))
load_env()
DB_PATH = Path(os.getenv('DATABASE_PATH', ROOT / 'backend' / 'dev.db'))
SECRET = os.getenv('JWT_SECRET', 'local-dev-secret').encode()
PORT = int(os.getenv('PORT', '4000'))
ACTIVE_ASSIGNMENTS = ('SIGNED_UP', 'ASSIGNED')
LEAVE_HOURS = 24

def now(): return datetime.now(timezone.utc).isoformat()
def iso_days(days): return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()
def connect():
    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row; con.execute('PRAGMA foreign_keys=ON'); return con
def rowdict(r): return dict(r) if r else None
def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 120000).hex()
    return f'{salt}${digest}'
def verify_password(password, stored):
    salt, digest = stored.split('$', 1)
    return hmac.compare_digest(hash_password(password, salt).split('$',1)[1], digest)
def b64(data): return base64.urlsafe_b64encode(json.dumps(data,separators=(',',':')).encode()).rstrip(b'=').decode()
def sign_token(user):
    payload = {'sub': user['id'], 'role': user['role'], 'exp': int(time.time()) + 8*3600}
    body = b64(payload); sig = base64.urlsafe_b64encode(hmac.new(SECRET, body.encode(), hashlib.sha256).digest()).rstrip(b'=').decode()
    return body + '.' + sig
def read_token(token):
    body, sig = token.split('.',1)
    expected = base64.urlsafe_b64encode(hmac.new(SECRET, body.encode(), hashlib.sha256).digest()).rstrip(b'=').decode()
    if not hmac.compare_digest(sig, expected): raise ValueError('bad signature')
    payload = json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body)%4)))
    if payload['exp'] < time.time(): raise ValueError('expired')
    return payload

def migrate():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con=connect(); cur=con.cursor()
    cur.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('ADMIN','WORKER')),is_active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS worker_profiles(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER UNIQUE NOT NULL,first_name TEXT NOT NULL,last_name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,phone TEXT NOT NULL,is_active INTEGER NOT NULL DEFAULT 1,internal_notes TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS clients(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,contact_person TEXT NOT NULL,email TEXT NOT NULL,phone TEXT NOT NULL,address TEXT NOT NULL,internal_notes TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,client_id INTEGER NOT NULL,description TEXT NOT NULL,start_date TEXT NOT NULL,end_date TEXT NOT NULL,start_time TEXT NOT NULL,end_time TEXT NOT NULL,location TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('DRAFT','PUBLISHED','COMPLETED','CANCELLED')),min_workers INTEGER NOT NULL,max_workers INTEGER,internal_notes TEXT,worker_instructions TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(client_id) REFERENCES clients(id));
    CREATE TABLE IF NOT EXISTS event_worker_assignments(id INTEGER PRIMARY KEY AUTOINCREMENT,event_id INTEGER NOT NULL,worker_id INTEGER NOT NULL,status TEXT NOT NULL CHECK(status IN ('SIGNED_UP','ASSIGNED','CANCELLED','REMOVED')),signed_up_at TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,FOREIGN KEY(worker_id) REFERENCES worker_profiles(id) ON DELETE CASCADE,UNIQUE(event_id,worker_id));
    CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_date); CREATE INDEX IF NOT EXISTS idx_assign_event ON event_worker_assignments(event_id); CREATE INDEX IF NOT EXISTS idx_assign_worker ON event_worker_assignments(worker_id);
    '''); con.commit(); con.close()

def seed():
    migrate(); con=connect(); cur=con.cursor(); ts=now()
    for table in ['event_worker_assignments','events','worker_profiles','clients','users']: cur.execute(f'DELETE FROM {table}')
    def user(name,email,password,role):
        cur.execute('INSERT INTO users(name,email,password_hash,role,is_active,created_at,updated_at) VALUES(?,?,?,?,1,?,?)',(name,email,hash_password(password),role,ts,ts)); return cur.lastrowid
    user('Admin Eventos','admin@kebab-events.local','Admin123!','ADMIN')
    workers=[]
    for first,last,email,phone in [('Ana','García','ana@kebab-events.local','+34 600 111 222'),('Luis','Martín','luis@kebab-events.local','+34 600 333 444'),('Sara','López','sara@kebab-events.local','+34 600 555 666')]:
        uid=user(f'{first} {last}',email,'Worker123!','WORKER'); cur.execute('INSERT INTO worker_profiles(user_id,first_name,last_name,email,phone,is_active,internal_notes,created_at,updated_at) VALUES(?,?,?,?,?,1,?,?,?)',(uid,first,last,email,phone,'Trabajador de prueba seed.',ts,ts)); workers.append(cur.lastrowid)
    clients=[]
    for data in [('ACME Corp','Marta Ruiz','eventos@acme.test','+34 910 111 222','Madrid Centro','Cliente recurrente.'),('Bodas del Sur','Pablo Soto','hola@bodasdelsur.test','+34 950 333 444','Sevilla','Atención a horarios.'),('Festival Norte','Laura Pérez','staff@festivalnorte.test','+34 944 555 666','Bilbao','Alto volumen.')]:
        cur.execute('INSERT INTO clients(name,contact_person,email,phone,address,internal_notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(*data,ts,ts)); clients.append(cur.lastrowid)
    events=[('Kickoff anual ACME',clients[0],'Evento corporativo de presentación anual.',15,15,'09:00','18:00','Palacio de Congresos, Madrid','PUBLISHED',3,5,'Revisar acreditaciones.','Uniforme negro, llegar 45 minutos antes.'),('Catering boda Soto',clients[1],'Servicio de apoyo en banquete.',25,25,'16:00','23:30','Hacienda El Olivar, Sevilla','PUBLISHED',2,2,'Contacto en finca: Carmen.','Zapato cómodo y camisa blanca.'),('Festival de invierno',clients[2],'Operativa de accesos y barras.',40,42,'12:00','02:00','BEC Bilbao','DRAFT',8,12,'Pendiente proveedor.','Briefing pendiente.'),('Cena corporativa cancelada',clients[0],'Evento cancelado por el cliente.',7,7,'20:00','23:00','Hotel Centro','CANCELLED',2,4,'No reactivar.','No aplica.'),('Feria gastronómica completada',clients[2],'Evento finalizado con éxito.',-10,-9,'10:00','20:00','Bilbao Arena','COMPLETED',2,3,'Buen resultado.','Histórico.')]
    ids=[]
    for e in events:
        cur.execute('INSERT INTO events(title,client_id,description,start_date,end_date,start_time,end_time,location,status,min_workers,max_workers,internal_notes,worker_instructions,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(e[0],e[1],e[2],iso_days(e[3]),iso_days(e[4]),e[5],e[6],e[7],e[8],e[9],e[10],e[11],e[12],ts,ts)); ids.append(cur.lastrowid)
    assigns=[(ids[0],workers[0],'ASSIGNED'),(ids[0],workers[1],'SIGNED_UP'),(ids[1],workers[0],'ASSIGNED'),(ids[1],workers[2],'ASSIGNED'),(ids[4],workers[0],'ASSIGNED'),(ids[4],workers[1],'ASSIGNED')]
    for a in assigns: cur.execute('INSERT INTO event_worker_assignments(event_id,worker_id,status,signed_up_at,created_at,updated_at) VALUES(?,?,?,?,?,?)',(*a,ts,ts,ts))
    con.commit(); con.close(); print('Seed completado: admin@kebab-events.local/Admin123!, ana@kebab-events.local/Worker123!')

def coverage(event, assignments):
    count=sum(1 for a in assignments if a['status'] in ACTIVE_ASSIGNMENTS); missing=max(event['min_workers']-count,0); full=bool(event['max_workers'] and count>=event['max_workers']); label=f'Faltan {missing} trabajadores'
    if event['status']=='CANCELLED': label='Evento cancelado'
    elif event['status']=='COMPLETED' or full: label='Evento completo'
    elif missing==0: label='Mínimo cubierto'
    return {'assignedCount':count,'minWorkers':event['min_workers'],'maxWorkers':event['max_workers'],'missingWorkers':missing,'isCovered':missing==0,'isFull':full,'label':label}

def enrich_event(con, event):
    event=dict(event); event['client']=rowdict(con.execute('SELECT * FROM clients WHERE id=?',(event['client_id'],)).fetchone())
    rows=con.execute('SELECT a.*,w.first_name,w.last_name,w.email,w.phone,w.is_active FROM event_worker_assignments a JOIN worker_profiles w ON w.id=a.worker_id WHERE a.event_id=? ORDER BY a.created_at DESC',(event['id'],)).fetchall()
    event['assignments']=[{**dict(r),'worker':{'id':r['worker_id'],'firstName':r['first_name'],'lastName':r['last_name'],'email':r['email'],'phone':r['phone'],'isActive':bool(r['is_active'])}} for r in rows]
    event['coverage']=coverage(event,event['assignments']); return camel(event)
def camel(obj):
    if isinstance(obj,list): return [camel(x) for x in obj]
    if not isinstance(obj,dict): return obj
    mp={'created_at':'createdAt','updated_at':'updatedAt','contact_person':'contactPerson','internal_notes':'internalNotes','client_id':'clientId','start_date':'startDate','end_date':'endDate','start_time':'startTime','end_time':'endTime','min_workers':'minWorkers','max_workers':'maxWorkers','worker_instructions':'workerInstructions','worker_id':'workerId','event_id':'eventId','signed_up_at':'signedUpAt','is_active':'isActive','first_name':'firstName','last_name':'lastName','user_id':'userId'}
    return {mp.get(k,k):camel(v) for k,v in obj.items()}
def decamel(data):
    mp={'createdAt':'created_at','updatedAt':'updated_at','contactPerson':'contact_person','internalNotes':'internal_notes','clientId':'client_id','startDate':'start_date','endDate':'end_date','startTime':'start_time','endTime':'end_time','minWorkers':'min_workers','maxWorkers':'max_workers','workerInstructions':'worker_instructions','workerId':'worker_id','eventId':'event_id','signedUpAt':'signed_up_at','isActive':'is_active','firstName':'first_name','lastName':'last_name'}
    return {mp.get(k,k):v for k,v in data.items()}

def validate_event(d):
    if d.get('min_workers',0) <= 0: raise ApiError(422,'El mínimo de trabajadores debe ser mayor que 0')
    if d.get('max_workers') and d['max_workers'] < d['min_workers']: raise ApiError(422,'El máximo no puede ser menor que el mínimo')
    if d['end_date'] < d['start_date']: raise ApiError(422,'La fecha de fin no puede ser anterior a la fecha de inicio')
class ApiError(Exception):
    def __init__(self,status,msg): self.status=status; self.msg=msg

class Handler(BaseHTTPRequestHandler):
    def send_json(self,status,data=None):
        self.send_response(status); self.send_header('Content-Type','application/json'); self.end_headers();
        if data is not None: self.wfile.write(json.dumps(data).encode())
    def body(self):
        n=int(self.headers.get('content-length','0')); return json.loads(self.rfile.read(n) or b'{}')
    def user(self, con):
        h=self.headers.get('Authorization','')
        if not h.startswith('Bearer '): raise ApiError(401,'No autenticado')
        payload=read_token(h[7:]); u=con.execute('SELECT * FROM users WHERE id=? AND is_active=1',(payload['sub'],)).fetchone()
        if not u: raise ApiError(401,'Usuario no válido o inactivo')
        u=dict(u); u['workerProfile']=rowdict(con.execute('SELECT * FROM worker_profiles WHERE user_id=?',(u['id'],)).fetchone()); return u
    def require(self,u,*roles):
        if u['role'] not in roles: raise ApiError(403,'No tienes permisos para realizar esta acción')
    def handle_api(self):
        con=connect(); parsed=urlparse(self.path); path=parsed.path; qs={k:v[0] for k,v in parse_qs(parsed.query).items()}
        try:
            if path=='/api/auth/login' and self.command=='POST':
                d=self.body(); u=con.execute('SELECT * FROM users WHERE email=?',(d.get('email'),)).fetchone()
                if not u or not verify_password(d.get('password',''),u['password_hash']): raise ApiError(401,'Credenciales incorrectas')
                u=dict(u); u['workerProfile']=rowdict(con.execute('SELECT * FROM worker_profiles WHERE user_id=?',(u['id'],)).fetchone()); return self.send_json(200,{'token':sign_token(u),'user':camel({k:v for k,v in u.items() if k!='password_hash'})})
            u=self.user(con)
            if path=='/api/auth/me': return self.send_json(200,{'user':camel({k:v for k,v in u.items() if k!='password_hash'})})
            parts=path.strip('/').split('/'); res=parts[1] if len(parts)>1 else ''
            if path=='/api/events/dashboard/summary':
                self.require(u,'ADMIN'); events=[enrich_event(con,r) for r in con.execute('SELECT * FROM events ORDER BY start_date').fetchall()]; today=datetime.now(timezone.utc).date().isoformat()
                return self.send_json(200,{'totalEvents':len(events),'upcomingEvents':sum(e['startDate']>=today for e in events),'understaffedEvents':sum(e['coverage']['missingWorkers']>0 and e['status'] not in ('CANCELLED','COMPLETED') for e in events),'completedEvents':sum(e['status']=='COMPLETED' for e in events),'activeWorkers':con.execute('SELECT COUNT(*) c FROM worker_profiles WHERE is_active=1').fetchone()['c'],'clients':con.execute('SELECT COUNT(*) c FROM clients').fetchone()['c'],'latestEvents':events[:5],'importantUpcoming':[e for e in events if e['startDate']>=today][:5]})
            if path=='/api/events/mine/list':
                self.require(u,'WORKER'); wid=u['workerProfile']['id']; rows=con.execute("SELECT * FROM event_worker_assignments WHERE worker_id=? AND status IN ('SIGNED_UP','ASSIGNED') ORDER BY created_at DESC",(wid,)).fetchall(); out=[]
                for a in rows: out.append({**camel(dict(a)),'event':enrich_event(con,con.execute('SELECT * FROM events WHERE id=?',(a['event_id'],)).fetchone())})
                return self.send_json(200,out)
            if res=='clients': return self.clients(con,u,parts,qs)
            if res=='workers': return self.workers(con,u,parts,qs)
            if res=='users': return self.users(con,u,parts)
            if res=='events': return self.events(con,u,parts,qs)
            raise ApiError(404,'Ruta no encontrada')
        except ApiError as e: return self.send_json(e.status,{'message':e.msg})
        except Exception as e: print(e); return self.send_json(500,{'message':'Error interno','details':str(e)})
        finally: con.close()
    def clients(self,con,u,parts,qs):
        self.require(u,'ADMIN'); ts=now()
        if len(parts)==2 and self.command=='GET':
            q=f"%{qs.get('q','')}%"; rows=con.execute('SELECT * FROM clients WHERE name LIKE ? OR email LIKE ? OR phone LIKE ? ORDER BY created_at DESC',(q,q,q)).fetchall(); return self.send_json(200,camel([dict(r) for r in rows]))
        if len(parts)==2 and self.command=='POST':
            d=decamel(self.body()); con.execute('INSERT INTO clients(name,contact_person,email,phone,address,internal_notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(d['name'],d['contact_person'],d['email'],d['phone'],d['address'],d.get('internal_notes'),ts,ts)); con.commit(); return self.send_json(201,{'message':'Cliente creado correctamente'})
        cid=int(parts[2])
        if self.command=='PUT':
            d=decamel(self.body()); con.execute('UPDATE clients SET name=?,contact_person=?,email=?,phone=?,address=?,internal_notes=?,updated_at=? WHERE id=?',(d['name'],d['contact_person'],d['email'],d['phone'],d['address'],d.get('internal_notes'),ts,cid)); con.commit(); return self.send_json(200,{'message':'Cliente actualizado correctamente'})
        if self.command=='DELETE': con.execute('DELETE FROM clients WHERE id=?',(cid,)); con.commit(); return self.send_json(204)
    def workers(self,con,u,parts,qs):
        self.require(u,'ADMIN'); ts=now()
        if len(parts)==2 and self.command=='GET':
            q=f"%{qs.get('q','')}%"; rows=con.execute('SELECT * FROM worker_profiles WHERE (first_name LIKE ? OR last_name LIKE ? OR email LIKE ?) ORDER BY created_at DESC',(q,q,q)).fetchall(); return self.send_json(200,camel([dict(r) for r in rows]))
        d=decamel(self.body()) if self.command in ('POST','PUT') else {}; 
        if len(parts)==2 and self.command=='POST':
            cur=con.execute('INSERT INTO users(name,email,password_hash,role,is_active,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(f"{d['first_name']} {d['last_name']}",d['email'],hash_password(d.get('password','Password123')),'WORKER',int(d.get('is_active',1)),ts,ts)); uid=cur.lastrowid
            con.execute('INSERT INTO worker_profiles(user_id,first_name,last_name,email,phone,is_active,internal_notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(uid,d['first_name'],d['last_name'],d['email'],d['phone'],int(d.get('is_active',1)),d.get('internal_notes'),ts,ts)); con.commit(); return self.send_json(201,{'message':'Trabajador creado correctamente'})
        wid=int(parts[2])
        if self.command=='PUT':
            con.execute('UPDATE worker_profiles SET first_name=?,last_name=?,email=?,phone=?,is_active=?,internal_notes=?,updated_at=? WHERE id=?',(d['first_name'],d['last_name'],d['email'],d['phone'],int(d.get('is_active',1)),d.get('internal_notes'),ts,wid)); wp=con.execute('SELECT * FROM worker_profiles WHERE id=?',(wid,)).fetchone(); con.execute('UPDATE users SET name=?,email=?,is_active=?,updated_at=? WHERE id=?',(f"{d['first_name']} {d['last_name']}",d['email'],int(d.get('is_active',1)),ts,wp['user_id'])); con.commit(); return self.send_json(200,{'message':'Trabajador actualizado correctamente'})
        if self.command=='DELETE': con.execute('DELETE FROM worker_profiles WHERE id=?',(wid,)); con.commit(); return self.send_json(204)
    def users(self,con,u,parts):
        self.require(u,'ADMIN'); ts=now()
        if len(parts)==2 and self.command=='GET': return self.send_json(200,camel([{k:v for k,v in dict(r).items() if k!='password_hash'} for r in con.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()]))
        d=decamel(self.body()) if self.command in ('POST','PUT') else {}
        if len(parts)==2 and self.command=='POST': con.execute('INSERT INTO users(name,email,password_hash,role,is_active,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(d['name'],d['email'],hash_password(d.get('password','Password123')),d['role'],int(d.get('is_active',1)),ts,ts)); con.commit(); return self.send_json(201,{'message':'Usuario creado correctamente'})
        uid=int(parts[2])
        if self.command=='PUT': con.execute('UPDATE users SET name=?,email=?,role=?,is_active=?,updated_at=? WHERE id=?',(d['name'],d['email'],d['role'],int(d.get('is_active',1)),ts,uid)); con.commit(); return self.send_json(200,{'message':'Usuario actualizado correctamente'})
        if self.command=='DELETE': con.execute('DELETE FROM users WHERE id=?',(uid,)); con.commit(); return self.send_json(204)
    def events(self,con,u,parts,qs):
        ts=now()
        if len(parts)==2 and self.command=='GET':
            clauses=[]; vals=[]
            if u['role']=='WORKER': clauses.append("status='PUBLISHED'")
            for key,col in [('status','status'),('clientId','client_id')]:
                if qs.get(key): clauses.append(f'{col}=?'); vals.append(qs[key])
            if qs.get('q'): clauses.append('(title LIKE ? OR location LIKE ?)'); vals += [f"%{qs['q']}%",f"%{qs['q']}%"]
            sql='SELECT * FROM events '+(('WHERE '+ ' AND '.join(clauses)) if clauses else '')+' ORDER BY start_date ASC'; events=[enrich_event(con,r) for r in con.execute(sql,vals).fetchall()]
            if qs.get('staffing')=='missing': events=[e for e in events if e['coverage']['missingWorkers']>0 and e['status'] not in ('CANCELLED','COMPLETED')]
            return self.send_json(200,events)
        if len(parts)==2 and self.command=='POST':
            self.require(u,'ADMIN'); d=decamel(self.body()); validate_event(d); con.execute('INSERT INTO events(title,client_id,description,start_date,end_date,start_time,end_time,location,status,min_workers,max_workers,internal_notes,worker_instructions,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(d['title'],d['client_id'],d['description'],d['start_date'][:10],d['end_date'][:10],d['start_time'],d['end_time'],d['location'],d['status'],d['min_workers'],d.get('max_workers'),d.get('internal_notes'),d.get('worker_instructions'),ts,ts)); con.commit(); return self.send_json(201,{'message':'Evento creado correctamente'})
        eid=int(parts[2])
        if len(parts)==3 and self.command=='GET':
            ev=enrich_event(con,con.execute('SELECT * FROM events WHERE id=?',(eid,)).fetchone());
            if u['role']=='WORKER' and ev['status']!='PUBLISHED': raise ApiError(403,'No tienes permisos para ver este evento')
            return self.send_json(200,ev)
        if len(parts)==3 and self.command=='PUT':
            self.require(u,'ADMIN'); d=decamel(self.body()); validate_event(d); con.execute('UPDATE events SET title=?,client_id=?,description=?,start_date=?,end_date=?,start_time=?,end_time=?,location=?,status=?,min_workers=?,max_workers=?,internal_notes=?,worker_instructions=?,updated_at=? WHERE id=?',(d['title'],d['client_id'],d['description'],d['start_date'][:10],d['end_date'][:10],d['start_time'],d['end_time'],d['location'],d['status'],d['min_workers'],d.get('max_workers'),d.get('internal_notes'),d.get('worker_instructions'),ts,eid)); con.commit(); return self.send_json(200,{'message':'Evento actualizado correctamente'})
        if len(parts)==3 and self.command=='DELETE': self.require(u,'ADMIN'); con.execute('DELETE FROM events WHERE id=?',(eid,)); con.commit(); return self.send_json(204)
        ev=enrich_event(con,con.execute('SELECT * FROM events WHERE id=?',(eid,)).fetchone())
        if len(parts)>=4 and parts[3]=='join':
            self.require(u,'WORKER'); wid=u['workerProfile']['id']
            if ev['status']!='PUBLISHED': raise ApiError(400,'Solo puedes apuntarte a eventos publicados')
            if ev['coverage']['isFull']: raise ApiError(400,'No puedes apuntarte a este evento porque ya está completo')
            old=con.execute('SELECT * FROM event_worker_assignments WHERE event_id=? AND worker_id=?',(eid,wid)).fetchone()
            if old and old['status'] in ACTIVE_ASSIGNMENTS: raise ApiError(409,'Ya estás apuntado a este evento')
            if old: con.execute("UPDATE event_worker_assignments SET status='SIGNED_UP',signed_up_at=?,updated_at=? WHERE id=?",(ts,ts,old['id']))
            else: con.execute("INSERT INTO event_worker_assignments(event_id,worker_id,status,signed_up_at,created_at,updated_at) VALUES(?,?,'SIGNED_UP',?,?,?)",(eid,wid,ts,ts,ts))
            con.commit(); return self.send_json(201,{'message':'Te has apuntado al evento correctamente'})
        if len(parts)>=4 and parts[3]=='leave':
            self.require(u,'WORKER');
            if ev['status'] in ('COMPLETED','CANCELLED'): raise ApiError(400,'No puedes salirte de eventos cerrados, completados o cancelados')
            if datetime.fromisoformat(ev['startDate']).replace(tzinfo=timezone.utc)-datetime.now(timezone.utc) < timedelta(hours=LEAVE_HOURS): raise ApiError(400,f'No puedes salirte de un evento con menos de {LEAVE_HOURS} horas de antelación')
            con.execute("UPDATE event_worker_assignments SET status='CANCELLED',updated_at=? WHERE event_id=? AND worker_id=?",(ts,eid,u['workerProfile']['id'])); con.commit(); return self.send_json(204)
        if len(parts)>=4 and parts[3]=='assignments':
            self.require(u,'ADMIN')
            if self.command=='POST':
                d=decamel(self.body());
                if ev['coverage']['isFull']: raise ApiError(400,'No puedes asignar más trabajadores porque el evento está completo')
                old=con.execute('SELECT * FROM event_worker_assignments WHERE event_id=? AND worker_id=?',(eid,d['worker_id'])).fetchone()
                if old: con.execute('UPDATE event_worker_assignments SET status=?,updated_at=? WHERE id=?',(d.get('status','ASSIGNED'),ts,old['id']))
                else: con.execute('INSERT INTO event_worker_assignments(event_id,worker_id,status,signed_up_at,created_at,updated_at) VALUES(?,?,?,?,?,?)',(eid,d['worker_id'],d.get('status','ASSIGNED'),ts,ts,ts))
                con.commit(); return self.send_json(201,{'message':'Trabajador asignado correctamente'})
            if self.command=='DELETE': con.execute("UPDATE event_worker_assignments SET status='REMOVED',updated_at=? WHERE event_id=? AND worker_id=?",(ts,eid,int(parts[4]))); con.commit(); return self.send_json(204)
    def do_GET(self):
        if self.path.startswith('/api/'): return self.handle_api()
        p = ROOT/'frontend'/(urlparse(self.path).path.lstrip('/') or 'index.html')
        if not p.exists(): p=ROOT/'frontend'/'index.html'
        self.send_response(200); self.send_header('Content-Type','text/css' if p.suffix=='.css' else 'application/javascript' if p.suffix=='.js' else 'text/html'); self.end_headers(); self.wfile.write(p.read_bytes())
    def do_POST(self): return self.handle_api()
    def do_PUT(self): return self.handle_api()
    def do_DELETE(self): return self.handle_api()

def serve():
    migrate(); print(f'App local en http://localhost:{PORT}'); ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
if __name__=='__main__':
    cmd=sys.argv[1] if len(sys.argv)>1 else 'serve'
    {'migrate':migrate,'seed':seed,'reset':lambda:(DB_PATH.exists() and DB_PATH.unlink(), seed()),'serve':serve}.get(cmd,serve)()
