"""
Controlled vocabulary for the Training Catalogue Manager.
Locked values for dropdowns and validation. No emojis.
"""

from enum import Enum


class ScrubStatus(str, Enum):
    """Status options for the scrubbing workflow."""
    NOT_REVIEWED = "not_reviewed"
    KEEP = "keep"
    MODIFY = "modify"
    SUNSET = "sunset"
    GAP = "gap"
    
    @classmethod
    def choices(cls) -> list:
        return [e.value for e in cls]
    
    @classmethod
    def display_labels(cls) -> dict:
        return {
            cls.NOT_REVIEWED.value: "Not Reviewed",
            cls.KEEP.value: "Keep",
            cls.MODIFY.value: "Modify",
            cls.SUNSET.value: "Sunset",
            cls.GAP.value: "Gap",
        }


class InvestDecision(str, Enum):
    """Decision options for the investment workflow."""
    BUILD = "build"
    BUY = "buy"
    ASSIGN_SME = "assign_sme"
    DEFER = "defer"
    
    @classmethod
    def choices(cls) -> list:
        return [e.value for e in cls]
    
    @classmethod
    def display_labels(cls) -> dict:
        return {
            cls.BUILD.value: "Build",
            cls.BUY.value: "Buy",
            cls.ASSIGN_SME.value: "Assign SME",
            cls.DEFER.value: "Defer",
        }


class SourceType(str, Enum):
    """Source types for catalog items."""
    SHAREPOINT = "sharepoint"
    ZIP = "zip"
    MANUAL = "manual"


# Fixed vocabulary for training taxonomy
DEPARTMENTS = [
    "Direct", "Indirect", "Integration", "FI", 
    "Partner Management", "Operations", "Compliance"
]

BUCKETS = ["Onboarding", "Upskilling"]

FUNCTIONAL_AREAS = [
    "Direct", "Indirect", "Integration", "FI",
    "Partner Management", "Operations", "Compliance", "General"
]

TRAINING_TYPES = [
    "Video",
    "Job Aid / PDF",
    "SOP / Process Document",
    "Slide Deck",
    "Interactive / eLearning",
    "Live / Instructor-Led"
]
