import hashlib
from pathlib import Path

from .adapters.gateway import AnthropicGatewayModel, GatewaySettings, SYSTEM_PROMPT
from .adapters.local import ScriptedModel, StatisticsEvaluator, StatisticsTool
from .city import City
from .controller import ExperimentController
from .runtime import ResidentRuntime
from .storage import SQLiteStorage


def build(database: str | Path, env_file: str | Path = ".env") -> tuple[City, ExperimentController, dict]:
    storage = SQLiteStorage(database)
    city = City(storage)
    settings = GatewaySettings.load(env_file)
    runtimes = {"demo": ResidentRuntime(ScriptedModel())}
    if settings:
        runtimes["live"] = ResidentRuntime(AnthropicGatewayModel(settings), {
            "adapter": "anthropic-messages-sse", "model": settings.model, "system_prompt": SYSTEM_PROMPT,
        })
    root = Path(__file__).parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    controller = ExperimentController(city, runtimes, StatisticsTool(), StatisticsEvaluator(), {"source_sha256": digest.hexdigest()})
    capabilities = {"live_available": settings is not None, "model": settings.model if settings else None}
    return city, controller, capabilities
