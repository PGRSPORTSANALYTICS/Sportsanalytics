#!/bin/bash
set -e

echo "Running post-merge setup..."

echo "Pushing to GitHub..."
git push --force-with-lease origin main || git push --force origin main || true

echo "post-merge OK"
