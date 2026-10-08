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
schemas/avro/fast/ride/requested/v1/schema.avsc
schemas/avro/fast/ride/accepted/v1/schema.avsc
schemas/avro/fast/ride/completed/v1/schema.avsc
```

Only Avro contracts are accepted. Every contract uses the Fast hierarchy above.

### Example schemas

| Schema | Format | File |
|--------|--------|------|
| Ride Completed | Avro (Fast) | `schemas/avro/fast/ride/completed/v1/schema.avsc` |

## Configuration

No GitHub App settings are required. No Registry credentials are needed for
generation, tests or CI. Manual Apicurio operations accept
`--registry "$APICURIO_URL"` and optional `APICURIO_TOKEN` in the local environment.

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
Avro namespace:    br.com.hellnet.fast.events.{domain}.v{version}
Avro record:       Fast{Domain}{Event}V{version}
```

Examples:

```text
fast-ride-requested
→ schemas/avro/fast/ride/requested/v1
→ br.com.hellnet.fast.ride.requested.v1
→ br.com.hellnet.fast.events.ride.v1
→ FastRideRequestedV1

fast-driver-location-updated
→ schemas/avro/fast/driver/location-updated/v1
→ fast.driver.location.updated.v1
→ br.com.hellnet.fast.events.driver.v1
→ FastDriverLocationUpdatedV1
```

The validator enforces these relationships, so a PR cannot place a Fast Avro contract in a flat `schemas/avro/fast-*` directory.

## Git tags

Each merged schema version receives an immutable tag after it reaches `main`:

```
schema/fast-ride-requested/v1
schema/fast-ride-completed/v1
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

### Register schema manually

```bash
./scripts/register.sh \
  --registry "$APICURIO_URL" \
  --group default \
  --schema schemas/avro/fast/ride/requested/v1
```

`scripts/check-compatibility.sh` performs a non-mutating Apicurio v2 rule test.
It requires an existing artifact with an explicit compatibility rule matching
metadata; missing/mismatched rules and authorization failures stop the check.
It never creates an artifact or updates a rule. Registration is a separate write.

### Redpanda Schema Registry

The repository contains contracts, not event payloads. This script registers Avro
schemas only; it never publishes fake messages. Topic creation is opt-in and does
not publish events.

Prerequisites: `python3` and `curl`. `rpk` is optional and is used only with
`--apply --create-topics`.

```bash
# Safe default: no network writes (REDPANDA_SCHEMA_REGISTRY_URL defaults to
# http://localhost:8081; REDPANDA_BROKERS defaults to localhost:9092).
bash scripts/register-redpanda.sh --dry-run

# Register schemas (does not create topics or publish messages).
bash scripts/register-redpanda.sh --apply --registry http://localhost:8081

# Register and, only when rpk is installed, create the derived topics.
bash scripts/register-redpanda.sh --apply --create-topics
```

The endpoint is the Confluent-compatible Redpanda API:
`POST /subjects/{subject}/versions`, with content type
`application/vnd.schemaregistry.v1+json` and a JSON body whose `schema` value is
the complete Avro document. The stable mapping intentionally keeps subjects and
topics distinct:

| Schema directory | Subject | Topic |
|---|---|---|
| `fast/ride/requested/v1` | `br.com.hellnet.fast.ride.requested.v1` | `br.com.hellnet.fast.ride.requested.v1` |
| `fast/ride/accepted/v1` | `br.com.hellnet.fast.ride.accepted.v1` | `br.com.hellnet.fast.ride.accepted.v1` |
| `fast/driver/location-updated/v1` | `fast.driver.location.updated.v1` | `fast.driver.location.updated.v1` |

Fast Avro directories follow `fast/{domain}/{event}/v{version}`. Event names may
contain additional hyphen-separated words; metadata converts those event segments
to dots for the stable topic/subject name. A dry-run prints the schema, subject, endpoint, and topic without a
write. Registration is idempotent: submitting the same schema to the same
subject lets the registry deduplicate it. Schema Registry synchronization is
separate from publishing events; applications publish real payloads later using
the registered contracts.

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
