# Atlantis development

- Read design.md and docs/contracts.md before changing architecture or rules.
- Keep model decisions, authoritative state changes, external execution and storage separate.
- ResidentRuntime must not import City, storage or the controller.
- Domain modules must not depend on database, HTTP or model implementations.
- City coordinates transactions; adapters cannot write city state.
- Use the same ModelPort for scripted fixtures and live residents. Label fixtures clearly.
- Do not prescribe roles or cooperation in live resident prompts.
- Keep credentials in environment variables or the ignored .env; never put them in observations, responses or tracked files.
- Unknown provider costs remain unknown. Prototype credit fees are separate from provider currency.
- Run `python3 -m unittest discover -s tests -v` for changes to rules or contracts.
- Keep user-approved scope distinct from temporary prototype settings. Do not mark research milestones complete from a scripted demo.
