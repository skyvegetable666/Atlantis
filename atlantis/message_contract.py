from dataclasses import dataclass

from .contracts import Record, RuleError


@dataclass(frozen=True)
class _TextParameter:
    name: str
    error_code: str
    error_message: str
    description: str
    required: bool = False
    nullable: bool = False
    trimmed_min: int | None = None
    trimmed_max: int | None = None

    def read(self, params: Record) -> str | None:
        value = params.get(self.name)
        valid = self.name in params or not self.required
        if valid and value is None and self.nullable:
            return None
        valid = valid and isinstance(value, str)
        if valid and (self.trimmed_min is not None or self.trimmed_max is not None):
            size = len(value.strip())
            valid = ((self.trimmed_min is None or size >= self.trimmed_min)
                     and (self.trimmed_max is None or size <= self.trimmed_max))
        if not valid:
            raise RuleError(self.error_code, self.error_message.format(min=self.trimmed_min, max=self.trimmed_max))
        return value

    def schema(self) -> Record:
        result = {
            "type": ["string", "null"] if self.nullable else "string",
            "description": self.description.format(min=self.trimmed_min, max=self.trimmed_max),
        }
        if self.trimmed_min is not None:
            result["minLength"] = self.trimmed_min
        # A raw maxLength would reject valid messages padded with whitespace.
        return result


MESSAGE_BODY = _TextParameter(
    name="body", required=True, trimmed_min=1, trimmed_max=8000,
    error_code="invalid_params",
    error_message="A message must contain between {min} and {max} characters.",
    description="Message text: {min}-{max} characters after trimming leading and trailing whitespace. Keep the original text.",
)
MESSAGE_RECIPIENT = _TextParameter(
    name="recipient", nullable=True,
    error_code="invalid_recipient",
    error_message="Private messages require another resident in this run.",
    description="Omit or use null for public chat; otherwise use another resident ID from this run for private chat.",
)
MESSAGE_PARAMETERS = (MESSAGE_BODY, MESSAGE_RECIPIENT)


def message_params_schema() -> Record:
    return {
        "type": "object",
        "properties": {parameter.name: parameter.schema() for parameter in MESSAGE_PARAMETERS},
        "required": [parameter.name for parameter in MESSAGE_PARAMETERS if parameter.required],
        "additionalProperties": False,
    }
