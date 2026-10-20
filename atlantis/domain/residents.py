from ..contracts import ActorContext, Record, RuleError


def authenticate(state: Record, run_id: str, actor: ActorContext) -> None:
    if actor.run_id != run_id:
        raise RuleError("forbidden", "Experiment identity mismatch.")
    if actor.role == "operator" and actor.actor_id == "treasury":
        return
    if actor.role != "resident" or actor.actor_id not in state:
        raise RuleError("forbidden", "Unknown resident identity.")


def wake(state: Record, eligible: list[str]) -> None:
    for actor_id in eligible:
        if state[actor_id]["status"] in ("waiting", "insufficient_credit"):
            state[actor_id]["status"] = "active"
