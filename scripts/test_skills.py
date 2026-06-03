import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rocky.config import load_config
from rocky.skills.manager import SkillManager
from rocky.skills.regression import SkillRegression
from rocky.engine.llm_client import LLMClient
from rocky.workers.coder import CoderWorker
from rocky.workers.reasoner import ReasonerWorker
from rocky.workers.writer import WriterWorker

async def main():
    print("[*] Running all active skill regression tests...")
    
    # Ensure config is loaded
    load_config()
    
    skill_manager = SkillManager()
    client = LLMClient()
    
    # Mock prompt builder
    from rocky.engine.prompt_builder import PromptBuilder
    prompt_builder = PromptBuilder()
    
    workers = {
        "coder": CoderWorker(client, prompt_builder),
        "reasoner": ReasonerWorker(client, prompt_builder),
        "writer": WriterWorker(client, prompt_builder)
    }
    
    def worker_factory(name):
        return workers[name]
        
    regression = SkillRegression(skill_manager, worker_factory)
    results = await regression.run_all_tests()
    
    if not results:
        print("[*] No active skills found to test.")
        return
        
    all_passed = True
    for name, success in results.items():
        status = "PASSED" if success else "FAILED"
        print(f"  - Skill '{name}': {status}")
        if not success:
            all_passed = False
            
    if all_passed:
        print("[+] All regression tests passed successfully.")
        sys.exit(0)
    else:
        print("[-] Some regression tests failed.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
