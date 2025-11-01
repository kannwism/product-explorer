"""
FastAPI server for Product Explorer
Simple API to trigger product explorations
"""

import asyncio
import os
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, HttpUrl
from pathlib import Path
from typing import List
from explore import explore_product_cli
from supabase_deployer import deploy_from_exploration
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Product Explorer API",
    description="Automated product exploration and documentation",
    version="1.0.0"
)


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


async def run_exploration(url: str, generate_demos: bool, execute_courses: bool):
    """Background task to run product exploration"""
    try:
        print(f"\n{'='*80}")
        print(f"Starting exploration: {url}")
        print(f"{'='*80}\n")

        await explore_product_cli(
            product_url=str(url),
            generate_demos=generate_demos,
            execute_courses=execute_courses
        )

        print(f"\n{'='*80}")
        print(f"Completed exploration: {url}")
        print(f"{'='*80}\n")

    except Exception as e:
        print(f"\n❌ Exploration failed for {url}: {e}")
        import traceback
        traceback.print_exc()


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

    # Queue the exploration in the background
    background_tasks.add_task(
        run_exploration,
        str(request.url),
        request.generate_demos,
        request.execute_courses
    )

    return ExploreResponse(
        status="started",
        url=str(request.url),
        message=f"Product exploration started for {request.url}. This will take 5-10 minutes. Results will be saved to the outputs directory."
    )


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
    uvicorn.run(app, host="0.0.0.0", port=8000)
