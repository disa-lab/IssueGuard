"""
Inference script for CodeBERT Secret Detection Model
Supports FP16 mixed precision and dynamic quantization for faster inference
"""

import os
import pandas as pd
import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, classification_report
from tqdm.auto import tqdm
import argparse
import re
import string
from pathlib import Path


# --- Helper Functions (same as training) ---
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
    
    return None


def process_dataframe(input_df: pd.DataFrame):
    """
    Prepare X_text, X_candidate, Y_labels from a raw dataframe.
    Returns: (X_text, X_candidate, Y_labels)
    """
    if not isinstance(input_df, pd.DataFrame):
        raise TypeError("Input must be a Pandas DataFrame.")
    
    required_cols = {"Issue_id", "text", "candidate_string", "label"}
    missing = required_cols - set(input_df.columns)
    if missing:
        raise KeyError(f"Missing required column(s): {missing}")
    
    if input_df.empty:
        print("Warning: Input DataFrame is empty.")
        return [], [], []
    
    df = input_df.copy()
    
    # Clean candidate_string & text
    for col in ["candidate_string", "text"]:
        df[col] = df[col].replace([np.inf, -np.inf], np.nan)
        df = df.dropna(subset=[col])
    
    # Clean label
    df["label"] = df["label"].replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=["label"])
    df["label"] = df["label"].astype(int)
    
    # Build clean_text then modified_text
    def _clean_safe(x):
        try:
            return clean_text("" if x is None else str(x))
        except Exception:
            return "" if x is None else str(x)
    
    df["clean_text"] = df["text"].map(_clean_safe)
    
    def _ctx_safe(row):
        try:
            return create_context_window(row["clean_text"], row["candidate_string"])
        except Exception:
            return row["clean_text"]
    
    df["modified_text"] = df.apply(_ctx_safe, axis=1)
    
    X_text = df["modified_text"].astype(str).tolist()
    X_candidate = df["candidate_string"].astype(str).tolist()
    Y_labels = df["label"].tolist()
    
    return X_text, X_candidate, Y_labels


class PairDataset(Dataset):
    """Dataset for text pair classification."""
    def __init__(self, encodings, labels):
        self.encodings = encodings
        self.labels = labels
    
    def __getitem__(self, idx):
        item = {key: val[idx].clone().detach() for key, val in self.encodings.items()}
        item['labels'] = torch.tensor(self.labels[idx], dtype=torch.long)
        return item
    
    def __len__(self):
        return len(self.labels)


def load_model(model_path, device, use_quantization=False):
    """
    Load the trained model with optional optimizations.
    
    Args:
        model_path: Path to saved model directory
        device: torch device
        use_quantization: Apply dynamic quantization (CPU only)
    """
    print(f"Loading model from: {model_path}")
    
    # Load tokenizer and model
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForSequenceClassification.from_pretrained(model_path)
    
    # Apply quantization if requested (only on CPU)
    if use_quantization and device.type == 'cpu':
        print("Applying dynamic quantization...")
        model = torch.quantization.quantize_dynamic(
            model, 
            {torch.nn.Linear}, 
            dtype=torch.qint8
        )
        print("✓ Quantization applied")
    elif use_quantization and device.type == 'cuda':
        print("Warning: Quantization is only supported on CPU. Skipping quantization.")
    
    model.to(device)
    model.eval()
    
    return model, tokenizer


def run_inference(
    model, 
    tokenizer, 
    test_loader, 
    device, 
    use_fp16=False
):
    """
    Run inference on test data.
    
    Args:
        model: The model to use for inference
        tokenizer: The tokenizer
        test_loader: DataLoader for test data
        device: torch device
        use_fp16: Use mixed precision inference (GPU only)
    """
    all_test_preds = []
    all_test_labels = []
    total_test_loss = 0
    
    print("\nRunning inference...")
    test_progress_bar = tqdm(test_loader, desc="Testing")
    
    with torch.no_grad():
        for batch in test_progress_bar:
            input_ids = batch['input_ids'].to(device)
            attention_mask = batch['attention_mask'].to(device)
            labels = batch['labels'].to(device)
            
            token_type_ids = batch.get('token_type_ids')
            kwargs = {
                "input_ids": input_ids, 
                "attention_mask": attention_mask, 
                "labels": labels
            }
            if token_type_ids is not None:
                kwargs["token_type_ids"] = token_type_ids.to(device)
            
            # Use mixed precision for inference if enabled and on GPU
            use_amp = use_fp16 and device.type == 'cuda'
            with torch.amp.autocast("cuda", enabled=use_amp):
                outputs = model(**kwargs)
                loss = outputs.loss
            
            total_test_loss += loss.item()
            
            logits = outputs.logits
            predictions = torch.argmax(logits, dim=-1)
            all_test_preds.extend(predictions.cpu().numpy())
            all_test_labels.extend(labels.cpu().numpy())
            
            test_progress_bar.set_postfix({'test_loss': f"{loss.item():.4f}"})
    
    return all_test_preds, all_test_labels, total_test_loss / len(test_loader)


def print_metrics(all_test_labels, all_test_preds, avg_test_loss, output_file=None):
    """Print and optionally save evaluation metrics."""
    # Calculate metrics
    test_accuracy = accuracy_score(all_test_labels, all_test_preds)
    
    print("\n" + "="*50)
    print("INFERENCE RESULTS")
    print("="*50)
    print(f"Test Loss: {avg_test_loss:.4f}")
    print(f"Test Accuracy: {test_accuracy:.4f}")
    
    # Label distributions
    unique_labels_true, counts_true = np.unique(all_test_labels, return_counts=True)
    print(f"\nTrue label distribution: {dict(zip(unique_labels_true, counts_true))}")
    
    unique_labels_pred, counts_pred = np.unique(all_test_preds, return_counts=True)
    print(f"Predicted label distribution: {dict(zip(unique_labels_pred, counts_pred))}")
    
    # Detailed classification report
    print("\n" + "-"*50)
    print("CLASSIFICATION REPORT")
    print("-"*50)
    labels_for_report = sorted(list(set(all_test_labels) | set(all_test_preds)))
    report = classification_report(
        all_test_labels, 
        all_test_preds, 
        labels=labels_for_report, 
        zero_division=0
    )
    print(report)
    
    # Additional metrics
    num_labels = len(labels_for_report)
    
    if num_labels == 2:
        # Binary classification metrics
        precision_binary, recall_binary, f1_binary, _ = precision_recall_fscore_support(
            all_test_labels, all_test_preds, average='binary', pos_label=1, zero_division=0
        )
        print(f"\nBinary Metrics (for class 1):")
        print(f"  F1-Score: {f1_binary:.4f}")
        print(f"  Precision: {precision_binary:.4f}")
        print(f"  Recall: {recall_binary:.4f}")
    
    # Macro and weighted metrics
    precision_macro, recall_macro, f1_macro, _ = precision_recall_fscore_support(
        all_test_labels, all_test_preds, average='macro', zero_division=0
    )
    precision_weighted, recall_weighted, f1_weighted, _ = precision_recall_fscore_support(
        all_test_labels, all_test_preds, average='weighted', zero_division=0
    )
    
    print(f"\nMacro Metrics:")
    print(f"  F1-Score: {f1_macro:.4f}")
    print(f"  Precision: {precision_macro:.4f}")
    print(f"  Recall: {recall_macro:.4f}")
    
    print(f"\nWeighted Metrics:")
    print(f"  F1-Score: {f1_weighted:.4f}")
    print(f"  Precision: {precision_weighted:.4f}")
    print(f"  Recall: {recall_weighted:.4f}")
    
    # Save to file if requested
    if output_file:
        print(f"\nSaving results to: {output_file}")
        with open(output_file, "w") as f:
            f.write("="*50 + "\n")
            f.write("INFERENCE RESULTS\n")
            f.write("="*50 + "\n")
            f.write(f"Test Loss: {avg_test_loss:.4f}\n")
            f.write(f"Test Accuracy: {test_accuracy:.4f}\n")
            f.write(f"\nTrue label distribution: {dict(zip(unique_labels_true, counts_true))}\n")
            f.write(f"Predicted label distribution: {dict(zip(unique_labels_pred, counts_pred))}\n")
            f.write("\n" + "-"*50 + "\n")
            f.write("CLASSIFICATION REPORT\n")
            f.write("-"*50 + "\n")
            f.write(report)
            if num_labels == 2:
                f.write(f"\nBinary Metrics (for class 1):\n")
                f.write(f"  F1-Score: {f1_binary:.4f}\n")
                f.write(f"  Precision: {precision_binary:.4f}\n")
                f.write(f"  Recall: {recall_binary:.4f}\n")
            f.write(f"\nMacro Metrics:\n")
            f.write(f"  F1-Score: {f1_macro:.4f}\n")
            f.write(f"  Precision: {precision_macro:.4f}\n")
            f.write(f"  Recall: {recall_macro:.4f}\n")
            f.write(f"\nWeighted Metrics:\n")
            f.write(f"  F1-Score: {f1_weighted:.4f}\n")
            f.write(f"  Precision: {precision_weighted:.4f}\n")
            f.write(f"  Recall: {recall_weighted:.4f}\n")
        print(f"✓ Results saved to {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Run inference with trained CodeBERT model")
    parser.add_argument(
        "--model_path", 
        type=str, 
        required=True,
        help="Path to saved model directory (e.g., models/balanced/microsoft_codebert-base_complete)"
    )
    parser.add_argument(
        "--test_file", 
        type=str, 
        default="test.csv",
        help="Path to test CSV file (default: test.csv)"
    )
    parser.add_argument(
        "--batch_size", 
        type=int, 
        default=16,
        help="Batch size for inference (default: 16)"
    )
    parser.add_argument(
        "--max_length", 
        type=int, 
        default=256,
        help="Maximum sequence length (default: 256)"
    )
    parser.add_argument(
        "--use_fp16", 
        action="store_true",
        help="Use FP16 mixed precision for inference (GPU only)"
    )
    parser.add_argument(
        "--use_quantization", 
        action="store_true",
        help="Apply dynamic quantization for faster inference (CPU only)"
    )
    parser.add_argument(
        "--output_file", 
        type=str,
        default="inference_results.txt",
        help="Path to save inference results (default: inference_results.txt)"
    )
    parser.add_argument(
        "--device", 
        type=str,
        default=None,
        help="Device to use (cuda/cpu). Auto-detect if not specified."
    )
    
    args = parser.parse_args()
    
    # Determine device
    if args.device:
        device = torch.device(args.device)
    else:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    print(f"Using device: {device}")
    
    # Check optimization settings
    if args.use_fp16 and device.type == 'cpu':
        print("Warning: FP16 is only effective on GPU. Disabling FP16.")
        args.use_fp16 = False
    
    if args.use_quantization and device.type == 'cuda':
        print("Warning: Dynamic quantization is recommended for CPU only.")
    
    print(f"FP16 Mixed Precision: {'Enabled' if args.use_fp16 else 'Disabled'}")
    print(f"Quantization: {'Enabled' if args.use_quantization else 'Disabled'}")
    
    # Load test data
    print(f"\nLoading test data from: {args.test_file}")
    test_df = pd.read_csv(args.test_file)
    print(f"Test samples in CSV: {len(test_df)}")
    
    # Process data
    X_text_test, X_candidate_test, Y_labels_test = process_dataframe(test_df)
    print(f"Processed test samples: {len(X_text_test)}")
    
    # Load model and tokenizer
    model, tokenizer = load_model(
        args.model_path, 
        device, 
        use_quantization=args.use_quantization
    )
    
    # Tokenize
    print("\nTokenizing test data...")
    test_encodings = tokenizer(
        X_text_test, 
        X_candidate_test, 
        padding=True, 
        truncation=True, 
        return_tensors='pt', 
        max_length=args.max_length
    )
    
    # Create dataset and dataloader
    Y_labels_test_arr = np.array(Y_labels_test).astype(int)
    test_dataset = PairDataset(test_encodings, Y_labels_test_arr)
    test_loader = DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False)
    
    # Run inference
    all_test_preds, all_test_labels, avg_test_loss = run_inference(
        model, 
        tokenizer, 
        test_loader, 
        device, 
        use_fp16=args.use_fp16
    )
    
    # Print and save metrics
    print_metrics(all_test_labels, all_test_preds, avg_test_loss, args.output_file)
    
    print("\n" + "="*50)
    print("Inference completed successfully!")
    print("="*50)


if __name__ == "__main__":
    main()
