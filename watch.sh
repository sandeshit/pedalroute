#!/usr/bin/env bash
# Prints the autoscaler's CPU reading and the API's replica count every 5 seconds,
# and keeps a copy in reports/watch.txt. Stop it with Control-C.
cd "$(dirname "$0")"
out=reports/watch.txt
printf '%-8s  %-22s  %-7s  %s\n' "time" "cpu (target 60%)" "wanted" "replicas ready" | tee -a "$out"
while true; do
  cpu=$(kubectl get hpa pedalroute -o jsonpath='{.status.currentMetrics[0].resource.current.averageUtilization}' 2>/dev/null)
  wanted=$(kubectl get hpa pedalroute -o jsonpath='{.status.desiredReplicas}' 2>/dev/null)
  ready=$(kubectl get deployment pedalroute -o jsonpath='{.status.readyReplicas}' 2>/dev/null)
  spec=$(kubectl get deployment pedalroute -o jsonpath='{.spec.replicas}' 2>/dev/null)
  [ -z "$cpu" ] && [ "${wanted:-0}" = 0 ] && wanted="-"
  printf '%-8s  %-22s  %-7s  %s of %s\n' "$(date +%H:%M:%S)" "${cpu:-unknown}${cpu:+%}" "${wanted:-?}" "${ready:-0}" "${spec:-?}" | tee -a "$out"
  sleep 5
done
