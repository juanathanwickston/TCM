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


class InvestEffort(str, Enum):
    """Timeline options for investment planning."""
    LESS_THAN_1W = "<1w"
    ONE_TO_TWO_W = "1-2w"
    TWO_TO_FOUR_W = "2-4w"
    ONE_TO_TWO_M = "1-2m"
    TWO_TO_THREE_M = "2-3m"
    THREE_M_PLUS = "3m+"
    
    @classmethod
    def choices(cls) -> list:
        return [e.value for e in cls]
    
    @classmethod
    def display_labels(cls) -> dict:
        return {
            cls.LESS_THAN_1W.value: "Less than 1 week",
            cls.ONE_TO_TWO_W.value: "1-2 weeks",
            cls.TWO_TO_FOUR_W.value: "2-4 weeks",
            cls.ONE_TO_TWO_M.value: "1-2 months",
            cls.TWO_TO_THREE_M.value: "2-3 months",
            cls.THREE_M_PLUS.value: "3+ months",
        }


class InvestCost(str, Enum):
    """Cost options for investment planning."""
    ZERO = "$0"
    UNDER_500 = "<$500"
    FIVE_HUNDRED_TO_2K = "$500-2k"
    TWO_K_TO_5K = "$2k-5k"
    FIVE_K_TO_10K = "$5k-10k"
    TEN_K_PLUS = "$10k+"
    
    @classmethod
    def choices(cls) -> list:
        return [e.value for e in cls]
    
    @classmethod
    def display_labels(cls) -> dict:
        return {
            cls.ZERO.value: "$0 (Internal)",
            cls.UNDER_500.value: "Under $500",
            cls.FIVE_HUNDRED_TO_2K.value: "$500 - $2,000",
            cls.TWO_K_TO_5K.value: "$2,000 - $5,000",
            cls.FIVE_K_TO_10K.value: "$5,000 - $10,000",
            cls.TEN_K_PLUS.value: "$10,000+",
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
