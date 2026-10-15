"""Transport fixtures exercise the adapter; they do not prove live Free access."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import shutil
import threading
import time
import os
import base64

MODULE = Path(__file__).resolve().parents[1] / "pc" / "development" / "provider.py"


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assertTrue(MODULE.is_file(), "Free provider implementation is missing")
        self.spec = importlib.util.spec_from_file_location("development_provider", MODULE)
        self.provider = importlib.util.module_from_spec(self.spec)
        self.spec.loader.exec_module(self.provider)

    def bridge(self, payload, *, delay=0):
        driver = self.root / "fixture.py"
        driver.write_text("import json,sys,time\nrequest=json.load(sys.stdin)\n"
                          + f"time.sleep({delay})\n"
                          + "with open('" + (self.root / 'sent').as_posix() + "','a') as f: f.write('1')\n"
                          + "print(" + repr(json.dumps(payload)) + ")\n", encoding="utf-8")
        return self.provider.ProviderBridge(self.root, [sys.executable, str(driver)])

    def decision(self, output):
        return {"status": "completed", "text": json.dumps({"output": output})}

    def test_text_response_and_sse_have_canonical_shapes(self):
        bridge = self.bridge(self.decision([{"type": "message", "text": "Готово"}]))
        response = bridge.generate({"input": "help", "model": "free"})
        self.assertEqual(response["output"][0]["content"], [{"type": "output_text", "text": "Готово", "annotations": []}])
        events = self.provider.response_events(response)
        self.assertEqual(events[0]["type"], "response.created")
        self.assertEqual(events[-1]["type"], "response.completed")
        self.assertEqual([e["sequence_number"] for e in events], list(range(len(events))))
        self.assertEqual(next(e for e in events if e["type"] == "response.output_text.delta")["delta"], "Готово")

    def test_single_json_code_fence_is_accepted_but_explanatory_text_is_not(self):
        raw = json.dumps({"output": [{"type": "message", "text": "ok"}]})
        bridge = self.bridge({"status": "completed", "text": "```json\n" + raw + "\n```"})
        self.assertEqual(bridge.generate({"input": "code fence"})["status"], "completed")
        bridge = self.bridge({"status": "completed", "text": "Here you go:\n```json\n" + raw + "\n```"})
        with self.assertRaises(self.provider.ProviderUnavailable):
            bridge.generate({"input": "explanatory text"})

    def test_function_call_preserves_id_and_validates_schema(self):
        request = {"input": "run", "tools": [{"type": "function", "name": "shell", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"], "additionalProperties": False}}]}
        bridge = self.bridge(self.decision([{"type": "function_call", "call_id": "call_exact", "name": "shell", "arguments": {"command": "pwd"}}]))
        result = bridge.generate(request)
        self.assertEqual(result["output"][0]["call_id"], "call_exact")
        self.assertEqual(json.loads(result["output"][0]["arguments"]), {"command": "pwd"})
        self.assertTrue(any(e["type"] == "response.function_call_arguments.done" for e in self.provider.response_events(result)))

    def test_patch_custom_call_is_preserved(self):
        patch = "*** Begin Patch\n*** End Patch"
        bridge = self.bridge(self.decision([{"type": "custom_tool_call", "call_id": "patch_1", "name": "apply_patch", "input": patch}]))
        result = bridge.generate({"input": "edit", "tools": [{"type": "custom", "name": "apply_patch", "format": {"type": "grammar", "syntax": "lark", "definition": "patch"}}]})
        self.assertEqual(result["output"][0]["input"], patch)
        self.assertEqual(next(e for e in self.provider.response_events(result) if e["type"] == "response.custom_tool_call_input.done")["input"], patch)

    def test_schema_type_property_and_union_survive_media_preparation(self):
        schema = {"type": "object", "properties": {"type": {"type": ["string", "null"]}}}
        request = {"input": "inspect", "tools": [{"type": "function", "name": "inspect", "parameters": schema}]}
        prepared, images = self.provider._prepare_images(request)
        self.assertEqual(prepared, request)
        self.assertEqual(images, [])
        bridge = self.bridge(self.decision([{"type": "function_call", "name": "inspect", "call_id": "schema_type", "arguments": {"type": None}}]))
        self.assertEqual(json.loads(bridge.generate(request)["output"][0]["arguments"]), {"type": None})

    def test_invalid_decisions_become_uncertain_and_are_never_replayed(self):
        for text in ('hello', '{"output":[]}', '{"output":[{"type":"function_call","call_id":"x","name":"unknown","arguments":{}}]}'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as folder:
                bridge = self.bridge({"status": "completed", "text": text})
                bridge = self.provider.ProviderBridge(folder, bridge.driver_command)
                for _ in range(2):
                    with self.assertRaises(self.provider.ProviderUnavailable) as error:
                        bridge.generate({"input": "same"})
                    self.assertEqual(error.exception.state, "uncertain")
        self.assertEqual((self.root / "sent").read_text(), "111")

    def test_completed_receipt_survives_restart_without_replaying(self):
        bridge = self.bridge(self.decision([{"type": "message", "text": "once"}]))
        first = bridge.generate({"input": "same"})
        other = self.provider.ProviderBridge(self.root, bridge.driver_command)
        self.assertEqual(first, other.generate({"input": "same"}))
        self.assertEqual((self.root / "sent").read_text(), "1")

    def test_quota_and_login_have_explicit_waiting_states(self):
        for status in ("waiting_user", "waiting_model"):
            bridge = self.bridge({"status": status, "reason": "manual action required", "sent": False})
            with self.assertRaises(self.provider.ProviderUnavailable) as error:
                bridge.generate({"input": status})
            self.assertEqual(error.exception.state, status)

    def test_wrong_schema_does_not_escape_to_tool_executor(self):
        bridge = self.bridge(self.decision([{"type": "function_call", "call_id": "call_a", "name": "shell", "arguments": {"command": 42}}]))
        with self.assertRaises(self.provider.ProviderUnavailable) as error:
            bridge.generate({"input": "run", "tools": [{"type": "function", "name": "shell", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}}}]})
        self.assertEqual(error.exception.state, "uncertain")

    def test_limits_and_timeout_do_not_resend(self):
        bridge = self.bridge(self.decision([{"type": "message", "text": "x" * 1_100_000}]))
        with self.assertRaises(self.provider.ProviderUnavailable):
            bridge.generate({"input": "big"})
        bridge = self.bridge(self.decision([{"type": "message", "text": "late"}]), delay=2)
        bridge.timeout_seconds = 0.1
        with self.assertRaises(self.provider.ProviderUnavailable) as error:
            bridge.generate({"input": "slow"})
        self.assertEqual(error.exception.state, "uncertain")

    def test_capabilities_never_claim_live_readiness_without_probe(self):
        bridge = self.provider.ProviderBridge(self.root, ["missing-relaykite-driver"])
        caps = bridge.capabilities()
        self.assertFalse(caps["ready"])
        self.assertFalse(caps["native_function_calling"])
        self.assertEqual(caps["state"], "waiting_user")

    def test_cancel_stops_owned_driver_and_prevents_replay(self):
        bridge = self.bridge(self.decision([{"type": "message", "text": "late"}]), delay=20)
        self.assertTrue(hasattr(bridge, "cancel_active"), "Provider cancellation is missing")
        errors = []
        def generate():
            try:
                bridge.generate({"input": "cancel me"})
            except self.provider.ProviderUnavailable as error:
                errors.append(error.state)
        thread = threading.Thread(target=generate)
        thread.start()
        deadline = time.monotonic() + 2
        while not bridge.cancel_active() and time.monotonic() < deadline:
            time.sleep(0.01)
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, ["uncertain"])
        with self.assertRaises(self.provider.ProviderUnavailable) as error:
            bridge.generate({"input": "cancel me"})
        self.assertEqual(error.exception.state, "uncertain")
        self.assertFalse((self.root / "sent").exists())

    def test_timeout_is_bounded_when_driver_never_reads_stdin(self):
        driver = self.root / "blocked.py"
        driver.write_text("import time\ntime.sleep(2)\n", encoding="utf8")
        bridge = self.provider.ProviderBridge(self.root, [sys.executable, str(driver)])
        bridge.timeout_seconds = 0.1
        started = time.monotonic()
        with self.assertRaises(self.provider.ProviderUnavailable):
            bridge.generate({"input": "x" * 90_000})
        self.assertLess(time.monotonic() - started, 1.5)

    def test_driver_installation_can_retry_a_confirmed_unsent_request(self):
        bridge = self.provider.ProviderBridge(self.root, ["missing-relaykite-driver"])
        with self.assertRaises(self.provider.ProviderUnavailable):
            bridge.generate({"input": "install then retry"})
        driver = self.bridge(self.decision([{"type": "message", "text": "installed"}]))
        response = driver.generate({"input": "install then retry"})
        self.assertEqual(response["status"], "completed")

    def test_required_named_tool_and_duplicate_call_ids_are_rejected(self):
        tool = {"type": "function", "name": "shell", "parameters": {"type": "object"}}
        call = {"type": "function_call", "call_id": "call_repeated", "name": "shell", "arguments": {}}
        cases = [([call, call], {}), ([{"type": "message", "text": "done"}], {"tool_choice": "required"}), ([call], {"tool_choice": "none"})]
        for index, (output, options) in enumerate(cases):
            with self.subTest(index=index):
                bridge = self.bridge(self.decision(output))
                with self.assertRaises(self.provider.ProviderUnavailable) as error:
                    bridge.generate({"input": str(index), "tools": [tool], **options})
                self.assertEqual(error.exception.state, "uncertain")

    def test_tool_schema_refs_required_and_additional_properties_are_enforced(self):
        schema = {"type": "object", "$defs": {"cmd": {"type": "string", "minLength": 1}}, "properties": {"command": {"$ref": "#/$defs/cmd"}}, "required": ["command"], "additionalProperties": False}
        for args in ({"command": "pwd"}, {}, {"command": ""}, {"command": "pwd", "secret": 1}):
            with self.subTest(args=args):
                call = {"type": "function_call", "call_id": "call_schema", "name": "shell", "arguments": args}
                bridge = self.bridge(self.decision([call]))
                request = {"input": json.dumps(args), "tools": [{"type": "function", "name": "shell", "parameters": schema}]}
                if args == {"command": "pwd"}:
                    self.assertEqual(bridge.generate(request)["output"][0]["call_id"], "call_schema")
                else:
                    with self.assertRaises(self.provider.ProviderUnavailable):
                        bridge.generate(request)

    def test_namespaced_plugin_calls_preserve_namespace_and_call_id(self):
        tools = [{"type": "namespace", "name": "computer", "tools": [{"type": "function", "name": "click", "parameters": {"type": "object", "required": ["target"], "properties": {"target": {"type": "string"}}}}]}]
        bridge = self.bridge(self.decision([{"type": "function_call", "namespace": "computer", "name": "click", "call_id": "call_computer", "arguments": {"target": "button"}}]))
        result = bridge.generate({"input": "click", "tools": tools})
        self.assertEqual(result["output"][0]["namespace"], "computer")
        self.assertEqual(result["output"][0]["name"], "click")
        self.assertEqual(result["output"][0]["call_id"], "call_computer")

    def test_remote_or_invalid_image_input_is_unavailable_before_send(self):
        bridge = self.bridge(self.decision([{"type": "message", "text": "not sent"}]))
        for image_url in ("https://example.com/image.png", "data:image/png;base64,AAAA", "data:image/png;base64," + ("a" * 3_000_000)):
            with self.subTest(image_url=image_url[:35]):
                with self.assertRaises(self.provider.ProviderUnavailable) as error:
                    bridge.generate({"input": [{"role": "user", "content": [{"type": "input_image", "image_url": image_url}]}]})
                self.assertEqual(error.exception.state, "waiting_user")
                self.assertIn("image", error.exception.reason.lower())
        self.assertFalse((self.root / "sent").exists())

    def test_data_image_is_sent_as_attachment_and_removed_from_text_prompt(self):
        png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
        driver = self.root / "image-fixture.py"
        capture = self.root / "capture.json"
        decision = self.decision([{"type": "message", "text": "image received"}])
        driver.write_text("import json,sys\nr=json.load(sys.stdin)\nfrom pathlib import Path\nPath(" + repr(str(capture)) + ").write_text(json.dumps(r),encoding='utf8')\nprint(" + repr(json.dumps(decision)) + ")\n", encoding="utf8")
        bridge = self.provider.ProviderBridge(self.root, [sys.executable, str(driver)])
        result = bridge.generate({"input": [{"role": "user", "content": [{"type": "input_text", "text": "Look"}, {"type": "input_image", "image_url": "data:image/png;base64," + png}]}]})
        sent = json.loads(capture.read_text(encoding="utf8"))
        self.assertEqual(result["status"], "completed")
        self.assertNotIn(png, sent["prompt"])
        self.assertEqual(sent["images"], [{"mime_type": "image/png", "data_base64": png}])

    @unittest.skipUnless(shutil.which("node"), "Node.js is optional")
    def test_ui_driver_rejects_invalid_input_before_browser_actions(self):
        script = MODULE.with_name("free-ui.mjs")
        self.assertTrue(script.is_file(), "Real browser UI driver is missing")
        run = subprocess.run(["node", str(script), "--profile", str(self.root / "profile")], input='{"operation":"generate","prompt":42}', text=True, capture_output=True, timeout=10)
        result = json.loads(run.stdout)
        self.assertEqual(result["status"], "waiting_user")
        self.assertIs(result["sent"], False)

    @unittest.skipUnless(shutil.which("node"), "Node.js is optional")
    def test_ui_driver_does_not_resend_after_interrupted_send(self):
        script = MODULE.with_name("free-ui.mjs")
        self.assertTrue(script.is_file(), "Real browser UI driver is missing")
        profile = self.root / "profile"
        receipt = profile / ".relaykite-ui-receipts" / (("a" * 64) + ".json")
        receipt.parent.mkdir(parents=True)
        receipt.write_text('{"state":"pending","request_id":"ui_previous"}', encoding="utf8")
        run = subprocess.run(["node", str(script), "--profile", str(profile)], input=json.dumps({"operation": "generate", "prompt": "do work", "fingerprint": "a" * 64, "request_id": "ui_test"}), text=True, capture_output=True, timeout=10)
        result = json.loads(run.stdout)
        self.assertEqual(result["status"], "uncertain")
        self.assertIs(result["sent"], True)

    @unittest.skipUnless(os.environ.get("RELAYKITE_BROWSER_TESTS") == "1", "Opt-in local Chromium DOM fixture; not live ChatGPT proof")
    def test_actual_browser_dom_driver_waits_for_complete_answer(self):
        """Real Chromium, routed HTML fixture, no ChatGPT network or account."""
        script = MODULE.with_name("free-ui.mjs")
        playwright = script.parent / "node_modules" / "playwright" / "index.mjs"
        self.assertTrue(playwright.is_file(), "Install the optional local Playwright dependency")
        expected = json.dumps({"output": [{"type": "message", "text": "DOM complete"}]})
        fixture = '''<html><body><button data-testid="accounts-profile-button">Profile</button><form onsubmit="return false">
          <div id="prompt-textarea" contenteditable="true"></div>
          <button data-testid="send-button" onclick="send()">Send</button>
          <input type="file" accept="image/*" multiple onchange="upload(event)"></form>
          <script>let uploaded=false;async function upload(event){
            const file=event.target.files[0];const bytes=new Uint8Array(await file.arrayBuffer());
            uploaded=file.type==='image/png'&&bytes[0]===137&&bytes[1]===80;
            const image=document.createElement('img');image.src=URL.createObjectURL(file);document.querySelector('form').append(image);
            document.querySelector('[data-testid=send-button]').disabled=true;
            setTimeout(()=>document.querySelector('[data-testid=send-button]').disabled=false,1000);
          }</script>
          <script>function send(){
            document.querySelector('[data-testid=send-button]').hidden=true;
            document.querySelector('#prompt-textarea').textContent='';
            const user=document.createElement('div'); user.dataset.messageAuthorRole='user'; user.textContent='request'; document.body.append(user);
            const stop=document.createElement('button');stop.dataset.testid='stop-button';stop.textContent='Stop generating';document.body.append(stop);
            const answer=document.createElement('div');answer.dataset.messageAuthorRole='assistant';answer.innerHTML='<div class="markdown"><pre><div>json <button>Copy code</button></div><code></code></pre></div>';document.body.append(answer);
            setTimeout(()=>answer.querySelector('code').textContent='{"output":',300);
            setTimeout(()=>answer.querySelector('code').textContent=uploaded?ANSWER:'{"error":"image was not uploaded"}',900);
            setTimeout(()=>{stop.remove();const copy=document.createElement('button');copy.dataset.testid='copy-turn-action-button';copy.textContent='Copy';answer.append(copy)},1400);
          }</script></body></html>'''.replace('ANSWER', json.dumps(expected))
        facade = self.root / "browser-facade.mjs"
        facade.write_text("import {chromium as real} from " + json.dumps(playwright.as_uri()) + ";\n"
            + "export const chromium={async launchPersistentContext(profile,options){const context=await real.launchPersistentContext(profile,{...options,headless:true,channel:process.env.RELAYKITE_TEST_BROWSER_CHANNEL||'chromium'});await context.route('**/*',route=>route.fulfill({status:200,contentType:'text/html',body:" + json.dumps(fixture) + "}));return context;}};", encoding="utf8")
        loader = self.root / "browser-loader.mjs"
        loader.write_text("export async function resolve(specifier,context,nextResolve){if(specifier==='playwright')return {url:" + json.dumps(facade.as_uri()) + ",shortCircuit:true};return nextResolve(specifier,context);}", encoding="utf8")
        started = time.monotonic()
        png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
        run = subprocess.run(["node", "--no-warnings", "--experimental-loader", loader.as_uri(), str(script), "--profile", str(self.root / "dom-profile"), "--headless"], input=json.dumps({"operation": "generate", "prompt": "fixture only", "fingerprint": "b" * 64, "request_id": "ui_dom", "images": [{"mime_type": "image/png", "data_base64": png}]}), text=True, capture_output=True, timeout=35)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["text"], expected)
        self.assertGreater(time.monotonic() - started, 4.5)


if __name__ == "__main__":
    unittest.main()
