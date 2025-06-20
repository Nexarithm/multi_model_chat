# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

**Start the server:**
```bash
python3 server.py
```
The server runs on http://localhost:3000 and serves the web interface.

**Install dependencies:**
```bash
pip install proxai
```
The application requires the `proxai` library for multi-model AI interactions.

**Environment variables:**
- `PROXDASH_API_KEY` (optional) - API key for ProxAI dashboard integration

**Check server logs:**
The server provides detailed colored logging output showing model loading, query progress, and response timing. Monitor the console for real-time status updates.

## Architecture Overview

This is a multi-model AI chat application that allows users to query multiple AI models simultaneously and combine their responses. The architecture consists of:

### Core Components

**server.py** - Python HTTP server that:
- Fetches available AI models using ProxAI's `list_models()` with `model_size='largest'`
- Handles parallel querying of selected models using `concurrent.futures.ThreadPoolExecutor`
- Implements response combination using a designated "combiner model" 
- Maintains chat history as a global list of message objects
- Manages asynchronous job processing with unique job IDs
- Provides real-time progress tracking for multi-model queries
- Serves static files (HTML/CSS) and provides REST API endpoints

**index.html** - Single-page web application with:
- Model selection interface that loads available models dynamically
- Chat interface for real-time conversation
- JavaScript handling for async communication with Python backend

### Key Workflows

**Model Selection Flow:**
1. Frontend fetches available models from `/models` endpoint
2. Backend calls `get_largest_models()` which filters ProxAI models (excludes deepseek-r1, prefers deepseek-v3)
3. User selects multiple models for querying and one combiner model
4. Selection is stored in frontend state for chat session

**Chat Flow:**
1. User message sent to `/chat` endpoint with selected models and combiner model
2. Backend creates a unique job ID and starts asynchronous processing
3. Frontend polls `/job/{job_id}` endpoint for status updates
4. Backend queries all selected models in parallel using `query_all_models_parallel()`
5. Progress is tracked and available via `/progress` endpoint for real-time updates
6. Successful responses are combined using the combiner model with a synthesis prompt
7. Combined response is added to chat history and returned to frontend via job completion

### ProxAI Integration

The application uses ProxAI (`px`) for:
- `px.models.list_models()` - Discovering available AI models
- `px.generate_text()` - Querying individual models with system prompts, chat history, and parameters
- Provider/model tuples for routing requests to specific AI services

Model responses include timing information and error handling for failed queries. The combiner model receives a special prompt to synthesize multiple AI responses into a coherent answer.

## File Structure

- `server.py` - Main Python server handling HTTP requests, model management, and parallel querying
- `index.html` - Frontend single-page application with model selection and chat interface  
- `style.css` - CSS styling for the web interface
- `README.md` - Basic project description

## Key Functions and Entry Points

**server.py key functions:**
- `get_largest_models()` - Fetches and filters available AI models from ProxAI 
- `query_all_models_parallel()` - Executes parallel queries to selected models
- `_process_chat_models()` - Main chat processing logic with response combination
- `create_job()` / `get_job()` / `update_job()` - Job management system for async processing
- `log_message()` - Pretty colored logging with timestamps and formatting
- `run_server()` - Server initialization and startup

**API Endpoints:**
- `GET /models` - Returns available AI models from ProxAI
- `POST /chat` - Initiates chat processing and returns job ID
- `GET /job/{job_id}` - Returns job status and results
- `GET /progress` - Returns real-time progress of current processing

**Model filtering logic:**
- Excludes `deepseek-r1` model automatically
- Adds `deepseek-v3` as fallback if no deepseek models are available
- Uses ProxAI's `model_size='largest'` parameter for model discovery