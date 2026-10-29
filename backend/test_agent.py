"""Exercise the real local HTTP/tool boundary with a deterministic owned model service."""

from contextlib import contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import unittest

import agent
import models
import source_catalog


def assistant(calls=None, content="Prepared the requested model.", **extra):
    return {"done": True, "done_reason": "stop", "message": {"role": "assistant", "content": content,
            "tool_calls": [{"function": {"name": name, "arguments": args}} for name, args in (calls or [])]}, **extra}


@contextmanager
def service(responses, **options):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, value):
            payload = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionError):
                pass

        def do_GET(self):
            requests.append((self.path, None))
            self.reply({"models": options.get("models", [{"name": "test-local:4b", "size": 2000000}, {"name": "x:cloud", "size": 2000000}])})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body))
            if self.path == "/api/show":
                self.reply(options.get("show", {"capabilities": ["completion", "tools", "thinking"], "thinking": {"values": [False, True], "default": True}}))
            else:
                time.sleep(options.get("delay", 0))
                self.reply(responses.pop(0))
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield agent.Ollama(f"http://127.0.0.1:{server.server_port}"), requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


class AgentBoundaryTests(unittest.TestCase):
    def request(self, message="Set the pendulum length to 2 m."):
        return {"message": message, "model": deepcopy(models.EXAMPLES[0]["model"]), "chatModel": "test-local:4b"}

    def test_real_http_tool_loop_proposes_valid_edits_without_mutating_current_project(self):
        body = self.request("Set up an oscillator with a 2 kg mass, then run it.")
        original = deepcopy(body)
        responses = [assistant([("list_examples", {})]), assistant([("load_example", {"id": "mass-spring"})]),
                     assistant([("set_parameters", {"values": {"mass": 2}}), ("validate_model", {}), ("request_run", {})]), assistant()]
        with service(responses) as (client, requests):
            result = agent.chat(body, client)
        self.assertEqual(body, original)
        self.assertEqual(result["actions"], [{"type": "load_example", "id": "mass-spring"}, {"type": "set_parameters", "values": {"mass": 2}}])
        self.assertEqual(result["proposedModel"]["parameters"]["mass"], 2)
        self.assertTrue(result["validation"]["valid"])
        self.assertTrue(result["runRequested"])
        calls = [body for path, body in requests if path == "/api/chat"]
        self.assertIs(calls[0]["think"], False)
        self.assertTrue(any(item.get("role") == "tool" for item in calls[-1]["messages"]))
        self.assertFalse(any(path not in ("/api/tags", "/api/show", "/api/chat") for path, _ in requests))

    def test_malicious_unknown_and_cross_family_tools_have_no_effect(self):
        body = self.request("Explain the current model. Do not run it.")
        responses = [assistant([("shell", {"command": "anything"}), ("set_parameters", {"values": {"sprungMass": 600}}),
                                ("set_parameters", {"values": {"mass": True}}), ("request_run", {})]), assistant()]
        with service(responses) as (client, _):
            result = agent.chat(body, client)
        self.assertEqual(result["actions"], [])
        self.assertIsNone(result["proposedModel"])
        self.assertFalse(result["runRequested"])
        self.assertTrue(all(not item["ok"] for item in result["toolResults"]))

    def test_invalid_edit_diagnostics_and_repair_are_preserved(self):
        responses = [assistant([("set_parameters", {"values": {"length": -2}})]),
                     assistant([("set_parameters", {"values": {"length": 2}})]), assistant()]
        with service(responses) as (client, _):
            result = agent.chat(self.request(), client)
        self.assertEqual(result["proposedModel"]["parameters"]["length"], 2)
        self.assertFalse(result["toolResults"][0]["ok"])
        self.assertEqual(result["toolResults"][0]["result"]["validation"]["issues"][0]["field"], "parameters.length")

    def test_pinned_source_load_keeps_provenance_and_rejects_override(self):
        responses = [assistant([("load_example", {"id": "srscm"})]), assistant([("set_parameters", {"values": {"mass": 2}})]), assistant()]
        with service(responses) as (client, _):
            result = agent.chat(self.request("Prepare the spatial slider crank source example."), client)
        expected = source_catalog.resolve_entry("srscm")
        self.assertEqual(result["proposedModel"]["sourceRevision"], expected["source"]["revision"])
        self.assertEqual(result["proposedModel"]["sourceHashes"], [item["sha256"] for item in expected["files"]])
        self.assertEqual(result["proposedModel"]["parameters"], {})
        self.assertFalse(result["toolResults"][1]["ok"])
        self.assertFalse(result["runRequested"])

    def test_missing_and_disguised_remote_models_are_rejected_before_inference(self):
        for options, code in [({"models": []}, "model_unavailable"), ({"show": {"capabilities": ["tools"], "remote_host": "https://example.test"}}, "model_unsupported")]:
            with self.subTest(code=code), service([], **options) as (client, requests):
                with self.assertRaises(agent.AgentError) as error:
                    agent.chat(self.request(), client)
                self.assertEqual(error.exception.code, code)
                self.assertFalse(any(path == "/api/chat" for path, _ in requests))

    def test_malformed_or_incomplete_generation_never_returns_partial_edits(self):
        invalids = [assistant(done_reason="length"), assistant(done=False), {"done": True, "message": {"role": "assistant", "tool_calls": [{"function": "not-an-object"}]}},
                    {"done": True, "message": {"role": "assistant", "tool_calls": "bad"}}]
        for bad in invalids:
            body = self.request()
            before = deepcopy(body)
            with self.subTest(response=bad), service([assistant([("set_parameters", {"values": {"length": 2}})]), bad]) as (client, _):
                with self.assertRaises(agent.AgentError):
                    agent.chat(body, client)
            self.assertEqual(body, before)

    def test_duplicate_nonfinite_arguments_and_extra_fields_do_not_mutate(self):
        responses = [assistant([("set_parameters", '{"values":{"mass":1,"mass":2}}'),
                                ("set_parameters", '{"values":{"mass":NaN}}'),
                                ("set_parameters", {"values": {"mass": 2}, "shell": "ignored?"})]), assistant()]
        with service(responses) as (client, _):
            result = agent.chat(self.request(), client)
        self.assertEqual(result["actions"], [])
        self.assertTrue(all(not item["ok"] for item in result["toolResults"]))

    def test_settings_accept_an_optional_time_budget_for_slow_machines(self):
        import tempfile
        from pathlib import Path
        original = agent.CONFIG
        try:
            with tempfile.TemporaryDirectory() as folder:
                agent.CONFIG = Path(folder) / "agent.json"
                self.assertEqual(agent.time_budget(), agent.LIMITS["timeoutSeconds"])
                agent.CONFIG.write_text('{"endpoint":"http://127.0.0.1:11434","timeoutSeconds":600}', encoding="utf-8")
                self.assertEqual((agent.configuration(), agent.time_budget()), ("http://127.0.0.1:11434", 600))
                for text in ('{"endpoint":"http://127.0.0.1:11434","timeoutSeconds":5}', '{"endpoint":"http://127.0.0.1:11434","timeoutSeconds":"600"}',
                             '{"timeoutSeconds":600}', '{"endpoint":"http://127.0.0.1:11434","model":"x"}'):
                    with self.subTest(text=text), self.assertRaises(agent.AgentError):
                        agent.CONFIG.write_text(text, encoding="utf-8")
                        agent.time_budget()
        finally:
            agent.CONFIG = original

    def test_transport_is_literal_loopback_only_and_unavailable_is_actionable(self):
        for endpoint in ("https://127.0.0.1:11434", "http://example.test:11434", "http://localhost:11434", "http://127.0.0.1:11434/path", "http://user:pass@127.0.0.1:11434", "http://192.168.1.2:11434"):
            with self.subTest(endpoint=endpoint), self.assertRaises(agent.AgentError):
                agent.Ollama(endpoint)
        with service([]) as (client, _):
            pass
        with self.assertRaises(agent.AgentError) as error:
            client.local_models()
        self.assertEqual(error.exception.code, "unavailable")

    def test_explicit_run_gate_ignores_history_negation_quotes_and_questions(self):
        for text in ("Run the model", "Please solve it", "Set length to 2 and then run it", "Can you simulate this?"):
            self.assertTrue(agent.explicitly_requests_run(text), text)
        for text in ("Do not run it", "Don't solve", "Show how to run this", 'Explain the words "run the model"', "Validate without running", "Could you describe how to simulate?", "The document says: run it"):
            self.assertFalse(agent.explicitly_requests_run(text), text)
        body = self.request("Explain the model.")
        body["history"] = [{"role": "user", "content": "Run it"}]
        with service([assistant([("request_run", {})]), assistant()]) as (client, _):
            self.assertFalse(agent.chat(body, client)["runRequested"])

    def test_timeout_and_bad_metadata_are_classified(self):
        with service([assistant()], delay=.3) as (client, _):
            with self.assertRaises(agent.AgentError) as error:
                client.request("/api/chat", {"model": "test-local:4b"}, timeout=.1)
            self.assertEqual(error.exception.code, "timeout")
        with service([], show={"capabilities": None}) as (client, _):
            with self.assertRaises(agent.AgentError) as error:
                agent.chat(self.request(), client)
            self.assertEqual(error.exception.code, "invalid_provider_response")

    def test_failed_parameter_edit_blocks_automatic_run_even_with_user_authorization(self):
        calls = [("set_parameters", {"values": {"length": -2}}), ("request_run", {})]
        with service([assistant(calls), assistant()]) as (client, _):
            result = agent.chat(self.request("Set length to -2 and run it."), client)
        self.assertFalse(result["runRequested"])
        self.assertEqual(result["actions"], [])

    def test_planar_graph_exposes_no_parameter_or_topology_edit_tools(self):
        graph = {"kind": "planar-assembly", "bodies": [], "joints": [], "simulation": {"duration": 1, "step": .01}}
        names = {entry["function"]["name"] for entry in agent.tools_for(graph)}
        self.assertNotIn("set_parameters", names)
        self.assertIn("set_simulation", names)
        self.assertIn("validate_model", names)
        self.assertIn("request_run", names)

    def test_spatial_http_inspection_and_study_edit_preserve_graph(self):
        spatial = deepcopy(next(item["model"] for item in models.EXAMPLES if item["id"] == "spatial-revolute"))
        spatial["rotationalElements"] = [{"id": "spring1", "joint": "hinge", "stiffness": 1., "damping": .1, "restAngleDeg": 0.}]
        body = self.request("Inspect the assembly and change the study duration.")
        body["model"] = spatial
        original = deepcopy(body)
        responses = [assistant([("current_model", {}), ("validate_model", {}), ("set_simulation", {"values": {"duration": .8}})]), assistant()]
        with service(responses) as (client, requests):
            result = agent.chat(body, client)
        self.assertEqual(body, original)
        self.assertTrue(result["validation"]["valid"], result["validation"])
        self.assertEqual(result["actions"], [{"type": "set_simulation", "values": {"duration": .8}}])
        expected = deepcopy(spatial); expected["simulation"]["duration"] = .8
        self.assertEqual(result["proposedModel"], expected)
        self.assertEqual(result["toolResults"][0]["result"]["model"], spatial)
        calls = [request for path, request in requests if path == "/api/chat"]
        names = {entry["function"]["name"] for entry in calls[0]["tools"]}
        self.assertNotIn("set_parameters", names)
        self.assertIn("set_simulation", names)

    def test_spatial_example_load_and_forged_graph_edit(self):
        responses = [assistant([("load_example", {"id": "spatial-revolute"})]),
                     assistant([("set_parameters", {"values": {"gravity": 2}}),
                                ("set_simulation", {"values": {"bodies": []}}),
                                ("edit_joint", {"joint": "hinge"})]), assistant()]
        with service(responses) as (client, requests):
            result = agent.chat(self.request("Load a spatial assembly."), client)
        original = next(item["model"] for item in models.EXAMPLES if item["id"] == "spatial-revolute")
        self.assertEqual(result["proposedModel"], original)
        self.assertEqual(result["actions"], [{"type": "load_example", "id": "spatial-revolute"}])
        self.assertTrue(all(not item["ok"] for item in result["toolResults"][1:]))
        calls = [request for path, request in requests if path == "/api/chat"]
        self.assertNotIn("set_parameters", {entry["function"]["name"] for entry in calls[1]["tools"]})
        example = next(item for item in agent.example_list() if item["id"] == "spatial-revolute")
        self.assertTrue(example["editable"])
        self.assertEqual(example["parameterBounds"], {})

    def test_spatial_atomic_graph_authoring_via_http(self):
        spatial = deepcopy(next(item["model"] for item in models.EXAMPLES if item["id"] == "spatial-revolute"))
        body = deepcopy(spatial["bodies"][0]); body.pop("id"); body["name"]="Payload"
        v = lambda x,y,z: {"x":x,"y":y,"z":z}
        edits=[
            {"collection":"bodies","operation":"add","id":"payload-1","values":body},
            {"collection":"joints","operation":"add","id":"ball","values":{"type":"spherical","a":"arm","b":"payload-1","anchorA":v(0,0,0),"anchorB":v(0,0,0)}},
            {"collection":"forces","operation":"add","id":"spring","values":{"type":"linear-spring-damper","a":"ground","b":"arm","anchorA":v(0,0,0),"anchorB":v(0,0,0),"stiffness":1.,"damping":.1,"restLength":1.}},
            {"collection":"loads","operation":"add","id":"load","values":{"body":"arm","frame":"body","point":v(0,0,0),"force":v(1,0,0),"torque":v(0,0,0),"offset":1.,"amplitude":0.,"frequencyHz":1.}},
            {"collection":"rotationalElements","operation":"add","id":"torsion","values":{"joint":"hinge","stiffness":1.,"damping":.1,"restAngleDeg":0.}},
            {"collection":"jointTorques","operation":"add","id":"drive","values":{"joint":"hinge","offset":0.,"amplitude":1.,"frequencyHz":1.}},
            {"collection":"bodies","operation":"update","id":"arm","values":{"mass":2.,"inertia":{"xx":.2,"yy":.2,"zz":.2}}},
        ]
        body_request=self.request("Add a payload and its joint, springs and load, then run it.");body_request["model"]=spatial;original=deepcopy(body_request)
        responses=[assistant([("edit_spatial_assembly",{"edits":edits}), ("set_spatial_gravity",{"values":{"x":1.}}), ("validate_model",{}), ("request_run",{})]), assistant()]
        with service(responses) as (client,requests): result=agent.chat(body_request,client)
        self.assertEqual(body_request,original)
        self.assertTrue(result["validation"]["valid"],result["validation"])
        self.assertTrue(result["runRequested"])
        self.assertEqual([item["type"] for item in result["actions"]],["edit_spatial_assembly","set_spatial_gravity"])
        self.assertEqual(result["proposedModel"]["bodies"][0]["mass"],2.)
        self.assertEqual(result["proposedModel"]["parameters"]["gravity"],{"x":1.,"y":0,"z":-9.81})
        self.assertEqual([item["id"] for item in result["proposedModel"]["bodies"]],["arm","payload-1"])
        for key in ("forces","loads","rotationalElements","jointTorques"):self.assertEqual(len(result["proposedModel"][key]),1)
        request=next(value for path,value in requests if path=="/api/chat")
        graph_tool=next(item for item in request["tools"] if item["function"]["name"]=="edit_spatial_assembly")
        schema=graph_tool["function"]["parameters"]["properties"]["edits"]
        self.assertEqual(schema["maxItems"],32)
        self.assertEqual({branch["properties"]["collection"]["enum"][0] for branch in schema["items"]["oneOf"]}, {"bodies","joints","forces","loads","rotationalElements","jointTorques","jointForces","contacts","frames"})
        self.assertTrue(all(branch["additionalProperties"] is False and branch["properties"]["values"]["additionalProperties"] is False for branch in schema["items"]["oneOf"]))

    def test_spatial_inertia_off_diagonal_updates_are_typed_and_validated(self):
        spatial=deepcopy(next(item["model"] for item in models.EXAMPLES if item["id"]=="spatial-revolute"))
        proposal=agent.Proposal(spatial,"Update the inertia tensor and do not run.")
        change={"collection":"bodies","operation":"update","id":"arm","values":{"inertia":{"xy":.01,"xz":-.01,"yz":.005}}}
        result=proposal.call("edit_spatial_assembly",{"edits":[change]})
        self.assertTrue(result["accepted"],result)
        self.assertEqual(result["model"]["bodies"][0]["inertia"]["xy"],.01)
        self.assertNotIn("xy",spatial["bodies"][0]["inertia"])
        bad=deepcopy(change);bad["values"]["inertia"]["xy"]=True
        with self.assertRaises(ValueError):proposal.call("edit_spatial_assembly",{"edits":[bad]})

    def test_spatial_center_of_mass_patch_initializes_legacy_bodies(self):
        spatial=deepcopy(next(item["model"] for item in models.EXAMPLES if item["id"]=="spatial-revolute"))
        proposal=agent.Proposal(spatial,"Offset the centre of mass and do not run.")
        change={"collection":"bodies","operation":"update","id":"arm","values":{"centerOfMass":{"x":.2}}}
        result=proposal.call("edit_spatial_assembly",{"edits":[change]})
        self.assertTrue(result["accepted"],result)
        self.assertEqual(result["model"]["bodies"][0]["centerOfMass"],{"x":.2,"y":0.,"z":0.})
        self.assertNotIn("centerOfMass",spatial["bodies"][0])
        bad=deepcopy(change);bad["values"]["centerOfMass"]["x"]=True
        with self.assertRaises(ValueError):proposal.call("edit_spatial_assembly",{"edits":[bad]})

    def test_spatial_joint_force_is_typed_and_validated(self):
        spatial=deepcopy(next(item["model"] for item in models.EXAMPLES if item["id"]=="spatial-prismatic"))
        joint=spatial["joints"][0]["id"]
        edit={"collection":"jointForces","operation":"add","id":"effort","values":{"joint":joint,"offset":1.,"amplitude":2.,"frequencyHz":1.}}
        proposal=agent.Proposal(spatial,"Add a time-varying axial force and do not run.")
        result=proposal.call("edit_spatial_assembly",{"edits":[edit]})
        self.assertTrue(result["accepted"],result)
        self.assertEqual(result["model"]["jointForces"][0]["amplitude"],2.)
        self.assertNotIn("jointForces",spatial)
        bad=deepcopy(edit);bad["id"]="bad";bad["values"]["amplitude"]=True
        with self.assertRaises(ValueError):proposal.call("edit_spatial_assembly",{"edits":[bad]})

    def test_oleo_agent_edits_are_typed_and_atomic(self):
        spatial=deepcopy(next(item['model'] for item in models.EXAMPLES if item['id']=='spatial-prismatic'))
        body=spatial['bodies'][0];pose=body['pose'];original=deepcopy(spatial)
        values={'type':'oleo-strut','a':'ground','b':body['id'],'anchorA':{'x':pose['x']-.5,'y':pose['y'],'z':pose['z']},'anchorB':{'x':0.,'y':0.,'z':0.},'restLength':.5,'pressure':100000.,'gasArea':.001,'gasVolume':.001,'gamma':1.4,'minLength':.3,'maxLength':.5,'stopStiffness':100.,'stopDamping':1.,'fluidArea':.001,'fluidDensity':850.,'dischargeCoefficient':.8,'compressionMeteringArea':.0002,'reboundMeteringArea':.0001}
        edit={'collection':'forces','operation':'add','id':'strut','values':values};proposal=agent.Proposal(spatial,'Add the specified oleo. Do not run.')
        result=proposal.call('edit_spatial_assembly',{'edits':[edit]});self.assertTrue(result['accepted'],result);self.assertEqual(spatial,original)
        update={'collection':'forces','operation':'update','id':'strut','values':{'pressure':120000.}}
        result=proposal.call('edit_spatial_assembly',{'edits':[update]});self.assertTrue(result['accepted'],result);before=deepcopy(proposal.model)
        incomplete=deepcopy(edit);incomplete['id']='incomplete';del incomplete['values']['pressure']
        self.assertFalse(proposal.call('edit_spatial_assembly',{'edits':[incomplete]})['accepted']);self.assertEqual(proposal.model,before)
        invalid=deepcopy(update);invalid['values']={'gasVolume':.0001};self.assertFalse(proposal.call('edit_spatial_assembly',{'edits':[invalid]})['accepted']);self.assertEqual(proposal.model,before)
        for value in (True,'120000',float('nan')):
            bad=deepcopy(update);bad['values']['pressure']=value
            with self.assertRaises(ValueError):proposal.call('edit_spatial_assembly',{'edits':[bad]})
            self.assertEqual(proposal.model,before)

    def test_prescribed_motion_add_update_and_invalid_batches_are_atomic(self):
        spatial=deepcopy(next(item['model'] for item in models.EXAMPLES if item['id']=='spatial-prismatic'))
        original=deepcopy(spatial); proposal=agent.Proposal(spatial,'Prescribe slider motion. Do not run.')
        edit={'collection':'joints','operation':'update','id':'guide','values':{'motion':{'amplitude':.025,'frequencyHz':1.}}}
        rejected=proposal.call('edit_spatial_assembly',{'edits':[edit]})
        self.assertFalse(rejected['accepted']);self.assertEqual(proposal.model,original)
        velocity={'collection':'bodies','operation':'update','id':'block','values':{'velocity':{'vx':0.,'vy':0.}}}
        result=proposal.call('edit_spatial_assembly',{'edits':[edit,velocity]})
        self.assertTrue(result['accepted'],result);self.assertEqual(result['model']['joints'][0]['motion'],{'amplitude':.025,'frequencyHz':1.})
        self.assertEqual(spatial,original)
        update=deepcopy(edit);update['values']['motion']={'amplitude':-.04}
        result=proposal.call('edit_spatial_assembly',{'edits':[update]})
        self.assertTrue(result['accepted'],result);self.assertEqual(result['model']['joints'][0]['motion'],{'amplitude':-.04,'frequencyHz':1.})
        old=deepcopy(proposal.model)
        for value in (True, float('nan'), '0.2'):
            bad=deepcopy(update);bad['values']['motion']['amplitude']=value
            with self.assertRaises(ValueError):proposal.call('edit_spatial_assembly',{'edits':[bad]})
            self.assertEqual(proposal.model,old)
        bad=deepcopy(update);bad['values']['motion']['frequencyHz']=1000
        self.assertFalse(proposal.call('edit_spatial_assembly',{'edits':[bad]})['accepted']);self.assertEqual(proposal.model,old)
        fresh=agent.Proposal(spatial,'Prescribe motion. Do not run.')
        with self.assertRaisesRegex(ValueError,'both amplitude and frequencyHz'):fresh.call('edit_spatial_assembly',{'edits':[update]})
        self.assertEqual(fresh.model,original)
        hinge=deepcopy(next(item['model'] for item in models.EXAMPLES if item['id']=='spatial-revolute'))
        hinge_proposal=agent.Proposal(hinge,'Prescribe motion. Do not run.');bad=deepcopy(edit);bad['id']='hinge'
        self.assertFalse(hinge_proposal.call('edit_spatial_assembly',{'edits':[bad]})['accepted']);self.assertEqual(hinge_proposal.model,hinge)

    def test_spatial_frame_and_contact_edits_are_atomic_and_validated(self):
        spatial=deepcopy(next(item["model"] for item in models.EXAMPLES if item["id"]=="spatial-revolute"))
        frame={"collection":"frames","operation":"add","id":"tip","values":{"name":"Tip", "body":"arm", "translation":{"x":0.,"y":0.,"z":.5},"rotation":{"rx":0.,"ry":0.,"rz":0.}}}
        contact={"collection":"contacts","operation":"add","id":"floor","values":{"body":"arm","center":{"x":0.,"y":0.,"z":0.},"radius":.1,"planePoint":{"x":0.,"y":0.,"z":-10.},"planeNormal":{"x":0.,"y":0.,"z":1.},"stiffness":100.}}
        proposal=agent.Proposal(spatial,"Add a frame and a sphere-plane contact. Do not run.")
        result=proposal.call("edit_spatial_assembly",{"edits":[frame,contact]})
        self.assertTrue(result["accepted"],result);self.assertEqual(result["model"]["frames"][0]["id"],"tip");self.assertEqual(result["model"]["contacts"][0]["id"],"floor")
        self.assertNotIn("frames",spatial);self.assertNotIn("contacts",spatial)
        bad=deepcopy(contact);bad["id"]="bad";bad["values"]["planeNormal"]["z"]=True
        with self.assertRaises(ValueError):proposal.call("edit_spatial_assembly",{"edits":[bad]})

    def test_ai_edits_linked_frame_and_rejects_direct_joint_edits(self):
        import reference_frames
        spatial=deepcopy(next(item['model'] for item in models.EXAMPLES if item['id']=='spatial-revolute'))
        spatial['frames']=[{'id':'pivot','name':'Pivot','body':'arm','translation':deepcopy(spatial['joints'][0]['anchorB']),'rotation':{'rx':0.,'ry':0.,'rz':0.}}]
        spatial['frameLinks']=[{'joint':'hinge','side':'b','frame':'pivot','axis':'y'}];reference_frames.sync_links(spatial)
        proposal=agent.Proposal(spatial,'Rotate the linked frame around its Y axis.')
        frame={'collection':'frames','operation':'update','id':'pivot','values':{'rotation':{'ry':30.}}}
        result=proposal.call('edit_spatial_assembly',{'edits':[frame]});self.assertTrue(result['accepted'],result)
        self.assertEqual(result['model']['frames'][0]['rotation']['ry'],30.)
        self.assertEqual(reference_frames.validate_links(result['model']),[])
        before=deepcopy(proposal.model)
        for values in ({'anchorB':{'x':.1}}, {'axisB':{'x':1.}}, {'b':'other'}):
            with self.subTest(values=values),self.assertRaisesRegex(ValueError,'Unlink'):
                proposal.call('edit_spatial_assembly',{'edits':[{'collection':'joints','operation':'update','id':'hinge','values':values}]})
            self.assertEqual(proposal.model,before)
        with self.assertRaises(ValueError):proposal.call('edit_spatial_assembly',{'edits':[{'collection':'frames','operation':'update','id':'pivot','values':{'body':'ground'}}]})
        self.assertEqual(proposal.model,before)
        stale=deepcopy(spatial);stale['frames'][0]['translation']['x']+=.1
        malformed=agent.Proposal(stale,'Change the mass.');unchanged=deepcopy(malformed.model)
        with self.assertRaisesRegex(ValueError,'Repair existing frame links'):
            malformed.call('edit_spatial_assembly',{'edits':[{'collection':'bodies','operation':'update','id':'arm','values':{'mass':2.}}]})
        self.assertEqual(malformed.model,unchanged)

    def test_ai_adds_damping_to_legacy_contact_without_changing_input(self):
        model=deepcopy(next(item['model'] for item in models.EXAMPLES if item['id']=='spatial-sphere-contact'))
        proposal=agent.Proposal(model,'Add contact damping. Do not run.')
        edit={'collection':'contacts','operation':'update','id':'floor','values':{'damping':10.}}
        result=proposal.call('edit_spatial_assembly',{'edits':[edit]})
        self.assertTrue(result['accepted'],result);self.assertEqual(result['model']['contacts'][0]['damping'],10.)
        self.assertNotIn('damping',model['contacts'][0])
        edit['values']['damping']=True
        with self.assertRaises(ValueError):proposal.call('edit_spatial_assembly',{'edits':[edit]})

    def test_ai_linked_frame_rotation_handles_axis_roundoff(self):
        import reference_frames
        model=deepcopy(next(item['model'] for item in models.EXAMPLES if item['id']=='spatial-revolute'))
        model['frames']=[{'id':'pivot','name':'Pivot','body':'arm','translation':deepcopy(model['joints'][0]['anchorB']),'rotation':{'rx':0.,'ry':90.,'rz':90.}}]
        model['frameLinks']=[{'joint':'hinge','side':'b','frame':'pivot','axis':'x'}];reference_frames.sync_links(model)
        edit={'collection':'frames','operation':'update','id':'pivot','values':{'rotation':{'rx':.08,'rz':89.92}}}
        result=agent.Proposal(model,'Rotate the linked frame.').call('edit_spatial_assembly',{'edits':[edit]})
        self.assertTrue(result['accepted'],result);self.assertLessEqual(max(abs(v) for v in result['model']['joints'][0]['axisB'].values()),1.)

    def test_spatial_copy_uses_exact_source_properties_and_attaches_atomically(self):
        spatial=deepcopy(next(item["model"] for item in models.EXAMPLES if item["id"]=="spatial-revolute"))
        zero={"x":0,"y":0,"z":0}
        edits=[{"collection":"bodies","operation":"copy","id":"payload","sourceId":"arm","values":{"name":"Payload"}},
               {"collection":"joints","operation":"add","id":"ball","values":{"type":"spherical","a":"arm","b":"payload","anchorA":zero,"anchorB":zero}}]
        proposal=agent.Proposal(spatial,"Copy arm into a new payload and connect it with a spherical joint.")
        result=proposal.call("edit_spatial_assembly",{"edits":edits})
        self.assertTrue(result["accepted"],result)
        copied=proposal.model["bodies"][1]
        for key in ("mass","inertia","pose","velocity"):self.assertEqual(copied[key],spatial["bodies"][0][key])
        self.assertEqual(copied["name"],"Payload")
        for source in ("missing", "ground"):
            edits[0]["sourceId"]=source;bad=agent.Proposal(spatial,"Copy the body and connect it.")
            with self.subTest(source=source),self.assertRaises(ValueError):bad.call("edit_spatial_assembly",{"edits":edits})
            self.assertEqual(bad.model,spatial)

    def test_spatial_agent_can_propose_an_unconnected_free_body(self):
        spatial=deepcopy(next(item['model'] for item in models.EXAMPLES if item['id']=='spatial-revolute'))
        edit={'collection':'bodies','operation':'copy','id':'payload','sourceId':'arm','values':{'name':'Free payload'}}
        result=agent.Proposal(spatial,'Copy arm into a free payload without a joint. Do not run.').call('edit_spatial_assembly',{'edits':[edit]})
        self.assertTrue(result['accepted'],result);self.assertEqual(len(result['model']['bodies']),2);self.assertEqual(len(result['model']['joints']),1)
        self.assertEqual(result['model']['bodies'][1]['name'],'Free payload');self.assertEqual(len(spatial['bodies']),1)

    def test_spatial_universal_joint_uses_the_existing_typed_joint_boundary(self):
        spatial=deepcopy(next(item["model"] for item in models.EXAMPLES if item["id"]=="spatial-revolute"))
        zero={"x":0,"y":0,"z":0}
        edits=[{"collection":"bodies","operation":"copy","id":"payload","sourceId":"arm","values":{"name":"Payload"}},
               {"collection":"joints","operation":"add","id":"universal","values":{"type":"universal","a":"arm","b":"payload","anchorA":zero,"anchorB":zero,"axisA":{"x":1,"y":0,"z":0},"axisB":{"x":0,"y":0,"z":1}}}]
        result=agent.Proposal(spatial,"Build a universal joint.").call("edit_spatial_assembly",{"edits":edits})
        self.assertTrue(result["accepted"],result)
        self.assertEqual(result["model"]["joints"][-1]["type"],"universal")

    def test_spatial_edit_is_atomic_for_malformed_invalid_and_cross_family_inputs(self):
        spatial = deepcopy(next(item["model"] for item in models.EXAMPLES if item["id"] == "spatial-revolute"))
        good={"collection":"bodies","operation":"update","id":"arm","values":{"mass":2.}}
        for bad in (
            {"collection":"bodies","operation":"delete","id":"arm","values":{"mass":1}},
            {"collection":"bodies","operation":"update","id":"arm","values":{"mass":True}},
            {"collection":"bodies","operation":"update","id":"arm","values":{"mass":10**400}},
            {"collection":"bodies","operation":"update","id":"arm","values":{"velocity":{"vx":0,"shell":"bad"}}},
            {"collection":"bodies","operation":"update","id":"arm","values":{"pose":{}}},
            {"collection":"bodies","operation":"update","id":"unknown","values":{"mass":1}},
            {"collection":"joints","operation":"update","id":"hinge","values":{"type":"spherical"}},
            {"collection":"joints","operation":"update","id":"hinge","values":{"anchorA":{"x":10}}},
            {"collection":"loads","operation":"add","id":"bad","values":{"body":"missing","frame":"other"}},
        ):
            with self.subTest(bad=bad):
                proposal=agent.Proposal(spatial,"Change the mass and then run it.")
                try: result=proposal.call("edit_spatial_assembly",{"edits":[good,bad]})
                except ValueError: pass
                else:self.assertFalse(result["accepted"])
                self.assertEqual(proposal.model,spatial)
                self.assertEqual(proposal.actions,[])
        for graph in (deepcopy(models.EXAMPLES[0]["model"]),{"kind":"planar-assembly","bodies":[],"joints":[],"simulation":{"duration":1,"step":.01}}):
            with self.subTest(kind=graph["kind"]), self.assertRaises(ValueError):
                agent.Proposal(graph,"change model").call("edit_spatial_assembly",{"edits":[good]})

    def test_unsolicited_graph_edit_is_only_a_draft_and_does_not_authorize_run(self):
        spatial=deepcopy(next(item["model"] for item in models.EXAMPLES if item["id"]=="spatial-revolute"))
        body=self.request("Explain the current graph. Do not run.");body["model"]=deepcopy(spatial);before=deepcopy(body)
        edit={"collection":"bodies","operation":"update","id":"arm","values":{"mass":2.}}
        with service([assistant([("edit_spatial_assembly",{"edits":[edit]}),("request_run",{})]),assistant()]) as (client,_):result=agent.chat(body,client)
        self.assertEqual(body,before);self.assertEqual(result["proposedModel"]["bodies"][0]["mass"],2.)
        self.assertFalse(result["runRequested"]);self.assertFalse(result["toolResults"][-1]["ok"])

    def test_spatial_rejected_edit_does_not_authorize_run_or_replace_graph(self):
        spatial=deepcopy(next(item["model"] for item in models.EXAMPLES if item["id"]=="spatial-revolute"))
        body=self.request("Remove arm and run it.");body["model"]=deepcopy(spatial)
        delete={"collection":"bodies","operation":"delete","id":"arm","values":{"mass":1}}
        responses=[assistant([("edit_spatial_assembly",{"edits":[delete]}),("request_run",{})]),assistant()]
        with service(responses) as (client,_):result=agent.chat(body,client)
        self.assertIsNone(result["proposedModel"]);self.assertFalse(result["runRequested"]);self.assertFalse(result["toolResults"][0]["ok"]);self.assertEqual(body["model"],spatial)
        proposal=agent.Proposal(spatial,"Explain the current graph.")
        loaded=proposal.call("load_example",{"id":"assembly-single"})
        self.assertTrue(loaded["accepted"]);self.assertEqual(spatial,body["model"])
        self.assertEqual(proposal.model["kind"],"planar-assembly")



if __name__ == "__main__":
    unittest.main()
