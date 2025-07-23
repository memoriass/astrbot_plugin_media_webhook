#!/usr/bin/env python3
"""
简单的语法检查脚本，用于验证插件代码的语法正确性
"""

import ast
import sys
import os

def check_syntax(file_path):
    """检查Python文件的语法"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        
        # 尝试解析AST
        ast.parse(source)
        print(f"✅ {file_path}: 语法检查通过")
        return True
        
    except SyntaxError as e:
        print(f"❌ {file_path}: 语法错误")
        print(f"   行 {e.lineno}: {e.text}")
        print(f"   错误: {e.msg}")
        return False
        
    except Exception as e:
        print(f"❌ {file_path}: 检查失败 - {e}")
        return False

def main():
    """主函数"""
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 要检查的文件
    files_to_check = [
        os.path.join(plugin_dir, 'main.py'),
        os.path.join(plugin_dir, 'test_webhook.py'),
        os.path.join(plugin_dir, 'check_syntax.py')
    ]
    
    print("开始语法检查...")
    print("=" * 50)
    
    all_passed = True
    for file_path in files_to_check:
        if os.path.exists(file_path):
            if not check_syntax(file_path):
                all_passed = False
        else:
            print(f"⚠️  文件不存在: {file_path}")
    
    print("=" * 50)
    if all_passed:
        print("🎉 所有文件语法检查通过！")
        return 0
    else:
        print("❌ 部分文件存在语法错误")
        return 1

if __name__ == "__main__":
    sys.exit(main())
