// Complete grading flow on isolated fixture records only. No external AI calls.
import {readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const fixture=JSON.parse(await readFile(join(tmpdir(),'hub-grade-browser-fixture.json'),'utf8'));
const targets=await(await fetch('http://127.0.0.1:9223/json/list')).json();
const target=targets.find(t=>t.type==='page'&&(t.url==='about:blank'||t.url.startsWith('http://127.0.0.1:8000/')));
if(!target) throw new Error('An isolated Chrome test profile is required');
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
let identity=0;const pending=new Map(),errors=[];
socket.onmessage=event=>{const value=JSON.parse(event.data);if(value.method==='Runtime.exceptionThrown')errors.push(value.params.exceptionDetails.exception?.description||value.params.exceptionDetails.text);const task=pending.get(value.id);if(task){pending.delete(value.id);value.error?task.reject(value.error):task.resolve(value.result);}};
const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++identity;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
const evaluate=async expression=>{const result=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
const until=async expression=>{for(let n=0;n<150;n++){if(await evaluate(expression))return;await new Promise(resolve=>setTimeout(resolve,150));}throw new Error('Timed out: '+expression);};
const url=path=>'http://127.0.0.1:8000'+path;
const navigate=async(path,selector)=>{await call('Page.navigate',{url:url(path)});await until(`!!document.querySelector(${JSON.stringify(selector)}) && document.readyState==='complete'`);};
const signIn=async role=>{
  await navigate('/comptes/connexion/','[name=csrfmiddlewaretoken]');
  await evaluate(`(async()=>{const form=[...document.forms].find(f=>new URL(f.action).pathname===${JSON.stringify(fixture.logout_url)});if(form)await fetch(form.action,{method:'POST',body:new FormData(form)});})()`);
  await navigate('/comptes/connexion/','[name=username]');
  await evaluate(`(async()=>{await fetch('/comptes/connexion/',{method:'POST',body:new URLSearchParams({username:${JSON.stringify(fixture[role].username)},password:${JSON.stringify(fixture[role].password)},csrfmiddlewaretoken:document.querySelector('[name=csrfmiddlewaretoken]').value})});})()`);
};
const submit=async(path,answers)=>{
  await navigate(path,'#exercise-answer-form');
  await evaluate(`(()=>{${JSON.stringify(answers)}.forEach((answer,i)=>{const fields=[...document.querySelectorAll('[name="reponse_'+i+'"]')];const field=fields.find(f=>f.tagName==='TEXTAREA'||f.value===answer);if(!field)throw new Error('Answer field missing');if(field.tagName==='TEXTAREA')field.value=answer;else field.checked=true;});document.getElementById('exercise-answer-form').requestSubmit();})()`);
};
const averageIs=number=>`document.body.textContent.replace(/\\s+/g,' ').includes('Moyenne générale : ${number},00 / 20')`;
try{
  await call('Runtime.enable');await call('Network.enable');await call('Network.setCacheDisabled',{cacheDisabled:true});
  await call('Emulation.setDeviceMetricsOverride',{width:1600,height:1000,deviceScaleFactor:1,mobile:false});
  await signIn('student');
  await submit(fixture.exercise_url,['HTML','HTML']);
  await until(`document.body.textContent.includes('Note enregistrée : 10,00')`);
  const lock=await evaluate(`({locked:[...document.querySelectorAll('#exercise-answer-form input[type=radio]')].every(f=>f.disabled),hints:document.querySelectorAll('[data-exercise-help="hint"]').length})`);
  if(!lock.locked||lock.hints)throw new Error(JSON.stringify(lock));
  const replay=await evaluate(`(async()=>{const form=document.getElementById('exercise-answer-form');const response=await fetch(location.pathname,{method:'POST',body:new URLSearchParams({csrfmiddlewaretoken:form.querySelector('[name=csrfmiddlewaretoken]').value,exercise_revision:form.dataset.revision,attempt_number:'1',reponse_0:'HTML',reponse_1:'CSS'})});return(await response.text()).includes('Note enregistrée : 10,00');})()`);
  if(!replay)throw new Error('Repeat changed the mark');
  await submit(fixture.open_url,['HTML organise le contenu.']);
  await until(`document.body.textContent.includes('Note en attente de validation')`);
  await navigate(fixture.student_url,'.table');await until(averageIs(10));
  await signIn('teacher');await navigate(fixture.teacher_url,'.table');
  const openCopy=await evaluate(`[...document.querySelectorAll('tr')].find(r=>r.textContent.includes('Question ouverte de test')).querySelector('a').pathname`);
  await evaluate(`[...document.querySelectorAll('tr')].find(r=>r.textContent.includes('QCM de test')).querySelector('form[action$="/autorisation/"] input[value="allow"]').form.requestSubmit()`);
  await until(`!!document.querySelector('form[action$="/autorisation/"] input[value="revoke"]')`);
  await signIn('student');await submit(fixture.exercise_url,['HTML','CSS']);
  await until(`document.body.textContent.includes('Note enregistrée : 20,00')`);
  await navigate(fixture.student_url,'.table');await until(averageIs(20));
  await signIn('teacher');await navigate(openCopy,'#teacher-mark-form');
  await evaluate(`document.getElementById('id_note').value='14';document.getElementById('id_commentaire').value='Correction navigateur';document.getElementById('teacher-mark-form').requestSubmit()`);
  await until(`document.body.textContent.includes('Note enregistrée : 14,00')`);
  await signIn('student');await navigate(fixture.student_url,'.table');await until(averageIs(17));
  const final=await evaluate(`({horizontalOverflow:document.documentElement.scrollWidth>innerWidth+1})`);
  if(final.horizontalOverflow||errors.length)throw new Error(JSON.stringify({final,errors}));
  console.log(JSON.stringify({firstMark:10,repeatBlocked:replay,teacherGrantedOneRetake:true,secondMark:20,teacherOpenMark:14,finalAverage:17,noHints:true,browserErrors:0}));
}finally{socket.close();}
