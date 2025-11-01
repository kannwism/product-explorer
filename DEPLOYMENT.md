# Deployment Guide

This guide explains how to deploy generated MDX course files to Supabase and trigger the MkDocs site deployment on Vercel.

## Overview

The deployment pipeline:
1. Uploads MDX files to Supabase storage
2. Gets public URLs for uploaded files
3. Triggers edge function to create MkDocs site and deploy to Vercel

## Setup

### Environment Variables

Add these to your `.env` file:

```bash
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
GITHUB_TOKEN=github_pat_xxxxx
```

These are already configured in the project `.env` file.

## Usage

### Option 1: Using the Convenience Function

The easiest way to deploy MDX files:

```python
from supabase_deployer import deploy_from_exploration

# Deploy MDX files from an exploration
result = deploy_from_exploration(
    mdx_files=[
        "outputs/course_1_getting-started.mdx",
        "outputs/course_2_advanced-features.mdx",
        "outputs/course_3_integration.mdx"
    ],
    product_url="https://app.example.com",
    output_dir="./outputs"
)

print(f"Deployed {len(result['uploaded_files'])} files")
print(f"Site: {result['site_name']}")
```

### Option 2: Using the Class Directly

For more control:

```python
from supabase_deployer import SupabaseDeployer
import os

# Initialize deployer
deployer = SupabaseDeployer(
    supabase_url=os.getenv('SUPABASE_URL'),
    supabase_anon_key=os.getenv('SUPABASE_ANON_KEY'),
    github_token=os.getenv('GITHUB_TOKEN'),
    storage_bucket="shared"  # default bucket
)

# Upload files
uploaded_files = deployer.upload_mdx_files(
    mdx_files=[
        "outputs/course_1.mdx",
        "outputs/course_2.mdx"
    ],
    base_remote_dir="courses/my-product"
)

# Trigger deployment
deployment_result = deployer.trigger_docs_deployment(
    uploaded_files=uploaded_files,
    site_name="My Product Docs",
    branch_name="docs-v1"  # optional, auto-generated if not provided
)

print(f"Deployment response: {deployment_result}")
```

### Option 3: Command Line

Deploy MDX files directly from the command line:

```bash
python supabase_deployer.py outputs/course_*.mdx
```

This will:
- Upload all matching MDX files to Supabase
- Trigger the edge function
- Print the deployment result

## Integration with explore.py

To integrate this into your exploration workflow (after your colleague finishes working on explore.py), you can add this at the end of the exploration:

```python
# After MDX files are generated
if mdx_files:  # List of generated MDX file paths
    from supabase_deployer import deploy_from_exploration

    try:
        deployment_result = deploy_from_exploration(
            mdx_files=mdx_files,
            product_url=product_url,
            output_dir=output_dir
        )

        print(f"\n📚 Docs deployed!")
        print(f"Site: {deployment_result['site_name']}")

        # Optional: Add deployment info to exploration result
        exploration_data['deployment'] = deployment_result

    except Exception as e:
        print(f"⚠️  Deployment failed (exploration still saved): {e}")
```

## Output Files

### Uploaded Files

MDX files are uploaded to Supabase storage with this structure:

```
courses/
  {domain}/
    {timestamp}/
      course_1_slug.mdx
      course_2_slug.mdx
      course_3_slug.mdx
      ...
```

Example:
```
courses/app_example_com/20251101_123456/course_1_getting-started.mdx
```

### Deployment Info File

A deployment info JSON file is saved locally:

```json
{
  "product_url": "https://app.example.com",
  "site_name": "App Example Com",
  "timestamp": "20251101_123456",
  "remote_directory": "courses/app_example_com/20251101_123456",
  "uploaded_files": [
    {
      "local_path": "outputs/course_1.mdx",
      "remote_path": "courses/app_example_com/20251101_123456/course_1.mdx",
      "public_url": "https://xxx.supabase.co/storage/v1/object/shared/public/..."
    }
  ],
  "deployment_response": {
    // Response from edge function
  }
}
```

## How It Works

### 1. File Upload to Supabase

The deployer uploads each MDX file to Supabase storage using the Storage API:

```
POST https://xxx.supabase.co/storage/v1/object/{bucket}/{path}
Authorization: Bearer {anon_key}
```

If a file already exists, it uses PUT to update it.

### 2. Edge Function Trigger

The deployer calls your edge function with the file URLs:

```
POST https://xxx.supabase.co/functions/v1/add-files-to-repo
Authorization: Bearer {anon_key}
Content-Type: application/json

{
  "name": "Product Name",
  "fileUrls": [
    {
      "url": "https://xxx.supabase.co/storage/v1/object/shared/public/...",
      "path": "docs/course_1.mdx"
    }
  ],
  "branchName": "docs-20251101-123456",
  "githubToken": "github_pat_xxxxx"
}
```

The edge function then:
- Creates a new branch in the GitHub repo
- Downloads the MDX files
- Creates the MkDocs site structure
- Deploys to Vercel

## Error Handling

The deployer includes error handling for common issues:

### File Not Found
```python
FileNotFoundError: File not found: outputs/course_1.mdx
```
Make sure the MDX files exist before deploying.

### Missing Environment Variables
```python
ValueError: SUPABASE_URL not provided and not found in environment
```
Check your `.env` file has all required variables.

### Upload Failed
If a file fails to upload, the deployer continues with other files and reports the error:
```
❌ Failed to upload course_2.mdx: HTTP 403 Forbidden
```

Check your Supabase storage permissions and bucket configuration.

### Edge Function Failed
```python
requests.exceptions.HTTPError: 500 Server Error
```
Check the edge function logs in Supabase dashboard.

## Testing

You can test the deployment without explore.py:

```bash
# Create a test MDX file
echo "# Test Course" > test.mdx

# Deploy it
python supabase_deployer.py test.mdx
```

This will upload the file and trigger the edge function.

## Troubleshooting

### Storage Permissions

If uploads fail with 403 errors, check your Supabase bucket permissions:
1. Go to Supabase Dashboard → Storage
2. Select the "shared" bucket
3. Ensure "Public bucket" is enabled or RLS policies allow uploads

### Edge Function Timeout

If the edge function times out:
- Check the Supabase function logs
- Verify GitHub token has correct permissions
- Ensure the repo exists and is accessible

### Invalid MDX

If deployment succeeds but Vercel build fails:
- Validate MDX syntax locally: `npx @mdx-js/mdx file.mdx`
- Check for missing imports or invalid components
- Review Vercel build logs

## Next Steps

After deployment:
1. Check the edge function response for the Vercel deployment URL
2. Visit the deployed site to verify the docs are correct
3. Share the docs URL with your team
