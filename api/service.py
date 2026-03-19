"""
Service layer for secret detection business logic.
"""

import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from .regex_manager import RegexPatternManager
from .model_manager import ModelManager
from .config import settings


class SecretDetectionService:
    """Service for detecting secrets in text."""
    
    def __init__(
        self,
        regex_manager: RegexPatternManager,
        model_manager: ModelManager,
        max_workers: int = 1,
        cache_size: int = 128
    ):
        """
        Initialize the detection service.
        
        Args:
            regex_manager: Manager for regex patterns
            model_manager: Manager for ML model
            max_workers: Maximum number of worker threads for inference
            cache_size: Maximum number of cached inference results (LRU). Set to 0 to disable caching.
        """
        self.regex_manager = regex_manager
        self.model_manager = model_manager
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.cache_size = cache_size
        self.cache_enabled = cache_size > 0
        
        # Statistics
        self.cache_hits = 0
        self.cache_misses = 0
        
        print(f"✓ Thread pool initialized with {max_workers} workers")
        if self.cache_enabled:
            print(f"✓ LRU cache initialized with size {cache_size}")
        else:
            print(f"✓ Caching disabled")
    
    def _create_context_key(self, text: str, candidate_string: str) -> str:
        """
        Create a unique cache key for a context window.
        
        Args:
            text: The full text
            candidate_string: The candidate string
            
        Returns:
            SHA256 hash of the context window
        """
        # Use the same context window creation logic as model_manager
        from .utils import clean_text, create_context_window
        cleaned_text = clean_text(text)
        context = create_context_window(
            cleaned_text,
            candidate_string,
            window_size=self.model_manager.window_size
        )
        # Create a hash of context + candidate for caching
        cache_input = f"{context}|||{candidate_string}"
        return hashlib.sha256(cache_input.encode()).hexdigest()
    
    def _get_cached_result(self, cache_key: str) -> Optional[Tuple[int, bool]]:
        """
        Get cached inference result.
        
        Args:
            cache_key: The cache key
            
        Returns:
            Tuple of (prediction, is_secret) or None if not cached
        """
        # Return None immediately if caching is disabled
        if not self.cache_enabled:
            return None
        
        if not hasattr(self, '_inference_cache'):
            self._inference_cache = {}
            self._cache_order = []
        
        if cache_key in self._inference_cache:
            # Move to end (most recently used)
            self._cache_order.remove(cache_key)
            self._cache_order.append(cache_key)
            self.cache_hits += 1
            return self._inference_cache[cache_key]
        
        self.cache_misses += 1
        return None
    
    def _set_cached_result(self, cache_key: str, prediction: int, is_secret: bool):
        """
        Store inference result in cache.
        
        Args:
            cache_key: The cache key
            prediction: The model prediction (0 or 1)
            is_secret: Whether it's a secret
        """
        # Don't cache if caching is disabled
        if not self.cache_enabled:
            return
        
        if not hasattr(self, '_inference_cache'):
            self._inference_cache = {}
            self._cache_order = []
        
        # Implement LRU eviction
        if cache_key not in self._inference_cache:
            if len(self._inference_cache) >= self.cache_size:
                # Remove least recently used
                lru_key = self._cache_order.pop(0)
                del self._inference_cache[lru_key]
        else:
            # Update order
            self._cache_order.remove(cache_key)
        
        self._inference_cache[cache_key] = (prediction, is_secret)
        self._cache_order.append(cache_key)
    
    def _detect_secrets_sync(
        self,
        text: str,
        max_results: Optional[int] = None,
        batch_size: int = 32
    ) -> Dict:
        """
        Synchronous method to detect secrets in text.
        This runs in a worker thread to avoid blocking.
        
        Args:
            text: Input text to analyze
            max_results: Maximum number of results to return
            batch_size: Batch size for inference
        
        Returns:
            Dictionary with detection results including all candidates
        """
        # Extract candidates using regex patterns
        candidates = self.regex_manager.extract_candidates(text)
        
        if not candidates:
            return {
                'success': True,
                'total_candidates': 0,
                'secrets_detected': 0,
                'detection_rate': 0.0,
                'secrets': [],
                'all_candidates': [],
                'cache_stats': {
                    'hits': self.cache_hits,
                    'misses': self.cache_misses,
                    'hit_rate': 0.0
                },
                'message': 'No candidate strings found matching regex patterns'
            }
        
        # Check cache for each candidate and separate into cached/uncached
        cached_results = {}
        uncached_candidates = []
        
        for candidate in candidates:
            cache_key = self._create_context_key(text, candidate['candidate_string'])
            cached = self._get_cached_result(cache_key)
            
            if cached is not None:
                prediction, is_secret = cached
                print(f"✓ CACHE HIT: '{candidate['candidate_string'][:50]}...' - is_secret: {is_secret}")
                cached_results[candidate['candidate_string']] = {
                    'candidate_string': candidate['candidate_string'],
                    'secret_type': candidate['secret_type'],
                    'pattern_id': candidate['pattern_id'],
                    'source': candidate['source'],
                    'position': candidate['position'],
                    'prediction': prediction,
                    'is_secret': is_secret,
                    'from_cache': True
                }
            else:
                print(f"✗ CACHE MISS: '{candidate['candidate_string'][:50]}...' - running new inference")
                uncached_candidates.append(candidate)
        
        # Run ML inference only on uncached candidates
        inference_results = []
        if uncached_candidates:
            print(f"\n🔍 Running ML inference on {len(uncached_candidates)} new candidate(s)...")
            inference_results = self.model_manager.run_inference(
                text, uncached_candidates, batch_size
            )
            
            # Cache the new results
            for result in inference_results:
                cache_key = self._create_context_key(text, result['candidate_string'])
                self._set_cached_result(
                    cache_key,
                    result['prediction'],
                    result['is_secret']
                )
                result['from_cache'] = False
                print(f"  → NEW DETECTION: '{result['candidate_string'][:50]}...' - is_secret: {result['is_secret']}")
        else:
            print(f"\n✓ All {len(candidates)} candidate(s) retrieved from cache - no new inference needed")
        
        # Combine cached and new results
        all_results = list(cached_results.values()) + inference_results
        
        # Filter for detected secrets
        secrets = [r for r in all_results if r['is_secret']]
        
        # Limit results if requested
        if max_results is not None:
            secrets = secrets[:max_results]
        
        # Calculate detection rate and cache hit rate
        detection_rate = len(secrets) / len(candidates) * 100 if candidates else 0.0
        total_requests = self.cache_hits + self.cache_misses
        cache_hit_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0.0
        
        # print(f"\n📊 Detection Summary:")
        # print(f"  - Total candidates: {len(candidates)}")
        # print(f"  - Secrets detected: {len(secrets)} ({detection_rate:.1f}%)")
        # print(f"  - Cache hits: {len(cached_results)} | New inferences: {len(uncached_candidates)}")
        # print(f"  - Overall cache hit rate: {cache_hit_rate:.1f}%")
        # print("-" * 70)
        
        return {
            'success': True,
            'total_candidates': len(candidates),
            'secrets_detected': len(secrets),
            'detection_rate': detection_rate,
            'secrets': secrets,
            'all_candidates': all_results,  # Include all candidates with their labels
            'cache_stats': {
                'hits': self.cache_hits,
                'misses': self.cache_misses,
                'hit_rate': cache_hit_rate
            },
            'message': f'Successfully analyzed text and found {len(secrets)} secrets'
        }
    
    async def detect_secrets(
        self,
        text: str,
        max_results: Optional[int] = None,
        batch_size: int = 32
    ) -> Dict:
        """
        Async method to detect secrets in text.
        Runs the actual inference in a thread pool to avoid blocking the event loop.
        
        Args:
            text: Input text to analyze
            max_results: Maximum number of results to return
            batch_size: Batch size for inference
        
        Returns:
            Dictionary with detection results
        """
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self.executor,
            self._detect_secrets_sync,
            text,
            max_results,
            batch_size
        )
        return result
    
    def get_stats(self) -> Dict:
        """
        Get service statistics.
        
        Returns:
            Dictionary with service stats including cache statistics
        """
        total_requests = self.cache_hits + self.cache_misses
        cache_hit_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0.0
        
        cache_size_current = 0
        if hasattr(self, '_inference_cache'):
            cache_size_current = len(self._inference_cache)
        
        return {
            'patterns_loaded': self.regex_manager.get_pattern_count(),
            'patterns_failed': self.regex_manager.get_failed_pattern_count(),
            'device': self.model_manager.get_device(),
            'cache_enabled': self.cache_enabled,
            'cache_size_limit': self.cache_size,
            'cache_size_current': cache_size_current,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'cache_hit_rate': cache_hit_rate
        }
    
    def clear_cache(self):
        """Clear the inference cache."""
        if hasattr(self, '_inference_cache'):
            self._inference_cache.clear()
            self._cache_order.clear()
        self.cache_hits = 0
        self.cache_misses = 0
        print("✓ Cache cleared")
    
    def shutdown(self):
        """Shutdown the thread pool executor."""
        print("\nShutting down thread pool...")
        self.executor.shutdown(wait=True)
        print("✓ Thread pool shutdown complete")
