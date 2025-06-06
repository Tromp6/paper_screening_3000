# Quick Setup Guide

## 🚀 **Getting Started in 5 Minutes**

### **1. Install Dependencies**
```bash
pip install -r requirements.txt
```

### **2. Create Environment File**
```bash
# Create .env file
touch .env

# Add your API keys (edit with your favorite editor)
nano .env
```

Add these lines to your `.env` file:
```bash
# OpenAI API (get from https://platform.openai.com/api-keys)
OPENAI_API_KEY=your_openai_api_key_here

# Zotero API (get from https://www.zotero.org/settings/keys) 
ZOT_USER_ID=your_zotero_user_id
ZOT_KEY=your_zotero_api_key_here
COLL_OA=your_zotero_collection_id
```

### **3. Test the Setup**
```bash
# Quick test run
python3 systematic_review.py --view-results --help
```

### **4. Run Your First Review**
```bash
# Start a complete systematic review
python3 systematic_review.py --full-auto --max-results 25
```

### **5. Manual Screening**
```bash
# After the automated workflow completes
python3 systematic_review.py --manual-screen --run review_run_YYYYMMDD_HHMMSS
```

### **6. Import to Zotero**
```bash
# After manual screening
python3 systematic_review.py --import-to-zotero --run review_run_YYYYMMDD_HHMMSS
```

## 🎯 **You're Ready!**

Your systematic literature review platform is now configured and ready to use. Check the main [README.md](README.md) for detailed usage instructions.

## 📞 **Need Help?**

- **Can't find API keys?** Check the Zotero and OpenAI documentation links above
- **Import failing?** The system will show detailed error messages and solutions
- **Want to customize?** Edit `search_config.py` for different research domains

---

**⏱️ Total setup time: ~5 minutes** 