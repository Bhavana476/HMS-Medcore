import React,{useEffect,useMemo,useRef,useState} from 'react';
import AccountAccess from './AccountAccess';
import {createRoot} from 'react-dom/client';
import {BrowserRouter,useNavigate} from 'react-router-dom';
import axios from 'axios';
import './style.css';
import './dashboard.css';
import './workspace.css';
import './portal.css';
import './medcore-theme.css';
import './polish.css';
import {PublicHome,Recovery,DoctorProfiles,Documents,RescheduleAppointments,Laboratory} from './Portal';
import {CareMessages,ReminderPreferences,BillPayments,ServiceSetup} from './Services';
import {Hospitals,Pharmacy,Vitals,Finance,AuditLog,AccountSecurity,StaffDashboard,AdminInsights,DoctorInsights,PrescriptionPrint,RecordClinicalDetails} from './Operations';
import hospitalHero from './assets/hospital-hero.png';
import wellnessHeart from './assets/wellness-heart.png';

const API=import.meta.env.VITE_API_URL||'http://127.0.0.1:8000/api';

// withCredentials sends the httpOnly refresh cookie to the auth endpoints.
const api=axios.create({baseURL:API,withCredentials:true});
localStorage.removeItem('refresh'); // refresh tokens now live only in an httpOnly cookie

api.interceptors.request.use(c=>{
  const t=localStorage.getItem('token');
  if(t)c.headers.Authorization=`Bearer ${t}`;
  return c;
});

// Access tokens last 15 minutes. On a 401, rotate the cookie-held refresh token once and retry.
let refreshing=null;
api.interceptors.response.use(r=>r,async error=>{
  const original=error.config;
  if(error.response?.status!==401||!localStorage.getItem('token')||original._retried||original.url.includes('/token/refresh/'))throw error;
  original._retried=true;
  refreshing=refreshing||axios.post(`${API}/token/refresh/`,{},{withCredentials:true})
    .then(r=>localStorage.setItem('token',r.data.access))
    .finally(()=>{refreshing=null;});
  try{await refreshing;}catch{localStorage.removeItem('token');throw error;}
  return api(original);
});

const ROLE_LABELS={
  SUPER_ADMIN:'Super Admin',
  ADMIN:'Administrator',
  DOCTOR:'Doctor',
  NURSE:'Nurse',
  RECEPTIONIST:'Receptionist',
  LAB_TECH:'Lab Technician',
  PHARMACIST:'Pharmacist',
  ACCOUNTANT:'Accountant',
  PATIENT:'Patient'
};

const NAV_ICONS={dashboard:'grid',accounts:'users',patients:'user',doctors:'stethoscope',appointments:'calendar','medical-records':'folder',prescriptions:'pill',bills:'receipt',documents:'folder','lab-orders':'heart',departments:'building',beds:'bed',availability:'clock',notifications:'bell',hospitals:'building',pharmacy:'pill',vitals:'heart',finance:'receipt','audit-logs':'file',security:'user'};

function Icon({name,size=18}){
  const shapes={
    grid:<><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
    users:<><path d="M16 20v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 20v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></>,
    user:<><circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/></>,
    file:<><path d="M6 2h8l4 4v16H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Z"/><path d="M14 2v5h5M8 12h8M8 16h8"/></>,
    stethoscope:<><path d="M6 3v5a4 4 0 0 0 8 0V3M4 3h4M12 3h4M10 12v2a5 5 0 0 0 10 0v-1"/><circle cx="20" cy="11" r="2"/></>,
    calendar:<><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/></>,
    folder:<><path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/></>,
    pill:<><path d="m9 15 6-6M6 18a4.24 4.24 0 0 1 0-6l6-6a4.24 4.24 0 0 1 6 6l-6 6a4.24 4.24 0 0 1-6 0Z"/></>,
    receipt:<><path d="M5 2h14v20l-3-2-4 2-4-2-3 2V2ZM9 7h6M9 11h6M9 15h4"/></>,
    building:<><rect x="5" y="4" width="14" height="17" rx="1"/><path d="M9 8h2M14 8h2M9 12h2M14 12h2M9 16h2M14 16h2M10 21v-4h4v4"/></>,
    sparkles:<><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3ZM20 3v4M18 5h4"/></>,
    pin:<><path d="m15 3 6 6-4 1-3 5-5-5 5-3 1-4ZM10 14l-7 7"/></>,
    bed:<><path d="M3 4v17M21 13v8M3 17h18M5 10h6a3 3 0 0 1 3 3H5v-3ZM14 10h4a3 3 0 0 1 3 3h-7"/></>,
    clock:<><circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/></>,
    bell:<><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4"/></>,
    search:<><circle cx="11" cy="11" r="7"/><path d="m16 16 5 5"/></>,
    sun:<><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></>,
    logout:<><path d="M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h5M14 7l5 5-5 5M8 12h11"/></>,
    heart:<><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{shapes[name]||shapes.grid}</svg>;
}

const NAVS={
  ADMIN:[
    ['Dashboard','dashboard'],
    ['Messages','care-threads'],
    ['Service Setup','integration-status'],

    ['Patients','patients'],
    ['Doctors','doctors'],
    ['Appointments','appointments'],
    ['Medical Records','medical-records'],
    ['Documents','documents'],
    ['Laboratory','lab-orders'],
    ['Prescriptions','prescriptions'],
    ['Billing','bills'],
    ['Departments','departments'],
    ['Bed Tracker','beds'],
    ['Availability','availability'],
    ['Pharmacy','pharmacy'],
    ['Finance','finance'],
    ['Staff Accounts','accounts'],
    ['Audit Log','audit-logs'],
    ['Notifications','notifications'],
    ['Account Security','security']
  ],

  SUPER_ADMIN:[
    ['Dashboard','dashboard'],
    ['Hospitals','hospitals'],
    ['Finance','finance'],
    ['Audit Log','audit-logs'],
    ['Account Security','security']
  ],

  NURSE:[
    ['Dashboard','dashboard'],
    ['Vitals & Notes','vitals'],
    ['Patients','patients'],
    ['Bed Tracker','beds'],
    ['Notifications','notifications'],
    ['Account Security','security']
  ],

  LAB_TECH:[
    ['Dashboard','dashboard'],
    ['Lab Queue','lab-orders'],
    ['Notifications','notifications'],
    ['Account Security','security']
  ],

  PHARMACIST:[
    ['Dashboard','dashboard'],
    ['Pharmacy','pharmacy'],
    ['Notifications','notifications'],
    ['Account Security','security']
  ],

  ACCOUNTANT:[
    ['Dashboard','dashboard'],
    ['Finance','finance'],
    ['Billing','bills'],
    ['Notifications','notifications'],
    ['Account Security','security']
  ],

  DOCTOR:[
    ['Dashboard','dashboard'],
    ['Messages','care-threads'],
    ['My Profile','doctors'],
    ['My Patients','patients'],
    ['My Appointments','appointments'],
    ['Medical Records','medical-records'],
    ['Documents','documents'],
    ['Laboratory','lab-orders'],
    ['Prescriptions','prescriptions'],
    ['Vitals','vitals'],
    ['Availability','availability'],
    ['Notifications','notifications'],
    ['Account Security','security']
  ],

  RECEPTIONIST:[
    ['Dashboard','dashboard'],
    ['User Accounts','accounts'],
    ['Patients','patients'],
    ['Appointments','appointments'],
    ['Doctors','doctors'],
    ['Bed Tracker','beds'],
    ['Availability','availability'],
    ['Billing','bills'],
    ['Notifications','notifications']
  ],

  PATIENT:[
    ['Dashboard','dashboard'],
    ['Messages','care-threads'],
    ['My Profile','patients'],
    ['My Appointments','appointments'],
    ['Medical History','medical-records'],
    ['Documents','documents'],
    ['Lab Results','lab-orders'],
    ['Care Team','doctors'],
    ['Prescriptions','prescriptions'],
    ['My Bills','bills'],
    ['Notifications','notifications'],
    ['Account Security','security']
  ]
};

// Pages that load their own data instead of using the generic /<page>/ fetch.
const SELF_LOADING=new Set(['hospitals','pharmacy','vitals','finance','audit-logs','security']);


/* =========================
   MAIN APP
========================= */

function App(){

  const [page,setPage]=useState('dashboard');
  const [me,setMe]=useState(null);
  const [data,setData]=useState([]);
  const [loadedPage,setLoadedPage]=useState(null);
  const [dash,setDash]=useState(null);
  const [calendarAppointments,setCalendarAppointments]=useState([]);
  const [calendarDischarges,setCalendarDischarges]=useState([]);
  const [loading,setLoading]=useState(false);
  const [lastUpdated,setLastUpdated]=useState(null);
  const patientSearch=useRef('');
  const patientDirectoryParams=useRef({q:'',page:1});
  const doctorDirectoryParams=useRef({q:'',page:1});
  const loadRequest=useRef(0);
  const [quickSearch,setQuickSearch]=useState('');

  const [dark,setDark]=useState(
    localStorage.getItem('dark')==='1'
  );

  const navs=me
    ?(NAVS[me.role]||[])
    :[];

  useEffect(()=>{
    api.get('/me/')
      .then(r=>setMe(r.data))
      .catch(logout);
  },[]);

  useEffect(()=>{
    document.body.classList.toggle('dark',dark);

    localStorage.setItem(
      'dark',
      dark?'1':'0'
    );
  },[dark]);

  useEffect(()=>{
    if(me){
      load(page);
    }
  },[page,me]);

  useEffect(()=>{
    if(!me)return;
    const timer=window.setInterval(()=>load(page,{},true),15000);
    return ()=>window.clearInterval(timer);
  },[me,page]);

  async function logout(){
    localStorage.removeItem('token');
    try{await axios.post(`${API}/logout/`,{},{withCredentials:true});}catch{/* session already ended */}
    location.reload();
  }

  async function load(p,params={},background=false){

    const requestId=++loadRequest.current;

    if(p==='patients'){
      if(['ADMIN','RECEPTIONIST','DOCTOR'].includes(me.role)){
        if(Object.keys(params).length)patientDirectoryParams.current=params;
        else params=patientDirectoryParams.current;
      }else if(!Object.keys(params).length&&patientSearch.current){
        params={q:patientSearch.current};
      }
    }else if(p==='doctors'&&['ADMIN','RECEPTIONIST'].includes(me.role)){
      if(Object.keys(params).length)doctorDirectoryParams.current=params;
      else params=doctorDirectoryParams.current;
    }

    if(!background)setLoading(true);

    try{

      if(SELF_LOADING.has(p)){

        if(requestId!==loadRequest.current)return;
        setData([]);

      }else if(p==='dashboard'){

        const [
          dashboardRes,
          appointmentsRes,
          dischargesRes
        ]=await Promise.all([
          api.get('/dashboard/'),
          api.get('/appointments/',{
            params:{}
          }),
          api.get('/discharges/')
        ]);

        if(requestId!==loadRequest.current)return;

        setDash(dashboardRes.data);

        setCalendarAppointments(
          appointmentsRes.data||[]
        );
        setCalendarDischarges(dischargesRes.data||[]);

      }else if(p==='patients'){

        const endpoint=['ADMIN','RECEPTIONIST','DOCTOR'].includes(me.role)?'/patient-directory/':'/patients/';
        const response=await api.get(endpoint,{params});
        if(requestId!==loadRequest.current)return;
        setData(response.data);

      }else if(p==='doctors'&&['ADMIN','RECEPTIONIST'].includes(me.role)){

        const response=await api.get('/doctor-directory/',{params});
        if(requestId!==loadRequest.current)return;
        setData(response.data);

      }else{

        const response=await api.get('/'+p+'/',{params});
        if(requestId!==loadRequest.current)return;
        setData(response.data);

      }

      setLastUpdated(new Date());

    }catch(e){

      if(requestId!==loadRequest.current)return;

      if(p==='dashboard'){

        setDash(null);
        setCalendarAppointments([]);
        setCalendarDischarges([]);

      }else{

        setData([]);

      }

    }finally{

      if(requestId===loadRequest.current){
        setLoadedPage(p);
        setLoading(false);
      }

    }
  }

  async function remove(id){

    if(me?.role!=='ADMIN')return;

    if(confirm('Delete this record?')){

      await api.delete(
        `/${page}/${id}/`
      );

      load(page);
    }
  }

  if(!me){

    return (
      <div className="loading">
        Loading your workspace...
      </div>
    );

  }

  return (
    <div className="app">

      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">+</span>
          <span className="brand-copy"><strong>MedCore <em>HMS</em></strong><small>Better Care &middot; Healthier Tomorrow</small></span>
        </div>
        <div className="role-pill">{ROLE_LABELS[me.role]}</div>
        <nav className="sidebar-nav">
          {navs.map(([label,key])=><button key={key} className={page===key?'active':''} onClick={()=>setPage(key)}>
            <Icon name={NAV_ICONS[key]}/><span>{label}</span>
          </button>)}
        </nav>
        <button className="logout" onClick={logout}><Icon name="logout"/><span>Logout</span></button>
      </aside>

      <main>

        <header className="topbar">
          <form className="top-search" onSubmit={e=>{e.preventDefault();patientSearch.current=quickSearch.trim();patientDirectoryParams.current={q:patientSearch.current,page:1};setPage('patients');load('patients',{q:patientSearch.current,page:1});}}>
            <Icon name="search" size={17}/>
            <input value={quickSearch} onChange={e=>setQuickSearch(e.target.value)} placeholder="Search patient records..." aria-label="Search patients"/>
          </form>
          <div className="topbar-actions">
            <button className="icon-button" title="Notifications" onClick={()=>setPage('notifications')}><Icon name="bell" size={19}/></button>
            <div className="profile-chip"><span className="profile-avatar">{(me.first_name||me.username||'U').slice(0,1).toUpperCase()}</span><span>{me.first_name||me.username}</span><span className="profile-chevron">&#9662;</span></div>
            <button className="icon-button" title={dark?'Switch to light mode':'Switch to dark mode'} onClick={()=>setDark(!dark)}><Icon name="sun" size={19}/></button>
          </div>
        </header>
        {page!=='dashboard'&&<div className="page-heading"><span className="page-heading-icon"><Icon name={NAV_ICONS[page]} size={27}/></span><div><h1>{navs.find(x=>x[1]===page)?.[0]||'Dashboard'}</h1><span className="muted">{ROLE_LABELS[me.role]} workspace</span></div></div>}

        <div className={`live-toolbar ${page==='dashboard'?'dashboard-live-toolbar':''}`}>
          <span className="live-indicator">Live data</span>
          <span className="muted">{lastUpdated?`Updated ${lastUpdated.toLocaleTimeString()}`:'Connecting...'}</span>
          <button className="refresh" onClick={()=>load(page)}><span aria-hidden="true">&#8635;</span> Refresh</button>
        </div>

        {
          loading||loadedPage!==page

          ?(
            <div className="loading">
              Loading...
            </div>
          )

          :page==='dashboard'

          ?(
            <RoleDashboard
              role={me.role}
              d={dash}
              appointments={
                calendarAppointments
              }
              discharges={calendarDischarges}
              setPage={setPage}
              userName={me.first_name||me.username}
            />
          )

          :page==='patients'
          ?(
            <PatientsPage role={me.role} data={data} reload={load}/>
          )

          :(
            <DataPage
              role={me.role}
              page={page}
              rows={data}
              reload={load}
              onDelete={remove}
              me={me}
            />
          )
        }

      </main>

    </div>
  );
}


/* =========================
   ROLE DASHBOARDS
========================= */

function RoleDashboard({
  role,
  d,
  appointments,
  discharges,
  setPage,
  userName
}){

  if(!d)return null;

  if(['SUPER_ADMIN','NURSE','LAB_TECH','PHARMACIST','ACCOUNTANT'].includes(role))
    return <StaffDashboard d={d} role={role} setPage={setPage} userName={userName}/>;

  if(role==='ADMIN')
    return (<>
      <AdminDashboard
        d={d}
        appointments={appointments}
        discharges={discharges}
        setPage={setPage}
        userName={userName}
      />
    </>);

  if(role==='DOCTOR')
    return (<>
      <DoctorInsights d={d} setPage={setPage}/>
      <DoctorDashboard
        d={d}
        appointments={appointments}
        discharges={discharges}
        setPage={setPage}
      />
    </>);

  if(role==='RECEPTIONIST')
    return (
      <ReceptionDashboard
        d={d}
        appointments={appointments}
        discharges={discharges}
        setPage={setPage}
      />
    );

  return (
    <PatientDashboard
      d={d}
      appointments={appointments}
      discharges={discharges}
      setPage={setPage}
    />
  );
}


/* =========================
   STAT CARD
========================= */

const STAT_ICONS={'My Patients':'users','My Appointments':'calendar','Pending':'clock','Completed':'heart','In Progress':'stethoscope','Upcoming':'calendar','Open Slots':'clock','Emergency Cases':'heart','Patient Records':'users','Appointments Today':'calendar','Pending Appointments':'clock','Emergency Flags':'heart','Available Beds':'bed','Pending Bills':'receipt','Appointments':'calendar','Medical Records':'folder','Prescriptions':'pill','Paid Bills':'receipt'};
const Stat=({title,value,icon})=>(
  <div className="card">
    <div className="icon"><Icon name={STAT_ICONS[title]||'grid'} size={25}/></div>
    <div><div className="muted">{title}</div><strong>{value}</strong></div>
  </div>
);

function LiveAppointmentList({title,description,appointments=[],upcomingOnly=false}){
  const currentDate=new Date();
  const today=`${currentDate.getFullYear()}-${String(currentDate.getMonth()+1).padStart(2,'0')}-${String(currentDate.getDate()).padStart(2,'0')}`;
  const visible=(appointments||[])
    .filter(a=>!upcomingOnly||(
      a.date>=today&&['Pending','Confirmed'].includes(a.status)
    ))
    .sort((a,b)=>`${a.date} ${a.time}`.localeCompare(`${b.date} ${b.time}`))
    .slice(0,5);

  return <section className="panel live-list">
    <div>
      <h2>{title}</h2>
      <p className="muted">{description}</p>
    </div>
    {visible.length?<div className="live-list-items">
      {visible.map(a=><div className="live-list-row" key={a.id}>
        <div>
          <strong>{a.patient_name||a.doctor_name||'Appointment'}</strong>
          <span>{a.doctor_name&&a.patient_name?`Dr. ${a.doctor_name}`:''}</span>
        </div>
        <div className="live-list-time">
          <strong>{a.date}</strong>
          <span>{String(a.time||'').slice(0,5)} · {a.status}</span>
        </div>
      </div>)}
    </div>:<p className="empty-inline">No live appointments to show.</p>}
  </section>;
}

/* =========================
   DEPARTMENT BARS
========================= */

function Bars({items}){

  const max=Math.max(
    ...items.map(
      x=>x.workload
    ),
    1
  );

  return (
    <div className="bars">

      {items.map(x=>(
        <div
          className="bar-row"
          key={x.name}
        >

          <span>
            {x.name}
          </span>

          <div>
            <i
              style={{
                width:
                  `${x.workload/max*100}%`
              }}
            />
          </div>

          <b>
            {x.workload}
          </b>

        </div>
      ))}

    </div>
  );
}


/* =========================
   ADMIN DASHBOARD
========================= */

function DashboardMetric({title,value,icon,tone,caption,onClick}){
  const content=<><span className="metric-icon"><Icon name={icon} size={22}/></span><span className="metric-copy"><span className="metric-title">{title}</span><strong>{value}</strong><small>{caption}</small></span></>;
  return onClick?<button className={`dashboard-metric tone-${tone}`} onClick={onClick}>{content}</button>:<div className={`dashboard-metric tone-${tone}`}>{content}</div>;
}

function DashboardRightRail({appointments,setPage}){
  const currentDate=new Date();
  const today=`${currentDate.getFullYear()}-${String(currentDate.getMonth()+1).padStart(2,'0')}-${String(currentDate.getDate()).padStart(2,'0')}`;
  const recent=[...(appointments||[])].sort((a,b)=>String(b.created_at||'').localeCompare(String(a.created_at||''))).slice(0,4);
  const upcoming=(appointments||[]).filter(a=>a.date>=today&&['Pending','Confirmed'].includes(a.status)).sort((a,b)=>`${a.date} ${a.time}`.localeCompare(`${b.date} ${b.time}`)).slice(0,3);
  return <aside className="dashboard-rail">
    <section className="rail-panel activity-panel">
      <div className="rail-heading"><h2><span className="rail-icon cyan"><Icon name="heart" size={17}/></span>Recent Activity</h2><button onClick={()=>setPage('appointments')}>View All</button></div>
      {recent.length?recent.map((a,i)=><div className="activity-item" key={a.id}><span className={`activity-dot dot-${i%4}`}/><span><strong>{a.status} appointment</strong><small>{a.patient_name} &middot; {a.date}</small></span></div>):<p className="empty-inline">No recent appointments.</p>}
    </section>
    <section className="rail-panel upcoming-panel">
      <div className="rail-heading"><h2><span className="rail-icon violet"><Icon name="calendar" size={17}/></span>Upcoming Appointments</h2><button onClick={()=>setPage('appointments')}>View All</button></div>
      {upcoming.length?upcoming.map(a=><button className="upcoming-item" key={a.id} onClick={()=>setPage('appointments')}><span>{String(a.time||'').slice(0,5)}</span><span><strong>{a.patient_name}</strong><small>{a.doctor_name}</small></span><b aria-hidden="true">&rsaquo;</b></button>):<p className="empty-inline">No upcoming appointments.</p>}
    </section>
    <section className="wellness-panel" onClick={()=>setPage('patients')}>
      <div><strong>Small steps<br/>make a big difference.</strong><small>Quality care, every day.</small></div>
      <img src={wellnessHeart} alt="Heart with a health pulse"/>
    </section>
  </aside>;
}

function AdminDashboard({d,appointments,discharges,setPage,userName}){
  const now=new Date();
  const hour=now.getHours();
  const greeting=hour<12?'Good Morning':hour<17?'Good Afternoon':'Good Evening';
  return <>
    <div className="admin-dashboard-grid">
      <div className="admin-dashboard-main">
        <div className="dashboard-greeting"><div><span>{greeting},</span><strong>{userName||'Administrator'} <span role="img" aria-label="hello">👋</span></strong><small>Welcome back to MedCore HMS</small></div><div className="date-chip"><Icon name="calendar" size={19}/><span>{now.toLocaleDateString('en-IN',{weekday:'short',day:'numeric',month:'short',year:'numeric'})}<small>{now.toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit'})}</small></span></div></div>
        <section className="command-hero">
          <div className="hero-copy"><h1>Hospital Command Center</h1><p>Manage people, care, revenue, capacity and hospital workload from one place.</p><div className="hero-points"><span>♡ Better Care</span><span>✧ Higher Efficiency</span><span>◇ Smarter Management</span></div></div>
          <img className="hero-art" src={hospitalHero} alt="Illustration of a modern hospital"/>
          <span className="hero-script">Healing<br/>Together ♡</span>
        </section>
        <AdminInsights d={d} setPage={setPage}/>
        <div className="dashboard-metrics-grid">
          <DashboardMetric title="Departments" value={d.departments} icon="building" tone="mint" caption="Hospital departments" onClick={()=>setPage('departments')}/>
          <DashboardMetric title="Patient Records" value={((d.patients||0)+(d.historical_admissions||0)).toLocaleString()} icon="users" tone="lavender" caption="Profiles and imported visits" onClick={()=>setPage('patients')}/>
          <DashboardMetric title="Doctors" value={Number(d.doctors||0).toLocaleString('en-IN')} icon="stethoscope" tone="sky" caption={`Registered staff; ${Number(d.imported_doctor_names||0).toLocaleString('en-IN')} historical names in archive`} onClick={()=>setPage('doctors')}/>
          <DashboardMetric title="Appointments" value={d.appointments} icon="calendar" tone="peach" caption="Scheduled visits" onClick={()=>setPage('appointments')}/>
          <DashboardMetric title="Emergency" value={d.emergency_patients} icon="heart" tone="rose" caption="Priority patients" onClick={()=>setPage('patients')}/>
        </div>
        <button className="beds-summary" onClick={()=>setPage('beds')}><span className="beds-summary-icon"><Icon name="bed" size={24}/></span><span><small>Beds Available</small><strong>{d.beds_available}/{d.beds_total}</strong></span><span className="beds-progress"><i style={{width:`${d.beds_total?100*(d.beds_total-d.beds_available)/d.beds_total:0}%`}}/></span><small>{d.beds_total?Math.round(100*(d.beds_total-d.beds_available)/d.beds_total):0}% occupied</small></button>
        <section className="quick-access"><div><strong>⚡ Quick Access</strong><small>Jump to key modules</small></div><div className="quick-actions">{[['New Appointment','appointments','calendar'],['View Records','medical-records','folder'],['Billing','bills','receipt'],['Bed Status','beds','bed'],['Departments','departments','building']].map(([label,key,icon])=><button key={key} onClick={()=>setPage(key)}><Icon name={icon} size={17}/>{label}</button>)}</div></section>
      </div>
      <DashboardRightRail appointments={appointments} setPage={setPage}/>
    </div>
    <div className="dashboard-lower">
      <div className="grid2"><section className="panel"><h2>Appointment Status</h2><div className="status-grid"><b>Pending {d.pending_appointments}</b><b>Confirmed {d.confirmed_appointments}</b><b>In Progress {d.in_progress_appointments||0}</b><b>Completed {d.completed_appointments}</b><b>No Show {d.no_show_appointments||0}</b><b>Cancelled {d.cancelled_appointments}</b></div></section><section className="panel"><h2>Department Workload</h2><Bars items={d.department_workload||[]}/></section></div>
      <CalendarGrid appointments={[...appointments,...discharges]} setPage={setPage} title="Care Calendar" description="Appointments and patient discharges by date."/>
    </div>
  </>;
}

/* =========================
   DOCTOR DASHBOARD
========================= */

function CareWorkspaceHeading({heading,text,icon}){
  return <div className="page-heading care-workspace-heading">
    <span className="page-heading-icon"><Icon name={icon} size={27}/></span>
    <div><h1>{heading}</h1><span className="muted">{text}</span></div>
  </div>;
}

function DoctorDashboard({
  d,
  appointments,
  discharges,
  setPage
}){

  return (
    <>
      <CareWorkspaceHeading
        icon="stethoscope"
        heading={`Welcome, Dr. ${d.doctor?.name||'Doctor'}`}
        text={`${d.doctor?.department_name||d.doctor?.specialization||'Clinical workspace'} · Focus on your patients, records and appointment slots.`}
      />

      <div className="care-workspace-metrics">

        <Stat
          title="My Patients"
          value={d.patients}
          icon="👥"
        />

        <Stat
          title="My Appointments"
          value={d.appointments}
          icon="📅"
        />

        <Stat
          title="Pending"
          value={d.pending_appointments}
          icon="⏳"
        />

        <Stat
          title="Completed"
          value={d.completed_appointments}
          icon="✓"
        />

        <Stat title="In Progress" value={d.in_progress_appointments||0} icon="🩺"/>

        <Stat
          title="Upcoming"
          value={d.upcoming_appointments}
          icon="🗓"
        />

        <Stat
          title="Open Slots"
          value={d.available_slots}
          icon="🕐"
        />

        <Stat
          title="Emergency Cases"
          value={d.emergency_patients}
          icon="🚨"
        />

      </div>

      <LiveAppointmentList
        title="My consultation queue"
        description="Only appointments assigned to your doctor profile."
        appointments={appointments}
      />

      <CalendarGrid
        appointments={[...appointments,...discharges]}
        setPage={setPage}
        title="My Care Calendar"
        description="Your appointments and patient discharges by date."
      />

    </>
  );
}


/* =========================
   RECEPTION DASHBOARD
========================= */

function ReceptionDashboard({
  d,
  appointments,
  discharges,
  setPage
}){

  return (
    <>
      <Banner
        cls="reception-banner"
        title="RECEPTION DESK"
        heading="Patient Flow & Front Office"
        text="Coordinate arrivals, appointments, beds, payments and urgent cases."
      />

      <div className="cards">

        <Stat
          title="Patient Records"
          value={((d.patients||0)+(d.historical_admissions||0)).toLocaleString()}
          icon="👥"
        />

        <Stat
          title="Appointments Today"
          value={d.appointments_today}
          icon="📅"
        />

        <Stat
          title="Pending Appointments"
          value={d.pending_appointments}
          icon="⏳"
        />

        <Stat
          title="Emergency Flags"
          value={d.emergency_patients}
          icon="🚨"
        />

        <Stat
          title="Available Beds"
          value={d.beds_available}
          icon="🛏"
        />

        <Stat
          title="Pending Bills"
          value={`₹${d.pending_bills.toLocaleString()}`}
          icon="₹"
        />

      </div>


      <CalendarGrid
        appointments={[...appointments,...discharges]}
        setPage={setPage}
        title="Care Calendar"
        description="Appointments and patient discharges by date."
      />

    </>
  );
}


/* =========================
   PATIENT DASHBOARD
========================= */

function PatientDashboard({
  d,
  appointments,
  setPage
}){

  const p=d.patient||{};

  return (
    <>
      <CareWorkspaceHeading
        icon="user"
        heading={`Welcome, ${p.full_name||'Patient'}`}
        text={`Patient ID: ${p.patient_id||'-'} · Your private care timeline, appointments, prescriptions and bills.`}
      />

      {p.emergency_priority&&(
        <div className="alert">
          🚨 Emergency priority flag is active on your record. Please inform reception immediately if symptoms worsen.
        </div>
      )}

      <div className="care-workspace-metrics">

        <Stat
          title="Appointments"
          value={d.appointments}
          icon="📅"
        />

        <Stat
          title="Upcoming"
          value={d.upcoming_appointments}
          icon="🗓"
        />

        <Stat
          title="Medical Records"
          value={d.medical_records}
          icon="📋"
        />

        <Stat
          title="Prescriptions"
          value={d.prescriptions}
          icon="💊"
        />

        <Stat
          title="Paid Bills"
          value={`₹${d.paid_total.toLocaleString()}`}
          icon="✓"
        />

        <Stat
          title="Pending Bills"
          value={`₹${d.pending_total.toLocaleString()}`}
          icon="₹"
        />

      </div>

      <LiveAppointmentList
        title="My upcoming care"
        description="Your confirmed and pending visits, shown from your private record."
        appointments={appointments}
        upcomingOnly
      />

      <CalendarGrid
        appointments={appointments}
        setPage={setPage}
      />

    </>
  );
}


/* =========================
   CALENDAR
========================= */

function CalendarGrid({
  appointments=[],
  setPage,
  title='Appointment Calendar',
  description='View scheduled appointments by date. Click a day to open the appointment list.',
  itemLabel='appointment',
  targetPage='appointments'
}){

  const [month,setMonth]=useState(
    ()=>new Date(
      new Date().getFullYear(),
      new Date().getMonth(),
      1
    )
  );

  const year=month.getFullYear();
  const monthIndex=month.getMonth();

  const firstDay=
    new Date(
      year,
      monthIndex,
      1
    ).getDay();

  const daysInMonth=
    new Date(
      year,
      monthIndex+1,
      0
    ).getDate();

  const cells=[];

  for(
    let i=0;
    i<firstDay;
    i++
  ){
    cells.push(null);
  }

  for(
    let day=1;
    day<=daysInMonth;
    day++
  ){
    cells.push(day);
  }

  while(
    cells.length%7!==0
  ){
    cells.push(null);
  }

  const byDate={};

  (appointments||[]).forEach(a=>{

    if(!a.date)return;

    (byDate[a.date] ||=
      []).push(a);

  });

  const todayKey=
    new Date()
      .toISOString()
      .slice(0,10);

  const monthLabel=
    month.toLocaleDateString(
      'en-IN',
      {
        month:'long',
        year:'numeric'
      }
    );

  const go=(delta)=>
    setMonth(
      new Date(
        year,
        monthIndex+delta,
        1
      )
    );

  return (
    <section className="panel dashboard-calendar">

      <div className="calendar-header">

        <div>

          <h2>
            {title}
          </h2>

          <p className="muted">
            {description}
          </p>

        </div>

        <div className="calendar-controls">

          <button
            onClick={()=>
              go(-1)
            }
          >
            ‹
          </button>

          <button
            className="today-btn"
            onClick={()=>
              setMonth(
                new Date(
                  new Date().getFullYear(),
                  new Date().getMonth(),
                  1
                )
              )
            }
          >
            Today
          </button>

          <strong>
            {monthLabel}
          </strong>

          <button
            onClick={()=>
              go(1)
            }
          >
            ›
          </button>

        </div>

      </div>

      <div className="calendar-weekdays">

        {[
          'Sun',
          'Mon',
          'Tue',
          'Wed',
          'Thu',
          'Fri',
          'Sat'
        ].map(d=>(
          <div key={d}>
            {d}
          </div>
        ))}

      </div>

      <div className="calendar-grid">

        {cells.map((day,i)=>{

          if(!day){

            return (
              <div
                className="calendar-cell empty-cell"
                key={`empty-${i}`}
              />
            );

          }

          const iso=
            `${year}-${String(monthIndex+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;

          const items=
            byDate[iso]||[];

          const dischargeCount=items.filter(
            item=>item.status==='Discharged'
          ).length;

          return (

            <button
              className={
                `calendar-cell ${
                  iso===todayKey
                    ?'today'
                    :''
                }`
              }
              key={iso}
              onClick={()=>
                setPage(targetPage)
              }
            >

              <span className="day-number">
                {day}
              </span>

              {items.length>0&&(

                <div className="calendar-events">

                  <span className="event-count">
                    {dischargeCount===items.length
                      ?`${dischargeCount} discharged`
                      :`${items.length} ${items.length===1?'event':'events'}`}
                  </span>

                  {items
                    .slice(0,2)
                    .map((a,j)=>(

                      <span
                        className={
                          `event-status status-${
                            String(
                              a.status||''
                            ).toLowerCase().replaceAll(' ','-')
                          }`
                        }
                        key={`${a.status}-${a.id??j}`}
                      >
                        {a.status==='Discharged'
                          ?'Discharged · '
                          :`${String(a.time||'').slice(0,5)} `}
                        {a.patient_name||
                          a.doctor_name||
                          'Appointment'}
                      </span>

                    ))}

                  {items.length>2&&(

                    <span className="more-events">
                      +{items.length-2} more
                    </span>

                  )}

                </div>

              )}

            </button>

          );

        })}

      </div>

    </section>
  );
}


/* =========================
   BANNER
========================= */

const Banner=({
  cls,
  title,
  heading,
  text
})=>(
  <div
    className={
      `dashboard-banner ${cls}`
    }
  >

    <span>
      {title}
    </span>

    <h2>
      {heading}
    </h2>

    <p>
      {text}
    </p>

  </div>
);


/* =========================
   DATA PAGE
========================= */

function DataPage({
  role,
  page,
  rows,
  reload,
  onDelete,
  me
}){
  if(page==='hospitals')return <Hospitals api={api}/>;
  if(page==='pharmacy')return <Pharmacy api={api} role={role}/>;
  if(page==='vitals')return <Vitals api={api} role={role}/>;
  if(page==='finance')return <Finance api={api} role={role}/>;
  if(page==='audit-logs')return <AuditLog api={api}/>;
  if(page==='security')return <AccountSecurity api={api} me={me}/>;
  if(page==='care-threads')return <CareMessages api={api} me={me}/>;
  if(page==='integration-status')return <ServiceSetup api={api}/>;
  if(page==='notifications'&&role==='PATIENT')return <><ReminderPreferences api={api}/><Table role={role} page={page} rows={rows}/></>;

  if(page==='documents')return <Documents api={api}/>;
  if(page==='lab-orders')return <Laboratory api={api} role={role}/>;
  if(page==='doctors')return <><DoctorProfiles api={api} role={role}/>{['ADMIN','RECEPTIONIST'].includes(role)&&<details className="portal-details"><summary>Historical doctor names from imported visits</summary><DoctorDirectory role={role} data={rows} reload={reload} onDelete={onDelete}/></details>}</>;
  if(page==='appointments')
    return (
      <AppointmentExplorer
        role={role}
        rows={rows}
        reload={reload}
        me={me}
      />
    );

  if(page==='accounts')
    return <AccountManager rows={rows} reload={reload} role={role}/>;

  if(page==='medical-records')
    return (
      <TimelineRecords
        role={role}
        rows={rows}
        reload={reload}
      />
    );

  if(page==='prescriptions')
    return <PrescriptionsPage role={role} rows={rows} reload={reload} onDelete={onDelete}/>;

  if(page==='bills')
    return <BillingPage role={role} rows={rows} reload={reload} onDelete={onDelete}/>;

  if(page==='departments')
    return <DepartmentsPage role={role} rows={rows} reload={reload} onDelete={onDelete}/>;

  if(page==='doctors'&&['ADMIN','RECEPTIONIST'].includes(role))
    return <DoctorDirectory role={role} data={rows} reload={reload} onDelete={onDelete}/>;

  if(page==='beds')
    return (
      <BedTracker
        rows={rows}
        reload={reload}
      />
    );

  if(page==='availability')
    return <AvailabilityPage role={role} rows={rows} reload={reload}/>;

  return (
    <Table
      role={role}
      page={page}
      rows={rows}
      onDelete={onDelete}
    />
  );
}

function AccountManager({rows,reload,role}){
  const [departments,setDepartments]=useState([]);
  useEffect(()=>{api.get('/departments/').then(r=>setDepartments(r.data)).catch(()=>setError('Could not load departments.'));},[]);
  const [form,setForm]=useState({username:'',password:'',first_name:'',last_name:'',email:'',phone:'',role:'DOCTOR',doctor_id:'',specialization:'',patient_id:'',full_name:'',gender:'Other',primary_concern:''});
  const [error,setError]=useState('');
  const [created,setCreated]=useState(null);
  const [saving,setSaving]=useState(false);
  const update=(key,value)=>setForm({...form,[key]:value});
  const submit=async e=>{
    e.preventDefault();setError('');setCreated(null);setSaving(true);
    try{const credentials={username:form.username,password:form.password,role:form.role};await api.post('/accounts/',form);setCreated(credentials);setForm({...form,username:'',password:'',first_name:'',last_name:'',email:'',phone:'',doctor_id:'',specialization:'',patient_id:'',full_name:'',primary_concern:''});reload('accounts');}
    catch(e){setError(e.response?.data?.detail||'Could not create this account. Check that the username and ID are unique.');}
    finally{setSaving(false);}
  };
  return <>
    <section className="panel">
      <h2>Create login account</h2>
      <p className="muted">Create separate credentials for doctors and patients. Passwords are not shown again after saving.</p>
      <form className="account-form" onSubmit={submit}>
        <input required placeholder="Username" value={form.username} onChange={e=>update('username',e.target.value)}/>
        <input required minLength="8" type="password" placeholder="Temporary password (8+ characters)" value={form.password} onChange={e=>update('password',e.target.value)}/>
        <input placeholder="First name" value={form.first_name} onChange={e=>update('first_name',e.target.value)}/>
        <input placeholder="Last name" value={form.last_name} onChange={e=>update('last_name',e.target.value)}/>
        <input type="email" placeholder="Email (optional)" value={form.email} onChange={e=>update('email',e.target.value)}/>
        <select value={form.role} onChange={e=>update('role',e.target.value)}>
          <option value="DOCTOR">Doctor</option><option value="PATIENT">Patient</option>{role==='ADMIN'&&['RECEPTIONIST','NURSE','LAB_TECH','PHARMACIST','ACCOUNTANT'].map(r=><option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
        </select>
        {form.role==='DOCTOR'&&<><input required placeholder="Unique Doctor ID (e.g. DOC-105)" value={form.doctor_id} onChange={e=>update('doctor_id',e.target.value)}/><input required placeholder="Specialization" value={form.specialization} onChange={e=>update('specialization',e.target.value)}/><select aria-label="Assigned department" value={form.department||''} onChange={e=>update('department',e.target.value)}><option value="">Department not assigned</option>{departments.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></>}
        {form.role==='PATIENT'&&<><input required placeholder="Patient ID (e.g. PAT-101)" value={form.patient_id} onChange={e=>update('patient_id',e.target.value)}/><input required placeholder="Phone" value={form.phone} onChange={e=>update('phone',e.target.value)}/><input placeholder="Full name" value={form.full_name} onChange={e=>update('full_name',e.target.value)}/><select value={form.gender} onChange={e=>update('gender',e.target.value)}><option>Other</option><option>Female</option><option>Male</option></select><input className="full-field" placeholder="Primary concern (e.g. fever, back pain)" value={form.primary_concern} onChange={e=>update('primary_concern',e.target.value)}/></>}
        {error&&<div className="error">{error}</div>}
        {created&&<div className="success">Account created — give <b>{created.username}</b> the temporary password <b>{created.password}</b> for {created.role.toLowerCase()} login.</div>}
        <button className="primary" disabled={saving}>{saving?'Creating…':'Create account'}</button>
      </form>
    </section>
    <section className="panel"><h2>Existing login accounts</h2><div className="account-list">{rows.map(u=><div key={u.id}><strong>{u.username}</strong><span>{u.first_name} {u.last_name} · {ROLE_LABELS[u.role]}</span></div>)}{!rows.length&&<p className="empty-inline">No accounts created yet.</p>}</div></section>
  </>;
}


/* =========================
   APPOINTMENTS
========================= */

function AppointmentExplorer({
  role,
  rows,
  reload,
  me
}){

  const [q,setQ]=useState('');
  const [date,setDate]=useState('');
  const [status,setStatus]=useState('');
  const [showCreate,setShowCreate]=useState(false);

  return (
    <section className="panel">

      <div className="toolbar filters">

        <input
          placeholder="Search patient ID, phone or doctor"
          value={q}
          onChange={e=>
            setQ(e.target.value)
          }
        />

        <input
          type="date"
          value={date}
          onChange={e=>
            setDate(e.target.value)
          }
        />

        <select
          value={status}
          onChange={e=>
            setStatus(e.target.value)
          }
        >

          <option value="">
            All statuses
          </option>

          {[
            'Pending',
            'Confirmed',
            'In Progress',
            'Completed',
            'Cancelled',
            'No Show'
          ].map(s=>(
            <option key={s}>
              {s}
            </option>
          ))}

        </select>

        <button
          className="primary"
          onClick={()=>
            reload(
              'appointments',
              {
                q,
                date,
                status
              }
            )
          }
        >
          Apply
        </button>

        {(
          <button className="primary" onClick={()=>setShowCreate(!showCreate)}>
            {showCreate?'Close':'New appointment'}
          </button>
        )}

      </div>

      {showCreate&&(
        <AppointmentForm
          role={role}
          onSaved={()=>{
            setShowCreate(false);
            reload('appointments',{q,date,status});
          }}
        />
      )}

      <div className="calendar-strip">

        {[0,1,2,3,4,5,6].map(i=>{

          const d=new Date();

          d.setDate(
            d.getDate()+i
          );

          const iso=
            d.toISOString()
             .slice(0,10);

          return (

            <button
              key={iso}
              onClick={()=>{
                setDate(iso);

                reload(
                  'appointments',
                  {
                    q,
                    status,
                    date:iso
                  }
                );
              }}
            >

              <b>
                {d.toLocaleDateString(
                  'en-IN',
                  {
                    weekday:'short'
                  }
                )}
              </b>

              <span>
                {d.getDate()}
              </span>

            </button>

          );

        })}

      </div>

      <Table
        role={role}
        page="appointments"
        rows={rows}
      />

      <RescheduleAppointments api={api} role={role} rows={rows} onSaved={()=>reload('appointments',{q,date,status})}/>
      {role!=='PATIENT'&&<AppointmentActions role={role} rows={rows} reload={()=>reload('appointments',{q,date,status},true)}/>}

    </section>
  );
}

function AppointmentForm({role,onSaved}){
  const [patients,setPatients]=useState([]);
  const [doctors,setDoctors]=useState([]);
  const [error,setError]=useState('');
  const [saving,setSaving]=useState(false);
  const [form,setForm]=useState({patient:'',doctor:'',date:'',time:'',reason:''});

  useEffect(()=>{
    Promise.all([api.get('/patients/'),api.get('/doctors/')])
      .then(([p,d])=>{setPatients(p.data||[]);setDoctors(d.data||[]);})
      .catch(()=>setError('Could not load patients and doctors.'));
  },[]);

  const submit=async e=>{
    e.preventDefault();setError('');setSaving(true);
    try{
      const payload={...form};
      if(role==='DOCTOR')delete payload.doctor;
      if(role==='PATIENT')delete payload.patient;
      await api.post('/appointments/',payload);
      onSaved();
    }catch(e){setError(Object.values(e.response?.data||{}).flat().join(' ')||'Could not book this appointment.');}
    finally{setSaving(false);}
  };

  return <form className="live-form" onSubmit={submit}>
    <h2>Schedule appointment</h2>
    {role!=='PATIENT'&&<select required value={form.patient} onChange={e=>setForm({...form,patient:e.target.value})}>
      <option value="">Select patient</option>
      {patients.map(p=><option key={p.id} value={p.id}>{p.full_name} ({p.patient_id})</option>)}
    </select>}
    {role!=='DOCTOR'&&<select required value={form.doctor} onChange={e=>setForm({...form,doctor:e.target.value})}>
      <option value="">Select doctor</option>
      {doctors.map(d=><option key={d.id} value={d.id}>{d.name} — {d.specialization}</option>)}
    </select>}
    <input required type="date" value={form.date} onChange={e=>setForm({...form,date:e.target.value})}/>
    <input required type="time" value={form.time} onChange={e=>setForm({...form,time:e.target.value})}/>
    <input placeholder="Reason for visit" value={form.reason} onChange={e=>setForm({...form,reason:e.target.value})}/>
    <p className="muted">New appointments start as Pending. Staff will confirm the booking.</p>
    {error&&<div className="error">{error}</div>}
    <button className="primary" disabled={saving}>{saving?'Saving…':'Save appointment'}</button>
  </form>;
}

function AvailabilityPage({role,rows,reload}){
  const [doctors,setDoctors]=useState([]);
  const [form,setForm]=useState({doctor:'',date:'',start_time:'',end_time:'',is_available:true});
  const [error,setError]=useState('');
  const [saving,setSaving]=useState(false);
  useEffect(()=>{
    if(role!=='DOCTOR')api.get('/doctors/').then(r=>setDoctors(r.data||[])).catch(()=>setError('Could not load doctors.'));
  },[role]);
  const save=async e=>{
    e.preventDefault();setSaving(true);setError('');
    try{
      const payload={...form};
      if(role==='DOCTOR')delete payload.doctor;
      await api.post('/availability/',payload);
      setForm({...form,date:'',start_time:'',end_time:''});
      reload('availability');
    }catch(e){setError(Object.values(e.response?.data||{}).flat().join(' ')||'Could not save availability.');}
    finally{setSaving(false);}
  };
  return <>
    {role!=='PATIENT'&&<section className="panel">
      <h2>Set doctor availability</h2>
      <p className="muted">Appointments must fall within these hours when a doctor has availability set for the selected date.</p>
      <form className="live-form" onSubmit={save}>
        {role!=='DOCTOR'&&<select required value={form.doctor} onChange={e=>setForm({...form,doctor:e.target.value})}><option value="">Select doctor</option>{doctors.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select>}
        <input required type="date" value={form.date} onChange={e=>setForm({...form,date:e.target.value})}/>
        <input required type="time" value={form.start_time} onChange={e=>setForm({...form,start_time:e.target.value})}/>
        <input required type="time" value={form.end_time} onChange={e=>setForm({...form,end_time:e.target.value})}/>
        <label><input type="checkbox" checked={form.is_available} onChange={e=>setForm({...form,is_available:e.target.checked})}/> Available for bookings</label>
        {error&&<div className="error">{error}</div>}
        <button className="primary" disabled={saving}>{saving?'Saving…':'Save availability'}</button>
      </form>
    </section>}
    <Table role={role} page="availability" rows={rows}/>
  </>;
}

function AppointmentActions({role,rows,reload}){
  const [error,setError]=useState('');
  const [notice,setNotice]=useState(null);
  const [updating,setUpdating]=useState(null);
  const next={Pending:[['Confirm','Confirmed'],['Cancel','Cancelled']],Confirmed:[['Start','In Progress'],['No show','No Show'],['Cancel','Cancelled']],'In Progress':[['Complete','Completed']]};
  const active=(rows||[]).filter(row=>next[row.status]&&(role!=='RECEPTIONIST'||row.status!=='In Progress')).slice(0,12);
  useEffect(()=>{
    if(!notice)return;
    const timer=window.setTimeout(()=>setNotice(null),4000);
    return ()=>window.clearTimeout(timer);
  },[notice]);
  const advance=async(row,status)=>{
    setError('');
    setUpdating(row.id);
    try{
      await api.patch(`/appointments/${row.id}/`,{status});
      setNotice({type:'success',title:'Appointment updated',message:`${row.patient_name}'s appointment is now ${status}.`});
      await reload();
    }catch(e){
      const message=Object.values(e.response?.data||{}).flat().join(' ')||'Could not update appointment.';
      setError(message);
      setNotice({type:'error',title:'Update failed',message});
    }finally{
      setUpdating(null);
    }
  };
  return <div className="appointment-actions">
    {notice&&<div className={`workflow-popup ${notice.type}`} role="status" aria-live="polite">
      <span className="workflow-popup-icon">{notice.type==='success'?'✓':'!'}</span>
      <span><strong>{notice.title}</strong><small>{notice.message}</small></span>
      <button aria-label="Close notification" onClick={()=>setNotice(null)}>×</button>
    </div>}
    <h2>Appointment workflow</h2>
    <p className="muted">Confirm bookings, start encounters, and complete visits in order.</p>
    {error&&<p className="error">{error}</p>}
    {active.map(row=><div className="workflow-row" key={row.id}>
      <span><strong>{row.patient_name}</strong> · {row.doctor_name} · {row.date} {String(row.time).slice(0,5)} · {row.status}</span>
      <span>{next[row.status].filter(([,status])=>role!=='RECEPTIONIST'||!['In Progress','Completed'].includes(status)).map(([label,status])=><button key={status} disabled={updating===row.id} onClick={()=>advance(row,status)}>{updating===row.id?'Updating...':label}</button>)}</span>
    </div>)}
    {!active.length&&<p className="empty-inline">No appointments need action.</p>}
  </div>;
}


/* =========================
   MEDICAL RECORDS
========================= */

function TimelineRecords({
  role,
  rows,
  reload
}){

  const [appointments,setAppointments]=useState([]);
  const [appointment,setAppointment]=useState('');
  const [diagnosis,setDiagnosis]=useState('');
  const [symptoms,setSymptoms]=useState('');
  const [treatment,setTreatment]=useState('');
  const [notes,setNotes]=useState('');
  const [showCreate,setShowCreate]=useState(false);
  const [error,setError]=useState('');
  const [saving,setSaving]=useState(false);
  const [clinical,setClinical]=useState({});
  useEffect(()=>{
    if(role==='ADMIN'){
      const recorded=new Set((rows||[]).map(record=>record.appointment));
      api.get('/appointments/').then(r=>setAppointments((r.data||[]).filter(a=>['Confirmed','In Progress'].includes(a.status)&&!recorded.has(a.id)))).catch(()=>setError('Could not load appointments.'));
    }
  },[role,rows]);
  const save=async e=>{
    e.preventDefault();setSaving(true);setError('');
    try{
      const extra=Object.fromEntries(Object.entries(clinical).filter(([,v])=>v!==''&&v!==undefined));
      await api.post('/medical-records/',{appointment,diagnosis,symptoms,treatment,notes,...extra},{headers:{'Content-Type':'application/json'}});
      setAppointment('');setDiagnosis('');setSymptoms('');setTreatment('');setNotes('');setClinical({});
      setAppointments(appointments.filter(a=>String(a.id)!==String(appointment)));
      setShowCreate(false);
      reload('medical-records');
    }catch(e){setError(Object.values(e.response?.data||{}).flat().join(' ')||'Could not save medical record.');}
    finally{setSaving(false);}
  };

  return (
    <>
      {role==='ADMIN'&&<section className="panel">
        <div className="module-create-heading"><div><h2>Medical records</h2><p className="muted">Create an encounter record from a confirmed appointment.</p></div><button className="primary" onClick={()=>setShowCreate(!showCreate)}>{showCreate?'Close':'New medical record'}</button></div>
        {showCreate&&<form className="live-form" onSubmit={save}>
          <select required value={appointment} onChange={e=>setAppointment(e.target.value)}><option value="">Select appointment</option>{appointments.map(a=><option key={a.id} value={a.id}>{a.date} · {a.patient_name} · {a.status}</option>)}</select>
          <input required placeholder="Diagnosis" value={diagnosis} onChange={e=>setDiagnosis(e.target.value)}/>
          <input placeholder="Symptoms" value={symptoms} onChange={e=>setSymptoms(e.target.value)}/>
          <input placeholder="Treatment plan" value={treatment} onChange={e=>setTreatment(e.target.value)}/>
          <input placeholder="Clinical notes" value={notes} onChange={e=>setNotes(e.target.value)}/>
          {[['icd10_code','ICD-10 code','text'],['blood_pressure','Blood pressure (e.g. 120/80)','text'],['pulse','Pulse (bpm)','number'],['temperature','Temperature (°C)','number'],['spo2','SpO2 (%)','number'],['height_cm','Height (cm)','number'],['weight_kg','Weight (kg)','number'],['adverse_reactions','Allergies / adverse drug reactions','text']].map(([key,label,type])=>
            <input key={key} type={type} step="any" min={type==='number'?0:undefined} placeholder={label} aria-label={label} value={clinical[key]||''} onChange={e=>setClinical({...clinical,[key]:e.target.value})}/>)}
          <fieldset className="form-field"><legend>Family history</legend>{['diabetes','hypertension','cancer','cardiac'].map(flag=><label key={flag}><input type="checkbox" checked={!!clinical.family_history?.[flag]} onChange={e=>setClinical({...clinical,family_history:{...(clinical.family_history||{}),[flag]:e.target.checked}})}/> {flag}</label>)}</fieldset>
          {error&&<div className="error">{error}</div>}
          <button className="primary" disabled={saving}>{saving?'Saving…':'Save record'}</button>
        </form>}
        {showCreate&&!appointments.length&&<p className="muted">No confirmed appointments are ready for a new record.</p>}
      </section>}
      <Table
        role={role}
        page="medical-records"
        rows={rows}
      />
      <RecordClinicalDetails rows={rows}/>

      {role!=='PATIENT'&&(

        <section className="panel">

          <h2>
            Patient Medical Timeline
          </h2>

          <p className="muted">
            Use the patient-specific view to follow diagnoses, symptoms and treatments chronologically.
          </p>

        </section>

      )}

    </>
  );
}

function formError(error,fallback){
  const detail=error.response?.data;
  if(typeof detail==='string')return detail;
  const message=Object.values(detail||{}).flat().join(' ');
  return message||fallback;
}

function PrescriptionsPage({role,rows,reload,onDelete}){
  const canCreate=role==='ADMIN';
  const [showCreate,setShowCreate]=useState(false);
  const [records,setRecords]=useState([]);
  const [form,setForm]=useState({record:'',medicine:'',dosage:'',frequency:'',duration:'',instructions:''});
  const [error,setError]=useState('');
  const [saving,setSaving]=useState(false);
  useEffect(()=>{
    if(canCreate)api.get('/medical-records/').then(r=>setRecords((r.data||[]).filter(record=>record.source==='Clinical'))).catch(()=>setError('Could not load medical records.'));
  },[canCreate,rows]);
  const update=(key,value)=>setForm({...form,[key]:value});
  const save=async e=>{
    e.preventDefault();setSaving(true);setError('');
    try{
      await api.post('/prescriptions/',form);
      setForm({record:'',medicine:'',dosage:'',frequency:'',duration:'',instructions:''});
      setShowCreate(false);
      reload('prescriptions');
    }catch(err){setError(formError(err,'Could not save prescription.'));}
    finally{setSaving(false);}
  };
  return <>
    {canCreate&&<section className="panel">
      <div className="module-create-heading"><div><h2>Prescriptions</h2><p className="muted">Add medication to an existing medical record.</p></div><button className="primary" onClick={()=>setShowCreate(!showCreate)}>{showCreate?'Close':'New prescription'}</button></div>
      {showCreate&&<form className="live-form" onSubmit={save}>
        <select required value={form.record} onChange={e=>update('record',e.target.value)}><option value="">Select medical record</option>{records.map(record=><option key={record.id} value={record.id}>#{record.id} · {record.patient} · {record.diagnosis}</option>)}</select>
        <input required placeholder="Medicine" value={form.medicine} onChange={e=>update('medicine',e.target.value)}/>
        <input required placeholder="Dosage" value={form.dosage} onChange={e=>update('dosage',e.target.value)}/>
        <input required placeholder="Frequency" value={form.frequency} onChange={e=>update('frequency',e.target.value)}/>
        <input required placeholder="Duration" value={form.duration} onChange={e=>update('duration',e.target.value)}/>
        <textarea placeholder="Instructions (optional)" value={form.instructions} onChange={e=>update('instructions',e.target.value)}/>
        {error&&<div className="error">{error}</div>}
        <button className="primary" disabled={saving||!records.length}>{saving?'Saving…':'Save prescription'}</button>
      </form>}
      {showCreate&&!records.length&&<p className="muted">Create a medical record before adding a prescription.</p>}
    </section>}
    <Table role={role} page="prescriptions" rows={rows} onDelete={onDelete}/>
    <PrescriptionPrint api={api} rows={rows}/>
  </>;
}

function BillingPage({role,rows,reload,onDelete}){
  const canCreate=['ADMIN','ACCOUNTANT','RECEPTIONIST'].includes(role);
  const [showCreate,setShowCreate]=useState(false);
  const [patients,setPatients]=useState([]);
  const [appointments,setAppointments]=useState([]);
  const initial={patient:'',appointment:'',consultation_fee:'0.00',medicine_charges:'0.00',lab_charges:'0.00',other_charges:'0.00',status:'Pending'};
  const [form,setForm]=useState(initial);
  const [error,setError]=useState('');
  const [saving,setSaving]=useState(false);
  useEffect(()=>{
    if(canCreate)Promise.all([api.get('/patients/'),api.get('/appointments/')])
      .then(([p,a])=>{setPatients(p.data||[]);setAppointments(a.data||[]);})
      .catch(()=>setError('Could not load patients or appointments.'));
  },[canCreate]);
  const update=(key,value)=>setForm({...form,[key]:value});
  const save=async e=>{
    e.preventDefault();setSaving(true);setError('');
    try{
      const {appointment,...fields}=form;
      await api.post('/bills/',appointment?{...fields,appointment}:fields);
      setForm(initial);setShowCreate(false);reload('bills');
    }catch(err){setError(formError(err,'Could not save bill.'));}
    finally{setSaving(false);}
  };
  return <>
    {canCreate&&<section className="panel">
      <div className="module-create-heading"><div><h2>Billing</h2><p className="muted">Create a patient bill. Total is calculated from the charges.</p></div><button className="primary" onClick={()=>setShowCreate(!showCreate)}>{showCreate?'Close':'New bill'}</button></div>
      {showCreate&&<form className="live-form" onSubmit={save}>
        <select required value={form.patient} onChange={e=>setForm({...form,patient:e.target.value,appointment:''})}><option value="">Select patient</option>{patients.map(p=><option key={p.id} value={p.id}>{p.full_name} ({p.patient_id})</option>)}</select>
        <select value={form.appointment} onChange={e=>update('appointment',e.target.value)}><option value="">No linked appointment</option>{appointments.filter(a=>String(a.patient)===String(form.patient)).map(a=><option key={a.id} value={a.id}>{a.date} · {a.doctor_name}</option>)}</select>
        {['consultation_fee','medicine_charges','lab_charges','other_charges'].map(key=><label className="form-field" key={key}>{key.replaceAll('_',' ')}<input required type="number" min="0" step="0.01" value={form[key]} onChange={e=>update(key,e.target.value)}/></label>)}
        <select value={form.status} onChange={e=>update('status',e.target.value)}><option>Pending</option><option>Paid</option><option>Cancelled</option></select>
        {error&&<div className="error">{error}</div>}
        <button className="primary" disabled={saving||!patients.length}>{saving?'Saving…':'Save bill'}</button>
      </form>}
    </section>}
    {['ADMIN','PATIENT'].includes(role)&&<BillPayments api={api} rows={rows} reload={reload}/>}
    <Table role={role} page="bills" rows={rows} onDelete={onDelete}/>
  </>;
}

function DepartmentsPage({role,rows,reload,onDelete}){
  const [showCreate,setShowCreate]=useState(false);
  const [name,setName]=useState('');
  const [description,setDescription]=useState('');
  const [error,setError]=useState('');
  const [saving,setSaving]=useState(false);
  const save=async e=>{
    e.preventDefault();setSaving(true);setError('');
    try{
      await api.post('/departments/',{name:name.trim(),description:description.trim()});
      setName('');setDescription('');setShowCreate(false);reload('departments');
    }catch(err){setError(formError(err,'Could not save department.'));}
    finally{setSaving(false);}
  };
  return <>
    {role==='ADMIN'&&<section className="panel">
      <div className="module-create-heading"><div><h2>Departments</h2><p className="muted">Add a department for hospital staff and workload tracking.</p></div><button className="primary" onClick={()=>setShowCreate(!showCreate)}>{showCreate?'Close':'New department'}</button></div>
      {showCreate&&<form className="live-form" onSubmit={save}>
        <input required maxLength={100} placeholder="Department name" value={name} onChange={e=>setName(e.target.value)}/>
        <textarea placeholder="Description (optional)" value={description} onChange={e=>setDescription(e.target.value)}/>
        {error&&<div className="error">{error}</div>}
        <button className="primary" disabled={saving}>{saving?'Saving…':'Save department'}</button>
      </form>}
    </section>}
    <Table role={role} page="departments" rows={rows} onDelete={onDelete}/>
  </>;
}


/* =========================
   BED TRACKER
========================= */

function BedTracker({rows}){
  const counts=useMemo(()=>rows.reduce((acc,row)=>({...acc,[row.status]:(acc[row.status]||0)+1}),{}),[rows]);
  const [status,setStatus]=useState('');
  return <>
    <div className="bed-metrics">
      {[['Available','bed','sky','Beds are available'],['Occupied','user','peach','Beds are occupied'],['Cleaning','sparkles','mint','Beds are being cleaned'],['Reserved','pin','rose','Beds are reserved']].map(([name,icon,tone,caption])=>
        <button key={name} className={`dashboard-metric tone-${tone} ${status===name?'metric-selected':''}`} aria-pressed={status===name} onClick={()=>setStatus(status===name?'':name)}>
          <span className="metric-icon"><Icon name={icon} size={27}/></span>
          <span className="metric-copy"><span className="metric-title">{name}</span><strong>{counts[name]||0}</strong><small>{caption}</small></span>
          <span className="metric-arrow" aria-hidden="true">&#8250;</span>
        </button>)}
    </div>
    {status&&<div className="filter-summary">Showing {status.toLowerCase()} beds <button onClick={()=>setStatus('')}>Show all beds</button></div>}
    <Table key={status} page="beds" rows={status?rows.filter(row=>row.status===status):rows}/>
  </>;
}


/* =========================
   TABLE
========================= */

function Table({
  role,
  page,
  rows,
  onDelete
}){

  const [q,setQ]=useState('');
  const [tablePage,setTablePage]=useState(1);
  const pageSize=page==='beds'?5:10;
  useEffect(()=>setTablePage(1),[q,page]);

  const filtered=
    (Array.isArray(rows)?rows:[])
      .filter(x=>
        JSON.stringify(x)
          .toLowerCase()
          .includes(
            q.toLowerCase()
          )
      );

  const pageCount=Math.max(1,Math.ceil(filtered.length/pageSize));
  const currentPage=Math.min(tablePage,pageCount);
  const visibleRows=filtered.slice((currentPage-1)*pageSize,currentPage*pageSize);

  const cols={
    patients:[
      'patient_id',
      'full_name',
      'gender',
      'phone',
      'blood_group',
      'primary_concern',
      'assigned_doctor',
      'appointment_date',
      'admission_status',
      'discharged_on',
      'emergency_priority',
      'allergies'
    ],

    doctors:[
      'doctor_id',
      'name',
      'specialization',
      'department_name',
      'experience',
      'available'
    ],

    departments:[
      'id',
      'name',
      'doctor_count'
    ],

    appointments:[
      'id',
      'patient_name',
      'doctor_name',
      'date',
      'time',
      'status',
      'emergency_priority'
    ],

    availability:[
      'id',
      'doctor_name',
      'specialization',
      'date',
      'start_time',
      'end_time',
      'is_available'
    ],

    'medical-records':[
      'id',
      'patient',
      'doctor',
      'source',
      'diagnosis',
      'created_at'
    ],

    prescriptions:[
      'id',
      'patient',
      'source',
      'medicine',
      'dosage',
      'frequency',
      'duration'
    ],

    bills:[
      'id',
      'patient_name',
      'total',
      'status',
      'created_at'
    ],

    beds:[
      'id',
      'ward',
      'bed_number',
      'status',
      'patient_name',
      'admitted_on'
    ],

    notifications:[
      'id',
      'title',
      'message',
      'read',
      'created_at'
    ]

  }[page]||
  Object.keys(
    rows?.[0]||{}
  ).slice(0,7);

  return (
    <section className="panel">

      <div className="toolbar">

        <input
          value={q}
          onChange={e=>
            setQ(e.target.value)
          }
          placeholder="Quick search..."
        />

        <span className="access-note">

          {
            role==='ADMIN'
              ?'Full management access'
              :role==='DOCTOR'
                ?'Doctor-linked data'
                :role==='RECEPTIONIST'
                  ?'Front-office access'
                  :'Your private data only'
          }

        </span>

      </div>

      <div className="table-wrap">

        <table>

          <thead>

            <tr>

              {cols.map(c=>(
                <th key={c}>
                  {c.replaceAll('_',' ')}
                </th>
              ))}

              {onDelete&&role==='ADMIN'&&page!=='patients'&&(
                <th>
                  Action
                </th>
              )}

              {page==='bills'&&(
                <th>
                  Invoice
                </th>
              )}

            </tr>

          </thead>

          <tbody>

            {visibleRows.map(r=>(

              <tr key={r.id}>

                {cols.map(c=>(

                  <td key={c}>

                    {
                      c==='status' ? <span className={`record-status record-${String(r[c]).toLowerCase().replaceAll(' ','-')}`}>{r[c]}</span> : typeof r[c]==='object'
                        ?(
                          r[c]?.name||
                          r[c]?.id
                        )
                        :String(
                          r[c]??'-'
                        ).slice(0,70)
                    }

                  </td>

                ))}

                {onDelete&&role==='ADMIN'&&page!=='patients'&&(

                  <td>

                    <button
                      className="danger"
                      onClick={()=>
                        onDelete(r.id)
                      }
                    >
                      Delete
                    </button>

                  </td>

                )}

                {page==='bills'&&(

                  <td>

                    <button
                      className="print"
                      onClick={()=>
                        printBill(r)
                      }
                    >
                      Print/PDF
                    </button>

                  </td>

                )}

              </tr>

            ))}

          </tbody>

        </table>

        {!filtered.length&&(

          <div className="empty">
            No records found.
          </div>

        )}

      </div>

      <div className="table-footer">
        <span>Showing {filtered.length?(currentPage-1)*pageSize+1:0} &ndash; {Math.min(currentPage*pageSize,filtered.length)} of {filtered.length} {page==='beds'?'beds':'records'}</span>
        <nav className="table-pagination" aria-label="Table pages">
          <button aria-label="Previous page" disabled={currentPage===1} onClick={()=>setTablePage(currentPage-1)}>&lsaquo;</button>
          {Array.from({length:Math.min(5,pageCount)},(_,i)=>Math.max(1,Math.min(currentPage-2,pageCount-4))+i).map(number=><button key={number} aria-current={number===currentPage?'page':undefined} className={number===currentPage?'selected':''} onClick={()=>setTablePage(number)}>{number}</button>)}
          <button aria-label="Next page" disabled={currentPage===pageCount} onClick={()=>setTablePage(currentPage+1)}>&rsaquo;</button>
        </nav>
      </div>
    </section>
  );
}


/* =========================
   PRINT BILL
========================= */

function printBill(b){

  const w=window.open(
    '',
    '_blank'
  );

  w.document.write(`
    <html>
      <head>
        <title>
          MedCore Invoice
        </title>

        <style>
          body{
            font-family:Arial;
            padding:40px
          }

          h1{
            color:#0f766e
          }

          table{
            width:100%;
            border-collapse:collapse
          }

          td{
            padding:10px;
            border-bottom:1px solid #ddd
          }
        </style>
      </head>

      <body>

        <h1>
          MedCore HMS
        </h1>

        <h2>
          Patient Invoice
        </h2>

        <table>

          <tr>
            <td>Invoice ID</td>
            <td>${b.id}</td>
          </tr>

          <tr>
            <td>Patient</td>
            <td>${b.patient_name||''}</td>
          </tr>

          <tr>
            <td>Total</td>
            <td>₹${b.total}</td>
          </tr>

          <tr>
            <td>Status</td>
            <td>${b.status}</td>
          </tr>

          <tr>
            <td>Date</td>
            <td>${String(
              b.created_at||''
            ).slice(0,10)}</td>
          </tr>

        </table>

        <p>
          Generated by MedCore HMS
        </p>

        <script>
          window.print()
        </script>

      </body>
    </html>
  `);

  w.document.close();
}


/* =========================
   ROOT
========================= */

function DoctorDirectory({role,data,reload,onDelete}){
  const [q,setQ]=useState(data?.q||'');
  useEffect(()=>setQ(data?.q||''),[data?.q]);
  const page=data?.page||1;
  const count=data?.count||0;
  const size=data?.page_size||50;
  const rows=data?.results||[];
  const columns=[
    ['doctor_id','Doctor ID'],['name','Name'],['specialization','Specialization'],
    ['department_name','Department'],['experience','Experience'],
    ['patient_count','Linked patients / visits'],['available','Available']
  ];
  return <section className="panel">
    <h2>Doctors</h2>
    <p className="muted">Historical names are references from imported visits, not verified members of this hospital. Unknown details are not inferred.</p>
    <form className="toolbar" onSubmit={e=>{e.preventDefault();reload('doctors',{q:q.trim(),page:1});}}>
      <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search doctor, ID, specialization or department..." aria-label="Search doctors"/>
      <button className="primary">Search</button>
    </form>
    <p className="muted">{count.toLocaleString()} doctors · Page {page} of {Math.max(1,Math.ceil(count/size))}</p>
    <div className="table-wrap"><table><thead><tr>{columns.map(([key,label])=><th key={key}>{label}</th>)}{role==='ADMIN'&&<th>Action</th>}</tr></thead>
      <tbody>{rows.map(row=><tr key={row.key}>{columns.map(([key])=><td key={key}>{row[key]===null||row[key]===undefined||row[key]===''?'Not provided':key==='available'?(row[key]?'Yes':'No'):row[key]}</td>)}{role==='ADMIN'&&<td>{row.registered?<button className="danger" onClick={()=>onDelete(row.id)}>Delete</button>:<span className="muted">Imported assignment</span>}</td>}</tr>)}</tbody>
    </table>{!rows.length&&<div className="empty">No doctors found.</div>}</div>
    <div className="toolbar patient-pagination"><button disabled={page<=1} onClick={()=>reload('doctors',{q:data?.q||'',page:page-1})}>Previous</button><button disabled={page*size>=count} onClick={()=>reload('doctors',{q:data?.q||'',page:page+1})}>Next</button></div>
  </section>;
}

function PatientsPage({role,data,reload}){
  if(!['ADMIN','RECEPTIONIST','DOCTOR'].includes(role))return <Table role={role} page="patients" rows={data}/>;
  return <PatientDirectory data={data} reload={reload}/>;
}

function PatientDirectory({data,reload}){
  const [q,setQ]=useState(data?.q||'');
  useEffect(()=>setQ(data?.q||''),[data?.q]);
  const page=data?.page||1;
  const count=data?.count||0;
  const size=data?.page_size||50;
  const rows=data?.results||[];
  const columns=[
    ['serial_number','S.No.'],
    ['record_id','Record ID'],['patient_id','Patient ID'],
    ['patient_name','Patient'],['doctor_name','Assigned doctor'],['date_of_birth','Date of birth'],['age','Age'],
    ['gender','Gender'],['blood_type','Blood type'],['phone','Phone'],['email','Email'],
    ['address','Address'],['emergency_contact','Emergency contact'],
    ['emergency_priority','Emergency priority'],['allergies','Allergies'],
    ['medical_condition','Condition / concern'],['registered_on','Registered'],
    ['admission_date','Admitted'],['appointment_date','Next appointment'],
    ['hospital','Hospital'],['admission_status','Status'],
    ['admission_type','Admission type'],['room_number','Room'],
    ['discharge_date','Discharged'],['medication','Medication'],
    ['test_results','Test result'],['insurance_provider','Insurance'],
    ['billing_amount','Billed amount']
  ];
  const cell=(row,key)=>{
    if(row[key]===null||row[key]===undefined||row[key]===''){
      return 'Not provided';
    }
    if(key==='emergency_priority')return row[key]?'Yes':'No';
    if(key==='doctor_name')return /^(dr\.?|doctor)\s/i.test(row[key])?row[key]:`Dr. ${row[key]}`;
    if(key==='billing_amount')return `₹${Number(row[key]).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2})}`;
    return row[key];
  };
  return <section className="panel patients-unified">
    <h2>Patients</h2>
    <p className="muted">Patient records. Missing details are shown as Not provided.</p>
    <form className="toolbar" onSubmit={e=>{e.preventDefault();reload('patients',{q:q.trim(),page:1});}}>
      <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search name, ID, phone, condition, doctor, medication..." aria-label="Search patient records"/>
      <button className="primary">Search</button>
    </form>
    <p className="muted">{count.toLocaleString()} records · Page {page} of {Math.max(1,Math.ceil(count/size))}</p>
    <div className="table-wrap"><table><thead><tr>{columns.map(([key,label])=><th key={key}>{label}</th>)}</tr></thead>
      <tbody>{rows.map((row,index)=><tr key={row.key}>{columns.map(([key])=><td key={key}>{key==='serial_number'?(page-1)*size+index+1:cell(row,key)}</td>)}</tr>)}</tbody>
    </table>{!rows.length&&<div className="empty">No patient records found.</div>}</div>
    <div className="toolbar patient-pagination"><button disabled={page<=1} onClick={()=>reload('patients',{q:data?.q||'',page:page-1})}>Previous</button><button disabled={page*size>=count} onClick={()=>reload('patients',{q:data?.q||'',page:page+1})}>Next</button></div>
  </section>;
}

function Root(){
  const [screen,setScreen]=useState(new URLSearchParams(location.search).has('reset_token')?'recover':'home');
  if(screen==='recover')return <Recovery api={api} onBack={()=>setScreen('home')}/>;
  if(localStorage.getItem('token'))return <App/>;
  if(screen==='account')return <AccountAccess api={api} onHome={()=>setScreen('home')} onRecover={()=>setScreen('recover')}/>;
  return <PublicHome api={api} onAccount={()=>setScreen('account')}/>;
}

createRoot(
  document.getElementById('root')
).render(
  <BrowserRouter>
    <Root/>
  </BrowserRouter>
);
