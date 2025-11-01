#!/usr/bin/env python3
"""
Product Explorer CLI - Command-line interface for exploring products

Usage:
    python explore.py <product_url>

Example:
    python explore.py https://app.example.com
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from product_explorer import ProductExplorer

# Load environment variables from parent directory
parent_dir = Path(__file__).parent.parent
load_dotenv(parent_dir / '.env')


def print_banner():
    """Print welcome banner."""
    print("\n" + "="*80)
    print("🔍 PRODUCT EXPLORER")
    print("="*80)
    print("Automated product analysis using AI browser automation")
    print("="*80 + "\n")


def check_api_keys():
    """Verify all required API keys are present."""
    required_keys = {
        'AGENTMAIL_API_KEY': 'AgentMail API Key',
        'BROWSER_USE_API_KEY': 'Browser-Use API Key',
        'OPENAI_API_KEY': 'OpenAI API Key'
    }
    
    missing_keys = []
    for key, name in required_keys.items():
        if not os.getenv(key):
            missing_keys.append(name)
    
    if missing_keys:
        print("❌ ERROR: Missing required API keys\n")
        print("The following API keys are required but not found in .env file:")
        for key in missing_keys:
            print(f"  - {key}")
        print("\nPlease add these keys to your .env file in the yc-hackathon directory.")
        print("Example .env format:")
        print("  AGENTMAIL_API_KEY=your_key_here")
        print("  BROWSER_USE_API_KEY=your_key_here")
        print("  OPENAI_API_KEY=your_key_here\n")
        return False
    
    return True


async def explore_product_cli(product_url: str, generate_demos: bool = True, execute_courses: bool = False):
    """Run the product exploration."""
    
    # Validate URL
    if not product_url.startswith(('http://', 'https://')):
        print(f"❌ ERROR: Invalid URL format: {product_url}")
        print("URL must start with http:// or https://\n")
        return
    
    print(f"🎯 Target: {product_url}\n")
    print("This will:")
    print("  1. Create a temporary email account")
    print("  2. Sign up for the product")
    print("  3. Handle email verification automatically")
    print("  4. Thoroughly explore the product interface")
    print("  5. Document all features and user actions")
    print("  6. Save a comprehensive report")
    if generate_demos:
        print("  7. Generate educational demos using AI (o3 model)")
    if execute_courses:
        print("  8. Execute all courses in parallel and create recordings\n")
    else:
        print("\n")
    
    # Get API keys
    agentmail_key = os.getenv('AGENTMAIL_API_KEY')
    browser_use_key = os.getenv('BROWSER_USE_API_KEY')
    openai_key = os.getenv('OPENAI_API_KEY')
    
    # Create explorer
    output_dir = Path(__file__).parent / "outputs"
    
    explorer = ProductExplorer(
        agentmail_api_key=agentmail_key,
        browser_use_api_key=browser_use_key,
        openai_api_key=openai_key,
        output_dir=str(output_dir)
    )
    
    try:
        # Run exploration
        result = await explorer.explore_product(product_url)
        
        # Print summary
        print("\n" + "="*80)
        print("✅ EXPLORATION COMPLETE!")
        print("="*80)
        print(f"Status: {result['status']}")
        print(f"Duration: {result['duration_seconds']:.1f} seconds\n")
        
        print("📄 Generated Files:")
        print(f"  Report:     {result['saved_files']['txt']}")
        print(f"  JSON Data:  {result['saved_files']['json']}")
        
        if result.get('share_url'):
            print(f"\n📺 Watch Recording:")
            print(f"  {result['share_url']}")
        
        print("\n💡 Next Steps:")
        print(f"  1. Read the report: cat '{result['saved_files']['txt']}'")
        print(f"  2. Review the JSON data for structured information")
        if result.get('share_url'):
            print(f"  3. Watch the browser recording to see the exploration")
        
        # Generate educational demos if enabled
        if generate_demos and result['success']:
            print("\n" + "="*80)
            print("🎓 Generating Educational Demos...")
            print("="*80 + "\n")
            
            try:
                from demo_generator import DemoGenerator
                
                generator = DemoGenerator(openai_api_key=openai_key)
                demo_collection = generator.generate_demos(
                    exploration_data=result,
                    num_demos=5,
                    max_tokens=16000
                )
                
                demo_files = generator.save_demos(
                    demo_collection=demo_collection,
                    exploration_data=result,
                    output_dir=output_dir
                )
                
                print("="*80)
                print("✅ EDUCATIONAL DEMOS GENERATED!")
                print("="*80)
                print(f"Courses: {len(demo_collection.demos)} demos created")
                print(f"Markdown: {demo_files['markdown']}")
                print(f"JSON: {demo_files['json']}")
                print("\n💡 Additional Next Steps:")
                print(f"  4. Review the educational demos: cat '{demo_files['markdown']}'")
                print(f"  5. Use demos to create tutorials or onboarding content")
                
                # Execute courses if enabled
                if execute_courses:
                    print("\n" + "="*80)
                    print("🎬 Executing Educational Courses...")
                    print("="*80 + "\n")
                    
                    try:
                        from course_executor import CourseExecutor
                        
                        executor = CourseExecutor(
                            agentmail_api_key=agentmail_key,
                            browser_use_api_key=browser_use_key,
                            openai_api_key=openai_key,
                            output_dir=str(output_dir)
                        )
                        
                        # Execute courses
                        execution_results = await executor.execute_all_courses(
                            demo_collection.model_dump(),
                            product_url
                        )
                        
                        # Save execution results
                        execution_report = executor.save_execution_results(
                            execution_results,
                            demo_collection.model_dump(),
                            output_dir
                        )
                        
                        print("="*80)
                        print("✅ COURSE EXECUTION COMPLETE!")
                        print("="*80)
                        print(f"Execution report: {execution_report}")
                        successful = sum(1 for r in execution_results if isinstance(r, dict) and r.get('status') == 'finished')
                        print(f"Successful: {successful}/{len(execution_results)}")
                        
                        # Generate MDX course content
                        print("\n" + "="*80)
                        print("🎨 Generating Clean MDX Course Content...")
                        print("="*80 + "\n")
                        
                        try:
                            from mdx_generator import MDXGenerator
                            
                            # Get product context from exploration
                            product_context = {
                                'product_name': demo_collection.product_name,
                                'product_url': product_url,
                                'product_overview': result.get('raw_analysis', '')[:1000]
                            }
                            
                            mdx_gen = MDXGenerator(openai_api_key=openai_key)
                            mdx_files = mdx_gen.generate_all_course_mdx(
                                demo_collection.model_dump(),
                                execution_results,
                                product_context,
                                output_dir
                            )
                            
                            print("="*80)
                            print("✅ MDX COURSE CONTENT GENERATED!")
                            print("="*80)
                            print(f"MDX files: {len(mdx_files)} courses")
                            for mdx_file in mdx_files:
                                print(f"  - {Path(mdx_file).name}")

                            # Deploy to Supabase
                            print("\n" + "="*80)
                            print("🚀 Deploying to Supabase...")
                            print("="*80 + "\n")

                            try:
                                from supabase_deployer import deploy_from_exploration

                                deployment_result = deploy_from_exploration(
                                    mdx_files=mdx_files,
                                    product_url=product_url,
                                    output_dir=str(output_dir)
                                )

                                print("="*80)
                                print("✅ DEPLOYMENT COMPLETE!")
                                print("="*80)
                                print(f"Site: {deployment_result['site_name']}")
                                print(f"Files deployed: {len(deployment_result['uploaded_files'])}")
                                if 'info_file' in deployment_result:
                                    print(f"Deployment info: {deployment_result['info_file']}")
                                print("="*80)

                                print("\n💡 Additional Next Steps:")
                                print(f"  6. Review execution report: cat '{execution_report}'")
                                print(f"  7. Watch course recordings to see demos in action")
                                print(f"  8. View MDX course content (ready for docs site)")
                                print(f"  9. Check deployment info for Supabase URLs")

                            except Exception as e:
                                print(f"\n⚠️  Supabase deployment failed: {e}")
                                import traceback
                                traceback.print_exc()
                                print("\n💡 Additional Next Steps:")
                                print(f"  6. Review execution report: cat '{execution_report}'")
                                print(f"  7. Watch course recordings to see demos in action")
                                print(f"  8. View MDX course content (ready for docs site)")

                        except Exception as e:
                            print(f"\n⚠️  MDX generation failed: {e}")
                            import traceback
                            traceback.print_exc()
                            print("\n💡 Additional Next Steps:")
                            print(f"  6. Review execution report: cat '{execution_report}'")
                            print(f"  7. Watch course recordings to see demos in action")
                        
                    except Exception as e:
                        print(f"\n⚠️  Course execution failed: {e}")
                        import traceback
                        traceback.print_exc()
                
            except Exception as e:
                print(f"\n⚠️  Demo generation failed (exploration still saved): {e}")
        
        print("\n" + "="*80 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Exploration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: Exploration failed")
        print(f"   {str(e)}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """Main CLI entry point."""
    print_banner()
    
    # Check for URL argument
    if len(sys.argv) < 2:
        print("❌ ERROR: No product URL provided\n")
        print("Usage:")
        print(f"  python {sys.argv[0]} <product_url> [--no-demos] [--execute-courses]\n")
        print("Options:")
        print(f"  --no-demos          Skip educational demo generation")
        print(f"  --execute-courses   Execute and record all generated courses\n")
        print("Example:")
        print(f"  python {sys.argv[0]} https://app.example.com --execute-courses\n")
        sys.exit(1)
    
    product_url = sys.argv[1]
    
    # Check for flags
    generate_demos = '--no-demos' not in sys.argv
    execute_courses = '--execute-courses' in sys.argv
    
    # Check API keys
    if not check_api_keys():
        sys.exit(1)
    
    # Run exploration
    asyncio.run(explore_product_cli(product_url, generate_demos=generate_demos, execute_courses=execute_courses))


if __name__ == "__main__":
    main()

