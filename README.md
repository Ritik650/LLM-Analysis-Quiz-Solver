---
title: LLM Analysis 
Agent emoji: 🤖 
colorFrom: blue 
colorTo: indigo 
sdk: docker 
pinned: false 
port: 7860
---
# **LLM Autonomous Quiz & Task Agent**

A sophisticated autonomous agent capable of navigating web pages, extracting instructions, and solving tasks dynamically. Built with **FastAPI**, **LangGraph**, and **Google Gemini 2.5 Flash**, this agent runs inside a Docker container and utilizes **Playwright** for rendering JavaScript-heavy websites.

## **Key Features**

* **Autonomous Navigation**: Fetches and renders full HTML using Playwright (Chromium).  
* **Intelligent Logic**: Uses LangGraph and Gemini 2.5 to parse instructions and decide on the next steps.  
* **Tool-Equipped**: Capable of writing/running Python code, downloading files, and sending API requests.  
* **Containerized**: Fully Dockerized environment using uv for fast dependency management.  
* **Resilient**: Implements retry logic, rate limiting, and dynamic routing based on server responses.

## **️Project Structure**
```
.  
├── agent.py                 \# Core LangGraph agent logic and prompt engineering  
├── main.py                  \# FastAPI entry point  
├── tools/                   \# Custom tool definitions  
│   ├── web_scraper.py       \# Playwright scraper  
│   ├── code_generate.py     \# Python code execution sandbox  
│   └── ...  
├── Dockerfile               \# Production environment definition  
├── pyproject.toml           \# Dependency management (uv)  
└── .env.example             \# Environment variable template
```
## **Deployment**

### **Option 1: Local Installation & Usage**

This project uses uv for package management and requires Playwright browsers.

### **1\. Clone the Repository**
```
git clone \<your-repo-url\>  
cd llm-analysis-tds-project-2
```
### **2\. Environment Setup**
Create a .env file in the root directory:
```
cp .env.example .env
```
Open .env and fill in your details:
```
GOOGLE_API_KEY=your_actual_gemini_key  
EMAIL=your_email_address  
SECRET=your_chosen_secret_token
```
### **3\. Install Dependencies**

Ensure you have uv installed, then sync the project:

```
# Install uv if you haven't already  
pip install uv

# Sync dependencies  
uv sync
```

### **4\. Install Playwright Browsers**

**Crucial Step:** You must install the browser binaries for the scraper to work.
```
uv run playwright install chromium
```
### **5\. Run the Server**

Start the FastAPI server:
```
uv run main.py
```
The server will start at ```http://0.0.0.0:7860```.


You can deploy this directly to a Hugging Face Space using the Docker SDK.

### **Option 2: HuggingFace (Recommended)**

1. **Create a Space**: Go to Hugging Face \-\> New Space.  
   * **SDK**: Select ```Docker```.  
   * **Template**: ```Blank```.  
2. **Clone the Space**: Clone the empty repository provided by Hugging Face to your local machine.  
3. **Copy Files**: Copy all files from this project into that new folder.  
4. **Push Code**:  
```
   git add .  
   git commit \-m "Initial deploy"  
   git push
```
5. **Configure Secrets**:  
   * Go to your Space's **Settings** tab.  
   * Scroll to **Variables and secrets**.  
   * Add the following **Secrets** (not Variables):  
     * ```GOOGLE_API_KEY```  
     * ```EMAIL``` 
     * ```SECRET```  
   * *The Space will restart automatically and build the Docker image.*


## **API Usage**

Once the server is running (locally or on HF), you can trigger the agent via a POST request.

**Endpoint:** ```/solve```

**Payload:**
```
{  
  "email": "your_email"
  "url": "https://example-quiz-url.com/start",  
  "secret": "your_secret_defined_in_env"  
}
```
**Example cURL:**
```
curl \-X POST "http://localhost:7860/solve" \\  
     \-H "Content-Type: application/json" \\  
     \-d '{"url": "https://target-website.com", "secret": "your_secret", "email": "your_email"}'
```