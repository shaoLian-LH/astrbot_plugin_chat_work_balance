# Changelog

## Unreleased

### Added
- Scaffolded the OneBot / aiocqhttp replay plugin entrypoint and package structure.
- Added plugin configuration schema for selecting an image analysis provider.
- Implemented replay models, OneBot message-chain resolver, resource analysis service, and merged-forward summary service.
- Added fake-object tests for the resolver, replay entrypoint, resource analysis, and merged-forward summary flows.
- Bootstrapped a minimal `uv` project with locked dev-test dependencies for Slice C verification.
- Added forward transcript extraction config, per-layer sampling, OneBot `Forward(id)` expansion, and transcript extraction tests for merged-forward parsing.
