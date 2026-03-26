#!/bin/bash
cd /Users/a13371/dev/kage-lab

echo "========================================="
echo "  kage-lab Unified Studio v2.0"
echo "========================================="
echo ""

# サーバー起動（Cloudflare Tunnel 自動接続込み）
python3 unified_server.py
