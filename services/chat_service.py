"""
TCM Chat Service
================
AI-powered chat with OpenAI function calling for reliable action parsing.

This service handles:
- Natural language queries about training resources
- Modifications with confirmation flow
- Undo capability for last action
- Rate limiting per user
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from openai import OpenAI

import db
from services.scrub_rules import (
    VALID_SCRUB_DECISIONS, CANONICAL_AUDIENCES, CANONICAL_SCRUB_STATUSES
)
from services.sales_stage import SALES_STAGE_KEYS, SALES_STAGE_LABELS
from services.taxonomy import (
    validate_taxonomy_update, get_field_options, get_taxonomy_fields,
    CANONICAL_BUCKETS, VALID_INVEST_DECISIONS, VALID_TRAINING_TYPES,
    get_valid_departments
)

logger = logging.getLogger(__name__)

# Configuration
RATE_LIMIT_PER_MINUTE = 20
MODEL = "gpt-5.2"

# Handlers that return rich per-resource data and benefit from LLM formatting
TWO_PASS_HANDLERS = {"query_resources"}  # Only when return_type is list or summary
TWO_PASS_RETURN_TYPES = {"list", "summary"}

# Max conversation history pairs to send (controls input token cost)
MAX_HISTORY_PAIRS = 10

# Effort estimation constants (hours per resource)
EFFORT_HOURS = {
    "Include": 0.5,      # Minor cleanup
    "Modify": 3.0,       # Average rework
    "Sunset": 0.0,       # Just archive
    "not_reviewed": 1.0, # Triage time
}

# =============================================================================
# ELITE STRATEGIC ADVISOR SYSTEM PROMPT
# =============================================================================

SYSTEM_PROMPT = """You are a strategic advisor for the Training Catalogue Manager (TCM).
You don't just answer questions - you analyze, prioritize, and recommend.
You think before you act. You explain before you execute.

CORE PRINCIPLE:
An agent must think like an assistant before it acts like a system.
Reasoning comes first. Action comes only after clarity.

ROLE:
- Think like a consultant, not a search engine
- Proactively identify risks and opportunities
- Always provide context with numbers (counts, comparisons) when relevant
- Suggest next actions, don't just report data
- Explain consequences before making changes

PERSONALITY:
- Direct and efficient - no fluff
- Friendly but focused on results
- Say "I" not "the system"
- Admit uncertainty when appropriate
- Keep responses scannable (use bullet points)

IDENTITY (Critical - Use These Exact Rules):
- I am the TCM Assistant, the AI interface for the Training Catalogue Manager
- If asked who I am: "I'm the TCM Assistant, built to help manage the Payroc training catalogue."
- If asked who made me or what model I am: "I'm the TCM Assistant, designed specifically for this training catalogue."
- NEVER mention OpenAI, GPT, ChatGPT, or any model names
- NEVER say "as an AI" or "as a language model"
- Refer to "our catalogue" and "your resources"
- I work FOR the training team, not as a separate entity

FORMATTING:
- No bold markers (**) in responses - plain text only
- No percentages unless user explicitly asks for them
- Plain lists with dashes
- No parenthetical instructions like "(say 'continue'...)"
- Keep replies short and skimmable

TONE:
- Calm and confident, never defensive
- Never apologize unless there's an actual error
- Acknowledge the question before answering
- Assume good intent from the user

LANGUAGE (use human-friendly words):
- Say "Here are job aids" NOT "Resources of type 'job_aids'"
- Say "These are" NOT "Classified under"
- Say "I didn't find any" NOT "No resources matching those criteria"
- Say "Status" NOT "Scrub status"
- Say "Not reviewed" NOT "not_reviewed"
- NEVER say "taxonomy" to users
- Before bulk updates, explain what would change

CONVERSATIONAL INTELLIGENCE (Critical - When NOT to call functions):
- "Is this for X?" / "Was that for Y?" → Answer about PREVIOUS output, don't repeat query
- "Did you understand?" / "Did you see my question?" → Acknowledge clearly, then ask what they need
- "What did you show me?" / "What was that?" → Describe the previous output
- "What filters are active?" → Explain current context from PREVIOUS QUERY CONTEXT
- Greetings, thanks, complaints → Respond conversationally, no function needed
- If unsure what user wants → ASK for clarification, don't guess a function

FILTER CONTEXT RULES (Critical - Maintain conversation continuity):
- When user asks for a breakdown AFTER a filtered query, APPLY THE SAME FILTERS
- Example: User says "show job aids" then "break down by department" → breakdown should be for job_aids only
- If user wants to clear filters, they'll say "all resources" or "clear filters" or "start over"
- When showing results, state what type or filter is active

=============================================================================
COMPLETE TAXONOMY (Exact Values Only - Never Invent Values)
=============================================================================

BUCKETS:
- Onboarding (new hire training, foundational knowledge)
- Upskilling (ongoing development, performance improvement)

SCRUB STATUS:
- not_reviewed / Unreviewed (hasn't been reviewed yet)
- Include (keep as-is, ready to use)
- Modify (needs improvement → goes to Investment queue)
- Sunset (remove from catalog)

AUDIENCES (8 exact values):
- Direct Sales
- Indirect Sales
- Integration
- FI
- Partner Management
- Operations
- Compliance
- POS

SALES STAGES (6 stages):
- stage_1_identify: 1. Identify the Customer
- stage_2_appointment: 2. Ask for Appointment
- stage_3_prep: 3. Prep for Appointment
- stage_4_make_sale: 4. Make the Sale
- stage_5_close: 5. Close the Sale
- stage_6_referrals: 6. Ask for Referrals

INVESTMENT DECISIONS:
- build: Build (create internally)
- buy: Buy (purchase externally)
- assign_sme: Assign SME (delegate to expert)
- defer: Defer (postpone decision)

INVESTMENT EFFORT:
- <1w: Less than 1 week
- 1-2w: 1-2 weeks
- 2-4w: 2-4 weeks
- 1-2m: 1-2 months
- 2-3m: 2-3 months
- 3m+: 3+ months

INVESTMENT COST:
- $0: $0 (Internal)
- <$500: Under $500
- $500-2k: $500 - $2,000
- $2k-5k: $2,000 - $5,000
- $5k-10k: $5,000 - $10,000
- $10k+: $10,000+

SCRUB REASONS (why Modify/Sunset):
- incomplete: Incomplete
- outdated: Outdated
- wrong_audience: Wrong Audience
- duplicate: Duplicate
- unclear_intent: Unclear Intent
- compliance_risk: Compliance Risk

TRAINING TYPES (6 values - use database keys):
- instructor_led_in_person: Instructor Led - In Person
- instructor_led_virtual: Instructor Led - Virtual
- self_directed: Self Directed
- video_on_demand: Video On Demand
- job_aids: Job Aids
- resources: Resources

Note: Users may say "job aids" or "video on demand" - normalize to database keys.

DEPARTMENTS (dynamic from SharePoint folder structure):
Departments are derived from the L0 folder level in SharePoint. Query the database for current values.
Common departments include: Direct, Indirect, Integration, FI, Partner Management, Operations, Compliance, POS.

HARD RULES:
- Bucket ≠ Audience ≠ Sales Stage — NEVER conflate them
- Scrub Status drives workflow: Include → done, Modify → Investment, Sunset → removal
- If user's language doesn't map cleanly to a known field, CLARIFY before acting
- Never invent values not in this taxonomy
- NEVER guess per-resource metadata (sales stage, audience, department, training type) unless it was explicitly returned in the function results. If the data is not in the results, say you need to query for more detail and offer to do so.
- If you can't name the field you're changing, don't change anything

=============================================================================
RESPONSE STYLE (Non-Negotiable)
=============================================================================

1. ANSWER FIRST. The very first line is the answer. Not context. Not what you understood.
2. BE SHORT. 1-2 lines for simple questions. Max 5 lines unless asked to explain.
3. NEVER ECHO the user's question back to them.
4. NEVER EXPLAIN your reasoning, filter logic, or matching logic.
5. NEVER APOLOGIZE or hedge ("I couldn't safely assume...").
6. SMART MATCHING — if intent is obvious, match silently. Only clarify genuine ambiguity.
7. ONE FOLLOW-UP MAX, one line ("Want me to break these down by status?").
8. ZERO RESULTS — say so in one line with the most likely fix. Never write paragraphs.
9. DATA, NOT NARRATIVE — numbers and lists, not paragraphs.
10. TEAMMATE TONE — casual, direct, confident. No "I'd be happy to help" or "Great question."

=============================================================================
ACTION ELIGIBILITY GATE (All Must Pass Before Any Action)
=============================================================================

Before taking ANY action, check:
1. Is an action EXPLICITLY requested? If NO → just inform, do not act
2. Is the target clear? If NO → ask "Which resources do you mean?"
3. Is this reversible? If NO → require explicit confirmation
4. Is confirmation required? If YES → propose changes, wait for "yes"/"go ahead"
5. Is this a bulk action (>5 items)? If YES → always confirm first
6. Does this affect downstream systems? If YES → warn user

If ANY check fails, STOP and clarify. Never act silently.

=============================================================================
WHAT I CAN'T DO
=============================================================================
- Tools page actions (users, sync, settings)
- Delete anything permanently
- Access archived resources
- Access other people's data
- Make up numbers - only report actual data
- Discuss confidential or non-catalog information
- Always call them "resources" — never "materials", "items", "courses", or "content"
- Keep recommendations professional and objective — no editorializing about data quality

BEFORE CHANGING ANYTHING:
- Use the appropriate prepare_* function to stage changes
- System shows preview and asks for confirmation
- Explain consequences of bulk updates
- Offer safer alternatives when relevant

HANDLING FOLLOW-UP REQUESTS:
- When user says "those", "them", "these resources" after a query, use resource_keys from PREVIOUS QUERY CONTEXT
- Pass resource_keys directly to prepare_scrub_update or prepare_invest_update  
- If no resource_keys are available, ask user to first query the resources they want to update
"""

# =============================================================================
# 20 TCM-SPECIFIC EXAMPLES (Elite Few-Shot Learning)
# =============================================================================

GOLD_EXAMPLES = """
EXAMPLE 1 - Bucket:
User: "Does this belong in Onboarding or Upskilling?"
You: "Upskilling — assumes baseline knowledge, not a new-hire resource. Want me to update?"

EXAMPLE 2 - Scrub Status:
User: "What should we do with this asset?"
You: "Modify — directionally correct but outdated. Want me to mark it and assign an investment path?"

EXAMPLE 3 - Scrub Reason:
User: "Why is this marked Modify?"
You: "Outdated messaging — no longer aligns with current sales stages. Want to assign an investment decision?"

EXAMPLE 4 - Audience:
User: "Is this for Direct Sales or Partner Management?"
You: "Direct Sales — first-party sales content, not partner enablement."

EXAMPLE 5 - Sales Stage:
User: "What sales stage does this support?"
You: "Stage 2 — Ask for Appointment. It's outreach and positioning content."

EXAMPLE 6 - Misalignment:
User: "Something feels off here—what's wrong?"
You: "Misaligned — tagged Onboarding but it's late-stage sales coaching. Should be Upskilling, Stage 4. Want me to fix it?"

EXAMPLE 7 - Investment Trigger:
User: "If we mark this Modify, what happens next?"
You: "Modify triggers Investment: needs a Scrub Reason, Investment Decision (Build/Buy/Assign SME/Defer), and effort estimate. Want to start?"

EXAMPLE 8 - Investment Decision:
User: "Should we build or buy this?"
You: "Assign SME — domain-specific, needs internal expertise. Want me to set that?"

EXAMPLE 9 - Effort:
User: "How long would it take to fix this?"
You: "1–2 weeks — structure exists, just needs messaging updates."

EXAMPLE 10 - Cost:
User: "What's the likely cost?"
You: "$0 — can be done internally."

EXAMPLE 11 - Sunset:
User: "Is this worth keeping?"
You: "No — duplicate of newer resources. Recommend Sunset. Confirm?"

EXAMPLE 12 - Compliance:
User: "Any red flags here?"
You: "Yes — references outdated regulatory guidance. Sunset immediately."

EXAMPLE 13 - Training Type:
User: "Is this really an eLearning?"
You: "No — Job Aids. No interactivity or assessments."

EXAMPLE 14 - Department:
User: "Which department owns this?"
You: "Operations — internal process content, not sales."

EXAMPLE 15 - Multi-Field:
User: "Why is this underperforming?"
You: "Three issues: wrong audience (Indirect vs Direct), misaligned sales stage, unclear scrub reason. Want me to fix all three?"

EXAMPLE 16 - Action Proposal:
User: "Fix this record."
You: "Proposed changes:
- Bucket → Upskilling
- Status → Modify
- Reason → Unclear Intent
Confirm to apply."

EXAMPLE 17 - Confirmation:
User: "Yes, go ahead."
You: "Done — Bucket set to Upskilling, Status to Modify, Reason to Unclear Intent."

EXAMPLE 18 - Change Summary:
User: "What changed?"
You: "Bucket: Upskilling (was Onboarding), Status: Modify (was Not Reviewed), Reason: Unclear Intent (was empty)."

EXAMPLE 19 - Taxonomy:
User: "When should something be Onboarding vs Upskilling?"
You: "Onboarding = new-hire fundamentals, assumes no prior knowledge. Upskilling = performance improvement, assumes experience. If it assumes prior knowledge, it's Upskilling."

EXAMPLE 20 - Catalog Health:
User: "What's our biggest issue right now?"
You: "Overloaded Onboarding — 46% marked Modify, only 22% confirmed Include. Advanced content is diluting new-hire clarity. Want to see the highest-priority items?"
"""


# OpenAI function definitions for structured actions
CHAT_FUNCTIONS = [
    {
        "name": "query_resources",
        "description": "Search or count training resources based on criteria. Use this for any read-only question about the data.",
        "parameters": {
            "type": "object",
            "properties": {
                "filters": {
                    "type": "object",
                    "description": "Filters to apply",
                    "properties": {
                        "bucket": {"type": "string", "description": "e.g., Onboarding, Upskilling"},
                        "scrub_status": {"type": "string", "enum": ["not_reviewed", "Include", "Modify", "Sunset"]},
                        "audience": {"type": "string"},
                        "has_audience": {"type": "boolean", "description": "True = has audience, False = missing"},
                        "primary_department": {"type": "string"},
                        "sales_stage": {"type": "string", "description": "Filter by sales stage. Valid keys: stage_1_identify, stage_2_appointment, stage_3_prep, stage_4_make_sale, stage_5_close, stage_6_referrals. Also accepts shorthand like 'close', 'identify', 'appointment', 'prep', 'make the sale', 'referrals'.", "enum": ["stage_1_identify", "stage_2_appointment", "stage_3_prep", "stage_4_make_sale", "stage_5_close", "stage_6_referrals"]},
                        "has_sales_stage": {"type": "boolean", "description": "True = has sales stage assigned, False = no sales stage"},
                        "has_scrub_reason": {"type": "boolean", "description": "True = has scrub reason, False = no scrub reason"},
                        "has_invest_decision": {"type": "boolean", "description": "True = has investment decision, False = no investment decision"},
                        "has_training_type": {"type": "boolean", "description": "True = has training type, False = no training type"},
                        "training_type": {"type": "string", "description": "Filter by training type: job_aids, video_on_demand, self_directed, instructor_led_virtual, instructor_led_in_person, resources. Also accepts 'Job Aids', 'Video On Demand' etc."},
                        "has_owner": {"type": "boolean", "description": "True = has scrub owner assigned, False = unowned"},
                        "search_text": {"type": "string", "description": "Search in display_name (use for keyword searches)"},
                    }
                },
                "return_type": {
                    "type": "string",
                    "enum": ["count", "list", "summary"],
                    "description": "What to return: count (just the number), list (show items), summary (grouped stats)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max items to return for list (default 10)"
                },
                "group_by": {
                    "type": "string",
                    "enum": ["scrub_status", "bucket", "audience", "primary_department", "training_type", "sales_stage", "invest_decision"],
                    "description": "For 'summary' return type: group results by this field instead of scrub_status"
                }
            },
            "required": ["return_type"]
        }
    },
    {
        "name": "prepare_scrub_update",
        "description": "Prepare to update scrubbing fields (status, owner, notes, audience). This stages the change for user confirmation.",
        "parameters": {
            "type": "object",
            "properties": {
                "resource_keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of resource_key values to update"
                },
                "filter_criteria": {
                    "type": "object",
                    "description": "Alternative: specify filter instead of explicit keys",
                    "properties": {
                        "bucket": {"type": "string"},
                        "scrub_status": {"type": "string"},
                        "has_audience": {"type": "boolean"},
                    }
                },
                "updates": {
                    "type": "object",
                    "properties": {
                        "scrub_status": {"type": "string", "enum": ["Include", "Modify", "Sunset"]},
                        "scrub_owner": {"type": "string"},
                        "scrub_notes": {"type": "string"},
                        "audience": {"type": "string"},
                    }
                }
            },
            "required": ["updates"]
        }
    },
    {
        "name": "prepare_invest_update",
        "description": "Prepare to update investment fields. Stages change for confirmation.",
        "parameters": {
            "type": "object",
            "properties": {
                "resource_keys": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "updates": {
                    "type": "object",
                    "properties": {
                        "invest_decision": {"type": "string"},
                        "invest_owner": {"type": "string"},
                        "invest_effort": {"type": "string"},
                        "invest_notes": {"type": "string"},
                    }
                }
            },
            "required": ["resource_keys", "updates"]
        }
    },
    {
        "name": "prepare_sales_stage_update",
        "description": "Prepare to update sales stage. Stages change for confirmation.",
        "parameters": {
            "type": "object",
            "properties": {
                "resource_keys": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "sales_stage": {
                    "type": "string",
                    "description": "One of the 6 sales stage keys"
                }
            },
            "required": ["resource_keys", "sales_stage"]
        }
    },
    # =========================================================================
    # STRATEGIC ADVISOR TOOLS
    # =========================================================================

    {
        "name": "get_high_risk_areas",
        "description": "Identify highest-risk areas in the catalog based on unreviewed count, unowned resources, and duplicates.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of risk areas to return (default 5)"
                }
            }
        }
    },
    {
        "name": "get_blocking_factors",
        "description": "Identify what's blocking progress (unowned resources, stalled items, etc).",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "estimate_effort",
        "description": "Estimate hours needed to address resources based on their scrub status.",
        "parameters": {
            "type": "object",
            "properties": {
                "filter_criteria": {
                    "type": "object",
                    "description": "Filters to select resources",
                    "properties": {
                        "bucket": {"type": "string"},
                        "primary_department": {"type": "string"},
                        "scrub_status": {"type": "string"}
                    }
                }
            }
        }
    },
    {
        "name": "get_priority_items",
        "description": "Get top items to review prioritized by risk and impact. Use when user has limited time.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of items to return (default 10)"
                },
                "focus_area": {
                    "type": "string",
                    "enum": ["unreviewed", "unowned", "onboarding", "modify"],
                    "description": "What to prioritize"
                }
            }
        }
    },
    {
        "name": "check_investment_alignment",
        "description": "Analyze if investment effort is allocated to the right areas. Compares where Modify items are vs where audience is.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_quick_wins",
        "description": "Find actions that provide immediate visible progress with minimal effort (e.g., sunset flagged items).",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_status_breakdown",
        "description": "Get detailed breakdown of resources by status for a specific bucket or department.",
        "parameters": {
            "type": "object",
            "properties": {
                "bucket": {"type": "string", "description": "Filter by bucket (Onboarding, Upskilling)"},
                "primary_department": {"type": "string", "description": "Filter by department"}
            }
        }
    },
    {
        "name": "continue_list",
        "description": "Continue showing more results from the previous query. Use when user says 'continue', 'show more', 'next', 'more'.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "explain_taxonomy",
        "description": "Explain a TCM taxonomy field, its valid values, and when to use it. Use this when user asks about field meanings, valid values, or classification rules.",
        "parameters": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "enum": ["bucket", "audience", "scrub_status", "scrub_reason", 
                             "sales_stage", "invest_decision", "invest_effort", 
                             "invest_cost", "training_type", "primary_department"],
                    "description": "Which taxonomy field to explain"
                }
            },
            "required": ["field"]
        }
    }
]


class ChatService:
    """Service for handling TCM chat interactions with OpenAI."""
    
    def __init__(self, user_id: int, username: str):
        self.user_id = user_id
        self.username = username
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        self.client = OpenAI(api_key=api_key)
        
        # Dynamic enum injection: query actual DB values for LLM schema constraints
        import copy
        self._functions = copy.deepcopy(CHAT_FUNCTIONS)
        try:
            depts = db.execute(
                "SELECT DISTINCT primary_department FROM resources WHERE is_archived=0 AND primary_department IS NOT NULL AND primary_department != ''",
                fetch="all"
            )
            auds = db.execute(
                "SELECT DISTINCT audience FROM resources WHERE is_archived=0 AND audience IS NOT NULL AND audience != ''",
                fetch="all"
            )
            self._dept_values = [r['primary_department'] for r in depts] if depts else []
            self._audience_values = [r['audience'] for r in auds] if auds else []
            
            # Walk schema tree and inject enum into FILTER contexts only (not updates)
            for func in self._functions:
                self._inject_enum_into_schema(func.get('parameters', {}), is_update_context=False)
        except Exception as e:
            logger.warning(f"Failed to load enum values for chat schema: {e}")
            self._dept_values = []
            self._audience_values = []
            self._functions = copy.deepcopy(CHAT_FUNCTIONS)
    
    def _inject_enum_into_schema(self, schema: dict, is_update_context: bool = False):
        """Recursively inject enum values into schema for primary_department and audience fields.
        Skips injection inside 'updates' blocks to allow setting new values."""
        if not isinstance(schema, dict):
            return
        props = schema.get('properties', {})
        for key, value in props.items():
            if key == 'updates':
                # Don't inject enums into update contexts — users need to set new values
                self._inject_enum_into_schema(value, is_update_context=True)
                continue
            if key == 'primary_department' and not is_update_context and self._dept_values:
                value['enum'] = self._dept_values
            elif key == 'audience' and not is_update_context and self._audience_values:
                value['enum'] = self._audience_values
            elif isinstance(value, dict) and 'properties' in value:
                self._inject_enum_into_schema(value, is_update_context=is_update_context)
    
    def _get_live_data_snapshot(self) -> str:
        """Get current data snapshot for prompt injection."""
        try:
            totals = db.get_resource_totals()
            rollups = db.get_scrub_rollups()
            
            # Count unowned resources
            unowned = db.execute(
                """SELECT COUNT(*) as cnt FROM resources 
                   WHERE is_archived = 0 AND is_placeholder = 0 
                   AND (scrub_owner IS NULL OR scrub_owner = '')""",
                fetch="one"
            )
            unowned_count = unowned['cnt'] if unowned else 0
            
            # Build snapshot
            total = totals.get('total_containers', 0)
            reviewed = totals.get('reviewed_containers', 0)
            pct = totals.get('scrubbing_pct', 0)
            
            # Get status breakdown
            by_status = rollups.get('by_decision', {})
            include_count = by_status.get('Include', {}).get('count', 0)
            modify_count = by_status.get('Modify', {}).get('count', 0)
            sunset_count = by_status.get('Sunset', {}).get('count', 0)
            unreviewed_count = by_status.get('not_reviewed', {}).get('count', 0)
            
            # Distinct departments and audiences for LLM context
            dept_str = ', '.join(self._dept_values) if self._dept_values else 'None'
            aud_str = ', '.join(self._audience_values) if self._audience_values else 'None'
            
            return f"""- Total resources: {total:,}
- Onboarding: {totals.get('onboarding', 0):,} | Upskilling: {totals.get('upskilling', 0):,}
- By status: Include={include_count}, Modify={modify_count}, Sunset={sunset_count}, Unreviewed={unreviewed_count}
- Reviewed: {reviewed} ({pct:.1f}%)
- Unowned resources: {unowned_count}
- Investment queue: {totals.get('investment_queue', 0)}
- Departments: {dept_str}
- Audiences: {aud_str}"""
        except Exception as e:
            logger.warning(f"Failed to get live snapshot: {e}")
            return "- Live data unavailable"
    
    def send_message(
        self, 
        message: str, 
        conversation_id: int,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process a user message and return response.
        
        Args:
            message: User's message text
            conversation_id: ID of current conversation
            context: Page context (current_page, filters, selected_resources)
        
        Returns:
            {
                'response': str,
                'action_pending': bool,
                'action_preview': dict | None,
                'conversation_id': int,
            }
        """
        # Rate limit check
        if not self._check_rate_limit():
            return {
                'response': "You're sending messages pretty fast! Give me a sec and try again.",
                'action_pending': False,
                'action_preview': None,
                'conversation_id': conversation_id,
            }
        
        # Save user message
        _save_message(conversation_id, 'user', message)
        
        # Auto-title: Set title from first user message if still "New conversation"
        conv_info = db.execute(
            "SELECT title FROM chat_conversations WHERE conversation_id = ?",
            (conversation_id,), fetch="one"
        )
        if conv_info and conv_info.get('title') == 'New conversation':
            new_title = message[:50] + ('...' if len(message) > 50 else '')
            update_conversation_title(conversation_id, new_title)
        
        # Check if this is a confirmation of pending action
        pending = get_pending_action(self.user_id)
        if pending and self._is_confirmation(message):
            return self._execute_pending_action(conversation_id, pending)
        
        if pending and self._is_cancellation(message):
            clear_pending_action(self.user_id)
            response = "No problem, cancelled that. What else can I help with?"
            _save_message(conversation_id, 'assistant', response)
            return {
                'response': response, 
                'action_pending': False, 
                'action_preview': None,
                'conversation_id': conversation_id,
            }
        
        # Build conversation history for context
        history = _get_conversation_history(conversation_id, limit=20)
        
        # Inject stored query context into selected_resources for follow-up support
        query_ctx = get_query_context(conversation_id)
        if query_ctx and query_ctx.get('resource_keys'):
            context['selected_resources'] = query_ctx['resource_keys'][:100]
        
        # Call OpenAI with function calling
        try:
            result = self._call_openai(message, history, context, conversation_id)
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            response = "Something went wrong on my end. Mind trying that again?"
            _save_message(conversation_id, 'assistant', response)
            return {
                'response': response,
                'action_pending': False,
                'action_preview': None,
                'conversation_id': conversation_id,
            }
        
        _save_message(conversation_id, 'assistant', result['response'], 
                     metadata=result.get('metadata'))
        
        return {
            'response': result['response'],
            'action_pending': result.get('action_pending', False),
            'action_preview': result.get('action_preview'),
            'conversation_id': conversation_id,
        }
    
    def _call_openai(self, message: str, history: List[Dict], context: Dict, conv_id: int) -> Dict:
        """Call OpenAI with selective two-pass function calling.
        
        Architecture:
        - Pass 1: LLM decides which function to call (or responds directly)
        - Pass 2 (selective): For data-rich handlers (list, summary), send raw data
          back to LLM so it can formulate a natural response from real data.
          Simple handlers (count, confirmations, strategic advisors) return directly.
        
        Cost optimizations:
        - Prompt caching: stable system prefix separated from dynamic context
        - History cap: last MAX_HISTORY_PAIRS exchanges only
        - Selective two-pass: only for handlers that return rich per-resource data
        """
        # Build context-aware system prompt with gold examples and live data
        live_snapshot = self._get_live_data_snapshot()
        
        # Load previous query context for follow-up support
        query_ctx = get_query_context(conv_id)
        query_ctx_block = ""
        if query_ctx:
            resource_keys = query_ctx.get('resource_keys', [])
            keys_preview = resource_keys[:20] if resource_keys else []
            keys_display = json.dumps(keys_preview) if keys_preview else "None"
            filters_display = json.dumps(query_ctx.get('filters', {})) if query_ctx.get('filters') else query_ctx.get('query', 'N/A')
            query_ctx_block = f"""
PREVIOUS QUERY CONTEXT (for follow-ups like "those", "them", "set these"):
- Type: {query_ctx.get('type', 'query')}
- Filters/Query: {filters_display}
- Count: {query_ctx.get('count', 0)}
- Resource keys (first 20): {keys_display}

CRITICAL FOLLOW-UP RULE: When user says "set those/them/these to X", you MUST pass these resource_keys to prepare_scrub_update. Do NOT call with empty resource_keys if keys are available above.
"""
        
        # PROMPT CACHING: Stable prefix (cached at 10x cheaper) + dynamic suffix
        stable_prefix = SYSTEM_PROMPT + "\n" + GOLD_EXAMPLES
        dynamic_context = f"""
{query_ctx_block}
LIVE DATA SNAPSHOT (current state):
{live_snapshot}

CURRENT CONTEXT:
- Page: {context.get('current_page', 'unknown')}
- Active filters: {json.dumps(context.get('filters', {}))}
- Selected resources: {context.get('selected_resources', [])}
- User: {self.username}
"""
        
        # HISTORY CAP: Limit conversation history to control input token cost
        trimmed_history = history
        if len(history) > MAX_HISTORY_PAIRS * 2:
            trimmed_history = history[-(MAX_HISTORY_PAIRS * 2):]
        
        messages = [
            {"role": "system", "content": stable_prefix},   # Cached after first call
            {"role": "system", "content": dynamic_context},  # Fresh each call
        ]
        messages.extend(trimmed_history)
        messages.append({"role": "user", "content": message})
        
        # Pass 1: LLM decides what to do
        response = self.client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=[{"type": "function", "function": f} for f in self._functions],
            tool_choice="auto",
            temperature=0.3,
            max_completion_tokens=800,
        )
        
        # Log usage for Pass 1
        self._log_usage(response, conv_id, 'pass_1')
        
        response_message = response.choices[0].message
        
        # Check if model wants to call a function
        if response_message.tool_calls:
            tool_call = response_message.tool_calls[0]
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            # Execute the function handler
            result = self._execute_function(function_name, function_args, context, conv_id)
            
            # SELECTIVE TWO-PASS: Only for data-rich handlers
            return_type = function_args.get('return_type', '')
            needs_two_pass = (
                function_name in TWO_PASS_HANDLERS and 
                return_type in TWO_PASS_RETURN_TYPES
            ) or function_name == 'continue_list'
            
            if needs_two_pass and result.get('data'):
                # Pass 2: Send raw data back to LLM for natural language response
                # Include formatting instructions to keep output compact
                pass2_payload = {
                    'formatting': (
                        'Present results compactly. For resource lists: '
                        'start with a 1-line count (e.g. "2 resources in Ask for Appointment:"), '
                        'then each resource as: numbered name on line 1, '
                        'status | audience | bucket on an indented line 2. '
                        'End with 1-2 sentence recommendation if actionable. '
                        'Never show resource_key values. '
                        'Do not echo the user\'s question back. '
                        'Use **bold** for key labels and counts. Do not use markdown headers. '
                        'Always call them "resources" (never "materials", "items", "courses"). '
                        'Keep recommendations professional and brief — no editorializing. '
                        'For breakdowns: use simple "label: count" lines.'
                    ),
                    'data': result['data']
                }
                messages.append(response_message)  # Assistant's function call
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(pass2_payload, default=str)
                })
                
                final_response = self.client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    temperature=0.3,
                    max_completion_tokens=1000,
                )
                
                # Log usage for Pass 2
                self._log_usage(final_response, conv_id, 'pass_2')
                
                response_text = final_response.choices[0].message.content
                response_text = self._enforce_formatting(response_text)
                
                # Preserve metadata from handler (resource_keys, query context, etc.)
                final_result = {'response': response_text}
                if result.get('metadata'):
                    final_result['metadata'] = result['metadata']
                if result.get('pending_action'):
                    final_result['pending_action'] = result['pending_action']
                return final_result
            
            # Single-pass: handler already formatted the response
            return result
        
        # Plain text response (no function call)
        response_text = response_message.content or "I'm not sure how to help with that."
        return {'response': self._enforce_formatting(response_text)}
    
    def _execute_function(self, name: str, args: Dict, context: Dict, conv_id: int) -> Dict:
        """Execute a function call from OpenAI."""
        
        if name == "query_resources":
            return self._handle_query(args, conv_id)
        
        elif name == "prepare_scrub_update":
            return self._prepare_scrub_update(args, context, conv_id)
        
        elif name == "prepare_invest_update":
            return self._prepare_invest_update(args, context, conv_id)
        
        elif name == "prepare_sales_stage_update":
            return self._prepare_sales_stage_update(args, context, conv_id)
        
        # Strategic advisor tools

        elif name == "get_high_risk_areas":
            return self._handle_high_risk_areas(args)
        
        elif name == "get_blocking_factors":
            return self._handle_blocking_factors(args)
        
        elif name == "estimate_effort":
            return self._handle_estimate_effort(args)
        
        elif name == "get_priority_items":
            return self._handle_priority_items(args, conv_id)
        
        elif name == "check_investment_alignment":
            return self._handle_investment_alignment(args)
        
        elif name == "get_quick_wins":
            return self._handle_quick_wins(args)
        
        elif name == "get_status_breakdown":
            return self._handle_status_breakdown(args)
        
        elif name == "continue_list":
            return self._handle_continue_list(args, conv_id)
        
        elif name == "explain_taxonomy":
            return self._handle_explain_taxonomy(args)
        
        return {'response': "I'm not sure how to do that."}
    
    def _enforce_formatting(self, text: str) -> str:
        """Server-side formatting enforcement.
        
        Strips markdown formatting the LLM might add despite prompt instructions.
        Bold (**text**) is kept — the frontend renders it as <strong>.
        """
        import re
        # Remove markdown headers: ## Header → Header
        text = re.sub(r'^#{1,3}\s+', '', text, flags=re.MULTILINE)
        # Remove arrow symbols that leak from old prompts
        text = text.replace(' → ', ' - ')
        return text
    
    def _log_usage(self, response, conv_id: int, call_type: str):
        """Log OpenAI API usage for cost tracking.
        
        Captures prompt_tokens, completion_tokens, and estimated cost
        from the API response and stores to ai_usage_log table.
        """
        try:
            if not hasattr(response, 'usage') or not response.usage:
                return
            
            usage = response.usage
            prompt_tokens = usage.prompt_tokens or 0
            completion_tokens = usage.completion_tokens or 0
            
            # GPT-5.2 pricing per million tokens
            input_rate = 1.75 / 1_000_000
            output_rate = 14.00 / 1_000_000
            estimated_cost = (prompt_tokens * input_rate) + (completion_tokens * output_rate)
            
            db.log_ai_usage(
                user_id=self.user_id,
                username=self.username,
                conversation_id=conv_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model=MODEL,
                call_type=call_type,
                estimated_cost=estimated_cost
            )
        except Exception as e:
            logger.warning(f"Failed to log AI usage: {e}")
    
    def _handle_query(self, args: Dict, conv_id: int) -> Dict:
        """Handle a query_resources function call."""
        filters = args.get('filters', {})
        return_type = args.get('return_type', 'count')
        limit = args.get('limit', 10)
        
        # FILTER INHERITANCE: If no filters specified and we have previous context, inherit filters
        # This handles "break down by department" after "show me job aids"
        if not filters and return_type == 'summary':
            query_ctx = get_query_context(conv_id)
            if query_ctx and query_ctx.get('filters'):
                filters = query_ctx['filters']
        
        # Build WHERE clause
        conditions = ["is_archived = 0", "is_placeholder = 0"]
        params = []
        
        if filters.get('bucket'):
            conditions.append("LOWER(bucket) = LOWER(?)")
            params.append(filters['bucket'])
        
        if filters.get('scrub_status'):
            conditions.append("scrub_status = ?")
            params.append(filters['scrub_status'])
        
        if filters.get('audience'):
            conditions.append("LOWER(audience) LIKE LOWER(?)")
            params.append(f"%{filters['audience']}%")
        
        if filters.get('has_audience') is False:
            conditions.append("(audience IS NULL OR audience = '')")
        elif filters.get('has_audience') is True:
            conditions.append("audience IS NOT NULL AND audience != ''")
        
        if filters.get('primary_department'):
            conditions.append("LOWER(primary_department) LIKE LOWER(?)")
            params.append(f"%{filters['primary_department']}%")
        
        # Sales stage filter
        if filters.get('sales_stage'):
            raw_stage = filters['sales_stage'].lower().strip()
            # Normalize common user inputs to database keys
            stage_map = {
                'identify': 'stage_1_identify', 'identify the customer': 'stage_1_identify', '1': 'stage_1_identify',
                'appointment': 'stage_2_appointment', 'ask for appointment': 'stage_2_appointment', '2': 'stage_2_appointment',
                'prep': 'stage_3_prep', 'prep for appointment': 'stage_3_prep', '3': 'stage_3_prep',
                'make the sale': 'stage_4_make_sale', 'make sale': 'stage_4_make_sale', '4': 'stage_4_make_sale',
                'close': 'stage_5_close', 'close the sale': 'stage_5_close', '5': 'stage_5_close',
                'referrals': 'stage_6_referrals', 'ask for referrals': 'stage_6_referrals', '6': 'stage_6_referrals',
            }
            # Also accept the raw keys directly
            for key in SALES_STAGE_KEYS:
                stage_map[key] = key
            normalized = stage_map.get(raw_stage, filters['sales_stage'])
            conditions.append("sales_stage = ?")
            params.append(normalized)
        
        # Has/missing filters for all major fields
        if filters.get('has_sales_stage') is True:
            conditions.append("(sales_stage IS NOT NULL AND sales_stage != '')")
        elif filters.get('has_sales_stage') is False:
            conditions.append("(sales_stage IS NULL OR sales_stage = '')")
        
        if filters.get('has_scrub_reason') is True:
            conditions.append("(scrub_reasons IS NOT NULL AND scrub_reasons != '')")
        elif filters.get('has_scrub_reason') is False:
            conditions.append("(scrub_reasons IS NULL OR scrub_reasons = '')")
        
        if filters.get('has_invest_decision') is True:
            conditions.append("(invest_decision IS NOT NULL AND invest_decision != '')")
        elif filters.get('has_invest_decision') is False:
            conditions.append("(invest_decision IS NULL OR invest_decision = '')")
        
        if filters.get('has_training_type') is True:
            conditions.append("(training_type IS NOT NULL AND training_type != '')")
        elif filters.get('has_training_type') is False:
            conditions.append("(training_type IS NULL OR training_type = '')")
        
        # Training type value filter (with user-friendly normalization)
        if filters.get('training_type'):
            raw_type = filters['training_type'].lower().strip()
            # Normalize common user inputs to database keys
            type_map = {
                'job aids': 'job_aids', 'job aid': 'job_aids', 'job_aids': 'job_aids',
                'video on demand': 'video_on_demand', 'video': 'video_on_demand', 'video_on_demand': 'video_on_demand',
                'self directed': 'self_directed', 'self-directed': 'self_directed', 'self_directed': 'self_directed',
                'instructor led virtual': 'instructor_led_virtual', 'virtual': 'instructor_led_virtual', 'instructor_led_virtual': 'instructor_led_virtual',
                'instructor led in person': 'instructor_led_in_person', 'in person': 'instructor_led_in_person', 'instructor_led_in_person': 'instructor_led_in_person',
                'resources': 'resources', 'resource': 'resources',
            }
            normalized = type_map.get(raw_type.replace('-', ' ').replace('_', ' '), raw_type.replace(' ', '_'))
            conditions.append("training_type = ?")
            params.append(normalized)
        
        if filters.get('has_owner') is True:
            conditions.append("(scrub_owner IS NOT NULL AND scrub_owner != '')")
        elif filters.get('has_owner') is False:
            conditions.append("(scrub_owner IS NULL OR scrub_owner = '')")
        
        # Text search in display_name
        if filters.get('search_text'):
            conditions.append("LOWER(display_name) LIKE LOWER(?)")
            params.append(f"%{filters['search_text']}%")
        
        where_clause = " AND ".join(conditions)
        
        if return_type == 'count':
            result = db.execute(
                f"SELECT COUNT(*) as cnt FROM resources WHERE {where_clause}",
                tuple(params), fetch="one"
            )
            count = result['cnt'] if result else 0
            
            # Get total for percentage calculation
            total_result = db.execute(
                "SELECT COUNT(*) as cnt FROM resources WHERE is_archived = 0 AND is_placeholder = 0",
                fetch="one"
            )
            total = total_result['cnt'] if total_result else 1
            
            # Build natural response
            type_label = self._get_type_label(filters)
            if count == 0 and (filters.get('primary_department') or filters.get('audience')):
                # Auto-retry with fuzzy matching before reporting 0
                fuzzy_conds = [c for c in conditions]
                fuzzy_params = [p for p in params]
                for i, cond in enumerate(fuzzy_conds):
                    if 'LIKE LOWER' not in cond and 'primary_department' in cond:
                        fuzzy_conds[i] = "LOWER(primary_department) LIKE LOWER(?)"
                        fuzzy_params[i] = f"%{filters['primary_department']}%"
                    if 'LIKE LOWER' not in cond and 'audience' in cond:
                        fuzzy_conds[i] = "LOWER(audience) LIKE LOWER(?)"
                        fuzzy_params[i] = f"%{filters['audience']}%"
                fuzzy_where = ' AND '.join(fuzzy_conds)
                retry = db.execute(
                    f"SELECT COUNT(*) as cnt FROM resources WHERE {fuzzy_where}",
                    tuple(fuzzy_params), fetch="one"
                )
                if retry and retry['cnt'] > 0:
                    count = retry['cnt']
                    where_clause = fuzzy_where
                    params = fuzzy_params
            
            if count == 0:
                response = f"No {type_label} found."
            else:
                response = f"There are {count:,} {type_label} in the catalog."
            
            # Store context for follow-ups
            save_query_context(conv_id, {
                'type': 'query',
                'filters': filters,
                'count': count,
                'total_count': total,
                'resource_keys': None,
                'where_clause': where_clause,
                'params': list(params)
            })
            
            return {'response': response}
        
        elif return_type == 'list':
            # First get total count
            total_result = db.execute(
                f"SELECT COUNT(*) as cnt FROM resources WHERE {where_clause}",
                tuple(params), fetch="one"
            )
            total_matching = total_result['cnt'] if total_result else 0
            
            # Enforce hard limit of 10
            limit = min(limit, 10)
            
            results = db.execute(
                f"""SELECT resource_key, display_name, bucket, scrub_status, audience,
                            sales_stage, primary_department, training_type 
                    FROM resources WHERE {where_clause} LIMIT ?""",
                tuple(params) + (limit,), fetch="all"
            )
            
            if not results:
                type_label = self._get_type_label(filters)
                filter_desc = self._describe_filters(filters)
                return {'response': f"I didn't find any {type_label}{filter_desc}."}
            
            # Build display text (fallback for single-pass)
            items = []
            for r in results:
                name = self._clean_display_name(r['display_name'] or r['resource_key'])
                status = (r['scrub_status'] or 'Not reviewed').replace('not_reviewed', 'Not reviewed')
                parts = [f"- {name} \u2013 {status}"]
                if r.get('sales_stage'):
                    stage_label = SALES_STAGE_LABELS.get(r['sales_stage'], r['sales_stage'])
                    parts.append(f"[{stage_label}]")
                items.append(' '.join(parts))
            
            type_label = self._get_type_label(filters)
            response = f"Here are {type_label}.\nShowing {len(results)} of {total_matching}.\n\n" + "\n".join(items)
            
            remaining = total_matching - len(results)
            if remaining > 0:
                response += f"\n\nYou can say \"show more\" to see the rest."
            
            # Store context for follow-ups with pagination support
            save_query_context(conv_id, {
                'type': 'list',
                'filters': filters,
                'count': len(results),
                'total_count': total_matching,
                'offset': 0,
                'limit': limit,
                'resource_keys': [r['resource_key'] for r in results],
                'where_clause': where_clause,
                'params': list(params)
            })
            
            # Build structured data for two-pass LLM formatting
            resource_data = []
            for r in results:
                resource_data.append({
                    'name': self._clean_display_name(r['display_name'] or r['resource_key']),
                    'bucket': r['bucket'] or 'Unassigned',
                    'status': (r['scrub_status'] or 'Not reviewed').replace('not_reviewed', 'Not reviewed'),
                    'audience': r['audience'] or 'Unassigned',
                })
            
            return {
                'response': response,
                'data': {
                    'resources': resource_data,
                    'total_matching': total_matching,
                    'showing': len(results),
                    'filters_applied': filters,
                    'has_more': remaining > 0
                },
                'metadata': {'query_results': [dict(r) for r in results]}
            }
        
        elif return_type == 'summary':
            # Group by specified field (default: scrub_status)
            group_field = args.get('group_by', 'scrub_status')
            valid_group_fields = ['scrub_status', 'bucket', 'audience', 'primary_department', 
                                  'training_type', 'sales_stage', 'invest_decision']
            if group_field not in valid_group_fields:
                group_field = 'scrub_status'
            
            results = db.execute(
                f"""SELECT {group_field}, COUNT(*) as cnt 
                    FROM resources WHERE {where_clause}
                    GROUP BY {group_field}
                    ORDER BY cnt DESC""",
                tuple(params), fetch="all"
            )
            
            if not results:
                type_label = self._get_type_label(filters)
                return {'response': f"I didn't find any {type_label} to break down."}
            
            total = sum(r['cnt'] for r in results)
            field_label = group_field.replace('_', ' ').replace('scrub status', 'status')
            
            lines = [f"Here's the {field_label} breakdown:\n"]
            for r in results:
                value = self._format_enum_label(r[group_field], group_field)
                lines.append(f"- {value}: {r['cnt']:,}")
            
            # Build structured data for two-pass
            breakdown_data = []
            for r in results:
                value = self._format_enum_label(r[group_field], group_field)
                breakdown_data.append({'group': value, 'count': r['cnt']})
            
            return {
                'response': '\n'.join(lines),
                'data': {
                    'breakdown': breakdown_data,
                    'group_by': field_label,
                    'total': total,
                    'filters_applied': filters
                }
            }
        
        return {'response': "Not sure what you're looking for."}
    
    def _handle_continue_list(self, args: Dict, conv_id: int) -> Dict:
        """
        Handle continue_list function call for DB-driven pagination.
        Always queries the database for the next page - never fabricates data.
        """
        # Get stored context from previous query
        context = get_query_context(conv_id)
        
        if not context or context.get('type') != 'list':
            return {
                'response': "I don't have a list to continue. Please run a query first, "
                           "like 'show me unreviewed resources' or 'list resources in Onboarding'."
            }
        
        # Get pagination info from context
        where_clause = context.get('where_clause')
        params = context.get('params', [])
        offset = context.get('offset', 0)
        limit = context.get('limit', 10)
        total_count = context.get('total_count', 0)
        
        if not where_clause:
            return {'response': "I can't continue - the previous query context is incomplete."}
        
        # Calculate new offset
        new_offset = offset + limit
        
        if new_offset >= total_count:
            return {'response': f"That's all {total_count} resources! No more to show."}
        
        # Query database for next page (NEVER fabricate data)
        results = db.execute(
            f"""SELECT resource_key, display_name, bucket, scrub_status, audience,
                        sales_stage, primary_department, training_type 
                FROM resources WHERE {where_clause} 
                LIMIT ? OFFSET ?""",
            tuple(params) + (limit, new_offset), fetch="all"
        )
        
        if not results:
            return {'response': f"That's all! No more resources to show."}
        
        items = []
        for r in results:
            name = self._clean_display_name(r['display_name'] or r['resource_key'])
            status = (r['scrub_status'] or 'Not reviewed').replace('not_reviewed', 'Not reviewed')
            parts = [f"- {name} \u2013 {status}"]
            if r.get('sales_stage'):
                stage_label = SALES_STAGE_LABELS.get(r['sales_stage'], r['sales_stage'])
                parts.append(f"[{stage_label}]")
            items.append(' '.join(parts))
        
        # Show position in full list
        start_num = new_offset + 1
        end_num = new_offset + len(results)
        response = f"Showing {start_num}-{end_num} of {total_count}.\n\n" + "\n".join(items)
        
        remaining = total_count - end_num
        if remaining > 0:
            response += f"\n\nYou can say \"show more\" to see the rest."
        else:
            response += "\n\nThat's everything."
        
        # Update context with new offset
        save_query_context(conv_id, {
            **context,
            'offset': new_offset,
            'resource_keys': [r['resource_key'] for r in results]
        })
        
        # Build structured data for two-pass
        resource_data = []
        for r in results:
            resource_data.append({
                'name': self._clean_display_name(r['display_name'] or r['resource_key']),
                'bucket': r['bucket'] or 'Unassigned',
                'status': (r['scrub_status'] or 'Not reviewed').replace('not_reviewed', 'Not reviewed'),
                'audience': r['audience'] or 'Unassigned',
            })
        
        return {
            'response': response,
            'data': {
                'resources': resource_data,
                'showing_range': f"{start_num}-{end_num}",
                'total': total_count,
                'has_more': remaining > 0
            },
            'metadata': {'query_results': [dict(r) for r in results]}
        }
    
    def _handle_explain_taxonomy(self, args: Dict) -> Dict:
        """
        Explain a TCM taxonomy field with all valid values and usage guidance.
        Uses centralized taxonomy metadata from taxonomy.py.
        """
        field = args.get('field')
        
        # Get taxonomy fields lazily (enables dynamic departments)
        taxonomy_fields = get_taxonomy_fields()
        
        if not field or field not in taxonomy_fields:
            available = ', '.join(taxonomy_fields.keys())
            return {
                'response': f"I can explain these taxonomy fields: {available}\n\n"
                           "Ask me about any of these to learn what values are valid and how to use them."
            }
        
        info = taxonomy_fields[field]
        
        # Build response
        response = f"{info['name']}\n\n"
        response += f"{info['definition']}\n\n"
        response += "Valid values:\n"
        response += "\n".join(f"- {v}" for v in info['values'])
        response += f"\n\nRule: {info['rule']}"
        
        return {'response': response}
    
    # Known file extensions to strip from display names
    _STRIP_EXTENSIONS = {'.pdf', '.mp4', '.docx', '.doc', '.xlsx', '.xls', '.png', 
                         '.jpg', '.jpeg', '.gif', '.pptx', '.ppt', '.csv', '.txt',
                         '.zip', '.html', '.htm', '.mov', '.wmv', '.avi', '.mp3'}
    
    def _format_enum_label(self, value, field: str = '') -> str:
        """Convert raw enum/DB values to user-friendly labels.
        e.g. 'self_directed' -> 'Self Directed', 'not_reviewed' -> 'Not Reviewed'"""
        if not value:
            return 'Unassigned'
        # Sales stages have their own label map
        if field == 'sales_stage' and value in SALES_STAGE_LABELS:
            return SALES_STAGE_LABELS[value]
        # Generic: replace underscores, title case
        return value.replace('_', ' ').title()
    
    def _clean_display_name(self, name: str) -> str:
        """Strip known file extensions from display name.
        Only strips extensions from the known allowlist to avoid
        mangling names like 'oneServer 3.2'."""
        import os
        _, ext = os.path.splitext(name)
        if ext.lower() in self._STRIP_EXTENSIONS:
            return name[:-len(ext)]
        return name
    
    def _get_type_label(self, filters: Dict) -> str:
        """Get a human-friendly label for the current filter context.
        Returns things like 'job aids', 'self directed training', or 'resources'."""
        if filters.get('training_type'):
            return filters['training_type'].replace('_', ' ')
        if filters.get('bucket'):
            return f"{filters['bucket']} resources"
        if filters.get('primary_department'):
            return f"{filters['primary_department']} resources"
        return "resources"
    
    def _describe_filters(self, filters: Dict, verbose: bool = False) -> str:
        """
        Create human-readable filter description.
        
        Args:
            filters: Filter dictionary
            verbose: If True, show SQL-like logic for transparency
        """
        if not filters:
            return "" if not verbose else " (all active resources)"
        
        parts = []
        
        # Exact value filters
        if filters.get('bucket'):
            parts.append(f"in {filters['bucket']}" if not verbose else f"bucket='{filters['bucket']}'")
        if filters.get('scrub_status'):
            status = filters['scrub_status']
            parts.append(f"with status '{status}'" if not verbose else f"scrub_status='{status}'")
        if filters.get('audience'):
            parts.append(f"for {filters['audience']}" if not verbose else f"audience='{filters['audience']}'")
        if filters.get('primary_department'):
            parts.append(f"in {filters['primary_department']}" if not verbose else f"department='{filters['primary_department']}'")
        if filters.get('sales_stage'):
            parts.append(f"at {filters['sales_stage']}" if not verbose else f"sales_stage='{filters['sales_stage']}'")
        
        # Has/missing filters
        if filters.get('has_audience') is False:
            parts.append("without an audience" if not verbose else "audience IS NULL")
        elif filters.get('has_audience') is True:
            parts.append("with an audience" if not verbose else "audience IS NOT NULL")
        
        if filters.get('has_sales_stage') is True:
            parts.append("with a sales stage" if not verbose else "sales_stage IS NOT NULL")
        elif filters.get('has_sales_stage') is False:
            parts.append("without a sales stage" if not verbose else "sales_stage IS NULL")
        
        if filters.get('has_scrub_reason') is True:
            parts.append("with a scrub reason" if not verbose else "scrub_reasons IS NOT NULL")
        elif filters.get('has_scrub_reason') is False:
            parts.append("without a scrub reason" if not verbose else "scrub_reasons IS NULL")
        
        if filters.get('has_invest_decision') is True:
            parts.append("with an investment decision" if not verbose else "invest_decision IS NOT NULL")
        elif filters.get('has_invest_decision') is False:
            parts.append("without an investment decision" if not verbose else "invest_decision IS NULL")
        
        if filters.get('has_training_type') is True:
            parts.append("with a training type" if not verbose else "training_type IS NOT NULL")
        elif filters.get('has_training_type') is False:
            parts.append("without a training type" if not verbose else "training_type IS NULL")
        
        # Training type value filter
        if filters.get('training_type'):
            type_label = filters['training_type'].replace('_', ' ').title()
            parts.append(f"({type_label})" if not verbose else f"training_type='{filters['training_type']}'")
        
        if filters.get('has_owner') is True:
            parts.append("with an owner" if not verbose else "scrub_owner IS NOT NULL")
        elif filters.get('has_owner') is False:
            parts.append("without an owner" if not verbose else "scrub_owner IS NULL")
        
        # Search text
        if filters.get('search_text'):
            parts.append(f"matching '{filters['search_text']}'" if not verbose else f"display_name LIKE '%{filters['search_text']}%'")
        
        if not parts:
            return "" if not verbose else " (all active resources)"
        
        separator = " AND " if verbose else " "
        return " " + separator.join(parts)
    
    def _prepare_scrub_update(self, args: Dict, context: Dict, conv_id: int) -> Dict:
        """Prepare a scrub update and request confirmation."""
        updates = args.get('updates', {})
        resource_keys = args.get('resource_keys', [])
        filter_criteria = args.get('filter_criteria', {})
        
        # If no explicit keys, find them via filter
        if not resource_keys and filter_criteria:
            resource_keys = self._find_keys_by_filter(filter_criteria)
        
        # If still no keys, check context for selected resources
        if not resource_keys:
            resource_keys = context.get('selected_resources', [])
        
        # Auto-recovery: Last resort, check query_context directly
        if not resource_keys:
            query_ctx = get_query_context(conv_id)
            if query_ctx and query_ctx.get('resource_keys'):
                resource_keys = query_ctx['resource_keys'][:100]
                logger.info(f"Auto-recovered {len(resource_keys)} keys from query_context")
        
        if not resource_keys:
            return {'response': "I need to know which resources to update. Try 'show me X resources' first, then 'set those to Y'."}
        
        # Validate updates using centralized taxonomy validation
        is_valid, error_msg = validate_taxonomy_update(updates)
        if not is_valid:
            # Provide helpful suggestions based on the field
            field_match = None
            for field_name in ['audience', 'scrub_status', 'scrub_reason', 'sales_stage', 'bucket']:
                if field_name in error_msg.lower():
                    field_match = field_name
                    break
            
            if field_match:
                options = get_field_options(field_match)
                return {
                    'response': f"⚠️ {error_msg}\n\n**Valid {field_match.replace('_', ' ').title()} options:**\n" +
                               "\n".join(f"- {opt}" for opt in options)
                }
            return {'response': f"⚠️ {error_msg}"}
        
        # Get resource names for confirmation
        resources = self._get_resource_names(resource_keys)
        
        if not resources:
            return {'response': "Couldn't find those resources. They may have been archived."}
        
        # SMART GUARDRAILS: Analyze consequences
        existing_decisions = db.execute(
            f"""SELECT resource_key, scrub_status FROM resources 
               WHERE resource_key IN ({','.join(['%s']*len(resource_keys))})
               AND scrub_status != 'not_reviewed'""",
            tuple(resource_keys),
            fetch="all"
        )
        override_count = len(existing_decisions) if existing_decisions else 0
        safe_count = len(resource_keys) - override_count
        
        # Store pending action
        action = {
            'type': 'scrub',
            'resource_keys': resource_keys,
            'updates': updates,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        save_pending_action(self.user_id, action)
        
        # Build confirmation message
        update_desc = []
        if updates.get('scrub_status'):
            update_desc.append(f"status to '{updates['scrub_status']}'")
        if updates.get('audience'):
            update_desc.append(f"audience to '{updates['audience']}'")
        if updates.get('scrub_owner'):
            update_desc.append(f"owner to '{updates['scrub_owner']}'")
        if updates.get('scrub_notes'):
            update_desc.append(f"add notes")
        
        names = [r['display_name'] or r['resource_key'] for r in resources]
        names_preview = names[:10]
        more = len(names) - 10 if len(names) > 10 else 0
        
        # Build response with guardrails
        response = f"**Updating {', '.join(update_desc)}** for {len(names)} resource{'s' if len(names) != 1 else ''}:\n"
        
        # Add consequence warning if overriding existing decisions
        if override_count > 0 and updates.get('scrub_status'):
            response += f"\n⚠️ **Warning**: {override_count} resources already have decisions that would be overridden.\n"
            response += f"✓ {safe_count} are unreviewed (safe to update).\n\n"
            response += "Options:\n"
            response += f"1. Proceed with all {len(names)} resources\n"
            response += f"2. Apply only to the {safe_count} unreviewed items (safer)\n\n"
        else:
            response += "\n".join(f"- {n}" for n in names_preview)
            if more:
                response += f"\n- ...and {more} more"
            response += "\n\n"
        
        response += "Want me to go ahead?"
        
        return {
            'response': response,
            'action_pending': True,
            'action_preview': {
                'type': 'scrub_update',
                'count': len(names),
                'updates': updates,
                'override_count': override_count,
                'safe_count': safe_count,
            },
            'metadata': {'pending_action': action},
        }
    
    def _prepare_invest_update(self, args: Dict, context: Dict, conv_id: int) -> Dict:
        """Prepare an investment update."""
        # Similar structure to scrub update
        updates = args.get('updates', {})
        resource_keys = args.get('resource_keys', [])
        
        if not resource_keys:
            resource_keys = context.get('selected_resources', [])
        
        # Auto-recovery: Last resort, check query_context directly
        if not resource_keys:
            query_ctx = get_query_context(conv_id)
            if query_ctx and query_ctx.get('resource_keys'):
                resource_keys = query_ctx['resource_keys'][:100]
                logger.info(f"Auto-recovered {len(resource_keys)} keys from query_context")
        
        if not resource_keys:
            return {'response': "Which resources should I update? Try 'show me X resources' first, then 'set those to Y'."}
        
        resources = self._get_resource_names(resource_keys)
        if not resources:
            return {'response': "Couldn't find those resources."}
        
        action = {
            'type': 'invest',
            'resource_keys': resource_keys,
            'updates': updates,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        save_pending_action(self.user_id, action)
        
        names = [r['display_name'] or r['resource_key'] for r in resources]
        count = len(names)
        plural = "s" if count != 1 else ""
        response = f"I'll update investment fields for {count} resource{plural}. Go ahead?"
        
        return {
            'response': response,
            'action_pending': True,
            'action_preview': {'type': 'invest_update', 'count': len(names)},
        }
    
    def _prepare_sales_stage_update(self, args: Dict, context: Dict, conv_id: int) -> Dict:
        """Prepare a sales stage update."""
        resource_keys = args.get('resource_keys', [])
        sales_stage = args.get('sales_stage')
        
        if not resource_keys:
            resource_keys = context.get('selected_resources', [])
        
        # Auto-recovery: Last resort, check query_context directly
        if not resource_keys:
            query_ctx = get_query_context(conv_id)
            if query_ctx and query_ctx.get('resource_keys'):
                resource_keys = query_ctx['resource_keys'][:100]
                logger.info(f"Auto-recovered {len(resource_keys)} keys from query_context")
        
        if not resource_keys:
            return {'response': "Which resources should I update? Try 'show me X resources' first, then 'set those to Y'."}
        
        if sales_stage not in SALES_STAGE_KEYS:
            return {'response': f"'{sales_stage}' isn't a valid sales stage."}
        
        resources = self._get_resource_names(resource_keys)
        if not resources:
            return {'response': "Couldn't find those resources."}
        
        action = {
            'type': 'sales_stage',
            'resource_keys': resource_keys,
            'updates': {'sales_stage': sales_stage},
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        save_pending_action(self.user_id, action)
        
        stage_label = SALES_STAGE_LABELS.get(sales_stage, sales_stage)
        response = f"I'll set sales stage to '{stage_label}' for {len(resources)} resource{'s' if len(resources) != 1 else ''}. Go ahead?"
        
        return {
            'response': response,
            'action_pending': True,
            'action_preview': {'type': 'sales_stage_update', 'count': len(resources)},
        }
    
    # =========================================================================
    # STRATEGIC ADVISOR HANDLERS
    # =========================================================================
    

    def _handle_high_risk_areas(self, args: Dict) -> Dict:
        """Identify highest-risk areas based on unreviewed and unowned resources."""
        limit = args.get('limit', 5)
        
        # Risk = unreviewed count * 3 + unowned count * 2
        risk_data = db.execute(
            """SELECT 
                bucket,
                primary_department,
                COUNT(*) as total,
                SUM(CASE WHEN scrub_status = 'not_reviewed' THEN 1 ELSE 0 END) as unreviewed,
                SUM(CASE WHEN scrub_owner IS NULL OR scrub_owner = '' THEN 1 ELSE 0 END) as unowned
               FROM resources
               WHERE is_archived = 0 AND is_placeholder = 0
               GROUP BY bucket, primary_department
               HAVING SUM(CASE WHEN scrub_status = 'not_reviewed' THEN 1 ELSE 0 END) > 0
                   OR SUM(CASE WHEN scrub_owner IS NULL OR scrub_owner = '' THEN 1 ELSE 0 END) > 0
               ORDER BY 
                   (SUM(CASE WHEN scrub_status = 'not_reviewed' THEN 1 ELSE 0 END) * 3 +
                    SUM(CASE WHEN scrub_owner IS NULL OR scrub_owner = '' THEN 1 ELSE 0 END) * 2) DESC
               LIMIT %s""",
            (limit,),
            fetch="all"
        )
        
        if not risk_data:
            return {'response': "No high-risk areas found. Great job!"}
        
        response = f"Top {len(risk_data)} highest-risk areas:\n\n"
        
        for i, area in enumerate(risk_data, 1):
            bucket = area['bucket'] or 'Unknown'
            dept = area['primary_department'] or 'Not Categorized'
            
            response += f"{i}. {bucket} - {dept}\n"
            response += f"   {area['unreviewed']} unreviewed, {area['unowned']} unowned\n"
        
        response += f"\nFocus on the top area first."
        
        return {'response': response}
    
    def _handle_blocking_factors(self, args: Dict) -> Dict:
        """Identify what's blocking progress."""
        # Get unowned resources
        unowned = db.execute(
            """SELECT COUNT(*) as cnt FROM resources 
               WHERE is_archived = 0 AND is_placeholder = 0 
               AND (scrub_owner IS NULL OR scrub_owner = '')""",
            fetch="one"
        )
        unowned_count = unowned['cnt'] if unowned else 0
        
        # Get unreviewed resources
        unreviewed = db.execute(
            """SELECT COUNT(*) as cnt FROM resources 
               WHERE is_archived = 0 AND is_placeholder = 0 
               AND scrub_status = 'not_reviewed'""",
            fetch="one"
        )
        unreviewed_count = unreviewed['cnt'] if unreviewed else 0
        
        # Get total
        total = db.execute(
            """SELECT COUNT(*) as cnt FROM resources 
               WHERE is_archived = 0 AND is_placeholder = 0""",
            fetch="one"
        )
        total_count = total['cnt'] if total else 1
        
        # Build response
        blockers = []
        
        if unowned_count > 0:
            pct = (unowned_count / total_count) * 100
            blockers.append({
                'issue': 'Unowned resources',
                'count': unowned_count,
                'pct': pct,
                'fix': 'Assign owners to unblock decisions'
            })
        
        if unreviewed_count > 0:
            pct = (unreviewed_count / total_count) * 100
            blockers.append({
                'issue': 'Unreviewed resources',
                'count': unreviewed_count,
                'pct': pct,
                'fix': 'Complete scrubbing review'
            })
        
        if not blockers:
            return {'response': "No major blocking factors identified. Progress is clear!"}
        
        # Sort by count descending
        blockers.sort(key=lambda x: x['count'], reverse=True)
        
        response = "Blocking factors, sorted by impact:\n\n"
        
        for b in blockers:
            response += f"- {b['issue']}: {b['count']:,}\n"
            response += f"  Fix: {b['fix']}\n\n"
        
        response += f"Addressing {blockers[0]['issue'].lower()} is the fastest way to unblock progress."
        
        return {'response': response}
    
    def _handle_estimate_effort(self, args: Dict) -> Dict:
        """Estimate hours needed based on scrub status."""
        filters = args.get('filter_criteria', {})
        
        # Build WHERE clause
        where_clauses = ["is_archived = 0", "is_placeholder = 0"]
        params = []
        
        if filters.get('bucket'):
            where_clauses.append("bucket = %s")
            params.append(filters['bucket'])
        
        if filters.get('primary_department'):
            where_clauses.append("LOWER(primary_department) LIKE LOWER(%s)")
            params.append(f"%{filters['primary_department']}%")
        
        if filters.get('scrub_status'):
            where_clauses.append("scrub_status = %s")
            params.append(filters['scrub_status'])
        
        where_sql = " AND ".join(where_clauses)
        
        # Get counts by status
        results = db.execute(
            f"""SELECT scrub_status, COUNT(*) as cnt
               FROM resources
               WHERE {where_sql}
               GROUP BY scrub_status""",
            tuple(params) if params else None,
            fetch="all"
        )
        
        if not results:
            return {'response': "No resources found matching those criteria."}
        
        # Calculate effort
        total_hours = 0
        breakdown = []
        total_resources = 0
        
        for row in results:
            raw_status = row['scrub_status'] or 'not_reviewed'
            display_status = self._format_enum_label(raw_status, 'scrub_status')
            count = row['cnt']
            total_resources += count
            hours = count * EFFORT_HOURS.get(raw_status, 1.0)
            total_hours += hours
            breakdown.append({
                'status': display_status,
                'count': count,
                'hours': hours
            })
        
        # Build response
        filter_desc = ""
        if filters.get('bucket'):
            filter_desc += f" in {filters['bucket']}"
        if filters.get('primary_department'):
            filter_desc += f" → {filters['primary_department']}"
        
        response = f"Effort estimate{filter_desc} ({total_resources:,} resources):\n\n"
        
        for b in breakdown:
            response += f"- {b['status']}: {b['count']:,} items, about {b['hours']:.1f} hours\n"
        
        response += f"\nTotal: {total_hours:.0f}-{total_hours * 1.2:.0f} hours (with buffer)\n"
        
        if total_hours > 40:
            response += "\nThat's significant. Consider breaking this into phases."
        
        return {'response': response}
    
    def _handle_priority_items(self, args: Dict, conv_id: int) -> Dict:
        """Get prioritized items to review."""
        limit = args.get('limit', 10)
        focus = args.get('focus_area', 'unreviewed')
        
        # Build query based on focus
        if focus == 'unreviewed':
            where = "scrub_status = 'not_reviewed'"
            order = "CASE WHEN bucket = 'Onboarding' THEN 0 ELSE 1 END, first_seen"
        elif focus == 'unowned':
            where = "(scrub_owner IS NULL OR scrub_owner = '')"
            order = "CASE WHEN bucket = 'Onboarding' THEN 0 ELSE 1 END, scrub_status"
        elif focus == 'onboarding':
            where = "bucket = 'Onboarding' AND scrub_status = 'not_reviewed'"
            order = "first_seen"
        elif focus == 'modify':
            where = "scrub_status = 'Modify'"
            order = "CASE WHEN bucket = 'Onboarding' THEN 0 ELSE 1 END, first_seen"
        else:
            where = "scrub_status = 'not_reviewed'"
            order = "first_seen"
        
        results = db.execute(
            f"""SELECT resource_key, display_name, bucket, primary_department, scrub_status
               FROM resources
               WHERE is_archived = 0 AND is_placeholder = 0 AND {where}
               ORDER BY {order}
               LIMIT %s""",
            (limit,),
            fetch="all"
        )
        
        if not results:
            return {'response': f"No {focus} items found. Great progress!"}
        
        response = f"Top {len(results)} {focus} items to review:\n\n"
        
        for i, r in enumerate(results, 1):
            bucket = r['bucket'] or 'Unknown'
            dept = r['primary_department'] or ''
            name = r['display_name'] or r['resource_key']
            response += f"{i}. {name}\n   {bucket} - {dept}\n"
        
        response += f"\nCompleting these reduces {focus} backlog significantly."
        
        # Store context for follow-ups
        save_query_context(conv_id, {
            'type': 'priority',
            'focus': focus,
            'count': len(results),
            'resource_keys': [r['resource_key'] for r in results]
        })
        
        return {'response': response}
    
    def _handle_investment_alignment(self, args: Dict) -> Dict:
        """Analyze if investment effort matches importance."""
        # Get Modify items by bucket (where effort is)
        modify_by_bucket = db.execute(
            """SELECT bucket, COUNT(*) as cnt
               FROM resources
               WHERE is_archived = 0 AND is_placeholder = 0 AND scrub_status = 'Modify'
               GROUP BY bucket""",
            fetch="all"
        )
        
        # Get total by bucket (importance proxy)
        total_by_bucket = db.execute(
            """SELECT bucket, COUNT(*) as cnt
               FROM resources
               WHERE is_archived = 0 AND is_placeholder = 0
               GROUP BY bucket""",
            fetch="all"
        )
        
        if not modify_by_bucket or not total_by_bucket:
            return {'response': "Insufficient data to analyze alignment."}
        
        # Convert to dicts
        modify_dict = {r['bucket']: r['cnt'] for r in modify_by_bucket}
        total_dict = {r['bucket']: r['cnt'] for r in total_by_bucket}
        
        total_modify = sum(modify_dict.values())
        total_all = sum(total_dict.values())
        
        # Calculate alignment
        misalignments = []
        for bucket, modify_count in modify_dict.items():
            total_count = total_dict.get(bucket, 0)
            
            modify_pct = (modify_count / total_modify * 100) if total_modify else 0
            importance_pct = (total_count / total_all * 100) if total_all else 0
            
            diff = abs(modify_pct - importance_pct)
            if diff > 10:  # Significant misalignment
                misalignments.append({
                    'bucket': bucket,
                    'modify_pct': modify_pct,
                    'importance_pct': importance_pct,
                    'diff': diff
                })
        
        if not misalignments:
            return {'response': "Investment effort appears well-aligned with importance."}
        
        response = "Potential investment misalignment detected:\n\n"
        
        for m in sorted(misalignments, key=lambda x: x['diff'], reverse=True):
            response += f"{m['bucket']}:\n"
            response += f"- Has {m['modify_pct']:.0f}% of Modify items\n"
            response += f"- But represents {m['importance_pct']:.0f}% of catalog\n\n"
        
        response += "Consider rebalancing investment toward higher-importance areas."
        
        return {'response': response}
    
    def _handle_quick_wins(self, args: Dict) -> Dict:
        """Find actions with immediate visible impact."""
        # Get sunset items (zero effort to archive)
        sunset_count = db.execute(
            """SELECT COUNT(*) as cnt FROM resources 
               WHERE is_archived = 0 AND is_placeholder = 0 
               AND scrub_status = 'Sunset'""",
            fetch="one"
        )
        sunset = sunset_count['cnt'] if sunset_count else 0
        
        # Get unassigned Include items (quick to process)
        include_unowned = db.execute(
            """SELECT COUNT(*) as cnt FROM resources 
               WHERE is_archived = 0 AND is_placeholder = 0 
               AND scrub_status = 'Include'
               AND (scrub_owner IS NULL OR scrub_owner = '')""",
            fetch="one"
        )
        include_no_owner = include_unowned['cnt'] if include_unowned else 0
        
        # Get total for percentage
        total = db.execute(
            """SELECT COUNT(*) as cnt FROM resources 
               WHERE is_archived = 0 AND is_placeholder = 0""",
            fetch="one"
        )
        total_count = total['cnt'] if total else 1
        
        wins = []
        
        if sunset > 0:
            pct = (sunset / total_count) * 100
            wins.append({
                'action': 'Archive Sunset items',
                'count': sunset,
                'pct': pct,
                'effort': 'Zero - just archive',
                'impact': f"Reduces catalog by {pct:.1f}%"
            })
        
        if include_no_owner > 0:
            wins.append({
                'action': 'Assign owners to Include items',
                'count': include_no_owner,
                'effort': 'Minimal - just assign',
                'impact': 'Clears ownership backlog'
            })
        
        if not wins:
            return {'response': "No quick wins available. Time for deeper work!"}
        
        response = "Quick wins (high impact, low effort):\n\n"
        
        for i, w in enumerate(wins, 1):
            response += f"{i}. {w['action']}\n"
            response += f"   {w['count']:,} items - {w['effort'].lower()}\n"
            response += f"   Impact: {w['impact']}\n\n"
        
        response += f"Start with {wins[0]['action'].lower()} for immediate visible progress."
        
        return {'response': response}
    
    def _handle_status_breakdown(self, args: Dict) -> Dict:
        """Get detailed status breakdown for bucket or department."""
        bucket = args.get('bucket')
        dept = args.get('primary_department')
        
        # Build WHERE
        where_clauses = ["is_archived = 0", "is_placeholder = 0"]
        params = []
        
        if bucket:
            where_clauses.append("bucket = %s")
            params.append(bucket)
        
        if dept:
            where_clauses.append("LOWER(primary_department) LIKE LOWER(%s)")
            dept = f"%{dept}%"
            params.append(dept)
        
        where_sql = " AND ".join(where_clauses)
        
        # Get totals
        total = db.execute(
            f"SELECT COUNT(*) as cnt FROM resources WHERE {where_sql}",
            tuple(params) if params else None,
            fetch="one"
        )
        total_count = total['cnt'] if total else 0
        
        if total_count == 0:
            return {'response': "No resources found matching those criteria."}
        
        # Get by status
        status_data = db.execute(
            f"""SELECT scrub_status, COUNT(*) as cnt
               FROM resources
               WHERE {where_sql}
               GROUP BY scrub_status
               ORDER BY cnt DESC""",
            tuple(params) if params else None,
            fetch="all"
        )
        
        # Build filter description
        filter_desc = ""
        if bucket:
            filter_desc = f" in {bucket}"
        if dept:
            filter_desc += f" → {dept}"
        
        response = f"Status breakdown{filter_desc} ({total_count:,} resources):\n\n"
        
        for row in status_data:
            status = self._format_enum_label(row['scrub_status'], 'scrub_status')
            count = row['cnt']
            response += f"- {status}: {count:,}\n"
        
        # Add insight
        not_reviewed = sum(r['cnt'] for r in status_data if (r['scrub_status'] or 'not_reviewed') == 'not_reviewed')
        if not_reviewed > 0:
            response += f"\n{not_reviewed:,} items still need review."
        
        return {'response': response}
    
    def _execute_pending_action(self, conversation_id: int, action: Dict) -> Dict:
        """Execute confirmed pending action."""
        clear_pending_action(self.user_id)
        
        # Save current state for undo
        self._save_undo_buffer(action['resource_keys'])
        
        try:
            count = self._apply_action(action)
            response = f"Done! Updated {count} resource{'s' if count != 1 else ''}. You can undo this if needed."
        except Exception as e:
            logger.error(f"Action execution error: {e}")
            response = "Hmm, something went wrong applying that change. Want to try again?"
            return {
                'response': response,
                'action_pending': False,
                'action_preview': None,
                'conversation_id': conversation_id,
            }
        
        _save_message(conversation_id, 'assistant', response,
                     metadata={'action_completed': True, 'count': count})
        
        return {
            'response': response,
            'action_pending': False,
            'action_preview': None,
            'conversation_id': conversation_id,
            'action_completed': True,
            'undo_available': True,
        }
    
    def _apply_action(self, action: Dict) -> int:
        """Apply a validated action to the database."""
        action_type = action['type']
        keys = action['resource_keys']
        updates = action.get('updates', {})
        
        count = 0
        with db.transaction() as conn:
            for key in keys:
                if action_type == 'scrub':
                    db.update_resource_scrub(
                        resource_key=key,
                        decision=updates.get('scrub_status', 'not_reviewed'),
                        owner=updates.get('scrub_owner', ''),
                        notes=updates.get('scrub_notes'),
                        audience=updates.get('audience'),
                        reviewed_by=self.username,
                        conn=conn
                    )
                elif action_type == 'invest':
                    db.update_resource_invest(
                        resource_key=key,
                        decision=updates.get('invest_decision'),
                        owner=updates.get('invest_owner', ''),
                        effort=updates.get('invest_effort'),
                        notes=updates.get('invest_notes'),
                        reviewed_by=self.username,
                        conn=conn
                    )
                elif action_type == 'sales_stage':
                    db.update_sales_stage(key, updates.get('sales_stage'), conn=conn)
                
                count += 1
        
        db.clear_cache()
        return count
    
    def _save_undo_buffer(self, resource_keys: List[str]):
        """Save current state of resources for potential undo."""
        if not resource_keys:
            return
        
        placeholders = ",".join("?" * len(resource_keys))
        current_state = db.execute(
            f"""SELECT resource_key, scrub_status, scrub_owner, scrub_notes,
                       audience, sales_stage, invest_decision, invest_owner,
                       invest_effort, invest_notes
                FROM resources WHERE resource_key IN ({placeholders})""",
            tuple(resource_keys), fetch="all"
        )
        
        db.execute(
            """INSERT INTO chat_undo_buffer (user_id, action_type, affected_keys, previous_state, created_at)
               VALUES (?, 'update', ?, ?, ?)
               ON CONFLICT (user_id) DO UPDATE SET
                   action_type = EXCLUDED.action_type,
                   affected_keys = EXCLUDED.affected_keys,
                   previous_state = EXCLUDED.previous_state,
                   created_at = EXCLUDED.created_at""",
            (self.user_id, list(resource_keys), 
             json.dumps([dict(r) for r in current_state]),
             datetime.now(timezone.utc).isoformat())
        )
    
    def undo_last_action(self) -> Dict[str, Any]:
        """Restore previous state from undo buffer."""
        buffer = db.execute(
            "SELECT * FROM chat_undo_buffer WHERE user_id = ?",
            (self.user_id,), fetch="one"
        )
        
        if not buffer:
            return {'success': False, 'message': "Nothing to undo."}
        
        prev_data = buffer['previous_state']
        previous = json.loads(prev_data) if isinstance(prev_data, str) else prev_data
        restored = 0
        
        with db.transaction() as conn:
            for record in previous:
                db.execute(
                    """UPDATE resources SET 
                       scrub_status = ?, scrub_owner = ?, scrub_notes = ?,
                       audience = ?, sales_stage = ?,
                       invest_decision = ?, invest_owner = ?, invest_effort = ?, invest_notes = ?
                       WHERE resource_key = ?""",
                    (record.get('scrub_status'), record.get('scrub_owner'), 
                     record.get('scrub_notes'), record.get('audience'),
                     record.get('sales_stage'), record.get('invest_decision'),
                     record.get('invest_owner'), record.get('invest_effort'),
                     record.get('invest_notes'), record['resource_key']),
                    conn=conn
                )
                restored += 1
            
            db.execute("DELETE FROM chat_undo_buffer WHERE user_id = ?",
                      (self.user_id,), conn=conn)
        
        db.clear_cache()
        return {
            'success': True, 
            'message': f"Undone! Restored {restored} resource{'s' if restored != 1 else ''} to previous state."
        }
    
    def _find_keys_by_filter(self, filter_criteria: Dict) -> List[str]:
        """Find resource keys matching filter criteria."""
        conditions = ["is_archived = 0", "is_placeholder = 0"]
        params = []
        
        if filter_criteria.get('bucket'):
            conditions.append("LOWER(bucket) = LOWER(?)")
            params.append(filter_criteria['bucket'])
        
        if filter_criteria.get('scrub_status'):
            conditions.append("scrub_status = ?")
            params.append(filter_criteria['scrub_status'])
        
        if filter_criteria.get('has_audience') is False:
            conditions.append("(audience IS NULL OR audience = '')")
        
        where_clause = " AND ".join(conditions)
        results = db.execute(
            f"SELECT resource_key FROM resources WHERE {where_clause}",
            tuple(params), fetch="all"
        )
        
        return [r['resource_key'] for r in results]
    
    def _get_resource_names(self, keys: List[str]) -> List[Dict]:
        """Get resource display names for confirmation messages."""
        if not keys:
            return []
        
        placeholders = ",".join("?" * len(keys))
        return db.execute(
            f"SELECT resource_key, display_name FROM resources WHERE resource_key IN ({placeholders})",
            tuple(keys), fetch="all"
        )
    
    def _check_rate_limit(self) -> bool:
        """Check if user is within rate limit."""
        # Simple implementation - could be enhanced with Redis
        # For now, just return True (rate limiting not enforced yet)
        return True
    
    def _is_confirmation(self, message: str) -> bool:
        """Check if message is confirming pending action."""
        confirmations = {'yes', 'y', 'confirm', 'confirmed', 'go ahead', 'proceed', 'do it', 'ok', 'sure', 'yep', 'yeah', 'absolutely', 'definitely'}
        return message.strip().lower() in confirmations
    
    def _is_cancellation(self, message: str) -> bool:
        """Check if message is cancelling pending action."""
        cancellations = {'no', 'n', 'cancel', 'cancelled', 'stop', 'nevermind', 'never mind', 'nope', 'nah', 'abort', 'wait'}
        return message.strip().lower() in cancellations


# ============================================================================
# Conversation & Message Management Functions
# ============================================================================

def create_conversation(user_id: int, title: str = "New conversation") -> int:
    """Create a new conversation and return its ID."""
    result = db.execute(
        """INSERT INTO chat_conversations (user_id, title, created_at, updated_at)
           VALUES (?, ?, ?, ?) RETURNING conversation_id""",
        (user_id, title, datetime.now(timezone.utc).isoformat(),
         datetime.now(timezone.utc).isoformat()),
        fetch="one"
    )
    return result['conversation_id']


def update_conversation_title(conversation_id: int, title: str):
    """Update conversation title."""
    db.execute(
        "UPDATE chat_conversations SET title = ? WHERE conversation_id = ?",
        (title[:100], conversation_id)  # Limit to 100 chars
    )


def delete_conversation(conversation_id: int, user_id: int):
    """Delete a conversation and its messages. Only allows deletion of own conversations."""
    # Verify ownership
    conv = db.execute(
        "SELECT user_id FROM chat_conversations WHERE conversation_id = ?",
        (conversation_id,), fetch="one"
    )
    if not conv or conv['user_id'] != user_id:
        raise ValueError("Conversation not found or not owned by user")
    
    # Delete messages first (foreign key constraint)
    db.execute(
        "DELETE FROM chat_messages WHERE conversation_id = ?",
        (conversation_id,)
    )
    # Delete conversation
    db.execute(
        "DELETE FROM chat_conversations WHERE conversation_id = ?",
        (conversation_id,)
    )


def backfill_conversation_titles():
    """One-time backfill of conversation titles from first message."""
    rows = db.execute(
        """SELECT DISTINCT ON (c.conversation_id) 
                  c.conversation_id, m.content
           FROM chat_conversations c
           JOIN chat_messages m ON m.conversation_id = c.conversation_id
           WHERE c.title = 'New conversation'
           AND m.role = 'user'
           ORDER BY c.conversation_id, m.message_id""",
        fetch="all"
    )
    count = 0
    for row in rows:
        new_title = row['content'][:50] + ('...' if len(row['content']) > 50 else '')
        update_conversation_title(row['conversation_id'], new_title)
        count += 1
    return count


def get_conversations(user_id: int) -> List[Dict]:
    """Get all conversations for a user."""
    return db.execute(
        """SELECT conversation_id, title, updated_at 
           FROM chat_conversations 
           WHERE user_id = ? 
           ORDER BY updated_at DESC""",
        (user_id,), fetch="all"
    )


def get_messages(conversation_id: int) -> List[Dict]:
    """Get all messages in a conversation."""
    return db.execute(
        """SELECT role, content, metadata, created_at
           FROM chat_messages 
           WHERE conversation_id = ?
           ORDER BY created_at ASC""",
        (conversation_id,), fetch="all"
    )


def _save_message(conv_id: int, role: str, content: str, metadata: Dict = None):
    """Save message to database."""
    db.execute(
        """INSERT INTO chat_messages (conversation_id, role, content, metadata, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (conv_id, role, content, json.dumps(metadata) if metadata else None,
         datetime.now(timezone.utc).isoformat())
    )
    
    # Update conversation timestamp
    db.execute(
        "UPDATE chat_conversations SET updated_at = ? WHERE conversation_id = ?",
        (datetime.now(timezone.utc).isoformat(), conv_id)
    )


def _get_conversation_history(conv_id: int, limit: int = 10) -> List[Dict]:
    """Get recent messages for context."""
    rows = db.execute(
        """SELECT role, content FROM chat_messages 
           WHERE conversation_id = ? 
           ORDER BY created_at DESC LIMIT ?""",
        (conv_id, limit), fetch="all"
    )
    return [{"role": r['role'], "content": r['content']} for r in reversed(rows)]


# ============================================================================
# Pending Action Management (stored in session-like table)
# ============================================================================

def save_pending_action(user_id: int, action: Dict):
    """Save pending action for user."""
    db.execute(
        """INSERT INTO chat_pending_actions (user_id, action_data, created_at)
           VALUES (?, ?, ?)
           ON CONFLICT (user_id) DO UPDATE SET
               action_data = EXCLUDED.action_data,
               created_at = EXCLUDED.created_at""",
        (user_id, json.dumps(action), datetime.now(timezone.utc).isoformat())
    )


def get_pending_action(user_id: int) -> Optional[Dict]:
    """Get pending action for user."""
    result = db.execute(
        "SELECT action_data FROM chat_pending_actions WHERE user_id = ?",
        (user_id,), fetch="one"
    )
    if result:
        data = result['action_data']
        return json.loads(data) if isinstance(data, str) else data
    return None


def clear_pending_action(user_id: int):
    """Clear pending action for user."""
    db.execute("DELETE FROM chat_pending_actions WHERE user_id = ?", (user_id,))


# ============================================================================
# Query Context Management (for follow-up support)
# ============================================================================

def save_query_context(conv_id: int, context: Dict):
    """Save last query context for follow-ups."""
    db.execute(
        "UPDATE chat_conversations SET query_context = ? WHERE conversation_id = ?",
        (json.dumps(context), conv_id)
    )


def get_query_context(conv_id: int) -> Optional[Dict]:
    """Get last query context."""
    result = db.execute(
        "SELECT query_context FROM chat_conversations WHERE conversation_id = ?",
        (conv_id,), fetch="one"
    )
    if result and result.get('query_context'):
        ctx = result['query_context']
        return json.loads(ctx) if isinstance(ctx, str) else ctx
    return None
