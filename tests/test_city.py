import ast
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from atlantis.adapters.local import ScriptedModel, StatisticsEvaluator, StatisticsTool
from atlantis.city import City
from atlantis.contracts import ActionRequest, ActorContext, ModelReply, RuleError, RunConfig, Usage
from atlantis.controller import ExperimentController
from atlantis.domain import accounts
from atlantis.runtime import ResidentRuntime
from atlantis.storage import SQLiteStorage


class CityTests(unittest.TestCase):
    def setUp(self):
        self.storage = SQLiteStorage(":memory:")
        self.addCleanup(self.storage.close)
        self.city = City(self.storage)
        self.run = self.city.create_run(RunConfig())
        self.city.set_status(self.run, "running")
        self.sequence = 0

    def act(self, kind, params, actor="resident-1", operation_id=None):
        self.sequence += 1
        context = ActorContext(self.run, actor, "operator" if actor == "treasury" else "resident")
        return self.city.dispatch(context, ActionRequest(operation_id or f"test-{self.sequence}", kind, params))

    def offer(self, reward=20):
        return {"title": "A funded task", "spec": "Return JSON.", "acceptance": "Valid JSON.", "reward": reward}

    def test_task_and_escrow_rollback_together(self):
        result = self.act("publish_task", self.offer(1000))
        state = self.city.snapshot(self.run)
        self.assertEqual(result.code, "insufficient_credit")
        self.assertEqual(list(state["tasks"]), ["task-1"])
        self.assertEqual(list(state["accounts"]["holds"]), ["task-1"])

    def test_idempotency_and_conflicting_payload(self):
        result = self.act("publish_task", self.offer(), operation_id="same")
        repeated = self.act("publish_task", self.offer(), operation_id="same")
        self.assertEqual(result, repeated)
        self.assertEqual(self.act("publish_task", self.offer(30), operation_id="same").code, "idempotency_conflict")
        state = self.city.snapshot(self.run)
        self.assertEqual(len(state["tasks"]), 2)
        self.assertEqual(state["agents"]["resident-1"]["available"], 30)

    def test_same_task_cannot_be_claimed_twice(self):
        self.assertEqual(self.act("claim_task", {"task_id": "task-1"}).status, "completed")
        self.assertEqual(self.act("claim_task", {"task_id": "task-1"}, actor="resident-2").code, "state_conflict")

    def test_acceptance_pays_exactly_once(self):
        self.act("claim_task", {"task_id": "task-1"})
        artifact = self.act("put_artifact", {"content": {"answer": 1}}).data["artifact_id"]
        self.act("submit_task", {"task_id": "task-1", "artifact_id": artifact})
        self.assertEqual(self.act("accept_task", {"task_id": "task-1"}, "treasury").status, "completed")
        self.assertEqual(self.act("accept_task", {"task_id": "task-1"}, "treasury").code, "state_conflict")
        state = self.city.snapshot(self.run)
        self.assertEqual(state["agents"]["resident-1"]["balance"], 110)
        self.assertEqual(len(state["accounts"]["ledger"]), 1)
        accounts.assert_valid(state["accounts"], 200)

    def test_established_contract_cannot_be_cancelled(self):
        self.act("claim_task", {"task_id": "task-1"})
        self.assertEqual(self.act("cancel_task", {"task_id": "task-1"}, "treasury").code, "state_conflict")
        self.assertIn("task-1", self.city.snapshot(self.run)["accounts"]["holds"])

    def test_invalid_submission_does_not_grant_artifact_access(self):
        self.act("claim_task", {"task_id": "task-1"})
        artifact = self.act("put_artifact", {"content": "private"}, "resident-2").data["artifact_id"]
        result = self.act("submit_task", {"task_id": "task-1", "artifact_id": artifact}, "resident-2")
        self.assertEqual(result.code, "forbidden")
        self.assertEqual(self.city.snapshot(self.run)["artifacts"][artifact]["visible_to"], ["resident-2"])
        self.assertEqual(self.city.observe(ActorContext(self.run, "resident-1"))["artifacts"], [])

    def test_private_messages_do_not_enter_third_resident_observation(self):
        with self.storage.transaction(self.run) as state:
            state["agents"]["observer"] = {"id": "observer", "name": "Observer", "status": "active", "message_cursor": 0}
            state["accounts"]["balances"]["observer"] = 0
        self.act("send_message", {"recipient": "resident-2", "body": "private offer"})
        self.act("send_message", {"body": "public offer"})
        observation = self.city.observe(ActorContext(self.run, "observer"))
        self.assertEqual([m["body"] for m in observation["messages"]], ["public offer"])
        self.assertEqual([m["body"] for m in observation["message_history"]], ["public offer"])
        self.assertNotIn("events", observation)
        self.assertNotIn("calls", observation)
        self.assertNotIn("scores", observation)

    def test_messages_remain_unread_until_decision_acknowledgement(self):
        self.act("send_message", {"recipient": "resident-2", "body": "hello"})
        context = ActorContext(self.run, "resident-2")
        first = self.city.observe(context)
        self.assertEqual(first, self.city.observe(context))
        call = self.city.reserve_decision(self.run, "resident-2", first)
        self.city.start_call(self.run, call["id"])
        self.city.finish_call(self.run, call["id"], Usage("fixture", cost_micros=0), {"kind": "wait", "params": {}})
        self.city.acknowledge_decision(self.run, call["id"])
        self.assertEqual(self.city.observe(context)["messages"], [])

    def test_disabled_communication_is_enforced(self):
        run = self.city.create_run(RunConfig(chat_mode="none"))
        self.city.set_status(run, "running")
        result = self.city.dispatch(ActorContext(run, "resident-1"), ActionRequest("message", "send_message", {"body": "hello"}))
        self.assertEqual(result.code, "forbidden")

    def test_model_cannot_supply_a_new_actor(self):
        result = self.act("accept_task", {"task_id": "task-1", "actor_id": "treasury"})
        self.assertEqual(result.code, "invalid_params")
        with self.assertRaises(RuleError):
            self.city.observe(ActorContext(self.run, "unknown-resident"))

    def test_paused_request_can_be_retried_after_resume(self):
        self.city.set_status(self.run, "paused")
        self.assertEqual(self.act("claim_task", {"task_id": "task-1"}, operation_id="retry").code, "run_not_running")
        self.city.set_status(self.run, "running")
        self.assertEqual(self.act("claim_task", {"task_id": "task-1"}, operation_id="retry").status, "completed")

    def test_malformed_identifiers_return_rejections(self):
        for kind, params in [("claim_task", {"task_id": []}), ("send_message", {"recipient": [], "body": "hi"}), ("submit_task", {"task_id": "task-1", "artifact_id": []})]:
            with self.subTest(kind=kind):
                self.assertEqual(self.act(kind, params).status, "rejected")

    def test_restart_never_replays_an_interrupted_call(self):
        call = self.city.reserve_decision(self.run, "resident-1", self.city.observe(ActorContext(self.run, "resident-1")))
        self.city.start_call(self.run, call["id"])
        self.city.recover()
        state = self.city.snapshot(self.run)
        self.assertEqual(state["status"], "paused")
        self.assertEqual(state["calls"][call["id"]]["status"], "unknown")
        self.assertIn(call["id"], state["accounts"]["holds"])
        with self.assertRaises(RuleError):
            self.city.set_status(self.run, "running")

    def test_second_controller_cannot_start_an_overlapping_decision(self):
        observation = self.city.observe(ActorContext(self.run, "resident-1"))
        first = self.city.reserve_decision(self.run, "resident-1", observation)
        self.assertIsNotNone(first)
        self.assertIsNone(self.city.reserve_decision(self.run, "resident-1", observation))
        self.assertEqual(len(self.city.snapshot(self.run)["calls"]), 1)

    def test_unknown_cost_is_preserved(self):
        call = self.city.reserve_decision(self.run, "resident-1", {})
        self.city.start_call(self.run, call["id"])
        self.city.finish_call(self.run, call["id"], Usage("gateway/model"), {"kind": "wait", "params": {}})
        self.assertIsNone(self.city.snapshot(self.run)["usage"][0]["cost_micros"])

    def test_nonfinite_data_is_rejected_without_losing_the_experiment(self):
        self.assertEqual(self.act("put_artifact", {"content": float("nan")}).code, "invalid_params")
        self.assertEqual(self.city.snapshot(self.run)["artifacts"], {})

    def test_scored_failure_never_pays_out(self):
        self.act("claim_task", {"task_id": "task-1"})
        artifact = self.act("put_artifact", {"content": {"sum": 0}}).data["artifact_id"]
        self.act("submit_task", {"task_id": "task-1", "artifact_id": artifact})
        controller = ExperimentController(self.city, {}, StatisticsTool(), StatisticsEvaluator())
        state = controller.advance(self.run)
        self.assertEqual(state["status"], "failed")
        self.assertFalse(state["scores"]["task-1"]["passed"])
        self.assertEqual(state["accounts"]["ledger"], [])


class IntegrationTests(unittest.TestCase):
    def test_demo_single_and_multi_resident_finish_and_conserve_credits(self):
        for count in (1, 2):
            for chat in ("none", "public", "private"):
                with self.subTest(count=count, chat=chat):
                    storage = SQLiteStorage(":memory:")
                    self.addCleanup(storage.close)
                    city = City(storage)
                    controller = ExperimentController(city, {"demo": ResidentRuntime(ScriptedModel())}, StatisticsTool(), StatisticsEvaluator())
                    run = city.create_run(RunConfig(agent_count=count, chat_mode=chat))
                    city.set_status(run, "running")
                    for _ in range(100):
                        state = controller.advance(run)
                        if state["status"] != "running":
                            break
                    self.assertEqual(state["status"], "completed")
                    self.assertTrue(state["scores"]["task-1"]["passed"])
                    payments = [e for e in state["accounts"]["ledger"] if e["purpose"] == "task_payment"]
                    self.assertEqual(len(payments), count)
                    self.assertEqual(len(state["accounts"]["holds"]), 0)
                    accounts.assert_valid(state["accounts"], 200)

    def test_pause_during_model_call_preserves_unapplied_decision(self):
        storage = SQLiteStorage(":memory:")
        self.addCleanup(storage.close)
        city = City(storage)
        run = city.create_run(RunConfig(agent_count=1))
        city.set_status(run, "running")

        class PausingModel:
            calls = 0

            def generate(self, observation, limits):
                self.calls += 1
                city.set_status(run, "paused")
                return ModelReply("claim_task", {"task_id": "task-1"}, Usage("fixture", cost_micros=0))

        model = PausingModel()
        controller = ExperimentController(city, {"demo": ResidentRuntime(model)}, StatisticsTool(), StatisticsEvaluator())
        state = controller.advance(run)
        self.assertEqual(state["tasks"]["task-1"]["status"], "open")
        self.assertFalse(state["calls"]["call-1"]["applied"])
        controller.advance(run)
        self.assertEqual(model.calls, 1)
        city.set_status(run, "running")
        state = controller.advance(run)
        self.assertEqual(state["tasks"]["task-1"]["status"], "claimed")
        self.assertEqual(model.calls, 1)
        self.assertEqual(len(state["accounts"]["ledger"]), 1)

    def test_call_budget_and_insufficient_credit_stop_execution(self):
        for config, status in [(RunConfig(agent_count=1, max_calls=1), "budget_exhausted"), (RunConfig(agent_count=1, resident_credits=1), "idle")]:
            storage = SQLiteStorage(":memory:")
            self.addCleanup(storage.close)
            city = City(storage)
            run = city.create_run(config)
            city.set_status(run, "running")
            controller = ExperimentController(city, {"demo": ResidentRuntime(ScriptedModel())}, StatisticsTool(), StatisticsEvaluator())
            for _ in range(10):
                state = controller.advance(run)
                if state["status"] != "running":
                    break
            self.assertEqual(state["status"], status)
            self.assertEqual(state["budget"]["started"], 1)
            self.assertEqual(len(state["agents"]), 1)

    def test_concurrent_reservations_cannot_double_spend(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "city.db"
            first, second = SQLiteStorage(path), SQLiteStorage(path)
            self.addCleanup(first.close)
            self.addCleanup(second.close)
            cities = [City(first), City(second)]
            run = cities[0].create_run(RunConfig())
            cities[0].set_status(run, "running")

            def publish(index):
                return cities[index].dispatch(ActorContext(run, "resident-1"), ActionRequest(f"concurrent-{index}", "publish_task", {"title": "Offer", "spec": "Work", "acceptance": "Check", "reward": 40}))

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(publish, (0, 1)))
            self.assertEqual(sorted(result.status for result in results), ["completed", "rejected"])
            self.assertEqual(cities[0].snapshot(run)["agents"]["resident-1"]["available"], 10)

    def test_persistence_survives_close_and_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "city.db"
            storage = SQLiteStorage(path)
            city = City(storage)
            run = city.create_run(RunConfig())
            before = city.snapshot(run)
            storage.close()
            reopened = SQLiteStorage(path)
            self.addCleanup(reopened.close)
            self.assertEqual(City(reopened).snapshot(run), before)

    def test_runtime_and_domains_have_no_infrastructure_imports(self):
        root = Path(__file__).resolve().parents[1] / "atlantis"
        for path in [root / "runtime.py", *sorted((root / "domain").glob("*.py"))]:
            tree = ast.parse(path.read_text())
            modules = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
            self.assertFalse(set(modules) & {"city", "storage", "controller", "bootstrap", "sqlite3", "server"}, path.name)


if __name__ == "__main__":
    unittest.main()
