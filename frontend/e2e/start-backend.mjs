// Starts Django on port 8001 with a fresh throwaway database seeded with demo data.
import {spawnSync,spawn} from 'node:child_process';
import {rmSync} from 'node:fs';
import {resolve} from 'node:path';

const backend=resolve(import.meta.dirname,'../../backend');
const python=process.env.PYTHON||(process.platform==='win32'?resolve(backend,'.venv/Scripts/python.exe'):'python');
const db=resolve(backend,'e2e.sqlite3');
rmSync(db,{force:true});
const env={...process.env,SQLITE_PATH:db,CORS_ALLOWED_ORIGINS:'http://localhost:5175,http://127.0.0.1:5175',FIELD_ENCRYPTION_KEY:''};
for(const args of [['migrate','--noinput'],['seed_prd_demo','--yes']]){
  const r=spawnSync(python,['manage.py',...args],{cwd:backend,env,stdio:'inherit'});
  if(r.status!==0)process.exit(r.status||1);
}
spawn(python,['manage.py','runserver','127.0.0.1:8001','--noreload'],{cwd:backend,env,stdio:'inherit'});
