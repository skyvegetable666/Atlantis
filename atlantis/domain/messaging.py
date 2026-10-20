from ..contracts import Record, RuleError


def visible(message: Record, actor: str) -> bool:
    return message["recipient"] is None or actor in (message["sender"], message["recipient"])


def send(state: list[Record], residents: Record, mode: str, actor: str, params: Record) -> Record:
    recipient, body = params.get("recipient"), params.get("body")
    if not isinstance(body, str) or not 0 < len(body.strip()) <= 8000:
        raise RuleError("invalid_params", "A message must contain between 1 and 8000 characters.")
    if mode == "none" or (recipient is not None and mode != "private"):
        raise RuleError("forbidden", "This communication channel is disabled in the experiment.")
    if recipient is not None and (not isinstance(recipient, str) or recipient not in residents or recipient == actor):
        raise RuleError("invalid_recipient", "Private messages require another resident in this run.")
    message = {
        "id": f"message-{len(state) + 1}", "sequence": len(state) + 1,
        "sender": actor, "recipient": recipient, "body": body,
    }
    state.append(message)
    return message


def unread(state: list[Record], actor: str, cursor: int) -> list[Record]:
    return [message for message in state if message["sequence"] > cursor and visible(message, actor)]
