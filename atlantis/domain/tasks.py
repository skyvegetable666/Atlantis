from ..contracts import Record, RuleError


def get(state: Record, task_id: str) -> Record:
    if not isinstance(task_id, str) or task_id not in state:
        raise RuleError("not_found", "Task does not exist in this experiment.")
    return state[task_id]


def publish(state: Record, task_id: str, publisher: str, params: Record) -> Record:
    title, spec = params.get("title"), params.get("spec")
    acceptance = params.get("acceptance")
    if not all(isinstance(value, str) and 0 < len(value) <= 8000 for value in (title, spec, acceptance)):
        raise RuleError("invalid_params", "Title, specification and acceptance terms are required.")
    parent_id = params.get("parent_id")
    if parent_id:
        parent = get(state, parent_id)
        if parent["assignee"] != publisher or parent["status"] != "claimed":
            raise RuleError("forbidden", "Only an active assignee can delegate from this task.")
    task = {
        "id": task_id, "publisher": publisher, "assignee": None,
        "title": title, "spec": spec, "acceptance": acceptance,
        "reward": params.get("reward"), "parent_id": parent_id,
        "input": params.get("input"), "status": "open", "artifact_id": None,
    }
    state[task_id] = task
    return task


def claim(state: Record, task_id: str, actor: str) -> Record:
    task = get(state, task_id)
    if task["status"] != "open":
        raise RuleError("state_conflict", "Task is no longer open.")
    if task["publisher"] == actor:
        raise RuleError("forbidden", "Publishers cannot claim their own task.")
    task.update(status="claimed", assignee=actor)
    return task


def submit(state: Record, task_id: str, actor: str, artifact_id: str) -> Record:
    task = get(state, task_id)
    if task["assignee"] != actor:
        raise RuleError("forbidden", "Only the assignee can submit.")
    if task["status"] != "claimed":
        raise RuleError("state_conflict", "Task is not awaiting a submission.")
    task.update(status="submitted", artifact_id=artifact_id)
    return task


def accept(state: Record, task_id: str, actor: str) -> Record:
    task = get(state, task_id)
    if task["publisher"] != actor:
        raise RuleError("forbidden", "Only the publisher can accept a delivery.")
    if task["status"] != "submitted":
        raise RuleError("state_conflict", "Task has no pending delivery.")
    task["status"] = "accepted"
    return task


def cancel(state: Record, task_id: str, actor: str) -> Record:
    task = get(state, task_id)
    if task["publisher"] != actor:
        raise RuleError("forbidden", "Only the publisher can withdraw an unclaimed offer.")
    if task["status"] != "open":
        raise RuleError("state_conflict", "An established contract cannot be withdrawn unilaterally.")
    task["status"] = "cancelled"
    return task
