{{/* Common labels */}}
{{- define "lakehouse.labels" -}}
app.kubernetes.io/part-of: lakehouse
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{/* Secret name: an externally-managed Secret if provided, else the chart's */}}
{{- define "lakehouse.secretName" -}}
{{- if .Values.secrets.existingSecret -}}{{ .Values.secrets.existingSecret }}{{- else -}}{{ .Release.Name }}-secrets{{- end -}}
{{- end -}}

{{/* envFrom the config + secret — every pod that runs ingestion/catalog code */}}
{{- define "lakehouse.envFrom" -}}
- configMapRef:
    name: {{ .Release.Name }}-config
- secretRef:
    name: {{ include "lakehouse.secretName" . }}
{{- end -}}

{{/* Raw-data claim name (chart-managed unless existingClaim set) */}}
{{- define "lakehouse.rawDataClaim" -}}
{{- if .Values.rawData.existingClaim -}}{{ .Values.rawData.existingClaim }}{{- else -}}{{ .Release.Name }}-rawdata{{- end -}}
{{- end -}}
