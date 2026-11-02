# pedalroute

Route-planning API for the city bike-share. Riders pick a start and end docking station and get
three cycle routes back (fastest, flattest, quietest). Each request searches the city's street
graph, so the API is CPU-bound and is meant to scale out with a HorizontalPodAutoscaler.

## Layout

- `app.py`: the API (Python standard library only), shipped to the pods in a ConfigMap.
- `Chart.yaml`, `values.yaml`, `templates/`: the Helm chart (Deployment, Service, ConfigMap, HPA).
- `load.sh start|stop`: a "morning rush" pod that keeps 8 riders asking for routes.
- `watch.sh`: prints the autoscaler's CPU reading and the replica count every 5 seconds
  (and keeps a copy in `reports/watch.txt`).

## Run locally (minikube with metrics-server)

```
helm install pedalroute . --wait
./load.sh start
./watch.sh
```

Endpoints: `/route?from=1&to=100`, `/stations`, `/stations/<id>`, `/healthz`, `/ready`, `/version`.
