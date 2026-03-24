#!/usr/bin/env python3
import os
import time
import random
import argparse
import json
from datetime import datetime, timezone
import urllib.request
import urllib.error


def dd_events_url(site: str) -> str:
    # US1 site is datadoghq.com -> api.datadoghq.com
    return f"https://api.{site}/api/v1/events"


def send_event(
    url: str,
    api_key: str,
    title: str,
    text: str,
    source_type_name: str,
    tags: list[str],
    aggregation_key: str,
) -> None:
    headers = {"Content-Type": "application/json", "DD-API-KEY": api_key}
    payload = {
        "title": title,
        "text": text,
        "source_type_name": source_type_name,   # this is what drives “Source” in the UI
        "tags": tags,                            # must be ["key:value", ...]
        "aggregation_key": aggregation_key,      # critical for dedupe
        "alert_type": "error",
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status_code = response.getcode()
            if status_code >= 300:
                body = response.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Datadog API error {status_code}: {body}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Datadog API error {exc.code}: {body}") from exc


def build_sumo_payload(
    *,
    summary: str,
    source: str,
    severity: str,
    spatag: str,
    details: str,
    severity_code: str,
    routing_key: str,
) -> dict:
    return {
        "payload": {
            "summary": summary,
            "source": source,
            "severity": severity,
            "custom_details": {
                "spatag": spatag,
                "details": details,
                "severity": severity_code,
            },
        },
        "routing_key": routing_key,
        "event_action": "trigger",
    }


def build_dynatrace_payload(
    *,
    summary: str,
    source: str,
    severity: str,
    details: str,
    environment: str,
    event: str,
    component: str,
    subcomponent: str,
    service: str,
    routing_key: str,
    client_url: str,
) -> dict:
    return {
        "payload": {
            "summary": summary,
            "source": source,
            "severity": severity,
            "custom_details": {
                "details": details,
                "environment": environment,
                "event": event,
                "component": component,
                "subcomponent": subcomponent,
                "service": service,
            },
        },
        "routing_key": routing_key,
        "event_action": "trigger",
        "client_url": client_url,
    }


def build_jl_event_payload(
    *,
    title: str,
    message: str,
    tags: list[str],
    service: str,
    source: str,
    aggregation_key: str,
    pipeline_stamp: str,
    status: str = "info",
) -> dict:
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "content": {
            "timestamp": timestamp,
            "status": status,
            "tags": tags,
            "service": service,
            "source": source,
            "message": message,
            "attributes": {
                "aggregation_key": aggregation_key,
                "pipeline_stamp": pipeline_stamp,
                "service": service,
                "title": title,
                "event_object": service,
                "_dd": {
                    "source_type_name": source,
                    "source_type_name_tag": source.replace(" ", "_"),
                },
                "status": status,
            },
        }
    }


def main():
    parser = argparse.ArgumentParser(description="Send mock DT+Sumo events into Datadog (US1).")
    parser.add_argument("--service", default="payments-api")
    parser.add_argument("--env", default="prod")
    parser.add_argument("--team", default="payments-sre")
    parser.add_argument("--issue", default="error_rate_spike")
    parser.add_argument("--severity", default="sev1")
    parser.add_argument("--source", default="MyApps", help="Datadog event source_type_name")
    parser.add_argument("--routing-key", default="", help="Vendor routing key (optional)")
    parser.add_argument(
        "--mode",
        choices=["sandbox", "jl"],
        default="sandbox",
        help="Which payload set to emit",
    )
    parser.add_argument("--jl-pipeline", default="macbank-demo2")
    parser.add_argument("--jl-event", default="resource_contention")
    parser.add_argument("--jl-component", default="cloudwatch")
    parser.add_argument("--jl-subcomponent", default="")
    parser.add_argument("--dt-count", type=int, default=8)
    parser.add_argument("--sumo-count", type=int, default=3)
    parser.add_argument("--splunk-count", type=int, default=2)
    parser.add_argument("--sleep-min", type=float, default=2.0)
    parser.add_argument("--sleep-max", type=float, default=6.0)
    args = parser.parse_args()

    if args.mode == "jl":
        api_key = os.environ.get("DD_API_KEY_JL")
        if not api_key:
            raise SystemExit("Missing DD_API_KEY_JL env var")
    else:
        api_key = os.environ.get("DD_API_KEY_BS")
        if not api_key:
            raise SystemExit("Missing DD_API_KEY_BS env var")

    site = os.environ.get("DD_SITE", "datadoghq.com")  # US1 default
    url = dd_events_url(site)

    if args.mode == "jl":
        jl_subcomponent = args.jl_subcomponent or f"{args.service}-dds_-_sit"
        base_tags = [
            "source:my_apps",
            f"service:{args.service}",
            f"event:{args.jl_event}",
            f"environment:{args.env}",
            f"subcomponent:{jl_subcomponent}",
            f"component:{args.jl_component}",
            f"pipeline:{args.jl_pipeline}",
        ]
    else:
        base_tags = [
            "demo:macbank-ir",
            f"service:{args.service}",
            f"env:{args.env}",
            f"team:{args.team}",
            f"issue:{args.issue}",
            f"severity:{args.severity}",
        ]

    # 8 Dynatrace-like events -> should dedupe to 1 alert via aggregation_key
    for i in range(args.dt_count):
        tags = base_tags + [
            "vendor:dynatrace",
            "source:dynatrace",
            f"host:pay-{i % 3}",
            f"http.status_code:{random.choice([500, 502, 503])}",
        ]
        aggregation_key = f"{args.issue}|{args.service}|dynatrace"
        problem_id = f"{args.issue}-{i + 1}"
        impacted_entity = f"{args.service}:pay-{i % 3}"
        summary = f"{problem_id} - {args.severity} - {impacted_entity}"
        if args.mode == "jl":
            message = (
                f"OPEN Problem {problem_id} in environment {args.env}\n"
                f"Problem detected at: {datetime.now(timezone.utc).strftime('%H:%M')} (UTC)\n\n"
                f"Simulated Dynatrace problem for {args.service}."
            )
            payload = build_jl_event_payload(
                title=summary,
                message=message,
                tags=tags,
                service=args.service,
                source="my apps",
                aggregation_key=aggregation_key,
                pipeline_stamp=args.jl_pipeline,
            )
        else:
            payload = build_dynatrace_payload(
                summary=summary,
                source=f"Dynatrace GCP OCP Workloads - {args.service}",
                severity="info",
                details=(
                    f"HTTP 5xx rate exceeded threshold on {args.service} "
                    f"(sample {i}). Simulated DT Problem event."
                ),
                environment=args.env,
                event=args.severity,
                component=args.service,
                subcomponent=f"{args.service}-api",
                service=args.service,
                routing_key=args.routing_key,
                client_url=f"https://dynatrace.local/problem/{problem_id}",
            )
        send_event(
            url=url,
            api_key=api_key,
            title=summary,
            text=json.dumps(payload, indent=2),
            source_type_name="dynatrace" if args.mode == "sandbox" else "my apps",
            tags=tags,
            aggregation_key=aggregation_key,  # dedupe key
        )
        print(
            f"Sent event {i + 1}/{args.dt_count} "
            f"[aggregation_key={aggregation_key}] "
            f"title='Dynatrace: High error rate detected' "
            f"tags={tags}"
        )
        time.sleep(random.uniform(args.sleep_min, args.sleep_max))

    # 3 Sumo-like events -> should dedupe to 1 alert via aggregation_key
    for i in range(args.sumo_count):
        tags = base_tags + [
            "vendor:sumologic",
            "source:sumo logic",
            f"region:ap-southeast-{i % 2 + 1}",
            "query:error_rate_5xx",
        ]
        aggregation_key = f"{args.issue}|{args.service}|sumologic"
        summary = f"{args.service} - 5xx error spike"
        if args.mode == "jl":
            payload = build_jl_event_payload(
                title=summary,
                message=f"Sumo alert: 5xx errors for {args.service} (window {i}).",
                tags=tags,
                service=args.service,
                source="my apps",
                aggregation_key=aggregation_key,
                pipeline_stamp=args.jl_pipeline,
            )
        else:
            payload = build_sumo_payload(
                summary=summary,
                source="Sumologic",
                severity="info",
                spatag=args.team,
                details=f"5xx errors spiking for {args.service} (window {i}).",
                severity_code="2",
                routing_key=args.routing_key,
            )
        send_event(
            url=url,
            api_key=api_key,
            title=summary,
            text=json.dumps(payload, indent=2),
            source_type_name="sumo logic" if args.mode == "sandbox" else "my apps",
            tags=tags,
            aggregation_key=aggregation_key,
        )
        print(
            f"Sent event {i + 1}/{args.sumo_count} "
            f"[aggregation_key={aggregation_key}] "
            f"title='Sumo Logic: 5xx error spike' "
            f"tags={tags}"
        )
        time.sleep(random.uniform(args.sleep_min, args.sleep_max))

    # 2 Splunk-like events -> should dedupe to 1 alert via aggregation_key
    for i in range(args.splunk_count):
        tags = base_tags + [
            "vendor:splunk",
            "source:splunk",
            f"index:app-{i % 2}",
            "query:errors_5xx",
        ]
        aggregation_key = f"{args.issue}|{args.service}|splunk"
        summary = f"{args.service} - splunk 5xx spike"
        if args.mode == "jl":
            payload = build_jl_event_payload(
                title=summary,
                message=f"Splunk alert: 5xx errors for {args.service} (window {i}).",
                tags=tags,
                service=args.service,
                source="my apps",
                aggregation_key=aggregation_key,
                pipeline_stamp=args.jl_pipeline,
            )
        else:
            payload = {
                "message": f"Splunk alert: 5xx errors for {args.service} (window {i}).",
                "severity": "critical",
                "service": args.service,
                "env": args.env,
                "team": args.team,
                "issue": args.issue,
            }
        send_event(
            url=url,
            api_key=api_key,
            title=summary,
            text=json.dumps(payload, indent=2),
            source_type_name="splunk" if args.mode == "sandbox" else "my apps",
            tags=tags,
            aggregation_key=aggregation_key,
        )
        print(
            f"Sent event {i + 1}/{args.splunk_count} "
            f"[aggregation_key={aggregation_key}] "
            f"title='Splunk: 5xx error spike' "
            f"tags={tags}"
        )
        time.sleep(random.uniform(args.sleep_min, args.sleep_max))

    print("Done. Search in Datadog Events Explorer for: demo:macbank-ir")


if __name__ == "__main__":
    main()

