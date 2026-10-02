# Train Celeste textual inversion on Azure from Termux

This path provisions a temporary Azure NVIDIA GPU VM, uploads the local verified Celeste reference pack, trains the SD1.5 textual inversion, downloads the finished artifact, and deletes the Azure resource group by default.

## Requirements on the phone

- Azure CLI authenticated with `az login`
- SSH/SCP
- the verified references at `data/references/celeste_vale/`

Run:

```bash
cd ~/spice-hoes
git pull
chmod +x scripts/azure-textual-inversion.sh scripts/train-textual-inversion.sh
./scripts/azure-textual-inversion.sh
```

Default Azure settings:

```text
resource group: spice-ti-rg
location: eastus
VM: spice-ti-gpu
size: Standard_NC4as_T4_v3
OS: Ubuntu 22.04
```

All are overridable:

```bash
AZURE_LOCATION=westus3 \
AZURE_VM_SIZE=Standard_NC8as_T4_v3 \
STEPS=2000 \
VECTORS=4 \
./scripts/azure-textual-inversion.sh
```

If the default GPU SKU is unavailable in the selected region, choose an NVIDIA GPU VM size available to the subscription and pass it through `AZURE_VM_SIZE`.

The script deletes the entire temporary resource group when it exits. To inspect or reuse the VM:

```bash
KEEP_VM=1 ./scripts/azure-textual-inversion.sh
```

Be aware that `KEEP_VM=1` continues Azure billing until the VM/resource group is stopped or deleted.

The downloaded artifact is:

```text
artifacts/embeddings/cvceleste.safetensors
```

Import that file into Local Dream's Embedding Manager. With the patched Local Dream build running:

```bash
curl -s -X POST http://127.0.0.1:8081/embeddings/reload | jq
curl -s http://127.0.0.1:8081/embeddings | jq
```

The inventory must contain `cvceleste` before running strict identity generation.
