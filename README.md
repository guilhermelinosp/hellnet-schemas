# hellnet-schemas

Centralized event-contract repository and Schema Registry automation for event-driven services.

```
Issue → generated PR → validation + review → main → immutable schema tag
                                                    └─ explicit Registry registration
```

[![pr-check](https://github.com/guilhermelinosp/hellnet-schemas/actions/workflows/pr-check.yml/badge.svg)](https://github.com/guilhermelinosp/hellnet-schemas/actions/workflows/pr-check.yml)
[![tag-schema](https://github.com/guilhermelinosp/hellnet-schemas/actions/workflows/tag-schema.yml/badge.svg)](https://github.com/guilhermelinosp/hellnet-schemas/actions/workflows/tag-schema.yml)
[![CodeQL](https://github.com/guilhermelinosp/hellnet-schemas/actions/workflows/codeql.yml/badge.svg)](https://github.com/guilhermelinosp/hellnet-schemas/actions/workflows/codeql.yml)

## How it works

```
Dev ──abre issue──► Issue Template ──Issue event──► Gera schema ──PR──► Review ──merge──► main
                                                                                             │
                                                                                         tag-schema
```

### Fluxo via Issue

1. Dev abre issue com template "New Schema"
2. GitHub Action `process-schema-issue` captura (`issues: opened`)
3. Script `generate-from-issue.sh` gera o schema no formato escolhido
4. Action cria branch, commita o schema, e abre um **Pull Request**
5. Time revisa o PR (diff do schema)
6. Ao merge na `main`, `tag-schema.yml` cria a tag imutável `schema/{nome}/v{versao}`
7. A sincronização com um Schema Registry é feita separadamente, pelo processo de registro correspondente

## Redpanda Schema Registry sync

PRs run a read-only compatibility test (`registry` job, part of `pr-gate`); merges to `main` set the subject
compatibility and register every schema (`sync-registry.yml`). Tailscale lives only in `templates`: both workflows call
`templates/.github/workflows/schema-sync.yml`, which triggers the `schema-registry.yml` hub (OIDC, `tag:github`,
ACL `192.168.1.2:443`). This repository holds no Tailscale variable or secret.

Local run: `python3 scripts/redpanda_registry.py check --registry https://schema.hellnet.com.br`.

## Quick start

### Creating a new schema

Open a new issue and fill the [template](.github/ISSUE_TEMPLATE/new-schema.yml):

```yaml
# What you fill in the issue:
Schema name: fast-order-created
Format: avro
Compatibility: BACKWARD
Fields:
  - name: orderId
    type: string
    required: true
  - name: amount
    type: double
    required: true
  - name: currency
    type: string
    default: "BRL"
```

After submitting:

1. GitHub Action generates the schema, creates the branch and opens a **Pull Request**
2. Team reviews the PR (schema diff)
3. When the PR is merged to `main`, `tag-schema.yml` creates the immutable schema tag
4. `Closes #<issue>` links the issue and closes it when the PR is merged

### Schema storage structure

Fast Avro contracts use the product/domain/event hierarchy:

```text
schemas/
└── avro/
    └── fast/
        └── {domain}/
            └── {event}/
                ├── v1/
                │   ├── schema.avsc
                │   └── .meta.json
                └── v2/
                    ├── schema.avsc
                    └── .meta.json
```

Example:

```text
schemas/avro/fast/order/requested/v1/schema.avsc
schemas/avro/fast/order/accepted/v1/schema.avsc
schemas/avro/fast/order/completed/v1/schema.avsc
```

Only Avro contracts are accepted. Every contract uses the Fast hierarchy above.

### Example schemas

| Schema | Format | File |
|--------|--------|------|
| Order Completed | Avro (Fast) | `schemas/avro/fast/order/completed/v1/schema.avsc` |

## Configuration

No GitHub App settings are required. No Registry credentials are needed for
generation, tests or CI. The Redpanda Schema Registry sync runs in CI (see below).

### Compatibility levels

| Level | Description |
|-------|-------------|
| `BACKWARD` | New schema can read data written with the previous |
| `FORWARD` | Old schema can read data written with the new |
| `FULL` | Both backward and forward compatible |
| `NONE` | No compatibility checks |

Published `vN` directories are append-only and cannot be edited or deleted. Create
the next version instead. Fast Avro versions intentionally have different subjects,
topics and record fullnames: `v2` is a **new contract identity**, not a promise that a
v1 consumer can read v2 events. Its metadata compatibility mode applies inside the
new Registry subject. Other contracts are compared with their previous directory
version. See [the evolution policy and validator limits](CONTRIBUTING.md#evolution-policy).

## Schema naming convention

Fast Avro contracts follow one canonical mapping:

```text
Issue schema name: fast-{domain}-{event}
Repository path:   schemas/avro/fast/{domain}/{event}/v{version}
Metadata name:     fast.{domain}.{event-as-dots}.v{version}
Avro namespace:    fast.events.{domain}.v{version}
Avro record:       Fast{Domain}{Event}V{version}
```

Examples:

```text
fast-order-requested
→ schemas/avro/fast/order/requested/v1
→ fast.order.requested.v1
→ fast.events.order.v1
→ FastOrderRequestedV1

fast-driver-location-updated
→ schemas/avro/fast/driver/location-updated/v1
→ fast.driver.location.updated.v1
→ fast.events.driver.v1
→ FastDriverLocationUpdatedV1
```

The validator enforces these relationships, so a PR cannot place a Fast Avro contract in a flat `schemas/avro/fast-*` directory.

## Git tags

Each merged schema version receives an immutable tag after it reaches `main`:

```
schema/fast-order-requested/v1
schema/fast-order-completed/v1
schema/fast-driver-location-updated/v1
```

## Related repos

| Repo | Purpose |
|------|---------|
| `hellnet-lib-kafka` | Kafka pub/sub library (consumes schemas) |
| `hellnet-lib-telemetry` | OpenTelemetry + logging |

## Development

### Validate schemas locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip --isolated install -r requirements.txt
./scripts/validate.sh
python -m unittest discover -s tests -v
git fetch origin main
python scripts/evolution.py --base origin/main
```

Use Python 3.11 or newer. Validation works offline after dependency installation.
See [contribution instructions](CONTRIBUTING.md) for Avro field types and safe
Issue retries.

### Register schemas

Registration happens in CI on merge to `main` (`sync-registry.yml`). For a read-only local test against the
Registry, run `python3 scripts/redpanda_registry.py check --registry https://schema.hellnet.com.br` (needs the tailnet).

### Redpanda Schema Registry and topics

The repository contains contracts, not event payloads. Schemas are registered by CI on merge to `main`
(`sync-registry.yml`); nothing here publishes messages. The `br.com.hellnet.` prefix applies to **topics only**:
schemas, subjects and Avro namespaces never carry it.

| Schema directory | Subject (schema) | Topic |
|---|---|---|
| `fast/order/requested/v1` | `fast.order.requested.v1` | `br.com.hellnet.fast.order.requested.v1` |
| `fast/order/accepted/v1` | `fast.order.accepted.v1` | `br.com.hellnet.fast.order.accepted.v1` |
| `fast/order/cancelled/v1` | `fast.order.cancelled.v1` | `br.com.hellnet.fast.order.cancelled.v1` |
| `fast/order/completed/v1` | `fast.order.completed.v1` | `br.com.hellnet.fast.order.completed.v1` |

Fast Avro directories follow `fast/{domain}/{event}/v{version}`; event segments joined by hyphens become dots in the
subject. Registration is idempotent: the same schema submitted to the same subject is deduplicated by the registry.
Each contract is registered twice from the same file: as `fast.order.<event>.v1` (catalog) and as
`br.com.hellnet.fast.order.<event>.v1-value` (the topic's subject under TopicNameStrategy, which `hellnet-lib-kafka` and
broker-side schema validation look up). Topics are created in the cluster (`redpanda-topics.sh`), not by CI.

## CI/CD

| Workflow | Trigger | Action |
|----------|---------|--------|
| `issue-schema.yml` | Issue opened/labeled `schema`; manual retry by Issue number | Validates input, generates a schema branch and reuses an existing PR on retries |
| `validate-pr.yml` | PR changing contracts/tooling; reusable call | Runs regression tests, real format validators, append-only history and compatibility gates |
| `codeql.yml` | Push to `main`, PR or manual run | Analyzes GitHub Actions workflows |
| `security.yml` | PR or manual run | Runs Gitleaks and Trivy security scans |
| `tag-schema.yml` | Schema changes merged to `main` | Creates missing immutable schema tags |

This repository contains Avro contracts and focused Python tooling with shell entry points.
CI does not install Go or run Go builds, tests, vet, GoSec or govulncheck.
All workflows use the standard `GITHUB_TOKEN` with job-scoped permissions. There is
no GitHub App, private key or external automation dependency in this repository.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). Licensed under [Apache 2.0](LICENSE).
