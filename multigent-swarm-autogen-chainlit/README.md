# Multi-Agent Debate System

A conversational AI system that uses multiple specialized agents to research topics, construct arguments, analyze them critically, and make informed decisions. Built with AutoGen, powered by Google's Gemini, and presented through a Chainlit interface.

## What It Does

This application simulates a structured debate process where AI agents collaborate to analyze complex questions. When you ask a question (like "Should an 80-year-old use iPhone or Android?"), the system:

1. **Researches** the topic using web search and scraping
2. **Constructs** logical arguments based on evidence
3. **Critiques** those arguments to identify weaknesses
4. **Decides** on the best position with detailed reasoning

## How It Works

The system uses a **Swarm architecture** where four specialized agents work in sequence:

```
User Question
     ↓
┌─────────────────┐
│ ResearcherAgent │ → Gathers facts, statistics, and evidence
└────────┬────────┘   Uses web search & scraping tools
         ↓
┌─────────────────┐
│ ArgumentAgent   │ → Structures logical arguments
└────────┬────────┘   Creates compelling narratives
         ↓
┌─────────────────┐
│  CriticAgent    │ → Identifies weaknesses
└────────┬────────┘   Constructs counterarguments
         ↓
┌─────────────────┐
│ DecisionAgent   │ → Evaluates all perspectives
└─────────────────┘   Provides final assessment
```

### Agent Details

- **ResearcherAgent**: Methodical information gatherer with web search and scraping capabilities
- **ArgumentAgent**: Logical strategist that builds persuasive cases
- **CriticAgent**: Devil's advocate that challenges assumptions
- **DecisionAgent**: Impartial evaluator that synthesizes conclusions

## Setup

### Prerequisites

- Python 3.13+
- API Keys:
  - Google Gemini API key
  - Serper API key (for web search)

### Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r pyproject.toml
   # or if using uv:
   uv sync
   ```

3. Create a `.env` file with your API keys:
   ```
   GEMINI_API_KEY=your_gemini_key_here
   SERPER_API_KEY=your_serper_key_here
   GEMINI_MODEL=gemini-2.0-flash
   ```
   
   **Note**: A direct Google search function using BeautifulSoup4 is available in `tools.py` as an alternative to Serper, but it's not consistent due to Google's anti-scraping measures. Serper API is recommended for reliable results.

### Running

```bash
chainlit run main.py
```

Then open your browser to the URL shown (typically `http://localhost:8000`)

## Features

- **Streaming Responses**: See agent thinking in real-time
- **Tool Visibility**: Watch as agents search and scrape the web
- **Multi-Perspective Analysis**: Get balanced views on complex topics
- **Conversation History**: Track the debate flow through all agents

## Tech Stack

- **AutoGen**: Multi-agent orchestration framework
- **Chainlit**: Interactive chat interface
- **Google Gemini**: LLM for agent reasoning
- **Crawl4AI**: Web scraping
- **Serper API**: Web search

## Configuration

Edit `config.py` to adjust:
- `MAX_MESSAGE_BEFRORRE_TERMINATION`: Maximum conversation length (default: 20)
- `GEMINI_MODEL`: Which Gemini model to use

## License

MIT

## Credits

Inspired by [tezansahu](https://github.com/tezansahu)