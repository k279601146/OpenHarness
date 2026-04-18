"""安全文件操作验证器 - MVP 阶段白名单策略"""

from pathlib import Path
from typing import Tuple

# 允许的文件扩展名白名单
SAFE_EXTENSIONS = {
    # 文档类
    '.md', '.txt', '.csv', '.json', '.yaml', '.yml',
    # 代码类（仅文本，不执行）
    '.html', '.css', '.js', '.jsx', '.ts', '.tsx', 
    '.py', '.java', '.go', '.rs', '.cpp', '.c', '.h',
    # 数据类
    '.xml', '.toml', '.ini', '.sql',
    # 配置类
    '.conf', '.config', '.properties',
}

# 危险路径黑名单（不允许访问的目录名）
DANGEROUS_PATHS = {
    '.ssh', '.env', '.git', 'credentials', 'secrets',
    'config', '.aws', '.azure', '.gcp', 'private',
    'node_modules', '.venv', 'venv', '__pycache__',
}


def validate_safe_file_operation(
    file_path: str, 
    user_workspace: str,
    operation: str = "write"
) -> Tuple[bool, str]:
    """
    验证文件操作是否安全
    
    Args:
        file_path: 目标文件路径
        user_workspace: 用户工作区根目录
        operation: 操作类型 (write/edit/read)
    
    Returns:
        (is_safe, error_message)
    """
    try:
        p = Path(file_path)
        
        # 1. 扩展名白名单验证
        if p.suffix.lower() not in SAFE_EXTENSIONS:
            return False, (
                f"❌ 安全限制：不允许 {operation} {p.suffix or '无扩展名'} 类型文件。\n"
                f"允许的文件类型：{', '.join(sorted(SAFE_EXTENSIONS))}"
            )
        
        # 2. 路径沙箱限制
        resolved = p.resolve()
        workspace = Path(user_workspace).resolve()
        
        try:
            # 检查是否在工作区内
            resolved.relative_to(workspace)
        except ValueError:
            return False, (
                f"❌ 安全限制：不允许访问工作区外的文件。\n"
                f"工作区路径：{workspace}\n"
                f"尝试访问：{resolved}"
            )
        
        # 3. 危险路径黑名单
        path_parts = set(p.parts)
        dangerous_found = path_parts & DANGEROUS_PATHS
        if dangerous_found:
            return False, (
                f"❌ 安全限制：不允许访问敏感目录。\n"
                f"检测到危险路径：{', '.join(dangerous_found)}"
            )
        
        # 4. 文件名黑名单
        dangerous_names = {
            '.env', '.env.local', '.env.production',
            'id_rsa', 'id_ed25519', 'credentials.json',
            'secrets.yaml', 'private.key'
        }
        if p.name.lower() in dangerous_names:
            return False, (
                f"❌ 安全限制：不允许操作敏感配置文件。\n"
                f"文件名：{p.name}"
            )
        
        return True, ""
        
    except Exception as e:
        return False, f"❌ 路径验证失败：{str(e)}"


def get_safe_extensions_help() -> str:
    """返回允许的文件类型帮助信息"""
    categories = {
        "文档": ['.md', '.txt', '.csv'],
        "代码": ['.py', '.js', '.ts', '.html', '.css'],
        "数据": ['.json', '.yaml', '.xml', '.toml'],
        "配置": ['.ini', '.conf', '.properties'],
    }
    
    lines = ["📋 允许的文件类型：\n"]
    for category, exts in categories.items():
        lines.append(f"  {category}：{', '.join(exts)}")
    
    return "\n".join(lines)
