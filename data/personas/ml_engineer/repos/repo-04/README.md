# model-shelf

One GPU, several models, not all needed all day.

`model-shelf` is a FastAPI service that accepts jobs for different transformer models. Jobs go on a Celery queue (Redis broker); workers ask the registry for the model, which loads it if needed and evicts the least recently used one when the memory budget would be exceeded. A schedule file says which models should be pinned during which hours.

## Endpoints
- `POST /jobs/{model}` returns a job id immediately
- `GET /jobs/{id}` returns status and result
- `GET /models` shows resident models and memory use

## Config
`schedule.yaml` example:
```
summariser:
  resident: ["08:00-18:00"]
```
Metrics are exposed on `/metrics` for Prometheus.
