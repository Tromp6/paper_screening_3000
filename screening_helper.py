# screening_helper.py — Helper for processing screening decisions from chat
"""
Helper functions for processing manual screening decisions from chat interactions.

Usage in chat:
1. User reviews papers displayed by screening_workflow.py --screen --topic <topic>
2. User provides decisions like: "approve: 1,3,5-8,12" or "reject: 2,4,9-11"
3. This script processes those decisions and updates the screening files
"""

import json
import re
from typing import List, Tuple
from screening_workflow import save_screening_decisions, SCREENING_DIR, TOPICS

def parse_screening_decision(decision_text: str) -> Tuple[List[int], List[int]]:
    """Parse screening decision text into approved and rejected indices"""
    
    approved_indices = []
    rejected_indices = []
    
    # Handle "approve all" or "reject all"
    if "approve all" in decision_text.lower():
        return "all", []
    elif "reject all" in decision_text.lower():
        return [], "all"
    
    # Parse approve: and reject: patterns
    approve_match = re.search(r'approve:\s*([0-9,\-\s]+)', decision_text, re.IGNORECASE)
    reject_match = re.search(r'reject:\s*([0-9,\-\s]+)', decision_text, re.IGNORECASE)
    
    if approve_match:
        approved_indices = parse_number_list(approve_match.group(1))
    
    if reject_match:
        rejected_indices = parse_number_list(reject_match.group(1))
    
    return approved_indices, rejected_indices

def parse_number_list(number_text: str) -> List[int]:
    """Parse comma-separated numbers and ranges into list of integers"""
    
    numbers = []
    parts = number_text.replace(' ', '').split(',')
    
    for part in parts:
        if '-' in part:
            # Handle ranges like "5-8"
            start, end = map(int, part.split('-'))
            numbers.extend(range(start, end + 1))
        else:
            # Handle single numbers
            if part.strip():
                numbers.append(int(part))
    
    # Convert to 0-based indices
    return [n - 1 for n in numbers if n > 0]

def process_screening_decision(topic: str, decision_text: str):
    """Process a screening decision and update the files"""
    
    if topic not in TOPICS:
        return f"❌ Unknown topic: {topic}. Available: {', '.join(TOPICS.keys())}"
    
    try:
        approved_indices, rejected_indices = parse_screening_decision(decision_text)
        
        # Handle "all" cases
        if approved_indices == "all":
            # Load papers to get count
            papers_file = f"{SCREENING_DIR}/{topic}/papers_for_screening.json"
            with open(papers_file, 'r') as f:
                data = json.load(f)
            approved_indices = list(range(len(data["papers"])))
            rejected_indices = []
        elif rejected_indices == "all":
            papers_file = f"{SCREENING_DIR}/{topic}/papers_for_screening.json"
            with open(papers_file, 'r') as f:
                data = json.load(f)
            approved_indices = []
            rejected_indices = list(range(len(data["papers"])))
        
        # Save decisions
        approved_count, rejected_count, pending_count = save_screening_decisions(
            topic, approved_indices, rejected_indices
        )
        
        return (f"✅ Processed screening decisions for {TOPICS[topic]['name']}:\n"
                f"   ✅ Approved: {approved_count} papers\n"
                f"   ❌ Rejected: {rejected_count} papers\n"
                f"   ⏳ Pending: {pending_count} papers")
        
    except Exception as e:
        return f"❌ Error processing decision: {e}"

def get_screening_status():
    """Get overall screening status across all topics"""
    
    status_summary = []
    total_papers = 0
    total_approved = 0
    total_rejected = 0
    total_pending = 0
    
    for topic_key, topic_info in TOPICS.items():
        papers_file = f"{SCREENING_DIR}/{topic_key}/papers_for_screening.json"
        
        try:
            with open(papers_file, 'r') as f:
                data = json.load(f)
            
            screening_status = data.get("screening_status", {})
            
            papers = screening_status.get("total_papers", 0)
            approved = screening_status.get("approved", 0)
            rejected = screening_status.get("rejected", 0)
            pending = screening_status.get("pending", papers)
            
            total_papers += papers
            total_approved += approved
            total_rejected += rejected
            total_pending += pending
            
            status = "✅ Complete" if pending == 0 else f"⏳ {pending} pending"
            
            status_summary.append(
                f"📂 {topic_info['name']}: {papers} papers ({approved} approved, {rejected} rejected, {status})"
            )
            
        except FileNotFoundError:
            status_summary.append(f"📂 {topic_info['name']}: No papers fetched yet")
    
    overall_status = "\n".join(status_summary)
    summary = (f"\n🎯 OVERALL SCREENING STATUS:\n"
               f"   📑 Total papers: {total_papers}\n"
               f"   ✅ Approved: {total_approved}\n"
               f"   ❌ Rejected: {total_rejected}\n"
               f"   ⏳ Pending: {total_pending}\n\n"
               f"{overall_status}")
    
    return summary

if __name__ == "__main__":
    # Example usage
    print("📋 Screening Helper - Example Usage:")
    print("process_screening_decision('attack', 'approve: 1,3,5-8 reject: 2,4')")
    print("get_screening_status()") 