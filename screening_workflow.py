# screening_workflow.py — Paper collection and screening for systematic reviews
"""
Paper collection and screening workflow for systematic literature reviews:

1. FETCH STAGE: Collect papers from OpenAlex and organize by topic
2. AI SCREENING STAGE: Automated screening with GPT-4o
3. IMPORT STAGE: Upload approved papers to Zotero

This implements PRISMA-compliant screening with complete audit trail.
All functions now support organized directory structure for better organization.

Usage with organized workflow:
    # Use through master workflow (recommended)
    python3 systematic_review.py --full-auto --max-results 50
    
    # Or use individual stages (legacy)
    python3 screening_workflow.py --fetch --max-results 30
    python3 screening_workflow.py --screen --topic attack
    python3 screening_workflow.py --import-approved
"""

import os, sys, re, time, math, json, requests
from datetime import datetime
from typing import List, Dict
from tqdm import tqdm
from dotenv import load_dotenv

# Import from existing scripts
# Note: Constants are defined locally to avoid circular imports
# Note: Other functions imported locally to avoid circular imports

# ── Constants ─────────────────────────────────────────────

# Local constants to avoid circular import issues
SEARCH_VERSION = "v1.4_2025-01-11_defensive_systems"
SCREENING_VERSION = "v1.0_2025-01-11"
FIXED_END_DATE = "2025-01-01"  # Fixed end date for reproducibility
DEFAULT_START_DATE = "2022-01-01"  # Focused on modern LLM security era

# ── Screening Configuration ─────────────────────────────────

SCREENING_DIR = "paper_screening"  # Legacy default, prefer organized directories
TOPICS = {
    "attack": {
        "name": "Attack Techniques",
        "description": "Jailbreak, prompt injection, and adversarial prompts",
        "queries": [
            '"jailbreak" AND "large language model"',
            '"prompt injection" AND "large language model"',
            '"adversarial prompt" AND "large language model"'
        ]
    },
    "defense": {
        "name": "Defense Strategies", 
        "description": "Alignment, guardrails, detection, and adversarial training",
        "queries": [
            '"alignment" AND "large language model"',
            '"guardrails" AND "large language model"',
            '"detection" AND "large language model"',
            '"adversarial training" AND "large language model"'
        ]
    },
    "general": {
        "name": "General Security",
        "description": "Broader LLM security research",
        "queries": [
            '"LLM security"'
        ]
    }
}

# ── Stage 1: Fetch and Organize Papers ─────────────────────

def fetch_and_organize_papers(max_results_per_query: int = 30):
    """Fetch papers from OpenAlex and organize by topic for screening"""
    
    # Import locally to avoid circular imports
    from systematic_review import openalex_query_with_metadata
    
    print("🎯 STAGE 1: FETCH AND ORGANIZE PAPERS FOR SCREENING")
    print("=" * 80)
    print(f"📅 Fixed timeframe: {DEFAULT_START_DATE} to {FIXED_END_DATE}")
    print(f"🔍 Screening version: {SCREENING_VERSION}")
    print(f"📊 Target: {len([q for topic in TOPICS.values() for q in topic['queries']]) * max_results_per_query} total papers")
    print("=" * 80)
    
    # Create screening directory structure
    for topic_key, topic_info in TOPICS.items():
        topic_dir = os.path.join(SCREENING_DIR, topic_key)
        os.makedirs(topic_dir, exist_ok=True)
        
        # Create topic info file
        topic_metadata = {
            "topic": topic_key,
            "name": topic_info["name"],
            "description": topic_info["description"],
            "queries": topic_info["queries"],
            "screening_version": SCREENING_VERSION,
            "fetch_timestamp": datetime.now().isoformat()
        }
        
        with open(os.path.join(topic_dir, "topic_info.json"), 'w') as f:
            json.dump(topic_metadata, f, indent=2)
    
    # Fetch papers for each topic
    total_fetched = 0
    
    for topic_key, topic_info in TOPICS.items():
        print(f"\n📂 Processing Topic: {topic_info['name']}")
        print(f"   📝 {topic_info['description']}")
        
        topic_papers = []
        
        for i, query in enumerate(topic_info["queries"], 1):
            print(f"\n🔍 Query {i}/{len(topic_info['queries'])}: {query}")
            
            papers, search_metadata = openalex_query_with_metadata(
                query,
                start_date=DEFAULT_START_DATE,
                end_date=FIXED_END_DATE,
                max_results=max_results_per_query,
                peer_reviewed_only=True,
                top_venues_only=False
            )
            
            if papers:
                # Add query info to each paper
                for paper in papers:
                    paper["source_query"] = query
                    paper["query_number"] = f"{i}/{len(topic_info['queries'])}"
                    paper["topic"] = topic_key
                
                topic_papers.extend(papers)
                print(f"   ✅ Collected {len(papers)} papers")
            else:
                print(f"   ❌ No papers found")
        
        # Remove duplicates within topic (same DOI)
        seen_dois = set()
        unique_papers = []
        for paper in topic_papers:
            doi = paper.get("doi", "").replace("https://doi.org/", "")
            if doi and doi not in seen_dois:
                seen_dois.add(doi)
                unique_papers.append(paper)
            elif not doi:  # Keep papers without DOIs for now
                unique_papers.append(paper)
        
        # Save topic papers for screening
        topic_dir = os.path.join(SCREENING_DIR, topic_key)
        papers_file = os.path.join(topic_dir, "papers_for_screening.json")
        
        screening_data = {
            "topic_metadata": {
                "topic": topic_key,
                "name": topic_info["name"],
                "description": topic_info["description"],
                "total_papers": len(unique_papers),
                "unique_papers": len(unique_papers),
                "duplicates_removed": len(topic_papers) - len(unique_papers),
                "fetch_timestamp": datetime.now().isoformat(),
                "screening_version": SCREENING_VERSION
            },
            "papers": unique_papers,
            "screening_status": {
                "total_papers": len(unique_papers),
                "reviewed": 0,
                "approved": 0,
                "rejected": 0,
                "pending": len(unique_papers)
            }
        }
        
        with open(papers_file, 'w', encoding='utf-8') as f:
            json.dump(screening_data, f, indent=2, ensure_ascii=False)
        
        total_fetched += len(unique_papers)
        print(f"   📄 Saved {len(unique_papers)} unique papers to {papers_file}")
    
    print(f"\n{'='*80}")
    print("📋 FETCH STAGE SUMMARY")
    print(f"{'='*80}")
    print(f"🎯 TOTAL PAPERS FETCHED: {total_fetched}")
    print(f"📁 Organized into {len(TOPICS)} topic folders")
    print(f"📍 Location: {SCREENING_DIR}/")
    print(f"▶️  NEXT STEP: Review papers by topic using --screen")
    print(f"{'='*80}")
    
    return total_fetched

# ── Stage 2: Screening Interface ───────────────────────────

def screen_papers_by_topic(topic: str):
    """Present papers for manual screening by topic"""
    
    if topic not in TOPICS:
        print(f"❌ Unknown topic: {topic}")
        print(f"Available topics: {', '.join(TOPICS.keys())}")
        return
    
    topic_dir = os.path.join(SCREENING_DIR, topic)
    papers_file = os.path.join(topic_dir, "papers_for_screening.json")
    
    if not os.path.exists(papers_file):
        print(f"❌ No papers found for topic '{topic}'")
        print(f"Run --fetch first to collect papers")
        return
    
    # Load papers
    with open(papers_file, 'r', encoding='utf-8') as f:
        screening_data = json.load(f)
    
    papers = screening_data["papers"]
    topic_info = TOPICS[topic]
    
    print(f"🔍 STAGE 2: SCREENING - {topic_info['name'].upper()}")
    print("=" * 80)
    print(f"📝 {topic_info['description']}")
    print(f"📊 Papers to review: {len(papers)}")
    print(f"📍 Topic: {topic}")
    print("=" * 80)
    
    # Display papers for review
    print(f"\n📋 PAPERS FOR SCREENING:")
    print(f"{'='*120}")
    
    for i, paper in enumerate(papers, 1):
        title = paper.get("title", "No title")[:80]
        if len(paper.get("title", "")) > 80:
            title += "..."
            
        authors = ", ".join([a["name"] for a in paper.get("authors", [])[:3]])
        if len(paper.get("authors", [])) > 3:
            authors += " et al."
            
        venue = paper.get("venue", {}).get("name", "Unknown venue")[:40]
        year = paper.get("publication_year", "N/A")
        citations = paper.get("citation_count", 0)
        
        print(f"\n{i:2d}. [{citations:4d} cites, {year}] {title}")
        print(f"    👥 {authors}")
        print(f"    📍 {venue}")
        print(f"    🔍 From query: {paper.get('source_query', 'Unknown')}")
        
        if paper.get("abstract"):
            abstract = paper["abstract"][:200] + "..." if len(paper.get("abstract", "")) > 200 else paper["abstract"]
            print(f"    📄 {abstract}")
    
    print(f"\n{'='*120}")
    print(f"📊 SCREENING SUMMARY:")
    print(f"   📑 Total papers: {len(papers)}")
    print(f"   🔍 Topic: {topic_info['name']}")
    print(f"   📝 Description: {topic_info['description']}")
    print(f"\n💡 Review these papers and respond with your screening decisions.")
    print(f"   Format: 'approve: 1,3,5-8,12' or 'reject: 2,4,9-11'")
    print(f"   Or: 'approve all' / 'reject all'")
    
    return papers, screening_data

def save_screening_decisions(topic: str, approved_indices: List[int], rejected_indices: List[int]):
    """Save screening decisions and update status"""
    
    topic_dir = os.path.join(SCREENING_DIR, topic)
    papers_file = os.path.join(topic_dir, "papers_for_screening.json")
    
    # Load current data
    with open(papers_file, 'r', encoding='utf-8') as f:
        screening_data = json.load(f)
    
    papers = screening_data["papers"]
    
    # Mark papers as approved/rejected
    for i in approved_indices:
        if 0 <= i < len(papers):
            papers[i]["screening_decision"] = "approved"
            papers[i]["screening_timestamp"] = datetime.now().isoformat()
    
    for i in rejected_indices:
        if 0 <= i < len(papers):
            papers[i]["screening_decision"] = "rejected"
            papers[i]["screening_timestamp"] = datetime.now().isoformat()
    
    # Update screening status
    approved_count = len([p for p in papers if p.get("screening_decision") == "approved"])
    rejected_count = len([p for p in papers if p.get("screening_decision") == "rejected"])
    reviewed_count = approved_count + rejected_count
    pending_count = len(papers) - reviewed_count
    
    screening_data["screening_status"] = {
        "total_papers": len(papers),
        "reviewed": reviewed_count,
        "approved": approved_count,
        "rejected": rejected_count,
        "pending": pending_count,
        "last_updated": datetime.now().isoformat()
    }
    
    # Save updated data
    with open(papers_file, 'w', encoding='utf-8') as f:
        json.dump(screening_data, f, indent=2, ensure_ascii=False)
    
    # Create approved papers file for Zotero import
    approved_papers = [p for p in papers if p.get("screening_decision") == "approved"]
    if approved_papers:
        approved_file = os.path.join(topic_dir, "approved_papers.json")
        with open(approved_file, 'w', encoding='utf-8') as f:
            json.dump({
                "topic": topic,
                "approved_papers": approved_papers,
                "approval_timestamp": datetime.now().isoformat(),
                "screening_version": SCREENING_VERSION
            }, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ SCREENING DECISIONS SAVED:")
    print(f"   ✅ Approved: {approved_count} papers")
    print(f"   ❌ Rejected: {rejected_count} papers") 
    print(f"   ⏳ Pending: {pending_count} papers")
    print(f"   📄 Updated: {papers_file}")
    
    return approved_count, rejected_count, pending_count

# ── Stage 3: Import Approved Papers ────────────────────────

def import_approved_papers():
    """Import all approved papers to Zotero"""
    
    # Import locally to avoid circular imports
    from systematic_review import openalex_to_zotero, push_papers, COLL
    
    print("🎯 STAGE 3: IMPORT APPROVED PAPERS TO ZOTERO")
    print("=" * 80)
    
    total_approved = 0
    total_imported = 0
    
    for topic_key, topic_info in TOPICS.items():
        topic_dir = os.path.join(SCREENING_DIR, topic_key)
        approved_file = os.path.join(topic_dir, "approved_papers.json")
        
        if not os.path.exists(approved_file):
            print(f"⚠️  No approved papers found for topic: {topic_info['name']}")
            continue
        
        # Load approved papers
        with open(approved_file, 'r', encoding='utf-8') as f:
            approved_data = json.load(f)
        
        approved_papers = approved_data["approved_papers"]
        total_approved += len(approved_papers)
        
        if not approved_papers:
            continue
        
        print(f"\n📂 Importing {topic_info['name']}: {len(approved_papers)} papers")
        
        # Convert to Zotero format
        zotero_papers = []
        for paper in approved_papers:
            # Create mock OpenAlex work structure
            mock_work = {
                "title": paper.get("title", ""),
                "publication_date": paper.get("publication_date", ""),
                "doi": paper.get("doi", ""),
                "abstract": paper.get("abstract", ""),
                "cited_by_count": paper.get("citation_count", 0),
                "type": paper.get("type", "article"),
                "authorships": [{"author": {"display_name": author["name"]}} for author in paper.get("authors", [])],
                "primary_location": {"source": paper.get("venue", {})},
                "concepts": [{"display_name": concept["name"], "score": concept["score"]} for concept in paper.get("concepts", [])]
            }
            
            zotero_papers.append(openalex_to_zotero(mock_work))
        
        # Import to Zotero
        successful, failed = push_papers(zotero_papers, COLL["oa"])
        total_imported += successful
        
        print(f"   ✅ Imported: {successful} papers")
        print(f"   ❌ Failed: {failed} papers")
    
    print(f"\n{'='*80}")
    print("📋 IMPORT SUMMARY")
    print(f"{'='*80}")
    print(f"🎯 TOTAL APPROVED: {total_approved} papers")
    print(f"✅ SUCCESSFULLY IMPORTED: {total_imported} papers")
    print(f"📚 Zotero collection: {COLL.get('oa', 'Not configured')}")
    print(f"✅ Systematic review ready for next phase!")
    print(f"{'='*80}")
    
    return total_imported

# ── Directory-Based Functions for Organized Workflow ──────

def fetch_and_organize_papers_to_directory(max_results_per_query: int = 30, output_dir: str = None):
    """Fetch papers and organize to specified directory structure"""
    
    # Import locally to avoid circular imports
    from systematic_review import openalex_query_with_metadata
    
    if output_dir is None:
        output_dir = os.path.join("paper_screening", "papers")
    
    print("🎯 STAGE 1: FETCH AND ORGANIZE PAPERS FOR SCREENING")
    print("=" * 80)
    print(f"📅 Fixed timeframe: {DEFAULT_START_DATE} to {FIXED_END_DATE}")
    print(f"🔍 Screening version: {SCREENING_VERSION}")
    print(f"📁 Output directory: {output_dir}")
    print(f"📊 Target: {len([q for topic in TOPICS.values() for q in topic['queries']]) * max_results_per_query} total papers")
    print("=" * 80)
    
    # Create directory structure
    os.makedirs(output_dir, exist_ok=True)
    
    # Create screening directory structure
    for topic_key, topic_info in TOPICS.items():
        topic_dir = os.path.join(output_dir, topic_key)
        os.makedirs(topic_dir, exist_ok=True)
        
        # Create topic info file
        topic_metadata = {
            "topic": topic_key,
            "name": topic_info["name"],
            "description": topic_info["description"],
            "queries": topic_info["queries"],
            "screening_version": SCREENING_VERSION,
            "fetch_timestamp": datetime.now().isoformat()
        }
        
        with open(os.path.join(topic_dir, "topic_info.json"), 'w') as f:
            json.dump(topic_metadata, f, indent=2)
    
    # Fetch papers for each topic
    total_fetched = 0
    
    for topic_key, topic_info in TOPICS.items():
        print(f"\n📂 Processing Topic: {topic_info['name']}")
        print(f"   📝 {topic_info['description']}")
        
        topic_papers = []
        
        for i, query in enumerate(topic_info["queries"], 1):
            print(f"\n🔍 Query {i}/{len(topic_info['queries'])}: {query}")
            
            papers, search_metadata = openalex_query_with_metadata(
                query,
                start_date=DEFAULT_START_DATE,
                end_date=FIXED_END_DATE,
                max_results=max_results_per_query,
                peer_reviewed_only=True,
                top_venues_only=False
            )
            
            if papers:
                # Add query info to each paper
                for paper in papers:
                    paper["source_query"] = query
                    paper["query_number"] = f"{i}/{len(topic_info['queries'])}"
                    paper["topic"] = topic_key
                
                topic_papers.extend(papers)
                print(f"   ✅ Collected {len(papers)} papers")
            else:
                print(f"   ❌ No papers found")
        
        # Remove duplicates within topic (same DOI)
        seen_dois = set()
        unique_papers = []
        for paper in topic_papers:
            doi = paper.get("doi", "").replace("https://doi.org/", "")
            if doi and doi not in seen_dois:
                seen_dois.add(doi)
                unique_papers.append(paper)
            elif not doi:  # Keep papers without DOIs for now
                unique_papers.append(paper)
        
        # Save topic papers for screening
        topic_dir = os.path.join(output_dir, topic_key)
        papers_file = os.path.join(topic_dir, "papers_for_screening.json")
        
        screening_data = {
            "topic_metadata": {
                "topic": topic_key,
                "name": topic_info["name"],
                "description": topic_info["description"],
                "total_papers": len(unique_papers),
                "unique_papers": len(unique_papers),
                "duplicates_removed": len(topic_papers) - len(unique_papers),
                "fetch_timestamp": datetime.now().isoformat(),
                "screening_version": SCREENING_VERSION
            },
            "papers": unique_papers,
            "screening_status": {
                "total_papers": len(unique_papers),
                "reviewed": 0,
                "approved": 0,
                "rejected": 0,
                "pending": len(unique_papers)
            }
        }
        
        with open(papers_file, 'w', encoding='utf-8') as f:
            json.dump(screening_data, f, indent=2, ensure_ascii=False)
        
        total_fetched += len(unique_papers)
        print(f"   📄 Saved {len(unique_papers)} unique papers to {papers_file}")
    
    print(f"\n{'='*80}")
    print("📋 FETCH STAGE SUMMARY")
    print(f"{'='*80}")
    print(f"🎯 TOTAL PAPERS FETCHED: {total_fetched}")
    print(f"📁 Organized into {len(TOPICS)} topic folders")
    print(f"📍 Location: {output_dir}/")
    print(f"▶️  NEXT STEP: Review papers by topic using AI screening")
    print(f"{'='*80}")
    
    return total_fetched

def import_approved_papers_from_directory(papers_dir: str = None, output_dir: str = None):
    """Import approved papers to Zotero from specified directory"""
    
    # Import locally to avoid circular imports
    from systematic_review import openalex_to_zotero, push_papers, COLL
    
    if papers_dir is None:
        papers_dir = os.path.join("paper_screening", "papers")
    if output_dir is None:
        output_dir = "zotero_imports"
    
    print("📚 STAGE 4: IMPORT APPROVED PAPERS TO ZOTERO")
    print("=" * 80)
    print(f"📁 Papers directory: {papers_dir}")
    print(f"📁 Zotero output directory: {output_dir}")
    
    os.makedirs(output_dir, exist_ok=True)
    
    all_approved = []
    total_by_topic = {}
    
    for topic_key in TOPICS.keys():
        topic_dir = os.path.join(papers_dir, topic_key)
        approved_file = os.path.join(topic_dir, "approved_papers.json")
        
        if os.path.exists(approved_file):
            with open(approved_file, 'r', encoding='utf-8') as f:
                topic_approved = json.load(f)
                all_approved.extend(topic_approved)
                total_by_topic[topic_key] = len(topic_approved)
                print(f"   📂 {TOPICS[topic_key]['name']}: {len(topic_approved)} approved papers")
        else:
            total_by_topic[topic_key] = 0
            print(f"   📂 {TOPICS[topic_key]['name']}: No approved papers found")
    
    if not all_approved:
        print("⚠️  No approved papers found. Run screening first.")
        return 0
    
    print(f"\n📊 Total approved papers: {len(all_approved)}")
    
    # Convert to Zotero format and import
    zotero_items = []
    for paper in all_approved:
        zotero_item = openalex_to_zotero(paper)
        zotero_items.append(zotero_item)
    
    print(f"📚 Importing {len(zotero_items)} papers to Zotero...")
    
    # Save import documentation
    import_doc = {
        "import_timestamp": datetime.now().isoformat(),
        "total_papers": len(all_approved),
        "papers_by_topic": total_by_topic,
        "zotero_collection": COLL.get("oa", "Not configured"),
        "screening_version": SCREENING_VERSION
    }
    
    doc_file = os.path.join(output_dir, f"import_documentation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(doc_file, 'w', encoding='utf-8') as f:
        json.dump(import_doc, f, indent=2)
    
    # Import to Zotero in batches
    total_successful = 0
    batch_size = 20
    
    for i in range(0, len(zotero_items), batch_size):
        batch = zotero_items[i:i+batch_size]
        successful, failed = push_papers(batch, COLL["oa"])
        total_successful += successful
        print(f"   ✅ Batch {i//batch_size + 1}: {successful} successful, {failed} failed")
        time.sleep(2)  # Rate limiting
    
    print(f"\n✅ Import completed: {total_successful} papers imported to Zotero")
    print(f"📄 Import documentation: {doc_file}")
    
    return total_successful

# ── Command Line Interface ──────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    if "--fetch" in sys.argv:
        max_results = 30
        if "--max-results" in sys.argv:
            idx = sys.argv.index("--max-results")
            if idx + 1 < len(sys.argv):
                max_results = int(sys.argv[idx + 1])
        
        fetch_and_organize_papers(max_results)
    
    elif "--screen" in sys.argv:
        if "--topic" in sys.argv:
            idx = sys.argv.index("--topic")
            if idx + 1 < len(sys.argv):
                topic = sys.argv[idx + 1]
                screen_papers_by_topic(topic)
            else:
                print("❌ --topic requires a topic name")
        else:
            print("❌ --screen requires --topic argument")
    
    elif "--import-approved" in sys.argv:
        import_approved_papers()
    
    else:
        print("❌ Unknown command. Use --fetch, --screen --topic <name>, or --import-approved")

def display_screening_results(screening_results: List[Dict], papers: List[Dict], limit: int = 10):
    """Display AI screening results in a formatted way"""
    
    included = [r for r in screening_results if r.get("decision") == "INCLUDE"]
    excluded = [r for r in screening_results if r.get("decision") == "EXCLUDE"]
    
    print(f"\n📊 AI SCREENING SUMMARY")
    print(f"{'='*60}")
    print(f"Total papers screened: {len(screening_results)}")
    print(f"✅ INCLUDED: {len(included)} papers")
    print(f"❌ EXCLUDED: {len(excluded)} papers")
    print(f"📈 Inclusion rate: {len(included)/len(screening_results)*100:.1f}%")
    
    # Show top included papers
    print(f"\n🎯 TOP {min(limit, len(included))} INCLUDED PAPERS:")
    print("-" * 60)
    
    # Sort by confidence
    included_sorted = sorted(included, key=lambda x: x.get("confidence", 0), reverse=True)
    
    for i, result in enumerate(included_sorted[:limit], 1):
        paper_id = result.get("paper_id", "")
        
        # Find corresponding paper
        paper = next((p for p in papers if p.get("doi") == paper_id), {})
        if not paper and "no_doi_" in paper_id:
            # Try to find by title hash
            title = result.get("title_screened", "")
            paper = next((p for p in papers if p.get("title") == title), {})
        
        title = paper.get("title", result.get("title_screened", "No title"))[:80]
        confidence = result.get("confidence", 0.0)
        reason = result.get("reason", "No reason provided")
        
        print(f"{i}. [Conf: {confidence:.2f}] {title}")
        print(f"   Reason: {reason}")
        if paper.get("venue"):
            venue_name = paper["venue"].get("name", "Unknown venue")[:50]
            year = paper.get("publication_year", "Unknown")
            print(f"   Venue: {venue_name} ({year})")
        print()
    
    # Show some excluded papers
    print(f"\n❌ SAMPLE EXCLUDED PAPERS:")
    print("-" * 60)
    
    excluded_sorted = sorted(excluded, key=lambda x: x.get("confidence", 0), reverse=True)
    
    for i, result in enumerate(excluded_sorted[:5], 1):
        paper_id = result.get("paper_id", "")
        
        # Find corresponding paper
        paper = next((p for p in papers if p.get("doi") == paper_id), {})
        if not paper and "no_doi_" in paper_id:
            title = result.get("title_screened", "")
            paper = next((p for p in papers if p.get("title") == title), {})
        
        title = paper.get("title", result.get("title_screened", "No title"))[:80]
        confidence = result.get("confidence", 0.0)
        reason = result.get("reason", "No reason provided")
        
        print(f"{i}. [Conf: {confidence:.2f}] {title}")
        print(f"   Reason: {reason}")
        print()
    
    print("=" * 60) 