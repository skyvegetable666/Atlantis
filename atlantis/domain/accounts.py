from ..contracts import Record, RuleError


def new(balances: dict[str, int]) -> Record:
    return {"balances": dict(balances), "holds": {}, "ledger": []}


def available(state: Record, owner: str) -> int:
    return state["balances"].get(owner, 0) - sum(
        hold["amount"] for hold in state["holds"].values() if hold["owner"] == owner
    )


def reserve(state: Record, owner: str, amount: int, reference: str) -> None:
    if type(amount) is not int or amount < 1:
        raise RuleError("invalid_amount", "Credits must be positive integers.")
    if reference in state["holds"]:
        raise RuleError("state_conflict", "A reservation already exists.")
    if available(state, owner) < amount:
        raise RuleError("insufficient_credit", "Available credits do not cover the reservation.")
    state["holds"][reference] = {"owner": owner, "amount": amount}


def settle(state: Record, reference: str, recipient: str, purpose: str) -> None:
    hold = state["holds"].pop(reference, None)
    if hold is None:
        raise RuleError("state_conflict", "Reservation is missing or already settled.")
    state["balances"][hold["owner"]] -= hold["amount"]
    state["balances"][recipient] = state["balances"].get(recipient, 0) + hold["amount"]
    state["ledger"].append({
        "id": reference, "from": hold["owner"], "to": recipient,
        "amount": hold["amount"], "purpose": purpose,
    })


def release(state: Record, reference: str) -> None:
    if state["holds"].pop(reference, None) is None:
        raise RuleError("state_conflict", "Reservation is missing.")


def assert_valid(state: Record, initial_total: int) -> None:
    if sum(state["balances"].values()) != initial_total:
        raise RuntimeError("Credit conservation violated.")
    for owner, balance in state["balances"].items():
        if balance < 0 or available(state, owner) < 0:
            raise RuntimeError("Negative or overspent balance.")
