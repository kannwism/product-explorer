# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Product Explorer is an automated product documentation pipeline that uses AI browser automation to explore web applications, sign up for accounts, and generate comprehensive educational content. The system:

1. Automatically signs up for products using temporary emails (AgentMail)
2. Handles email verification (links or codes) via GPT-4o extraction
3. Explores products thoroughly using Browser-Use Cloud API
4. Generates educational demos using OpenAI o3-mini
5. Executes courses in parallel with live video recording
6. Produces production-ready MDX documentation with embedded screenshots

## Core Architecture

### Main Components

**product_explorer.py** - Core exploration engine
- `ProductExplorer` class orchestrates the full exploration workflow
- Creates Browser-Use Cloud sessions and tasks
- Monitors email verification in background asyncio task
- When verification link arrives, stops old session and creates new session starting at verification URL
- Updates `self.task_id` dynamically so `wait_for_task_completion()` follows the new task
- Parses LLM output using regex to extract structured actions
- Saves JSON data and human-readable TXT reports

**explore.py** - CLI entry point
- Validates URLs and API keys
- Orchestrates full pipeline: exploration → demos → course execution → MDX generation
- Handles `--no-demos` and `--execute-courses` flags
- Loads `.env` from parent directory (legacy path: `/Users/typham-swann/Desktop/yc-hackathon/.env`)

**demo_generator.py** - Educational content generation
- Uses OpenAI o3-mini with Pydantic structured outputs
- Generates 5 progressive courses (beginner → advanced)
- Produces `DemoCollection` with specific UI steps and learning objectives

**course_executor.py** - Parallel course execution
- Executes all demos simultaneously with unique emails per course
- Uses `LiveVideoRecorder` to capture browser sessions as WebM video files
- Creates timeline JSON files with timestamps and URLs for each step
- Saves execution reports with credentials and recording links

**mdx_generator.py** - Production documentation
- Converts execution results + demos into clean MDX files
- Embeds screenshots from course execution
- Uses simple, user-friendly language via GPT-4o processing
- Outputs ready for Next.js, Docusaurus, or other doc frameworks

**api.py** - FastAPI server
- `/explore` endpoint to trigger explorations via HTTP POST
- `/health` endpoint checks API key configuration
- `/outputs` endpoint lists generated files
- Runs explorations as background tasks

**live_video_recorder.py** - Video capture
- Records live browser sessions to WebM format
- Uses Playwright to download CDP session data
- Produces 1280x720 videos at ~1-3MB per minute
- Saves to outputs directory with session ID naming

### Data Flow

```
1. User provides product URL
   ↓
2. ProductExplorer creates temp email + password
   ↓
3. Browser-Use Cloud session created at product URL
   ↓
4. Task created with detailed exploration prompt
   ↓
5. Background email monitor watches for verification
   ↓
6. [If verification link] → Stop session, create new session at link, create new task
   ↓
7. wait_for_task_completion() polls current self.task_id
   ↓
8. Parse LLM output into structured actions
   ↓
9. Save JSON + TXT report
   ↓
10. [If --execute-courses] DemoGenerator creates courses
   ↓
11. [If --execute-courses] CourseExecutor runs all in parallel
   ↓
12. [If --execute-courses] MDXGenerator produces final docs
```

### Key Patterns

**Dynamic Task Switching**: When email verification occurs, the system:
- Stops the initial session
- Creates a new session starting at the verification URL
- Creates a continuation task on the new session
- Updates `self.task_id` so the main waiting loop follows the new task

**Async Email Monitoring**: Runs as a separate `asyncio.create_task()` that:
- Polls AgentMail inbox every 3 seconds
- Uses GPT-4o to extract verification URLs from email body
- Cancels itself when exploration completes

**Structured LLM Output**: Uses Pydantic models with OpenAI structured outputs for:
- Demo generation (DemoCollection, EducationalDemo, UIStep)
- MDX content generation (clean, user-friendly text)

**Parallel Execution**: CourseExecutor uses `asyncio.gather()` to:
- Run all courses simultaneously (each with unique email + session)
- Record videos in parallel using LiveVideoRecorder
- Generate timeline JSON logs per course

## Development Commands

### Setup
```bash
# Install dependencies (uses uv)
uv sync

# Activate virtual environment
source .venv/bin/activate

# Or just run with uv
uv run python explore.py <url>
```

### Running Explorations
```bash
# Basic exploration (exploration + demos)
python explore.py https://app.example.com

# Full pipeline (exploration + demos + execution + MDX)
python explore.py https://app.example.com --execute-courses

# Skip demo generation
python explore.py https://app.example.com --no-demos
```

### API Server
```bash
# Start server
uvicorn api:app --reload --port 8000

# Or with uv
uv run uvicorn api:app --reload --port 8000

# Test endpoints
curl http://localhost:8000/health
curl -X POST http://localhost:8000/explore -H "Content-Type: application/json" -d '{"url": "https://app.example.com"}'
curl http://localhost:8000/outputs
```

### Deployment (Render)
The project includes `render.yaml` for deployment. Server runs on port specified by `$PORT` environment variable.

## Environment Variables

Required in `.env` file:
- `AGENTMAIL_API_KEY` - Temporary email service (agentmail.to)
- `BROWSER_USE_API_KEY` - Browser automation (browser-use.com)
- `OPENAI_API_KEY` - LLM for verification extraction, demos, MDX generation

The explore.py script loads `.env` from parent directory by default for legacy compatibility.

## Output Files

All files saved to `outputs/` directory with timestamp and domain-based naming:

### Exploration
- `exploration_{domain}_{timestamp}.json` - Structured data
- `exploration_{domain}_{timestamp}_REPORT.txt` - Human-readable report

### Demos
- `demos_{domain}_{timestamp}_COURSES.md` - Markdown course listing
- `demos_{domain}_{timestamp}.json` - Structured demo data

### Course Execution
- `course_executions_{domain}_{timestamp}_REPORT.md` - Execution summary
- `course_executions_{domain}_{timestamp}.json` - Execution data
- `course_{N}_{session_id}_timeline.json` - Per-course timeline logs
- `course_{N}_{session_id}.webm` - Video recordings (if LiveVideoRecorder used)

### MDX Content
- `course_{N}_{slug}.mdx` - Production-ready documentation files

## Common Debugging Scenarios

### Exploration fails early
- Check the `share_url` in JSON output to watch browser recording
- Verify the product's signup flow matches expected patterns
- Review task output in JSON for error messages

### Verification hangs
- GPT-4o extraction may fail on unusual email formats
- Check 90s timeout in `get_verification_data()`
- Verify AgentMail inbox is receiving emails (check via AgentMail dashboard)

### Course execution fails
- Each course needs unique email - ensure AgentMail has available inboxes
- Browser-Use API rate limits may apply - check for 429 errors
- Timeline JSON will show where execution stopped

### MDX generation produces invalid syntax
- MDXGenerator uses GPT-4o to clean content - may need prompt tuning
- Check that screenshots exist from course execution
- Validate MDX with `npx @mdx-js/mdx path/to/file.mdx`

## API Integration Notes

### Browser-Use Cloud API
Base URL: `https://api.browser-use.com/api/v2`

Key endpoints used:
- `POST /sessions` - Create browser session
- `POST /tasks` - Create automation task
- `GET /tasks/{id}` - Poll task status
- `PATCH /sessions/{id}` - Stop session (action: "stop")
- `POST /sessions/{id}/public-share` - Get recording share URL

Headers: `X-Browser-Use-API-Key: {key}`

### AgentMail API
Uses `agentmail` Python SDK:
- `AsyncAgentMail.inboxes.create()` - Create inbox
- `AsyncAgentMail.inboxes.messages.list()` - Poll for messages
- `AsyncAgentMail.inboxes.messages.get()` - Get full message

## Code Quality Notes

- All async operations use `asyncio` with proper error handling
- Retry logic implemented for Browser-Use API (rate limit handling)
- Timeouts configured for email verification (90s default)
- File I/O uses `pathlib.Path` consistently
- API keys validated before starting long-running operations
- Output files use descriptive naming with timestamps
