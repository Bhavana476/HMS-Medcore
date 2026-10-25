import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';

// Rendering smoke tests, not a substitute for interactive browser tests.
const server=await createServer({server:{middlewareMode:true},appType:'custom'});
try{
  const portal=await server.ssrLoadModule('/src/Portal.jsx');
  const services=await server.ssrLoadModule('/src/Services.jsx');
  const api={get:()=>{throw new Error('Rendering must not perform network requests');}};
  for(const [component,props,text] of [
    [portal.PublicHome,{api,onLogin(){}},'A simpler way to manage your care.'],
    [portal.Documents,{api},'Patient documents'],
    [portal.Laboratory,{api,role:'PATIENT'},'My approved lab results'],
    [services.CareMessages,{api,me:{id:1,role:'PATIENT'}},'Your care-team conversations'],
    [services.ReminderPreferences,{api},'Appointment reminders'],
    [services.BillPayments,{api,rows:[{id:1,total:100,status:'Pending',patient_name:'Example'}],reload(){}},'Invoice #1'],
    [services.ServiceSetup,{api},'Service readiness'],
  ]){
    const html=renderToStaticMarkup(React.createElement(component,props));
    assert.ok(html.includes(text),`${component.name} failed to render expected content`);
    console.log(`PASS ${component.name}`);
  }
}finally{await server.close();}
