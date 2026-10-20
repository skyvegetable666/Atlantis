from .contracts import Limits, ModelCallError, ModelPort, ModelReply, Record, RuleError


class ResidentRuntime:
    """Produces intentions from observations; has no city or storage reference."""

    def __init__(self, model: ModelPort, metadata: Record | None = None):
        self.model = model
        self.metadata = metadata or {"adapter": type(model).__name__}

    def decide(self, observation: Record, limits: Limits) -> ModelReply:
        reply = self.model.generate(observation, limits)
        if not isinstance(reply, ModelReply):
            raise RuleError("invalid_model_output", "The model must return one structured action.")
        if not isinstance(reply.kind, str) or not isinstance(reply.params, dict):
            raise ModelCallError("The model must return one structured action.", reply.usage)
        return reply
