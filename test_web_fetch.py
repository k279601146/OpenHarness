import asyncio
import sys
import os

# Ensure the src directory is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from openharness.tools.web_fetch_tool import WebFetchTool, WebFetchToolInput

async def main():
    print("Testing WebFetchTool with defuddle...")
    tool = WebFetchTool()
    
    # 构造输入参数
    arguments = WebFetchToolInput(url="https://github.com/kepano/defuddle")
    
    # 执行工具
    result = await tool.execute(arguments=arguments, context=None)
    
    print("\n--- Fetch Result ---")
    print(result.output)

if __name__ == "__main__":
    asyncio.run(main())
