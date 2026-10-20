import json

from ..contracts import Record, RuleError


def put(state: Record, artifact_id: str, owner: str, content: object) -> Record:
    try:
        encoded = json.dumps(content, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise RuleError("invalid_params", "Artifacts must be finite JSON data.") from error
    if len(encoded.encode()) > 128_000:
        raise RuleError("invalid_params", "The prototype limits each artifact to 128 KB.")
    artifact = {"id": artifact_id, "owner": owner, "content": content, "visible_to": [owner]}
    state[artifact_id] = artifact
    return artifact


def read(state: Record, artifact_id: str, actor: str) -> Record:
    if not isinstance(artifact_id, str):
        raise RuleError("invalid_params", "An artifact identifier is required.")
    artifact = state.get(artifact_id)
    if artifact is None:
        raise RuleError("not_found", "Artifact does not exist.")
    if actor not in artifact["visible_to"]:
        raise RuleError("forbidden", "Artifact is private.")
    return artifact


def deliver(state: Record, artifact_id: str, actor: str, publisher: str) -> None:
    artifact = read(state, artifact_id, actor)
    if artifact["owner"] != actor:
        raise RuleError("forbidden", "A submission must be an artifact owned by the assignee.")
    if publisher not in artifact["visible_to"]:
        artifact["visible_to"].append(publisher)
