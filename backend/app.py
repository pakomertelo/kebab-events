#!/usr/bin/env python3
import base64, hashlib, hmac, json, math, os, secrets, sqlite3, sys, time
from collections import defaultdict
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
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
load_env()
DB_PATH = Path(os.getenv('DATABASE_PATH', ROOT / 'backend' / 'dev.db'))
SECRET = os.getenv('JWT_SECRET', 'local-dev-secret').encode()
PORT = int(os.getenv('PORT', '4000'))
LEAVE_HOURS = 24
ACTIVE = ('JOINED', 'ASSIGNED', 'RESERVE', 'ATTENDED')
NORMAL_ACTIVE = ('JOINED', 'ASSIGNED', 'ATTENDED')
RESERVE_ACTIVE = ('RESERVE',)
EVENT_TYPES = ('Boda','Concierto','Congreso','Fiesta privada','Evento corporativo','Festival','Catering','Otro')

def utcnow(): return datetime.now(timezone.utc)
def now(): return utcnow().isoformat()
def iso_days(days): return (utcnow() + timedelta(days=days)).date().isoformat()
def connect():
    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row; con.execute('PRAGMA foreign_keys=ON'); return con
def rowdict(r): return dict(r) if r else None
class ApiError(Exception):
    def __init__(self, status, msg): self.status, self.msg = status, msg

def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 120000).hex()
    return f'{salt}${digest}'
def verify_password(password, stored):
    salt, digest = stored.split('$', 1)
    return hmac.compare_digest(hash_password(password, salt).split('$', 1)[1], digest)
def b64(data): return base64.urlsafe_b64encode(json.dumps(data, separators=(',', ':')).encode()).rstrip(b'=').decode()
def sign_token(user):
    body = b64({'sub': user['id'], 'role': user['role'], 'exp': int(time.time()) + 8 * 3600})
    sig = base64.urlsafe_b64encode(hmac.new(SECRET, body.encode(), hashlib.sha256).digest()).rstrip(b'=').decode()
    return f'{body}.{sig}'
def read_token(token):
    body, sig = token.split('.', 1)
    expected = base64.urlsafe_b64encode(hmac.new(SECRET, body.encode(), hashlib.sha256).digest()).rstrip(b'=').decode()
    if not hmac.compare_digest(sig, expected): raise ValueError('bad signature')
    payload = json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)))
    if payload['exp'] < time.time(): raise ValueError('expired')
    return payload

def migrate():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = connect(); cur = con.cursor()
    cur.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('ADMIN','WORKER')),is_active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS worker_profiles(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER UNIQUE NOT NULL,first_name TEXT NOT NULL,last_name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,phone TEXT NOT NULL,is_active INTEGER NOT NULL DEFAULT 1,internal_notes TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS clients(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,contact_person TEXT NOT NULL,email TEXT NOT NULL,phone TEXT NOT NULL,address TEXT NOT NULL,internal_notes TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,client_id INTEGER NOT NULL,type TEXT NOT NULL DEFAULT 'Otro',description TEXT NOT NULL,start_date TEXT NOT NULL,end_date TEXT NOT NULL,start_time TEXT NOT NULL,end_time TEXT NOT NULL,location TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('DRAFT','PUBLISHED','COMPLETED','CANCELLED')),min_workers INTEGER NOT NULL,max_workers INTEGER,hourly_rate REAL NOT NULL DEFAULT 0,currency TEXT NOT NULL DEFAULT 'EUR',reserve_enabled INTEGER NOT NULL DEFAULT 1,reserve_percentage REAL NOT NULL DEFAULT 10,internal_notes TEXT,worker_instructions TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(client_id) REFERENCES clients(id));
    CREATE TABLE IF NOT EXISTS event_worker_assignments(id INTEGER PRIMARY KEY AUTOINCREMENT,event_id INTEGER NOT NULL,worker_id INTEGER NOT NULL,slot_type TEXT NOT NULL DEFAULT 'NORMAL' CHECK(slot_type IN ('NORMAL','RESERVE')),status TEXT NOT NULL CHECK(status IN ('JOINED','ASSIGNED','RESERVE','CANCELLED','ATTENDED','NO_SHOW','REMOVED')),attendance_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(attendance_status IN ('PENDING','ATTENDED','NO_SHOW','CANCELLED')),signed_up_at TEXT NOT NULL,joined_at TEXT NOT NULL,promoted_at TEXT,attended_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,FOREIGN KEY(worker_id) REFERENCES worker_profiles(id) ON DELETE CASCADE,UNIQUE(event_id,worker_id));
    CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_date); CREATE INDEX IF NOT EXISTS idx_events_type ON events(type); CREATE INDEX IF NOT EXISTS idx_assign_event ON event_worker_assignments(event_id); CREATE INDEX IF NOT EXISTS idx_assign_worker ON event_worker_assignments(worker_id);
    ''')
    # Lightweight additive migrations for databases created by the previous version.
    for table, columns in {
        'events': [('type', "TEXT NOT NULL DEFAULT 'Otro'"), ('hourly_rate', 'REAL NOT NULL DEFAULT 0'), ('currency', "TEXT NOT NULL DEFAULT 'EUR'"), ('reserve_enabled', 'INTEGER NOT NULL DEFAULT 1'), ('reserve_percentage', 'REAL NOT NULL DEFAULT 10')],
        'event_worker_assignments': [('slot_type', "TEXT NOT NULL DEFAULT 'NORMAL'"), ('attendance_status', "TEXT NOT NULL DEFAULT 'PENDING'"), ('joined_at', 'TEXT'), ('promoted_at', 'TEXT'), ('attended_at', 'TEXT')]
    }.items():
        existing = {r['name'] for r in cur.execute(f'PRAGMA table_info({table})')}
        for name, ddl in columns:
            if name not in existing: cur.execute(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}')
    cur.execute("UPDATE event_worker_assignments SET status='JOINED' WHERE status='SIGNED_UP'")
    cur.execute("UPDATE event_worker_assignments SET status='REMOVED' WHERE status='REMOVED'")
    cur.execute("UPDATE event_worker_assignments SET joined_at=COALESCE(joined_at,signed_up_at,created_at,?)", (now(),))
    con.commit(); con.close()

def seed():
    migrate(); con = connect(); cur = con.cursor(); ts = now()
    for table in ['event_worker_assignments','events','worker_profiles','clients','users']: cur.execute(f'DELETE FROM {table}')
    def user(name,email,password,role):
        cur.execute('INSERT INTO users(name,email,password_hash,role,is_active,created_at,updated_at) VALUES(?,?,?,?,1,?,?)',(name,email,hash_password(password),role,ts,ts)); return cur.lastrowid
    user('Admin Eventos','admin@kebab-events.local','Admin123!','ADMIN')
    workers=[]
    for first,last,email,phone in [('Ana','García','ana@kebab-events.local','+34 600 111 222'),('Luis','Martín','luis@kebab-events.local','+34 600 333 444'),('Sara','López','sara@kebab-events.local','+34 600 555 666'),('Diego','Navarro','diego@kebab-events.local','+34 600 777 888')]:
        uid=user(f'{first} {last}',email,'Worker123!','WORKER')
        cur.execute('INSERT INTO worker_profiles(user_id,first_name,last_name,email,phone,is_active,internal_notes,created_at,updated_at) VALUES(?,?,?,?,?,1,?,?,?)',(uid,first,last,email,phone,'Trabajador de prueba seed.',ts,ts)); workers.append(cur.lastrowid)
    clients=[]
    for data in [('ACME Corp','Marta Ruiz','eventos@acme.test','+34 910 111 222','Madrid Centro','Cliente recurrente.'),('Bodas del Sur','Pablo Soto','hola@bodasdelsur.test','+34 950 333 444','Sevilla','Atención a horarios.'),('Festival Norte','Laura Pérez','staff@festivalnorte.test','+34 944 555 666','Bilbao','Alto volumen.')]:
        cur.execute('INSERT INTO clients(name,contact_person,email,phone,address,internal_notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(*data,ts,ts)); clients.append(cur.lastrowid)
    events=[
        ('Kickoff anual ACME',clients[0],'Evento corporativo','Evento corporativo de presentación anual.',15,15,'09:00','18:00','Palacio de Congresos, Madrid','PUBLISHED',3,3,14,'EUR',1,10,'Revisar acreditaciones.','Uniforme negro, llegar 45 minutos antes.'),
        ('Catering boda Soto',clients[1],'Boda','Servicio de apoyo en banquete.',25,25,'16:00','23:30','Hacienda El Olivar, Sevilla','PUBLISHED',2,2,12,'EUR',1,10,'Contacto en finca: Carmen.','Zapato cómodo y camisa blanca.'),
        ('Festival de invierno',clients[2],'Festival','Operativa de accesos y barras.',40,42,'12:00','02:00','BEC Bilbao','DRAFT',8,12,13.5,'EUR',1,15,'Pendiente proveedor.','Briefing pendiente.'),
        ('Cena corporativa cancelada',clients[0],'Evento corporativo','Evento cancelado por el cliente.',7,7,'20:00','23:00','Hotel Centro','CANCELLED',2,4,16,'EUR',0,0,'No reactivar.','No aplica.'),
        ('Feria gastronómica completada',clients[2],'Festival','Evento finalizado con éxito.',-10,-9,'10:00','20:00','Bilbao Arena','COMPLETED',2,3,11,'EUR',1,10,'Buen resultado.','Histórico.'),
    ]
    ids=[]
    for e in events:
        cur.execute('''INSERT INTO events(title,client_id,type,description,start_date,end_date,start_time,end_time,location,status,min_workers,max_workers,hourly_rate,currency,reserve_enabled,reserve_percentage,internal_notes,worker_instructions,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(e[0],e[1],e[2],e[3],iso_days(e[4]),iso_days(e[5]),e[6],e[7],e[8],e[9],e[10],e[11],e[12],e[13],e[14],e[15],e[16],e[17],ts,ts)); ids.append(cur.lastrowid)
    assigns=[(ids[0],workers[0],'NORMAL','ASSIGNED','PENDING'),(ids[0],workers[1],'NORMAL','JOINED','PENDING'),(ids[0],workers[2],'RESERVE','RESERVE','PENDING'),(ids[1],workers[0],'NORMAL','ASSIGNED','PENDING'),(ids[1],workers[2],'NORMAL','ASSIGNED','PENDING'),(ids[4],workers[0],'NORMAL','ATTENDED','ATTENDED'),(ids[4],workers[1],'NORMAL','ATTENDED','ATTENDED')]
    for event_id,worker_id,slot,status,attendance in assigns:
        cur.execute('''INSERT INTO event_worker_assignments(event_id,worker_id,slot_type,status,attendance_status,signed_up_at,joined_at,attended_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)''',(event_id,worker_id,slot,status,attendance,ts,ts,ts if attendance=='ATTENDED' else None,ts,ts))
    con.commit(); con.close(); print('Seed completado: admin@kebab-events.local/Admin123!, ana@kebab-events.local/Worker123!')

def camel(obj):
    if isinstance(obj, list): return [camel(x) for x in obj]
    if not isinstance(obj, dict): return obj
    mp={'created_at':'createdAt','updated_at':'updatedAt','contact_person':'contactPerson','internal_notes':'internalNotes','client_id':'clientId','start_date':'startDate','end_date':'endDate','start_time':'startTime','end_time':'endTime','min_workers':'minWorkers','max_workers':'maxWorkers','hourly_rate':'hourlyRate','reserve_enabled':'reserveEnabled','reserve_percentage':'reservePercentage','worker_instructions':'workerInstructions','worker_id':'workerId','event_id':'eventId','slot_type':'slotType','attendance_status':'attendanceStatus','signed_up_at':'signedUpAt','joined_at':'joinedAt','promoted_at':'promotedAt','attended_at':'attendedAt','is_active':'isActive','first_name':'firstName','last_name':'lastName','user_id':'userId'}
    return {mp.get(k,k):camel(v) for k,v in obj.items()}
def decamel(data):
    mp={'contactPerson':'contact_person','internalNotes':'internal_notes','clientId':'client_id','startDate':'start_date','endDate':'end_date','startTime':'start_time','endTime':'end_time','minWorkers':'min_workers','maxWorkers':'max_workers','hourlyRate':'hourly_rate','reserveEnabled':'reserve_enabled','reservePercentage':'reserve_percentage','workerInstructions':'worker_instructions','workerId':'worker_id','slotType':'slot_type','attendanceStatus':'attendance_status','isActive':'is_active','firstName':'first_name','lastName':'last_name'}
    return {mp.get(k,k):v for k,v in data.items()}
def parse_dt(date_value, time_value): return datetime.fromisoformat(f'{date_value[:10]}T{time_value}').replace(tzinfo=timezone.utc)
def duration_hours(event):
    start, end = parse_dt(event['start_date'], event['start_time']), parse_dt(event['end_date'], event['end_time'])
    return max(round((end - start).total_seconds() / 3600, 2), 0)
def reserve_capacity(event):
    if not event.get('reserve_enabled') or not event.get('max_workers'): return 0
    return math.ceil(event['max_workers'] * float(event.get('reserve_percentage') or 0) / 100)
def money(value): return round(float(value or 0), 2)
def event_financials(event, assignments):
    hours = duration_hours(event); pay = money(hours * float(event.get('hourly_rate') or 0))
    normal = [a for a in assignments if a['slot_type']=='NORMAL' and a['status'] in ACTIVE]
    attended = [a for a in assignments if a['slot_type']=='NORMAL' and a['attendance_status']=='ATTENDED']
    return {'durationHours':hours,'estimatedPayPerWorker':pay,'confirmedPayPerWorker':pay,'estimatedStaffCost':money(pay*len(normal)),'confirmedStaffCost':money(pay*len(attended)),'currency':event.get('currency','EUR')}
def coverage(event, assignments):
    normal = [a for a in assignments if a['slot_type']=='NORMAL' and a['status'] in ACTIVE]
    reserve = [a for a in assignments if a['slot_type']=='RESERVE' and a['status'] in ACTIVE]
    normal_cap = event.get('max_workers') or event['min_workers']; reserve_cap = reserve_capacity(event)
    missing = max(event['min_workers'] - len(normal), 0); normal_available=max(normal_cap-len(normal),0); reserve_available=max(reserve_cap-len(reserve),0)
    full = normal_available == 0; reserve_full = reserve_cap > 0 and reserve_available == 0
    label = f'Faltan {missing} trabajadores'
    if event['status']=='CANCELLED': label='Evento cancelado'
    elif event['status']=='COMPLETED': label='Evento completo'
    elif full and reserve_full: label='Evento completo'
    elif missing==0: label='Mínimo cubierto'
    return {'normalCount':len(normal),'reserveCount':len(reserve),'assignedCount':len(normal),'minWorkers':event['min_workers'],'maxWorkers':event.get('max_workers'),'reserveEnabled':bool(event.get('reserve_enabled')),'reservePercentage':event.get('reserve_percentage'),'reserveCapacity':reserve_cap,'normalAvailable':normal_available,'reserveAvailable':reserve_available,'missingWorkers':missing,'isCovered':missing==0,'isFull':full,'isReserveFull':reserve_full,'label':label}
def enrich_event(con, event):
    event=dict(event); event['reserve_enabled']=bool(event.get('reserve_enabled'))
    event['client']=rowdict(con.execute('SELECT * FROM clients WHERE id=?',(event['client_id'],)).fetchone())
    rows=con.execute('''SELECT a.*,w.first_name,w.last_name,w.email,w.phone,w.is_active FROM event_worker_assignments a JOIN worker_profiles w ON w.id=a.worker_id WHERE a.event_id=? AND a.status!='REMOVED' ORDER BY a.joined_at ASC,a.created_at ASC''',(event['id'],)).fetchall()
    assignments=[]
    for r in rows:
        d=dict(r); d['worker']={'id':r['worker_id'],'firstName':r['first_name'],'lastName':r['last_name'],'email':r['email'],'phone':r['phone'],'isActive':bool(r['is_active'])}; assignments.append(d)
    event['assignments']=assignments; event['coverage']=coverage(event, assignments); event['financials']=event_financials(event, assignments)
    return camel(event)
def validate_event(d):
    for key in ['title','description','start_date','end_date','start_time','end_time','location','type']: 
        if not d.get(key): raise ApiError(422, f'Campo obligatorio: {key}')
    if d.get('type') not in EVENT_TYPES: d['type']='Otro'
    d['min_workers']=int(d.get('min_workers') or 0); d['max_workers']=int(d['max_workers']) if d.get('max_workers') not in (None,'') else None
    d['hourly_rate']=float(d.get('hourly_rate') or 0); d['reserve_percentage']=float(d.get('reserve_percentage') if d.get('reserve_percentage') not in (None,'') else 10); d['reserve_enabled']=1 if str(d.get('reserve_enabled', True)).lower() in ('1','true','on','yes') else 0
    if d['min_workers'] <= 0: raise ApiError(422,'El mínimo de trabajadores debe ser mayor que 0')
    if d['max_workers'] and d['max_workers'] < d['min_workers']: raise ApiError(422,'El máximo no puede ser menor que el mínimo')
    if d['hourly_rate'] < 0: raise ApiError(422,'El precio por hora debe ser mayor o igual a 0')
    if not 0 <= d['reserve_percentage'] <= 100: raise ApiError(422,'El porcentaje de reserva debe estar entre 0 y 100')
    if d['reserve_enabled'] and not d['max_workers']: raise ApiError(422,'Para activar reserva debes definir máximo de trabajadores normales')
    if parse_dt(d['end_date'], d['end_time']) <= parse_dt(d['start_date'], d['start_time']): raise ApiError(422,'La fecha y hora de fin deben ser posteriores al inicio')
    d['currency']=d.get('currency') or 'EUR'; return d

def promote_first_reserve(con, event_id):
    reserve = con.execute("SELECT * FROM event_worker_assignments WHERE event_id=? AND slot_type='RESERVE' AND status='RESERVE' ORDER BY joined_at ASC LIMIT 1", (event_id,)).fetchone()
    if reserve:
        con.execute("UPDATE event_worker_assignments SET slot_type='NORMAL',status='JOINED',promoted_at=?,updated_at=? WHERE id=?", (now(), now(), reserve['id']))
        return True
    return False

def monthly_earnings(con, worker_id):
    rows=con.execute("""SELECT a.*,e.*,c.name client_name FROM event_worker_assignments a JOIN events e ON e.id=a.event_id JOIN clients c ON c.id=e.client_id WHERE a.worker_id=? AND a.status!='REMOVED' ORDER BY e.start_date DESC""", (worker_id,)).fetchall()
    months=defaultdict(lambda:{'month':'','estimatedTotal':0,'confirmedTotal':0,'events':[]})
    today=utcnow().date().isoformat()
    for r in rows:
        event=dict(r); month=event['start_date'][:7]; fin=event_financials(event,[dict(r)])
        estimated = fin['estimatedPayPerWorker'] if event['slot_type']=='NORMAL' and event['status'] in ACTIVE and event['attendance_status']!='NO_SHOW' else 0
        confirmed = fin['confirmedPayPerWorker'] if event['slot_type']=='NORMAL' and event['attendance_status']=='ATTENDED' else 0
        m=months[month]; m['month']=month; m['estimatedTotal']=money(m['estimatedTotal']+estimated); m['confirmedTotal']=money(m['confirmedTotal']+confirmed)
        m['events'].append({'eventId':event['event_id'],'title':event['title'],'date':event['start_date'],'hours':fin['durationHours'],'hourlyRate':event['hourly_rate'],'estimated':money(estimated),'confirmed':money(confirmed),'status':event['status'],'slotType':event['slot_type'],'attendanceStatus':event['attendance_status'],'isFuture':event['start_date']>=today})
    return list(months.values())

class Handler(BaseHTTPRequestHandler):
    def send_json(self,status,data=None):
        self.send_response(status); self.send_header('Content-Type','application/json'); self.end_headers()
        if data is not None: self.wfile.write(json.dumps(data).encode())
    def body(self):
        n=int(self.headers.get('content-length','0')); return json.loads(self.rfile.read(n) or b'{}')
    def user(self, con):
        h=self.headers.get('Authorization','')
        if not h.startswith('Bearer '): raise ApiError(401,'No autenticado')
        try: payload=read_token(h[7:])
        except Exception: raise ApiError(401,'Sesión inválida o caducada')
        u=con.execute('SELECT * FROM users WHERE id=? AND is_active=1',(payload['sub'],)).fetchone()
        if not u: raise ApiError(401,'Usuario no válido o inactivo')
        u=dict(u); u['workerProfile']=rowdict(con.execute('SELECT * FROM worker_profiles WHERE user_id=?',(u['id'],)).fetchone()); return u
    def require(self,u,*roles):
        if u['role'] not in roles: raise ApiError(403,'No tienes permisos para realizar esta acción')
    def route(self):
        con=connect(); parsed=urlparse(self.path); path=parsed.path; qs={k:v[0] for k,v in parse_qs(parsed.query).items()}
        try:
            if path=='/api/auth/login' and self.command=='POST':
                d=self.body(); u=con.execute('SELECT * FROM users WHERE email=?',(d.get('email'),)).fetchone()
                if not u or not verify_password(d.get('password',''),u['password_hash']): raise ApiError(401,'Credenciales incorrectas')
                u=dict(u); u['workerProfile']=rowdict(con.execute('SELECT * FROM worker_profiles WHERE user_id=?',(u['id'],)).fetchone()); return self.send_json(200,{'token':sign_token(u),'user':camel({k:v for k,v in u.items() if k!='password_hash'})})
            u=self.user(con)
            if path=='/api/auth/me': return self.send_json(200,{'user':camel({k:v for k,v in u.items() if k!='password_hash'})})
            if path=='/api/meta/event-types': return self.send_json(200,list(EVENT_TYPES))
            if path=='/api/workers/me/profile':
                self.require(u,'WORKER'); wp=u['workerProfile']; assignments=con.execute("SELECT * FROM event_worker_assignments WHERE worker_id=? AND status!='REMOVED'",(wp['id'],)).fetchall()
                events=[enrich_event(con,con.execute('SELECT * FROM events WHERE id=?',(a['event_id'],)).fetchone()) for a in assignments]
                return self.send_json(200,{'profile':camel(wp),'stats':{'upcoming':sum(e['startDate']>=utcnow().date().isoformat() and any(a['workerId']==wp['id'] and a['slotType']=='NORMAL' for a in e['assignments']) for e in events),'reserve':sum(any(a['workerId']==wp['id'] and a['slotType']=='RESERVE' and a['status']=='RESERVE' for a in e['assignments']) for e in events),'completed':sum(e['status']=='COMPLETED' for e in events)},'earnings':monthly_earnings(con,wp['id'])})
            if path=='/api/workers/me/earnings': self.require(u,'WORKER'); return self.send_json(200,monthly_earnings(con,u['workerProfile']['id']))
            if path=='/api/events/dashboard/summary':
                self.require(u,'ADMIN'); events=[enrich_event(con,r) for r in con.execute('SELECT * FROM events ORDER BY start_date').fetchall()]; today=utcnow().date().isoformat()
                return self.send_json(200,{'totalEvents':len(events),'upcomingEvents':sum(e['startDate']>=today for e in events),'understaffedEvents':sum(e['coverage']['missingWorkers']>0 and e['status'] not in ('CANCELLED','COMPLETED') for e in events),'completedEvents':sum(e['status']=='COMPLETED' for e in events),'activeWorkers':con.execute('SELECT COUNT(*) c FROM worker_profiles WHERE is_active=1').fetchone()['c'],'clients':con.execute('SELECT COUNT(*) c FROM clients').fetchone()['c'],'estimatedStaffCost':money(sum(e['financials']['estimatedStaffCost'] for e in events)),'confirmedStaffCost':money(sum(e['financials']['confirmedStaffCost'] for e in events)),'latestEvents':events[:5],'importantUpcoming':[e for e in events if e['startDate']>=today][:5]})
            if path=='/api/events/calendar': return self.events(con,u,['api','events'],qs,calendar=True)
            if path=='/api/events/mine/list':
                self.require(u,'WORKER'); wid=u['workerProfile']['id']; rows=con.execute("SELECT * FROM event_worker_assignments WHERE worker_id=? AND status IN ('JOINED','ASSIGNED','RESERVE','ATTENDED') ORDER BY created_at DESC",(wid,)).fetchall(); out=[]
                for a in rows: out.append({**camel(dict(a)),'event':enrich_event(con,con.execute('SELECT * FROM events WHERE id=?',(a['event_id'],)).fetchone())})
                return self.send_json(200,out)
            parts=path.strip('/').split('/'); res=parts[1] if len(parts)>1 else ''
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
            q=f"%{qs.get('q','')}%"; return self.send_json(200,camel([dict(r) for r in con.execute('SELECT * FROM clients WHERE name LIKE ? OR email LIKE ? OR phone LIKE ? ORDER BY created_at DESC',(q,q,q)).fetchall()]))
        d=decamel(self.body()) if self.command in ('POST','PUT') else {}; cid=int(parts[2]) if len(parts)>2 else None
        if len(parts)==2 and self.command=='POST': con.execute('INSERT INTO clients(name,contact_person,email,phone,address,internal_notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(d['name'],d['contact_person'],d['email'],d['phone'],d['address'],d.get('internal_notes'),ts,ts)); con.commit(); return self.send_json(201,{'message':'Cliente creado correctamente'})
        if self.command=='PUT': con.execute('UPDATE clients SET name=?,contact_person=?,email=?,phone=?,address=?,internal_notes=?,updated_at=? WHERE id=?',(d['name'],d['contact_person'],d['email'],d['phone'],d['address'],d.get('internal_notes'),ts,cid)); con.commit(); return self.send_json(200,{'message':'Cliente actualizado correctamente'})
        if self.command=='DELETE': con.execute('DELETE FROM clients WHERE id=?',(cid,)); con.commit(); return self.send_json(204)
    def workers(self,con,u,parts,qs):
        self.require(u,'ADMIN'); ts=now()
        if len(parts)==2 and self.command=='GET':
            q=f"%{qs.get('q','')}%"; rows=con.execute('SELECT * FROM worker_profiles WHERE first_name LIKE ? OR last_name LIKE ? OR email LIKE ? ORDER BY created_at DESC',(q,q,q)).fetchall(); return self.send_json(200,camel([dict(r) for r in rows]))
        d=decamel(self.body()) if self.command in ('POST','PUT') else {}; wid=int(parts[2]) if len(parts)>2 else None
        if len(parts)==2 and self.command=='POST':
            cur=con.execute('INSERT INTO users(name,email,password_hash,role,is_active,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(f"{d['first_name']} {d['last_name']}",d['email'],hash_password(d.get('password','Password123')),'WORKER',int(d.get('is_active',1)),ts,ts)); uid=cur.lastrowid
            con.execute('INSERT INTO worker_profiles(user_id,first_name,last_name,email,phone,is_active,internal_notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(uid,d['first_name'],d['last_name'],d['email'],d['phone'],int(d.get('is_active',1)),d.get('internal_notes'),ts,ts)); con.commit(); return self.send_json(201,{'message':'Trabajador creado correctamente'})
        if self.command=='PUT':
            con.execute('UPDATE worker_profiles SET first_name=?,last_name=?,email=?,phone=?,is_active=?,internal_notes=?,updated_at=? WHERE id=?',(d['first_name'],d['last_name'],d['email'],d['phone'],int(d.get('is_active',1)),d.get('internal_notes'),ts,wid)); wp=con.execute('SELECT * FROM worker_profiles WHERE id=?',(wid,)).fetchone(); con.execute('UPDATE users SET name=?,email=?,is_active=?,updated_at=? WHERE id=?',(f"{d['first_name']} {d['last_name']}",d['email'],int(d.get('is_active',1)),ts,wp['user_id'])); con.commit(); return self.send_json(200,{'message':'Trabajador actualizado correctamente'})
        if self.command=='DELETE': con.execute('DELETE FROM worker_profiles WHERE id=?',(wid,)); con.commit(); return self.send_json(204)
    def users(self,con,u,parts):
        self.require(u,'ADMIN'); ts=now()
        if len(parts)==2 and self.command=='GET': return self.send_json(200,camel([{k:v for k,v in dict(r).items() if k!='password_hash'} for r in con.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()]))
        d=decamel(self.body()) if self.command in ('POST','PUT') else {}; uid=int(parts[2]) if len(parts)>2 else None
        if len(parts)==2 and self.command=='POST': con.execute('INSERT INTO users(name,email,password_hash,role,is_active,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(d['name'],d['email'],hash_password(d.get('password','Password123')),d['role'],int(d.get('is_active',1)),ts,ts)); con.commit(); return self.send_json(201,{'message':'Usuario creado correctamente'})
        if self.command=='PUT': con.execute('UPDATE users SET name=?,email=?,role=?,is_active=?,updated_at=? WHERE id=?',(d['name'],d['email'],d['role'],int(d.get('is_active',1)),ts,uid)); con.commit(); return self.send_json(200,{'message':'Usuario actualizado correctamente'})
        if self.command=='DELETE': con.execute('DELETE FROM users WHERE id=?',(uid,)); con.commit(); return self.send_json(204)
    def events(self,con,u,parts,qs,calendar=False):
        ts=now()
        if (len(parts)==2 and self.command=='GET') or calendar:
            clauses=[]; vals=[]
            if u['role']=='WORKER': clauses.append("status='PUBLISHED'")
            for key,col in [('status','status'),('clientId','client_id'),('type','type')]:
                if qs.get(key): clauses.append(f'{col}=?'); vals.append(qs[key])
            if qs.get('from'): clauses.append('start_date>=?'); vals.append(qs['from'])
            if qs.get('to'): clauses.append('start_date<=?'); vals.append(qs['to'])
            if qs.get('q'): clauses.append('(title LIKE ? OR location LIKE ? OR description LIKE ?)'); vals += [f"%{qs['q']}%"]*3
            sql='SELECT * FROM events '+(('WHERE '+ ' AND '.join(clauses)) if clauses else '')+' ORDER BY start_date ASC,start_time ASC'
            events=[enrich_event(con,r) for r in con.execute(sql,vals).fetchall()]
            if qs.get('staffing')=='missing': events=[e for e in events if e['coverage']['missingWorkers']>0 and e['status'] not in ('CANCELLED','COMPLETED')]
            if qs.get('availability')=='normal': events=[e for e in events if e['coverage']['normalAvailable']>0]
            if qs.get('availability')=='reserve': events=[e for e in events if e['coverage']['normalAvailable']==0 and e['coverage']['reserveAvailable']>0]
            if qs.get('availability')=='complete': events=[e for e in events if e['coverage']['normalAvailable']==0 and e['coverage']['reserveAvailable']==0]
            if u['role']=='WORKER' and qs.get('participation'):
                wid=u['workerProfile']['id']
                def mya(e): return next((a for a in e['assignments'] if a['workerId']==wid and a['status'] in ACTIVE), None)
                p=qs['participation']
                if p=='joined': events=[e for e in events if (a:=mya(e)) and a['slotType']=='NORMAL']
                elif p=='reserve': events=[e for e in events if (a:=mya(e)) and a['slotType']=='RESERVE']
                elif p=='not_joined': events=[e for e in events if not mya(e)]
                elif p=='available': events=[e for e in events if not mya(e) and (e['coverage']['normalAvailable']>0 or e['coverage']['reserveAvailable']>0)]
            return self.send_json(200,events)
        if len(parts)==2 and self.command=='POST':
            self.require(u,'ADMIN'); d=validate_event(decamel(self.body()))
            con.execute('''INSERT INTO events(title,client_id,type,description,start_date,end_date,start_time,end_time,location,status,min_workers,max_workers,hourly_rate,currency,reserve_enabled,reserve_percentage,internal_notes,worker_instructions,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(d['title'],d['client_id'],d['type'],d['description'],d['start_date'][:10],d['end_date'][:10],d['start_time'],d['end_time'],d['location'],d['status'],d['min_workers'],d.get('max_workers'),d['hourly_rate'],d['currency'],d['reserve_enabled'],d['reserve_percentage'],d.get('internal_notes'),d.get('worker_instructions'),ts,ts)); con.commit(); return self.send_json(201,{'message':'Evento creado correctamente'})
        eid=int(parts[2]); ev=enrich_event(con,con.execute('SELECT * FROM events WHERE id=?',(eid,)).fetchone())
        if len(parts)==3 and self.command=='GET':
            if u['role']=='WORKER' and ev['status']!='PUBLISHED': raise ApiError(403,'No tienes permisos para ver este evento')
            return self.send_json(200,ev)
        if len(parts)==3 and self.command=='PUT':
            self.require(u,'ADMIN'); d=validate_event(decamel(self.body()))
            con.execute('''UPDATE events SET title=?,client_id=?,type=?,description=?,start_date=?,end_date=?,start_time=?,end_time=?,location=?,status=?,min_workers=?,max_workers=?,hourly_rate=?,currency=?,reserve_enabled=?,reserve_percentage=?,internal_notes=?,worker_instructions=?,updated_at=? WHERE id=?''',(d['title'],d['client_id'],d['type'],d['description'],d['start_date'][:10],d['end_date'][:10],d['start_time'],d['end_time'],d['location'],d['status'],d['min_workers'],d.get('max_workers'),d['hourly_rate'],d['currency'],d['reserve_enabled'],d['reserve_percentage'],d.get('internal_notes'),d.get('worker_instructions'),ts,eid)); con.commit(); return self.send_json(200,{'message':'Evento actualizado correctamente'})
        if len(parts)==3 and self.command=='DELETE': self.require(u,'ADMIN'); con.execute('DELETE FROM events WHERE id=?',(eid,)); con.commit(); return self.send_json(204)
        if len(parts)>=4 and parts[3]=='join':
            self.require(u,'WORKER'); wid=u['workerProfile']['id']
            if ev['status']!='PUBLISHED': raise ApiError(400,'Solo puedes apuntarte a eventos publicados y no cancelados/completados')
            old=con.execute('SELECT * FROM event_worker_assignments WHERE event_id=? AND worker_id=?',(eid,wid)).fetchone()
            if old and old['status'] in ACTIVE: raise ApiError(409,'Ya estás apuntado a este evento')
            if ev['coverage']['normalAvailable']>0: slot,status='NORMAL','JOINED'; msg='Te has apuntado al evento correctamente'
            elif ev['coverage']['reserveAvailable']>0: slot,status='RESERVE','RESERVE'; msg='Te has apuntado como reserva correctamente'
            else: raise ApiError(400,'Evento completo y reserva completa')
            if old: con.execute('UPDATE event_worker_assignments SET slot_type=?,status=?,attendance_status="PENDING",signed_up_at=?,joined_at=?,updated_at=? WHERE id=?',(slot,status,ts,ts,ts,old['id']))
            else: con.execute('INSERT INTO event_worker_assignments(event_id,worker_id,slot_type,status,attendance_status,signed_up_at,joined_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(eid,wid,slot,status,'PENDING',ts,ts,ts,ts))
            con.commit(); return self.send_json(201,{'message':msg,'slotType':slot})
        if len(parts)>=4 and parts[3]=='leave':
            self.require(u,'WORKER'); wid=u['workerProfile']['id']
            if ev['status'] in ('COMPLETED','CANCELLED'): raise ApiError(400,'No puedes salirte de eventos cerrados, completados o cancelados')
            if parse_dt(ev['startDate'], ev['startTime'])-utcnow() < timedelta(hours=LEAVE_HOURS): raise ApiError(400,f'No puedes salirte de un evento con menos de {LEAVE_HOURS} horas de antelación')
            old=con.execute('SELECT * FROM event_worker_assignments WHERE event_id=? AND worker_id=?',(eid,wid)).fetchone()
            con.execute("UPDATE event_worker_assignments SET status='CANCELLED',attendance_status='CANCELLED',updated_at=? WHERE event_id=? AND worker_id=?",(ts,eid,wid))
            if old and old['slot_type']=='NORMAL': promote_first_reserve(con,eid)
            con.commit(); return self.send_json(204)
        if len(parts)>=4 and parts[3]=='assignments':
            self.require(u,'ADMIN')
            wid=int(parts[4]) if len(parts)>4 else None
            if wid and len(parts)>=6 and parts[5]=='promote' and self.command=='POST':
                con.execute("UPDATE event_worker_assignments SET slot_type='NORMAL',status='JOINED',promoted_at=?,updated_at=? WHERE event_id=? AND worker_id=?",(ts,ts,eid,wid)); con.commit(); return self.send_json(200,{'message':'Reserva promocionada a plaza normal'})
            if wid and len(parts)>=6 and parts[5]=='attendance' and self.command=='POST':
                d=self.body(); att=d.get('attendanceStatus','PENDING')
                if att not in ('PENDING','ATTENDED','NO_SHOW','CANCELLED'): raise ApiError(422,'Estado de asistencia no válido')
                status={'ATTENDED':'ATTENDED','NO_SHOW':'NO_SHOW','CANCELLED':'CANCELLED','PENDING':'ASSIGNED'}.get(att,'ASSIGNED')
                con.execute('UPDATE event_worker_assignments SET attendance_status=?,status=?,attended_at=?,updated_at=? WHERE event_id=? AND worker_id=?',(att,status,ts if att=='ATTENDED' else None,ts,eid,wid)); con.commit(); return self.send_json(200,{'message':'Asistencia actualizada correctamente'})
            if self.command=='POST':
                d=decamel(self.body()); slot=d.get('slot_type') or ('NORMAL' if ev['coverage']['normalAvailable']>0 else 'RESERVE'); status='ASSIGNED' if slot=='NORMAL' else 'RESERVE'
                if slot=='NORMAL' and ev['coverage']['normalAvailable']<=0: raise ApiError(400,'No quedan plazas normales')
                if slot=='RESERVE' and ev['coverage']['reserveAvailable']<=0: raise ApiError(400,'No quedan plazas de reserva')
                old=con.execute('SELECT * FROM event_worker_assignments WHERE event_id=? AND worker_id=?',(eid,d['worker_id'])).fetchone()
                if old: con.execute('UPDATE event_worker_assignments SET slot_type=?,status=?,attendance_status="PENDING",updated_at=? WHERE id=?',(slot,status,ts,old['id']))
                else: con.execute('INSERT INTO event_worker_assignments(event_id,worker_id,slot_type,status,attendance_status,signed_up_at,joined_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(eid,d['worker_id'],slot,status,'PENDING',ts,ts,ts,ts))
                con.commit(); return self.send_json(201,{'message':'Trabajador asignado correctamente'})
            if self.command=='DELETE':
                removed=con.execute('SELECT * FROM event_worker_assignments WHERE event_id=? AND worker_id=?',(eid,wid)).fetchone(); con.execute("UPDATE event_worker_assignments SET status='REMOVED',attendance_status='CANCELLED',updated_at=? WHERE event_id=? AND worker_id=?",(ts,eid,wid))
                if removed and removed['slot_type']=='NORMAL': promote_first_reserve(con,eid)
                con.commit(); return self.send_json(204)
    def do_GET(self):
        if self.path.startswith('/api/'): return self.route()
        p = ROOT/'frontend'/(urlparse(self.path).path.lstrip('/') or 'index.html')
        if not p.exists(): p=ROOT/'frontend'/'index.html'
        self.send_response(200); self.send_header('Content-Type','text/css' if p.suffix=='.css' else 'application/javascript' if p.suffix=='.js' else 'text/html'); self.end_headers(); self.wfile.write(p.read_bytes())
    def do_POST(self): return self.route()
    def do_PUT(self): return self.route()
    def do_DELETE(self): return self.route()

def serve(): migrate(); print(f'App local en http://localhost:{PORT}'); ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
if __name__=='__main__':
    cmd=sys.argv[1] if len(sys.argv)>1 else 'serve'
    {'migrate':migrate,'seed':seed,'reset':lambda:(DB_PATH.exists() and DB_PATH.unlink(), seed()),'serve':serve}.get(cmd,serve)()
