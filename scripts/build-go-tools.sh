#!/usr/bin/env sh
set -eu
mkdir -p bin
go build -trimpath -ldflags="-s -w" -o bin/spiceimg ./cmd/spiceimg
echo "built bin/spiceimg"
