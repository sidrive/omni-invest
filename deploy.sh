#!/bin/bash
set -e

MSG=${1:-"deploy: $(date '+%Y-%m-%d %H:%M') WIB"}

echo "🚀 Deploying backend..."
git add -A
git commit -m "$MSG" || echo "⚠️  Nothing to commit"
git push origin main

echo ""
echo "✅ Push done. Jalankan di STB:"
echo "   /home/sidrive/deploy-backend.sh"
