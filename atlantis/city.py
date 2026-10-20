from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

from .contracts import ActionRequest, ActionResult, ActorContext, Record, RuleError, RunConfig, StoragePort, Usage
from .domain import accounts, artifacts, messaging, residents, tasks

ACTION_FIELDS = {
    "publish_task": {"title", "spec", "acceptance", "reward", "parent_id", "input"},
    "claim_task": {"task_id"}, "submit_task": {"task_id", "artifact_id"},
    "accept_task": {"task_id"}, "cancel_task": {"task_id"},
    "send_message": {"recipient", "body"}, "put_artifact": {"content"},
    "run_tool": {"name", "arguments"}, "wait": set(),
}


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class City:
    """The only writer of authoritative city state; external work stays outside transactions."""

    def __init__(self, storage: StoragePort):
        self.storage = storage

    @staticmethod
    def _event(state: Record, actor: str, kind: str, data: Record) -> None:
        state["events"].append({
            "sequence": len(state["events"]) + 1, "time": timestamp(),
            "actor": actor, "kind": kind, "data": copy.deepcopy(data),
        })

    @staticmethod
    def _authenticate(state: Record, actor: ActorContext) -> None:
        residents.authenticate(state["agents"], state["id"], actor)

    @staticmethod
    def _wake(state: Record, recipients: list[str] | None = None) -> None:
        eligible = [agent_id for agent_id in (recipients if recipients is not None else state["agents"])
                    if accounts.available(state["accounts"], agent_id) >= state["config"]["demo_call_fee"]]
        residents.wake(state["agents"], eligible)

    def create_run(self, config: RunConfig, manifest: Record | None = None) -> str:
        config.validate()
        run_id = uuid4().hex[:12]
        names = ("Ada", "Lin")[:config.agent_count]
        base, remainder = divmod(config.resident_credits, len(names))
        agents = {
            f"resident-{index + 1}": {"id": f"resident-{index + 1}", "name": name, "status": "active", "message_cursor": 0}
            for index, name in enumerate(names)
        }
        balances = {agent_id: base + (index < remainder) for index, agent_id in enumerate(agents)}
        balances.update(treasury=config.treasury_credits, resource_sink=0)
        state = {
            "schema_version": 1, "contract_version": "0.1", "id": run_id,
            "created_at": timestamp(), "status": "ready", "config": asdict(config),
            "manifest": copy.deepcopy(manifest or {}),
            "agents": agents, "accounts": accounts.new(balances), "tasks": {},
            "messages": [], "artifacts": {}, "events": [], "operations": {},
            "calls": {}, "usage": [], "scores": {}, "turn": 0,
            "budget": {"limit": config.max_calls, "started": 0, "reserved": 0},
        }
        tasks.publish(state["tasks"], "task-1", "treasury", {
            "title": "Summarize a public dataset", "reward": config.main_reward,
            "spec": "Return a JSON object with count, sum, min and max for the input numbers.",
            "acceptance": "All four statistics must match the input exactly; numeric JSON values are required.",
            "input": [13, 8, 21, 5, 34, 3],
        })
        accounts.reserve(state["accounts"], "treasury", config.main_reward, "task-1")
        self._event(state, "treasury", "run_created", {"mode": config.execution_mode, "task_id": "task-1"})
        self.storage.create(state)
        return run_id

    def snapshot(self, run_id: str) -> Record:
        state = self.storage.read(run_id)
        for agent in state["agents"].values():
            agent["balance"] = state["accounts"]["balances"][agent["id"]]
            agent["available"] = accounts.available(state["accounts"], agent["id"])
        return state

    def list_runs(self) -> list[Record]:
        return [{"id": s["id"], "status": s["status"], "config": s["config"], "created_at": s["created_at"]}
                for s in self.storage.list_runs()]

    def set_status(self, run_id: str, status: str) -> None:
        if status not in ("running", "paused"):
            raise RuleError("invalid_status", "Only start/resume and pause are operator controls.")
        with self.storage.transaction(run_id) as state:
            if state["status"] in ("completed", "budget_exhausted", "failed"):
                raise RuleError("state_conflict", "A finished experiment cannot be restarted.")
            if status == "running" and any(c["status"] == "unknown" for c in state["calls"].values()):
                raise RuleError("unresolved_call", "An interrupted external call requires reconciliation.")
            state["status"] = status
            self._event(state, "treasury", "run_status", {"status": status})

    def observe(self, actor: ActorContext) -> Record:
        state = self.storage.read(actor.run_id)
        self._authenticate(state, actor)
        if actor.role != "resident":
            raise RuleError("forbidden", "Resident observations require a resident identity.")
        agent = state["agents"][actor.actor_id]
        visible_messages = messaging.unread(state["messages"], actor.actor_id, agent["message_cursor"])
        # Cap a single observation without acknowledging messages that were not supplied.
        delivered_messages = visible_messages[:20]
        return copy.deepcopy({
            "run_id": state["id"], "self": agent,
            "available_credits": accounts.available(state["accounts"], actor.actor_id),
            "residents": [{"id": a["id"], "name": a["name"]} for a in state["agents"].values()],
            "chat_mode": state["config"]["chat_mode"], "call_fee": state["config"]["demo_call_fee"],
            "tasks": list(state["tasks"].values()), "messages": delivered_messages,
            "message_history": [m for m in state["messages"] if messaging.visible(m, actor.actor_id)][-20:],
            "message_cursor": max([agent["message_cursor"]] + [m["sequence"] for m in delivered_messages]),
            "artifacts": [a for a in state["artifacts"].values() if actor.actor_id in a["visible_to"]],
            "last_results": [v["result"] for v in state["operations"].values() if v["actor"] == actor.actor_id][-4:],
        })

    def dispatch(self, actor: ActorContext, request: ActionRequest) -> ActionResult:
        with self.storage.transaction(actor.run_id) as state:
            self._authenticate(state, actor)
            if not isinstance(request.operation_id, str) or not 0 < len(request.operation_id) <= 180:
                raise RuleError("invalid_params", "An operation identifier is required.")
            key = f"{actor.actor_id}:{request.operation_id}"
            try:
                fingerprint = hashlib.sha256(json.dumps(
                    {"kind": request.kind, "params": request.params}, sort_keys=True, allow_nan=False
                ).encode()).hexdigest()
            except (TypeError, ValueError):
                return ActionResult("rejected", code="invalid_params", message="Actions require finite JSON data.")
            prior = state["operations"].get(key)
            if prior:
                if prior["fingerprint"] != fingerprint:
                    return ActionResult("rejected", code="idempotency_conflict", message="Operation identifier was reused with different data.")
                return ActionResult(**copy.deepcopy(prior["result"]))
            if state["status"] != "running":
                return ActionResult("rejected", code="run_not_running", message="The experiment is not running.")
            candidate = copy.deepcopy(state)
            try:
                if not isinstance(request.kind, str) or request.kind not in ACTION_FIELDS or not isinstance(request.params, dict):
                    raise RuleError("invalid_action", "Unknown or malformed action.")
                if set(request.params) - ACTION_FIELDS[request.kind]:
                    raise RuleError("invalid_params", "Unexpected action parameters.")
                result = self._perform(candidate, actor, request)
                accounts.assert_valid(candidate["accounts"], sum((state["config"]["resident_credits"], state["config"]["treasury_credits"])))
            except RuleError as error:
                result = ActionResult("rejected", code=error.code, message=str(error))
            else:
                state.clear()
                state.update(candidate)
            state["operations"][key] = {"actor": actor.actor_id, "fingerprint": fingerprint, "result": result.to_dict()}
            self._event(state, actor.actor_id, request.kind, {"request": asdict(request), "result": result.to_dict()})
            return copy.deepcopy(result)

    def _perform(self, state: Record, actor: ActorContext, request: ActionRequest) -> ActionResult:
        params, actor_id, kind = request.params, actor.actor_id, request.kind
        if kind in ("send_message", "run_tool", "wait", "put_artifact", "claim_task", "submit_task") and actor.role != "resident":
            raise RuleError("forbidden", "This action belongs to a resident.")
        if kind == "publish_task":
            if len(state["tasks"]) >= 64:
                raise RuleError("capacity_limit", "The prototype limits each experiment to 64 tasks.")
            task_id = f"task-{len(state['tasks']) + 1}"
            task = tasks.publish(state["tasks"], task_id, actor_id, params)
            accounts.reserve(state["accounts"], actor_id, task["reward"], task_id)
            self._wake(state)
            return ActionResult("completed", {"task_id": task_id})
        if kind in ("claim_task", "submit_task", "accept_task", "cancel_task"):
            task_id = params.get("task_id")
            task = tasks.get(state["tasks"], task_id)
            if kind == "claim_task":
                tasks.claim(state["tasks"], task_id, actor_id)
            elif kind == "submit_task":
                artifact_id = params.get("artifact_id")
                artifacts.deliver(state["artifacts"], artifact_id, actor_id, task["publisher"])
                tasks.submit(state["tasks"], task_id, actor_id, artifact_id)
            elif kind == "accept_task":
                tasks.accept(state["tasks"], task_id, actor_id)
                accounts.settle(state["accounts"], task_id, task["assignee"], "task_payment")
            else:
                tasks.cancel(state["tasks"], task_id, actor_id)
                accounts.release(state["accounts"], task_id)
            self._wake(state)
            return ActionResult("completed", {"task_id": task_id, "status": task["status"]})
        if kind == "send_message":
            message = messaging.send(state["messages"], state["agents"], state["config"]["chat_mode"], actor_id, params)
            self._wake(state, [message["recipient"]] if message["recipient"] else None)
            return ActionResult("completed", {"message_id": message["id"]})
        if kind == "put_artifact":
            if "content" not in params:
                raise RuleError("invalid_params", "Artifact content is required.")
            artifact_id = f"artifact-{len(state['artifacts']) + 1}"
            artifacts.put(state["artifacts"], artifact_id, actor_id, params["content"])
            return ActionResult("completed", {"artifact_id": artifact_id})
        if kind == "run_tool":
            if params.get("name") != "statistics" or not isinstance(params.get("arguments"), dict):
                raise RuleError("invalid_tool", "Only the scoped statistics tool is available in this prototype.")
            call = self._reserve(state, actor_id, "tool", params)
            return ActionResult("pending", {"call_id": call["id"]})
        if kind == "wait":
            state["agents"][actor_id]["status"] = "waiting"
            return ActionResult("completed", {"waiting": True})
        raise RuleError("invalid_action", "Unsupported action.")

    def _reserve(self, state: Record, actor_id: str, kind: str, payload: Record) -> Record:
        if state["status"] != "running":
            raise RuleError("run_not_running", "The experiment is not running.")
        budget = state["budget"]
        if budget["started"] + budget["reserved"] >= budget["limit"]:
            raise RuleError("budget_exhausted", "The experiment has no call slots remaining.")
        call_id = f"call-{len(state['calls']) + 1}"
        accounts.reserve(state["accounts"], actor_id, state["config"]["demo_call_fee"], call_id)
        call = {
            "id": call_id, "actor": actor_id, "kind": kind, "status": "reserved",
            "payload": copy.deepcopy(payload), "applied": False,
        }
        state["calls"][call_id] = call
        budget["reserved"] += 1
        return call

    def reserve_decision(self, run_id: str, actor_id: str, observation: Record) -> Record | None:
        with self.storage.transaction(run_id) as state:
            if state["status"] != "running":
                return None
            if any(c["status"] in ("reserved", "executing") or
                   (c["kind"] == "model" and c["status"] == "done" and not c["applied"])
                   for c in state["calls"].values()):
                return None
            if actor_id not in state["agents"] or state["agents"][actor_id]["status"] != "active":
                return None
            try:
                call = self._reserve(state, actor_id, "model", {"observation": observation})
            except RuleError as error:
                if error.code == "insufficient_credit":
                    state["agents"][actor_id]["status"] = "insufficient_credit"
                elif error.code == "budget_exhausted":
                    state["status"] = "budget_exhausted"
                else:
                    raise
                self._event(state, actor_id, error.code, {})
                return None
            state["turn"] += 1
            return copy.deepcopy(call)

    def start_call(self, run_id: str, call_id: str) -> Record | None:
        with self.storage.transaction(run_id) as state:
            call = state["calls"][call_id]
            if call["status"] != "reserved" or state["status"] != "running":
                return None
            call["status"] = "executing"
            state["budget"]["reserved"] -= 1
            state["budget"]["started"] += 1
            self._event(state, call["actor"], "call_started", {"call_id": call_id, "kind": call["kind"]})
            return copy.deepcopy(call)

    def finish_call(self, run_id: str, call_id: str, usage: Usage, output: object = None, error: str | None = None) -> None:
        with self.storage.transaction(run_id) as state:
            call = state["calls"][call_id]
            if call["status"] != "executing":
                return
            call["status"] = "failed" if error else "done"
            call["error"] = error
            call["output"] = copy.deepcopy(output)
            call["usage"] = asdict(usage)
            state["usage"].append({"call_id": call_id, "actor": call["actor"], **asdict(usage)})
            # Prototype credit fees are fixed per attempt, independent of provider currency.
            accounts.settle(state["accounts"], call_id, "resource_sink", "prototype_call_fee")
            if call["kind"] == "tool" and not error:
                artifact_id = f"artifact-{len(state['artifacts']) + 1}"
                artifacts.put(state["artifacts"], artifact_id, call["actor"], output)
                call["artifact_id"] = artifact_id
            if error:
                state["agents"][call["actor"]]["status"] = "error"
                state["status"] = "paused"
            self._event(state, call["actor"], "call_finished", {
                "call_id": call_id, "status": call["status"], "usage": asdict(usage), "error": error,
                "artifact_id": call.get("artifact_id"),
            })

    def acknowledge_decision(self, run_id: str, call_id: str) -> None:
        with self.storage.transaction(run_id) as state:
            call = state["calls"][call_id]
            if call["status"] != "done" or call["kind"] != "model":
                raise RuleError("state_conflict", "Only completed decisions can be acknowledged.")
            call["applied"] = True
            agent = state["agents"][call["actor"]]
            agent["message_cursor"] = max(agent["message_cursor"], call["payload"]["observation"]["message_cursor"])

    def record_score(self, run_id: str, task_id: str, report: Record) -> None:
        with self.storage.transaction(run_id) as state:
            if state["scores"].get(task_id) == report:
                return
            state["scores"][task_id] = copy.deepcopy(report)
            self._event(state, "treasury", "independent_score", {"task_id": task_id, **report})
            task = tasks.get(state["tasks"], task_id)
            if task["status"] == "accepted" and report["passed"]:
                state["status"] = "completed"
            elif not report["passed"]:
                state["status"] = "failed"

    def mark_idle(self, run_id: str) -> None:
        with self.storage.transaction(run_id) as state:
            if state["status"] == "running":
                state["status"] = "idle"
                self._event(state, "treasury", "run_idle", {"reason": "No schedulable residents or pending work."})

    def recover(self) -> None:
        for summary in self.list_runs():
            with self.storage.transaction(summary["id"]) as state:
                interrupted = [call for call in state["calls"].values() if call["status"] == "executing"]
                for call in interrupted:
                    call["status"] = "unknown"
                if state["status"] == "running" or interrupted:
                    state["status"] = "paused"
                    self._event(state, "treasury", "restart_recovery", {
                        "unknown_calls": [call["id"] for call in interrupted],
                    })
