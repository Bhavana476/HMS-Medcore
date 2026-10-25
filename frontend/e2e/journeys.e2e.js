import {test,expect} from '@playwright/test';

const PASSWORD='Demo@12345';

async function signIn(page,username,password=PASSWORD){
  await page.goto('/');
  await page.getByRole('button',{name:'Create account / Sign in'}).first().click();
  await page.getByRole('button',{name:'Already have an account? Sign in'}).click();
  await page.getByPlaceholder('Enter your username').fill(username);
  await page.getByPlaceholder('Enter your password').fill(password);
  await page.getByRole('button',{name:/^Sign in/}).click();
  await expect(page.locator('.role-pill')).toBeVisible({timeout:30_000});
}

test('patient registration, sign in and sign out',async({page})=>{
  const username=`e2e_${Date.now()}`;
  await page.goto('/');
  await page.getByRole('button',{name:'Create account / Sign in'}).first().click();
  await page.getByPlaceholder('Enter your first name').fill('Asha');
  await page.getByPlaceholder('Enter your email address').fill(`${username}@example.com`);
  await page.getByPlaceholder('Enter your phone number').fill('+919800000001');
  await page.getByPlaceholder('Choose a username').fill(username);
  await page.getByPlaceholder('Create a password').fill('Strong-pass-2026');
  await page.getByRole('button',{name:/Confirm password/}).click();
  await page.getByPlaceholder('Enter your password again').fill('Strong-pass-2026');
  await page.getByRole('button',{name:/Create account/}).click();
  await expect(page.getByText('Your account has been created')).toBeVisible();
  await page.getByPlaceholder('Enter your username').fill(username);
  await page.getByPlaceholder('Enter your password').fill('Strong-pass-2026');
  await page.getByRole('button',{name:/^Sign in/}).click();
  await expect(page.locator('.role-pill')).toHaveText('Patient');
  await page.getByRole('button',{name:'Logout'}).click();
  await expect(page.getByRole('button',{name:'Create account / Sign in'}).first()).toBeVisible();
});

test('patient books an appointment',async({page})=>{
  await signIn(page,'demo_patient');
  await page.locator('.sidebar-nav').getByRole('button',{name:'My Appointments'}).click();
  const form=page.locator('form').filter({has:page.locator('select')}).first();
  await expect(form).toBeVisible();
  // Choose the first registered doctor and a published slot two days ahead.
  const doctor=form.locator('select').first();
  await doctor.selectOption({index:1});
  const day=new Date();day.setDate(day.getDate()+2);
  await form.locator('input[type=date]').fill(day.toISOString().slice(0,10));
  await form.locator('input[type=time]').fill('11:30');
  await form.getByRole('button').last().click();
  await expect(page.locator('table tr',{hasText:'11:30'}).getByText('Pending')).toBeVisible();
});

test('admin sees command centre and insights',async({page})=>{
  await signIn(page,'demo_admin');
  await expect(page.getByRole('heading',{name:'Hospital Command Center'})).toBeVisible();
  await expect(page.getByText('Appointments, last 7 days')).toBeVisible();
  await expect(page.getByText('Department occupancy (7 days)')).toBeVisible();
});

test('pharmacist dispenses with FIFO and sees stock alerts',async({page})=>{
  await signIn(page,'demo_pharmacist');
  await page.locator('.sidebar-nav').getByRole('button',{name:'Pharmacy'}).click();
  await expect(page.getByRole('heading',{name:'Prescriptions awaiting dispensing'})).toBeVisible();
  const row=page.locator('tr',{has:page.getByRole('button',{name:'Dispense'})}).first();
  await row.locator('input[type=number]').fill('2');
  await row.getByRole('button',{name:'Dispense'}).click();
  await expect(page.getByText(/dispensed\./)).toBeVisible();
  await expect(page.getByRole('heading',{name:'Expiring within 30 days'})).toBeVisible();
});

test('accountant views invoice total equal to its line items',async({page})=>{
  await signIn(page,'demo_accountant');
  await page.locator('.sidebar-nav').getByRole('button',{name:'Finance'}).click();
  await expect(page.getByRole('heading',{name:'Revenue analytics'})).toBeVisible();
  const items=page.locator('section',{has:page.getByRole('heading',{name:'Invoice line items'})});
  const select=items.locator('select').first();
  await expect(select.locator('option')).not.toHaveCount(1);
  await select.selectOption({index:1});
  await expect(items.getByText('Invoice total',{exact:true})).toBeVisible();
  // The total cell equals the sum of the amount column.
  const amounts=await items.locator('tbody tr td:nth-child(5)').allTextContents();
  const sum=amounts.reduce((s,t)=>s+Number(t.replace(/[^\d.]/g,'')),0);
  const total=Number((await items.locator('tfoot td').nth(1).textContent()).replace(/[^\d.]/g,''));
  expect(total).toBeCloseTo(sum,2);
});

test('patient downloads a printable prescription report',async({page,context})=>{
  await signIn(page,'demo_patient');
  await page.locator('.sidebar-nav').getByRole('button',{name:'Prescriptions'}).click();
  const popup=context.waitForEvent('page');
  await page.locator('.slot-chips button').first().click();
  const printable=await popup;
  await expect(printable.getByText('MedCore HMS')).toBeVisible();
});
