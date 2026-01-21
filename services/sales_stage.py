"""
Sales Stage Constants
=====================
Single source of truth for Sales Stage classification.
Imported by Scrubbing, Inventory, and Dashboard.

This is classification metadata, NOT sync logic.
"""

# Canonical values and labels
SALES_STAGES = [
    ("stage_1_identify", "1. Identify the Customer"),
    ("stage_2_appointment", "2. Ask for Appointment"),
    ("stage_3_prep", "3. Prep for Appointment"),
    ("stage_4_make_sale", "4. Make the Sale"),
    ("stage_5_close", "5. Close the Sale"),
    ("stage_6_referrals", "6. Ask for Referrals"),
]

# Key → Label mapping for display
SALES_STAGE_LABELS = {k: v for k, v in SALES_STAGES}

# Just the keys for validation
SALES_STAGE_KEYS = [k for k, _ in SALES_STAGES]
