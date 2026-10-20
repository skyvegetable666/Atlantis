from __future__ import annotations

import threading
from dataclasses import asdict

from .city import City
from .contracts import ActionRequest, ActorContext, EvaluationPort, Limits, ModelCallError, Record, RunConfig, ToolPort, Usage
from .runtime import ResidentRuntime


class ExperimentController:
    def __init__(self, city: City, runtimes: dict[str, ResidentRuntime], tools: ToolPort, evaluator: EvaluationPort, metadata: Record | None = None):
        self.city, self.runtimes, self.tools, self.evaluator = city, runtimes, tools, evaluator
        self.limits = Limits(max_output_tokens=1536, timeout_seconds=60)
        self._step_lock = threading.Lock()
        self.metadata = metadata or {}

    def create_run(self, config: RunConfig) -> str:
        config.validate()
        if config.execution_mode not in self.runtimes:
            raise ValueError("No runtime is configured for this execution mode.")
        return self.city.create_run(config, {
            **self.metadata, "model": self.runtimes[config.execution_mode].metadata,
            "limits": asdict(self.limits), "tool": type(self.tools).__name__, "evaluator": type(self.evaluator).__name__,
        })

    def advance(self, run_id: str) -> Record:
        with self._step_lock:
            state = self.city.snapshot(run_id)
            if state["status"] != "running":
                return state
            main = state["tasks"]["task-1"]
            if main["status"] in ("submitted", "accepted"):
                artifact = state["artifacts"][main["artifact_id"]]
                report = self.evaluator.evaluate(main, artifact["content"])
                if report.passed and main["status"] == "submitted":
                    result = self.city.dispatch(ActorContext(run_id, "treasury", "operator"), ActionRequest(
                        "main-acceptance", "accept_task", {"task_id": main["id"]},
                    ))
                    if result.status != "completed":
                        return self.city.snapshot(run_id)
                self.city.record_score(run_id, main["id"], asdict(report))
                return self.city.snapshot(run_id)
            unapplied = next((c for c in state["calls"].values() if c["kind"] == "model" and c["status"] == "done" and not c["applied"]), None)
            if unapplied:
                self._apply(run_id, unapplied)
                return self.city.snapshot(run_id)
            reserved = next((c for c in state["calls"].values() if c["status"] == "reserved"), None)
            if reserved:
                self._execute(run_id, reserved["id"])
                return self.city.snapshot(run_id)
            active = [a for a in state["agents"].values() if a["status"] == "active"]
            if not active:
                self.city.mark_idle(run_id)
                return self.city.snapshot(run_id)
            actor = active[state["turn"] % len(active)]
            context = ActorContext(run_id, actor["id"])
            call = self.city.reserve_decision(run_id, actor["id"], self.city.observe(context))
            if call:
                self._execute(run_id, call["id"])
            return self.city.snapshot(run_id)

    def _execute(self, run_id: str, call_id: str) -> None:
        call = self.city.start_call(run_id, call_id)
        if call is None:
            return
        mode = self.city.snapshot(run_id)["config"]["execution_mode"]
        try:
            if call["kind"] == "model":
                reply = self.runtimes[mode].decide(call["payload"]["observation"], self.limits)
                self.city.finish_call(run_id, call_id, reply.usage, {"kind": reply.kind, "params": reply.params})
                if self.city.snapshot(run_id)["status"] == "running":
                    self._apply(run_id, self.city.snapshot(run_id)["calls"][call_id])
            else:
                payload = call["payload"]
                reply = self.tools.execute(payload["name"], payload["arguments"], {"run_id": run_id, "actor_id": call["actor"]}, self.limits)
                self.city.finish_call(run_id, call_id, reply.usage, reply.content)
        except Exception as error:
            safe_error = str(error) if isinstance(error, (ValueError, RuntimeError, ModelCallError)) else type(error).__name__
            usage = error.usage if isinstance(error, ModelCallError) else Usage(provider=mode, cost_micros=None, simulated=mode == "demo")
            self.city.finish_call(run_id, call_id, usage, error=safe_error)

    def _apply(self, run_id: str, call: Record) -> None:
        output = call["output"]
        result = self.city.dispatch(ActorContext(run_id, call["actor"]), ActionRequest(
            f"{call['id']}:action", output["kind"], output["params"],
        ))
        if result.code != "run_not_running":
            self.city.acknowledge_decision(run_id, call["id"])
