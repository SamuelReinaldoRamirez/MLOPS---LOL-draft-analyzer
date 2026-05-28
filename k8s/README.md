# Kubernetes manifests — production-ready deployment

> **Status: deployable, validated.** The full LoL Draft Predictor stack
> (Postgres, API, Streamlit, MLflow, Prometheus, Grafana, Ingress) is described
> as 32 Kubernetes resources organised into a 3-level Kustomize tree. Offline
> schema validation (`make k8s-validate`) passes against the upstream Kubernetes
> JSON schemas via `kubeconform`. The Phase-3 demo still runs on Docker
> Compose; these manifests are the path to a cluster deployment when needed.

## Tree

```
k8s/
├── kustomization.yaml         # root: aggregates base + monitoring + ingress
├── base/                      # workloads
│   ├── namespace.yaml         # ns: lol-draft
│   ├── configmap.yaml         # non-secret env (mirrors .env.example)
│   ├── secret.yaml            # template (POSTGRES_PASSWORD, GRAFANA_*, RIOT_API_KEY)
│   ├── models-pvc.yaml        # RWX 1Gi shared by api+streamlit
│   ├── mlflow-pvc.yaml        # RWO 5Gi for /mlflow/artifacts
│   ├── postgres-statefulset.yaml   # StatefulSet 1 replica, volumeClaimTemplate 10Gi
│   ├── api-deployment.yaml         # 2 replicas, hardened securityContext
│   ├── api-service.yaml            # ClusterIP :8000
│   ├── api-hpa.yaml                # HPA 2→6 (CPU 70%, mem 80%)
│   ├── streamlit-deployment.yaml   # Deployment + Service + HPA 2→4
│   └── mlflow-deployment.yaml      # Deployment + Service ClusterIP :5000
├── monitoring/                # Phase-4 observability on K8s
│   ├── prometheus-configmap.yaml   # scrapes Service DNS targets
│   ├── prometheus-pvc.yaml         # 5Gi TSDB, 14d retention
│   ├── prometheus-deployment.yaml  # Deployment + Service ClusterIP :9090
│   ├── grafana-configmap.yaml      # datasource + dashboards provider
│   ├── grafana-pvc.yaml            # 1Gi state
│   └── grafana-deployment.yaml     # creds via secretKeyRef
└── ingress/                   # external exposure + lockdown
    ├── ingress.yaml           # nginx-ingress + cert-manager (Let's Encrypt)
    └── networkpolicy.yaml     # default-deny + 6 targeted allow rules
```

## What is included

| Concern                | How                                                                  |
|------------------------|----------------------------------------------------------------------|
| Stateful Postgres      | `StatefulSet` + per-replica PVC (`volumeClaimTemplate`, RWO 10Gi)    |
| Stateless workloads    | `Deployment` for api, streamlit, mlflow, prometheus, grafana          |
| Shared models volume   | `PersistentVolumeClaim` RWX 1Gi — same `.pkl` files across api pods   |
| MLflow artefact store  | `PersistentVolumeClaim` RWO 5Gi mounted at `/mlflow/artifacts`        |
| Prometheus TSDB        | `PersistentVolumeClaim` RWO 5Gi, 14-day retention                    |
| Horizontal scaling     | `HorizontalPodAutoscaler` on api (2→6) and streamlit (2→4)            |
| Config / secrets       | One ConfigMap + one Secret, injected via `envFrom:` in every workload |
| TLS termination        | `Ingress` + cert-manager `ClusterIssuer: letsencrypt-prod`           |
| Namespace lockdown     | `NetworkPolicy` default-deny + 6 targeted allow rules                 |
| Pod hardening          | `runAsNonRoot`, `readOnlyRootFilesystem`, `capabilities: drop ALL`    |
| Prometheus discovery   | Annotations on api pods + scrape job using Service DNS               |
| Grafana auto-provisioning | Datasource + dashboard mounted from ConfigMaps                    |
| Dashboards single-source | `configMapGenerator` reads `monitoring/grafana/dashboards/*.json` |

## Prerequisites (per cluster, one time)

1. **Ingress controller** — install `ingress-nginx`:
   ```bash
   kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml
   ```
2. **cert-manager** with a `ClusterIssuer` named `letsencrypt-prod`:
   ```bash
   kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.15.0/cert-manager.yaml
   # then create the ClusterIssuer (HTTP-01 challenge via the nginx-ingress).
   ```
3. **metrics-server** (required for HPA):
   ```bash
   kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
   ```
4. **CNI with NetworkPolicy support** — Calico / Cilium / Antrea / kube-router.
   `kindnet` and the default GKE CNI also work for `Ingress`-typed rules.

## Prerequisites (per project)

1. **Push images to a registry** (compose builds them locally as
   `lol-draft-api:latest`, etc.). In a real cluster:
   ```bash
   docker compose build
   docker tag lol-draft-api:latest ghcr.io/<org>/lol-draft-api:<tag>
   docker push ghcr.io/<org>/lol-draft-api:<tag>
   ```
   Then either edit each `image:` field or add an overlay with:
   ```yaml
   images:
     - name: lol-draft-api
       newName: ghcr.io/<org>/lol-draft-api
       newTag: <tag>
   ```
2. **Restore the DB dump** into the Postgres pod (one time, after first apply):
   ```bash
   kubectl -n lol-draft cp database/lol_draft.dump postgres-0:/tmp/dump.dvc
   kubectl -n lol-draft exec postgres-0 -- pg_restore \
     -U $POSTGRES_USER -d $POSTGRES_DB /tmp/dump.dvc
   ```
3. **Override `Secret` values** before the first apply (or use SealedSecrets /
   ExternalSecrets pointed at a real secret backend).

## Validation (offline, no cluster needed)

```bash
make k8s-validate
# under the hood:
kubectl kustomize --load-restrictor=LoadRestrictionsNone k8s | \
  kubeconform -summary -strict -ignore-missing-schemas
# → "Summary: 32 resources found parsing stdin - Valid: 32, Invalid: 0"
```

`--load-restrictor=LoadRestrictionsNone` is required because the Grafana
dashboards ConfigMap is generated from
`monitoring/grafana/dashboards/lol_api_overview.json` (outside the `k8s/`
kustomize root). This avoids duplicating the dashboard JSON.

## Apply

```bash
make k8s-apply             # asks for confirmation, then `kubectl apply -k`
make k8s-status            # pods / services / ingress / hpa / pvc
make k8s-delete            # tears the stack down (asks for confirmation)
```

## What is intentionally not here

- **HPA on Postgres / MLflow / Prometheus** — these have single-writer state
  (Postgres TSDB / MLflow file artifacts / Prometheus TSDB). Use HA mode of
  Postgres (managed DB or Patroni) and Thanos / Mimir for Prometheus HA.
- **PodDisruptionBudgets** — easy add (`minAvailable: 1` on every Deployment)
  but adds noise without a planned-disruption story; defer to overlay.
- **PrometheusRule / Alertmanager** — current metrics are demoable; alert
  routing is an SRE-team decision (Slack? PagerDuty?) and lives outside the
  app repo.
- **An auto-retrain CronJob** — `scripts/auto_retrain.py` is currently
  triggered from the host (or compose); promoting it to a CronJob is a
  one-file addition once the training image is pushed to a registry.
