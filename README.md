# MacBank Incident Response - Mock Events

This repo contains a small Python script that sends mock Dynatrace, Sumo Logic,
and Splunk events into Datadog. It supports two modes:

- `sandbox`: Ben's sandbox pipeline using the original payloads.
- `jl`: JL pipeline using the JL payload format.

## Requirements

- Python 3.10+
- Datadog API keys in your environment

## Setup

```bash
export DD_API_KEY_BS=YOUR_SANDBOX_KEY
export DD_API_KEY_JL=YOUR_JL_KEY
# Optional (default is datadoghq.com)
export DD_SITE=datadoghq.com
```

## Usage

Sandbox mode (default):

```bash
python mock_dt_sumo_events.py
```

Sandbox with options:

```bash
python mock_dt_sumo_events.py --mode sandbox --service payments-api --env prod \
  --dt-count 5 --sumo-count 2 --splunk-count 1
```

JL mode:

```bash
python mock_dt_sumo_events.py --mode jl --service bfspega-dechub --env non \
  --jl-pipeline macbank-demo2 --jl-event resource_contention \
  --jl-component cloudwatch --jl-subcomponent bfspega-dechub-dds_-_sit
```

## Notes

- All events include tags and an `aggregation_key` for correlation.
- `--routing-key` can be passed through to vendor payloads when needed.
