{{- define "pedalroute.selectorLabels" -}}
app.kubernetes.io/name: pedalroute
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "pedalroute.labels" -}}
{{ include "pedalroute.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
