// @vitest-environment jsdom
import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {render,screen,cleanup,waitFor} from '@testing-library/react';
import {StaffDashboard,RecordClinicalDetails,AuditLog} from './Operations';

afterEach(cleanup);

describe('StaffDashboard',()=>{
  it('shows pharmacist stock warnings',()=>{
    render(<StaffDashboard role="PHARMACIST" userName="Asha" setPage={()=>{}} d={{medicines:4,pending_dispense:2,low_stock_count:1,expiring_count:0,low_stock:[{id:1,name:'Amoxicillin',stock:3,reorder_level:10}],expiring:[]}}/>);
    expect(screen.getByText('Welcome, Asha')).toBeTruthy();
    expect(screen.getByText('Amoxicillin')).toBeTruthy();
    expect(screen.getByText('3 left')).toBeTruthy();
  });
  it('renders accountant money values in rupees',()=>{
    render(<StaffDashboard role="ACCOUNTANT" userName="Ravi" setPage={()=>{}} d={{revenue:1500,revenue_today:0,pending_bills:200,open_claims:1}}/>);
    expect(screen.getByText(/1,500/)).toBeTruthy();
  });
});

describe('RecordClinicalDetails',()=>{
  it('hides records without clinical detail',()=>{
    const {container}=render(<RecordClinicalDetails rows={[{id:1,diagnosis:'Flu',family_history:{},vaccination_history:[]}]}/>);
    expect(container.innerHTML).toBe('');
  });
  it('shows vitals, BMI and allergies',()=>{
    render(<RecordClinicalDetails rows={[{id:2,patient:'Pat',diagnosis:'Asthma',icd10_code:'J45',pulse:80,bmi:24.2,adverse_reactions:'Penicillin',family_history:{diabetes:true},vaccination_history:[],created_at:'2026-10-01T10:00:00Z'}]}/>);
    expect(screen.getByText(/ICD-10 J45/)).toBeTruthy();
    expect(screen.getByText('24.2')).toBeTruthy();
    expect(screen.getByText(/Penicillin/)).toBeTruthy();
    expect(screen.getByText(/diabetes/)).toBeTruthy();
  });
});

describe('AuditLog',()=>{
  it('loads entries from the API',async()=>{
    const api={get:vi.fn().mockResolvedValue({data:[{id:1,username:'admin',method:'POST',path:'/api/bills/',status_code:201,ip_address:'127.0.0.1',created_at:'2026-10-01T10:00:00Z'}]})};
    render(<AuditLog api={api}/>);
    await waitFor(()=>expect(screen.getByText('/api/bills/')).toBeTruthy());
    expect(api.get).toHaveBeenCalledWith('/audit-logs/');
  });
});
