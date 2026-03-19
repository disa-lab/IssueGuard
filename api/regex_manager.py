"""
Manager for loading and applying regex patterns.
"""

import os
import re
from typing import List, Dict, Tuple
import pandas as pd


class RegexPatternManager:
    """Manages loading and applying regex patterns for candidate extraction."""
    
    def __init__(self, regex_file: str):
        """
        Initialize the regex pattern manager.
        
        Args:
            regex_file: Path to Excel file containing regex patterns
        """
        self.regex_file = regex_file
        self.patterns: List[Dict] = []
        self.failed_patterns: List[Dict] = []
        self._load_patterns()
    
    def _load_patterns(self) -> None:
        """Load and compile regex patterns from Excel file."""
        print(f"Loading regex patterns from: {self.regex_file}")
        
        if not os.path.exists(self.regex_file):
            raise FileNotFoundError(f"Regex file not found: {self.regex_file}")
        
        df = pd.read_excel(self.regex_file)
        print(f"Loaded {len(df)} regex patterns from Excel")
        
        for idx, row in df.iterrows():
            pattern_str = row['Regular Expression']
            secret_type = row['Secret Type']
            source = row['Source']
            
            try:
                compiled_pattern = re.compile(pattern_str, re.IGNORECASE)
                self.patterns.append({
                    'pattern_id': idx,
                    'secret_type': secret_type,
                    'regex': compiled_pattern,
                    'regex_str': pattern_str,
                    'source': source
                })
            except re.error as e:
                self.failed_patterns.append({
                    'pattern_id': idx,
                    'secret_type': secret_type,
                    'error': str(e)
                })
        
        print(f"✓ Successfully compiled {len(self.patterns)} patterns")
        if self.failed_patterns:
            print(f"✗ Failed to compile {len(self.failed_patterns)} patterns")
    
    def extract_candidates(self, text: str) -> List[Dict]:
        """
        Apply all regex patterns to extract candidate strings from text.
        
        Args:
            text: The text to search for candidates
        
        Returns:
            List of candidate dictionaries with metadata
        """
        candidates = []
        seen_candidates = set()  # To avoid duplicates
        
        for pattern_info in self.patterns:
            matches = pattern_info['regex'].finditer(text)
            
            for match in matches:
                candidate_str = match.group(0)
                
                # Skip empty or very short candidates
                if not candidate_str or len(candidate_str.strip()) < 3:
                    continue
                
                # Create unique key to avoid exact duplicates
                unique_key = (candidate_str, pattern_info['pattern_id'])
                
                if unique_key not in seen_candidates:
                    seen_candidates.add(unique_key)
                    candidates.append({
                        'candidate_string': candidate_str,
                        'secret_type': pattern_info['secret_type'],
                        'pattern_id': pattern_info['pattern_id'],
                        'source': pattern_info['source'],
                        'position': (match.start(), match.end())
                    })
        
        return candidates
    
    def get_pattern_count(self) -> int:
        """Get the number of successfully loaded patterns."""
        return len(self.patterns)
    
    def get_failed_pattern_count(self) -> int:
        """Get the number of failed patterns."""
        return len(self.failed_patterns)
