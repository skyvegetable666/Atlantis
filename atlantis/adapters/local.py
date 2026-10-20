import math

from ..contracts import Limits, ModelReply, Record, ScoreReport, ToolReply, Usage


class StatisticsTool:
    def execute(self, name: str, arguments: Record, scope: Record, limits: Limits) -> ToolReply:
        if name != "statistics" or set(arguments) != {"numbers"}:
            raise ValueError("The statistics tool accepts only numbers.")
        numbers = arguments["numbers"]
        if not isinstance(numbers, list) or not 0 < len(numbers) <= 10000:
            raise ValueError("Provide between 1 and 10000 numbers.")
        if any(type(n) not in (int, float) or not math.isfinite(n) or abs(n) > 10**12 for n in numbers):
            raise ValueError("Numbers must be finite and within the prototype range.")
        content = {"count": len(numbers), "sum": sum(numbers), "min": min(numbers), "max": max(numbers)}
        return ToolReply(content, Usage(provider="local-statistics", cost_micros=0))


class StatisticsEvaluator:
    def evaluate(self, task: Record, content: object) -> ScoreReport:
        numbers = sorted(task["input"])
        total = 0
        for number in numbers:
            total += number
        expected = {"count": len(numbers), "sum": total, "min": numbers[0], "max": numbers[-1]}
        valid = isinstance(content, dict) and set(content) == set(expected)
        if valid:
            valid = all(type(content[key]) in (int, float) and content[key] == value for key, value in expected.items())
        return ScoreReport(valid, 1.0 if valid else 0.0, "Exact statistics match." if valid else "Statistics or output schema differ.")


class ScriptedModel:
    """A hiring fixture, deliberately not evidence of emergent cooperation."""

    @staticmethod
    def _reply(kind: str, **params: object) -> ModelReply:
        return ModelReply(kind, params, Usage(provider="scripted-fixture", cost_micros=0, simulated=True))

    def generate(self, observation: Record, limits: Limits) -> ModelReply:
        actor = observation["self"]["id"]
        main = next(t for t in observation["tasks"] if t["id"] == "task-1")
        own_artifacts = [a for a in observation["artifacts"] if a["owner"] == actor]
        children = [t for t in observation["tasks"] if t["parent_id"] == main["id"]]
        multi = len(observation["residents"]) > 1
        if actor == "resident-1":
            if main["status"] == "open":
                return self._reply("claim_task", task_id=main["id"])
            if main["status"] != "claimed":
                return self._reply("wait")
            if multi and not children:
                return self._reply(
                    "publish_task", title="Compute the dataset statistics", spec=main["spec"],
                    acceptance=main["acceptance"], reward=8, parent_id=main["id"], input=main["input"],
                )
            if multi:
                child = children[0]
                if child["status"] == "submitted":
                    return self._reply("accept_task", task_id=child["id"])
                if child["status"] != "accepted":
                    return self._reply("wait")
                if not own_artifacts:
                    delivered = next(a for a in observation["artifacts"] if a["id"] == child["artifact_id"])
                    return self._reply("put_artifact", content=delivered["content"])
            elif not own_artifacts:
                return self._reply("run_tool", name="statistics", arguments={"numbers": main["input"]})
            return self._reply("submit_task", task_id=main["id"], artifact_id=own_artifacts[-1]["id"])
        if not children:
            return self._reply("wait")
        child = children[0]
        if child["status"] == "open":
            return self._reply("claim_task", task_id=child["id"])
        if child["status"] == "claimed" and child["assignee"] == actor:
            sent = any(m["sender"] == actor for m in observation["message_history"])
            if not sent and observation["chat_mode"] != "none":
                params = {"body": "I have claimed the statistics task and will submit the JSON artifact."}
                if observation["chat_mode"] == "private":
                    params["recipient"] = child["publisher"]
                return self._reply("send_message", **params)
            if not own_artifacts:
                return self._reply("run_tool", name="statistics", arguments={"numbers": child["input"]})
            return self._reply("submit_task", task_id=child["id"], artifact_id=own_artifacts[-1]["id"])
        return self._reply("wait")
