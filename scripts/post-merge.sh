#!/bin/bash
set -e

echo "Running post-merge setup..."

echo "Pushing to GitHub..."
if [ -n "$GITHUB_TOKEN" ]; then
    git remote set-url origin "https://x-oauth-basic:${GITHUB_TOKEN}@github.com/PGRSPORTSANALYTICS/Sportsanalytics.git"
fi
git push --force-with-lease origin main || git push --force origin main || true

echo "post-merge OK"
