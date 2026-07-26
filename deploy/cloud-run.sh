#!/usr/bin/env bash
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
: "${REGION:=asia-east1}"
: "${SERVICE_NAME:=longread-collector}"
: "${FIRECRAWL_API_KEY:?Set FIRECRAWL_API_KEY}"
: "${GOOGLE_SHEET_ID:=1Ohi2amTCPnIZZont7rwOLO487DFk64-pemLT8O76xq4}"
: "${COLLECTOR_TOKEN:?Set COLLECTOR_TOKEN}"

IMAGE="${REGION}-docker.pkg.dev/${GOOGLE_CLOUD_PROJECT}/longread/${SERVICE_NAME}:latest"

gcloud artifacts repositories describe longread --location "$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create longread --repository-format=docker --location "$REGION"

gcloud builds submit --tag "$IMAGE" .

gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --region "$REGION" \
  --no-allow-unauthenticated \
  --set-env-vars "FIRECRAWL_API_KEY=${FIRECRAWL_API_KEY},JINA_API_KEY=${JINA_API_KEY:-},GOOGLE_SHEET_ID=${GOOGLE_SHEET_ID},GOOGLE_SERVICE_ACCOUNT_FILE=/var/secrets/google/key.json,COLLECTOR_TOKEN=${COLLECTOR_TOKEN}" \
  --set-secrets "/var/secrets/google/key.json=longread-google-service-account:latest"

echo "Deploy complete. Create a Cloud Scheduler job that POSTs {\"query_file\":\"config/queries.yaml\"} to /collect."
