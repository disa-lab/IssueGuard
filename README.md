# IssueGuard: Real-Time Secret Leak Prevention Tool

IssueGuard is a Google Chrome extension designed to detect sensitive information such as API keys, tokens, passwords, and credentials within GitHub issue reports. The tool combines regex-based candidate extraction with a fine-tuned CodeBERT model to provide accurate, context-aware secret detection in real time.

This system helps users analyze issue content directly on the GitHub page, preventing accidental secret leakage without requiring developers to navigate away from their workflow.

The overall methodology of IssueGuard is shown below:

![IssueGuard System Diagram](assets/IssueGuard.png)

IssueGuard classifies extracted candidates into two categories: **Secret** and **Non-sensitive**, based on the annotation criteria defined in the following work:

*Sadif Ahmed, Md Nafiu Rahman, Zahin Wahab, Gias Uddin, and Rifat Shahriyar. "Secret Breach Prevention in Software Issue Reports." (2025).*
Link: https://arxiv.org/abs/2410.23657


## System Requirements

- Python 3.12.0 or higher  
- Google Chrome browser


## Installation and Setup

### Clone the Repository

```bash
git clone https://github.com/nafiurahman00/IssueGuard.git
cd IssueGuard
```

### Download the Model
Download the pre-trained CodeBERT model from GitHub releases:

1. Go to the [GitHub Releases page](https://github.com/nafiurahman00/IssueGuard/releases)
2. Download the `models.zip` file from the latest release
3. Extract the `models.zip` file in the root directory of the project

After extraction, verify that the model files are present at:  
`models/balanced/microsoft_codebert-base_complete/`

### Start the FastAPI Server

**Option 1: Using Docker (Recommended)**
```bash
docker compose up --build
```
> Requires [Docker](https://docs.docker.com/get-docker/) and [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) for GPU support.

**Option 2: Run Directly**

### Install Python Dependencies
```bash
pip install -r requirements_fastapi.txt
```
```bash
python main.py
```

### Install the Chrome Extension
1. Open Google Chrome and navigate to `chrome://extensions/`.
2. Enable "Developer mode" using the toggle switch in the top right corner.
3. Click on "Load unpacked" and select the `IssueGuardExtension` directory from the cloned repository.
4. The IssueGuard extension should now appear in your list of extensions.

### Usage

1. Ensure the backend server is running
2. Open any GitHub issue creation page
3. Start writing or pasting text in the issue description box

IssueGuard will automatically analyze the content.
Detected secrets are highlighted, and a tooltip lists all true secrets identified by the model.
Regex-captured false positives are ignored based on the model’s classification.

Example GitHub issue pages for testing:

https://github.com/*any-repo*/issues/new

Any public issue creation form containing text inputs

### Links
Video demonstration: https://www.youtube.com/watch?v=kvbWA8rr9cU

