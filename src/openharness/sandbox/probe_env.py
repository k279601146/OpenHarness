import asyncio
from e2b_code_interpreter import Sandbox

async def check():
    print("--- Debugging 'npx skills find' ---")
    template_id = "nlhz8vlwyupq845jsdg9"
    api_key = "e2b_95ff0a89ea3077bb41c9cb33430ee1c35d8fcf07"
    try:
        sbx = Sandbox.create(template_id, api_key=api_key)
        try:
            # 模拟 Agent 的调用，但我们要看 stdout 和 stderr
            print("Running: npx --yes skills find ppt")
            res = sbx.commands.run("npx --yes skills find ppt")
            
            print(f"Exit Code: {res.exit_code}")
            print(f"STDOUT: '{res.stdout}'")
            print(f"STDERR: '{res.stderr}'")
            
            if not res.stdout and not res.stderr:
                print("Checking network...")
                net_res = sbx.commands.run("curl -I https://skills.sh")
                print(f"Network Check (skills.sh): {net_res.exit_code}")

        finally:
            sbx.kill()

    except Exception as e:
        print(f"Execution failed: {e}")

if __name__ == "__main__":
    asyncio.run(check())
