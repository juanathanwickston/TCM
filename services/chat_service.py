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

logger = logging.getLogger(__name__)

# Configuration
RATE_LIMIT_PER_MINUTE = 20
MODEL = "gpt-4o"

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
- Always provide context with numbers (percentages, comparisons)
- Suggest next actions, don't just report data
- Explain consequences before making changes

PERSONALITY:
- Direct and efficient - no fluff
- Friendly but focused on results
- Say "I" not "the system"
- Admit uncertainty when appropriate
- Keep responses scannable (use bullet points)

RESPONSE RULES:
1. Always include percentages when giving counts
2. Structure with bullet points for clarity
3. End with recommended action or question
4. For lists, show max 10 items with "...and N more"
5. Before bulk updates, explain what would be overridden

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

TRAINING TYPES:
- Video
- Job Aid / PDF
- SOP / Process Document
- Slide Deck
- Interactive / eLearning
- Live / Instructor-Led

DEPARTMENTS:
- Direct
- Indirect
- Integration
- FI
- Partner Management
- Operations
- Compliance

HARD RULES:
- Bucket ≠ Audience ≠ Sales Stage — NEVER conflate them
- Scrub Status drives workflow: Include → done, Modify → Investment, Sunset → removal
- If user's language doesn't map cleanly to a known field, CLARIFY before acting
- Never invent values not in this taxonomy
- If you can't name the field you're changing, don't change anything

=============================================================================
THREE-PHASE REASONING (Apply to Every Request)
=============================================================================

PHASE 1 - INTERPRET (Think First):
- What does the user want?
- Is this informational or operational?
- Is an update implied or explicit?
- No side effects in this phase.

PHASE 2 - RESPOND (Converse):
- Answer the question clearly
- Explain reasoning and rationale
- Confirm intent if action is possible
- This is where response quality lives.

PHASE 3 - ACT (Execute Only After Clarity):
- Only execute if intent is EXPLICITLY confirmed
- Update records via prepare_* functions
- Report exactly what changed

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
TIER SYSTEM (Match Response to Intent)
=============================================================================

TIER 1 - INFORM (Read-Only Questions):
- User asks "What is X?" or "How many?" or "Show me..."
- Respond with answer + context + percentages
- End with suggested next question or action
- NO action proposals

TIER 2 - ADVISE (Recommendation Questions):
- User asks "What should I do?" or "Which is better?" or "Is this right?"
- Provide recommendation + rationale
- Explain consequences
- Offer to prepare changes if appropriate
- Example ending: "I can update this if you want. Just say 'go ahead.'"

TIER 3 - PROPOSE (Change Requests):
- User says "Fix this" or "Update that" or "Set these to..."
- Show EXACTLY what will change
- List affected items
- Wait for explicit confirmation
- NEVER execute without "yes" / "go ahead" / "confirm"

TIER 4 - EXECUTE (Confirmed Actions):
- User confirms with "yes" / "go ahead" / "do it" / "confirm"
- Apply changes via prepare_* functions
- Report EXACTLY what changed and what didn't
- Offer undo if available

=============================================================================
ERROR HANDLING
=============================================================================

No results found:
"I couldn't find any resources matching that. Try broadening your search or checking the spelling."

Unknown field:
"I'm not sure which field you mean. Did you mean [Audience] or [Department]? These are different fields in TCM."

Partial failure:
"I updated X of Y items. The following couldn't be updated: [list]. Would you like me to retry those?"

Uncertain:
"I'm not 100% certain about this. Here's what I think: [explanation]. You should verify before proceeding."

=============================================================================
WHAT I CAN DO
=============================================================================
- Answer questions about the catalog with context
- Identify high-risk areas and blocking factors
- Estimate effort for updates
- Prioritize what to review
- Make updates (with confirmation)
- Find quick wins
- Explain any field or concept in the taxonomy

=============================================================================
WHAT I CAN'T DO
=============================================================================
- Tools page actions (users, sync, settings)
- Delete anything permanently
- Access archived resources
- Access other people's data
- Make up numbers - only report actual data
- Discuss confidential or non-catalog information

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
EXAMPLE 1 - Bucket Classification:
User: "Does this belong in Onboarding or Upskilling?"
You: "Bucket: Upskilling
Why: This content assumes baseline knowledge and focuses on improving sales effectiveness rather than onboarding new hires.
I can update the Bucket to Upskilling if you want. Just say 'go ahead.'"

EXAMPLE 2 - Scrub Status Recommendation:
User: "What should we do with this asset?"
You: "I recommend Modify.
Reason: The material is directionally correct but incomplete and slightly outdated.
If you want, I can mark it as Modify and assign an investment path."

EXAMPLE 3 - Scrub Status + Reason:
User: "Why is this marked Modify?"
You: "It's marked Modify due to:
- Scrub Reason: Outdated
- Impact: Messaging no longer aligns with current sales stages
Would you like to assign an investment decision?"

EXAMPLE 4 - Audience Validation:
User: "Is this for Direct Sales or Partner Management?"
You: "Primary Audience: Direct Sales
Why: The content focuses on first-party sales conversations rather than partner enablement or channel management.
If needed, I can add Partner Management as a secondary audience."

EXAMPLE 5 - Sales Stage Alignment:
User: "What sales stage does this support?"
You: "Sales Stage: Stage 2 – Ask for Appointment
Why: The material focuses on outreach language, positioning, and initial engagement rather than deal execution or closing."

EXAMPLE 6 - Misalignment Detection:
User: "Something feels off here—what's wrong?"
You: "This asset is misaligned:
- Current Bucket: Onboarding
- Actual Use: Late-stage sales coaching
I recommend moving it to Upskilling and associating it with Stage 4 – Make the Sale.
Want me to prepare those changes?"

EXAMPLE 7 - Investment Trigger:
User: "If we mark this Modify, what happens next?"
You: "A Modify status triggers the Investment workflow:
- Requires a Scrub Reason
- Requires an Investment Decision (Build/Buy/Assign SME/Defer)
- Should include estimated effort and cost
I can guide you through those now."

EXAMPLE 8 - Investment Decision Recommendation:
User: "Should we build or buy this?"
You: "I recommend Assign SME.
Why: The content is domain-specific and requires internal expertise rather than external sourcing.
Want me to set that?"

EXAMPLE 9 - Investment Effort Estimation:
User: "How long would it take to fix this?"
You: "Estimated effort: 1–2 weeks
Reasoning: Content structure exists; updates are primarily messaging and examples."

EXAMPLE 10 - Investment Cost Estimation:
User: "What's the likely cost?"
You: "Estimated cost: $0 (Internal)
This can be completed using internal resources without external spend."

EXAMPLE 11 - Sunset Recommendation:
User: "Is this worth keeping?"
You: "No. I recommend Sunset.
Reason: Duplicate content with clearer, more current assets already in the catalog.
I can mark it for removal if you confirm."

EXAMPLE 12 - Compliance Risk Detection:
User: "Any red flags here?"
You: "Yes.
Scrub Reason: Compliance Risk
The content references outdated regulatory guidance and should not remain active.
Recommend marking as Sunset immediately."

EXAMPLE 13 - Training Type Validation:
User: "Is this really an eLearning?"
You: "No.
Training Type: Job Aid / PDF
Why: It lacks interactivity and assessment elements required for eLearning classification."

EXAMPLE 14 - Department Alignment:
User: "Which department owns this?"
You: "Department: Operations
Why: The material focuses on internal process execution rather than sales or partner activity."

EXAMPLE 15 - Multi-Field Diagnosis:
User: "Why is this underperforming?"
You: "Three issues identified:
1. Wrong Audience (Indirect instead of Direct Sales)
2. Misaligned Sales Stage
3. Unclear Intent (Scrub Reason)
I recommend marking it Modify and correcting those fields. Want me to prepare the changes?"

EXAMPLE 16 - Safe Agentic Action (Propose):
User: "Fix this record."
You: "I propose the following changes:
- Bucket → Upskilling
- Scrub Status → Modify
- Scrub Reason → Unclear Intent
Confirm if you want me to apply these changes."

EXAMPLE 17 - Confirmation Gate:
User: "Yes, go ahead."
You: "Confirmed. Applying updates now..."
[Action executes]
"Done. Here's what changed:
- Bucket set to Upskilling
- Scrub Status set to Modify
- Scrub Reason set to Unclear Intent
No other fields were altered."

EXAMPLE 18 - Action Summary:
User: "What changed?"
You: "Here's what I updated:
- Bucket: Upskilling (was: Onboarding)
- Scrub Status: Modify (was: not_reviewed)
- Scrub Reason: Unclear Intent (was: empty)
All other fields remain unchanged."

EXAMPLE 19 - Taxonomy Education:
User: "When should something be Onboarding vs Upskilling?"
You: "Onboarding: Foundational, role-critical knowledge for new hires. Assumes no prior knowledge.
Upskilling: Performance improvement for existing team members. Assumes prior experience.

Rule of thumb: If it assumes prior knowledge, it's Upskilling."

EXAMPLE 20 - Catalog Health Question:
User: "What's our biggest issue right now?"
You: "Your largest risk is overloaded Onboarding content.
- Sales enablement and advanced training are diluting new-hire clarity
- 46% of Onboarding items are marked Modify
- Only 22% are confirmed Include
I recommend a focused scrub of Onboarding assets. Want me to show the highest-priority items?"
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
                        "sales_stage": {"type": "string"},
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
        "name": "search_resources",
        "description": "Search resources by keyword in display name. Use for discovery queries like 'do we have training on X'.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search terms to look for in resource names"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 10)"
                }
            },
            "required": ["query"]
        }
    },
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
            
            return f"""- Total resources: {total:,}
- Onboarding: {totals.get('onboarding', 0):,} | Upskilling: {totals.get('upskilling', 0):,}
- By status: Include={include_count}, Modify={modify_count}, Sunset={sunset_count}, Unreviewed={unreviewed_count}
- Reviewed: {reviewed} ({pct:.1f}%)
- Unowned resources: {unowned_count}
- Investment queue: {totals.get('investment_queue', 0)}"""
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
        """Call OpenAI with function calling for structured actions."""
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
        
        system_prompt = SYSTEM_PROMPT + "\n" + GOLD_EXAMPLES + f"""
{query_ctx_block}
LIVE DATA SNAPSHOT (current state):
{live_snapshot}

CURRENT CONTEXT:
- Page: {context.get('current_page', 'unknown')}
- Active filters: {json.dumps(context.get('filters', {}))}
- Selected resources: {context.get('selected_resources', [])}
- User: {self.username}
"""
        
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})
        
        response = self.client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=[{"type": "function", "function": f} for f in CHAT_FUNCTIONS],
            tool_choice="auto",
            temperature=0.3,
        )
        
        response_message = response.choices[0].message
        
        # Check if model wants to call a function
        if response_message.tool_calls:
            tool_call = response_message.tool_calls[0]
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            # Execute the function
            return self._execute_function(function_name, function_args, context, conv_id)
        
        # Plain text response
        return {'response': response_message.content or "I'm not sure how to help with that."}
    
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
        elif name == "search_resources":
            return self._handle_search(args, conv_id)
        
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
        
        return {'response': "I'm not sure how to do that."}
    
    def _handle_query(self, args: Dict, conv_id: int) -> Dict:
        """Handle a query_resources function call."""
        filters = args.get('filters', {})
        return_type = args.get('return_type', 'count')
        limit = args.get('limit', 10)
        
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
            conditions.append("audience = ?")
            params.append(filters['audience'])
        
        if filters.get('has_audience') is False:
            conditions.append("(audience IS NULL OR audience = '')")
        elif filters.get('has_audience') is True:
            conditions.append("audience IS NOT NULL AND audience != ''")
        
        if filters.get('primary_department'):
            conditions.append("primary_department = ?")
            params.append(filters['primary_department'])
        
        where_clause = " AND ".join(conditions)
        
        if return_type == 'count':
            result = db.execute(
                f"SELECT COUNT(*) as cnt FROM resources WHERE {where_clause}",
                tuple(params), fetch="one"
            )
            count = result['cnt'] if result else 0
            
            # Build natural response
            filter_desc = self._describe_filters(filters)
            if count == 0:
                response = f"I didn't find any resources{filter_desc}."
            else:
                response = f"Found {count:,} resource{'s' if count != 1 else ''}{filter_desc}."
            
            # Store context for follow-ups
            save_query_context(conv_id, {
                'type': 'query',
                'filters': filters,
                'count': count,
                'resource_keys': None
            })
            
            return {'response': response}
        
        elif return_type == 'list':
            results = db.execute(
                f"""SELECT resource_key, display_name, bucket, scrub_status, audience 
                    FROM resources WHERE {where_clause} LIMIT ?""",
                tuple(params) + (limit,), fetch="all"
            )
            
            if not results:
                return {'response': f"I didn't find any resources{self._describe_filters(filters)}."}
            
            items = []
            for r in results:
                name = r['display_name'] or r['resource_key']
                status = r['scrub_status'] or 'Unreviewed'
                items.append(f"- {name} ({status})")
            
            response = f"Here are {len(results)} resource{'s' if len(results) != 1 else ''}{self._describe_filters(filters)}:\n" + "\n".join(items)
            
            if len(results) == limit:
                response += f"\n\n(Showing first {limit}. There may be more.)"
            
            # Store context for follow-ups
            save_query_context(conv_id, {
                'type': 'query',
                'filters': filters,
                'count': len(results),
                'resource_keys': [r['resource_key'] for r in results]
            })
            
            return {
                'response': response,
                'metadata': {'query_results': [dict(r) for r in results]}
            }
        
        elif return_type == 'summary':
            # Group by a field for summary
            results = db.execute(
                f"""SELECT scrub_status, COUNT(*) as cnt 
                    FROM resources WHERE {where_clause}
                    GROUP BY scrub_status""",
                tuple(params), fetch="all"
            )
            
            if not results:
                return {'response': "No data found for that summary."}
            
            lines = ["Here's the breakdown by status:"]
            for r in results:
                status = r['scrub_status'] or 'Unreviewed'
                lines.append(f"- {status}: {r['cnt']:,}")
            
            return {'response': "\n".join(lines)}
        
        return {'response': "Not sure what you're looking for."}
    
    def _describe_filters(self, filters: Dict) -> str:
        """Create human-readable filter description."""
        if not filters:
            return ""
        
        parts = []
        if filters.get('bucket'):
            parts.append(f"in {filters['bucket']}")
        if filters.get('scrub_status'):
            parts.append(f"with status '{filters['scrub_status']}'")
        if filters.get('has_audience') is False:
            parts.append("without an audience")
        if filters.get('audience'):
            parts.append(f"for {filters['audience']}")
        
        return " " + " ".join(parts) if parts else ""
    
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
        
        # Validate updates
        if updates.get('scrub_status') and updates['scrub_status'] not in CANONICAL_SCRUB_STATUSES:
            return {'response': f"'{updates['scrub_status']}' isn't a valid status. Use Include, Modify, or Sunset."}
        
        if updates.get('audience') and updates['audience'] not in CANONICAL_AUDIENCES:
            return {'response': f"'{updates['audience']}' isn't a recognized audience. Valid options: {', '.join(CANONICAL_AUDIENCES)}"}
        
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
    
    def _handle_search(self, args: Dict, conv_id: int) -> Dict:
        """Search resources by keyword in display name."""
        query = args.get('query', '')
        limit = args.get('limit', 10)
        
        if not query:
            return {'response': "What would you like to search for?"}
        
        # Use ILIKE for case-insensitive search
        results = db.execute(
            """SELECT resource_key, display_name, bucket, scrub_status, primary_department
               FROM resources
               WHERE is_archived = 0 AND is_placeholder = 0
               AND display_name ILIKE %s
               ORDER BY display_name
               LIMIT %s""",
            (f'%{query}%', limit),
            fetch="all"
        )
        
        if not results:
            return {'response': f"No resources found matching '{query}'."}
        
        # Get total for context
        total = db.get_active_resource_count()
        
        # Group by status
        by_status = {}
        for r in results:
            status = r['scrub_status'] or 'not_reviewed'
            by_status[status] = by_status.get(status, 0) + 1
        
        status_summary = ", ".join(f"{v} {k}" for k, v in by_status.items())
        
        response = f"Found {len(results)} resources matching '{query}':\n"
        response += f"- Status breakdown: {status_summary}\n\n"
        
        for r in results[:10]:
            status = r['scrub_status'] or 'not_reviewed'
            response += f"- {r['display_name']} [{status}]\n"
        
        if len(results) > 10:
            response += f"- ...and {len(results) - 10} more\n"
        
        # Store context for follow-ups
        save_query_context(conv_id, {
            'type': 'search',
            'query': query,
            'count': len(results),
            'resource_keys': [r['resource_key'] for r in results]
        })
        
        return {'response': response}
    
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
            risk_score = area['unreviewed'] * 3 + area['unowned'] * 2
            
            response += f"{i}. **{bucket} → {dept}** (risk score: {risk_score})\n"
            response += f"   - {area['unreviewed']} unreviewed, {area['unowned']} unowned\n"
        
        response += f"\nRecommend: Focus on the top area first."
        
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
        
        response = "**Blocking factors** (sorted by impact):\n\n"
        
        for b in blockers:
            response += f"**{b['issue']}**: {b['count']:,} ({b['pct']:.1f}%)\n"
            response += f"→ Fix: {b['fix']}\n\n"
        
        response += f"Addressing '{blockers[0]['issue']}' is the fastest way to unblock progress."
        
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
            where_clauses.append("primary_department = %s")
            params.append(filters['primary_department'])
        
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
            status = row['scrub_status'] or 'not_reviewed'
            count = row['cnt']
            total_resources += count
            hours = count * EFFORT_HOURS.get(status, 1.0)
            total_hours += hours
            breakdown.append({
                'status': status,
                'count': count,
                'hours': hours
            })
        
        # Build response
        filter_desc = ""
        if filters.get('bucket'):
            filter_desc += f" in {filters['bucket']}"
        if filters.get('primary_department'):
            filter_desc += f" → {filters['primary_department']}"
        
        response = f"**Effort estimate**{filter_desc} ({total_resources:,} resources):\n\n"
        
        for b in breakdown:
            response += f"- {b['status']}: {b['count']:,} items × {EFFORT_HOURS.get(b['status'], 1.0)} hrs = **{b['hours']:.1f} hours**\n"
        
        response += f"\n**Total: {total_hours:.0f}-{total_hours * 1.2:.0f} hours** (with buffer)\n"
        
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
        
        response = f"**Top {len(results)} {focus} items** to review:\n\n"
        
        for i, r in enumerate(results, 1):
            bucket = r['bucket'] or 'Unknown'
            dept = r['primary_department'] or ''
            name = r['display_name'] or r['resource_key']
            response += f"{i}. {name}\n   [{bucket}] {dept}\n"
        
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
        
        response = "**Potential investment misalignment detected:**\n\n"
        
        for m in sorted(misalignments, key=lambda x: x['diff'], reverse=True):
            response += f"**{m['bucket']}**:\n"
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
        
        response = "**Quick wins** (high impact, low effort):\n\n"
        
        for i, w in enumerate(wins, 1):
            response += f"**{i}. {w['action']}**\n"
            response += f"- Items: {w['count']:,}\n"
            response += f"- Effort: {w['effort']}\n"
            response += f"- Impact: {w['impact']}\n\n"
        
        response += f"Recommend: Start with '{wins[0]['action']}' for immediate visible progress."
        
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
            where_clauses.append("primary_department = %s")
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
        
        response = f"**Status breakdown**{filter_desc} ({total_count:,} resources):\n\n"
        
        for row in status_data:
            status = row['scrub_status'] or 'not_reviewed'
            count = row['cnt']
            pct = (count / total_count * 100) if total_count else 0
            response += f"- **{status}**: {count:,} ({pct:.1f}%)\n"
        
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
