# Optional AKS Helm

AKS and Helm are optional extensions for this demo. Keep Azure Container Apps as the default deployment target unless a task explicitly asks for AKS.

Render the chart locally:

```bash
helm template careai-platform infra/helm/optional-aks
```

The chart intentionally uses placeholder images and no committed secrets. Set image repositories and tags with `--set` or a private values file if you deploy it to a real AKS cluster.
