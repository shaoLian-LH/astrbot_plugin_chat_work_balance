# Changelog

## Unreleased

### Added
- Scaffolded the OneBot / aiocqhttp replay plugin entrypoint and package structure.
- Added plugin configuration schema for selecting an image analysis provider.
- Implemented replay models, OneBot message-chain resolver, resource analysis service, and merged-forward summary service.
- Added fake-object tests for the resolver, replay entrypoint, resource analysis, and merged-forward summary flows.
- Bootstrapped a minimal `uv` project with locked dev-test dependencies for Slice C verification.
- Added forward transcript extraction config, per-layer sampling, OneBot `Forward(id)` expansion, and transcript extraction tests for merged-forward parsing.
- Added ForwardSummaryService with dedicated message-provider selection, Chinese prompt guidance, retry handling, and focused summary-service tests.
- Integrated forward transcript extraction and summary service into the OneBot resolver and plugin entrypoint, with end-to-end replay and error-path tests.
- Redacted forward-summary runtime logs so transcript text and LLM summary bodies no longer leak through provider, resolver, or replay-stage logging.
- Added OneBot `get_forward_msg` response-shape compatibility for real `messages` payloads, direct `call_action` adapters, and empty forward references.

### Fixed
- Fixed nested merged-forward parsing for OneBot forward segments that carry inline `data.content` nodes.
