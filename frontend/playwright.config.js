import {defineConfig} from '@playwright/test';

// Critical user journeys against a real backend and a throwaway seeded database.
export default defineConfig({
  testDir:'./e2e',
  testMatch:'**/*.e2e.js',
  timeout:60_000,
  workers:1,
  reporter:[['list'],['html',{open:'never'}]],
  use:{baseURL:'http://localhost:5175',trace:'retain-on-failure',screenshot:'only-on-failure'},
  webServer:[
    {command:'node e2e/start-backend.mjs',url:'http://127.0.0.1:8001/api/public-directory/',timeout:240_000,reuseExistingServer:false},
    {command:'npx vite --port 5175 --strictPort',url:'http://localhost:5175',env:{VITE_API_URL:'http://127.0.0.1:8001/api'},timeout:60_000,reuseExistingServer:false},
  ],
});
