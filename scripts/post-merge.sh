#!/bin/bash
set -e

echo "Running post-merge setup..."

echo "Pushing to GitHub..."
git push origin main || true

echo "post-merge OK"
