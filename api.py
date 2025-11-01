"""
FastAPI server for Product Explorer
Simple API to trigger product explorations
"""

import os
import sys
import logging
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, HttpUrl
from pathlib import Path
from typing import List, Dict, Optional
from explore import explore_product_cli
from supabase_deployer import deploy_from_exploration
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging to stdout so Render can see it
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Product Explorer API",
    description="Automated product exploration and documentation",
    version="1.0.0"
)

# In-memory task tracking (in production, use a database)
active_tasks: Dict[str, dict] = {}


class ExploreRequest(BaseModel):
    """Request to explore a product"""
    url: HttpUrl
    generate_demos: bool = True
    execute_courses: bool = False


class ExploreResponse(BaseModel):
    """Response when exploration starts"""
    status: str
    url: str
    message: str


class DeployRequest(BaseModel):
    """Request to deploy MDX files"""
    mdx_file_paths: List[str]
    product_url: HttpUrl


class DeployResponse(BaseModel):
    """Response when deployment completes"""
    status: str
    site_name: str
    files_deployed: int
    message: str


async def run_exploration(task_id: str, url: str, generate_demos: bool, execute_courses: bool):
    """Background task to run product exploration"""
    try:
        logger.info("="*80)
        logger.info(f"🚀 STARTING EXPLORATION: {url}")
        logger.info(f"Task ID: {task_id}")
        logger.info(f"Generate Demos: {generate_demos}")
        logger.info(f"Execute Courses: {execute_courses}")
        logger.info("="*80)

        # Update task status
        active_tasks[task_id]['status'] = 'running'
        active_tasks[task_id]['started_at'] = datetime.now().isoformat()

        await explore_product_cli(
            product_url=str(url),
            generate_demos=generate_demos,
            execute_courses=execute_courses
        )

        logger.info("="*80)
        logger.info(f"✅ COMPLETED EXPLORATION: {url}")
        logger.info(f"Task ID: {task_id}")
        logger.info("="*80)

        # Update task status
        active_tasks[task_id]['status'] = 'completed'
        active_tasks[task_id]['completed_at'] = datetime.now().isoformat()

    except Exception as e:
        logger.error("="*80)
        logger.error(f"❌ EXPLORATION FAILED: {url}")
        logger.error(f"Task ID: {task_id}")
        logger.error(f"Error: {e}")
        logger.error("="*80)
        import traceback
        traceback.print_exc()

        # Update task status
        active_tasks[task_id]['status'] = 'failed'
        active_tasks[task_id]['error'] = str(e)
        active_tasks[task_id]['failed_at'] = datetime.now().isoformat()


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "Product Explorer API",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    """Detailed health check"""

    # Check API keys
    api_keys = {
        "agentmail": bool(os.getenv('AGENTMAIL_API_KEY')),
        "browser_use": bool(os.getenv('BROWSER_USE_API_KEY')),
        "openai": bool(os.getenv('OPENAI_API_KEY'))
    }

    # Check outputs directory
    outputs_dir = Path(__file__).parent / "outputs"
    outputs_exists = outputs_dir.exists()

    all_keys_present = all(api_keys.values())

    return {
        "status": "healthy" if all_keys_present else "degraded",
        "api_keys": api_keys,
        "outputs_directory": {
            "exists": outputs_exists,
            "path": str(outputs_dir)
        }
    }


@app.post("/explore", response_model=ExploreResponse)
async def explore(request: ExploreRequest, background_tasks: BackgroundTasks):
    """
    Start a product exploration

    The exploration runs in the background and may take 5-10 minutes.
    Results are saved to the outputs directory on the server.
    """

    # Validate API keys
    if not os.getenv('AGENTMAIL_API_KEY'):
        raise HTTPException(status_code=500, detail="AGENTMAIL_API_KEY not configured")
    if not os.getenv('BROWSER_USE_API_KEY'):
        raise HTTPException(status_code=500, detail="BROWSER_USE_API_KEY not configured")
    if not os.getenv('OPENAI_API_KEY'):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    # Generate task ID
    task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Create task record
    active_tasks[task_id] = {
        'url': str(request.url),
        'status': 'queued',
        'generate_demos': request.generate_demos,
        'execute_courses': request.execute_courses,
        'created_at': datetime.now().isoformat()
    }

    logger.info(f"📝 Queued exploration task: {task_id} for {request.url}")

    # Queue the exploration in the background
    background_tasks.add_task(
        run_exploration,
        task_id,
        str(request.url),
        request.generate_demos,
        request.execute_courses
    )

    return ExploreResponse(
        status="started",
        url=str(request.url),
        message=f"Product exploration started (Task ID: {task_id}). Check /tasks/{task_id} for status. This will take 5-10 minutes."
    )


@app.get("/tasks")
async def list_tasks():
    """List all exploration tasks and their status"""
    return {
        "tasks": active_tasks,
        "count": len(active_tasks)
    }


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Get status of a specific exploration task"""
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return active_tasks[task_id]


@app.get("/outputs")
async def list_outputs():
    """List all exploration output files"""

    outputs_dir = Path(__file__).parent / "outputs"

    if not outputs_dir.exists():
        return {"files": [], "count": 0}

    files = []
    for file in sorted(outputs_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True):
        if file.is_file():
            files.append({
                "name": file.name,
                "size_mb": round(file.stat().st_size / 1024 / 1024, 2),
                "modified": file.stat().st_mtime
            })

    return {
        "files": files,
        "count": len(files),
        "directory": str(outputs_dir)
    }


@app.post("/deploy", response_model=DeployResponse)
async def deploy(request: DeployRequest):
    """
    Deploy MDX files to Supabase and trigger docs site deployment

    This endpoint:
    1. Uploads MDX files to Supabase storage
    2. Triggers the edge function to create MkDocs site
    3. Deploys to Vercel via GitHub

    Files can be:
    - Relative paths from outputs directory (e.g., "course_1.mdx")
    - Absolute paths (e.g., "/Users/mari/git/product-explorer/outputs/course_1.mdx")
    """

    # Validate Supabase API keys
    if not os.getenv('SUPABASE_URL'):
        raise HTTPException(status_code=500, detail="SUPABASE_URL not configured")
    if not os.getenv('SUPABASE_ANON_KEY'):
        raise HTTPException(status_code=500, detail="SUPABASE_ANON_KEY not configured")
    if not os.getenv('GITHUB_TOKEN'):
        raise HTTPException(status_code=500, detail="GITHUB_TOKEN not configured")

    # Resolve file paths
    outputs_dir = Path(__file__).parent / "outputs"
    resolved_paths = []

    for file_path in request.mdx_file_paths:
        path = Path(file_path)

        # If relative path, resolve from outputs directory
        if not path.is_absolute():
            path = outputs_dir / file_path

        # Check file exists
        if not path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"File not found: {file_path}"
            )

        # Check it's an MDX file
        if path.suffix.lower() != '.mdx':
            raise HTTPException(
                status_code=400,
                detail=f"File is not an MDX file: {file_path}"
            )

        resolved_paths.append(str(path))

    # Deploy the files
    try:
        result = deploy_from_exploration(
            mdx_files=resolved_paths,
            product_url=str(request.product_url),
            output_dir=str(outputs_dir)
        )

        return DeployResponse(
            status="success",
            site_name=result['site_name'],
            files_deployed=len(result['uploaded_files']),
            message=f"Successfully deployed {len(result['uploaded_files'])} files to {result['site_name']}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Deployment failed: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
