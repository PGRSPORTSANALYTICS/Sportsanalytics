#!/bin/bash

# Railway Setup Script
# This helps automate the Railway deployment process

echo "🚀 Railway Deployment Setup"
echo "=============================="
echo ""

# Step 1: Export database
echo "📊 Step 1: Exporting database..."
python3 export_database_to_railway.py

if [ $? -ne 0 ]; then
    echo "❌ Database export failed"
    exit 1
fi

echo ""
echo "✅ Database exported to railway_export/"
echo ""

# Step 2: Git setup
echo "📦 Step 2: Preparing Git repository..."

# Initialize git if not already done
if [ ! -d .git ]; then
    git init
    echo "✅ Git repository initialized"
else
    echo "ℹ️  Git repository already exists"
fi

# Add .gitignore
if [ ! -f .gitignore ]; then
    echo "⚠️  No .gitignore found (should have been created)"
fi

# Stage all files
git add .

echo ""
echo "📋 Files ready to commit:"
git status --short

echo ""
echo "=============================="
echo "✅ Setup Complete!"
echo "=============================="
echo ""
echo "Next Steps:"
echo "1. Create GitHub repository at https://github.com/new"
echo "2. Run these commands:"
echo ""
echo "   git commit -m 'Initial commit for Railway deployment'"
echo "   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git"
echo "   git push -u origin main"
echo ""
echo "3. Go to https://railway.app/"
echo "4. New Project → Deploy from GitHub → Select your repo"
echo "5. Add PostgreSQL database"
echo "6. Set environment variables (see RAILWAY_DEPLOYMENT.md)"
echo "7. Configure services (see RAILWAY_CHECKLIST.md)"
echo ""
echo "📖 Full guide: RAILWAY_DEPLOYMENT.md"
echo "✅ Checklist: RAILWAY_CHECKLIST.md"
echo ""
