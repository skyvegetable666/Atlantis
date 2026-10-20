from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol

Record = dict[str, Any]


class RuleError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ActorContext:
    run_id: str
    actor_id: str
    role: Literal["resident", "operator"] = "resident"


@dataclass(frozen=True)
class ActionRequest:
    operation_id: str
    kind: str
    params: Record = field(default_factory=dict)


@dataclass(frozen=True)
class ActionResult:
    status: Literal["completed", "pending", "rejected"]
    data: Record = field(default_factory=dict)
    code: str | None = None
    message: str | None = None

    def to_dict(self) -> Record:
        return asdict(self)


@dataclass(frozen=True)
class Limits:
    max_output_tokens: int = 2048
    timeout_seconds: int = 30


@dataclass(frozen=True)
class Usage:
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_micros: int | None = None
    simulated: bool = False
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


class ModelCallError(Exception):
    def __init__(self, message: str, usage: Usage):
        super().__init__(message)
        self.usage = usage


@dataclass(frozen=True)
class ModelReply:
    kind: str
    params: Record
    usage: Usage


@dataclass(frozen=True)
class ToolReply:
    content: Any
    usage: Usage


@dataclass(frozen=True)
class ScoreReport:
    passed: bool
    score: float
    detail: str


@dataclass(frozen=True)
class RunConfig:
    execution_mode: Literal["demo", "live"] = "demo"
    agent_count: int = 2
    chat_mode: Literal["none", "public", "private"] = "private"
    max_calls: int = 80
    resident_credits: int = 100
    treasury_credits: int = 100
    main_reward: int = 60
    demo_call_fee: int = 1

    def validate(self) -> None:
        if self.execution_mode not in ("demo", "live"):
            raise RuleError("invalid_config", "Unknown execution mode.")
        if type(self.agent_count) is not int or self.agent_count not in (1, 2):
            raise RuleError("invalid_config", "This fixture supports one or two residents.")
        if self.chat_mode not in ("none", "public", "private"):
            raise RuleError("invalid_config", "Unknown chat mode.")
        for name in ("max_calls", "resident_credits", "treasury_credits", "main_reward", "demo_call_fee"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise RuleError("invalid_config", f"{name} must be a positive integer.")
        if self.main_reward > self.treasury_credits:
            raise RuleError("invalid_config", "Task rewards need funded backing.")


class StoragePort(Protocol):
    def create(self, state: Record) -> None: ...
    def read(self, run_id: str) -> Record: ...
    def list_runs(self) -> list[Record]: ...
    def transaction(self, run_id: str) -> AbstractContextManager[Record]: ...


class ModelPort(Protocol):
    def generate(self, observation: Record, limits: Limits) -> ModelReply: ...


class ToolPort(Protocol):
    def execute(self, name: str, arguments: Record, scope: Record, limits: Limits) -> ToolReply: ...


class EvaluationPort(Protocol):
    def evaluate(self, task: Record, content: Any) -> ScoreReport: ...
