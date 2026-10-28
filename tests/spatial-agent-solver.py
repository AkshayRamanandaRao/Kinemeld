"""Run a locally proposed spatial assembly with real MBDyn; never invokes a solver inside the agent."""
from copy import deepcopy
from pathlib import Path
import json,math,sys
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'backend'))
import agent,models,solver
from test_agent import assistant,service

model=deepcopy(next(item['model'] for item in models.EXAMPLES if item['id']=='spatial-revolute'))
edits=[{'collection':'bodies','operation':'update','id':'arm','values':{'mass':2.}},
       {'collection':'rotationalElements','operation':'add','id':'spring','values':{'joint':'hinge','stiffness':1.,'damping':.1,'restAngleDeg':0.}},
       {'collection':'jointTorques','operation':'add','id':'motor','values':{'joint':'hinge','amplitude':.1,'frequencyHz':1.,'offset':0.}}]
request={'message':'Set the mass and add the spring and motor, then run it.','model':model,'chatModel':'test-local:4b'}
with service([assistant([('edit_spatial_assembly',{'edits':edits}),('validate_model',{}),('request_run',{})]),assistant()]) as (client,_):
    proposal=agent.chat(request,client)
assert proposal['runRequested'] and proposal['validation']['valid'],proposal
result,status=solver.run(proposal['proposedModel'])
assert status==200 and result['ok'] and result['source']=='MBDyn',(status,result)
assert result['samples'] and all(math.isfinite(sample['rotationalStates'][0]['torque']) and math.isfinite(sample['actuationStates'][0]['torque']) for sample in result['samples'])
report={'ok':True,'source':'MBDyn','runId':result['runId'],'sampleCount':len(result['samples']),'checks':['owned local model HTTP tool loop','atomic spatial graph edits','explicit run authorization','real MBDyn run outside agent module','rotational and actuation output']}
path=root/'verification'/'spatial-agent.json';path.write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report))
