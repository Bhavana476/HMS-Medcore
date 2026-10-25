import React,{useEffect,useState} from 'react';
import './operations.css';
import './operations-art.css';

const errorText=e=>{const d=e?.response?.data;if(typeof d==='string')return d;return Object.values(d||{}).flat().join(' ')||'Could not complete this request. Please try again.';};
const money=v=>Number(v||0).toLocaleString('en-IN',{style:'currency',currency:'INR'});
const localDay=(offset=0)=>{const d=new Date();d.setDate(d.getDate()+offset);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
const label=s=>String(s).replaceAll('_',' ').toLowerCase().replace(/^./,c=>c.toUpperCase());

function useLoader(fn,deps=[]){
  const [state,setState]=useState({data:null,error:'',loading:true});
  const load=()=>{setState(s=>({...s,loading:true}));return fn().then(data=>setState({data,error:'',loading:false})).catch(e=>setState({data:null,error:errorText(e),loading:false}));};
  useEffect(()=>{load();},deps);
  return [state,load];
}

function Status({error,message}){return <>{error&&<p className="error" role="alert">{error}</p>}{message&&<p className="success" role="status">{message}</p>}</>;}
function Kpi({title,value,tone,onClick}){
  const body=<><span className="muted">{title}</span><strong>{value}</strong></>;
  return onClick?<button type="button" className={`ops-kpi ${tone||''}`} onClick={onClick}>{body}</button>:<div className={`ops-kpi ${tone||''}`}>{body}</div>;
}
function Empty({children}){return <p className="empty">{children}</p>;}

/* Accessible SVG bar chart: one series, labelled values. */
function BarChart({data,valueKey,labelKey,format=v=>v,height=160}){
  const max=Math.max(1,...data.map(d=>Number(d[valueKey])||0));
  const w=Math.max(280,data.length*44);
  if(!data.some(d=>Number(d[valueKey])))return <div className="ops-chart-empty"><span style={{marginTop:70}}>No activity in this period yet</span></div>;
  return <div className="ops-chart"><svg viewBox={`0 0 ${w} ${height+34}`} role="img" aria-label={data.map(d=>`${d[labelKey]}: ${format(d[valueKey])}`).join(', ')}>
    <defs><linearGradient id="opsBarGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#4f7cff"/><stop offset="1" stopColor="#1fb89a"/></linearGradient></defs>
    {data.map((d,i)=>{const v=Number(d[valueKey])||0;const h=Math.round(v/max*height);const x=i*(w/data.length)+8;const bw=w/data.length-16;
      return <g key={`${d[labelKey]}-${i}`}><rect x={x} y={height-h+14} width={bw} height={h} rx="4" className="ops-bar"><title>{`${d[labelKey]}: ${format(v)}`}</title></rect>
        <text x={x+bw/2} y={height-h+10} textAnchor="middle" className="ops-bar-value">{v?format(v):''}</text>
        <text x={x+bw/2} y={height+30} textAnchor="middle" className="ops-bar-label">{String(d[labelKey]).slice(5)}</text></g>;})}
  </svg></div>;
}

/* ============ dashboards ============ */

export function StaffDashboard({d,role,setPage,userName}){
  const cards={
    SUPER_ADMIN:[['Hospitals',d.hospitals,'hospitals'],['Verified',d.verified_hospitals,'hospitals'],['Platform users',d.users],['Patients',d.patients],['Appointments',d.appointments],['Revenue',money(d.revenue),'finance']],
    PHARMACIST:[['Active medicines',d.medicines,'pharmacy'],['Awaiting dispense',d.pending_dispense,'pharmacy'],['Low stock',d.low_stock_count,'pharmacy','warn'],['Expiring ≤30 days',d.expiring_count,'pharmacy','warn']],
    NURSE:[['Admitted patients',d.admitted,'patients'],['Beds available',d.beds_available,'beds'],['Beds occupied',d.beds_occupied,'beds'],['Vitals recorded today',d.vitals_today,'vitals'],['Emergency flags',d.emergency_patients,'patients','warn']],
    LAB_TECH:[['Ordered',d.ordered,'lab-orders'],['Samples collected',d.sample_collected,'lab-orders'],['Processing',d.processing,'lab-orders'],['Awaiting approval',d.review,'lab-orders','warn'],['Approved today',d.approved_today,'lab-orders']],
    ACCOUNTANT:[['Total revenue',money(d.revenue),'finance'],['Revenue today',money(d.revenue_today),'finance'],['Outstanding',money(d.pending_bills),'bills','warn'],['Open insurance claims',d.open_claims,'finance']],
  }[role]||[];
  return <section className="panel">
    <h2>Welcome, {userName}</h2>
    <div className="ops-kpis">{cards.map(([t,v,p,tone])=><Kpi key={t} title={t} value={v??0} tone={tone} onClick={p?()=>setPage(p):undefined}/>)}</div>
    {role==='PHARMACIST'&&<PharmacyAlerts alerts={d}/>}
  </section>;
}

export function AdminInsights({d,setPage}){
  if(d.appointments_7d===undefined)return null;
  const maxLoad=Math.max(1,...(d.department_occupancy||[]).map(x=>x.appointments_7d));
  return <section className="panel ops-insights">
    <div className="ops-kpis">
      <Kpi title="Patients today" value={d.patients_today} onClick={()=>setPage('patients')}/>
      <Kpi title="Revenue today" value={money(d.revenue_today)} onClick={()=>setPage('finance')}/>
      <Kpi title="Occupied beds" value={`${d.beds_occupied} / ${d.beds_total}`} onClick={()=>setPage('beds')}/>
      <Kpi title="Active doctors" value={d.active_doctors} onClick={()=>setPage('doctors')}/>
    </div>
    <div className="ops-grid">
      <div><h3>Appointments, last 7 days</h3><BarChart data={d.appointments_7d} valueKey="count" labelKey="date"/></div>
      <div><h3>Department occupancy (7 days)</h3>
        <div className="ops-heatmap">{(d.department_occupancy||[]).map(x=><div key={x.name} style={{'--heat':x.appointments_7d/maxLoad}} title={`${x.name}: ${x.appointments_7d} appointments, ${x.doctors} doctors`}><b>{x.name}</b><span>{x.appointments_7d} visits · {x.doctors} dr</span></div>)}</div>
        {!d.department_occupancy?.length&&<Empty>No departments yet.</Empty>}</div>
      <div><h3>Low-stock pharmacy alerts</h3>{d.low_stock?.length?<ul className="ops-list">{d.low_stock.map(m=><li key={m.id}><b>{m.name}</b> <span className="warn-text">{m.stock} left</span> <span className="muted">reorder at {m.reorder_level}</span></li>)}</ul>:<Empty>Stock levels are healthy.</Empty>}</div>
      <div><h3>Recent activity</h3>{d.recent_activity?.length?<ul className="ops-list">{d.recent_activity.map(a=><li key={a.id}><span className="muted">{new Date(a.created_at).toLocaleTimeString()}</span> {a.username||'anonymous'} · {a.method} {a.path} <span className="muted">({a.status_code})</span></li>)}</ul>:<Empty>No changes recorded yet.</Empty>}</div>
    </div>
  </section>;
}

function MiniMonth({dates}){
  const now=new Date();const first=new Date(now.getFullYear(),now.getMonth(),1);const days=new Date(now.getFullYear(),now.getMonth()+1,0).getDate();
  const counts={};dates.forEach(d=>{counts[d]=(counts[d]||0)+1;});
  const cells=[...Array(first.getDay()).fill(null),...Array.from({length:days},(_,i)=>i+1)];
  return <div className="ops-month" aria-label="Follow-up calendar">{['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].map(d=><b key={d} title={d}>{d[0]}</b>)}
    {cells.map((n,i)=>{if(!n)return <span key={`blank-${i}`}/>;const key=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(n).padStart(2,'0')}`;
      return <span key={key} className={`${counts[key]?'has':''} ${n===now.getDate()?'today':''}`} title={counts[key]?`${counts[key]} appointment(s)`:''}>{n}</span>;})}
  </div>;
}

export function DoctorInsights({d,setPage}){
  if(!d.follow_ups)return null;
  return <section className="panel ops-insights"><div className="ops-grid">
    <div><h3>Upcoming follow-ups</h3><MiniMonth dates={d.follow_ups.map(a=>a.date)}/></div>
    <div><h3>Pending lab approvals</h3>{d.pending_lab_approvals.length?<ul className="ops-list">{d.pending_lab_approvals.map(o=><li key={o.id}><b>{o.test}</b> · {o.patient} <span className="muted">{o.result}</span></li>)}</ul>:<Empty>Nothing awaiting your approval.</Empty>}
      {!!d.pending_lab_approvals.length&&<button className="primary" onClick={()=>setPage('lab-orders')}>Review results</button>}</div>
    <div><h3>Recent prescriptions</h3>{d.recent_prescriptions.length?<ul className="ops-list">{d.recent_prescriptions.map(p=><li key={p.id}><b>{p.medicine}</b> {p.dosage} · {p.patient}</li>)}</ul>:<Empty>No prescriptions yet.</Empty>}</div>
  </div></section>;
}

/* ============ super admin ============ */

export function Hospitals({api}){
  const [{data,error},load]=useLoader(()=>api.get('/hospitals/').then(r=>r.data));
  const [form,setForm]=useState({name:'',code:'',address:'',phone:'',email:''});const [msg,setMsg]=useState('');const [err,setErr]=useState('');
  const run=async fn=>{setErr('');setMsg('');try{await fn();await load();}catch(e){setErr(errorText(e));}};
  return <section className="panel"><h2>Hospitals</h2><p className="muted">Onboard hospitals and verify them before staff start using the platform.</p>
    <form className="live-form" onSubmit={e=>{e.preventDefault();run(async()=>{await api.post('/hospitals/',form);setForm({name:'',code:'',address:'',phone:'',email:''});setMsg('Hospital created. Verify it once checks are complete.');});}}>
      {[['name','Hospital name',true],['code','Short code',true],['address','Address'],['phone','Phone'],['email','Email']].map(([k,l,req])=><label className="form-field" key={k}>{l}<input required={!!req} type={k==='email'?'email':'text'} value={form[k]} onChange={e=>setForm({...form,[k]:e.target.value})}/></label>)}
      <button className="primary">Add hospital</button></form>
    <Status error={error||err} message={msg}/>
    <div className="table-wrap"><table><thead><tr><th>Name</th><th>Code</th><th>Users</th><th>Patients</th><th>Status</th><th>Action</th></tr></thead>
      <tbody>{(data||[]).map(h=><tr key={h.id}><td>{h.name}</td><td>{h.code}</td><td>{h.user_count}</td><td>{h.patient_count}</td><td>{h.verified?'Verified':'Pending verification'}</td>
        <td>{!h.verified&&<button className="primary" onClick={()=>run(()=>api.post(`/hospitals/${h.id}/verify/`))}>Verify</button>}</td></tr>)}</tbody></table>
      {data&&!data.length&&<Empty>No hospitals onboarded yet.</Empty>}</div>
  </section>;
}

/* ============ pharmacy ============ */

function PharmacyAlerts({alerts}){
  return <div className="ops-grid">
    <div><h3>Low stock</h3>{alerts.low_stock?.length?<ul className="ops-list">{alerts.low_stock.map(m=><li key={m.id}><b>{m.name}</b> <span className="warn-text">{m.stock} left</span> <span className="muted">reorder at {m.reorder_level}</span></li>)}</ul>:<Empty>No low-stock medicines.</Empty>}</div>
    <div><h3>Expiring within 30 days</h3>{alerts.expiring?.length?<ul className="ops-list">{alerts.expiring.map(b=><li key={b.id}><b>{b.medicine_name}</b> batch {b.batch_number} · {b.quantity} units <span className={b.expired?'warn-text':'muted'}>{b.expired?'EXPIRED':'expires'} {b.expiry_date}</span></li>)}</ul>:<Empty>No batches expiring soon.</Empty>}</div>
  </div>;
}

export function Pharmacy({api,role}){
  const [search,setSearch]=useState('');
  const [{data,error},load]=useLoader(()=>Promise.all([api.get('/medicines/',{params:{search}}),api.get('/medicine-batches/'),api.get('/medicines/alerts/'),api.get('/prescription-items/',{params:{pending:1}})]).then(([m,b,a,q])=>({medicines:m.data,batches:b.data,alerts:a.data,queue:q.data})),[search]);
  const [med,setMed]=useState({name:'',form:'tablet',manufacturer:'',reorder_level:10});
  const [batch,setBatch]=useState({medicine:'',batch_number:'',manufacturing_date:'',expiry_date:'',quantity:'',unit_cost:'',mrp:''});
  const [qty,setQty]=useState({});const [msg,setMsg]=useState('');const [err,setErr]=useState('');
  const run=async(fn,ok)=>{setErr('');setMsg('');try{await fn();setMsg(ok);await load();}catch(e){setErr(errorText(e));}};
  const d=data||{medicines:[],batches:[],alerts:{},queue:[]};
  return <>
    <section className="panel"><h2>Prescriptions awaiting dispensing</h2><p className="muted">Stock is issued oldest-expiry first. Expired or quarantined batches are never dispensed.</p>
      <Status error={error||err} message={msg}/>
      <div className="table-wrap"><table><thead><tr><th>Patient</th><th>Medicine</th><th>Dosage</th><th>Frequency</th><th>Duration</th><th>Quantity</th><th></th></tr></thead>
        <tbody>{d.queue.map(i=><tr key={i.id}><td>{i.patient_name}</td><td>{i.medicine_name}</td><td>{i.dosage}</td><td>{i.frequency}</td><td>{i.duration}</td>
          <td><input type="number" min="1" aria-label={`Quantity of ${i.medicine_name}`} value={qty[i.id]||''} onChange={e=>setQty({...qty,[i.id]:e.target.value})}/></td>
          <td><button className="primary" disabled={!qty[i.id]} onClick={()=>run(()=>api.post(`/prescription-items/${i.id}/dispense/`,{quantity:qty[i.id]}),`${i.medicine_name} dispensed.`)}>Dispense</button></td></tr>)}</tbody></table>
        {!d.queue.length&&<Empty>No prescriptions waiting.</Empty>}</div></section>
    <section className="panel"><h2>Stock alerts</h2><PharmacyAlerts alerts={d.alerts}/></section>
    <section className="panel"><div className="section-intro"><h2>Medicine inventory</h2><input aria-label="Search medicines" placeholder="Search medicines" value={search} onChange={e=>setSearch(e.target.value)}/></div>
      <div className="table-wrap"><table><thead><tr><th>Medicine</th><th>Form</th><th>Usable stock</th><th>Reorder level</th><th>Next expiry</th></tr></thead>
        <tbody>{d.medicines.map(m=><tr key={m.id}><td>{m.name}</td><td>{m.form}</td><td className={m.low_stock?'warn-text':''}>{m.stock}{m.low_stock&&' (low)'}</td><td>{m.reorder_level}</td><td>{m.next_expiry||'—'}</td></tr>)}</tbody></table>
        {!d.medicines.length&&<Empty>No medicines found.</Empty>}</div>
      {['ADMIN','PHARMACIST'].includes(role)&&<div className="ops-grid">
        <form className="live-form" onSubmit={e=>{e.preventDefault();run(async()=>{await api.post('/medicines/',med);setMed({...med,name:'',manufacturer:''});},'Medicine added.');}}><h3>Add medicine</h3>
          <label className="form-field">Name<input required value={med.name} onChange={e=>setMed({...med,name:e.target.value})}/></label>
          <label className="form-field">Form<select value={med.form} onChange={e=>setMed({...med,form:e.target.value})}>{['tablet','capsule','syrup','injection','topical'].map(f=><option key={f}>{f}</option>)}</select></label>
          <label className="form-field">Manufacturer<input value={med.manufacturer} onChange={e=>setMed({...med,manufacturer:e.target.value})}/></label>
          <label className="form-field">Reorder level<input type="number" min="0" required value={med.reorder_level} onChange={e=>setMed({...med,reorder_level:e.target.value})}/></label>
          <button className="primary">Add medicine</button></form>
        <form className="live-form" onSubmit={e=>{e.preventDefault();run(async()=>{await api.post('/medicine-batches/',batch);setBatch({...batch,batch_number:'',quantity:''});},'Batch received.');}}><h3>Receive batch</h3>
          <label className="form-field">Medicine<select required value={batch.medicine} onChange={e=>setBatch({...batch,medicine:e.target.value})}><option value="">Choose</option>{d.medicines.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
          {[['batch_number','Batch number','text'],['manufacturing_date','Manufactured','date'],['expiry_date','Expiry','date'],['quantity','Quantity','number'],['unit_cost','Unit cost (INR)','number'],['mrp','MRP (INR)','number']].map(([k,l,t])=><label className="form-field" key={k}>{l}<input required type={t} min={t==='number'?0:undefined} step={t==='number'?'0.01':undefined} value={batch[k]} onChange={e=>setBatch({...batch,[k]:e.target.value})}/></label>)}
          <button className="primary">Add batch</button></form>
      </div>}
    </section>
    <section className="panel"><h2>Batches</h2><div className="table-wrap"><table><thead><tr><th>Medicine</th><th>Batch</th><th>Expiry</th><th>Qty</th><th>MRP</th><th>Status</th><th></th></tr></thead>
      <tbody>{d.batches.map(b=><tr key={b.id}><td>{b.medicine_name}</td><td>{b.batch_number}</td><td>{b.expiry_date}</td><td>{b.quantity}</td><td>{money(b.mrp)}</td>
        <td>{b.quarantined?'Quarantined':b.expired?<span className="warn-text">Expired</span>:'Usable'}</td>
        <td>{!b.quarantined&&<button className="danger" onClick={()=>run(()=>api.post(`/medicine-batches/${b.id}/quarantine/`),'Batch quarantined.')}>Quarantine</button>}</td></tr>)}</tbody></table>
      {!d.batches.length&&<Empty>No batches received yet.</Empty>}</div></section>
  </>;
}

/* ============ nursing ============ */

export function Vitals({api,role}){
  const [patient,setPatient]=useState('');
  const [{data,error},load]=useLoader(()=>Promise.all([api.get('/patients/'),api.get('/vitals/',{params:patient?{patient}:{}})]).then(([p,v])=>({patients:p.data,vitals:v.data})),[patient]);
  const blank={blood_pressure:'',pulse:'',temperature:'',spo2:'',height_cm:'',weight_kg:'',medication_notes:''};
  const [form,setForm]=useState(blank);const [msg,setMsg]=useState('');const [err,setErr]=useState('');
  const canRecord=['ADMIN','NURSE','DOCTOR'].includes(role);
  const submit=async e=>{e.preventDefault();setErr('');setMsg('');try{const body=Object.fromEntries(Object.entries({...form,patient}).filter(([,v])=>v!==''));await api.post('/vitals/',body);setForm(blank);setMsg('Observation recorded.');load();}catch(x){setErr(errorText(x));}};
  const d=data||{patients:[],vitals:[]};
  return <section className="panel"><h2>Vitals & medication notes</h2><p className="muted">Entries are append-only and cannot be edited or deleted. BMI is calculated automatically.</p>
    <label className="form-field">Patient<select value={patient} onChange={e=>setPatient(e.target.value)}><option value="">All patients</option>{d.patients.map(p=><option key={p.id} value={p.id}>{p.full_name} · {p.patient_id}</option>)}</select></label>
    {canRecord&&patient&&<form className="live-form" onSubmit={submit}>
      {[['blood_pressure','Blood pressure','text'],['pulse','Pulse (bpm)','number'],['temperature','Temperature (°C)','number'],['spo2','SpO2 (%)','number'],['height_cm','Height (cm)','number'],['weight_kg','Weight (kg)','number']].map(([k,l,t])=><label className="form-field" key={k}>{l}<input type={t} step="any" min={t==='number'?0:undefined} value={form[k]} onChange={e=>setForm({...form,[k]:e.target.value})}/></label>)}
      <label className="form-field">Medication administration notes<textarea value={form.medication_notes} onChange={e=>setForm({...form,medication_notes:e.target.value})}/></label>
      <button className="primary">Record observation</button></form>}
    {canRecord&&!patient&&<p className="muted">Choose a patient to record new vitals.</p>}
    <Status error={error||err} message={msg}/>
    <div className="table-wrap"><table><thead><tr><th>Time</th><th>Patient</th><th>BP</th><th>Pulse</th><th>Temp</th><th>SpO2</th><th>BMI</th><th>Notes</th><th>By</th></tr></thead>
      <tbody>{d.vitals.map(v=><tr key={v.id}><td>{new Date(v.created_at).toLocaleString()}</td><td>{v.patient_name}</td><td>{v.blood_pressure||'—'}</td><td>{v.pulse??'—'}</td><td>{v.temperature??'—'}</td><td>{v.spo2??'—'}</td><td>{v.bmi??'—'}</td><td>{v.medication_notes||'—'}</td><td>{v.recorded_by_name}</td></tr>)}</tbody></table>
      {!d.vitals.length&&<Empty>No observations recorded.</Empty>}</div>
  </section>;
}

/* ============ finance ============ */

export function Finance({api,role}){
  const [range,setRange]=useState({from:localDay(-29),to:localDay()});
  const canAnalyse=['ADMIN','ACCOUNTANT','SUPER_ADMIN'].includes(role);
  const [{data,error},load]=useLoader(()=>Promise.all([canAnalyse?api.get('/analytics/revenue/',{params:range}):Promise.resolve({data:null}),role==='SUPER_ADMIN'?Promise.resolve({data:[]}):api.get('/insurance-claims/'),role==='SUPER_ADMIN'?Promise.resolve({data:[]}):api.get('/bills/')]).then(([r,c,b])=>({revenue:r.data,claims:c.data,bills:b.data})),[range.from,range.to]);
  const d=data||{revenue:null,claims:[],bills:[]};
  return <>
    {canAnalyse&&<section className="panel"><div className="section-intro"><h2>Revenue analytics</h2>
      <div className="toolbar"><label>From <input type="date" value={range.from} onChange={e=>setRange({...range,from:e.target.value})}/></label><label>To <input type="date" value={range.to} onChange={e=>setRange({...range,to:e.target.value})}/></label></div></div>
      <Status error={error}/>
      {d.revenue&&<><div className="ops-kpis">{Object.entries(d.revenue.by_category).map(([k,v])=><Kpi key={k} title={label(k)} value={money(v)}/>)}<Kpi title="Outstanding" value={money(d.revenue.outstanding)} tone="warn"/></div>
        <h3>Paid revenue per day</h3><BarChart data={d.revenue.daily} valueKey="revenue" labelKey="date" format={v=>v>=1000?`${Math.round(v/1000)}k`:Math.round(v)}/></>}
    </section>}
    {role!=='SUPER_ADMIN'&&<InvoiceItems api={api} role={role} bills={d.bills} reload={load}/>}
    {role!=='SUPER_ADMIN'&&<Claims api={api} role={role} claims={d.claims} bills={d.bills} reload={load}/>}
  </>;
}

function InvoiceItems({api,role,bills,reload}){
  const [bill,setBill]=useState('');const [items,setItems]=useState([]);const [err,setErr]=useState('');
  const [form,setForm]=useState({category:'CONSULTATION',description:'',quantity:1,unit_price:''});
  const current=bills.find(b=>String(b.id)===bill);
  const loadItems=()=>bill?api.get('/bill-items/',{params:{bill}}).then(r=>setItems(r.data)).catch(e=>setErr(errorText(e))):setItems([]);
  useEffect(()=>{loadItems();},[bill]);
  const run=async fn=>{setErr('');try{await fn();await loadItems();await reload();}catch(e){setErr(errorText(e));}};
  const editable=current&&current.status==='Pending'&&['ADMIN','ACCOUNTANT','RECEPTIONIST'].includes(role);
  return <section className="panel"><h2>Invoice line items</h2><p className="muted">Charges from consultation, laboratory, pharmacy and room stays. The invoice total always equals the sum of its items.</p>
    <label className="form-field">Invoice<select value={bill} onChange={e=>setBill(e.target.value)}><option value="">Choose invoice</option>{bills.map(b=><option key={b.id} value={b.id}>#{b.id} · {b.patient_name} · {money(b.total)} · {b.status}</option>)}</select></label>
    <Status error={err}/>
    {current&&<><div className="table-wrap"><table><thead><tr><th>Category</th><th>Description</th><th>Qty</th><th>Unit price</th><th>Amount</th>{editable&&<th></th>}</tr></thead>
      <tbody>{items.map(i=><tr key={i.id}><td>{label(i.category)}</td><td>{i.description}</td><td>{i.quantity}</td><td>{money(i.unit_price)}</td><td>{money(i.amount)}</td>{editable&&<td><button className="danger" onClick={()=>run(()=>api.delete(`/bill-items/${i.id}/`))}>Remove</button></td>}</tr>)}</tbody>
      <tfoot><tr><td colSpan={4}><b>Invoice total</b></td><td><b>{money(current.total)}</b></td>{editable&&<td/>}</tr></tfoot></table></div>
      {editable&&<form className="live-form" onSubmit={e=>{e.preventDefault();run(async()=>{await api.post('/bill-items/',{...form,bill});setForm({...form,description:'',unit_price:''});});}}>
        <label className="form-field">Category<select value={form.category} onChange={e=>setForm({...form,category:e.target.value})}>{['CONSULTATION','LAB','PHARMACY','ROOM','OTHER'].map(c=><option key={c} value={c}>{label(c)}</option>)}</select></label>
        <label className="form-field">Description<input required value={form.description} onChange={e=>setForm({...form,description:e.target.value})}/></label>
        <label className="form-field">Quantity<input required type="number" min="1" value={form.quantity} onChange={e=>setForm({...form,quantity:e.target.value})}/></label>
        <label className="form-field">Unit price (INR)<input required type="number" min="0" step="0.01" value={form.unit_price} onChange={e=>setForm({...form,unit_price:e.target.value})}/></label>
        <button className="primary">Add line item</button></form>}</>}
  </section>;
}

function Claims({api,role,claims,bills,reload}){
  const [form,setForm]=useState({bill:'',provider:'',policy_number:'',tpa_name:'',claimed_amount:'',notes:''});const [approved,setApproved]=useState({});const [err,setErr]=useState('');
  const canManage=['ADMIN','ACCOUNTANT'].includes(role);
  const run=async fn=>{setErr('');try{await fn();await reload();}catch(e){setErr(errorText(e));}};
  const next={DRAFT:['SUBMITTED'],SUBMITTED:['APPROVED','REJECTED'],APPROVED:['SETTLED']};
  return <section className="panel"><h2>Insurance claims (TPA)</h2><p className="muted">Draft → Submitted to TPA → Approved or Rejected → Settled.</p><Status error={err}/>
    {canManage&&<form className="live-form" onSubmit={e=>{e.preventDefault();run(async()=>{await api.post('/insurance-claims/',form);setForm({bill:'',provider:'',policy_number:'',tpa_name:'',claimed_amount:'',notes:''});});}}>
      <label className="form-field">Invoice<select required value={form.bill} onChange={e=>setForm({...form,bill:e.target.value})}><option value="">Choose invoice</option>{bills.map(b=><option key={b.id} value={b.id}>#{b.id} · {b.patient_name} · {money(b.total)}</option>)}</select></label>
      {[['provider','Insurer'],['policy_number','Policy number'],['tpa_name','TPA (optional)'],['claimed_amount','Claimed amount (INR)']].map(([k,l])=><label className="form-field" key={k}>{l}<input required={k!=='tpa_name'} type={k==='claimed_amount'?'number':'text'} min="0" step="0.01" value={form[k]} onChange={e=>setForm({...form,[k]:e.target.value})}/></label>)}
      <button className="primary">Create claim</button></form>}
    <div className="table-wrap"><table><thead><tr><th>Invoice</th><th>Patient</th><th>Insurer</th><th>Policy</th><th>Claimed</th><th>Approved</th><th>Status</th>{canManage&&<th>Action</th>}</tr></thead>
      <tbody>{claims.map(c=><tr key={c.id}><td>#{c.bill}</td><td>{c.patient_name}</td><td>{c.provider}</td><td>{c.policy_number}</td><td>{money(c.claimed_amount)}</td><td>{c.approved_amount?money(c.approved_amount):'—'}</td><td>{label(c.status)}</td>
        {canManage&&<td className="ops-actions">{c.status==='SUBMITTED'&&<input type="number" min="0" step="0.01" placeholder="Approved ₹" aria-label="Approved amount" value={approved[c.id]||''} onChange={e=>setApproved({...approved,[c.id]:e.target.value})}/>}
          {(next[c.status]||[]).map(s=><button key={s} className={s==='REJECTED'?'danger':'primary'} disabled={s==='APPROVED'&&!approved[c.id]} onClick={()=>run(()=>api.post(`/insurance-claims/${c.id}/transition/`,{status:s,approved_amount:approved[c.id]}))}>{label(s)}</button>)}</td>}</tr>)}</tbody></table>
      {!claims.length&&<Empty>No insurance claims.</Empty>}</div>
  </section>;
}

/* ============ audit, security, records ============ */

export function AuditLog({api}){
  const [{data,error}]=useLoader(()=>api.get('/audit-logs/').then(r=>r.data));
  const [q,setQ]=useState('');
  const rows=(data||[]).filter(r=>`${r.username} ${r.method} ${r.path} ${r.ip_address}`.toLowerCase().includes(q.toLowerCase()));
  return <section className="panel"><div className="section-intro"><div><h2>Audit log</h2><p className="muted">Every create, update and delete request, with user, IP address and time. Latest 500 shown.</p></div><input aria-label="Filter audit log" placeholder="Filter by user, path or IP" value={q} onChange={e=>setQ(e.target.value)}/></div>
    <Status error={error}/>
    <div className="table-wrap"><table><thead><tr><th>Time</th><th>User</th><th>Action</th><th>Path</th><th>Result</th><th>IP</th></tr></thead>
      <tbody>{rows.map(r=><tr key={r.id}><td>{new Date(r.created_at).toLocaleString()}</td><td>{r.username||'anonymous'}</td><td>{r.method}</td><td>{r.path}</td><td className={r.status_code>=400?'warn-text':''}>{r.status_code}</td><td>{r.ip_address||'—'}</td></tr>)}</tbody></table>
      {data&&!rows.length&&<Empty>No matching entries.</Empty>}</div></section>;
}

export function AccountSecurity({api,me}){
  const [status,setStatus]=useState({email:me.email_verified,phone:me.phone_verified});
  const [sent,setSent]=useState('');const [code,setCode]=useState('');const [msg,setMsg]=useState('');const [err,setErr]=useState('');
  const [signature,setSignature]=useState('');
  useEffect(()=>{if(me.role==='DOCTOR')api.get('/doctor-signature/').then(r=>setSignature(r.data.signature)).catch(()=>{});},[]);
  const send=async channel=>{setErr('');setMsg('');try{const r=await api.post('/verify/send/',{channel});setSent(channel);setMsg(r.data.detail);}catch(e){setErr(errorText(e));}};
  const confirm=async e=>{e.preventDefault();setErr('');try{await api.post('/verify/confirm/',{channel:sent,code});setStatus({...status,[sent]:true});setSent('');setCode('');setMsg('Verified successfully.');}catch(x){setErr(errorText(x));}};
  const upload=file=>{setErr('');if(!file)return;if(file.type!=='image/png'||file.size>200*1024){setErr('Choose a PNG image under 200 KB.');return;}
    const reader=new FileReader();reader.onload=async()=>{try{const r=await api.put('/doctor-signature/',{signature:reader.result});setSignature(r.data.signature);setMsg('Signature saved. It will appear on printed prescriptions.');}catch(e){setErr(errorText(e));}};reader.readAsDataURL(file);};
  return <section className="panel"><h2>Account security</h2>
    <div className="ops-kpis">
      <div className="ops-kpi"><span className="muted">Email {me.email||'(not set)'}</span><strong>{status.email?'Verified':'Not verified'}</strong>{!status.email&&me.email&&<button className="primary" onClick={()=>send('email')}>Send code</button>}</div>
      <div className="ops-kpi"><span className="muted">Phone {me.phone||'(not set)'}</span><strong>{status.phone?'Verified':'Not verified'}</strong>{!status.phone&&me.phone&&<button className="primary" onClick={()=>send('phone')}>Send SMS code</button>}</div>
    </div>
    {sent&&<form className="live-form" onSubmit={confirm}><label className="form-field">6-digit code sent to your {sent}<input required inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" value={code} onChange={e=>setCode(e.target.value)}/></label><button className="primary">Verify</button></form>}
    {me.role==='DOCTOR'&&<div><h3>Prescription signature</h3>{signature?<img className="ops-signature" src={signature} alt="Your saved signature"/>:<p className="muted">No signature uploaded.</p>}
      <label className="form-field">Upload PNG signature<input type="file" accept="image/png" onChange={e=>upload(e.target.files[0])}/></label></div>}
    <Status error={err} message={msg}/>
    <p className="muted">Signing out revokes your session token on the server. Sessions expire after 15 minutes of inactivity and are renewed automatically while you work.</p>
  </section>;
}

export function PrescriptionPrint({api,rows}){
  const [err,setErr]=useState('');
  if(!rows?.length)return null;
  const open=async id=>{setErr('');const w=window.open('','_blank');try{const r=await api.get(`/prescriptions/${id}/print/`,{responseType:'blob'});w.location.href=URL.createObjectURL(r.data);}catch(e){w?.close();setErr('Could not open this prescription.');}};
  return <section className="panel"><h2>Print prescriptions</h2><p className="muted">Opens a letterhead copy with the doctor's signature. Use your browser's Save as PDF to download it.</p><Status error={err}/>
    <div className="slot-chips">{rows.map(p=><button key={p.id} onClick={()=>open(p.id)}>#{p.id} · {p.medicine} · {p.patient}</button>)}</div></section>;
}

export function RecordClinicalDetails({rows}){
  const detailed=(rows||[]).filter(r=>r.blood_pressure||r.pulse||r.bmi||r.icd10_code||r.adverse_reactions||Object.values(r.family_history||{}).some(Boolean)||r.vaccination_history?.length);
  if(!detailed.length)return null;
  return <section className="panel"><h2>Encounter clinical details</h2><div className="document-grid">{detailed.map(r=><article className="document-card" key={r.id}>
    <span className="eyebrow">#{r.id} · {new Date(r.created_at).toLocaleDateString()}</span><h3>{r.patient}</h3>
    <p><b>{r.diagnosis}</b>{r.icd10_code&&<span className="muted"> · ICD-10 {r.icd10_code}</span>}</p>
    <dl className="ops-dl">{[['BP',r.blood_pressure],['Pulse',r.pulse],['Temp °C',r.temperature],['SpO2 %',r.spo2],['BMI',r.bmi]].filter(([,v])=>v!==null&&v!==''&&v!==undefined).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
    {r.adverse_reactions&&<p className="warn-text">Allergies / reactions: {r.adverse_reactions}</p>}
    {Object.values(r.family_history||{}).some(Boolean)&&<p className="muted">Family history: {Object.entries(r.family_history).filter(([,v])=>v).map(([k])=>k).join(', ')}</p>}
    {!!r.vaccination_history?.length&&<p className="muted">Vaccines: {r.vaccination_history.map(v=>`${v.vaccine} (${v.date})`).join(', ')}</p>}
  </article>)}</div></section>;
}
