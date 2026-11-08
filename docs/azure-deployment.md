# Deploying the API to Azure

Same route as the data converter (Project 1): build the image in Azure Container Registry
(ACR) and run it on Azure Container Apps. No local Docker needed. Read the cost and budget
sections of that project's `docs/azure-deployment.md` first; they apply here unchanged.

What's different for this service:

- **Bigger container.** The embedding model, torch and Chroma need about 1.5 GB of RAM, so
  use 1 vCPU / 2 GiB instead of 0.25 vCPU / 0.5 GiB. Scaled to zero it still costs nothing
  while idle, but each active second uses more of the free grant.
- **A second secret**, `ANTHROPIC_API_KEY`, for the answer step.
- **The index is baked into the image** (`RUN python -m src.cli build` in the Dockerfile),
  so a new replica starts ready. Documents added through `POST /documents` live in the
  container's filesystem and are **lost when it restarts or scales to zero**. To keep them,
  mount an Azure Files share at `/app/index`, or move the vector store to Azure AI Search
  (below).

## Steps

```bash
az login
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
az provider register --namespace Microsoft.ContainerRegistry

RG=document-qa-rg
LOCATION=germanywestcentral    # Student subscriptions may restrict regions
ACR=documentqa$RANDOM          # Globally unique, letters and digits only
ENVIRONMENT=document-qa-env
APP=document-qa-api
API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo "$API_KEY"                # Save this in a password manager
read -rs ANTHROPIC_API_KEY     # Paste your key; it isn't echoed or saved in shell history

az group create --name $RG --location $LOCATION
az acr create --resource-group $RG --name $ACR --sku Basic
az acr build --registry $ACR --image $APP:v1 .     # from the repository root

az containerapp env create --name $ENVIRONMENT --resource-group $RG --location $LOCATION

az containerapp create \
  --name $APP \
  --resource-group $RG \
  --environment $ENVIRONMENT \
  --image $ACR.azurecr.io/$APP:v1 \
  --registry-server $ACR.azurecr.io \
  --registry-identity system \
  --secrets api-key="$API_KEY" anthropic-key="$ANTHROPIC_API_KEY" \
  --env-vars API_KEY=secretref:api-key ANTHROPIC_API_KEY=secretref:anthropic-key \
  --ingress external \
  --target-port 8000 \
  --cpu 1 --memory 2Gi \
  --min-replicas 0 --max-replicas 1
```

`--max-replicas 1` keeps the in-memory rate limit accurate and means there is only one copy
of uploaded documents.

Check it, then remove everything when you're done:

```bash
URL=https://$(az containerapp show --name $APP --resource-group $RG \
  --query properties.configuration.ingress.fqdn --output tsv)
curl "$URL/health"
curl -X POST "$URL/ask" -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"question": "How long can a Temporary Access Pass be valid?"}'

az group delete --name $RG
```

## Moving the vector store to Azure AI Search

Not implemented; this is the path if the demo grows. `src/store.py` keeps all storage behind
the `Index` class (`add`, `delete_document`, `vector_search`, `keyword_search`), so an
`AzureSearchIndex` with the same methods would slot in. Azure AI Search does hybrid
(BM25 + vector, fused with RRF) natively, which is the retrieval setup the eval chose.
Its free tier (50 MB, 3 indexes at the time of writing) fits this corpus; check the
[pricing page](https://azure.microsoft.com/pricing/details/search/) before relying on that.
