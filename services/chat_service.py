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
MODEL = "gpt-4o-mini"

# System prompt for natural, human-like responses
SYSTEM_PROMPT = """You are a helpful assistant for the Training Catalogue Manager (TCM). 
You help users find information about training resources and make updates.

PERSONALITY:
- Talk like a friendly coworker, not a robot
- Keep it casual but professional
- Short answers when short answers work
- Say "I" not "this system" or "the assistant"
- If you don't know, just say so

EXAMPLES OF GOOD RESPONSES:
- "Found 23 courses in Onboarding that need review."
- "All set! Updated 5 resources to 'Include'."
- "Hmm, I didn't find any matches. Want to try different filters?"
- "That's outside my wheelhouse - I stick to training data."

WHAT I CAN DO:
- Search and count resources
- Show breakdowns by audience, type, department, stage
- Find resources missing data (no audience, unreviewed, etc.)
- Update: status (Include/Modify/Sunset), audience, owner, notes, sales stage
- Update investment fields: decision, owner, effort, notes

WHAT I CAN'T DO:
- Anything on the Tools page (users, sync, settings)
- Delete anything
- Access other people's chats
- Make stuff up - I only report what's actually in the data

BEFORE CHANGING ANYTHING:
- You MUST use the appropriate function to prepare the change
- The system will show the user what will change and ask for confirmation
- Never claim you've made changes without using a function

IF I'M NOT SURE:
- Say "I'm not sure" rather than guess
- Ask for clarification if the request is ambiguous
- Only report numbers from actual query results

AVAILABLE DATA:
- resources table with: display_name, bucket, primary_department, training_type, 
  scrub_status, scrub_owner, audience, sales_stage, invest_decision, etc.
- Valid scrub_status: Include, Modify, Sunset (or not_reviewed/Unreviewed)
- Valid audiences: Direct Sales, Indirect Sales, Integration, FI, 
  Partner Management, Operations, Compliance, POS
- Valid sales_stages: 1-6 (Identify Customer through Ask for Referrals)
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
        history = _get_conversation_history(conversation_id, limit=10)
        
        # Call OpenAI with function calling
        try:
            result = self._call_openai(message, history, context)
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
    
    def _call_openai(self, message: str, history: List[Dict], context: Dict) -> Dict:
        """Call OpenAI with function calling for structured actions."""
        # Build context-aware system prompt
        system_prompt = SYSTEM_PROMPT + f"""

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
            return self._execute_function(function_name, function_args, context)
        
        # Plain text response
        return {'response': response_message.content or "I'm not sure how to help with that."}
    
    def _execute_function(self, name: str, args: Dict, context: Dict) -> Dict:
        """Execute a function call from OpenAI."""
        
        if name == "query_resources":
            return self._handle_query(args)
        
        elif name == "prepare_scrub_update":
            return self._prepare_scrub_update(args, context)
        
        elif name == "prepare_invest_update":
            return self._prepare_invest_update(args, context)
        
        elif name == "prepare_sales_stage_update":
            return self._prepare_sales_stage_update(args, context)
        
        return {'response': "I'm not sure how to do that."}
    
    def _handle_query(self, args: Dict) -> Dict:
        """Handle a query_resources function call."""
        filters = args.get('filters', {})
        return_type = args.get('return_type', 'count')
        limit = args.get('limit', 10)
        
        # Build WHERE clause
        conditions = ["is_archived = 0", "is_placeholder = 0"]
        params = []
        
        if filters.get('bucket'):
            conditions.append("bucket = ?")
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
    
    def _prepare_scrub_update(self, args: Dict, context: Dict) -> Dict:
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
        
        if not resource_keys:
            return {'response': "I need to know which resources to update. Can you be more specific or select some items?"}
        
        # Validate updates
        if updates.get('scrub_status') and updates['scrub_status'] not in CANONICAL_SCRUB_STATUSES:
            return {'response': f"'{updates['scrub_status']}' isn't a valid status. Use Include, Modify, or Sunset."}
        
        if updates.get('audience') and updates['audience'] not in CANONICAL_AUDIENCES:
            return {'response': f"'{updates['audience']}' isn't a recognized audience. Valid options: {', '.join(CANONICAL_AUDIENCES)}"}
        
        # Get resource names for confirmation
        resources = self._get_resource_names(resource_keys)
        
        if not resources:
            return {'response': "Couldn't find those resources. They may have been archived."}
        
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
        
        response = f"I'll update {', '.join(update_desc)} for {len(names)} resource{'s' if len(names) != 1 else ''}:\n"
        response += "\n".join(f"- {n}" for n in names_preview)
        if more:
            response += f"\n- ...and {more} more"
        response += "\n\nWant me to go ahead?"
        
        return {
            'response': response,
            'action_pending': True,
            'action_preview': {
                'type': 'scrub_update',
                'count': len(names),
                'updates': updates,
            },
            'metadata': {'pending_action': action},
        }
    
    def _prepare_invest_update(self, args: Dict, context: Dict) -> Dict:
        """Prepare an investment update."""
        # Similar structure to scrub update
        updates = args.get('updates', {})
        resource_keys = args.get('resource_keys', [])
        
        if not resource_keys:
            resource_keys = context.get('selected_resources', [])
        
        if not resource_keys:
            return {'response': "Which resources should I update?"}
        
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
    
    def _prepare_sales_stage_update(self, args: Dict, context: Dict) -> Dict:
        """Prepare a sales stage update."""
        resource_keys = args.get('resource_keys', [])
        sales_stage = args.get('sales_stage')
        
        if not resource_keys:
            resource_keys = context.get('selected_resources', [])
        
        if not resource_keys:
            return {'response': "Which resources should I update?"}
        
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
        
        previous = json.loads(buffer['previous_state'])
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
            conditions.append("bucket = ?")
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
        confirmations = {'yes', 'y', 'confirm', 'go ahead', 'proceed', 'do it', 'ok', 'sure', 'yep', 'yeah'}
        return message.strip().lower() in confirmations
    
    def _is_cancellation(self, message: str) -> bool:
        """Check if message is cancelling pending action."""
        cancellations = {'no', 'n', 'cancel', 'stop', 'nevermind', 'never mind', 'nope', 'nah'}
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
        return json.loads(result['action_data'])
    return None


def clear_pending_action(user_id: int):
    """Clear pending action for user."""
    db.execute("DELETE FROM chat_pending_actions WHERE user_id = ?", (user_id,))
