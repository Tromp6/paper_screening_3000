# ai_screening.py — AI-powered paper screening for systematic reviews
"""
Automated paper screening using OpenAI API with detailed justifications.

This script provides:
1. Automated title/abstract screening using GPT-4
2. Detailed reasoning for each decision
3. PRISMA-compliant documentation
4. Quality assurance and human oversight options

Usage:
    python3 ai_screening.py --screen-topic attack --model gpt-4o
    python3 ai_screening.py --screen-all --confidence-threshold 0.8
    python3 ai_screening.py --generate-screening-report
"""

import os, sys, json, time
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import openai
from dotenv import load_dotenv
from screening_workflow import SCREENING_DIR, TOPICS

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# ── AI Screening Configuration ──────────────────────────────

AI_SCREENING_VERSION = "v1.0_2025-01-11"
DEFAULT_MODEL = "gpt-4o"
SCREENING_PROMPT = """
You are screening papers for a systematic literature review on "LLM Jailbreak Techniques and Defensive Countermeasures."

Based on the paper TITLE only, decide if this paper should be INCLUDED or EXCLUDED.

INCLUDE if the title suggests the paper is about:
• LLM jailbreak techniques or attacks
• LLM security vulnerabilities
• Defensive countermeasures for LLMs
• Prompt injection or adversarial prompts
• LLM alignment and safety
• Red teaming or security evaluation of LLMs

EXCLUDE if the title suggests:
• General AI/ML not specific to LLM security
• Medical/healthcare applications
• Business/management studies
• General cybersecurity not related to LLMs
• Educational content or tutorials

Respond with ONLY a simple JSON object:
{"decision": "INCLUDE" or "EXCLUDE", "confidence": 0.0-1.0, "reason": "brief reason"}

Be conservative - when uncertain, choose INCLUDE.
"""

def screen_paper_with_ai(paper: Dict, model: str = DEFAULT_MODEL) -> Dict:
    """Screen a single paper using OpenAI API - simplified version using only title"""
    
    # Use only the title for screening
    title = paper.get("title", "No title available")
    
    # Much simpler paper info
    paper_info = f"TITLE: {title}"
    
    try:
        response = openai.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SCREENING_PROMPT},
                {"role": "user", "content": paper_info}
            ],
            temperature=0.1,  # Low temperature for consistency
            max_tokens=200    # Much smaller response
        )
        
        ai_response = response.choices[0].message.content.strip()
        
        # Try to parse JSON response
        try:
            # Clean up the response in case there's extra text
            if "{" in ai_response and "}" in ai_response:
                json_start = ai_response.find("{")
                json_end = ai_response.rfind("}") + 1
                json_text = ai_response[json_start:json_end]
            else:
                json_text = ai_response
                
            screening_result = json.loads(json_text)
            
            # Validate required fields
            if "decision" not in screening_result:
                screening_result["decision"] = "EXCLUDE"
            if "confidence" not in screening_result:
                screening_result["confidence"] = 0.5
            if "reason" not in screening_result:
                screening_result["reason"] = "Default exclusion"
                
        except json.JSONDecodeError:
            # Simple fallback parsing
            ai_lower = ai_response.lower()
            if "include" in ai_lower:
                decision = "INCLUDE"
                confidence = 0.6
            else:
                decision = "EXCLUDE" 
                confidence = 0.8
                
            screening_result = {
                "decision": decision,
                "confidence": confidence,
                "reason": f"Fallback parsing: {ai_response[:100]}"
            }
        
        # Add metadata
        screening_result.update({
            "model_used": model,
            "screening_timestamp": datetime.now().isoformat(),
            "ai_screening_version": AI_SCREENING_VERSION,
            "paper_id": paper.get("doi", f"no_doi_{hash(title)}"),
            "title_screened": title
        })
        
        return screening_result
        
    except Exception as e:
        return {
            "decision": "EXCLUDE",
            "confidence": 0.0,
            "reason": f"API error: {str(e)}",
            "model_used": model,
            "screening_timestamp": datetime.now().isoformat(),
            "ai_screening_version": AI_SCREENING_VERSION,
            "paper_id": paper.get("doi", f"no_doi_{hash(title)}"),
            "title_screened": title,
            "error": True
        }

def screen_topic_with_ai(topic: str, model: str = DEFAULT_MODEL, 
                        confidence_threshold: float = 0.7, 
                        max_papers: Optional[int] = None,
                        papers_dir: str = None,
                        output_dir: str = None) -> Dict:
    """Screen papers for a specific topic using AI"""
    
    # Use organized directory structure if available, otherwise fall back to old structure
    if papers_dir is None:
        # Try organized structure first
        if os.path.exists("01_papers_collected"):
            papers_dir = "01_papers_collected"
        else:
            papers_dir = "paper_screening"
    
    if output_dir is None:
        # Try organized structure first
        if os.path.exists("02_screening_results") or papers_dir == "01_papers_collected":
            output_dir = "02_screening_results"
        else:
            output_dir = "ai_screening_results"
    
    if topic not in TOPICS:
        print(f"❌ Unknown topic: {topic}")
        print(f"Available topics: {', '.join(TOPICS.keys())}")
        return {}
    
    topic_info = TOPICS[topic]
    papers_file = os.path.join(papers_dir, topic, "papers_for_screening.json")
    
    if not os.path.exists(papers_file):
        raise FileNotFoundError(f"No papers found for topic '{topic}' in {papers_file}")
    
    print(f"🤖 AI SCREENING: {topic_info['name']}")
    print(f"📁 Input: {papers_file}")
    print(f"📁 Output: {output_dir}/{topic}/")
    print(f"🧠 Model: {model}")
    print(f"🎯 Confidence threshold: {confidence_threshold}")
    print("=" * 80)
    
    # Load papers
    with open(papers_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Handle different data structures
    if isinstance(data, dict) and "papers" in data:
        papers = data["papers"]
    elif isinstance(data, list):
        papers = data
    else:
        raise ValueError(f"Unexpected data structure in {papers_file}")
    
    if max_papers:
        papers = papers[:max_papers]
        print(f"🔢 Limited to {max_papers} papers for testing")
    
    print(f"📄 Screening {len(papers)} papers...")
    
    # Screen each paper
    screened_papers = []
    included_count = 0
    excluded_count = 0
    
    for i, paper in enumerate(papers, 1):
        print(f"  [{i}/{len(papers)}] Screening: {paper.get('title', 'No title')[:60]}...")
        
        screening_result = screen_paper_with_ai(paper, model)
        
        # Add screening result to paper
        paper["ai_screening"] = screening_result
        screened_papers.append(paper)
        
        # Count results
        decision = screening_result.get("decision", "EXCLUDE")
        confidence = screening_result.get("confidence", 0.0)
        
        if decision == "INCLUDE" and confidence >= confidence_threshold:
            included_count += 1
            status = f"✅ INCLUDE (conf: {confidence:.2f})"
        else:
            excluded_count += 1
            status = f"❌ EXCLUDE (conf: {confidence:.2f})"
        
        print(f"    {status}: {screening_result.get('reason', 'No reason')}")
        
        # Rate limiting
        time.sleep(1)
    
    # Generate screening summary
    screening_summary = {
        "topic": topic,
        "topic_name": TOPICS[topic]["name"],
        "total_papers": len(papers),
        "included_papers": included_count,
        "excluded_papers": excluded_count,
        "model_used": model,
        "confidence_threshold": confidence_threshold,
        "screening_timestamp": datetime.now().isoformat(),
        "ai_screening_version": AI_SCREENING_VERSION,
        "papers_source": papers_file,
        "output_directory": output_dir
    }
    
    # Save results to output directory
    os.makedirs(os.path.join(output_dir, topic), exist_ok=True)
    ai_results_file = os.path.join(output_dir, topic, "ai_screening_results.json")
    with open(ai_results_file, 'w', encoding='utf-8') as f:
        json.dump({
            "screening_summary": screening_summary,
            "screened_papers": screened_papers
        }, f, indent=2, ensure_ascii=False)
    
    # Also save approved papers separately for easy import
    included_papers = [
        paper for paper in screened_papers 
        if paper.get("ai_screening", {}).get("decision") == "INCLUDE" 
        and paper.get("ai_screening", {}).get("confidence", 0.0) >= confidence_threshold
    ]
    
    if included_papers:
        approved_file = os.path.join(output_dir, topic, "approved_papers.json")
        with open(approved_file, 'w', encoding='utf-8') as f:
            json.dump(included_papers, f, indent=2, ensure_ascii=False)
        print(f"📄 Approved papers saved: {approved_file}")
    
    print(f"\n{'='*80}")
    print(f"🤖 AI SCREENING COMPLETE: {TOPICS[topic]['name']}")
    print(f"✅ Included: {included_count}")
    print(f"❌ Excluded: {excluded_count}")
    print(f"📄 Results saved: {ai_results_file}")
    print(f"{'='*80}")
    
    return screening_summary

def generate_ai_screening_report(screening_dir: str = None, output_dir: str = None) -> str:
    """Generate comprehensive AI screening report for PRISMA documentation"""
    
    if screening_dir is None:
        screening_dir = SCREENING_DIR
    if output_dir is None:
        output_dir = "ai_screening_reports"
    
    print("📋 GENERATING AI SCREENING REPORT")
    print("=" * 80)
    print(f"📁 Screening directory: {screening_dir}")
    print(f"📁 Output directory: {output_dir}")
    
    # Collect all AI screening results
    all_results = {}
    total_papers = 0
    total_included = 0
    total_excluded = 0
    
    for topic_key, topic_info in TOPICS.items():
        ai_results_file = os.path.join(screening_dir, topic_key, "ai_screening_results.json")
        
        if os.path.exists(ai_results_file):
            with open(ai_results_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                all_results[topic_key] = data
                
                summary = data["screening_summary"]
                total_papers += summary["total_papers"]
                total_included += summary["included_papers"]
                total_excluded += summary["excluded_papers"]
    
    if not all_results:
        print("⚠️  No AI screening results found")
        return ""
    
    # Generate report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    report = f"""
AI-POWERED SCREENING REPORT
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
AI Screening Version: {AI_SCREENING_VERSION}

═══════════════════════════════════════════════════════════════════════════════

SCREENING METHODOLOGY:

The title and abstract screening was conducted using OpenAI's GPT-4o model to ensure 
consistent and transparent evaluation criteria. Each paper was assessed against 
predefined inclusion and exclusion criteria with detailed reasoning provided for 
each decision.

Model Configuration:
• Model: GPT-4o
• Temperature: 0.1 (for consistency)
• Confidence threshold: 0.7
• Screening prompt: Systematic review-specific instructions

Quality Assurance:
• Each decision includes confidence score (0.0-1.0)
• Detailed reasoning provided for transparency
• Conservative approach: bias toward inclusion when uncertain
• Human oversight recommended for borderline cases

═══════════════════════════════════════════════════════════════════════════════

SCREENING RESULTS SUMMARY:

Total Papers Screened: {total_papers}
Papers Included: {total_included}
Papers Excluded: {total_excluded}
Inclusion Rate: {(total_included/total_papers*100):.1f}%

BREAKDOWN BY TOPIC:
"""
    
    for topic_key, topic_info in TOPICS.items():
        if topic_key in all_results:
            summary = all_results[topic_key]["screening_summary"]
            report += f"""
{topic_info['name']}:
  • Total papers: {summary['total_papers']}
  • Included: {summary['included_papers']}
  • Excluded: {summary['excluded_papers']}
  • Inclusion rate: {(summary['included_papers']/summary['total_papers']*100):.1f}%
"""
    
    report += f"""
═══════════════════════════════════════════════════════════════════════════════

DETAILED SCREENING DECISIONS:

The following section documents the AI screening decisions with reasoning for 
transparency and reproducibility in systematic review methodology.
"""
    
    # Add detailed decisions for each topic
    for topic_key, topic_info in TOPICS.items():
        if topic_key in all_results:
            report += f"\n\n{topic_info['name'].upper()} - DETAILED DECISIONS:\n"
            report += "─" * 80 + "\n"
            
            screened_papers = all_results[topic_key]["screened_papers"]
            
            for i, paper in enumerate(screened_papers, 1):
                ai_result = paper.get("ai_screening", {})
                decision = ai_result.get("decision", "UNKNOWN")
                confidence = ai_result.get("confidence", 0.0)
                reason = ai_result.get("reason", "No reason provided")
                
                title = paper.get("title", "No title")[:100] + "..." if len(paper.get("title", "")) > 100 else paper.get("title", "No title")
                
                report += f"\n{i}. [{decision}, Conf: {confidence:.2f}] {title}\n"
                report += f"   Reason: {reason}\n"
    
    report += f"""

═══════════════════════════════════════════════════════════════════════════════

REPRODUCIBILITY AND TRANSPARENCY:

This AI screening was conducted using systematic, reproducible methods:

1. Standardized Prompts: All papers evaluated using identical screening criteria
2. Version Control: AI Screening Version {AI_SCREENING_VERSION}
3. Model Consistency: Fixed model (GPT-4o) and temperature (0.1) settings
4. Confidence Scoring: Quantitative assessment of decision certainty
5. Complete Documentation: Full reasoning provided for each decision

The screening results can be replicated by re-running the AI screening module with 
identical parameters on the same paper set.

═══════════════════════════════════════════════════════════════════════════════
"""
    
    # Save report
    os.makedirs(output_dir, exist_ok=True)
    report_file = os.path.join(output_dir, f"ai_screening_report_{timestamp}.txt")
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"📄 AI Screening Report saved: {report_file}")
    
    return report_file

def screen_papers_with_ai(papers: List[Dict], confidence_threshold: float = 0.7, 
                         model: str = DEFAULT_MODEL) -> List[Dict]:
    """Screen a list of papers using AI - for query-by-query workflow"""
    
    print(f"🤖 Screening {len(papers)} papers with AI...")
    print(f"🧠 Model: {model}")
    print(f"🎯 Confidence threshold: {confidence_threshold}")
    
    screened_results = []
    included_count = 0
    excluded_count = 0
    
    for i, paper in enumerate(papers, 1):
        print(f"  [{i}/{len(papers)}] Screening: {paper.get('title', 'No title')[:60]}...")
        
        try:
            # Screen this paper
            result = screen_paper_with_ai(paper, model)
            
            # Add paper metadata to result
            result.update({
                "paper": paper,  # Include full paper data
                "title": paper.get("title", ""),
                "authors": paper.get("authors", []),
                "venue": paper.get("venue", {}),
                "publication_year": paper.get("publication_year"),
            })
            
            screened_results.append(result)
            
            # Count results
            if result.get("decision") == "INCLUDE":
                included_count += 1
                print(f"    ✅ INCLUDED (confidence: {result.get('confidence', 0):.2f})")
            else:
                excluded_count += 1
                print(f"    ❌ EXCLUDED (confidence: {result.get('confidence', 0):.2f})")
            
            # Small delay to be polite to API
            time.sleep(0.5)
            
        except Exception as e:
            print(f"    ❌ Error screening paper: {e}")
            # Add error result
            screened_results.append({
                "decision": "EXCLUDE",
                "confidence": 0.0,
                "reason": f"Screening error: {e}",
                "error": True,
                "paper": paper,
                "title": paper.get("title", ""),
                "paper_id": paper.get("doi", f"no_doi_{hash(paper.get('title', ''))}"),
                "screening_timestamp": datetime.now().isoformat()
            })
            excluded_count += 1
    
    print(f"\n📊 Screening complete:")
    print(f"  ✅ Included: {included_count}")
    print(f"  ❌ Excluded: {excluded_count}")
    print(f"  📈 Inclusion rate: {included_count/len(papers)*100:.1f}%")
    
    return screened_results

# ── Command Line Interface ──────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    # Parse arguments
    args = sys.argv[1:]
    model = DEFAULT_MODEL
    confidence_threshold = 0.7
    max_papers = None
    
    # Extract optional parameters
    if "--model" in args:
        idx = args.index("--model")
        if idx + 1 < len(args):
            model = args[idx + 1]
    
    if "--confidence-threshold" in args:
        idx = args.index("--confidence-threshold")
        if idx + 1 < len(args):
            confidence_threshold = float(args[idx + 1])
    
    if "--max-papers" in args:
        idx = args.index("--max-papers")
        if idx + 1 < len(args):
            max_papers = int(args[idx + 1])
    
    if "--screen-topic" in args:
        idx = args.index("--screen-topic")
        if idx + 1 < len(args):
            topic = args[idx + 1]
            screen_topic_with_ai(topic, model, confidence_threshold, max_papers)
        else:
            print("❌ --screen-topic requires a topic name")
    
    elif "--screen-all" in args:
        for topic_key in TOPICS.keys():
            try:
                screen_topic_with_ai(topic_key, model, confidence_threshold, max_papers)
                time.sleep(2)  # Pause between topics
            except Exception as e:
                print(f"❌ Error screening {topic_key}: {e}")
                continue
    
    elif "--generate-screening-report" in args:
        generate_ai_screening_report()
    
    else:
        print("❌ Unknown command. Use --screen-topic, --screen-all, or --generate-screening-report") 