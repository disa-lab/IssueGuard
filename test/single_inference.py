"""
Single Data Inference Script for Secret Detection
==================================================
This script performs end-to-end inference on a single issue report:
1. Loads 761 regex patterns from Excel file
2. Applies all regexes to extract candidate strings
3. Creates context windows around each candidate
4. Runs model inference (supports fast inference with FP16/quantization)
5. Returns detected secrets with confidence scores

Usage:
    python single_inference.py --issue_text "Your issue report here..."
    python single_inference.py --issue_file path/to/issue.txt
    python single_inference.py --issue_text "..." --use_fp16  # GPU acceleration
    python single_inference.py --issue_text "..." --use_quantization  # CPU optimization
"""

import os
import re
import pandas as pd
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from torch.utils.data import DataLoader, Dataset
import argparse
import string
from pathlib import Path
from typing import List, Dict, Tuple
import json
from tqdm.auto import tqdm


# ==================== Helper Functions ====================

def clean_text(text, remove_non_printable=True):
    """Clean a single text string."""
    if not isinstance(text, str):
        return ""
    
    cleaned = text.strip()
    cleaned = re.sub(r'[\r\n\t]+', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = re.sub(r'(</s>|<eos>)', '', cleaned)
    
    if remove_non_printable:
        printable_chars = set(string.printable)
        cleaned = ''.join(filter(lambda x: x in printable_chars, cleaned))
    
    return cleaned


def create_context_window(text, target_string, window_size=200):
    """Create a context window around the target string."""
    target_index = text.find(target_string)
    
    if target_index != -1:
        start_index = max(0, target_index - window_size)
        end_index = min(len(text), target_index + len(target_string) + window_size)
        context_window = text[start_index:end_index]
        return context_window
    
    return text  # Return full text if target not found


# ==================== Regex Pattern Loader ====================

def load_regex_patterns(excel_file='Secret-Regular-Expression.xlsx'):
    """
    Load all regex patterns from the Excel file.
    
    Returns:
        List of dicts with pattern info: [{
            'pattern_id': int,
            'secret_type': str,
            'regex': compiled regex,
            'regex_str': str (original pattern),
            'source': str
        }]
    """
    print(f"Loading regex patterns from: {excel_file}")
    
    if not os.path.exists(excel_file):
        raise FileNotFoundError(f"Excel file not found: {excel_file}")
    
    df = pd.read_excel(excel_file)
    print(f"Loaded {len(df)} regex patterns")
    
    patterns = []
    failed_patterns = []
    
    for idx, row in df.iterrows():
        pattern_str = row['Regular Expression']
        secret_type = row['Secret Type']
        source = row['Source']
        
        try:
            # Compile the regex pattern
            compiled_pattern = re.compile(pattern_str, re.IGNORECASE)
            patterns.append({
                'pattern_id': idx,
                'secret_type': secret_type,
                'regex': compiled_pattern,
                'regex_str': pattern_str,
                'source': source
            })
        except re.error as e:
            failed_patterns.append({
                'pattern_id': idx,
                'secret_type': secret_type,
                'error': str(e)
            })
    
    print(f"✓ Successfully compiled {len(patterns)} patterns")
    if failed_patterns:
        print(f"✗ Failed to compile {len(failed_patterns)} patterns")
    
    return patterns, failed_patterns


# ==================== Candidate Extraction ====================

def extract_candidates(issue_text: str, patterns: List[Dict]) -> List[Dict]:
    """
    Apply all regex patterns to extract candidate strings from issue text.
    
    Args:
        issue_text: The issue report text
        patterns: List of compiled regex patterns
    
    Returns:
        List of candidate dicts: [{
            'candidate_string': str,
            'secret_type': str,
            'pattern_id': int,
            'source': str,
            'position': tuple (start, end)
        }]
    """
    print(f"\nApplying {len(patterns)} regex patterns to extract candidates...")
    
    candidates = []
    seen_candidates = set()  # To avoid duplicates
    
    for pattern_info in tqdm(patterns, desc="Extracting candidates"):
        matches = pattern_info['regex'].finditer(issue_text)
        
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
    
    print(f"✓ Extracted {len(candidates)} unique candidate strings")
    return candidates


# ==================== Model Loading ====================

def load_model(model_path, device, use_quantization=False):
    """
    Load the trained model with optional optimizations.
    
    Args:
        model_path: Path to saved model directory
        device: torch device
        use_quantization: Apply dynamic quantization (CPU only)
    """
    print(f"\nLoading model from: {model_path}")
    
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model not found: {model_path}")
    
    # Load tokenizer and model
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForSequenceClassification.from_pretrained(model_path)
    
    # Apply quantization if requested (only on CPU)
    if use_quantization and device.type == 'cpu':
        print("Applying dynamic quantization for faster CPU inference...")
        model = torch.quantization.quantize_dynamic(
            model, 
            {torch.nn.Linear}, 
            dtype=torch.qint8
        )
        print("✓ Quantization applied")
    elif use_quantization and device.type == 'cuda':
        print("Warning: Quantization is only supported on CPU. Skipping.")
    
    model.to(device)
    model.eval()
    
    print(f"✓ Model loaded successfully on {device}")
    return model, tokenizer


# ==================== Fast Inference ====================

class PairDataset(Dataset):
    """Dataset for text pair classification."""
    def __init__(self, encodings):
        self.encodings = encodings
    
    def __getitem__(self, idx):
        return {key: val[idx].clone().detach() for key, val in self.encodings.items()}
    
    def __len__(self):
        return len(self.encodings['input_ids'])


def run_fast_inference(
    model, 
    tokenizer, 
    issue_text: str,
    candidates: List[Dict],
    device,
    use_fp16=False,
    batch_size=32,
    max_length=256,
    window_size=200
):
    """
    Run fast inference on all candidates.
    
    Args:
        model: Trained model
        tokenizer: Model tokenizer
        issue_text: Original issue text
        candidates: List of candidate dicts
        device: torch device
        use_fp16: Use mixed precision (GPU only)
        batch_size: Batch size for inference
        max_length: Max sequence length
        window_size: Context window size
    
    Returns:
        List of results with predictions and confidence scores
    """
    if not candidates:
        print("No candidates to process")
        return []
    
    print(f"\nPreparing {len(candidates)} candidates for inference...")
    
    # Clean the issue text once
    cleaned_text = clean_text(issue_text)
    
    # Prepare data for model
    contexts = []
    candidate_strings = []
    
    for candidate in candidates:
        # Create context window around the candidate
        context = create_context_window(
            cleaned_text, 
            candidate['candidate_string'],
            window_size=window_size
        )
        contexts.append(context)
        candidate_strings.append(candidate['candidate_string'])
    
    # Tokenize all candidates at once
    print("Tokenizing candidates...")
    encodings = tokenizer(
        contexts,
        candidate_strings,
        padding=True,
        truncation=True,
        return_tensors='pt',
        max_length=max_length
    )
    
    # Create dataset and dataloader
    dataset = PairDataset(encodings)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=False)
    
    # Run inference
    print(f"Running inference with batch_size={batch_size}...")
    all_predictions = []
    all_probabilities = []
    
    use_amp = use_fp16 and device.type == 'cuda'
    
    with torch.no_grad():
        for batch in tqdm(dataloader, desc="Inference"):
            # Move batch to device
            input_ids = batch['input_ids'].to(device)
            attention_mask = batch['attention_mask'].to(device)
            
            kwargs = {
                "input_ids": input_ids,
                "attention_mask": attention_mask
            }
            
            # Add token_type_ids if present
            if 'token_type_ids' in batch:
                kwargs['token_type_ids'] = batch['token_type_ids'].to(device)
            
            # Run inference with optional mixed precision
            with torch.cuda.amp.autocast(enabled=use_amp):
                outputs = model(**kwargs)
            
            # Get predictions and probabilities
            logits = outputs.logits
            probabilities = torch.softmax(logits, dim=-1)
            predictions = torch.argmax(logits, dim=-1)
            
            all_predictions.extend(predictions.cpu().numpy())
            all_probabilities.extend(probabilities.cpu().numpy())
    
    # Combine results with candidate information
    print("Processing results...")
    results = []
    
    for idx, (candidate, pred, prob) in enumerate(zip(candidates, all_predictions, all_probabilities)):
        results.append({
            'candidate_string': candidate['candidate_string'],
            'secret_type': candidate['secret_type'],
            'pattern_id': candidate['pattern_id'],
            'source': candidate['source'],
            'position': candidate['position'],
            'prediction': int(pred),
            'is_secret': bool(pred == 1),
            'confidence_secret': float(prob[1]),
            'confidence_not_secret': float(prob[0]),
            'confidence_score': float(prob[pred])
        })
    
    return results


# ==================== Result Processing ====================

def filter_and_rank_results(results: List[Dict], confidence_threshold=0.5):
    """
    Filter results by confidence and rank by confidence score.
    
    Args:
        results: List of inference results
        confidence_threshold: Minimum confidence for positive predictions
    
    Returns:
        Filtered and sorted results
    """
    # Filter for positive predictions (secrets)
    secrets = [r for r in results if r['is_secret'] and r['confidence_score'] >= confidence_threshold]
    
    # Sort by confidence score (descending)
    secrets_sorted = sorted(secrets, key=lambda x: x['confidence_score'], reverse=True)
    
    return secrets_sorted


def print_results(results: List[Dict], show_all=False):
    """Print inference results in a readable format."""
    
    if not results:
        print("\n" + "="*70)
        print("No secrets detected!")
        print("="*70)
        return
    
    secrets = [r for r in results if r['is_secret']]
    non_secrets = [r for r in results if not r['is_secret']]
    
    print("\n" + "="*70)
    print(f"INFERENCE RESULTS - Total Candidates: {len(results)}")
    print("="*70)
    print(f"✓ Detected Secrets: {len(secrets)}")
    print(f"✗ Not Secrets: {len(non_secrets)}")
    
    if secrets:
        print("\n" + "-"*70)
        print("DETECTED SECRETS (Ranked by Confidence)")
        print("-"*70)
        
        for idx, secret in enumerate(secrets, 1):
            print(f"\n{idx}. Secret Type: {secret['secret_type']}")
            print(f"   Candidate: {secret['candidate_string'][:100]}{'...' if len(secret['candidate_string']) > 100 else ''}")
            print(f"   Confidence: {secret['confidence_score']:.4f} ({secret['confidence_score']*100:.2f}%)")
            print(f"   Position: {secret['position']}")
            print(f"   Source: {secret['source']} (Pattern ID: {secret['pattern_id']})")
    
    if show_all and non_secrets:
        print("\n" + "-"*70)
        print("NON-SECRETS (Top 10 by confidence)")
        print("-"*70)
        
        non_secrets_sorted = sorted(non_secrets, key=lambda x: x['confidence_score'], reverse=True)
        
        for idx, non_secret in enumerate(non_secrets_sorted[:10], 1):
            print(f"\n{idx}. Secret Type: {non_secret['secret_type']}")
            print(f"   Candidate: {non_secret['candidate_string'][:100]}{'...' if len(non_secret['candidate_string']) > 100 else ''}")
            print(f"   Confidence (not secret): {non_secret['confidence_score']:.4f} ({non_secret['confidence_score']*100:.2f}%)")


def save_results(results: List[Dict], output_file='inference_output.json'):
    """Save results to JSON file."""
    print(f"\nSaving results to: {output_file}")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Results saved to {output_file}")


# ==================== Main Function ====================

def main():
    parser = argparse.ArgumentParser(
        description="Single inference script for secret detection",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--issue_text",
        type=str,
        help="Issue report text as a string"
    )
    input_group.add_argument(
        "--issue_file",
        type=str,
        help="Path to file containing issue report text"
    )
    
    # Model and patterns
    parser.add_argument(
        "--model_path",
        type=str,
        default="models/balanced/microsoft_codebert-base_complete",
        help="Path to trained model (default: models/balanced/microsoft_codebert-base_complete)"
    )
    parser.add_argument(
        "--regex_file",
        type=str,
        default="Secret-Regular-Expression.xlsx",
        help="Path to Excel file with regex patterns (default: Secret-Regular-Expression.xlsx)"
    )
    
    # Inference options
    parser.add_argument(
        "--batch_size",
        type=int,
        default=32,
        help="Batch size for inference (default: 32)"
    )
    parser.add_argument(
        "--max_length",
        type=int,
        default=256,
        help="Maximum sequence length (default: 256)"
    )
    parser.add_argument(
        "--window_size",
        type=int,
        default=200,
        help="Context window size around candidates (default: 200)"
    )
    parser.add_argument(
        "--confidence_threshold",
        type=float,
        default=0.5,
        help="Minimum confidence for positive predictions (default: 0.5)"
    )
    
    # Optimization options
    parser.add_argument(
        "--use_fp16",
        action="store_true",
        help="Use FP16 mixed precision for faster GPU inference"
    )
    parser.add_argument(
        "--use_quantization",
        action="store_true",
        help="Use dynamic quantization for faster CPU inference"
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Device to use (cuda/cpu). Auto-detect if not specified."
    )
    
    # Output options
    parser.add_argument(
        "--output_file",
        type=str,
        default="inference_output.json",
        help="Output JSON file (default: inference_output.json)"
    )
    parser.add_argument(
        "--show_all",
        action="store_true",
        help="Show all results including non-secrets"
    )
    parser.add_argument(
        "--no_save",
        action="store_true",
        help="Don't save results to file"
    )
    
    args = parser.parse_args()
    
    # ==================== Setup ====================
    
    print("="*70)
    print("SECRET DETECTION - SINGLE INFERENCE SCRIPT")
    print("="*70)
    
    # Determine device
    if args.device:
        device = torch.device(args.device)
    else:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    print(f"Device: {device}")
    print(f"FP16: {'Enabled' if args.use_fp16 else 'Disabled'}")
    print(f"Quantization: {'Enabled' if args.use_quantization else 'Disabled'}")
    
    # Validate optimization settings
    if args.use_fp16 and device.type == 'cpu':
        print("Warning: FP16 only works on GPU. Disabling FP16.")
        args.use_fp16 = False
    
    # ==================== Load Issue Text ====================
    
    if args.issue_text:
        issue_text = args.issue_text
        print(f"\nIssue text length: {len(issue_text)} characters")
    else:
        print(f"\nLoading issue text from: {args.issue_file}")
        with open(args.issue_file, 'r', encoding='utf-8') as f:
            issue_text = f.read()
        print(f"Issue text length: {len(issue_text)} characters")
    
    # ==================== Load Regex Patterns ====================
    
    patterns, failed_patterns = load_regex_patterns(args.regex_file)
    
    if not patterns:
        print("Error: No valid regex patterns loaded!")
        return
    
    # ==================== Extract Candidates ====================
    
    candidates = extract_candidates(issue_text, patterns)
    
    if not candidates:
        print("\n" + "="*70)
        print("No candidates found matching any regex patterns!")
        print("="*70)
        return
    
    # ==================== Load Model ====================
    
    model, tokenizer = load_model(
        args.model_path,
        device,
        use_quantization=args.use_quantization
    )
    
    # ==================== Run Inference ====================
    
    results = run_fast_inference(
        model,
        tokenizer,
        issue_text,
        candidates,
        device,
        use_fp16=args.use_fp16,
        batch_size=args.batch_size,
        max_length=args.max_length,
        window_size=args.window_size
    )
    
    # ==================== Filter and Display Results ====================
    
    secrets = filter_and_rank_results(results, args.confidence_threshold)
    
    print_results(results, show_all=args.show_all)
    
    # ==================== Save Results ====================
    
    if not args.no_save:
        save_results(results, args.output_file)
    
    # ==================== Summary ====================
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Total Candidates Extracted: {len(candidates)}")
    print(f"Secrets Detected: {len(secrets)}")
    print(f"Detection Rate: {len(secrets)/len(candidates)*100:.2f}%")
    print(f"Confidence Threshold: {args.confidence_threshold}")
    print("="*70)
    
    print("\n✓ Inference completed successfully!")


if __name__ == "__main__":
    main()
