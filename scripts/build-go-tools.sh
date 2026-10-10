#!/usr/bin/env sh
set -eu
command -v go >/dev/null 2>&1 || { echo "Go is required: https://go.dev/dl/ (Termux: pkg install golang)" >&2; exit 1; }
mkdir -p bin
go build -trimpath -ldflags="-s -w" -o bin/spiceimg ./cmd/spiceimg
go build -trimpath -ldflags="-s -w" -o bin/spicemedia ./cmd/spicemedia
echo "built bin/spiceimg and bin/spicemedia"
