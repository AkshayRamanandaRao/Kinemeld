"""Optional live-Ollama semantic checks; no proposed changes are applied or run."""
from copy import deepcopy
from pathlib import Path
import json,sys,time
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'backend'))
import agent,models
selection=sys.argv[1] if len(sys.argv)>1 else 'qwen3.5:4b'
model=deepcopy(next(item['model'] for item in models.EXAMPLES if item['id']=='spatial-revolute'))
requests=[('mass','Set the mass of body arm to 2 kilograms. Do not run.'),('copy','Copy body arm to a new body named payload with the same mass, inertia, pose and velocity, and connect arm to payload with a spherical joint ball using zero local anchors on both bodies. Do not run.')]
results=[]
for name,message in requests:
    original=deepcopy(model);start=time.monotonic()
    try:
        answer=agent.chat({'message':message,'model':model,'chatModel':selection});candidate=answer['proposedModel'] or model
        if name=='mass': correct=candidate['bodies'][0]['mass']==2
        else:
            payload=next((body for body in candidate['bodies'] if body['id']=='payload'),None);joint=next((item for item in candidate['joints'] if item['id']=='ball'),None)
            correct=bool(payload and joint and all(payload[key]==model['bodies'][0][key] for key in ('mass','inertia','pose','velocity')) and joint['type']=='spherical' and joint['a']=='arm' and joint['b']=='payload' and joint['anchorA']=={'x':0,'y':0,'z':0} and joint['anchorB']=={'x':0,'y':0,'z':0})
        result={'case':name,'ok':bool(correct and answer['validation']['valid'] and not answer['runRequested'] and model==original),'actions':answer['actions'],'runRequested':answer['runRequested']}
    except (agent.AgentError,KeyError,TypeError,ValueError) as exc:result={'case':name,'ok':False,'error':str(exc)}
    result['seconds']=round(time.monotonic()-start,2);results.append(result)
report={'ok':all(item['ok'] for item in results),'model':selection,'cases':results,'scope':'Actual local-model inference only; no draft was applied or solver run.'}
path=root/'verification'/'spatial-agent-live.json';path.write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report))
if not report['ok']:raise SystemExit(1)
