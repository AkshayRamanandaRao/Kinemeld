"""Owned Studio and local-Ollama fixture for the browser AI-authoring test."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import sys
import threading

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'backend'))
import agent
import server

class ModelService(BaseHTTPRequestHandler):
    def log_message(self,*_): pass
    def respond(self,value):
        data=json.dumps(value).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_GET(self): self.respond({'models':[{'name':'fixture:tools','size':2000000}]})
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path=='/api/show': return self.respond({'capabilities':['tools'],'thinking':{'values':[False],'default':False}})
        messages=body['messages']
        if messages[-1]['role']=='tool': return self.respond({'done':True,'done_reason':'stop','message':{'role':'assistant','content':'Review the staged model.','tool_calls':[]}})
        user=next(message['content'] for message in reversed(messages) if message['role']=='user')
        if user.startswith('Oleo'):
            edits=[{'collection':'forces','operation':'update','id':'oleo','values':{'pressure':1200000.}}]
            calls=[('edit_spatial_assembly',{'edits':edits})]
        elif user.startswith('Motion'):
            edits=[{'collection':'joints','operation':'update','id':'fixture','values':{'motion':{'amplitude':.025,'frequencyHz':1.}}}]
            calls=[('edit_spatial_assembly',{'edits':edits})]
        elif user.startswith('Damping'):
            edits=[{'collection':'contacts','operation':'update','id':'floor','values':{'damping':10.}}]
            calls=[('edit_spatial_assembly',{'edits':edits})]
        elif user.startswith('FreeBody'):
            edits=[{'collection':'bodies','operation':'copy','id':'payload','sourceId':'arm','values':{'name':'Free payload'}},
                   {'collection':'bodies','operation':'update','id':'payload','values':{'pose':{'x':1.5}}}]
            calls=[('edit_spatial_assembly',{'edits':edits})]
        elif user.startswith('FrameContact'):
            edits=[{'collection':'frames','operation':'add','id':'tip','values':{'name':'Tip','body':'arm','translation':{'x':0.,'y':0.,'z':.5},'rotation':{'rx':0.,'ry':0.,'rz':0.}}},
                   {'collection':'contacts','operation':'add','id':'floor','values':{'body':'arm','center':{'x':0.,'y':0.,'z':0.},'radius':.1,'planePoint':{'x':0.,'y':0.,'z':-10.},'planeNormal':{'x':0.,'y':0.,'z':1.},'stiffness':100.}}]
            calls=[('edit_spatial_assembly',{'edits':edits})]
        elif user.startswith('COM'):
            edits=[{'collection':'bodies','operation':'update','id':'arm','values':{'centerOfMass':{'x':.02,'y':-.01,'z':.03}}}]
            calls=[('edit_spatial_assembly',{'edits':edits})]
        elif user.startswith('Tensor'):
            edits=[{'collection':'bodies','operation':'update','id':'arm','values':{'inertia':{'xy':.01,'xz':-.01,'yz':.005}}}]
            calls=[('edit_spatial_assembly',{'edits':edits})]
        elif user.startswith('Create'):
            edits=[{'collection':'bodies','operation':'update','id':'arm','values':{'mass':2.}}, {'collection':'rotationalElements','operation':'add','id':'torsion','values':{'joint':'hinge','stiffness':1.,'damping':.1,'restAngleDeg':0.}}]
            calls=[('edit_spatial_assembly',{'edits':edits}),('set_spatial_gravity',{'values':{'x':1.}})]
            if 'then run' in user.lower(): calls.append(('request_run',{}))
        elif user.startswith('Explain'):
            edits=[{'collection':'bodies','operation':'update','id':'arm','values':{'mass':2.}}]
            calls=[('edit_spatial_assembly',{'edits':edits}),('request_run',{})]
        else:
            edits=[{'collection':'bodies','operation':'update','id':'arm','values':{'mass':-2.}}, {'collection':'rotationalElements','operation':'add','id':'bad','values':{'joint':'missing','stiffness':1.,'damping':.1,'restAngleDeg':0.}}]
            calls=[('edit_spatial_assembly',{'edits':edits}),('request_run',{})]
        self.respond({'done':True,'done_reason':'stop','message':{'role':'assistant','content':'Preparing the requested changes.','tool_calls':[{'function':{'name':name,'arguments':args}} for name,args in calls]}})

fixture=ThreadingHTTPServer(('127.0.0.1',0),ModelService)
threading.Thread(target=fixture.serve_forever,daemon=True).start()
agent.configuration=lambda:f'http://127.0.0.1:{fixture.server_port}'
server.TOUR_PREFERENCE=root/'runs'/'spatial-agent-test-tour.json'
app=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
print(json.dumps({'port':app.server_port}),flush=True)
try:app.serve_forever()
finally:app.server_close();fixture.shutdown();fixture.server_close()
