#!/usr/bin/env bash

# This script launches the MRS real-time simulation stack using the new decentralized 
# architecture (two separate nodes for observer and main triangulation).

set -euo pipefail

export AUTO_START_NODE_OVERRIDE="decentralized"

SCRIPT_PATH="$(readlink -f "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"

echo "Avviando lo stack in modalità DECENTRALIZED..."
exec "$SCRIPT_DIR/launch_realtime_stack.sh" "$@"
