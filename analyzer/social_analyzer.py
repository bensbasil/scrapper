"""
analyzer/social_analyzer.py
----------------------------
Minor fix #18: Legacy module wrapper.
The actual implementation lives in `enrichment.social_analyzer` (SocialAnalyzer).
This re-export preserves backward compatibility for legacy imports.
"""

from enrichment.social_analyzer import SocialAnalyzer, SocialProfile, SocialAnalysisResult

__all__ = ["SocialAnalyzer", "SocialProfile", "SocialAnalysisResult"]
