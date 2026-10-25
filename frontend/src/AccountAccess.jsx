import React,{useState} from 'react';
import './account-access.css';

function Icon({name}){
 const shapes={user:<><circle cx="12" cy="7" r="3"/><path d="M5 21v-3a7 7 0 0 1 14 0v3Z"/></>,mail:<><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 6 9 7 9-7"/></>,phone:<path d="M7 3H4a1 1 0 0 0-1 1c0 9 8 17 17 17a1 1 0 0 0 1-1v-3l-5-2-2 2a14 14 0 0 1-7-7l2-2Z"/>,lock:<><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4m-4 4v3"/></>,shield:<><path d="m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6Z"/><path d="m8 11 3 3 5-5"/></>,calendar:<><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 2v6m10-6v6M3 11h18m-13 5 2 2 5-4"/></>,heart:<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 22l8.8-9.6a5.5 5.5 0 0 0 0-7.8Z"/>,arrow:<path d="M4 12h16m-6-6 6 6-6 6"/>};
 return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{shapes[name]}</svg>;
}
export default function AccountAccess({api,onHome,onRecover}){
 const [creating,setCreating]=useState(true);
 const [confirming,setConfirming]=useState(false);
 const [form,setForm]=useState({first_name:'',last_name:'',username:'',email:'',phone:'',password:'',confirm:''});
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [message,setMessage]=useState('');
 const change=e=>setForm({...form,[e.target.name]:e.target.value});
 const switchMode=()=>{setCreating(!creating);setConfirming(false);setError('');setMessage('');setForm({...form,password:'',confirm:''});};
 const submit=async e=>{
  e.preventDefault();setError('');setMessage('');
  if(creating&&!confirming){setConfirming(true);return;}
  if(creating&&form.password!==form.confirm){setError('Passwords do not match.');return;}
  setBusy(true);
  try{
   if(creating){
    const {confirm,...data}=form;await api.post('/signup/',data);
    setCreating(false);setConfirming(false);setForm({...form,password:'',confirm:''});
    setMessage('Your account has been created. Sign in to get started.');
   }else{
    const result=await api.post('/login/',{username:form.username,password:form.password});
    localStorage.setItem('token',result.data.access);window.location.assign('/');
   }
  }catch(err){setError(err.response?.data?Object.values(err.response.data).flat().join(' '):'Cannot connect to the server. Please try again shortly.');}
  finally{setBusy(false);}
 };
 const field=(name,label,placeholder,icon='user',type='text',autoComplete=name,required=true)=><label className="access-field" key={name}><span>{label}</span><span className="access-input"><Icon name={icon}/><input name={name} type={type} placeholder={placeholder} autoComplete={autoComplete} required={required} maxLength={name==='phone'?20:type==='password'?128:150} minLength={name==='password'&&creating?8:undefined} value={form[name]} onChange={change} autoFocus={name==='confirm'}/></span></label>;
 return <div className="account-page">
  <div className="access-photo" aria-hidden="true"/>
  <svg className="access-wave" viewBox="0 0 550 220" aria-hidden="true"><path d="M0 0Q230 185 550 220H0Z" fill="#d3e2ff"/><path d="M0 65Q210 202 470 220H0Z" fill="#b3c9ff"/><path d="M235 180c65-4 87-79 58-68-10 4-11 13-11 13s-15-24-25-7c-18 31 44 58 85 49s64-47 123-20" fill="none" stroke="#92b3ff" strokeWidth="3"/></svg>
  <section className="access-intro" aria-label="Welcome to MedCore">
   <button className="access-brand" onClick={onHome} aria-label="MedCore hospital home"><span className="access-brand-mark">♥<b>+</b></span><span>MedCore<small>Better Care · Healthier Tomorrow</small></span></button>
   <h1>Your Health<br/><strong>Matters to Us</strong></h1>
   <p>Create your account and take the<br className="access-desktop-break"/> first step towards a healthier you.</p>
   <ul className="access-benefits">{[['shield','Secure & Private','Your data is always protected'],['user','Expert Care','Connect with trusted professionals'],['calendar','Easy Appointments','Book your visits in just a few clicks'],['heart','Better Health','Because you matter']].map(([icon,title,description])=><li key={title}><span className="access-benefit-icon"><Icon name={icon}/></span><div>{title}<small>{description}</small></div></li>)}</ul>
  </section>
  <section className="access-card" aria-labelledby="access-title">
   <div className="access-heading"><span className="access-title-icon"><Icon name={confirming?'lock':'user'}/></span><div><h2 id="access-title">{creating?(confirming?'Secure your account':'Create your account'):'Welcome back'}</h2><p>{creating?(confirming?'Confirm your password to finish creating your account.':'First visit? Create a patient account to get started.'):'Sign in with your existing account.'}</p></div></div>
   <form onSubmit={submit}>
    {creating&&!confirming&&<>{field('first_name','First name','Enter your first name','user','text','given-name')}{field('last_name','Last name','Enter your last name','user','text','family-name',false)}{field('email','Email','Enter your email address','mail','email','email')}{field('phone','Phone','Enter your phone number','phone','tel','tel')}</>}
    {!confirming&&field('username','Username',creating?'Choose a username':'Enter your username')}
    {!confirming&&field('password','Password',creating?'Create a password':'Enter your password','lock','password',creating?'new-password':'current-password')}
    {creating&&!confirming&&<small className="access-hint">ⓘ Use at least 8 characters and avoid common passwords.</small>}
    {creating&&confirming&&<><p className="access-confirm-note">Creating an account for <strong>{form.first_name}</strong> using {form.email}.</p>{field('confirm','Confirm password','Enter your password again','lock','password','new-password')}</>}
    {error&&<p className="access-error" role="alert">{error}</p>}
    {message&&<p className="access-success" role="status">{message}</p>}
    <button className="access-submit" disabled={busy}>{busy?'Please wait…':creating?(confirming?'Create account':'Confirm password'):'Sign in'}<Icon name="arrow"/></button>
    {creating&&confirming&&<button type="button" className="access-link" disabled={busy} onClick={()=>{setConfirming(false);setError('');}}>Back to your details</button>}
   </form>
   <div className="access-footer"><button className="access-link" disabled={busy} onClick={switchMode}>{creating?'Already have an account? Sign in':'New here? Create an account'}</button>{!creating&&<button className="access-link" onClick={onRecover}>Forgot password?</button>}</div>
  </section>
  <div className="access-heart" aria-hidden="true"><Icon name="heart"/><span>+</span></div>
 </div>;
}
