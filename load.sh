#!/usr/bin/env bash
# Simulated morning rush: riders asking for routes between random docking stations.
#   ./load.sh start   starts the "morning-rush" pod (8 riders in parallel, stops by itself after 30 min)
#   ./load.sh stop    stops it
set -euo pipefail
case "${1:-}" in
  start)
    kubectl delete pod morning-rush --ignore-not-found --now >/dev/null
    kubectl apply -f - >/dev/null <<'YAML'
apiVersion: v1
kind: Pod
metadata:
  name: morning-rush
  labels:
    app.kubernetes.io/name: morning-rush
spec:
  restartPolicy: Never
  activeDeadlineSeconds: 1800
  containers:
    - name: riders
      image: curlimages/curl:8.10.1
      resources:
        requests: {cpu: 100m, memory: 32Mi}
        limits: {cpu: 500m, memory: 64Mi}
      command:
        - sh
        - -c
        - |
          rider() {
            while true; do
              from=$(( RANDOM % 100 + 1 )); to=$(( RANDOM % 100 + 1 ))
              [ "$from" = "$to" ] && continue
              curl -s -o /dev/null -m 10 "http://pedalroute/route?from=$from&to=$to"
            done
          }
          for i in 1 2 3 4 5 6 7 8; do rider & done
          wait
YAML
    kubectl wait --for=condition=Ready pod/morning-rush --timeout=120s >/dev/null
    echo "morning rush started: 8 riders asking for routes"
    ;;
  stop)
    kubectl delete pod morning-rush --ignore-not-found --now >/dev/null
    echo "morning rush stopped"
    ;;
  *)
    echo "usage: ./load.sh start|stop" >&2; exit 1 ;;
esac
