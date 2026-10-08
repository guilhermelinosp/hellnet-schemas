"""Sync Avro contracts with the Redpanda Schema Registry (Confluent-compatible API).

check: read-only; every schema must be compatible with the latest registered version.
apply: sets the subject compatibility from .meta.json and registers the schema (idempotent).
"""
import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from contracts import FILES, MODES, confined_path, read_json, require, validate_tree

CONTENT_TYPE = "application/vnd.schemaregistry.v1+json"
# The br.com.hellnet. prefix belongs to topics only. Each contract is registered as its own subject (catalog) and as
# <topic>-value (TopicNameStrategy), the subject hellnet-lib-kafka and broker-side validation look up for a topic.
TOPIC_PREFIX = "br.com.hellnet."


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Registry redirects are refused; supply the final endpoint")


def call(base, path, method="GET", body=None):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": CONTENT_TYPE, "Accept": CONTENT_TYPE}
    if os.environ.get("REDPANDA_REGISTRY_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["REDPANDA_REGISTRY_TOKEN"]
    req = urllib.request.Request(base.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return 404, None
        raise ValueError(f"Registry HTTP {error.code} on {method} {path}") from error


def contracts(root):
    root = Path(root).resolve()
    for meta_path in sorted(root.glob("**/v*/.meta.json")):
        meta = read_json(confined_path(meta_path, root))
        require(meta.get("type") == "avro" and meta.get("compatibility") in MODES, f"invalid metadata: {meta_path}")
        schema = read_json(confined_path(meta_path.parent / FILES["avro"], root))
        document = json.dumps(schema, separators=(",", ":"))
        for subject in (meta["name"], f"{TOPIC_PREFIX}{meta['name']}-value"):
            yield subject, meta["compatibility"], document


def sync(registry, root, apply):
    parsed = urllib.parse.urlsplit(registry)
    require(parsed.scheme in {"http", "https"} and parsed.netloc and not parsed.query and not parsed.fragment
            and not parsed.username, "invalid Registry base URL")
    validate_tree(root)
    found = list(contracts(root))
    require(found, f"no Avro contracts under {root}")
    for subject, compat, schema in found:
        quoted = urllib.parse.quote(subject, safe="")
        payload = {"schema": schema, "schemaType": "AVRO"}
        if apply:
            call(registry, f"/config/{quoted}", "PUT", {"compatibility": compat})
            _, result = call(registry, f"/subjects/{quoted}/versions", "POST", payload)
            print(f"registered {subject} (id {result['id']}, {compat})")
            continue
        status, _ = call(registry, f"/subjects/{quoted}/versions/latest")
        if status == 404:
            print(f"new subject {subject}: will be registered on merge")
            continue
        _, verdict = call(registry, f"/compatibility/subjects/{quoted}/versions/latest", "POST", payload)
        require(verdict.get("is_compatible") is True, f"{subject} is not {compat}-compatible with the Registry")
        print(f"compatible {subject} ({compat})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["check", "apply"])
    parser.add_argument("--registry", default=os.environ.get("REDPANDA_SCHEMA_REGISTRY_URL"))
    parser.add_argument("--schemas", default="schemas", type=Path)
    args = parser.parse_args()
    try:
        require(args.registry, "set --registry or REDPANDA_SCHEMA_REGISTRY_URL")
        sync(args.registry, args.schemas, args.mode == "apply")
    except Exception as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
