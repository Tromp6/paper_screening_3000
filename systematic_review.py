# systematic_review.py — Master workflow for systematic literature reviews
"""
COMPREHENSIVE SYSTEMATIC REVIEW WORKFLOW - PRISMA COMPLIANT
Single entry point for the complete PRISMA-compliant systematic review process.

This script orchestrates the query-by-query iterative workflow:
1. Interactive query-by-query paper collection and AI screening
2. Manual review interface for human validation
3. PRISMA documentation generation from all queries
4. Zotero import of final approved papers

PRISMA-COMPLIANT APPROACH:
- Uses external queries_config.json with 8 strategic queries
- 5+ citation threshold for quality assurance (uniform PRISMA-compliant)
- Balanced attack/defense coverage (jailbreak vs. safety research)
- Complete documentation for reproducibility

MAIN WORKFLOW (Query-by-Query Default):
    python3 systematic_review.py                    # Start new workflow
    python3 systematic_review.py --max-results 50   # Limit papers per query

RESUME WORKFLOW:
    python3 systematic_review.py --start-from 3 --run review_run_YYYYMMDD_HHMMSS
    python3 systematic_review.py --run review_run_YYYYMMDD_HHMMSS

MANUAL SCREENING (after AI screening):
    python3 systematic_review.py --manual-screen --run review_run_YYYYMMDD_HHMMSS

ZOTERO IMPORT (after manual review):
    python3 systematic_review.py --import-to-zotero --run review_run_YYYYMMDD_HHMMSS

OTHER OPTIONS:
    python3 systematic_review.py --view-results --run review_run_YYYYMMDD_HHMMSS

QUERY-BY-QUERY FEATURES:
- Processes one strategic query at a time (fetch + AI screen combined)
- Interactive review after each query with detailed results
- Resume capability: start from any query number  
- Preserves previous results when modifying later queries
- On-demand directory creation (no pre-created folders)
- Generates combined PRISMA report only when all queries complete
- Uses external queries_config.json for easy query modification

QUALITY APPROACH:
- Timeframe: 2022-2025 (modern LLM era)
- Citation threshold: 5+ for quality assurance (PRISMA-compliant uniform)
- Attack/Defense balance: Refined queries for proportional coverage
- Expected total: ~300 high-quality papers
"""

import os, sys, time, json
from datetime import datetime
from typing import Dict, List, Optional
import subprocess

# Import our workflow modules
try:
    from screening_workflow import fetch_and_organize_papers, SCREENING_DIR, TOPICS
    from ai_screening import screen_topic_with_ai, generate_ai_screening_report
    from prisma_generator import save_prisma_documentation, collect_screening_data
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure all workflow scripts are in the same directory")
    sys.exit(1)

# ── Reproducibility Constants ───────────────────────────────

SEARCH_VERSION = "v1.4_2025-01-11_defensive_systems"
SCREENING_VERSION = "v1.0_2025-01-11"
FIXED_END_DATE = "2025-01-01"  # Fixed end date for reproducibility
DEFAULT_START_DATE = "2022-01-01"  # Focused on modern LLM security era

# Import refined search configuration - use fallback since no strategic queries needed for query-by-query
try:
    # Constants are now imported from constants.py above
    PRISMA_SEARCH_AVAILABLE = True
except ImportError:
    print("⚠️  Warning: constants.py not available - using fallback configuration")
    PRISMA_SEARCH_AVAILABLE = False
    DEFAULT_START_DATE = "2022-01-01"
    FIXED_END_DATE = "2025-01-01"
    SEARCH_VERSION = "v1.1_2025-01-11"

# ── OPENALEX INTEGRATION AND ZOTERO FUNCTIONS ─────────────────────

def openalex_query_with_metadata(term: str, start_date: str = None, end_date: str = None, 
                  min_citations: int = 0, pub_types: List[str] = None, 
                  open_access_only: bool = False, peer_reviewed_only: bool = True,
                  top_venues_only: bool = False, max_results: int = None) -> tuple:
    """Query OpenAlex API with metadata tracking"""
    import requests
    
    if start_date is None:
        start_date = DEFAULT_START_DATE
    if end_date is None:
        end_date = FIXED_END_DATE
    
    # Build OpenAlex API parameters using the correct working syntax
    base = "https://api.openalex.org/works"
    params = {
        "search": term,
        "per_page": 200,
        "mailto": "example@uni.edu",  # Required by OpenAlex
        "sort": "cited_by_count:desc"
    }
    
    # Build filters using correct OpenAlex syntax
    filters = []
    
    # Date range filter - use correct OpenAlex syntax
    if start_date and end_date:
        filters.append(f"from_publication_date:{start_date},to_publication_date:{end_date}")
    elif start_date:
        filters.append(f"from_publication_date:{start_date},to_publication_date:{FIXED_END_DATE}")
    elif end_date:
        filters.append(f"to_publication_date:{end_date}")
    
    # Citation threshold filter - use correct syntax
    if min_citations > 0:
        filters.append(f"cited_by_count:>{min_citations}")
    
    # Publication types filter
    if pub_types:
        type_filter = "|".join(pub_types)
        filters.append(f"type:{type_filter}")
    
    # Open access filter
    if open_access_only:
        filters.append("is_oa:true")
    
    # Peer review filter (exclude preprints)
    if peer_reviewed_only:
        filters.append("type:!preprint")
    
    # Top venues only filter
    if top_venues_only:
        filters.append("primary_location.source.is_in_doaj:true|primary_location.source.impact_factor:>1")
    
    # Add filters to params if any
    if filters:
        params["filter"] = ",".join(filters)
    
    # Collect papers
    papers = []
    total_collected = 0
    page = 1
    
    print(f"🔍 OpenAlex Query: {term}")
    print(f"📅 Date Range: {start_date} to {end_date}")
    print(f"📊 Min Citations: {min_citations}")
    print(f"🔧 API Filters: {params.get('filter', 'None')}")
    
    cursor = "*"  # OpenAlex cursor paging
    total = None
    
    while cursor:
        params["cursor"] = cursor
        try:
            response = requests.get(base, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if total is None:
                total = data["meta"]["count"]
                print(f"   📊 Total results found: {total}")
                if max_results and total > max_results:
                    print(f"   ⚡ Limiting to {max_results} results")
            
            results = data.get("results", [])
            if not results:
                break
            
            for work in results:
                # Extract and clean paper metadata
                paper = extract_paper_metadata(work)
                papers.append(paper)
                total_collected += 1
                
                # Stop if we've reached max_results
                if max_results and total_collected >= max_results:
                    break
            
            print(f"   📄 Page {page}: {len(results)} papers (total: {total_collected})")
            
            # Check if we should continue
            if max_results and total_collected >= max_results:
                break
            
            # Check for next page
            cursor = data.get("meta", {}).get("next_cursor")
            if not cursor:
                break
            
            page += 1
            time.sleep(0.1)  # Rate limiting
            
        except requests.exceptions.RequestException as e:
            print(f"❌ API Error: {e}")
            break
        except Exception as e:
            print(f"❌ Processing Error: {e}")
            break
    
    # Create search metadata
    search_metadata = {
        "query": term,
        "api_endpoint": base,
        "date_range": f"{start_date} to {end_date}",
        "min_citations": min_citations,
        "peer_reviewed_only": peer_reviewed_only,
        "total_found": total_collected,
        "max_results_limit": max_results,
        "search_timestamp": datetime.now().isoformat(),
        "filters_applied": filters,
        "api_params": params
    }
    
    print(f"✅ Found {len(papers)} papers for query: {term}")
    return papers, search_metadata

def extract_paper_metadata(work: dict) -> dict:
    """Extract and normalize metadata from OpenAlex work object"""
    
    # Basic bibliographic info
    paper = {
        "title": work.get("title", "").strip(),
        "doi": work.get("doi", "").replace("https://doi.org/", "") if work.get("doi") else "",
        "publication_year": work.get("publication_year"),
        "publication_date": work.get("publication_date"),
        "type": work.get("type", "article"),
        "citation_count": work.get("cited_by_count", 0),
        "is_oa": work.get("open_access", {}).get("is_oa", False),
        "abstract": "",  # OpenAlex doesn't provide abstracts
        "openalex_id": work.get("id", "")
    }
    
    # Authors
    authors = []
    for author in work.get("authorships", []):
        author_info = author.get("author", {})
        if author_info:
            authors.append({
                "name": author_info.get("display_name", ""),
                "id": author_info.get("id", ""),
                "orcid": author_info.get("orcid")
            })
    paper["authors"] = authors
    
    # Venue information
    venue = work.get("primary_location", {}).get("source") or work.get("host_venue", {})
    if venue:
        paper["venue"] = {
            "name": venue.get("display_name", ""),
            "type": venue.get("type", ""),
            "issn": venue.get("issn_l") or venue.get("issn"),
            "is_oa": venue.get("is_oa", False)
        }
    else:
        paper["venue"] = {}
    
    # Concepts/keywords
    concepts = []
    for concept in work.get("concepts", []):
        concepts.append({
            "name": concept.get("display_name", ""),
            "score": concept.get("score", 0),
            "level": concept.get("level", 0)
        })
    paper["concepts"] = concepts
    
    # Volume/issue/pages if available
    location = work.get("primary_location", {}) or work.get("best_oa_location", {})
    if location:
        paper["volume"] = location.get("volume")
        paper["issue"] = location.get("issue") 
        paper["first_page"] = location.get("first_page")
        paper["last_page"] = location.get("last_page")
    
    return paper

def openalex_to_zotero(work: dict) -> dict:
    """Convert OpenAlex work to Zotero-compatible format"""
    
    # Determine item type
    work_type = work.get("type", "article").lower()
    if work_type in ["journal-article", "article"]:
        item_type = "journalArticle"
    elif work_type in ["book-chapter", "chapter"]:
        item_type = "bookSection"
    elif work_type in ["book", "monograph"]:
        item_type = "book"
    elif work_type in ["proceedings-article", "conference-paper"]:
        item_type = "conferencePaper"
    elif work_type == "preprint":
        item_type = "preprint"
    elif work_type in ["dissertation", "thesis"]:
        item_type = "thesis"
    else:
        item_type = "journalArticle"  # Default fallback
    
    # Build Zotero item
    zotero_item = {
        "itemType": item_type,
        "title": work.get("title", ""),
        "creators": [],
        "date": work.get("publication_date", ""),
        "url": work.get("openalex_id", ""),
        "abstractNote": work.get("abstract", ""),
        "extra": f"Citation count: {work.get('citation_count', 0)}\nOpenAlex ID: {work.get('openalex_id', '')}"
    }
    
    # Add DOI only for compatible item types
    if item_type in ["journalArticle", "conferencePaper", "preprint"] and work.get("doi"):
        zotero_item["DOI"] = work["doi"]
    
    # Authors
    if work.get("authors"):
        for author in work["authors"]:
            name = author.get("name", "")
            if name:
                # Try to split first/last name
                name_parts = name.split()
                if len(name_parts) >= 2:
                    zotero_item["creators"].append({
                        "creatorType": "author",
                        "firstName": " ".join(name_parts[:-1]),
                        "lastName": name_parts[-1]
                    })
                else:
                    zotero_item["creators"].append({
                        "creatorType": "author",
                        "name": name
                    })
    
    # Venue-specific fields
    venue = work.get("venue", {})
    if venue and venue.get("name"):
        if item_type == "journalArticle":
            zotero_item["publicationTitle"] = venue["name"]
            if venue.get("issn"):
                zotero_item["ISSN"] = venue["issn"]
        elif item_type == "conferencePaper":
            zotero_item["proceedingsTitle"] = venue["name"]
        elif item_type == "bookSection":
            zotero_item["bookTitle"] = venue["name"]
    
    # Volume/issue/pages
    if work.get("volume"):
        zotero_item["volume"] = str(work["volume"])
    if work.get("issue"):
        zotero_item["issue"] = str(work["issue"])
    if work.get("first_page") and work.get("last_page"):
        zotero_item["pages"] = f"{work['first_page']}-{work['last_page']}"
    elif work.get("first_page"):
        zotero_item["pages"] = str(work["first_page"])
    
    # Year
    if work.get("publication_year"):
        zotero_item["date"] = str(work["publication_year"])
    
    return zotero_item

def push_papers(papers: List[dict], collection_key: str):
    """Push papers to Zotero with error handling"""
    
    import os
    from pyzotero import zotero
    
    # Get Zotero credentials from environment
    zot_user_id = os.getenv('ZOT_USER_ID')
    zot_key = os.getenv('ZOT_KEY')
    
    if not zot_user_id or not zot_key:
        print("❌ Zotero credentials not configured in .env file")
        print("   Add ZOT_USER_ID and ZOT_KEY to your .env file")
        return 0, len(papers)
    
    successful = 0
    failed = 0
    
    try:
        # Initialize Zotero client
        zot = zotero.Zotero(zot_user_id, 'user', zot_key)
        
        print(f"📚 Importing {len(papers)} papers to Zotero collection: {collection_key}")
        
        for i, paper in enumerate(papers, 1):
            try:
                # Check if paper already exists by DOI
                doi = paper.get("DOI", paper.get("doi"))
                if doi:
                    existing = zot.items(q=doi, limit=1)
                    if existing:
                        print(f"   ⚠️  Paper {i} already exists (DOI: {doi})")
                        failed += 1
                        continue
                
                # Create item in Zotero
                response = zot.create_items([paper])
                
                if response.get('success'):
                    # Add to collection if specified
                    if collection_key and collection_key != "LLM_JAILBREAK_SURVEY":
                        item_key = response['success']['0']
                        try:
                            zot.addto_collection(collection_key, item_key)
                        except Exception as e:
                            print(f"   ⚠️  Added to library but failed to add to collection: {e}")
                    
                    successful += 1
                    print(f"   ✅ Paper {i}: {paper.get('title', 'Unknown')[:50]}...")
                else:
                    failed += 1
                    print(f"   ❌ Paper {i} failed: {response.get('failed', 'Unknown error')}")
                    
            except Exception as e:
                failed += 1
                print(f"   ❌ Paper {i} failed: {str(e)}")
        
        print(f"   ✅ Successfully imported: {successful}")
        print(f"   ❌ Failed imports: {failed}")
        
        return successful, failed
        
    except Exception as e:
        print(f"❌ Zotero connection failed: {e}")
        print("   Check your ZOT_USER_ID and ZOT_KEY in .env file")
        return 0, len(papers)

def save_search_results(papers: List[dict], query: str, search_metadata: dict, output_dir: str = "zotero_imports"):
    """Save search results with metadata for reproducibility"""
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Create filename from query
    safe_query = "".join(c if c.isalnum() or c in "- " else "_" for c in query)[:50]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_query}_{timestamp}.json"
    
    results_data = {
        "search_metadata": search_metadata,
        "papers": papers,
        "export_timestamp": datetime.now().isoformat(),
        "total_papers": len(papers)
    }
    
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(results_data, f, indent=2, ensure_ascii=False)
    
    print(f"💾 Search results saved: {filepath}")
    return filepath

def save_workflow_log(run_dir: str, workflow_steps: List[Dict], metadata: Dict):
    """Save complete workflow execution log"""
    
    log_file = os.path.join(run_dir, "04_workflow_logs", "workflow_log.json")
    
    workflow_log = {
        "workflow_metadata": {
            "run_id": os.path.basename(run_dir),
            "start_time": metadata.get("start_time"),
            "end_time": datetime.now().isoformat(),
            "search_version": SEARCH_VERSION,
            "workflow_version": metadata.get("workflow_version", "v1.0"),
            "total_duration": str(datetime.now() - datetime.fromisoformat(metadata.get("start_time", datetime.now().isoformat())))
        },
        "execution_steps": workflow_steps,
        "reproducibility_info": {
            "search_period": f"{DEFAULT_START_DATE} to {FIXED_END_DATE}",
            "api_base": "https://api.openalex.org/works",
            "screening_model": "gpt-4o",
            "exact_replication": "Use DOI lists in paper collection results"
        }
    }
    
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(workflow_log, f, indent=2, ensure_ascii=False)
    
    print(f"📋 Workflow log saved: {log_file}")
    return log_file

# ── Master Workflow Configuration ───────────────────────────

def create_run_folder() -> tuple:
    """Create organized folder structure for query-by-query review runs"""
    
    # Create timestamp for this run
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"review_run_{run_timestamp}"
    
    # Main results directory structure
    base_dir = "systematic_review_results"
    run_dir = os.path.join(base_dir, run_id)
    
    # Query-by-query directories only
    directories = {
        "run_root": run_dir,
        "reports": os.path.join(run_dir, "02_reports_generated"),
        "zotero": os.path.join(run_dir, "03_zotero_imports"),
        "logs": os.path.join(run_dir, "04_workflow_logs"),
        
        # General documentation (not run-specific)
        "documentation": os.path.join(base_dir, "documentation"),
        "templates": os.path.join(base_dir, "documentation", "templates"),
        "archive": os.path.join(base_dir, "archived_runs")
    }
    
    # Create all directories
    for dir_path in directories.values():
        os.makedirs(dir_path, exist_ok=True)
    
    # Create README file for this run
    readme_content = f"""# Query-by-Query Systematic Review Run: {run_id}

## Run Information
- **Run ID**: {run_id}
- **Mode**: Query-by-Query Iterative Workflow (Default)
- **Started**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **Search Version**: {SEARCH_VERSION}
- **Search Period**: {DEFAULT_START_DATE} to {FIXED_END_DATE}
- **Topic**: Jailbreak Techniques for Large Language Models and Defensive Countermeasures

## Folder Structure
- `01_individual_queries/` - Created dynamically as each query is processed
  - `papers/query_XX/` - Papers collected for each specific query
  - `screening/query_XX/` - AI screening results for each query
- `02_reports_generated/` - PRISMA documentation and combined reports
- `03_zotero_imports/` - Final combined import files
- `04_workflow_logs/` - Workflow execution logs and state

## Query-by-Query Process
Each query creates its own folder only when processed:
1. Query processed → `01_individual_queries/papers/query_XX/` created
2. AI screening → `01_individual_queries/screening/query_XX/` created
3. Manual screening → Updates screening results in place
4. Final report → Combines all completed queries

## Reproducibility
All search parameters and processing steps documented for exact replication.
Query state and progress saved for resume capability.

## Commands
- Continue workflow: `python3 systematic_review.py --query-by-query --run {run_id}`
- Manual screening: `python3 systematic_review.py --manual-screen --run {run_id}`
- Zotero import: `python3 systematic_review.py --import-to-zotero --run {run_id}`
"""
    
    readme_file = os.path.join(run_dir, "README.md")
    with open(readme_file, 'w', encoding='utf-8') as f:
        f.write(readme_content)
    
    # Create documentation README if it doesn't exist
    doc_readme = os.path.join(directories["documentation"], "README.md")
    if not os.path.exists(doc_readme):
        doc_content = f"""# Systematic Review Documentation

This folder contains general documentation and templates that apply across all review runs.

## Contents
- `templates/` - PRISMA templates and documentation templates
- `search_strategies/` - Documented search strategies and versions
- `methodology/` - General methodology documentation

## Run-Specific Results
Individual review runs are stored in numbered folders in the parent directory.
Each run contains its own complete documentation and results.

## Current Active Runs
Check the parent directory for folders named `review_run_YYYYMMDD_HHMMSS`
"""
        os.makedirs(os.path.dirname(doc_readme), exist_ok=True)
        with open(doc_readme, 'w', encoding='utf-8') as f:
            f.write(doc_content)
    
    print(f"📁 Created organized run folder: {run_dir}")
    print(f"📋 Run ID: {run_id}")
    print(f"📄 Run documentation: {readme_file}")
    
    return run_dir, directories

WORKFLOW_VERSION = "v1.0_2025-01-11"
DEFAULT_MAX_RESULTS = None  # Use complete dataset with quality filters
DEFAULT_MIN_CITATIONS = 15  # PRISMA-compliant quality threshold
DEFAULT_CONFIDENCE = 0.7

class SystematicReviewWorkflow:
    """Master class for managing the query-by-query systematic review workflow"""
    
    def __init__(self):
        self.workflow_start = datetime.now()
        self.steps_completed = []
        self.results = {}
        
        # Create organized folder structure for this run
        self.run_dir, self.directories = create_run_folder()
        self.metadata = {
            "start_time": self.workflow_start.isoformat(),
            "workflow_version": WORKFLOW_VERSION,
            "run_id": os.path.basename(self.run_dir)
        }
        
    def log_step(self, step_name: str, result: any = None):
        """Log completed workflow steps"""
        self.steps_completed.append({
            "step": step_name,
            "timestamp": datetime.now().isoformat(),
            "result": result
        })
        
    def print_workflow_header(self):
        """Print workflow introduction"""
        print("🎯 SYSTEMATIC LITERATURE REVIEW WORKFLOW")
        print("=" * 80)
        print(f"📋 Topic: Jailbreak Techniques for Large Language Models and Defensive Countermeasures")
        print(f"🔍 Search Version: {SEARCH_VERSION}")
        print(f"📅 Search Period: {DEFAULT_START_DATE} to {FIXED_END_DATE}")
        print(f"🤖 Workflow Version: {WORKFLOW_VERSION}")
        print(f"📁 Run Directory: {self.run_dir}")
        print(f"⏰ Started: {self.workflow_start.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
    def step_1_fetch_papers(self, max_results: int = DEFAULT_MAX_RESULTS) -> Dict:
        """Step 1: Fetch papers using PRISMA-compliant improved search strategy"""
        print("\n📊 STEP 1: FETCH PAPERS - PRISMA-COMPLIANT IMPROVED SEARCH")
        print("─" * 70)
        print(f"📅 Timeframe: {DEFAULT_START_DATE} to {FIXED_END_DATE} (modern LLM era)")
        print(f"🔍 Search strategy: Improved 15-query approach with organized topic folders")
        print(f"📊 Quality threshold: {DEFAULT_MIN_CITATIONS}+ citations for impact assessment")
        print(f"🔬 PRISMA compliance: Balanced attack/defense coverage, organized by topic")
        print("─" * 70)
        
        try:
            if PRISMA_SEARCH_AVAILABLE:
                # Use our improved strategic search with organized topic folders
                print("🎯 Using improved strategic search with topic organization")
                
                # Create documentation directory for search strategy
                docs_dir = os.path.join(self.run_dir, "04_workflow_logs")
                os.makedirs(docs_dir, exist_ok=True)
                
                # Run strategic search with documentation
                papers_folder = os.path.join(self.run_dir, "01_papers_collected")
                # from zap3zotero import strategic_queries_search_organized  # Legacy workflow - not used in query-by-query mode
                # total_papers, topic_papers = strategic_queries_search_organized(papers_folder)
                
                print("⚠️ Legacy workflow not available - this method is deprecated in favor of query-by-query mode")
                return self._fallback_search_method()
                
        except Exception as e:
            print(f"❌ Error in paper fetching: {e}")
            return {"status": "error", "message": str(e)}
    
    def step_2_ai_screening(self, confidence_threshold: float = DEFAULT_CONFIDENCE) -> Dict:
        """Step 2: AI-powered screening of all topics"""
        print("\n🤖 STEP 2: AI-POWERED SCREENING")
        print("─" * 50)
        
        screening_results = {}
        total_included = 0
        total_excluded = 0
        
        for topic_key, topic_info in TOPICS.items():
            try:
                print(f"\n🔍 Screening {topic_info['name']}...")
                result = screen_topic_with_ai(
                    topic_key, 
                    confidence_threshold=confidence_threshold,
                    papers_dir=self.directories["papers"],
                    output_dir=self.directories["screening"]
                )
                screening_results[topic_key] = result
                total_included += result["included_papers"]
                total_excluded += result["excluded_papers"]
                time.sleep(2)  # Rate limiting between topics
            except Exception as e:
                print(f"❌ Error screening {topic_key}: {e}")
                screening_results[topic_key] = {"status": "failed", "error": str(e)}
        
        summary = {
            "status": "completed",
            "total_included": total_included,
            "total_excluded": total_excluded,
            "confidence_threshold": confidence_threshold,
            "topic_results": screening_results,
            "output_directory": self.directories["screening"]
        }
        
        self.log_step("ai_screening", summary)
        print(f"\n✅ Step 2 completed: {total_included} papers included, {total_excluded} excluded")
        print(f"📁 Screening results saved to: {self.directories['screening']}")
        return summary
    
    def step_3_generate_reports(self) -> Dict:
        """Step 3: Generate AI screening and PRISMA reports"""
        print("\n📋 STEP 3: GENERATE REPORTS")
        print("─" * 50)
        
        try:
            # Generate AI screening report
            print("🤖 Generating AI screening report...")
            ai_report_file = generate_ai_screening_report(
                screening_dir=self.directories["screening"],
                output_dir=self.directories["reports"]
            )
            
            # Generate PRISMA documentation
            print("📊 Generating PRISMA documentation...")
            screening_data = collect_screening_data(papers_dir=self.directories["papers"])
            prisma_files = save_prisma_documentation(
                screening_data, 
                output_dir=self.directories["reports"]
            )
            
            result = {
                "status": "completed",
                "ai_report": ai_report_file,
                "prisma_files": prisma_files,
                "screening_data": screening_data,
                "output_directory": self.directories["reports"]
            }
            
            self.log_step("generate_reports", result)
            print(f"✅ Step 3 completed: Reports generated")
            print(f"📁 Reports saved to: {self.directories['reports']}")
            return result
        except Exception as e:
            error_result = {"status": "failed", "error": str(e)}
            self.log_step("generate_reports", error_result)
            print(f"❌ Step 3 failed: {e}")
            return error_result
    
    def run_full_workflow(self, max_results: int = DEFAULT_MAX_RESULTS, 
                         confidence_threshold: float = DEFAULT_CONFIDENCE) -> Dict:
        """Run the complete PRISMA-compliant workflow end-to-end"""
        print("🚀 RUNNING FULL AUTOMATED WORKFLOW - PRISMA COMPLIANT")
        print("=" * 80)
        print(f"🔬 Approach: Refined search strategy with quality filtering")
        print(f"📊 Quality threshold: {DEFAULT_MIN_CITATIONS}+ citations")
        print(f"📅 Timeframe: {DEFAULT_START_DATE} to {FIXED_END_DATE}")
        print(f"⚖️  PRISMA compliance: No arbitrary limits, balanced coverage")
        print("=" * 80)
        
        workflow_results = {}
        
        # Step 1: Fetch papers using refined PRISMA-compliant approach
        workflow_results["step_1"] = self.step_1_fetch_papers()  # No max_results limit
        if workflow_results["step_1"]["status"] == "failed":
            return self._finish_workflow(workflow_results, "failed_at_step_1")
        
        # Step 2: AI screening
        workflow_results["step_2"] = self.step_2_ai_screening(confidence_threshold)
        if workflow_results["step_2"]["status"] == "failed":
            return self._finish_workflow(workflow_results, "failed_at_step_2")
        
        # Step 3: Generate reports
        workflow_results["step_3"] = self.step_3_generate_reports()
        if workflow_results["step_3"]["status"] == "failed":
            return self._finish_workflow(workflow_results, "failed_at_step_3")
        
        return self._finish_workflow(workflow_results, "completed")
    
    def _finish_workflow(self, workflow_results: Dict, status: str) -> Dict:
        """Complete the workflow and save logs"""
        
        # Save workflow log
        log_file = save_workflow_log(self.run_dir, self.steps_completed, self.metadata)
        
        # Print summary
        self.print_workflow_summary(workflow_results)
        
        workflow_results["workflow_status"] = status
        workflow_results["run_directory"] = self.run_dir
        workflow_results["workflow_log"] = log_file
        
        return workflow_results
    
    def print_workflow_summary(self, results: Dict):
        """Print comprehensive workflow summary"""
        print("\n" + "=" * 80)
        print("📋 SYSTEMATIC REVIEW WORKFLOW SUMMARY")
        print("=" * 80)
        
        duration = datetime.now() - self.workflow_start
        print(f"⏰ Total Duration: {duration}")
        
        # Only check step results (step_1, step_2, etc.), not workflow metadata strings
        step_results = {k: v for k, v in results.items() if k.startswith('step_') and isinstance(v, dict)}
        completed_steps = len([s for s in step_results.values() if s.get('status') == 'completed'])
        print(f"📊 Steps Completed: {completed_steps}/3")
        
        if "step_1" in results and isinstance(results["step_1"], dict) and results["step_1"]["status"] == "completed":
            print(f"📄 Papers Fetched: {results['step_1']['total_papers']}")
        
        if "step_2" in results and isinstance(results["step_2"], dict) and results["step_2"]["status"] == "completed":
            print(f"✅ Papers Included: {results['step_2']['total_included']}")
            print(f"❌ Papers Excluded: {results['step_2']['total_excluded']}")
        
        print("\n📁 Generated Files:")
        if "step_3" in results and isinstance(results["step_3"], dict) and results["step_3"]["status"] == "completed":
            print(f"  🤖 AI Report: {results['step_3']['ai_report']}")
            for file in results["step_3"]["prisma_files"]:
                print(f"  📋 PRISMA: {file}")
        
        print("\n🎉 SYSTEMATIC REVIEW WORKFLOW COMPLETE!")
        print("📖 Ready for manual screening and Zotero import")
        print(f"📋 Next step: python3 systematic_review.py --manual-screen --run {os.path.basename(self.run_dir)}")
        print("=" * 80)
    
    def manual_screening_interface(self):
        """Interactive manual screening of AI-selected papers from query-by-query workflow"""
        print("\n👤 MANUAL SCREENING INTERFACE")
        print("=" * 80)
        print("Review AI-screened papers and make final inclusion/exclusion decisions")
        print("=" * 80)
        
        # Find all completed query screening results
        screening_files = self._find_query_screening_files()
        if not screening_files:
            print("❌ No AI screening results found")
            print("🔄 Run AI screening first with: --query-by-query")
            return
        
        print(f"📊 Found {len(screening_files)} completed queries for manual review")
        
        # Ask user what they want to review
        print("\n📋 What would you like to review?")
        print("1. 🟢 Only AI-INCLUDED papers (recommended for efficiency)")
        print("2. 🔴 Only AI-REJECTED papers (check for false negatives)")
        print("3. 🔄 BOTH included and rejected papers (comprehensive review)")
        print("4. 📊 Show statistics first")
        print("5. ✅ ACCEPT all AI decisions and proceed to Zotero import")
        
        while True:
            choice = input("\n🎯 Select option (1-5): ").strip()
            if choice in ["1", "2", "3", "4", "5"]:
                break
            print("❌ Please enter 1, 2, 3, 4, or 5")
        
        # Handle option 5: Accept all AI decisions
        if choice == "5":
            print("\n✅ ACCEPTING ALL AI DECISIONS")
            print("=" * 60)
            
            total_ai_included = 0
            total_accepted = 0
            
            for query_id, screening_file in screening_files.items():
                with open(screening_file, 'r', encoding='utf-8') as f:
                    screening_data = json.load(f)
                
                screening_results = screening_data.get("screening_results", [])
                ai_included = [r for r in screening_results if r.get("decision") == "INCLUDE"]
                
                # Mark all AI-included papers as manually accepted
                for result in ai_included:
                    result["manual_screening"] = {
                        "decision": "INCLUDE", 
                        "timestamp": datetime.now().isoformat(),
                        "method": "bulk_accept_ai_decisions"
                    }
                
                # Save updated results
                with open(screening_file, 'w', encoding='utf-8') as f:
                    json.dump(screening_data, f, indent=2, ensure_ascii=False)
                
                total_ai_included += len(ai_included)
                total_accepted += len(ai_included)
                
                query_name = screening_data.get("query_config", {}).get("description", f"Query {query_id}")
                print(f"📂 {query_name}: {len(ai_included)} papers accepted")
            
            print(f"\n📊 BULK ACCEPTANCE COMPLETE")
            print(f"✅ Total AI-included papers accepted: {total_accepted}")
            print(f"🚀 Proceeding directly to Zotero import...")
            
            # Automatically proceed to Zotero import
            print(f"\n📚 IMPORTING TO ZOTERO")
            print("=" * 60)
            try:
                import_results = self.import_to_zotero_after_manual_review()
                if import_results["status"] == "completed":
                    print(f"\n🎉 COMPLETE WORKFLOW FINISHED!")
                    print(f"📊 Papers imported to Zotero: {import_results['papers_imported']}")
                    print(f"📈 Success rate: {import_results.get('success_rate', 'N/A')}")
                    print(f"📁 Import documentation: {import_results.get('documentation', 'N/A')}")
                    return
                else:
                    print(f"❌ Zotero import failed: {import_results.get('error', 'Unknown error')}")
                    return
            except Exception as e:
                print(f"❌ Error during Zotero import: {e}")
                print(f"📋 Manual import command: python3 systematic_review.py --import-to-zotero --run {os.path.basename(self.run_dir)}")
                return
        
        # Show statistics if requested
        if choice == "4":
            self._show_query_screening_statistics(screening_files)
            print("\n📋 What would you like to review?")
            print("1. 🟢 Only AI-INCLUDED papers")
            print("2. 🔴 Only AI-REJECTED papers") 
            print("3. 🔄 BOTH included and rejected papers")
            print("5. ✅ ACCEPT all AI decisions and proceed to Zotero import")
            while True:
                choice = input("\n🎯 Select option (1-3, 5): ").strip()
                if choice in ["1", "2", "3", "5"]:
                    break
                print("❌ Please enter 1, 2, 3, or 5")
            
            # Handle option 5 after showing statistics
            if choice == "5":
                return self.manual_screening_interface()  # Recursive call to handle option 5
        
        # Determine what to review (for options 1-3)
        review_included = choice in ["1", "3"]
        review_rejected = choice in ["2", "3"]
        
        print(f"\n🔍 REVIEW MODE:")
        if review_included and review_rejected:
            print("📋 Reviewing BOTH AI-included and AI-rejected papers")
        elif review_included:
            print("🟢 Reviewing only AI-INCLUDED papers")
        elif review_rejected:
            print("🔴 Reviewing only AI-REJECTED papers")
        
        # Load AI screening results and conduct review
        total_reviewed = 0
        total_changes = 0
        
        for query_id, screening_file in screening_files.items():
            with open(screening_file, 'r', encoding='utf-8') as f:
                screening_data = json.load(f)
            
            query_config = screening_data.get("query_config", {})
            query_name = query_config.get("description", f"Query {query_id}")
            screening_results = screening_data.get("screening_results", [])
            
            # Filter papers based on user choice
            papers_to_review = []
            if review_included:
                ai_included = [r for r in screening_results if r.get("decision") == "INCLUDE"]
                papers_to_review.extend(ai_included)
            
            if review_rejected:
                ai_rejected = [r for r in screening_results if r.get("decision") == "EXCLUDE"]
                papers_to_review.extend(ai_rejected)
            
            if not papers_to_review:
                print(f"\n📂 {query_name}: No papers to review")
                continue
            
            print(f"\n📂 {query_name}: {len(papers_to_review)} papers to review")
            print("─" * 60)
            
            topic_changes = 0
            changes_made = 0  # Initialize changes_made for this query
            
            for i, result in enumerate(papers_to_review, 1):
                ai_decision = result.get("decision", "UNKNOWN")
                confidence = result.get("confidence", 0.0)
                reason = result.get("reason", "No reason")
                
                # Determine paper status emoji
                status_emoji = "🟢" if ai_decision == "INCLUDE" else "🔴" if ai_decision == "EXCLUDE" else "❓"
                
                print(f"\n[{i}/{len(papers_to_review)}] Paper:")
                print(f"📄 Title: {result.get('title', 'No title')}")
                authors = result.get('authors', [])
                if authors and isinstance(authors, list):
                    author_names = [a.get('name', str(a)) if isinstance(a, dict) else str(a) for a in authors[:3]]
                    print(f"👥 Authors: {', '.join(author_names)}")
                print(f"📍 Venue: {result.get('venue', {}).get('name', 'Unknown') if isinstance(result.get('venue'), dict) else result.get('venue', 'Unknown')} ({result.get('publication_year', 'Unknown')})")
                print(f"{status_emoji} AI Decision: {ai_decision} (confidence: {confidence:.2f})")
                print(f"💭 AI Reason: {reason}")
                
                if result.get("abstract"):
                    abstract = result["abstract"][:300] + "..." if len(result["abstract"]) > 300 else result["abstract"]
                    print(f"📄 Abstract: {abstract}")
                
                # Show current manual decision if exists
                existing_manual = result.get("manual_screening", {})
                if existing_manual:
                    manual_decision = existing_manual.get("decision", "UNKNOWN")
                    manual_timestamp = existing_manual.get("timestamp", "Unknown")
                    print(f"👤 Previous Manual Decision: {manual_decision} (at {manual_timestamp[:19]})")
                
                while True:
                    if ai_decision == "INCLUDE":
                        choice_input = input(f"\n👤 Your decision [A]ccept/[R]eject/[S]kip: ").strip().upper()
                    else:  # AI rejected it
                        choice_input = input(f"\n👤 Your decision [I]nclude/[R]eject (confirm)/[S]kip: ").strip().upper()
                    
                    if choice_input == "A" or choice_input == "I":
                        # Save original AI decision for audit trail
                        if "original_ai_decision" not in result:
                            result["original_ai_decision"] = result["decision"]
                            result["original_ai_reason"] = result["reason"]
                            result["original_ai_confidence"] = result["confidence"]
                        
                        # Overwrite decision directly
                        result["decision"] = "INCLUDE"
                        result["confidence"] = 1.0
                        result["reason"] = f"Manual override: Included by human reviewer (original AI: {result.get('original_ai_decision', 'UNKNOWN')})"
                        result["manual_timestamp"] = datetime.now().isoformat()
                        
                        # Set manual_screening field for detection logic
                        result["manual_screening"] = {
                            "decision": "INCLUDE",
                            "timestamp": datetime.now().isoformat(),
                            "method": "individual_query_review"
                        }
                        
                        if ai_decision == "EXCLUDE":
                            print("🔄 Overriding AI rejection - paper INCLUDED")
                            changes_made += 1
                        else:
                            print("✅ Confirmed for inclusion")
                        break
                    elif choice_input == "R":
                        # Save original AI decision for audit trail
                        if "original_ai_decision" not in result:
                            result["original_ai_decision"] = result["decision"]
                            result["original_ai_reason"] = result["reason"]
                            result["original_ai_confidence"] = result["confidence"]
                        
                        # Overwrite decision directly
                        result["decision"] = "EXCLUDE"
                        result["confidence"] = 1.0
                        result["reason"] = f"Manual override: Excluded by human reviewer (original AI: {result.get('original_ai_decision', 'UNKNOWN')})"
                        result["manual_timestamp"] = datetime.now().isoformat()
                        
                        # Set manual_screening field for detection logic
                        result["manual_screening"] = {
                            "decision": "EXCLUDE",
                            "timestamp": datetime.now().isoformat(),
                            "method": "individual_query_review"
                        }
                        
                        if ai_decision == "INCLUDE":
                            print("🔄 Overriding AI inclusion - paper REJECTED")
                            changes_made += 1
                        else:
                            print("❌ Confirmed rejection")
                        break
                    elif choice_input == "S":
                        print("⏭️ Skipped (keeping AI decision)")
                        # Even for skipped papers, mark that they were manually reviewed
                        result["manual_screening"] = {
                            "decision": result.get("decision", "UNKNOWN"),
                            "timestamp": datetime.now().isoformat(),
                            "method": "individual_query_review_skipped"
                        }
                        break
                    else:
                        if ai_decision == "INCLUDE":
                            print("❌ Invalid choice. Please enter A (Accept), R (Reject), or S (Skip)")
                        else:
                            print("❌ Invalid choice. Please enter I (Include), R (Reject), or S (Skip)")
                
                total_reviewed += 1
            
            total_changes += topic_changes
            
            # Save updated results
            with open(screening_file, 'w', encoding='utf-8') as f:
                json.dump(screening_data, f, indent=2, ensure_ascii=False)
            
            # Update summary with final counts after manual screening
            self._update_query_summary_after_manual_screening(screening_file, screening_data)
            
            print(f"\n📊 {query_name} completed: {topic_changes} AI decisions overridden")
        
        print(f"\n{'='*80}")
        print("📋 MANUAL SCREENING COMPLETE")
        print(f"{'='*80}")
        print(f"📊 Total papers reviewed: {total_reviewed}")
        print(f"🔄 AI decisions changed: {total_changes}")
        print(f"✅ Ready for Zotero import")
        print(f"📋 Next step: python3 systematic_review.py --import-to-zotero --run {os.path.basename(self.run_dir)}")
        print(f"{'='*80}")
    
    def _find_query_screening_files(self) -> Dict[int, str]:
        """Find all completed query screening files"""
        screening_files = {}
        queries_dir = os.path.join(self.run_dir, "01_individual_queries", "screening")
        
        if not os.path.exists(queries_dir):
            return screening_files
        
        for query_folder in os.listdir(queries_dir):
            if query_folder.startswith("query_"):
                try:
                    query_id = int(query_folder.split("_")[1])
                    screening_file = os.path.join(queries_dir, query_folder, "ai_screening_results.json")
                    if os.path.exists(screening_file):
                        screening_files[query_id] = screening_file
                except (ValueError, IndexError):
                    continue
        
        return screening_files
    
    def _show_query_screening_statistics(self, screening_files):
        """Show summary of manual screening results across all queries"""
        print("\n" + "="*60)
        print("📊 MANUAL SCREENING RESULTS BY QUERY")
        print("="*60)
        
        total_manually_reviewed = 0
        total_manually_included = 0
        total_manually_excluded = 0
        
        for query_id, screening_file in screening_files.items():
            with open(screening_file, 'r', encoding='utf-8') as f:
                screening_data = json.load(f)
            
            screening_results = screening_data.get("screening_results", [])
            manually_reviewed = [r for r in screening_results if r.get("manual_screening")]
            manually_included = [r for r in manually_reviewed if r["manual_screening"].get("decision") == "INCLUDE"]
            manually_excluded = [r for r in manually_reviewed if r["manual_screening"].get("decision") == "EXCLUDE"]
            
            total_manually_reviewed += len(manually_reviewed)
            total_manually_included += len(manually_included)
            total_manually_excluded += len(manually_excluded)
            
            if manually_reviewed:
                print(f"\n🔍 Query #{query_id}:")
                print(f"   👤 {len(manually_reviewed)} papers manually reviewed")
                print(f"   ✅ {len(manually_included)} manually included")
                print(f"   ❌ {len(manually_excluded)} manually excluded")
        
        print(f"\n📊 TOTAL ACROSS ALL QUERIES:")
        print(f"   👤 {total_manually_reviewed} papers manually reviewed")
        print(f"   ✅ {total_manually_included} manually included")
        print(f"   ❌ {total_manually_excluded} manually excluded")
        print("="*60)
    
    def import_to_zotero_after_manual_review(self) -> Dict:
        """Import final approved papers to Zotero after manual screening"""
        print("\n📚 IMPORTING FINAL APPROVED PAPERS TO ZOTERO")
        print("=" * 80)
        
        # Find all completed query screening results
        screening_files = self._find_query_screening_files()
        if not screening_files:
            print("❌ No screening results found")
            return {"status": "failed", "error": "No screening results available"}
        
        # Collect manually reviewed papers from all queries
        final_approved = []
        stats_by_query = {}
        
        for query_id, screening_file in screening_files.items():
            with open(screening_file, 'r', encoding='utf-8') as f:
                screening_data = json.load(f)
            
            query_config = screening_data.get("query_config", {})
            query_name = query_config.get("description", f"Query {query_id}")
            screening_results = screening_data.get("screening_results", [])
            
            ai_included = [r for r in screening_results if r.get("decision") == "INCLUDE"]
            
            manual_approved = []
            manual_rejected = 0
            
            for result in ai_included:
                manual_decision = result.get("manual_screening", {}).get("decision")
                
                if manual_decision == "INCLUDE":
                    manual_approved.append(result)
                elif manual_decision == "EXCLUDE":
                    manual_rejected += 1
                elif manual_decision == "DEFERRED" or manual_decision is None:
                    # Keep AI decision if not manually reviewed
                    manual_approved.append(result)
            
            final_approved.extend(manual_approved)
            stats_by_query[query_id] = {
                "query_name": query_name,
                "ai_included": len(ai_included),
                "manual_approved": len(manual_approved),
                "manual_rejected": manual_rejected
            }
            
            print(f"📂 {query_name}: {len(manual_approved)} papers approved for import")
        
        if not final_approved:
            print("⚠️  No papers approved for import")
            return {"status": "completed", "papers_imported": 0}
        
        print(f"\n📊 Total papers for import: {len(final_approved)}")
        
        # Convert and import to Zotero with improved error handling
        try:
            from screening_workflow import import_approved_papers_from_directory
            # openalex_to_zotero and push_papers functions are defined in this file
            
            # Get Zotero collection from environment variable
            import os
            zotero_collection = os.getenv('COLL_OA', 'fallbackExample')  # Use your actual collection ID as default
            
            # Convert to Zotero format with pre-validation
            zotero_items = []
            conversion_failures = []
            
            for result in final_approved:
                try:
                    # Pre-validate and fix common issues
                    cleaned_paper = self._clean_paper_for_zotero(result)
                    zotero_item = openalex_to_zotero(cleaned_paper)
                    zotero_items.append(zotero_item)
                except Exception as e:
                    conversion_failures.append({
                        "paper": result,
                        "error": str(e),
                        "title": result.get("title", "Unknown")
                    })
                    print(f"⚠️  Conversion failed for: {result.get('title', 'Unknown')[:60]}... - {e}")
            
            print(f"📚 Importing {len(zotero_items)} papers to Zotero...")
            
            # Import in batches with detailed error tracking
            total_successful = 0
            total_failed = 0
            batch_size = 20
            import_failures = []
            
            for i in range(0, len(zotero_items), batch_size):
                batch = zotero_items[i:i+batch_size]
                successful, failed = push_papers(batch, zotero_collection)
                total_successful += successful
                total_failed += failed
                
                # Track failures for documentation
                if failed > 0:
                    batch_start = i
                    batch_end = min(i + batch_size, len(zotero_items))
                    for j in range(batch_start, batch_end):
                        if j < len(final_approved):  # Safety check
                            import_failures.append({
                                "paper": final_approved[j],
                                "title": final_approved[j].get("title", "Unknown"),
                                "batch": f"{i//batch_size + 1}",
                                "estimated_error": "Likely DOI/itemType mismatch or duplicate"
                            })
                
                print(f"   ✅ Batch {i//batch_size + 1}: {successful} successful, {failed} failed")
                time.sleep(2)
            
            # Save comprehensive import documentation with failure tracking
            import_doc = {
                "import_timestamp": datetime.now().isoformat(),
                "total_papers_imported": total_successful,
                "total_papers_failed": total_failed + len(conversion_failures),
                "success_rate": f"{(total_successful / len(final_approved) * 100):.1f}%",
                "stats_by_query": stats_by_query,
                "zotero_collection": zotero_collection,
                "final_approved_papers": final_approved,
                "import_failures": {
                    "conversion_failures": conversion_failures,
                    "upload_failures": import_failures,
                    "total_failures": total_failed + len(conversion_failures),
                    "common_issues": {
                        "doi_itemtype_mismatch": "DOI field not valid for book/chapter types",
                        "duplicate_detection": "Paper already exists in Zotero",
                        "metadata_validation": "Missing or invalid required fields",
                        "api_rate_limiting": "Temporary API throttling"
                    },
                    "mitigation_strategies": {
                        "retry_failures": "Re-run import command to retry failed papers",
                        "manual_import": "Add failed papers manually using DOIs",
                        "metadata_cleanup": "Clean paper metadata before import",
                        "itemtype_detection": "Improve automatic item type detection"
                    }
                },
                "reproducibility_info": {
                    "failed_papers_included": True,
                    "manual_retry_possible": True,
                    "doi_list_available": True
                }
            }
            
            os.makedirs(self.directories["zotero"], exist_ok=True)
            doc_file = os.path.join(self.directories["zotero"], f"final_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            with open(doc_file, 'w', encoding='utf-8') as f:
                json.dump(import_doc, f, indent=2, ensure_ascii=False)
            
            # Create a separate file with just failed papers for easy manual import
            if conversion_failures or import_failures:
                failed_papers_file = os.path.join(self.directories["zotero"], f"failed_imports_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                failed_papers_doc = {
                    "failed_papers_for_manual_import": {
                        "conversion_failures": conversion_failures,
                        "upload_failures": import_failures,
                        "instructions": "Use DOIs to manually add these papers to Zotero",
                        "doi_list": [p["paper"].get("doi", "No DOI") for p in conversion_failures + import_failures if p["paper"].get("doi")]
                    }
                }
                with open(failed_papers_file, 'w', encoding='utf-8') as f:
                    json.dump(failed_papers_doc, f, indent=2, ensure_ascii=False)
                print(f"📄 Failed papers documented: {failed_papers_file}")
            
            print(f"\n✅ Import completed: {total_successful} papers imported to Zotero")
            print(f"❌ Import failures: {total_failed + len(conversion_failures)} papers failed")
            print(f"📈 Success rate: {(total_successful / len(final_approved) * 100):.1f}%")
            print(f"📄 Import documentation: {doc_file}")
            
            # Print summary
            print(f"\n📊 IMPORT SUMMARY BY QUERY:")
            for query_id, stats in stats_by_query.items():
                query_name = stats['query_name']
                print(f"   {query_name}: {stats['ai_included']} AI → {stats['manual_approved']} final ({stats['manual_rejected']} rejected)")
            
            # Show failed papers summary
            if conversion_failures or import_failures:
                print(f"\n❌ FAILED IMPORTS:")
                print(f"   🔧 Conversion failures: {len(conversion_failures)}")
                print(f"   📤 Upload failures: {len(import_failures)}")
                print(f"   💡 Common causes: DOI/itemType mismatch, duplicates, metadata issues")
                print(f"   🔄 Retry: python3 systematic_review.py --retry-failed-imports --run {os.path.basename(self.run_dir)}")
            
            return {
                "status": "completed",
                "papers_imported": total_successful,
                "papers_failed": total_failed + len(conversion_failures),
                "success_rate": f"{(total_successful / len(final_approved) * 100):.1f}%",
                "documentation": doc_file,
                "stats": stats_by_query,
                "failures": {
                    "conversion": conversion_failures,
                    "upload": import_failures
                }
            }
            
        except Exception as e:
            print(f"❌ Import failed: {e}")
            return {"status": "failed", "error": str(e)}
    
    def _clean_paper_for_zotero(self, paper: dict) -> dict:
        """Clean and validate paper metadata to minimize Zotero import failures"""
        cleaned_paper = paper.copy()
        
        # Fix common DOI/itemType mismatches
        paper_type = paper.get("type", "article").lower()
        doi = paper.get("doi", "")
        
        # Remove DOI for book chapters and books to avoid Zotero validation errors
        if paper_type in ["book-chapter", "book", "monograph"] and doi:
            # Keep DOI in a custom field but remove from main DOI field
            cleaned_paper["original_doi"] = doi
            cleaned_paper["doi"] = ""
            
        # Ensure valid item type mapping
        type_mapping = {
            "article": "article",
            "journal-article": "article", 
            "proceedings-article": "article",
            "book-chapter": "book",
            "book": "book",
            "monograph": "book",
            "conference-paper": "conferencePaper",
            "preprint": "preprint",
            "thesis": "thesis",
            "dissertation": "thesis"
        }
        
        if paper_type in type_mapping:
            cleaned_paper["type"] = type_mapping[paper_type]
        else:
            cleaned_paper["type"] = "article"  # Default fallback
        
        # Clean title
        if "title" in cleaned_paper and cleaned_paper["title"]:
            # Remove excessive whitespace and normalize
            cleaned_paper["title"] = " ".join(cleaned_paper["title"].split())
        
        # Validate authors list
        if "authors" in cleaned_paper and cleaned_paper["authors"]:
            valid_authors = []
            for author in cleaned_paper["authors"]:
                if isinstance(author, dict) and author.get("name"):
                    valid_authors.append(author)
            cleaned_paper["authors"] = valid_authors
        
        # Clean venue information
        if "venue" in cleaned_paper and cleaned_paper["venue"]:
            venue = cleaned_paper["venue"]
            if isinstance(venue, dict) and not venue.get("name"):
                cleaned_paper["venue"] = {}
        
        return cleaned_paper
    
    def _fallback_search_method(self) -> Dict:
        """Fallback search method when strategic search is not available"""
        print("⚠️ Strategic search not available, using screening workflow fallback")
        
        try:
            # Use the basic screening workflow as fallback
            papers_dir = self.directories["papers"]
            
            # Ensure directory exists
            os.makedirs(papers_dir, exist_ok=True)
            
            # Use screening workflow to fetch papers
            results = fetch_and_organize_papers(max_papers_per_query=50, output_dir=papers_dir)
            
            return {
                "status": "success",
                "total_papers": results.get("total_papers", 0),
                "organized_papers": results.get("total_papers", 0),
                "topic_organization": results.get("papers_by_topic", {}),
                "methodology": ["🔄 Fallback search method using screening workflow"],
                "version": "fallback_v1.0",
                "guardian_included": False,
                "papers_directory": papers_dir
            }
            
        except Exception as e:
            print(f"❌ Fallback search failed: {e}")
            return {"status": "error", "message": str(e)}
    
    def view_results_summary(self):
        """Display comprehensive results summary"""
        print("\n📊 SYSTEMATIC REVIEW RESULTS SUMMARY")
        print("=" * 80)
        print(f"📁 Run Directory: {self.run_dir}")
        print(f"📋 Run ID: {os.path.basename(self.run_dir)}")
        
        # Check what steps have been completed
        if os.path.exists(os.path.join(self.directories["papers"], "attack", "papers_for_screening.json")):
            print("✅ Step 1: Papers collected")
        else:
            print("❌ Step 1: Papers not collected")
            return
            
        if os.path.exists(os.path.join(self.directories["screening"], "attack", "ai_screening_results.json")):
            print("✅ Step 2: AI screening completed")
        else:
            print("❌ Step 2: AI screening not completed")
            return
            
        if os.path.exists(os.path.join(self.directories["reports"])):
            print("✅ Step 3: Reports generated")
        else:
            print("❌ Step 3: Reports not generated")
        
        # Show detailed statistics
        total_papers = 0
        ai_included = 0
        ai_excluded = 0
        manually_reviewed = 0
        manually_rejected = 0
        
        print(f"\n📋 DETAILED STATISTICS:")
        for topic_key, topic_info in TOPICS.items():
            # Papers collected
            papers_file = os.path.join(self.directories["papers"], topic_key, "papers_for_screening.json")
            if os.path.exists(papers_file):
                with open(papers_file, 'r') as f:
                    papers_data = json.load(f)
                    topic_papers = len(papers_data.get("papers", []))
                    total_papers += topic_papers
            else:
                topic_papers = 0
            
            # AI screening results
            ai_file = os.path.join(self.directories["screening"], topic_key, "ai_screening_results.json")
            if os.path.exists(ai_file):
                with open(ai_file, 'r') as f:
                    ai_data = json.load(f)
                    topic_ai_included = len([p for p in ai_data["screened_papers"] if p.get("ai_screening", {}).get("decision") == "INCLUDE"])
                    topic_ai_excluded = len([p for p in ai_data["screened_papers"] if p.get("ai_screening", {}).get("decision") == "EXCLUDE"])
                    topic_manual_reviewed = len([p for p in ai_data["screened_papers"] if p.get("manual_screening")])
                    topic_manual_rejected = len([p for p in ai_data["screened_papers"] if p.get("manual_screening", {}).get("decision") == "EXCLUDE"])
                    
                    ai_included += topic_ai_included
                    ai_excluded += topic_ai_excluded
                    manually_reviewed += topic_manual_reviewed
                    manually_rejected += topic_manual_rejected
            else:
                topic_ai_included = topic_ai_excluded = 0
            
            print(f"   📂 {topic_info['name']}: {topic_papers} collected → {topic_ai_included} AI included, {topic_ai_excluded} AI excluded")
        
        print(f"\n📊 OVERALL TOTALS:")
        print(f"   📄 Papers collected: {total_papers}")
        print(f"   🤖 AI included: {ai_included}")
        print(f"   ❌ AI excluded: {ai_excluded}")
        print(f"   👤 Manually reviewed: {manually_reviewed}")
        print(f"   🔄 Manual rejections: {manually_rejected}")
        print(f"   📈 Final approved: {ai_included - manually_rejected}")
        
        # Show next steps
        print(f"\n📋 NEXT STEPS:")
        if manually_reviewed == 0 and ai_included > 0:
            print(f"   👤 Manual screening: python3 systematic_review.py --manual-screen --run {os.path.basename(self.run_dir)}")
        elif ai_included > 0:
            print(f"   📚 Zotero import: python3 systematic_review.py --import-to-zotero --run {os.path.basename(self.run_dir)}")
        print(f"   📊 View this summary: python3 systematic_review.py --view-results --run {os.path.basename(self.run_dir)}")
        
        print("=" * 80)

    def run_query_by_query_workflow(self, start_from_query: int = 1, max_results_per_query: int = None) -> Dict:
        """Run iterative query-by-query workflow with deduplication only at report generation"""
        
        print("🔄 QUERY-BY-QUERY WORKFLOW WITH LATE-STAGE DEDUPLICATION")
        print("=" * 80)
        print(f"📋 Approach: Collect → Screen → Dedupe at Report Generation (with conflict resolution)")
        print(f"🔄 Resume capability: Start from query #{start_from_query}")
        print(f"📁 Run Directory: {self.run_dir}")
        print(f"⚡ Benefits: Preserve all screening decisions, handle conflicts intelligently")
        print("=" * 80)
        
        # Load queries configuration
        queries_config = self._load_queries_config()
        if not queries_config:
            return {"status": "failed", "error": "Could not load queries configuration"}
        
        strategic_queries = queries_config["strategic_queries"]
        workflow_config = queries_config["workflow_config"]
        search_strategy = queries_config["search_strategy"]
        
        # Filter queries to start from specified query
        remaining_queries = [q for q in strategic_queries if q["id"] >= start_from_query]
        
        if not remaining_queries:
            print(f"❌ No queries found starting from query #{start_from_query}")
            return {"status": "failed", "error": f"Invalid start query: {start_from_query}"}
        
        print(f"📊 Processing {len(remaining_queries)} queries starting from #{start_from_query}")
        print(f"📋 Queries to process: {[q['id'] for q in remaining_queries]}")
        
        # PHASE 1: Collect and screen each query independently (no deduplication)
        print(f"\n🔍 PHASE 1: COLLECT & SCREEN PER QUERY (PRESERVING DUPLICATES)")
        print("=" * 60)
        
        completed_queries = []
        failed_queries = []
        total_papers_collected = 0
        total_papers_screened = 0
        
        for query_config in remaining_queries:
            query_id = query_config["id"]
            description = query_config["description"]
            
            print(f"\n📊 Processing Query #{query_id}: {description}")
            
            try:
                # Fetch papers (no deduplication)
                fetch_result = self._fetch_single_query(query_config, search_strategy, max_results_per_query)
                if fetch_result["status"] != "success":
                    print(f"❌ Query #{query_id} failed: {fetch_result.get('error', 'Unknown error')}")
                    failed_queries.append({"query_id": query_id, "stage": "fetch", "error": fetch_result.get("error")})
                    continue
                
                papers_count = fetch_result["papers_found"]
                total_papers_collected += papers_count
                
                print(f"   📄 Papers collected: {papers_count}")
                
                # Immediately screen this query
                print(f"\n🤖 Screening Query #{query_id}")
                screening_result = self._screen_single_query(query_config, workflow_config)
                if screening_result["status"] != "success":
                    print(f"❌ Query #{query_id} failed at screening stage: {screening_result.get('error', 'Unknown error')}")
                    failed_queries.append({"query_id": query_id, "stage": "screening", "error": screening_result.get("error")})
                    continue
                
                total_papers_screened += papers_count
                
                # Success - log completion
                query_summary = {
                    "query_id": query_id,
                    "query_text": query_config["query"],
                    "description": description,
                    "papers_collected": papers_count,
                    "papers_included": screening_result["papers_included"],
                    "papers_excluded": screening_result["papers_excluded"],
                    "completion_time": datetime.now().isoformat()
                }
                completed_queries.append(query_summary)
                
                print(f"   🟢 AI included: {screening_result['papers_included']}")
                print(f"   🔴 AI excluded: {screening_result['papers_excluded']}")
                
                # Pause for user review (if configured)
                if workflow_config.get("pause_between_queries", True):
                    self._pause_for_query_review(query_config, screening_result)
                
                # Ask if user wants to continue to next query before the loop continues
                if query_config != remaining_queries[-1]:  # Not the last query
                    next_query = None
                    for q in remaining_queries:
                        if q["id"] > query_config["id"]:
                            next_query = q
                            break
                    
                    if next_query:
                        print(f"\n{'='*80}")
                        print(f"🔄 QUERY #{query_config['id']} COMPLETED")
                        print(f"📊 Next: Query #{next_query['id']} - {next_query['description']}")
                        print(f"{'='*80}")
                        
                        while True:
                            continue_choice = input(f"\n🎯 Continue to Query #{next_query['id']}? [Y]es/[N]o (exit workflow): ").strip().upper()
                            if continue_choice in ["Y", "YES", ""]:
                                print(f"▶️  Continuing to Query #{next_query['id']}...")
                                break
                            elif continue_choice in ["N", "NO"]:
                                print(f"🛑 Workflow stopped by user after Query #{query_config['id']}")
                                print(f"📋 To resume later: python3 systematic_review.py --start-from {next_query['id']} --run {os.path.basename(self.run_dir)}")
                                
                                # Generate partial report with completed queries only
                                print(f"\n📊 Generating partial report for completed queries...")
                                try:
                                    report_result = self._generate_combined_report()
                                    if report_result["status"] == "success":
                                        print(f"✅ Partial report generated with {len(completed_queries)} completed queries")
                                except Exception as e:
                                    print(f"⚠️ Could not generate partial report: {e}")
                                
                                # Save workflow state
                                workflow_state = {
                                    "approach": "query_by_query_stopped_by_user",
                                    "completed_queries": completed_queries,
                                    "stopped_at_query": query_config["id"],
                                    "next_query": next_query["id"],
                                    "total_processed": len(completed_queries),
                                    "workflow_status": "stopped_by_user",
                                    "completion_time": datetime.now().isoformat()
                                }
                                self._save_workflow_state(workflow_state)
                                
                                return {
                                    "status": "stopped_by_user",
                                    "completed_queries": len(completed_queries),
                                    "stopped_after_query": query_config["id"],
                                    "next_query": next_query["id"],
                                    "workflow_state": workflow_state
                                }
                            else:
                                print("❌ Please enter Y (Yes) or N (No)")
                
            except Exception as e:
                print(f"❌ Query #{query_id} failed with exception: {e}")
                failed_queries.append({"query_id": query_id, "stage": "exception", "error": str(e)})
                continue
        
        # Save workflow state
        workflow_state = {
            "approach": "query_by_query_with_late_stage_deduplication",
            "deduplication_approach": "at_report_generation_with_conflict_resolution",
            "completed_queries": completed_queries,
            "failed_queries": failed_queries,
            "total_processed": len(completed_queries) + len(failed_queries),
            "total_remaining": len(strategic_queries) - start_from_query + 1,
            "workflow_status": "completed" if not failed_queries else "in_progress",
            "last_processed_query": completed_queries[-1]["query_id"] if completed_queries else None,
            "completion_time": datetime.now().isoformat()
        }
        
        self._save_workflow_state(workflow_state)
        
        # Print summary
        print(f"\n{'='*80}")
        print("📊 COLLECTION & SCREENING SUMMARY (DUPLICATES PRESERVED)")
        print("=" * 80)
        print(f"📄 Total papers collected: {total_papers_collected}")
        print(f"🤖 Total papers screened: {total_papers_screened}")
        print(f"✅ Successfully completed: {len(completed_queries)} queries")
        print(f"❌ Failed queries: {len(failed_queries)}")
        print(f"🔄 Deduplication: Will be performed at report generation with conflict resolution")
        
        # Calculate efficiency metrics
        per_query_efficiency_gain = f"{(total_papers_screened / total_papers_collected * 100):.1f}% duplicates removed per-query" if total_papers_collected > 0 else "0%"
        
        # Save workflow state with per-query deduplication metadata
        deduplication_metadata = {
            "approach": "per_query_deduplication",
            "original_count": total_papers_collected,
            "unique_count_after_per_query_dedup": total_papers_screened,
            "per_query_duplicates_removed": total_papers_screened - total_papers_collected,
            "per_query_efficiency_gain": per_query_efficiency_gain,
            "deduplication_method": "doi_and_openalex_id_per_query",
            "cross_query_deduplication": "applied_at_report_level"
        }
        
        workflow_state = {
            "approach": "query_by_query_with_late_stage_deduplication",
            "deduplication_approach": "at_report_generation_with_conflict_resolution",
            "completed_queries": completed_queries,
            "failed_queries": failed_queries,
            "total_processed": len(completed_queries) + len(failed_queries),
            "total_remaining": len(strategic_queries) - start_from_query + 1,
            "workflow_status": "completed" if not failed_queries else "in_progress",
            "last_processed_query": completed_queries[-1]["query_id"] if completed_queries else None,
            "completion_time": datetime.now().isoformat()
        }
        
        self._save_workflow_state(workflow_state)
        
        # Print final summary with per-query deduplication information
        print(f"\n{'='*80}")
        print("📊 LATE-STAGE DEDUPLICATION WORKFLOW SUMMARY")
        print("=" * 80)
        print(f"📄 Total papers collected: {total_papers_collected}")
        print(f"🔄 Per-query duplicates removed: {total_papers_screened - total_papers_collected} ({per_query_efficiency_gain})")
        print(f"✅ Papers after per-query dedup: {total_papers_screened}")
        print(f"✅ Successfully completed: {len(completed_queries)} queries")
        print(f"❌ Failed queries: {len(failed_queries)}")
        print(f"🔄 Deduplication: Will be performed at report generation with conflict resolution")
        
        for completed in completed_queries:
            print(f"   ✅ Query #{completed['query_id']}: {completed['papers_collected']} → {completed['papers_included']} included")
        
        if failed_queries:
            print(f"\n❌ FAILED QUERIES:")
            for failed in failed_queries:
                print(f"   ❌ Query #{failed['query_id']}: {failed['stage']} stage - {failed['error']}")
        
        # Check if all queries are complete
        all_queries_complete = len(completed_queries) == len(strategic_queries) and not failed_queries
        
        if all_queries_complete:
            print(f"\n🎉 ALL QUERIES COMPLETED - GENERATING FINAL REPORT WITH CROSS-QUERY DEDUPLICATION")
            report_result = self._generate_combined_report()
            workflow_state["final_report"] = report_result
            
            # Show per-query deduplication benefits
            total_ai_included = sum(q['papers_included'] for q in completed_queries)
            
            print(f"\n{'='*80}")
            print("🤖 SCREENING COMPLETE - PER-QUERY DEDUPLICATION BENEFITS")
            print("=" * 80)
            print(f"📊 Original papers found: {total_papers_collected}")
            print(f"🔄 Per-query deduplication: {total_papers_screened - total_papers_collected} duplicates removed")
            print(f"📈 Per-query efficiency gain: {per_query_efficiency_gain}")
            print(f"✅ Papers screened: {total_papers_screened}")
            print(f"🟢 Total AI-included papers: {total_ai_included}")
            print(f"📋 Cross-query deduplication: Applied at report level for final results")
            print(f"⚡ Workflow benefits: Independent queries, easy to add/remove/modify")
            
            # Check if manual screening was already done OR declined on individual queries
            screening_files = self._find_query_screening_files()
            manual_screening_done = False
            manual_screening_declined = False
            total_manually_reviewed = 0
            total_declined = 0
            
            for query_id, screening_file in screening_files.items():
                with open(screening_file, 'r', encoding='utf-8') as f:
                    screening_data = json.load(f)
                
                screening_results = screening_data.get("screening_results", [])
                manually_reviewed = [r for r in screening_results if r.get("manual_screening")]
                total_manually_reviewed += len(manually_reviewed)
                
                # Check if manual screening was declined for this query
                manual_status = screening_data.get("manual_screening_status", {})
                if manual_status.get("declined", False):
                    total_declined += 1
            
            manual_screening_done = total_manually_reviewed > 0
            manual_screening_declined = total_declined == len(screening_files)  # All queries declined
            
            if manual_screening_done:
                print(f"✅ Manual screening already completed on individual queries")
                print(f"👤 {total_manually_reviewed} papers manually reviewed across queries")
                print(f"🚀 Ready for final steps")
                
                while True:
                    choice = input("\n📚 Import to Zotero now? [Y]es/[N]o/[R]eview manual screening results: ").strip().upper()
                    
                    if choice == "Y" or choice == "":
                        print("\n🚀 STARTING ZOTERO IMPORT...")
                        import_results = self.import_to_zotero_after_manual_review()
                        print(f"\n🎉 COMPLETE WORKFLOW FINISHED!")
                        print(f"📊 Papers imported to Zotero: {import_results.get('papers_imported', 0)}")
                        workflow_state["zotero_import"] = import_results
                        break
                    elif choice == "N":
                        print(f"📋 Zotero import skipped. Run later with:")
                        print(f"   python3 systematic_review.py --import-to-zotero --run {os.path.basename(self.run_dir)}")
                        break
                    elif choice == "R":
                        print("\n📊 MANUAL SCREENING RESULTS SUMMARY:")
                        self._show_query_screening_statistics(screening_files)
                        continue
                    else:
                        print("❌ Please enter Y, N, or R")
            elif manual_screening_declined:
                print(f"📋 Manual screening declined for all queries - proceeding to final steps")
                print(f"🤖 Using AI decisions for all {total_ai_included} included papers")
                print(f"🚀 Ready for Zotero import")
                
                # Auto-accept all AI decisions since user declined manual screening
                print("✅ Auto-accepting all AI decisions...")
                for query_id, screening_file in screening_files.items():
                    with open(screening_file, 'r', encoding='utf-8') as f:
                        screening_data = json.load(f)
                    
                    screening_results = screening_data.get("screening_results", [])
                    ai_included = [r for r in screening_results if r.get("decision") == "INCLUDE"]
                    
                    # Mark all AI-included papers as accepted
                    for result in ai_included:
                        if not result.get("manual_screening"):  # Don't override existing manual decisions
                            result["manual_screening"] = {
                                "decision": "INCLUDE", 
                                "timestamp": datetime.now().isoformat(),
                                "method": "auto_accept_declined_manual_screening"
                            }
                    
                    with open(screening_file, 'w', encoding='utf-8') as f:
                        json.dump(screening_data, f, indent=2, ensure_ascii=False)
                
                while True:
                    choice = input("\n📚 Import to Zotero now? [Y]es/[N]o: ").strip().upper()
                    
                    if choice == "Y" or choice == "":
                        print("\n🚀 STARTING ZOTERO IMPORT...")
                        import_results = self.import_to_zotero_after_manual_review()
                        print(f"\n🎉 COMPLETE WORKFLOW FINISHED!")
                        print(f"📊 Papers imported to Zotero: {import_results.get('papers_imported', 0)}")
                        workflow_state["zotero_import"] = import_results
                        break
                    elif choice == "N":
                        print(f"📋 Zotero import skipped. Run later with:")
                        print(f"   python3 systematic_review.py --import-to-zotero --run {os.path.basename(self.run_dir)}")
                        break
                    else:
                        print("❌ Please enter Y or N")
            else:
                print(f"📋 Ready for manual screening to validate AI decisions (enhanced efficiency from deduplication)")
                
                while True:
                    choice = input("\n👤 Start manual screening now? [Y]es/[N]o/[S]kip to Zotero import: ").strip().upper()
                    
                    if choice == "Y" or choice == "":
                        print("\n🚀 STARTING MANUAL SCREENING...")
                        self.manual_screening_interface()
                        
                        # After manual screening, offer Zotero import
                        print(f"\n{'='*80}")
                        print("👤 MANUAL SCREENING COMPLETE")
                        print("=" * 80)
                        
                        while True:
                            import_choice = input("\n📚 Import to Zotero now? [Y]es/[N]o: ").strip().upper()
                            if import_choice == "Y" or import_choice == "":
                                print("\n🚀 STARTING ZOTERO IMPORT...")
                                import_results = self.import_to_zotero_after_manual_review()
                                print(f"\n🎉 COMPLETE WORKFLOW FINISHED!")
                                print(f"📊 Papers imported to Zotero: {import_results.get('papers_imported', 0)}")
                                workflow_state["zotero_import"] = import_results
                                break
                            elif import_choice == "N":
                                print(f"📋 Zotero import skipped. Run later with:")
                                print(f"   python3 systematic_review.py --import-to-zotero --run {os.path.basename(self.run_dir)}")
                                break
                            else:
                                print("❌ Please enter Y or N")
                        break
                        
                    elif choice == "N":
                        print(f"📋 Manual screening skipped. Run later with:")
                        print(f"   python3 systematic_review.py --manual-screen --run {os.path.basename(self.run_dir)}")
                        break
                        
                    elif choice == "S":
                        print("\n📚 SKIPPING TO ZOTERO IMPORT (accepting all AI decisions)")
                        print("⚠️  This will import all AI-included papers without manual review")
                        
                        confirm = input("Are you sure? [y/N]: ").strip().upper()
                        if confirm == "Y":
                            # Accept all AI decisions automatically
                            print("✅ Auto-accepting all AI decisions...")
                            screening_files = self._find_query_screening_files()
                            
                            for query_id, screening_file in screening_files.items():
                                with open(screening_file, 'r', encoding='utf-8') as f:
                                    screening_data = json.load(f)
                                
                                screening_results = screening_data.get("screening_results", [])
                                ai_included = [r for r in screening_results if r.get("decision") == "INCLUDE"]
                                
                                # Mark all as accepted
                                for result in ai_included:
                                    result["manual_screening"] = {
                                        "decision": "INCLUDE", 
                                        "timestamp": datetime.now().isoformat(),
                                        "method": "auto_accept_for_zotero"
                                    }
                                
                                with open(screening_file, 'w', encoding='utf-8') as f:
                                    json.dump(screening_data, f, indent=2, ensure_ascii=False)
                            
                            # Proceed to Zotero import
                            print("\n🚀 STARTING ZOTERO IMPORT...")
                            import_results = self.import_to_zotero_after_manual_review()
                            print(f"\n🎉 COMPLETE WORKFLOW FINISHED!")
                            print(f"📊 Papers imported to Zotero: {import_results.get('papers_imported', 0)}")
                            workflow_state["zotero_import"] = import_results
                            break
                        else:
                            continue
                            
                    else:
                        print("❌ Please enter Y, N, or S")
            
        else:
            next_query = max(completed_queries, key=lambda x: x["query_id"])["query_id"] + 1 if completed_queries else start_from_query
            print(f"\n📋 TO RESUME: python3 systematic_review.py --start-from {next_query} --run {os.path.basename(self.run_dir)}")
        
        print("=" * 80)
        
        return {
            "status": "completed" if not failed_queries else "partial",
            "approach": "query_by_query_with_late_stage_deduplication",
            "deduplication_metadata": deduplication_metadata,
            "completed_queries": len(completed_queries),
            "failed_queries": len(failed_queries),
            "workflow_state": workflow_state,
            "all_complete": all_queries_complete
        }
    
    def _load_queries_config(self) -> Dict:
        """Load queries configuration from external file"""
        config_file = "queries_config.json"
        
        if not os.path.exists(config_file):
            print(f"❌ Queries configuration not found: {config_file}")
            print("📋 Create this file with your strategic queries")
            return None
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            print(f"✅ Loaded queries configuration: {config['search_strategy']['version']}")
            print(f"📊 Found {len(config['strategic_queries'])} strategic queries")
            return config
            
        except Exception as e:
            print(f"❌ Error loading queries configuration: {e}")
            return None
    
    
    def _fetch_single_query(self, query_config: Dict, search_strategy: Dict, max_results: int = None) -> Dict:
        """Fetch papers for a single query without deduplication"""
        
        query_id = query_config["id"]
        query_text = query_config["query"]
        
        print(f"📊 Fetching papers for query #{query_id}")
        
        try:
            # Import the single query function
            papers, search_metadata = openalex_query_with_metadata(
                query_text,
                start_date=search_strategy["timeframe"]["start_date"],
                end_date=search_strategy["timeframe"]["end_date"],
                min_citations=search_strategy["quality_criteria"]["min_citations"],
                max_results=max_results,
                peer_reviewed_only=search_strategy["quality_criteria"]["peer_reviewed_only"]
            )
            
            papers_count = len(papers)
            
            # Create directories for this query only when needed
            queries_base_dir = os.path.join(self.run_dir, "01_individual_queries")
            query_papers_dir = os.path.join(queries_base_dir, "papers", f"query_{query_id:02d}")
            os.makedirs(query_papers_dir, exist_ok=True)
            
            query_data = {
                "query_config": query_config,
                "search_metadata": search_metadata,
                "papers": papers,  # Store all papers including duplicates
                "total_papers": papers_count,
                "deduplication_applied": False,
                "deduplication_scope": "none_preserving_all_for_late_stage",
                "fetch_timestamp": datetime.now().isoformat()
            }
            
            papers_file = os.path.join(query_papers_dir, "papers_for_screening.json")
            with open(papers_file, 'w', encoding='utf-8') as f:
                json.dump(query_data, f, indent=2, ensure_ascii=False)
            
            print(f"   ✅ Found {papers_count} papers (duplicates preserved)")
            print(f"   📄 Saved to: {papers_file}")
            
            return {
                "status": "success",
                "papers_found": papers_count,
                "papers_file": papers_file,
                "search_metadata": search_metadata
            }
            
        except Exception as e:
            print(f"❌ Error fetching query #{query_id}: {e}")
            return {"status": "failed", "error": str(e)}
    
    def _screen_single_query(self, query_config: Dict, workflow_config: Dict) -> Dict:
        """Screen papers for a single query using AI"""
        
        query_id = query_config["id"]
        
        print(f"🤖 Step 2: AI screening for query #{query_id}")
        
        try:
            # Load papers for this query
            queries_base_dir = os.path.join(self.run_dir, "01_individual_queries")
            query_papers_dir = os.path.join(queries_base_dir, "papers", f"query_{query_id:02d}")
            papers_file = os.path.join(query_papers_dir, "papers_for_screening.json")
            
            if not os.path.exists(papers_file):
                return {"status": "failed", "error": f"Papers file not found: {papers_file}"}
            
            with open(papers_file, 'r', encoding='utf-8') as f:
                query_data = json.load(f)
            
            papers = query_data["papers"]
            
            if not papers:
                print("   ⚠️ No papers to screen")
                return {"status": "success", "papers_included": 0, "papers_excluded": 0}
            
            # Import AI screening function
            from ai_screening import screen_papers_with_ai
            
            # Run AI screening
            screening_results = screen_papers_with_ai(
                papers,
                confidence_threshold=workflow_config.get("confidence_threshold", 0.7),
                model=workflow_config.get("ai_screening_model", "gpt-4o")
            )
            
            # Count results
            included_papers = len([r for r in screening_results if r.get("decision") == "INCLUDE"])
            excluded_papers = len([r for r in screening_results if r.get("decision") == "EXCLUDE"])
            
            # Create screening directory for this query only when needed
            query_screening_dir = os.path.join(queries_base_dir, "screening", f"query_{query_id:02d}")
            os.makedirs(query_screening_dir, exist_ok=True)
            
            screening_data = {
                "query_config": query_config,
                "screening_metadata": {
                    "confidence_threshold": workflow_config.get("confidence_threshold", 0.7),
                    "model": workflow_config.get("ai_screening_model", "gpt-4o"),
                    "screening_timestamp": datetime.now().isoformat()
                },
                "screening_results": screening_results,
                "summary": {
                    "total_papers": len(papers),
                    "papers_included": included_papers,
                    "papers_excluded": excluded_papers,
                    "inclusion_rate": included_papers / len(papers) if papers else 0
                }
            }
            
            screening_file = os.path.join(query_screening_dir, "ai_screening_results.json")
            with open(screening_file, 'w', encoding='utf-8') as f:
                json.dump(screening_data, f, indent=2, ensure_ascii=False)
            
            print(f"   🟢 Included: {included_papers} papers")
            print(f"   🔴 Excluded: {excluded_papers} papers")
            print(f"   📄 Results saved to: {screening_file}")
            
            return {
                "status": "success",
                "papers_included": included_papers,
                "papers_excluded": excluded_papers,
                "screening_file": screening_file,
                "inclusion_rate": included_papers / len(papers) if papers else 0
            }
            
        except Exception as e:
            print(f"   ❌ Error screening papers: {e}")
            return {"status": "failed", "error": str(e)}
    
    def _pause_for_query_review(self, query_config: Dict, screening_result: Dict):
        """Pause workflow for user to review query results"""
        
        query_id = query_config["id"]
        
        print(f"\n📋 QUERY #{query_id} REVIEW")
        print("─" * 60)
        print(f"Query: {query_config['query']}")
        print(f"Description: {query_config['description']}")
        print(f"Papers included: {screening_result['papers_included']}")
        print(f"Papers excluded: {screening_result['papers_excluded']}")
        print(f"Inclusion rate: {screening_result.get('inclusion_rate', 0):.2%}")
        
        while True:
            choice = input("\n🎯 What would you like to do? [C]ontinue/[M]anual screen this query/[R]eview details/[Q]uit: ").strip().upper()
            
            if choice == "C" or choice == "":
                # Mark that manual screening was declined for this query
                self._mark_manual_screening_declined(query_config, screening_result)
                break
            elif choice == "M":
                print(f"\n👤 MANUAL SCREENING FOR QUERY #{query_id}")
                print("=" * 60)
                self._manual_screen_single_query(query_config, screening_result)
                print(f"\n✅ Manual screening for Query #{query_id} completed")
                break
            elif choice == "R":
                self._show_query_details(query_config, screening_result)
            elif choice == "Q":
                print("⏸️ Workflow paused. Resume with --start-from flag")
                sys.exit(0)
            else:
                print("❌ Please enter C, M, R, or Q")

    def _mark_manual_screening_declined(self, query_config: Dict, screening_result: Dict):
        """Mark that manual screening was declined for this query"""
        
        try:
            screening_file = screening_result["screening_file"]
            with open(screening_file, 'r', encoding='utf-8') as f:
                screening_data = json.load(f)
            
            # Add metadata indicating manual screening was declined
            screening_data["manual_screening_status"] = {
                "declined": True,
                "timestamp": datetime.now().isoformat(),
                "method": "continue_without_manual_review"
            }
            
            with open(screening_file, 'w', encoding='utf-8') as f:
                json.dump(screening_data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"⚠️ Warning: Could not mark manual screening status: {e}")
    
    def _manual_screen_single_query(self, query_config: Dict, screening_result: Dict):
        """Manual screening for a single query"""
        
        query_id = query_config["id"]
        screening_file = screening_result["screening_file"]
        
        try:
            # Load screening results
            with open(screening_file, 'r', encoding='utf-8') as f:
                screening_data = json.load(f)
            
            query_config = screening_data.get("query_config", {})
            query_name = query_config.get("description", f"Query {query_id}")
            screening_results = screening_data.get("screening_results", [])
            
            ai_included = [r for r in screening_results if r.get("decision") == "INCLUDE"]
            ai_excluded = [r for r in screening_results if r.get("decision") == "EXCLUDE"]
            
            print(f"📊 Query #{query_id} screening results:")
            print(f"   🟢 AI included: {len(ai_included)} papers")
            print(f"   🔴 AI excluded: {len(ai_excluded)} papers")
            
            if not ai_included and not ai_excluded:
                print(f"⚠️ No papers found for Query #{query_id}")
                return
            
            # Ask what to review (same options as main manual screening)
            print(f"\n📋 What would you like to review for Query #{query_id}?")
            print("1. 🟢 Only AI-INCLUDED papers")
            print("2. 🔴 Only AI-EXCLUDED papers")
            print("3. 🔄 BOTH included and excluded papers")
            print("4. ✅ ACCEPT all AI decisions for this query")
            
            while True:
                review_choice = input("\n🎯 Select option (1-4): ").strip()
                if review_choice in ["1", "2", "3", "4"]:
                    break
                print("❌ Please enter 1, 2, 3, or 4")
            
            if review_choice == "4":
                # Accept all AI decisions
                for result in ai_included:
                    result["manual_screening"] = {
                        "decision": "INCLUDE",
                        "timestamp": datetime.now().isoformat(),
                        "method": "bulk_accept_query"
                    }
                
                with open(screening_file, 'w', encoding='utf-8') as f:
                    json.dump(screening_data, f, indent=2, ensure_ascii=False)
                
                print(f"✅ Accepted all {len(ai_included)} AI-included papers for Query #{query_id}")
                return
            
            # Determine what to review
            papers_to_review = []
            if review_choice in ["1", "3"] and ai_included:
                papers_to_review.extend(ai_included)
            if review_choice in ["2", "3"] and ai_excluded:
                papers_to_review.extend(ai_excluded)
            
            if not papers_to_review:
                if review_choice == "1":
                    print("⚠️ No AI-included papers to review")
                elif review_choice == "2":
                    print("⚠️ No AI-excluded papers to review")
                return
            
            print(f"\n🔍 Reviewing {len(papers_to_review)} papers for Query #{query_id}")
            
            # Manual review process
            changes_made = 0
            for i, result in enumerate(papers_to_review, 1):
                ai_decision = result.get("decision", "UNKNOWN")
                confidence = result.get("confidence", 0.0)
                reason = result.get("reason", "No reason")
                
                # Status emoji
                status_emoji = "🟢" if ai_decision == "INCLUDE" else "🔴"
                
                print(f"\n[{i}/{len(papers_to_review)}] Paper:")
                print(f"📄 Title: {result.get('title', 'No title')}")
                authors = result.get('authors', [])
                if authors and isinstance(authors, list):
                    author_names = [a.get('name', str(a)) if isinstance(a, dict) else str(a) for a in authors[:3]]
                    print(f"👥 Authors: {', '.join(author_names)}")
                print(f"📍 Venue: {result.get('venue', {}).get('name', 'Unknown') if isinstance(result.get('venue'), dict) else result.get('venue', 'Unknown')} ({result.get('publication_year', 'Unknown')})")
                print(f"{status_emoji} AI Decision: {ai_decision} (confidence: {confidence:.2f})")
                print(f"💭 AI Reason: {reason}")
                
                if result.get("abstract"):
                    abstract = result["abstract"][:300] + "..." if len(result["abstract"]) > 300 else result["abstract"]
                    print(f"📄 Abstract: {abstract}")
                
                while True:
                    if ai_decision == "INCLUDE":
                        choice_input = input(f"\n👤 Your decision [A]ccept/[R]eject/[S]kip: ").strip().upper()
                    else:  # AI rejected it
                        choice_input = input(f"\n👤 Your decision [I]nclude/[R]eject (confirm)/[S]kip: ").strip().upper()
                    
                    if choice_input == "A" or choice_input == "I":
                        # Save original AI decision for audit trail
                        if "original_ai_decision" not in result:
                            result["original_ai_decision"] = result["decision"]
                            result["original_ai_reason"] = result["reason"]
                            result["original_ai_confidence"] = result["confidence"]
                        
                        # Overwrite decision directly
                        result["decision"] = "INCLUDE"
                        result["confidence"] = 1.0
                        result["reason"] = f"Manual override: Included by human reviewer (original AI: {result.get('original_ai_decision', 'UNKNOWN')})"
                        result["manual_timestamp"] = datetime.now().isoformat()
                        
                        # Set manual_screening field for detection logic
                        result["manual_screening"] = {
                            "decision": "INCLUDE",
                            "timestamp": datetime.now().isoformat(),
                            "method": "individual_query_review"
                        }
                        
                        if ai_decision == "EXCLUDE":
                            print("🔄 Overriding AI rejection - paper INCLUDED")
                            changes_made += 1
                        else:
                            print("✅ Confirmed for inclusion")
                        break
                    elif choice_input == "R":
                        # Save original AI decision for audit trail
                        if "original_ai_decision" not in result:
                            result["original_ai_decision"] = result["decision"]
                            result["original_ai_reason"] = result["reason"]
                            result["original_ai_confidence"] = result["confidence"]
                        
                        # Overwrite decision directly
                        result["decision"] = "EXCLUDE"
                        result["confidence"] = 1.0
                        result["reason"] = f"Manual override: Excluded by human reviewer (original AI: {result.get('original_ai_decision', 'UNKNOWN')})"
                        result["manual_timestamp"] = datetime.now().isoformat()
                        
                        # Set manual_screening field for detection logic
                        result["manual_screening"] = {
                            "decision": "EXCLUDE",
                            "timestamp": datetime.now().isoformat(),
                            "method": "individual_query_review"
                        }
                        
                        if ai_decision == "INCLUDE":
                            print("🔄 Overriding AI inclusion - paper REJECTED")
                            changes_made += 1
                        else:
                            print("❌ Confirmed rejection")
                        break
                    elif choice_input == "S":
                        print("⏭️ Skipped (keeping AI decision)")
                        # Even for skipped papers, mark that they were manually reviewed
                        result["manual_screening"] = {
                            "decision": result.get("decision", "UNKNOWN"),
                            "timestamp": datetime.now().isoformat(),
                            "method": "individual_query_review_skipped"
                        }
                        break
                    else:
                        if ai_decision == "INCLUDE":
                            print("❌ Invalid choice. Please enter A (Accept), R (Reject), or S (Skip)")
                        else:
                            print("❌ Invalid choice. Please enter I (Include), R (Reject), or S (Skip)")
            
            # Save updated results
            with open(screening_file, 'w', encoding='utf-8') as f:
                json.dump(screening_data, f, indent=2, ensure_ascii=False)
            
            # Update summary with final counts after manual screening
            self._update_query_summary_after_manual_screening(screening_file, screening_data)
            
            print(f"\n📊 Query #{query_id} manual screening completed: {changes_made} AI decisions changed")
            
        except Exception as e:
            print(f"❌ Error during manual screening: {e}")
    
    def _update_query_summary_after_manual_screening(self, screening_file: str, screening_data: Dict):
        """Update the query summary to reflect final decisions after manual screening"""
        
        try:
            screening_results = screening_data.get("screening_results", [])
            
            # Recalculate based on final decisions
            final_included = len([r for r in screening_results if r.get("decision") == "INCLUDE"])
            final_excluded = len([r for r in screening_results if r.get("decision") == "EXCLUDE"])
            total_papers = len(screening_results)
            
            # Update the summary section
            screening_data["summary"] = {
                "total_papers": total_papers,
                "papers_included": final_included,
                "papers_excluded": final_excluded,
                "inclusion_rate": final_included / total_papers if total_papers > 0 else 0,
                "manual_screening_completed": True,
                "last_updated": datetime.now().isoformat()
            }
            
            # Save the updated data with corrected summary
            with open(screening_file, 'w', encoding='utf-8') as f:
                json.dump(screening_data, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Summary updated: {final_included} included, {final_excluded} excluded")
            
        except Exception as e:
            print(f"⚠️ Warning: Could not update summary: {e}")
    
    def _show_query_details(self, query_config: Dict, screening_result: Dict):
        """Show detailed results for a specific query"""
        
        query_id = query_config["id"]
        
        try:
            # Load screening results
            screening_file = screening_result["screening_file"]
            with open(screening_file, 'r', encoding='utf-8') as f:
                screening_data = json.load(f)
            
            screening_results = screening_data["screening_results"]
            included_results = [r for r in screening_results if r.get("decision") == "INCLUDE"]
            
            print(f"\n📊 DETAILED RESULTS FOR QUERY #{query_id}")
            print("=" * 60)
            
            # Show top included papers
            print(f"🟢 TOP INCLUDED PAPERS:")
            for i, result in enumerate(included_results[:5], 1):
                title = result.get("title", "No title")[:60]
                confidence = result.get("confidence", 0.0)
                reason = result.get("reason", "No reason")[:100]
                print(f"{i}. [{confidence:.2f}] {title}")
                print(f"   Reason: {reason}")
            
            if len(included_results) > 5:
                print(f"   ... and {len(included_results) - 5} more included papers")
            
        except Exception as e:
            print(f"❌ Error showing details: {e}")
    
    def _save_workflow_state(self, workflow_state: Dict):
        """Save current workflow state for resume capability"""
        
        state_file = os.path.join(self.run_dir, "04_workflow_logs", "query_workflow_state.json")
        
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(workflow_state, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Workflow state saved: {state_file}")
    
    def _generate_combined_report(self) -> Dict:
        """Generate final combined report from all completed queries"""
        
        print("📊 Generating combined report from all queries...")
        
        try:
            # Use the updated prisma_generator with deduplication
            from prisma_generator import collect_screening_data, save_prisma_documentation
            
            # Collect and deduplicate data using the new function
            screening_data = collect_screening_data(run_dir=self.run_dir)
            
            if not screening_data:
                print("❌ No screening data found to generate report")
                return {"status": "failed", "error": "No screening data available"}
            
            # Generate combined PRISMA documentation
            report_files = save_prisma_documentation(
                screening_data,
                output_dir=self.directories["reports"]
            )
            
            print(f"✅ Combined report generated: {len(report_files)} files")
            
            return {
                "status": "success",
                "report_files": report_files,
                "total_queries": screening_data["totals"]["total_queries"],
                "total_papers": screening_data["totals"]["total_identified"],
                "duplicates_removed": screening_data["totals"]["duplicates_removed"],
                "total_unique": screening_data["totals"]["total_after_deduplication"],
                "total_included": screening_data["totals"]["total_approved"],
                "deduplication_rate": screening_data["deduplication_info"]["deduplication_rate"]
            }
            
        except Exception as e:
            print(f"❌ Error generating combined report: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "failed", "error": str(e)}

# ── Interactive Mode ────────────────────────────────────────

def interactive_mode():
    """Interactive workflow selection"""
    print("🎯 INTERACTIVE SYSTEMATIC REVIEW WORKFLOW")
    print("=" * 50)
    
    workflow = SystematicReviewWorkflow()
    workflow.print_workflow_header()
    
    while True:
        print("\n📋 Available Actions:")
        print("1. 🚀 Run full automated workflow")
        print("2. 📊 Step 1: Fetch papers")
        print("3. 🤖 Step 2: AI screening")
        print("4. 📋 Step 3: Generate reports")
        print("5. 📈 View workflow status")
        print("6. 🏁 Exit")
        
        choice = input("\n🎯 Select option (1-6): ").strip()
        
        if choice == "1":
            max_results = int(input("📊 Papers per query (default 50): ") or 50)
            confidence = float(input("🎯 Confidence threshold (default 0.7): ") or 0.7)
            results = workflow.run_full_workflow(max_results, confidence)
            workflow.print_workflow_summary(results)
            break
        elif choice == "2":
            max_results = int(input("📊 Papers per query (default 50): ") or 50)
            workflow.step_1_fetch_papers(max_results)
        elif choice == "3":
            confidence = float(input("🎯 Confidence threshold (default 0.7): ") or 0.7)
            workflow.step_2_ai_screening(confidence)
        elif choice == "4":
            workflow.step_3_generate_reports()
        elif choice == "5":
            print(f"\n📊 Steps completed: {len(workflow.steps_completed)}")
            for step in workflow.steps_completed:
                print(f"  ✅ {step['step']} at {step['timestamp']}")
        elif choice == "6":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please select 1-6.")

# ── Command Line Interface ──────────────────────────────────

def load_existing_workflow(run_id: str) -> 'SystematicReviewWorkflow':
    """Load an existing workflow run for manual screening or Zotero import"""
    
    base_dir = "systematic_review_results"
    run_dir = os.path.join(base_dir, run_id)
    
    if not os.path.exists(run_dir):
        print(f"❌ Review run not found: {run_id}")
        print(f"📁 Looking in: {run_dir}")
        
        # Show available runs
        if os.path.exists(base_dir):
            available_runs = [d for d in os.listdir(base_dir) if d.startswith("review_run_")]
            if available_runs:
                print(f"\n📋 Available review runs:")
                for run in sorted(available_runs):
                    print(f"   📂 {run}")
            else:
                print(f"⚠️  No review runs found in {base_dir}")
        sys.exit(1)
    
    # Create workflow object with existing directories
    workflow = SystematicReviewWorkflow.__new__(SystematicReviewWorkflow)
    workflow.workflow_start = datetime.now()
    workflow.steps_completed = []
    workflow.results = {}
    workflow.run_dir = run_dir
    
    # Set up directory structure
    workflow.directories = {
        "run_root": run_dir,
        "papers": os.path.join(run_dir, "01_papers_collected"),
        "screening": os.path.join(run_dir, "02_screening_results"), 
        "reports": os.path.join(run_dir, "02_reports_generated"),
        "zotero": os.path.join(run_dir, "03_zotero_imports"),
        "logs": os.path.join(run_dir, "04_workflow_logs"),
        "documentation": os.path.join("systematic_review_results", "documentation"),
        "templates": os.path.join("systematic_review_results", "documentation", "templates"),
        "archive": os.path.join("systematic_review_results", "archived_runs")
    }
    
    workflow.metadata = {
        "start_time": workflow.workflow_start.isoformat(),
        "workflow_version": WORKFLOW_VERSION,
        "run_id": run_id
    }
    
    print(f"📁 Loaded existing review run: {run_id}")
    return workflow

if __name__ == "__main__":
    
    # Parse command line arguments
    run_id = None
    start_from_query = 1
    max_results_per_query = None
    
    if "--run" in sys.argv:
        idx = sys.argv.index("--run")
        if idx + 1 < len(sys.argv):
            run_id = sys.argv[idx + 1]
    
    if "--start-from" in sys.argv:
        idx = sys.argv.index("--start-from")
        if idx + 1 < len(sys.argv):
            start_from_query = int(sys.argv[idx + 1])
    
    if "--max-results" in sys.argv:
        idx = sys.argv.index("--max-results")
        if idx + 1 < len(sys.argv):
            max_results_per_query = int(sys.argv[idx + 1])
    
    # Determine workflow type
    if "--manual-screen" in sys.argv or "--import-to-zotero" in sys.argv or "--view-results" in sys.argv or "--generate-report" in sys.argv:
        # Operations on existing runs
        if not run_id:
            print("❌ --run parameter required for manual screening, Zotero import, viewing results, and generating reports")
            print("📋 Usage: python3 systematic_review.py --generate-report --run review_run_YYYYMMDD_HHMMSS")
            sys.exit(1)
        workflow = load_existing_workflow(run_id)
    elif run_id:
        # Resume existing workflow
        workflow = load_existing_workflow(run_id)
        workflow.print_workflow_header()
    else:
        # Create new query-by-query workflow (default)
        workflow = SystematicReviewWorkflow()
        workflow.print_workflow_header()
    
    # Execute requested operation
    if "--manual-screen" in sys.argv:
        workflow.manual_screening_interface()
    
    elif "--import-to-zotero" in sys.argv:
        results = workflow.import_to_zotero_after_manual_review()
        print(f"\n✅ Zotero import completed: {results.get('papers_imported', 0)} papers imported")
    
    elif "--view-results" in sys.argv:
        workflow.view_results_summary()
    
    elif "--generate-report" in sys.argv:
        print("📊 GENERATING COMBINED REPORT")
        print("=" * 60)
        report_result = workflow._generate_combined_report()
        if report_result["status"] == "success":
            print(f"\n✅ Report generation completed!")
            print(f"📄 Report files: {len(report_result.get('report_files', []))}")
            print(f"📊 Total papers: {report_result.get('total_papers', 0)}")
            print(f"🟢 Total included: {report_result.get('total_included', 0)}")
            for report_file in report_result.get('report_files', []):
                print(f"   📄 {report_file}")
        else:
            print(f"❌ Report generation failed: {report_result.get('error', 'Unknown error')}")
    
    elif len(sys.argv) == 1:
        # No arguments - start new query-by-query workflow with integrated early deduplication
        print("🔄 Starting new query-by-query workflow with integrated early deduplication (default)")
        results = workflow.run_query_by_query_workflow(
            start_from_query=start_from_query,
            max_results_per_query=max_results_per_query
        )
        
        # Handle different result types
        if results.get("status") == "stopped_by_user":
            print(f"\n🛑 Workflow stopped by user after Query #{results.get('stopped_after_query', 'unknown')}")
            print(f"📊 Completed {results.get('completed_queries', 0)} queries")
            print(f"📋 To resume: python3 systematic_review.py --start-from {results.get('next_query', 1)} --run {os.path.basename(workflow.run_dir)}")
        else:
            all_complete = results.get('all_complete', False)
            status_text = 'completed' if all_complete else 'partially completed'
            print(f"\n🎉 Query-by-query workflow {status_text}")
   
    elif "--early-dedup" in sys.argv:
        # Legacy early deduplication workflow (now deprecated, redirect to regular workflow)
        print("ℹ️  The --early-dedup flag is deprecated. Early deduplication is now integrated into the regular workflow.")
        print("🔄 Starting regular query-by-query workflow (which includes early deduplication)")
        results = workflow.run_query_by_query_workflow(
            start_from_query=start_from_query,
            max_results_per_query=max_results_per_query
        )
        
        # Handle different result types
        if results.get("status") == "stopped_by_user":
            print(f"\n🛑 Workflow stopped by user after Query #{results.get('stopped_after_query', 'unknown')}")
            print(f"📊 Completed {results.get('completed_queries', 0)} queries")
        else:
            print(f"\n🎉 Query-by-query workflow completed!")
            if results.get('deduplication_metadata'):
                print(f"📈 Efficiency gain: {results.get('deduplication_metadata', {}).get('efficiency_gain', 'N/A')}")
    
    else:
        # Resume or start query-by-query workflow with parameters
        print(f"🔄 {'Resuming' if run_id else 'Starting'} query-by-query workflow with integrated early deduplication")
        if start_from_query > 1:
            print(f"📋 Starting from query #{start_from_query}")
        
        results = workflow.run_query_by_query_workflow(
            start_from_query=start_from_query,
            max_results_per_query=max_results_per_query
        )
        
        # Handle different result types
        if results.get("status") == "stopped_by_user":
            print(f"\n🛑 Workflow stopped by user after Query #{results.get('stopped_after_query', 'unknown')}")
            print(f"📊 Completed {results.get('completed_queries', 0)} queries")
            print(f"📋 To resume: python3 systematic_review.py --start-from {results.get('next_query', 1)} --run {os.path.basename(workflow.run_dir)}")
        else:
            all_complete = results.get('all_complete', False)
            status_text = 'completed' if all_complete else 'partially completed'
            print(f"\n🎉 Query-by-query workflow {status_text}")
        