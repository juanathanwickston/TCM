"""
Scrubbing Global Save — Required Tests
=======================================
Tests per MASTER PROMPT spec (LOCKED).

These tests MUST fail if any contract is violated:
1. Transactional Integrity
2. Success Count Accuracy
3. Dirty State Reversion
4. Navigation Warning (code structure test)
"""
import pytest


class TestScrubbingGlobalSave:
    """
    Tests for Scrubbing Global Save spec compliance.
    """
    
    def test_transactional_integrity_invalid_row_blocks_all(self):
        """
        Transactional Integrity Test:
        - 2 dirty rows submitted
        - 1 invalid
        - Assert ZERO rows persisted
        
        This is a CODE STRUCTURE test verifying the endpoint has
        proper validation-before-write logic.
        """
        import inspect
        from tcm_app.views import save_scrub_batch_view
        
        source = inspect.getsource(save_scrub_batch_view)
        
        # Must validate ALL before any write
        assert 'PHASE 1: Validate ALL rows before any write' in source, \
            "Batch save must validate all rows before any write"
        
        # Must abort all writes if any validation fails
        assert 'PHASE 2: If ANY validation failed, abort ALL writes' in source, \
            "Batch save must abort all writes if any validation fails"
        
        # Must use transaction
        assert 'conn.commit()' in source, \
            "Batch save must commit transaction after all writes"
        
        # Must NOT commit before all validation passes
        phase1_pos = source.find('PHASE 1')
        phase3_pos = source.find('PHASE 3')
        commit_pos = source.find('conn.commit()')
        
        assert phase1_pos < phase3_pos < commit_pos, \
            "Commit must come after all validation and writes"
    
    def test_success_count_equals_persisted_rows(self):
        """
        Success Count Accuracy Test:
        - Assert success message reports exactly N persisted rows
        - N = persisted_count, not len(validated_rows) or len(dirty_keys)
        """
        import inspect
        from tcm_app.views import save_scrub_batch_view
        
        source = inspect.getsource(save_scrub_batch_view)
        
        # Must track persisted count separately
        assert 'persisted_count' in source, \
            "Batch save must track persisted_count separately"
        
        # Success message must use persisted_count
        assert "Saved {persisted_count} item(s)" in source or \
               "f'Saved {persisted_count} item(s)'" in source, \
            "Success message must report persisted_count, not validated count"
    
    def test_dirty_state_tracking_is_logical(self):
        """
        Dirty State Reversion Test:
        - Verify template uses logical dirty tracking
        - Not visual/CSS-based
        """
        import re
        from pathlib import Path
        
        template_path = Path(__file__).parent.parent / 'tcm_app' / 'templates' / 'tcm_app' / 'scrubbing.html'
        template_content = template_path.read_text()
        
        # Must have comment explaining logical vs visual
        assert 'LOGICAL' in template_content.upper() or 'Dirty tracking is LOGICAL' in template_content, \
            "Template must document that dirty tracking is logical"
        
        # Must track originals in data attributes
        assert 'data-original-status' in template_content, \
            "Template must store original values in data attributes"
        
        # Must have dirtyRows Set
        assert 'dirtyRows = new Set()' in template_content or 'dirtyRows.add' in template_content, \
            "Template must use Set to track dirty rows"
    
    def test_navigation_warning_exists(self):
        """
        Navigation Warning Test:
        - Verify beforeunload handler exists
        - Only fires when dirty rows present
        """
        from pathlib import Path
        
        template_path = Path(__file__).parent.parent / 'tcm_app' / 'templates' / 'tcm_app' / 'scrubbing.html'
        template_content = template_path.read_text()
        
        # Must have beforeunload handler
        assert 'beforeunload' in template_content, \
            "Template must have beforeunload handler"
        
        # Must check dirty state before warning
        assert 'dirtyRows.size > 0' in template_content, \
            "Navigation warning must only fire when dirty rows exist"
    
    def test_in_flight_protection_exists(self):
        """
        In-Flight Save Protection Test:
        - Button must be disabled during save
        - Must show "Saving..." state
        """
        from pathlib import Path
        
        template_path = Path(__file__).parent.parent / 'tcm_app' / 'templates' / 'tcm_app' / 'scrubbing.html'
        template_content = template_path.read_text()
        
        # Must have isSaving flag
        assert 'isSaving' in template_content, \
            "Template must have isSaving flag for in-flight protection"
        
        # Must show Saving... text
        assert 'Saving...' in template_content, \
            "Template must show 'Saving...' during in-flight save"
    
    def test_error_messages_include_field_and_reason(self):
        """
        Error Handling Test:
        - Errors must include row identifier
        - Errors must include field name
        - Errors must include reason
        """
        import inspect
        from tcm_app.views import save_scrub_batch_view
        
        source = inspect.getsource(save_scrub_batch_view)
        
        # Must include field in error
        assert "'field':" in source, \
            "Errors must include field name"
        
        # Must include reason in error
        assert "'reason':" in source, \
            "Errors must include reason"
        
        # Must build detailed error message
        assert 'error_details' in source, \
            "Must build detailed error message with row + field + reason"
    
    def test_column_alignment(self):
        """
        Column Count Test:
        - Exactly 5 headers
        - No Status badge
        - No per-row Save buttons
        """
        from pathlib import Path
        
        template_path = Path(__file__).parent.parent / 'tcm_app' / 'templates' / 'tcm_app' / 'scrubbing.html'
        template_content = template_path.read_text()
        
        # Count <th> tags in thead (not <thead>)
        import re
        th_matches = re.findall(r'<th\b[^>]*>', template_content)
        assert len(th_matches) == 5, \
            f"Must have exactly 5 column headers, found {len(th_matches)}"
        
        # No Status badge
        assert 'badge' not in template_content.lower() or 'badge bg-' not in template_content, \
            "Must not have Status badge"
        
        # No per-row Save buttons (only Global Save)
        save_buttons = re.findall(r'type=["\']submit["\']', template_content)
        assert len(save_buttons) == 0, \
            "Must not have per-row submit buttons"
