from ..contracts import Record, RuleError
from ..message_contract import MESSAGE_BODY, MESSAGE_RECIPIENT


def visible(message: Record, actor: str) -> bool:
    return message["recipient"] is None or actor in (message["sender"], message["recipient"])


def send(state: list[Record], residents: Record, mode: str, actor: str, params: Record) -> Record:
    body = MESSAGE_BODY.read(params)
    recipient = params.get(MESSAGE_RECIPIENT.name)
    if mode == "none" or (recipient is not None and mode != "private"):
        raise RuleError("forbidden", "This communication channel is disabled in the experiment.")
    recipient = MESSAGE_RECIPIENT.read(params)
    if recipient is not None and (recipient not in residents or recipient == actor):
        raise RuleError("invalid_recipient", "Private messages require another resident in this run.")
    message = {
        "id": f"message-{len(state) + 1}", "sequence": len(state) + 1,
        "sender": actor, "recipient": recipient, "body": body,
    }
    state.append(message)
    return message


def unread(state: list[Record], actor: str, cursor: int) -> list[Record]:
    return [message for message in state if message["sequence"] > cursor and visible(message, actor)]
