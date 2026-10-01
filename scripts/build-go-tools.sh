#!/usr/bin/env sh
set -eu
mkdir -p bin
go build -trimpath -ldflags="-s -w" -o bin/spiceimg ./cmd/spiceimg
go build -trimpath -ldflags="-s -w" -o bin/spicemedia ./cmd/spicemedia
echo "built bin/spiceimg and bin/spicemedia"
