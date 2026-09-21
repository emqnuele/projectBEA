#!/bin/zsh

set -e

cd "$(dirname "$0")/../.."

MODEL="mlx-community/Qwen3.5-9B-MLX-4bit"
HOST="127.0.0.1"
PORT="8080"

echo "======================================"
echo " SHURA LOCAL INFERENCE"
echo "======================================"
echo "Model : $MODEL"
echo "Host  : $HOST"
echo "Port  : $PORT"
echo "API   : http://$HOST:$PORT/v1"
echo "======================================"
echo

exec ./.venv/bin/mlx_lm.server \
  --model "$MODEL" \
  --host "$HOST" \
  --port "$PORT"
