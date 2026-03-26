#!/bin/bash
# mobile_claude.sh
eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null)"
cd ~/Dropbox/CA_Works/20260316_Claude_code

echo "=============================="
echo "  Claude Code Mobile Chat"
echo "  Type message + Enter"
echo "  Type 'exit' to quit"
echo "=============================="
echo ""

while true; do
    printf "YOU> "
    read -r input
    [ -z "$input" ] && continue
    [ "$input" = "exit" ] && echo "Bye." && break
    echo ""
    claude -p "$input"
    echo ""
done
