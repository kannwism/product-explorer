"""
Supabase Deployer - Upload MDX files to Supabase and trigger docs deployment
Handles the full pipeline from local MDX files to deployed MkDocs site on Vercel
"""

import os
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import urlparse
import json


class SupabaseDeployer:
    """Deploy generated MDX files to Supabase and trigger docs site deployment"""

    def __init__(
        self,
        supabase_url: str,
        supabase_anon_key: str,
        github_token: str,
        storage_bucket: str = "shared"
    ):
        """
        Initialize the Supabase deployer.

        Args:
            supabase_url: Supabase project URL (e.g., https://xxx.supabase.co)
            supabase_anon_key: Supabase anonymous/public key
            github_token: GitHub personal access token for deployment
            storage_bucket: Supabase storage bucket name (default: "shared")
        """
        self.supabase_url = supabase_url.rstrip('/')
        self.supabase_anon_key = supabase_anon_key
        self.github_token = github_token
        self.storage_bucket = storage_bucket

        # Edge function endpoint
        self.edge_function_url = f"{self.supabase_url}/functions/v1/add-files-to-repo"

        # Storage API endpoint
        self.storage_url = f"{self.supabase_url}/storage/v1/object/{self.storage_bucket}"

    def upload_file(self, file_path: str, remote_path: Optional[str] = None) -> Dict[str, str]:
        """
        Upload a file to Supabase storage.

        Args:
            file_path: Local path to the file
            remote_path: Remote path in storage bucket (if None, uses filename)

        Returns:
            Dict with 'local_path', 'remote_path', and 'public_url'
        """
        file_path_obj = Path(file_path)

        if not file_path_obj.exists():
            raise FileNotFoundError(f"File not found: {file_path_obj}")

        # Determine remote path
        if remote_path is None:
            remote_path = file_path_obj.name

        # Remove leading slash if present
        remote_path = remote_path.lstrip('/')

        print(f"   📤 Uploading {file_path_obj.name} to {remote_path}...")

        # Read file content
        with open(file_path_obj, 'rb') as f:
            file_content = f.read()

        # Upload to Supabase storage
        headers = {
            'Authorization': f'Bearer {self.supabase_anon_key}',
            'Content-Type': 'application/octet-stream'
        }

        upload_url = f"{self.storage_url}/{remote_path}"

        response = requests.post(
            upload_url,
            headers=headers,
            data=file_content
        )

        if response.status_code not in [200, 201]:
            # Try upsert if file exists
            response = requests.put(
                upload_url,
                headers=headers,
                data=file_content
            )

        response.raise_for_status()

        # Construct public URL
        public_url = f"{self.storage_url}/public/{remote_path}"

        print(f"   ✅ Uploaded to: {public_url}")

        return {
            'local_path': str(file_path_obj),
            'remote_path': remote_path,
            'public_url': public_url
        }

    def upload_mdx_files(
        self,
        mdx_files: List[str],
        base_remote_dir: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Upload multiple MDX files to Supabase storage.

        Args:
            mdx_files: List of local MDX file paths
            base_remote_dir: Base directory in storage (e.g., "courses/product-name")

        Returns:
            List of upload results with local_path, remote_path, and public_url
        """
        print(f"\n{'='*80}")
        print(f"📤 UPLOADING MDX FILES TO SUPABASE")
        print(f"{'='*80}")
        print(f"Files to upload: {len(mdx_files)}")
        print(f"Storage bucket: {self.storage_bucket}")
        if base_remote_dir:
            print(f"Remote directory: {base_remote_dir}")
        print(f"{'='*80}\n")

        uploaded_files = []

        for file_path in mdx_files:
            file_path = Path(file_path)

            # Determine remote path
            if base_remote_dir:
                remote_path = f"{base_remote_dir.rstrip('/')}/{file_path.name}"
            else:
                remote_path = file_path.name

            try:
                result = self.upload_file(str(file_path), remote_path)
                uploaded_files.append(result)
            except Exception as e:
                print(f"   ❌ Failed to upload {file_path.name}: {e}")
                # Continue with other files

        print(f"\n✅ Uploaded {len(uploaded_files)}/{len(mdx_files)} files successfully\n")

        return uploaded_files

    def trigger_docs_deployment(
        self,
        uploaded_files: List[Dict[str, str]],
        site_name: str,
        branch_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Trigger the edge function to deploy docs to Vercel.

        Args:
            uploaded_files: List of uploaded file info (from upload_mdx_files)
            site_name: Name for the docs site
            branch_name: Git branch name (if None, generates timestamp-based name)

        Returns:
            Response from the edge function
        """
        print(f"{'='*80}")
        print(f"🚀 TRIGGERING DOCS DEPLOYMENT")
        print(f"{'='*80}")
        print(f"Site name: {site_name}")

        # Generate branch name if not provided
        if branch_name is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            branch_name = f"docs-{timestamp}"

        print(f"Branch: {branch_name}")
        print(f"Files: {len(uploaded_files)}")
        print(f"{'='*80}\n")

        # Build file URLs array for edge function
        file_urls = []
        for file_info in uploaded_files:
            file_urls.append({
                'url': file_info['public_url'],
                'path': f"docs/{Path(file_info['remote_path']).name}"
            })

        # Prepare request payload
        payload = {
            'name': site_name,
            'fileUrls': file_urls,
            'branchName': branch_name,
            'githubToken': self.github_token
        }

        # Make request to edge function
        headers = {
            'Authorization': f'Bearer {self.supabase_anon_key}',
            'Content-Type': 'application/json'
        }

        print("📡 Calling edge function...")
        print(f"   Endpoint: {self.edge_function_url}")

        response = requests.post(
            self.edge_function_url,
            headers=headers,
            json=payload
        )

        response.raise_for_status()
        result = response.json()

        print(f"\n✅ Deployment triggered successfully!")
        print(f"{'='*80}")

        if isinstance(result, dict):
            for key, value in result.items():
                print(f"   {key}: {value}")
        else:
            print(f"   Response: {result}")

        print(f"{'='*80}\n")

        return result

    def deploy_exploration_docs(
        self,
        mdx_files: List[str],
        product_url: str,
        output_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Complete deployment pipeline: upload MDX files and trigger deployment.

        Args:
            mdx_files: List of local MDX file paths to deploy
            product_url: The product URL that was explored (for naming)
            output_dir: Optional output directory to save deployment info

        Returns:
            Dict with deployment information including URLs and response
        """
        print(f"\n{'='*80}")
        print(f"📦 COMPLETE DOCS DEPLOYMENT PIPELINE")
        print(f"{'='*80}")
        print(f"Product: {product_url}")
        print(f"MDX files: {len(mdx_files)}")
        print(f"{'='*80}\n")

        # Extract product name from URL for naming
        parsed = urlparse(product_url)
        domain = parsed.netloc.replace('.', '_')
        site_name = domain.replace('_', ' ').title()

        # Create remote directory path
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        remote_dir = f"courses/{domain}/{timestamp}"

        # Upload files
        uploaded_files = self.upload_mdx_files(mdx_files, remote_dir)

        if not uploaded_files:
            raise Exception("No files were uploaded successfully")

        # Trigger deployment
        deployment_result = self.trigger_docs_deployment(
            uploaded_files=uploaded_files,
            site_name=site_name
        )

        # Prepare deployment info
        deployment_info = {
            'product_url': product_url,
            'site_name': site_name,
            'timestamp': timestamp,
            'remote_directory': remote_dir,
            'uploaded_files': uploaded_files,
            'deployment_response': deployment_result
        }

        # Save deployment info if output_dir provided
        if output_dir:
            output_path = Path(output_dir)
            info_file = output_path / f"deployment_{domain}_{timestamp}.json"

            with open(info_file, 'w') as f:
                json.dump(deployment_info, f, indent=2)

            print(f"💾 Deployment info saved to: {info_file}\n")
            deployment_info['info_file'] = str(info_file)

        return deployment_info


def deploy_from_exploration(
    mdx_files: List[str],
    product_url: str,
    output_dir: str = "./outputs",
    supabase_url: Optional[str] = None,
    supabase_anon_key: Optional[str] = None,
    github_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convenience function to deploy MDX files from an exploration.
    Loads credentials from environment variables if not provided.

    Args:
        mdx_files: List of MDX file paths to deploy
        product_url: The product URL that was explored
        output_dir: Output directory for deployment info
        supabase_url: Supabase URL (or from SUPABASE_URL env var)
        supabase_anon_key: Supabase anon key (or from SUPABASE_ANON_KEY env var)
        github_token: GitHub token (or from GITHUB_TOKEN env var)

    Returns:
        Deployment information dict
    """
    # Load from environment if not provided
    supabase_url = supabase_url or os.getenv('SUPABASE_URL')
    supabase_anon_key = supabase_anon_key or os.getenv('SUPABASE_ANON_KEY')
    github_token = github_token or os.getenv('GITHUB_TOKEN')

    # Validate credentials
    if not supabase_url:
        raise ValueError("SUPABASE_URL not provided and not found in environment")
    if not supabase_anon_key:
        raise ValueError("SUPABASE_ANON_KEY not provided and not found in environment")
    if not github_token:
        raise ValueError("GITHUB_TOKEN not provided and not found in environment")

    # Create deployer and deploy
    deployer = SupabaseDeployer(
        supabase_url=supabase_url,
        supabase_anon_key=supabase_anon_key,
        github_token=github_token
    )

    return deployer.deploy_exploration_docs(
        mdx_files=mdx_files,
        product_url=product_url,
        output_dir=output_dir
    )


# Example usage
if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    load_dotenv()

    if len(sys.argv) < 2:
        print("Usage: python supabase_deployer.py <mdx_file1> [mdx_file2] ...")
        print("\nExample:")
        print("  python supabase_deployer.py outputs/course_1_*.mdx outputs/course_2_*.mdx")
        print("\nEnvironment variables required:")
        print("  SUPABASE_URL - Your Supabase project URL")
        print("  SUPABASE_ANON_KEY - Your Supabase anonymous key")
        print("  GITHUB_TOKEN - Your GitHub personal access token")
        sys.exit(1)

    mdx_files = sys.argv[1:]

    # For testing, use a dummy product URL
    product_url = "https://app.example.com"

    try:
        result = deploy_from_exploration(
            mdx_files=mdx_files,
            product_url=product_url
        )

        print("\n" + "="*80)
        print("✅ DEPLOYMENT COMPLETE")
        print("="*80)
        print(f"Site: {result['site_name']}")
        print(f"Files deployed: {len(result['uploaded_files'])}")
        if 'info_file' in result:
            print(f"Info: {result['info_file']}")
        print("="*80)

    except Exception as e:
        print(f"\n❌ Deployment failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
