import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from atlantis.adapters.gateway import AnthropicGatewayModel, GatewaySettings
from atlantis.adapters.local import StatisticsEvaluator, StatisticsTool
from atlantis.city import City
from atlantis.contracts import Limits, ModelCallError, RunConfig
from atlantis.controller import ExperimentController
from atlantis.runtime import ResidentRuntime
from atlantis.storage import SQLiteStorage


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                owner.requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                events = [
                    {"type": "message_start", "message": {"usage": {"input_tokens": 25}}},
                    *([
                        {"type": "content_block_start", "content_block": {"type": "tool_use", "name": "city_action", "input": {}}},
                        {"type": "content_block_delta", "delta": {"type": "input_json_delta", "partial_json": owner.output}},
                    ] if owner.tool_mode else [{"type": "content_block_delta", "delta": {"type": "text_delta", "text": owner.output}}]),
                    {"type": "message_delta", "usage": {"output_tokens": 10}},
                ]
                if owner.complete:
                    events.append({"type": "message_stop"})
                for event in events:
                    self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())

        self.output = '{"kind":"wait","params":{}}'
        self.complete = True
        self.tool_mode = False
        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.model = AnthropicGatewayModel(GatewaySettings(f"http://127.0.0.1:{self.server.server_port}", "test-model", "test-token"))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_streaming_protocol_and_provider_usage(self):
        reply = self.model.generate({"self": {"id": "resident-1"}}, Limits())
        self.assertEqual(reply.kind, "wait")
        self.assertEqual(reply.usage.input_tokens, 25)
        self.assertEqual(reply.usage.output_tokens, 10)
        self.assertIsNone(reply.usage.cost_micros)
        self.assertTrue(self.requests[0]["stream"])
        self.assertNotIn("test-token", json.dumps(self.requests[0]))

    def test_invalid_json_preserves_billed_token_usage(self):
        self.output = "not an action"
        with self.assertRaises(ModelCallError) as captured:
            self.model.generate({}, Limits())
        self.assertEqual(captured.exception.usage.output_tokens, 10)

    def test_native_tool_stream_becomes_a_validated_intention(self):
        self.tool_mode = True
        reply = self.model.generate({}, Limits())
        self.assertEqual(reply.kind, "wait")
        self.assertEqual(self.requests[0]["tool_choice"]["name"], "city_action")

    def test_outgoing_schema_defines_message_params_without_a_fallback(self):
        self.model.generate({}, Limits())
        schema = self.requests[0]["tools"][0]["input_schema"]
        self.assertEqual(schema["required"], ["kind", "params"])
        self.assertFalse(schema["additionalProperties"])
        message_branches = []
        for branch in schema["oneOf"]:
            kinds = branch["properties"]["kind"]["enum"]
            if "send_message" in kinds:
                self.assertEqual(kinds, ["send_message"])
                message_branches.append(branch)
        self.assertEqual(len(message_branches), 1)
        params = message_branches[0]["properties"]["params"]
        self.assertEqual(set(params["properties"]), {"body", "recipient"})
        self.assertEqual(params["required"], ["body"])
        self.assertFalse(params["additionalProperties"])
        self.assertEqual(params["properties"]["body"]["type"], "string")
        self.assertEqual(params["properties"]["body"]["minLength"], 1)
        self.assertNotIn("maxLength", params["properties"]["body"])
        self.assertIn("8000", params["properties"]["body"]["description"])
        self.assertEqual(params["properties"]["recipient"]["type"], ["string", "null"])
        other_kinds = {kind for branch in schema["oneOf"] if branch not in message_branches
                       for kind in branch["properties"]["kind"]["enum"]}
        self.assertEqual(other_kinds, set(schema["properties"]["kind"]["enum"]) - {"send_message"})

    def test_message_results_preserve_model_usage_and_call_fees(self):
        self.tool_mode = True
        storage = SQLiteStorage(":memory:")
        self.addCleanup(storage.close)
        city = City(storage)
        controller = ExperimentController(city, {"live": ResidentRuntime(self.model)}, StatisticsTool(), StatisticsEvaluator())
        cases = [
            ({"body": "hello"}, None),
            ({"body": "hello", "recipient": None}, None),
            ({"body": "hello", "recipient": "resident-2"}, None),
            ({"message": "wrong field"}, "invalid_params"),
            ({"body": "hello", "to": "resident-2"}, "invalid_params"),
            ({"body": 1}, "invalid_params"),
            ({"body": "hello", "recipient": []}, "invalid_recipient"),
        ]
        for params, code in cases:
            with self.subTest(params=params):
                self.output = json.dumps({"kind": "send_message", "params": params})
                run = controller.create_run(RunConfig(execution_mode="live"))
                city.set_status(run, "running")
                state = controller.advance(run)
                result = next(iter(state["operations"].values()))["result"]
                self.assertEqual(result["status"], "completed" if code is None else "rejected")
                self.assertEqual(result["code"], code)
                self.assertEqual(len(state["messages"]), 1 if code is None else 0)
                self.assertEqual(state["status"], "running")
                self.assertEqual(state["calls"]["call-1"]["status"], "done")
                self.assertEqual(len(state["usage"]), 1)
                self.assertEqual(state["usage"][0]["input_tokens"], 25)
                self.assertEqual(state["usage"][0]["output_tokens"], 10)
                self.assertIsNone(state["usage"][0]["cost_micros"])
                self.assertEqual(state["budget"]["started"], 1)
                self.assertEqual(state["accounts"]["balances"]["resident-1"], 49)
                self.assertEqual(state["accounts"]["balances"]["resource_sink"], 1)

    def test_truncated_stream_never_becomes_a_successful_action(self):
        self.complete = False
        with self.assertRaises(ModelCallError):
            self.model.generate({}, Limits())


if __name__ == "__main__":
    unittest.main()
