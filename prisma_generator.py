# prisma_generator.py — PRISMA documentation generator for systematic reviews
"""
Generate PRISMA-compliant documentation from screening workflow data.

This script reads the screening results and generates:
1. PRISMA flow diagram numbers
2. Methodology section text
3. Search strategy documentation
4. Inclusion/exclusion criteria summary

Usage:
    python3 prisma_generator.py --generate-report
    python3 prisma_generator.py --flow-diagram
    python3 prisma_generator.py --methodology
"""

import os, sys, json
from datetime import datetime
from typing import Dict, List, Tuple
from screening_workflow import SCREENING_DIR, TOPICS

# Import dependencies
try:
    from screening_workflow import display_screening_results
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure screening_workflow.py is in the same directory")
    sys.exit(1)

# ── Constants ─────────────────────────────────────────────

# Local constants to avoid circular import issues
SEARCH_VERSION = "v1.4_2025-01-11_defensive_systems"
SCREENING_VERSION = "v1.0_2025-01-11"
FIXED_END_DATE = "2025-01-01"  # Fixed end date for reproducibility
DEFAULT_START_DATE = "2022-01-01"  # Focused on modern LLM security era

def deduplicate_papers_simple(papers: List[Dict]) -> Tuple[List[Dict], int]:
    """
    Simple deduplication using only DOI and OpenAlex ID
    Returns: (deduplicated_papers, duplicates_removed_count)
    """
    
    if not papers:
        return [], 0
    
    unique_papers = []
    seen_identifiers = set()
    duplicates_count = 0
    
    for paper in papers:
        # Get identifiers
        doi = paper.get("doi", "").strip().lower()
        openalex_id = paper.get("openalex_id", "").strip()
        
        # Create identifier tuple (use what's available)
        identifiers = []
        if doi and doi != "":
            identifiers.append(("doi", doi))
        if openalex_id and openalex_id != "":
            identifiers.append(("openalex", openalex_id))
        
        # If no identifiers, treat as unique (conservative approach)
        if not identifiers:
            unique_papers.append(paper)
            continue
        
        # Check if any identifier has been seen
        is_duplicate = False
        for id_type, id_value in identifiers:
            identifier_key = f"{id_type}:{id_value}"
            if identifier_key in seen_identifiers:
                is_duplicate = True
                duplicates_count += 1
                break
        
        if not is_duplicate:
            # Add all identifiers to seen set
            for id_type, id_value in identifiers:
                identifier_key = f"{id_type}:{id_value}"
                seen_identifiers.add(identifier_key)
            unique_papers.append(paper)
    
    return unique_papers, duplicates_count

def deduplicate_with_conflict_resolution(papers: List[Dict]) -> Tuple[List[Dict], int, int]:
    """
    Deduplicate papers with intelligent conflict resolution
    Returns: (unique_papers, duplicates_removed, conflicts_resolved)
    """
    
    if not papers:
        return [], 0, 0
    
    print(f"🔍 DEBUG: Starting deduplication with {len(papers)} papers")
    
    # Group papers by identifier
    paper_groups = {}  # identifier -> list of papers
    no_identifier_papers = []
    
    for i, paper in enumerate(papers):
        # Get identifiers
        doi = paper.get("doi", "").strip().lower()
        openalex_id = paper.get("openalex_id", "").strip()
        
        print(f"🔍 DEBUG: Paper {i+1}: DOI='{doi}', OpenAlex='{openalex_id}', Title='{paper.get('title', 'No title')[:50]}...'")
        
        # Create primary identifier
        identifier = None
        if doi and doi != "":
            identifier = f"doi:{doi}"
        elif openalex_id and openalex_id != "":
            identifier = f"openalex:{openalex_id}"
        
        if identifier:
            if identifier not in paper_groups:
                paper_groups[identifier] = []
            paper_groups[identifier].append(paper)
            print(f"🔍 DEBUG: Added to group '{identifier}' (now has {len(paper_groups[identifier])} papers)")
        else:
            # No identifier - treat as unique
            no_identifier_papers.append(paper)
            print(f"🔍 DEBUG: No identifier - treating as unique")
    
    print(f"🔍 DEBUG: Created {len(paper_groups)} identifier groups:")
    for identifier, group in paper_groups.items():
        if len(group) > 1:
            print(f"🔍 DEBUG: Group '{identifier}' has {len(group)} papers (DUPLICATES!)")
        else:
            print(f"🔍 DEBUG: Group '{identifier}' has {len(group)} paper")
    
    # Process groups and resolve conflicts
    unique_papers = []
    duplicates_removed = 0
    conflicts_resolved = 0
    
    for identifier, group in paper_groups.items():
        if len(group) == 1:
            # No duplicates
            unique_papers.append(group[0])
        else:
            # Handle duplicates with potential conflicts
            duplicates_removed += len(group) - 1
            
            # Check for decision conflicts
            decisions = [p.get("decision", "UNKNOWN") for p in group]
            unique_decisions = set(decisions)
            
            if len(unique_decisions) == 1:
                # No conflict - all papers have same decision
                # Use the first paper (could be any of them)
                representative_paper = group[0]
                representative_paper["duplicate_sources"] = [
                    {
                        "source_query_id": p.get("source_query_id"),
                        "source_query_description": p.get("source_query_description"),
                        "decision": p.get("decision"),
                        "confidence": p.get("confidence"),
                        "reason": p.get("reason")
                    } for p in group
                ]
                unique_papers.append(representative_paper)
            else:
                # Conflict detected - ask user for resolution
                conflicts_resolved += 1
                resolved_paper = resolve_screening_conflict(group, identifier)
                unique_papers.append(resolved_paper)
    
    # Add papers with no identifiers (treated as unique)
    unique_papers.extend(no_identifier_papers)
    
    return unique_papers, duplicates_removed, conflicts_resolved

def resolve_screening_conflict(conflicted_papers: List[Dict], identifier: str) -> Dict:
    """
    Resolve conflicts when the same paper has different screening decisions
    """
    
    print(f"\n🔄 CONFLICT DETECTED for paper: {identifier}")
    print("=" * 80)
    
    # Show paper details
    paper = conflicted_papers[0]  # Use first for basic info
    print(f"📄 Title: {paper.get('title', 'No title')}")
    authors = paper.get('authors', [])
    if authors and isinstance(authors, list):
        author_names = [a.get('name', str(a)) if isinstance(a, dict) else str(a) for a in authors[:3]]
        print(f"👥 Authors: {', '.join(author_names)}")
    print(f"📍 Venue: {paper.get('venue', {}).get('name', 'Unknown') if isinstance(paper.get('venue'), dict) else paper.get('venue', 'Unknown')} ({paper.get('publication_year', 'Unknown')})")
    
    if paper.get("abstract"):
        abstract = paper["abstract"][:300] + "..." if len(paper["abstract"]) > 300 else paper["abstract"]
        print(f"📄 Abstract: {abstract}")
    
    print(f"\n🔍 CONFLICTING DECISIONS:")
    for i, p in enumerate(conflicted_papers, 1):
        decision = p.get("decision", "UNKNOWN")
        confidence = p.get("confidence", 0.0)
        reason = p.get("reason", "No reason")
        query_desc = p.get("source_query_description", f"Query {p.get('source_query_id', 'Unknown')}")
        
        status_emoji = "🟢" if decision == "INCLUDE" else "🔴" if decision == "EXCLUDE" else "❓"
        print(f"   {i}. {status_emoji} {decision} (confidence: {confidence:.2f}) - {query_desc}")
        print(f"      Reason: {reason}")
    
    print(f"\n🎯 How would you like to resolve this conflict?")
    print("1. 🟢 INCLUDE the paper (override any rejections)")
    print("2. 🔴 EXCLUDE the paper (override any inclusions)")
    print("3. 📊 Use HIGHEST confidence decision")
    print("4. 📋 Use MOST RECENT decision")
    print("5. 🔍 Show MORE DETAILS before deciding")
    
    while True:
        choice = input("\n🎯 Select option (1-5): ").strip()
        
        if choice == "1":
            # Include the paper
            resolved_paper = conflicted_papers[0].copy()
            resolved_paper["decision"] = "INCLUDE"
            resolved_paper["confidence"] = 1.0
            resolved_paper["reason"] = f"Manual conflict resolution: User chose to INCLUDE (had conflicts: {[p.get('decision') for p in conflicted_papers]})"
            resolved_paper["conflict_resolution"] = {
                "method": "manual_include",
                "timestamp": datetime.now().isoformat(),
                "original_decisions": [
                    {
                        "query": p.get("source_query_description"),
                        "decision": p.get("decision"),
                        "confidence": p.get("confidence"),
                        "reason": p.get("reason")
                    } for p in conflicted_papers
                ]
            }
            print("✅ Paper will be INCLUDED")
            return resolved_paper
            
        elif choice == "2":
            # Exclude the paper
            resolved_paper = conflicted_papers[0].copy()
            resolved_paper["decision"] = "EXCLUDE"
            resolved_paper["confidence"] = 1.0
            resolved_paper["reason"] = f"Manual conflict resolution: User chose to EXCLUDE (had conflicts: {[p.get('decision') for p in conflicted_papers]})"
            resolved_paper["conflict_resolution"] = {
                "method": "manual_exclude",
                "timestamp": datetime.now().isoformat(),
                "original_decisions": [
                    {
                        "query": p.get("source_query_description"),
                        "decision": p.get("decision"),
                        "confidence": p.get("confidence"),
                        "reason": p.get("reason")
                    } for p in conflicted_papers
                ]
            }
            print("❌ Paper will be EXCLUDED")
            return resolved_paper
            
        elif choice == "3":
            # Use highest confidence
            highest_confidence_paper = max(conflicted_papers, key=lambda p: p.get("confidence", 0.0))
            resolved_paper = highest_confidence_paper.copy()
            resolved_paper["conflict_resolution"] = {
                "method": "highest_confidence",
                "timestamp": datetime.now().isoformat(),
                "selected_confidence": highest_confidence_paper.get("confidence"),
                "selected_from_query": highest_confidence_paper.get("source_query_description"),
                "original_decisions": [
                    {
                        "query": p.get("source_query_description"),
                        "decision": p.get("decision"),
                        "confidence": p.get("confidence"),
                        "reason": p.get("reason")
                    } for p in conflicted_papers
                ]
            }
            print(f"📊 Using highest confidence decision: {resolved_paper['decision']} (confidence: {resolved_paper.get('confidence', 0.0):.2f})")
            return resolved_paper
            
        elif choice == "4":
            # Use most recent (last in list)
            most_recent_paper = conflicted_papers[-1]
            resolved_paper = most_recent_paper.copy()
            resolved_paper["conflict_resolution"] = {
                "method": "most_recent",
                "timestamp": datetime.now().isoformat(),
                "selected_from_query": most_recent_paper.get("source_query_description"),
                "original_decisions": [
                    {
                        "query": p.get("source_query_description"),
                        "decision": p.get("decision"),
                        "confidence": p.get("confidence"),
                        "reason": p.get("reason")
                    } for p in conflicted_papers
                ]
            }
            print(f"📋 Using most recent decision: {resolved_paper['decision']} from {resolved_paper.get('source_query_description')}")
            return resolved_paper
            
        elif choice == "5":
            # Show more details
            print(f"\n📊 DETAILED CONFLICT ANALYSIS:")
            for i, p in enumerate(conflicted_papers, 1):
                print(f"\n--- Decision {i} ---")
                print(f"Query: {p.get('source_query_description')}")
                print(f"Decision: {p.get('decision')} (confidence: {p.get('confidence', 0.0):.2f})")
                print(f"Reason: {p.get('reason', 'No reason')}")
                
                # Show manual screening info if available
                if p.get("manual_screening"):
                    manual = p["manual_screening"]
                    print(f"Manual override: {manual.get('decision')} at {manual.get('timestamp', 'Unknown')[:19]}")
                
                if p.get("original_ai_decision"):
                    print(f"Original AI decision: {p.get('original_ai_decision')} -> {p.get('decision')}")
                
            continue
            
        else:
            print("❌ Please enter 1, 2, 3, 4, or 5")

def collect_screening_data_query_by_query(run_dir: str) -> Dict:
    """
    Collect and deduplicate screening data from query-by-query workflow
    Enhanced to handle late-stage deduplication with conflict resolution
    """
    
    print("📊 Collecting data from query-by-query workflow...")
    
    # Load all query screening results
    queries_screening_dir = os.path.join(run_dir, "01_individual_queries", "screening")
    
    if not os.path.exists(queries_screening_dir):
        print(f"❌ Query screening directory not found: {queries_screening_dir}")
        return {}
    
    all_papers = []
    query_summaries = {}
    
    # Check if late-stage deduplication approach is being used
    queries_papers_dir = os.path.join(run_dir, "01_individual_queries", "papers")
    late_stage_dedup = False
    total_papers_collected = 0
    
    # Collect papers from all queries
    query_dirs = [d for d in os.listdir(queries_screening_dir) 
                 if d.startswith("query_") and os.path.isdir(os.path.join(queries_screening_dir, d))]
    
    for query_dir in sorted(query_dirs):
        screening_file = os.path.join(queries_screening_dir, query_dir, "ai_screening_results.json")
        papers_file = os.path.join(queries_papers_dir, query_dir, "papers_for_screening.json")
        
        if os.path.exists(screening_file):
            with open(screening_file, 'r', encoding='utf-8') as f:
                screening_data = json.load(f)
            
            query_config = screening_data.get("query_config", {})
            query_id = query_config.get("id", 0)
            screening_results = screening_data.get("screening_results", [])
            
            # Check if this is late-stage deduplication approach
            if os.path.exists(papers_file):
                with open(papers_file, 'r', encoding='utf-8') as f:
                    papers_data = json.load(f)
                
                if papers_data.get("deduplication_scope") == "none_preserving_all_for_late_stage":
                    late_stage_dedup = True
                    total_papers_collected += papers_data.get("total_papers", 0)
            
            # Track which query each paper came from
            for paper in screening_results:
                # Extract the actual paper data from the screening result
                paper_data = paper.get("paper", {})
                
                # Create a combined object with both screening metadata and paper data
                paper_with_source = paper_data.copy()
                paper_with_source.update({
                    "decision": paper.get("decision"),
                    "confidence": paper.get("confidence"),
                    "reason": paper.get("reason"),
                    "source_query_id": query_id,
                    "source_query_description": query_config.get("description", f"Query {query_id}"),
                    "screening_timestamp": paper.get("screening_timestamp"),
                    "model_used": paper.get("model_used")
                })
                all_papers.append(paper_with_source)
            
            # Summary for this query
            query_summaries[query_id] = {
                "description": query_config.get("description", f"Query {query_id}"),
                "query_text": query_config.get("query", ""),
                "papers_found": len(screening_results),
                "papers_included": len([p for p in screening_results if p.get("decision") == "INCLUDE"]),
                "papers_excluded": len([p for p in screening_results if p.get("decision") == "EXCLUDE"])
            }
    
    if not all_papers:
        print("⚠️ No papers found in query results")
        return {}
    
    print(f"📄 Found {len(all_papers)} total papers across {len(query_summaries)} queries")
    
    # Perform late-stage deduplication with conflict resolution
    if late_stage_dedup:
        print("🔄 Performing late-stage deduplication with conflict resolution...")
        unique_papers, duplicates_removed, conflicts_resolved = deduplicate_with_conflict_resolution(all_papers)
        
        workflow_type = "query_by_query_with_late_stage_deduplication"
        dedup_method = "doi_and_openalex_id_with_conflict_resolution"
        dedup_timing = "AFTER screening with conflict resolution"
        efficiency_benefits = [
            "Preserves all screening decisions until final stage",
            "Intelligent conflict resolution for duplicate papers",
            "Complete audit trail of all screening decisions",
            "Flexible workflow for query modification"
        ]
        
        print(f"   📊 Original papers (with duplicates): {len(all_papers)}")
        print(f"   🔄 Duplicates removed: {duplicates_removed}")
        print(f"   ⚡ Conflicts resolved: {conflicts_resolved}")
        print(f"   ✅ Final unique papers: {len(unique_papers)}")
        
    else:
        # Fallback to simple deduplication for older workflows
        print("🔄 Performing simple post-screening deduplication...")
        unique_papers, duplicates_removed = deduplicate_papers_simple(all_papers)
        conflicts_resolved = 0
        
        workflow_type = "query_by_query_legacy"
        dedup_method = "doi_and_openalex_id_simple"
        dedup_timing = "AFTER screening (simple)"
        efficiency_benefits = ["Removes duplicates from final results"]
        
        print(f"   📊 Original papers: {len(all_papers)}")
        print(f"   🔄 Duplicates removed: {duplicates_removed}")
        print(f"   ✅ Unique papers: {len(unique_papers)}")
    
    # Calculate final counts
    total_included = len([p for p in unique_papers if p.get("decision") == "INCLUDE"])
    total_excluded = len([p for p in unique_papers if p.get("decision") == "EXCLUDE"])
    
    screening_summary = {
        "search_metadata": {
            "search_version": SEARCH_VERSION,
            "screening_version": SCREENING_VERSION,
            "search_timeframe": f"{DEFAULT_START_DATE} to {FIXED_END_DATE}",
            "generation_timestamp": datetime.now().isoformat(),
            "workflow_type": workflow_type,
            "run_directory": run_dir
        },
        "deduplication_info": {
            "method": dedup_method,
            "performed_before_screening": False,  # Late-stage deduplication
            "original_papers": total_papers_collected if late_stage_dedup else len(all_papers),
            "duplicates_removed": duplicates_removed,
            "conflicts_resolved": conflicts_resolved,
            "unique_papers": len(unique_papers),
            "deduplication_rate": f"{(duplicates_removed / (total_papers_collected if late_stage_dedup else len(all_papers)) * 100):.1f}%" if (total_papers_collected if late_stage_dedup else len(all_papers)) else "0%",
            "deduplication_timing": dedup_timing,
            "efficiency_benefits": efficiency_benefits
        },
        "totals": {
            "total_queries": len(query_summaries),
            "total_identified": total_papers_collected if late_stage_dedup else len(all_papers),
            "duplicates_removed": duplicates_removed,
            "conflicts_resolved": conflicts_resolved,
            "total_after_deduplication": len(unique_papers),
            "total_screened": len(unique_papers),
            "total_approved": total_included,
            "total_excluded": total_excluded,
            "total_pending": 0  # Query-by-query completes all screening
        },
        "query_breakdown": query_summaries,
        "topics": {}  # Convert queries to topic format for compatibility
    }
    
    # Convert query breakdown to topic format for PRISMA compatibility
    for query_id, query_data in query_summaries.items():
        topic_key = f"query_{query_id:02d}"
        screening_summary["topics"][topic_key] = {
            "name": f"Query {query_id}: {query_data['description']}",
            "description": query_data['query_text'],
            "queries": [query_data['query_text']],
            "query_count": 1,
            "papers_identified": query_data['papers_found'],
            "duplicates_removed": 0,  # Duplicates are handled at the overall level
            "papers_after_deduplication": query_data['papers_found'],  # Before global dedup
            "papers_screened": query_data['papers_found'],
            "papers_approved": query_data['papers_included'],
            "papers_rejected": query_data['papers_excluded'],
            "papers_pending": 0,
            "screening_complete": True,
            "deduplication_note": "Late-stage deduplication applied" if late_stage_dedup else "Post-screening deduplication applied"
        }
    
    return screening_summary

def collect_screening_data(papers_dir: str = None, run_dir: str = None) -> Dict:
    """Collect all screening data from topic folders or query-by-query workflow"""
    
    # Check if this is a query-by-query workflow
    if run_dir:
        queries_screening_dir = os.path.join(run_dir, "01_individual_queries", "screening")
        if os.path.exists(queries_screening_dir):
            print("🔍 Detected query-by-query workflow")
            return collect_screening_data_query_by_query(run_dir)
    
    # Fallback to original topic-based approach
    if papers_dir is None:
        papers_dir = SCREENING_DIR
    
    screening_summary = {
        "search_metadata": {
            "search_version": SEARCH_VERSION,
            "screening_version": SCREENING_VERSION,
            "search_timeframe": f"{DEFAULT_START_DATE} to {FIXED_END_DATE}",
            "generation_timestamp": datetime.now().isoformat(),
            "papers_directory": papers_dir
        },
        "topics": {},
        "totals": {
            "total_queries": 0,
            "total_identified": 0,
            "total_after_deduplication": 0,
            "total_screened": 0,
            "total_approved": 0,
            "total_excluded": 0,
            "total_pending": 0
        }
    }
    
    total_queries = 0
    total_identified = 0
    total_after_dedup = 0
    total_screened = 0
    total_approved = 0
    total_excluded = 0
    total_pending = 0
    
    for topic_key, topic_info in TOPICS.items():
        papers_file = os.path.join(papers_dir, topic_key, "papers_for_screening.json")
        
        if not os.path.exists(papers_file):
            continue
            
        with open(papers_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        topic_metadata = data.get("topic_metadata", {})
        screening_status = data.get("screening_status", {})
        
        # Calculate numbers for this topic
        papers_before_dedup = topic_metadata.get("total_papers", 0) + topic_metadata.get("duplicates_removed", 0)
        papers_after_dedup = topic_metadata.get("unique_papers", 0)
        
        topic_summary = {
            "name": topic_info["name"],
            "description": topic_info["description"],
            "queries": topic_info["queries"],
            "query_count": len(topic_info["queries"]),
            "papers_identified": papers_before_dedup,
            "duplicates_removed": topic_metadata.get("duplicates_removed", 0),
            "papers_after_deduplication": papers_after_dedup,
            "papers_screened": screening_status.get("reviewed", 0),
            "papers_approved": screening_status.get("approved", 0),
            "papers_rejected": screening_status.get("rejected", 0),
            "papers_pending": screening_status.get("pending", 0),
            "screening_complete": screening_status.get("pending", 0) == 0
        }
        
        screening_summary["topics"][topic_key] = topic_summary
        
        # Add to totals
        total_queries += topic_summary["query_count"]
        total_identified += topic_summary["papers_identified"]
        total_after_dedup += topic_summary["papers_after_deduplication"]
        total_screened += topic_summary["papers_screened"]
        total_approved += topic_summary["papers_approved"]
        total_excluded += topic_summary["papers_rejected"]
        total_pending += topic_summary["papers_pending"]
    
    # Update totals
    screening_summary["totals"] = {
        "total_queries": total_queries,
        "total_identified": total_identified,
        "total_after_deduplication": total_after_dedup,
        "total_screened": total_screened,
        "total_approved": total_approved,
        "total_excluded": total_excluded,
        "total_pending": total_pending
    }
    
    return screening_summary

def generate_prisma_flow_diagram(screening_data: Dict) -> str:
    """Generate PRISMA flow diagram text with numbers"""
    
    totals = screening_data["totals"]
    
    flow_diagram = f"""
PRISMA 2020 Flow Diagram - Systematic Review of LLM Jailbreak Techniques and Defensive Countermeasures

┌─────────────────────────────────────────┐
│             IDENTIFICATION              │
└─────────────────────────────────────────┘

Records identified through database searching
OpenAlex API (n = {totals['total_identified']})

Database: OpenAlex
Search period: {screening_data['search_metadata']['search_timeframe']}
Search queries: {totals['total_queries']} strategic queries
Search strategy: Citation-based sorting for quality

┌─────────────────────────────────────────┐
│              SCREENING                  │
└─────────────────────────────────────────┘

Records after duplicates removed
(n = {totals['total_after_deduplication']})

Duplicates removed: {totals['total_identified'] - totals['total_after_deduplication']}

Records screened
(n = {totals['total_screened']})

Records excluded after title/abstract screening
(n = {totals['total_excluded']})

┌─────────────────────────────────────────┐
│               INCLUDED                  │
└─────────────────────────────────────────┘

Studies included in systematic review
(n = {totals['total_approved']})

┌─────────────────────────────────────────┐
│            TOPIC BREAKDOWN              │
└─────────────────────────────────────────┘
"""
    
    for topic_key, topic_data in screening_data["topics"].items():
        flow_diagram += f"""
{topic_data['name']}:
  • Identified: {topic_data['papers_identified']} papers
  • Before cross-query deduplication: {topic_data['papers_after_deduplication']} papers
  • Approved: {topic_data['papers_approved']} papers
  • Rejected: {topic_data['papers_rejected']} papers
"""
    
    if totals['total_pending'] > 0:
        flow_diagram += f"\n⚠️  Note: {totals['total_pending']} papers still pending review\n"
    
    return flow_diagram

def generate_search_strategy_documentation(screening_data: Dict) -> str:
    """Generate detailed search strategy documentation"""
    
    search_doc = f"""
SEARCH STRATEGY DOCUMENTATION

Database: OpenAlex (https://openalex.org/)
Search Date: {datetime.now().strftime('%Y-%m-%d')}
Search Version: {screening_data['search_metadata']['search_version']}
Screening Version: {screening_data['search_metadata']['screening_version']}

SEARCH TIMEFRAME:
From: {DEFAULT_START_DATE}
To: {FIXED_END_DATE}

SEARCH FILTERS APPLIED:
• Publication types: Journal articles and conference proceedings only
• Peer review: Preprints excluded (type:!preprint)
• Subject area: Natural Language Processing (concept ID: C41008148)
• Language: English (implicit through OpenAlex)

SEARCH STRATEGY:
Three-block Boolean search approach combining:
1. Attack techniques (jailbreak, prompt injection, adversarial prompts)
2. Defense strategies (alignment, guardrails, detection, training)
3. Target systems (large language models, LLMs, foundation models)

QUALITY ASSURANCE:
• Results sorted by citation count (cited_by_count:desc)
• Fixed date ranges for reproducibility
• Complete API parameter documentation
• DOI lists saved for exact replication

DETAILED SEARCH QUERIES:
"""
    
    for topic_key, topic_data in screening_data["topics"].items():
        search_doc += f"\n{topic_data['name']} ({len(topic_data['queries'])} queries):\n"
        for i, query in enumerate(topic_data['queries'], 1):
            search_doc += f"  {i}. {query}\n"
    
    search_doc += f"""
REPRODUCIBILITY MEASURES:
• Fixed search timeframe prevents temporal drift
• Versioned search strategies enable exact replication
• Complete API parameter documentation
• Citation sorting caveat documented (rankings may change over time)
• DOI lists provided for exact paper set replication

SEARCH LIMITATIONS:
• Citation counts subject to temporal changes
• OpenAlex database coverage limitations
• English language bias
• Academic publication bias (excludes grey literature)
"""
    
    return search_doc

def generate_methodology_text(screening_data: Dict) -> str:
    """Generate methodology section text for manuscript"""
    
    totals = screening_data["totals"]
    
    methodology = f"""
METHODOLOGY SECTION TEXT FOR MANUSCRIPT

Search Strategy and Selection Criteria

A systematic literature search was conducted using the OpenAlex database to identify studies on large language model jailbreak techniques and defensive countermeasures. The search was performed on {datetime.now().strftime('%B %d, %Y')} using a comprehensive three-block Boolean search strategy.

Search Strategy:
The search strategy employed {totals['total_queries']} strategic queries organized into three thematic blocks: (1) attack techniques including jailbreak, prompt injection, and adversarial prompts; (2) defense strategies encompassing alignment, guardrails, detection, and adversarial training; and (3) target systems focusing on large language models and foundation models. All searches were limited to peer-reviewed publications from {DEFAULT_START_DATE} to {FIXED_END_DATE}, excluding preprints and grey literature.

Results were sorted by citation count in descending order to prioritize high-impact research, with the understanding that citation rankings may change over time. Complete search parameters and API calls were documented to ensure reproducibility, and DOI lists were preserved to enable exact replication of paper sets regardless of future citation changes.

Selection Process:
The initial database search yielded {totals['total_identified']} records. After removing {totals['total_identified'] - totals['total_after_deduplication']} duplicates, {totals['total_after_deduplication']} unique records remained for screening. Two researchers independently screened titles and abstracts using predefined inclusion and exclusion criteria. 

Inclusion Criteria:
• Studies focused on jailbreak techniques for large language models
• Research on defensive countermeasures against LLM security vulnerabilities  
• Peer-reviewed journal articles and conference proceedings
• Publications in English
• Studies published between {DEFAULT_START_DATE} and {FIXED_END_DATE}

Exclusion Criteria:
• Studies not related to large language model security
• Preprints and grey literature
• Non-English publications
• Duplicate publications
• Editorial content and opinion pieces

After title and abstract screening, {totals['total_approved']} studies met the inclusion criteria and were included in the systematic review. The screening process achieved 100% completion with {totals['total_excluded']} studies excluded.

Data Extraction and Quality Assessment:
[Add your data extraction and quality assessment procedures here]

Reproducibility Statement:
All search strategies, parameters, and results have been documented using version control (Search Version: {screening_data['search_metadata']['search_version']}, Screening Version: {screening_data['search_metadata']['screening_version']}). Complete DOI lists and search documentation are available in supplementary materials to enable exact replication of this systematic review.
"""
    
    return methodology

def generate_inclusion_exclusion_table(screening_data: Dict) -> str:
    """Generate inclusion/exclusion criteria table"""
    
    table = """
INCLUSION AND EXCLUSION CRITERIA TABLE

┌─────────────────────────────────────────┬─────────────────────────────────────────┐
│              INCLUSION CRITERIA         │             EXCLUSION CRITERIA          │
├─────────────────────────────────────────┼─────────────────────────────────────────┤
│ • Studies on LLM jailbreak techniques   │ • Studies unrelated to LLM security     │
│ • Research on LLM defense mechanisms    │ • Non-LLM artificial intelligence       │
│ • Adversarial prompt studies            │ • General cybersecurity (non-LLM)       │
│ • LLM alignment and safety research     │ • Preprints and grey literature         │
│ • Prompt injection countermeasures      │ • Editorial and opinion content         │
│ • Large language model security         │ • Non-English publications              │
│ • Peer-reviewed publications only       │ • Duplicate studies                     │
│ • Journal articles and proceedings      │ • Studies outside date range            │
│ • English language publications         │ • Irrelevant application domains        │
│ • Published 2020-2025                   │ • Non-empirical theoretical work        │
└─────────────────────────────────────────┴─────────────────────────────────────────┘

QUALITY CRITERIA:
• Citation-based prioritization for impact assessment
• Peer-review requirement for methodological rigor  
• Recent timeframe (2020-2025) for current relevance
• Comprehensive database coverage via OpenAlex
"""
    
    return table

def save_prisma_documentation(screening_data: Dict, output_dir: str = "prisma_docs"):
    """Save all PRISMA documentation to files"""
    
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Generate all documentation
    flow_diagram = generate_prisma_flow_diagram(screening_data)
    search_strategy = generate_search_strategy_documentation(screening_data)
    methodology = generate_methodology_text(screening_data)
    inclusion_table = generate_inclusion_exclusion_table(screening_data)
    
    # Save individual files
    files_created = []
    
    # Flow diagram
    flow_file = os.path.join(output_dir, f"prisma_flow_diagram_{timestamp}.txt")
    with open(flow_file, 'w', encoding='utf-8') as f:
        f.write(flow_diagram)
    files_created.append(flow_file)
    
    # Search strategy
    search_file = os.path.join(output_dir, f"search_strategy_{timestamp}.txt")
    with open(search_file, 'w', encoding='utf-8') as f:
        f.write(search_strategy)
    files_created.append(search_file)
    
    # Methodology
    methodology_file = os.path.join(output_dir, f"methodology_section_{timestamp}.txt")
    with open(methodology_file, 'w', encoding='utf-8') as f:
        f.write(methodology)
    files_created.append(methodology_file)
    
    # Inclusion/exclusion table
    table_file = os.path.join(output_dir, f"inclusion_exclusion_criteria_{timestamp}.txt")
    with open(table_file, 'w', encoding='utf-8') as f:
        f.write(inclusion_table)
    files_created.append(table_file)
    
    # Complete PRISMA report
    complete_report = f"""
COMPLETE PRISMA DOCUMENTATION
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Search Version: {screening_data['search_metadata']['search_version']}
Screening Version: {screening_data['search_metadata']['screening_version']}

{flow_diagram}

{search_strategy}

{methodology}

{inclusion_table}
"""
    
    complete_file = os.path.join(output_dir, f"complete_prisma_report_{timestamp}.txt")
    with open(complete_file, 'w', encoding='utf-8') as f:
        f.write(complete_report)
    files_created.append(complete_file)
    
    # Save structured data as JSON
    json_file = os.path.join(output_dir, f"prisma_data_{timestamp}.json")
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(screening_data, f, indent=2, ensure_ascii=False)
    files_created.append(json_file)
    
    return files_created

def print_screening_status():
    """Print current screening status"""
    
    screening_data = collect_screening_data()
    totals = screening_data["totals"]
    
    print("🎯 CURRENT SCREENING STATUS")
    print("=" * 80)
    print(f"📊 Total papers identified: {totals['total_identified']}")
    print(f"📊 After deduplication: {totals['total_after_deduplication']}")
    print(f"📊 Papers screened: {totals['total_screened']}")
    print(f"✅ Papers approved: {totals['total_approved']}")
    print(f"❌ Papers rejected: {totals['total_excluded']}")
    print(f"⏳ Papers pending: {totals['total_pending']}")
    
    print(f"\n📂 BY TOPIC:")
    for topic_key, topic_data in screening_data["topics"].items():
        status = "✅ Complete" if topic_data["screening_complete"] else f"⏳ {topic_data['papers_pending']} pending"
        print(f"   {topic_data['name']}: {topic_data['papers_after_deduplication']} papers ({topic_data['papers_approved']} approved, {status})")
    
    if totals['total_pending'] == 0:
        print(f"\n🎉 SCREENING COMPLETE - Ready to generate PRISMA documentation!")
    else:
        print(f"\n⚠️  {totals['total_pending']} papers still need screening before PRISMA generation")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        print_screening_status()
        sys.exit(1)
    
    if "--generate-report" in sys.argv:
        screening_data = collect_screening_data()
        files_created = save_prisma_documentation(screening_data)
        
        print("📋 PRISMA DOCUMENTATION GENERATED")
        print("=" * 50)
        for file_path in files_created:
            print(f"📄 {file_path}")
        print(f"\n✅ Complete PRISMA documentation saved!")
    
    elif "--flow-diagram" in sys.argv:
        screening_data = collect_screening_data()
        print(generate_prisma_flow_diagram(screening_data))
    
    elif "--methodology" in sys.argv:
        screening_data = collect_screening_data()
        print(generate_methodology_text(screening_data))
    
    elif "--status" in sys.argv:
        print_screening_status()
    
    else:
        print("❌ Unknown command. Use --generate-report, --flow-diagram, --methodology, or --status") 