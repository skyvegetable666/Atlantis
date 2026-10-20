import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from atlantis.adapters.gateway import AnthropicGatewayModel, GatewaySettings
from atlantis.contracts import Limits, ModelCallError


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

    def test_truncated_stream_never_becomes_a_successful_action(self):
        self.complete = False
        with self.assertRaises(ModelCallError):
            self.model.generate({}, Limits())


if __name__ == "__main__":
    unittest.main()
