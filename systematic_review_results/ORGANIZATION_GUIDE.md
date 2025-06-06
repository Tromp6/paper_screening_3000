# Systematic Review Output Organization Guide

Generated: 2025-06-01 11:41:06

## New Folder Structure

```
systematic_review_results/
├── review_run_YYYYMMDD_HHMMSS/     # Each review run gets its own folder
│   ├── README.md                    # Run-specific documentation
│   ├── 01_papers_collected/         # Raw papers by topic
│   ├── 02_screening_results/        # AI screening decisions
│   ├── 02_reports_generated/        # PRISMA docs and reports
│   ├── 03_zotero_imports/          # Zotero import files
│   └── 04_workflow_logs/           # Complete execution logs
├── documentation/                   # General docs and templates
│   ├── README.md
│   ├── templates/
│   └── prisma_examples/
├── archived_runs/                   # Completed review runs
└── legacy_files/                    # Files from old unorganized system
```

## Benefits of New Organization

### 🎯 **Clear Purpose**
Each folder has a specific, obvious purpose:
- Run folders: Complete results for one review execution
- Documentation: Templates and examples for reuse
- Archive: Historical data that's no longer active

### 📊 **Easy Comparison**
- All runs have identical structure
- Easy to compare results across different runs
- Clear progression from papers → screening → reports → import

### 🔍 **Better Navigation**
- Numbered folders show workflow sequence
- README files explain each folder's contents
- No more guessing what files contain

### 📋 **PRISMA Compliance**
- Complete audit trail for each run
- All documentation in logical sequence
- Easy to generate PRISMA flow diagrams

## Usage Examples

### Starting a New Review
```bash
python3 systematic_review.py --full-auto --max-results 50
```
Creates: `review_run_20250101_143022/` with complete workflow

### Finding Latest Results
```bash
ls -la systematic_review_results/review_run_*
```
Shows all runs, newest first

### Checking Run Progress
```bash
cat systematic_review_results/review_run_*/README.md
```
Shows status of each run

### Archiving Completed Run
```bash
mv systematic_review_results/review_run_20250101_143022/ \
   systematic_review_results/archived_runs/
```

