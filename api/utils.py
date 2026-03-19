"""
Utility functions for text processing.
"""

import re
import string


def clean_text(text: str, remove_non_printable: bool = True) -> str:
    """
    Clean a single text string.
    
    Args:
        text: Input text to clean
        remove_non_printable: Whether to remove non-printable characters
    
    Returns:
        Cleaned text string
    """
    if not isinstance(text, str):
        return ""
    
    cleaned = text.strip()
    cleaned = re.sub(r'[\r\n\t]+', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = re.sub(r'(</s>|<eos>)', '', cleaned)
    
    if remove_non_printable:
        printable_chars = set(string.printable)
        cleaned = ''.join(filter(lambda x: x in printable_chars, cleaned))
        
    cleaned = re.sub(r'[\'"\│]', '', cleaned)
    dir_list_clean = re.sub(r'drwx[-\s]*\d+\s+\w+\s+\w+\s+\d+\s+\w+\s+\d+\s+[0-9a-fA-F-]+.*','',cleaned)
    shell_code_free_text = re.sub(r'```shell([^`]+)```','',dir_list_clean,flags=re.IGNORECASE)
    shell_code_free_text = re.sub(r'```Shell\s*"([^"]*)"\s*```','',shell_code_free_text,flags=re.IGNORECASE)
    # saved_game_free_text = re.sub(r'```([^`]+)```','',shell_code_free_text) #etay jhamela hobe
    saved_game_free_text = re.sub(r'<details><summary>Saved game</summary>\n\n```(.*?)```', '', shell_code_free_text)
    remove_packages = re.sub(r'(\w+\.)+\w+','',saved_game_free_text)
    java_exp_free_text = re.sub(r'at\s[\w.$]+\.([\w]+)\(([^:]+:\d+)\)','',remove_packages)
    # url_free_text= re.sub(https?://[^\s#]+#[A-Za-z0-9\-]+,'', java_exp_free_text, flags=re.IGNORECASE)
    url_with_fragment_text= re.sub(r'https?://[^\s#]+#[A-Za-z0-9\-\=\+]+','', java_exp_free_text, flags=re.IGNORECASE)
    url_free_text= re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '',url_with_fragment_text)
    commit_free_text= re.sub(r'commit[ ]?(?:id)?[ ]?[:]?[ ]?([0-9a-f]{40})\b', '', url_free_text, flags=re.IGNORECASE)
    file_path_free_text = re.sub(r"/[\w/. :-]+",'',commit_free_text)
    file_path_free_text = re.sub( r'(/[^/\s]+)+','',file_path_free_text)
    sha256_free_text = re.sub(r'sha256\s*[:]?[=]?\s*[a-fA-F0-9]{64}','',file_path_free_text)
    sha1_free_text = re.sub(r'git-tree-sha1\s*=\s*[a-fA-F0-9]+','',sha256_free_text)
    build_id_free_text = re.sub(r'build-id\s*[:]?[=]?\s*([a-fA-F0-9]+)','',sha1_free_text)
    guids_free_text = re.sub(r'GUIDs:\s+([0-9a-fA-F-]+\s+[0-9a-fA-F-]+\s+[0-9a-fA-F-]+)','',build_id_free_text)
    uuids_free_text = re.sub(r'([0-9a-fA-F-]+\s*,\s*[0-9a-fA-F-]+\s*,\s*[0-9a-fA-F-]+)','',guids_free_text)
    event_id_free_text = re.sub(r'<([^>]+)>','',uuids_free_text)
    UUID_free_text = re.sub(r'(?:UUID|GUID|version|id)[\\=:"\'\s]*\b[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}\b','',event_id_free_text,flags=re.IGNORECASE) ##without the prefix so many false positives can be omitted
    hex_free_text = re.sub(r'(?:data|address|id)[\\=:"\'\s]*\b0x[0-9a-fA-F]+\b','',UUID_free_text,flags=re.IGNORECASE) ## deleting hex ids directly can cause issues
    ss_free_text = re.sub(r'Screenshot_(\d{4}[_-]\d{2}[_-]\d{2}[_-]\d{2}[_-]\d{2}[_-]\d{2}[_-]\d{2}[_-]\w+)','',hex_free_text,flags=re.IGNORECASE)
    cleaned = ss_free_text    

    
    return cleaned
    
    


def create_context_window(text: str, target_string: str, window_size: int = 200) -> str:
    """
    Create a context window around the target string.
    
    Args:
        text: Full text to search in
        target_string: String to find and create context around
        window_size: Number of characters before and after target
    
    Returns:
        Context window text, or full text if target not found
    """
    target_index = text.find(target_string)
    
    if target_index != -1:
        start_index = max(0, target_index - window_size)
        end_index = min(len(text), target_index + len(target_string) + window_size)
        context_window = text[start_index:end_index]
        return context_window
    
    return text  # Return full text if target not found
