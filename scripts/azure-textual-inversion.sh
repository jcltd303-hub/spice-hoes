#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PERSONA="${PERSONA:-celeste_vale}"
TOKEN="${TOKEN:-cvceleste}"
REFERENCE_DIR="${REFERENCE_DIR:-$ROOT/data/references/$PERSONA}"
AZURE_RG="${AZURE_RG:-spice-ti-rg}"
AZURE_LOCATION="${AZURE_LOCATION:-eastus}"
AZURE_VM="${AZURE_VM:-spice-ti-gpu}"
AZURE_VM_SIZE="${AZURE_VM_SIZE:-Standard_NC4as_T4_v3}"
AZURE_USER="${AZURE_USER:-spice}"
BASE_MODEL="${BASE_MODEL:-stable-diffusion-v1-5/stable-diffusion-v1-5}"
STEPS="${STEPS:-2000}"
VECTORS="${VECTORS:-4}"
LR="${LR:-5e-4}"
KEEP_VM="${KEEP_VM:-0}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing required command: $1" >&2; exit 1; }; }
need az
need ssh
need scp
need git

if [[ ! -d "$REFERENCE_DIR" ]]; then
  echo "missing verified reference directory: $REFERENCE_DIR" >&2
  exit 1
fi

REF_COUNT="$(find "$REFERENCE_DIR" -maxdepth 1 -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' \) | wc -l | tr -d ' ')"
if [[ "$REF_COUNT" -lt 4 ]]; then
  echo "need at least four reference images in $REFERENCE_DIR; found $REF_COUNT" >&2
  exit 1
fi

if ! az account show >/dev/null 2>&1; then
  echo "Azure CLI is not logged in. Run: az login" >&2
  exit 1
fi

cleanup() {
  if [[ "$KEEP_VM" != "1" ]]; then
    echo "Deleting Azure resource group $AZURE_RG ..."
    az group delete --name "$AZURE_RG" --yes --no-wait >/dev/null 2>&1 || true
  else
    echo "KEEP_VM=1; leaving $AZURE_VM running in $AZURE_RG"
  fi
}
trap cleanup EXIT

echo "Creating resource group $AZURE_RG in $AZURE_LOCATION ..."
az group create --name "$AZURE_RG" --location "$AZURE_LOCATION" >/dev/null

if ! az vm show -g "$AZURE_RG" -n "$AZURE_VM" >/dev/null 2>&1; then
  echo "Creating GPU VM $AZURE_VM ($AZURE_VM_SIZE) ..."
  az vm create     --resource-group "$AZURE_RG"     --name "$AZURE_VM"     --image Ubuntu2204     --size "$AZURE_VM_SIZE"     --admin-username "$AZURE_USER"     --generate-ssh-keys     --public-ip-sku Standard     --os-disk-size-gb 128     --storage-sku Premium_LRS     >/dev/null
fi

IP="$(az vm show -d -g "$AZURE_RG" -n "$AZURE_VM" --query publicIps -o tsv)"
if [[ -z "$IP" ]]; then
  echo "could not resolve VM public IP" >&2
  exit 1
fi
echo "GPU VM: $IP"

echo "Installing NVIDIA driver extension ..."
az vm extension set   --resource-group "$AZURE_RG"   --vm-name "$AZURE_VM"   --publisher Microsoft.HpcCompute   --name NvidiaGpuDriverLinux   --version 1.6   >/dev/null || true

echo "Waiting for SSH ..."
for _ in $(seq 1 60); do
  if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "$AZURE_USER@$IP" true 2>/dev/null; then
    break
  fi
  sleep 10
done
ssh -o StrictHostKeyChecking=no "$AZURE_USER@$IP" true

echo "Waiting for NVIDIA runtime ..."
for _ in $(seq 1 60); do
  if ssh "$AZURE_USER@$IP" 'command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1'; then
    break
  fi
  sleep 10
done
ssh "$AZURE_USER@$IP" nvidia-smi

echo "Preparing remote trainer ..."
ssh "$AZURE_USER@$IP" 'sudo apt-get update -y && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y git python3-venv python3-pip rsync'

REMOTE_ROOT="/home/$AZURE_USER/spice-hoes"
ssh "$AZURE_USER@$IP" "rm -rf '$REMOTE_ROOT' && git clone --depth 1 https://github.com/jcltd303-hub/spice-hoes.git '$REMOTE_ROOT'"
ssh "$AZURE_USER@$IP" "mkdir -p '$REMOTE_ROOT/data/references/$PERSONA'"

echo "Uploading verified Celeste reference pack ..."
scp -o StrictHostKeyChecking=no "$REFERENCE_DIR"/* "$AZURE_USER@$IP:$REMOTE_ROOT/data/references/$PERSONA/"

echo "Installing CUDA PyTorch + textual-inversion dependencies ..."
ssh "$AZURE_USER@$IP" "cd '$REMOTE_ROOT' &&   python3 -m venv .venv-ti &&   . .venv-ti/bin/activate &&   python -m pip install --upgrade pip &&   pip install --index-url https://download.pytorch.org/whl/cu124 torch torchvision &&   grep -vE '^(torch|torchvision)' requirements-textual-inversion.txt > /tmp/spice-ti-req.txt &&   pip install -r /tmp/spice-ti-req.txt &&   accelerate config default"

echo "Training $TOKEN ..."
ssh "$AZURE_USER@$IP" "cd '$REMOTE_ROOT' &&   . .venv-ti/bin/activate &&   PERSONA='$PERSONA' TOKEN='$TOKEN'   BASE_MODEL='$BASE_MODEL' STEPS='$STEPS' VECTORS='$VECTORS' LR='$LR'   REFERENCE_DIR='$REMOTE_ROOT/data/references/$PERSONA'   ./scripts/train-textual-inversion.sh"

mkdir -p "$ROOT/artifacts/embeddings"
echo "Downloading trained embedding ..."
scp "$AZURE_USER@$IP:$REMOTE_ROOT/artifacts/embeddings/$TOKEN.safetensors"     "$ROOT/artifacts/embeddings/$TOKEN.safetensors"

echo
echo "READY:"
echo "  $ROOT/artifacts/embeddings/$TOKEN.safetensors"
echo
echo "Import this file into Local Dream -> Embedding Manager."
